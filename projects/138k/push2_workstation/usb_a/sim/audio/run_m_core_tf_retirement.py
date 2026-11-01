#!/usr/bin/env python3
"""Exercise the actual disabled TF parameter and media-stop boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    names = ('rtl/control/workstation_parameters.sv', 'rtl/audio/scope_vec/scope_tf_control.sv',
             'rtl/workstation/workstation_runtime_controlled.sv',
             'sim/audio/tb_workstation_m_core_tf_retirement.sv')
    sources = []
    for name in names:
        destination = output / 'source-snapshot' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / name).read_bytes())
        sources.append(destination)
    rom = output / 'pitch_bend_q20.mem'
    rom.write_bytes((args.project / 'sim/data/audio_chain/pitch_bend_q20.mem').read_bytes())
    records = []
    for variant in ('baseline', 'missing_tf_enter_guard'):
        selected = list(sources)
        if variant != 'baseline':
            text = sources[0].read_text()
            anchor = '104: if (TF_CONTROL_ENABLE && (value_i == 64 || value_i == 127) &&'
            if text.count(anchor) != 1:
                raise ValueError('TF enter negative-control anchor drift')
            mutant = output / 'mutant_parameters.sv'
            mutant.write_text(text.replace(anchor, '104: if ((value_i == 64 || value_i == 127) &&'))
            selected[0] = mutant
        command = ['iverilog', '-g2012', '-s', 'tb_workstation_m_core_tf_retirement',
                   '-DAUDIO_BEND_MEM_FILE="' + str(rom) + '"',
                   '-o', str(output / (variant + '.vvp')), *map(str, selected)]
        with (output / (variant + '-compile.log')).open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        log = output / (variant + '-run.log')
        with log.open('w') as stream:
            result = subprocess.run(['vvp', str(output / (variant + '.vvp'))],
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=60)
        passed = result.returncode == 0 and 'PASS m_core_tf_retirement' in log.read_text()
        if passed != (variant == 'baseline'):
            raise ValueError('Unexpected TF boundary result: ' + variant + ': ' + log.read_text())
        records.append(dict(variant=variant, argv=command, exit_code=result.returncode,
                            expected_result_verified=True, log_sha256=sha(log)))
    record = dict(schema=1, passed=True, scope='actual parameter/default comparison and absent TF stop boundary',
                  source_sha256={name: sha(path) for name, path in zip(names, sources)},
                  runner_sha256=sha(Path(__file__)), rom_sha256=sha(rom), variants=records,
                  hardware_tested=False, physical_timing_tested=False)
    (output / 'verification.json').write_text(json.dumps(record, indent=2) + '\n')
    print((output / 'baseline-run.log').read_text(), end='')
    print('PASS missing_tf_enter_guard rejected; verification=' + sha(output / 'verification.json'))


if __name__ == '__main__':
    main()
