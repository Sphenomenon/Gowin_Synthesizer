#!/usr/bin/env python3
"""Actual block codec bounds, simultaneous failure fences and exact PCM reconstruction."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = ['rtl/workstation/workstation_task3_pcm_block_tx.sv',
               'rtl/workstation/workstation_task3_pcm_block_rx.sv']
    tb = 'sim/audio/tb_workstation_task3_pcm_block_bounds.sv'
    extras = ['rtl/workstation/task3_paired_channels.vh', tb,
              'sim/audio/run_workstation_task3_pcm_block_bounds.py']
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = {rel: sha(root / rel) for rel in sources + extras}
    commands = []
    passed, error, checks = False, None, 0
    try:
        binary = output / 'pcm_block_bounds.vvp'
        for argv, name in [(['iverilog', '-g2012', '-I.', '-s',
                            'tb_workstation_task3_pcm_block_bounds', '-o', str(binary),
                            tb, *sources], 'build.log'), (['vvp', str(binary)], 'run.log')]:
            result = subprocess.run(argv, cwd=root, text=True, capture_output=True)
            log = output / name
            log.write_text(result.stdout + result.stderr)
            commands.append(dict(argv=argv, returncode=result.returncode,
                                 log=str(log), log_sha256=sha(log)))
            if result.returncode:
                raise ValueError('failed command: ' + ' '.join(argv))
        match = re.search(r'PASS task3 PCM block bounds checks=(\d+) exact_frames=17', result.stdout)
        if not match:
            raise ValueError('expected endpoint evidence absent')
        checks = int(match[1])
        passed = True
    except ValueError as exc:
        error = str(exc)
    unchanged = inputs == {rel: sha(root / rel) for rel in inputs}
    report = dict(schema=1, passed=passed and unchanged, error=error,
                  source_unchanged=unchanged, inputs_sha256=inputs,
                  invocations=commands, checks=checks,
                  exact_frames=17,
                  scope='actual codec modules: framing, context/index/credit bounds and simultaneous fault handshakes',
                  hardware_tested=False, physical_LCD_verified=False,
                  physical_DAC_or_latency_verified=False,
                  sustainable_phone_PCM1_verified=False,
                  full_CNN_or_long_recording_verified=False)
    target = output / 'verification.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], verification=str(target), error=error)))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
