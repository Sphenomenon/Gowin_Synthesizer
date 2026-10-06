#!/usr/bin/env python3
"""Compare pipelined CQT against immutable accepted RTL, including every DDR write."""
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TAG = 'cnn83-accepted-20261006'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = (args.output or ROOT / 'out' / datetime.now().strftime('cqt_pipeline_%Y%m%d_%H%M%S')).resolve()
    out.mkdir(parents=True, exist_ok=True)
    prefix = subprocess.check_output(['git', 'rev-parse', '--show-prefix'], cwd=ROOT, text=True).strip()
    old = subprocess.check_output(['git', 'show', TAG + ':' + prefix + 'rtl/music/basic_pitch_cqt_engine.sv'], cwd=ROOT)
    reference = out / 'basic_pitch_cqt_engine_reference.sv'
    # Share the unchanged RAM wrapper to avoid a duplicate module declaration.
    text = old.decode().split('module basic_pitch_signal_ram #', 1)[0]
    reference.write_text(text.replace('module basic_pitch_cqt_engine #', 'module basic_pitch_cqt_engine_reference #'))
    src = ROOT / 'rtl/music/basic_pitch_cqt_engine.sv'
    tb = Path(__file__).with_name('tb_cqt_pipeline_equivalence.sv')
    (out / 'inputs.json').write_text(json.dumps({
        'reference_tag': TAG, 'reference_sha256': hashlib.sha256(old).hexdigest(),
        'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in [src, tb, Path(__file__), ROOT / 'rtl/music/basic_pitch_ddr_map.svh',
                             ROOT / 'rtl/music/basic_pitch_fixed_pkg.svh']},
    }, indent=2) + '\n')

    def run(ddr):
        binary = out / ('cqt_' + str(ddr) + '.vvp')
        command = ['iverilog', '-g2012', '-I', str(ROOT / 'rtl/music'), '-s', 'tb_cqt_pipeline_equivalence',
                   '-Ptb_cqt_pipeline_equivalence.DDR=' + str(ddr), '-o', str(binary),
                   str(reference), str(src), str(tb)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        text = result.stdout + result.stderr
        if result.returncode == 0:
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=180)
            text += result.stdout + result.stderr
        (out / ('cqt_' + str(ddr) + '.log')).write_text(text)
        passed = result.returncode == 0 and 'PASS CQT pipeline/reference:' in text
        print('DDR', ddr, 'PASS' if passed else 'FAIL', result.stdout.strip(), flush=True)
        return {'ddr': ddr, 'passed': passed, 'exit_code': result.returncode}

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(run, [0, 1]))
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    if not all(r['passed'] for r in result):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
