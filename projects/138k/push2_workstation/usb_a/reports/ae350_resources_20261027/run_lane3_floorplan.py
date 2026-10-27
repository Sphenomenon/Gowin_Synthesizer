"""Authorized C6 SRAM control, retaining B2/B3 as an automatic rollback."""

from datetime import datetime
import argparse
import fcntl
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / 'out/workstation_resource_a26_20261027_c6_floorplan'
OUTPUT = ROOT / 'out/hdmi_startup_ab_20261027/c6_floorplan_control'
CAPTURE = runpy.run_path(str(ROOT / 'reports/hdmi_usb3_20261025/capture_ddr_jtag.py'))
IMAGES = {
    'B2': (ROOT / 'out/official_ddr_ab_20261026_01/c11026b2', '0xC11026B2',
           'b1160972329e51428c14e16cb46d641359a35e8d76852506b07802591f55480a'),
    'B3': (ROOT / 'out/official_ddr_ab_20261026_01/c11026b3', '0xC11026B3',
           'a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c'),
}


def ready(observation, image):
    if image == 'B2':
        expected = {f'status_sync[{bit}]': value for bit, value in
                    ((0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 0))}
    else:
        expected = {f'memory_flags[{bit}]': value for bit, value in
                    ((0, 1), (1, 1), (2, 0), (3, 1), (4, 0), (6, 1), (7, 1))}
        expected.update({f'video_diagnostics[{bit}]': value for bit, value in
                         ((9, 1), (10, 1), (11, 1), (12, 0))})
    return all(observation['signals'][name]['values'] == {str(value): 1024}
               for name, value in expected.items())


def main(*, global_reference_clock=False):
    candidate = (ROOT / 'out/workstation_resource_a26_20261027_c7_refclock'
                 if global_reference_clock else CANDIDATE)
    output = (ROOT / 'out/hdmi_startup_ab_20261027/c7_refclock_control'
              if global_reference_clock else OUTPUT)
    image = 'C7' if global_reference_clock else 'C6'
    user_code = '0xC11027C7' if global_reference_clock else '0xC11027C6'
    phase_prefix = image.lower()
    gates = json.loads((candidate / 'audit_returncodes.json').read_text())
    timing = json.loads((candidate / 'timing-audit.json').read_text())
    numeric_timing_passed = not any(
        problem != 'clock summary inventory differs from the native plan'
        for problem in timing['problems'])
    for name in ('check_common_cdc', 'check_routes', 'check_pll'):
        if gates['checks'][name]['returncode']:
            raise ValueError('physical audit failed: ' + name)
    IMAGES[image] = (candidate, user_code, gates['bitstream_sha256'])
    output.mkdir()
    report = dict(started_at=datetime.now().astimezone().isoformat(), operations=[],
                  authorization='User explicitly authorized subsequent diagnostic SRAM writes',
                  flash_accessed=False, power_cycle_performed=False, completed=False,
                  hardware_acceptance=False, release_ready=False,
                  numeric_timing_passed=numeric_timing_passed,
                  strict_timing_passed=gates['checks']['check_timing']['returncode'] == 0)

    def save():
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def program_and_capture(image, phase):
        source, code, checksum = IMAGES[image]
        bitstream = source / 'impl/pnr/ao_0.fs'
        if CAPTURE['digest'](bitstream) != checksum:
            raise ValueError('bitstream changed: ' + image)
        destination = output / phase
        destination.mkdir()
        metadata = json.loads((source / 'inputs.json').read_text())
        filename = metadata.get('gao_file', 'diagnostic.gao')
        shutil.copyfile(source / filename, destination / filename)
        (destination / 'inputs.json').write_text(json.dumps(metadata, indent=2) + '\n')
        command = ['gowin-programmer-cli', '--device', 'GW5AST-138C', '--cable-index', '5',
                   '--location', '54', '--frequency', '0.9MHz', '--operation_index', '2',
                   '--fsFile', str(bitstream)]
        operation = dict(image=image, phase=phase, bitstream_sha256=checksum, command=command,
                         started_at=datetime.now().astimezone().isoformat(), captures=[])
        report['operations'].append(operation)
        save()
        print('PROGRAM', phase, image, flush=True)
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        log = destination / 'program.log'
        log.write_text(result.stdout + result.stderr)
        operation.update(returncode=result.returncode, log_sha256=CAPTURE['digest'](log))
        if result.returncode or 'Finished.' not in log.read_text():
            raise RuntimeError('SRAM write failed: ' + phase)
        CAPTURE['identity'](destination / 'identity_after.log', code)
        report['final_image'] = code
        for sequence in range(1, 4):
            observation = CAPTURE['capture'](destination, sequence)
            operation['captures'].append(dict(sequence=sequence, ready=ready(observation, image),
                                              first=observation['first'], last=observation['last'],
                                              csv_sha256=observation['csv_sha256']))
            save()
            time.sleep(0.43)
        operation['ready'] = all(capture['ready'] for capture in operation['captures'])
        operation['finished_at'] = datetime.now().astimezone().isoformat()
        save()
        print('READY', phase, operation['ready'], flush=True)
        return operation['ready']

    with Path('/tmp/gw138k_20261025.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        CAPTURE['identity'](output / 'identity_before.log', '0xC11026B3')
        keep_candidate = False
        try:
            direct = program_and_capture(image, phase_prefix + '_direct')
            report['direct_ready'] = direct
            if direct:
                report['reload_ready'] = program_and_capture(image, phase_prefix + '_reload')
                keep_candidate = report['reload_ready'] and numeric_timing_passed
            else:
                if not program_and_capture('B2', 'b2_prime'):
                    raise RuntimeError('B2 control failed')
                report['after_b2_ready'] = program_and_capture(image, phase_prefix + '_after_b2')
            report['completed'] = True
        finally:
            if not keep_candidate:
                try:
                    report['rollback_b2_ready'] = program_and_capture('B2', 'rollback_b2')
                finally:
                    report['rollback_b3_ready'] = program_and_capture('B3', 'rollback_b3')
            report['finished_at'] = datetime.now().astimezone().isoformat()
            save()
            print(json.dumps({key: value for key, value in report.items()
                              if key != 'operations'}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--global-reference-clock', action='store_true')
    args = parser.parse_args()
    main(global_reference_clock=args.global_reference_clock)
