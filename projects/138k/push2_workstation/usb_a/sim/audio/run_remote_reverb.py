#!/usr/bin/env python3
"""Verify the real W reverb, fixed M deadline and context/failure fences.

This is a synchronous logical-transport source test, never a measurement of
LCD bandwidth, CDC, routing, physical resources, acoustic latency or a board.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if not shutil.which('verilator'):
        raise RuntimeError('Verilator is required')
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    math_name = 'legacy/rtl/audio/audio_math_pkg.sv'
    math_path = output / 'audio_math_pkg.sv'
    math_path.write_bytes(baseline.read_bytes(math_name))
    sources = [ROOT / name for name in (
        'rtl/memory/workstation_sdp.sv',
        'rtl/memory/workstation_sdp_banked.sv',
        'rtl/audio/workstation_runtime_spatial_reverb.sv',
        'rtl/audio/workstation_remote_reverb_m.sv',
        'rtl/audio/workstation_remote_reverb_w.sv',
        'sim/audio/tb_workstation_remote_reverb.sv')]
    headers = [ROOT / 'rtl/audio/runtime_spatial_room_preset.svh']
    locked = {str(path.relative_to(ROOT)): sha(path) for path in sources + headers + [Path(__file__)]}
    command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
               '--top-module', 'tb_workstation_remote_reverb', '--Mdir', str(output / 'obj'),
               '-o', 'remote_reverb', '-I' + str(ROOT), str(math_path), *map(str, sources)]
    built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
    (output / 'compile.stdout').write_text(built.stdout)
    (output / 'compile.stderr').write_text(built.stderr)
    if built.returncode:
        raise RuntimeError('compile failed: ' + built.stderr[-6000:])
    new_warnings = [line for line in built.stderr.splitlines()
                    if line.startswith('%Warning-') and 'workstation_remote_reverb' in line]
    if new_warnings:
        raise RuntimeError('partition RTL warnings: ' + '\n'.join(new_warnings))
    run = subprocess.run([str(output / 'obj/remote_reverb')], cwd=ROOT,
                         capture_output=True, text=True, timeout=180)
    (output / 'run.stdout').write_text(run.stdout)
    (output / 'run.stderr').write_text(run.stderr)
    if run.returncode:
        raise RuntimeError('test failed: ' + run.stdout[-6000:] + run.stderr[-2000:])
    results = [json.loads(line.split(' ', 1)[1]) for line in run.stdout.splitlines()
               if line.startswith('REMOTE_REVERB_RESULT ')]
    if len(results) != 1 or not results[0].get('passed'):
        raise RuntimeError('missing structured verification result')
    for name, expected in locked.items():
        if sha(ROOT / name) != expected:
            raise RuntimeError('verified input changed: ' + name)
    evidence = dict(schema=1, passed=True, scope='synchronous logical transport RTL only',
                    hardware_tested=False, physical_timing_accepted=False,
                    physical_transport_selected=False, source_sha256=locked,
                    baseline=baseline.evidence(), baseline_math_sha256=sha(math_path),
                    results=results[0], compile_command=command)
    (output / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
