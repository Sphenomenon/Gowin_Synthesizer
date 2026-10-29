#!/usr/bin/env python3
"""Bounded physical PCM observation CDC and independent persistent loss telemetry."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / 'rtl/music/music_async_fifo.sv',
               project / 'src/migration/gw138k_counter_cdc.sv',
               ROOT / 'rtl/audio/workstation_pcm_observation_bridge.sv',
               Path(__file__).with_name('tb_workstation_pcm_observation_bridge.sv')]
    profile_path = project.parents[1] / 'workstation_profile.json'
    profile = json.loads(profile_path.read_text())
    inputs = sources + [Path(__file__).resolve(), profile_path]
    hashes = {str(path): digest(path) for path in inputs}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                  identity='pcm-observation-offline-v1-' + identity[:16], source_set_sha256=identity,
                  prepared_reference_candidate=profile['candidate_identity'], input_sha256=hashes,
                  scope='Actual maintained Gray FIFO plus existing registered-Gray counter CDC; atomic98bit frames; no audio backpressure',
                  configuration=dict(test_fifo_depth=4, test_counter_max=7, default_fifo_depth=16, default_counter_max=4294967295),
                  limits='Digital asynchronous functional simulation; requires held-payload/Gray path physical constraints and coordinated peer reset; no profile/top or board selection')
    try:
        lint_command = ['verilator', '--lint-only', '-Wno-fatal', '--top-module', 'workstation_pcm_observation_bridge', *map(str, sources[:-1])]
        result['lint_argv'] = lint_command
        with (output / 'lint.log').open('w') as stream:
            subprocess.run(lint_command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        result['lint_warning_count'] = (output / 'lint.log').read_text().count('%Warning-')
        if result['lint_warning_count']:
            raise ValueError('Observation RTL lint warning')
        result['lint_log_sha256'] = digest(output / 'lint.log')
        command = ['iverilog', '-g2012', '-s', 'tb_workstation_pcm_observation_bridge',
                   '-o', str(output / 'observation.vvp'), *map(str, sources)]
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        result['runs'] = []
        for index, (source_phase, destination_phase) in enumerate(((7.3, 1.1), (0.2, 12.7), (58.9, 4.3))):
            logfile = output / f'run{index}.log'
            run_command = ['vvp', str(output / 'observation.vvp'), f'+SOURCE_PHASE={source_phase}', f'+DESTINATION_PHASE={destination_phase}']
            with logfile.open('w') as stream:
                subprocess.run(run_command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
            log = logfile.read_text()
            if 'PASS pcm_observation:' not in log:
                raise ValueError('Missing observation verification')
            result['runs'].append(dict(source_phase_ns=source_phase, destination_phase_ns=destination_phase,
                                       metrics={key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)},
                                       run_argv=run_command, log=log, run_log_sha256=digest(logfile)))
            print(log, end='')
        result['compile_log_sha256'] = digest(output / 'compile.log')
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('Observation source drift')
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
