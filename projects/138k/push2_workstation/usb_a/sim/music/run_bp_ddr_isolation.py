#!/usr/bin/env python3
"""Reproduce the old DP/delay alias, then prove the isolated map with 172 frames."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--project', type=Path, help='Use CNN and DDR-map inputs from a staged workstation Prj1')
    args = parser.parse_args()
    out = args.output or ROOT / 'out' / datetime.now().strftime('bp_ddr_isolation_%Y%m%d_%H%M%S')
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    project = args.project.resolve() if args.project else ROOT
    music = project / 'rtl/music'
    memory = project / 'src/memory' if args.project else ROOT / 'rtl'
    vit = music / 'basic_pitch_viterbi.sv'
    header = music / 'basic_pitch_ddr_map.svh'
    text = header.read_text()
    needle = "BP_DDR_BPTR_BYTE_BASE       32'h3040_0000"
    assert text.count(needle) == 1, 'review negative control when BP allocation changes'
    old = out / 'basic_pitch_ddr_map_old.svh'
    old.write_text(text.replace(needle, "BP_DDR_BPTR_BYTE_BASE       32'h3000_0000"))
    negative = out / 'basic_pitch_viterbi_old_map.sv'
    negative.write_text(vit.read_text().replace('"basic_pitch_ddr_map.svh"', f'"{old}"'))
    tb = HERE / 'tb_viterbi_ddr_isolation.sv'
    inputs = [vit, header, tb, memory / 'ddr_address_map.vh',
              music / 'basic_pitch_fixed_pkg.svh', Path(__file__)]
    (out / 'inputs_sha256.json').write_text(json.dumps({
        str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in inputs}, indent=2) + '\n')

    def run(case):
        name, src = case
        start = time.monotonic()
        log = ''
        exe = out / (name + '.vvp')
        commands = [
            ['iverilog', '-g2012', '-I', str(music), '-I', str(memory),
             '-s', 'tb_viterbi_ddr_isolation', '-o', str(exe), str(src), str(tb)],
            ['vvp', str(exe)],
        ]
        for cmd in commands:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            log += result.stdout + result.stderr
            if result.returncode:
                break
        (out / (name + '.log')).write_text(log)
        confirmed = (result.returncode == 0 and 'PASS Viterbi DDR isolation oracle:' in log
                     if name == 'new_map' else
                     result.returncode != 0 and 'external backpointer' in log)
        record = {'case': name, 'expected_behavior_confirmed': confirmed,
                  'exit_code': result.returncode, 'seconds': round(time.monotonic() - start, 2)}
        print(json.dumps(record), flush=True)
        print(result.stdout.strip(), flush=True)
        return record

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [('old_map', negative), ('new_map', vit)]))
    (out / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print(out, flush=True)
    if not all(r['expected_behavior_confirmed'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
