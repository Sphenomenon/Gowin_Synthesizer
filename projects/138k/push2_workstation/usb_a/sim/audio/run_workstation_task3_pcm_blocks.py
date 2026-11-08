#!/usr/bin/env python3
"""Explicit block-v1 endpoints: bounded queues, negotiation, isolation and failure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--registered-w-tx-class', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = ['rtl/workstation/' + name + '.sv' for name in (
        'workstation_task3_w_bus_endpoint', 'workstation_task3_m_bus_endpoint',
        'workstation_task3_pcm_block_tx', 'workstation_task3_pcm_block_rx',
        'workstation_task3_record_ingress', 'workstation_task3_final_tap_export',
        'workstation_task3_phone_command_ingress', 'workstation_task3_phone_command_proxy',
        'workstation_task3_phone_command_mux')]
    sources += ['rtl/music/workstation_task3_tf_analysis_source.sv',
                'rtl/music/workstation_task3_score_commit_m.sv']
    tb = 'sim/audio/tb_workstation_task3_pcm_blocks.sv'
    extras = ['rtl/workstation/task3_paired_channels.vh', tb,
              'sim/audio/run_workstation_task3_pcm_blocks.py']
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = {rel: sha(root / rel) for rel in sources + extras}
    commands = []
    passed, error, checks, mixed_checks = False, None, 0, 0
    parameters=['-Ptb_workstation_task3_pcm_blocks.REGISTER_W_TX_CLASS='+str(int(args.registered_w_tx_class))]
    try:
        binary = output / 'pcm_blocks.vvp'
        for argv, name in [(['iverilog', '-g2012', '-I.', '-s',
                            'tb_workstation_task3_pcm_blocks', *parameters, '-o', str(binary),
                            tb, *sources], 'build.log'), (['vvp', str(binary)], 'run.log')]:
            result = subprocess.run(argv, cwd=root, text=True, capture_output=True)
            log = output / name
            log.write_text(result.stdout + result.stderr)
            commands.append(dict(argv=argv, returncode=result.returncode,
                                 log=str(log), log_sha256=sha(log)))
            if result.returncode:
                raise ValueError('failed command: ' + ' '.join(argv))
        match = re.search(r'PASS task3 paired PCM blocks checks=(\d+) cnn_frames=61 record_frames=24 seals=1', result.stdout)
        if not match:
            raise ValueError('expected endpoint evidence absent')
        checks = int(match[1])
        mixed_binary = output / 'mixed_media.vvp'
        for argv, name in [(['iverilog', '-g2012', '-DTASK3_MIXED_MEDIA', '-I.', '-s',
                            'tb_workstation_task3_pcm_blocks', *parameters, '-o', str(mixed_binary),
                            tb, *sources], 'mixed-build.log'),
                           (['vvp', str(mixed_binary)], 'mixed-run.log')]:
            mixed = subprocess.run(argv, cwd=root, text=True, capture_output=True)
            log = output / name
            log.write_text(mixed.stdout + mixed.stderr)
            commands.append(dict(argv=argv, returncode=mixed.returncode,
                                 log=str(log), log_sha256=sha(log)))
            if mixed.returncode:
                raise ValueError('failed mixed-version command: ' + ' '.join(argv))
        mixed_match = re.search(r'PASS task3 mixed media checks=(\d+)', mixed.stdout)
        if not mixed_match:
            raise ValueError('mixed-version rejection evidence absent')
        mixed_checks = int(mixed_match[1])
        passed = True
    except ValueError as exc:
        error = str(exc)
    unchanged = inputs == {rel: sha(root / rel) for rel in inputs}
    report = dict(schema=1, passed=passed and unchanged, error=error,
                  registered_w_tx_class=args.registered_w_tx_class,
                  source_unchanged=unchanged, inputs_sha256=inputs,
                  invocations=commands, checks=checks, mixed_version_checks=mixed_checks,
                  cnn_frames=61, record_frames=24, seals=1,
                  scope='actual explicit block-mode M/W endpoints; CNN and M phone owner are deterministic fixtures; actual bounded record ingress',
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
