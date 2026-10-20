#!/usr/bin/env python3
"""Program/verify external Flash at address zero, reload it, then verify identity.

Uses the board's previously verified Arora V operation 54 at 2.5 MHz.
This replaces the Flash boot image. SRAM-only testing is in program_sram.py.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

from program_sram import verified_artifact

CLI = '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/programmer_cli'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    artifact, expected_user = verified_artifact(args.manifest)
    if args.check_only:
        print(json.dumps({'verified': True, 'artifact': artifact, 'user_code': hex(expected_user)}, indent=2))
        return 0
    project = Path(__file__).resolve().parent
    out = project/'reports'/('flash_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True)
    report = {'started_at': datetime.now().astimezone().isoformat(), 'passed': False,
              'artifact': artifact, 'expected_user_code': hex(expected_user),
              'manifest': str(args.manifest.resolve()), 'steps': {}}
    base = ['--device', 'GW5A-25A']
    cable = ['--cable-index', '1', '--channel', '0', '--frequency', '2.5MHz']

    def run(name, operation, extra=()):
        command = [CLI, *base, '--operation_index', str(operation), *extra, *cable]
        log = out/(name+'.log')
        step = {'command': command, 'log': str(log), 'passed': False}
        report['steps'][name] = step
        with log.open('w') as stream:
            process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        text = log.read_text(errors='replace')
        step['returncode'] = process.returncode
        step['passed'] = (process.returncode == 0 and 'Finished.' in text and
                          not re.search(r'\berror\b|\bfailed\b|\bfailure\b', text, re.I))
        if not step['passed']:
            raise RuntimeError(name+' failed; see '+str(log))
        return text

    try:
        before = run('device_before', 0)
        if '0x0001281B' not in before:
            raise ValueError('Unexpected FPGA device ID')
        # Detect can be intermittently unavailable on this board. Retry read-only
        # detection once; never retry an erase/program automatically.
        for attempt in range(2):
            try:
                detected = run('flash_id_'+str(attempt+1), 51)
                if not re.search(r'Detected Flash id:\s*0x0B4017!', detected, re.I):
                    raise ValueError('Unexpected board Flash ID')
                break
            except RuntimeError:
                if attempt:
                    raise
        if hashlib.sha256(Path(artifact['path']).read_bytes()).hexdigest() != artifact['sha256']:
            raise ValueError('Artifact changed before Flash programming')
        text = run('program_verify', 54, ['--fsFile', artifact['path'], '--spiaddr', '0x000000'])
        if 'Program and Verify Flash successfully.' not in text:
            raise RuntimeError('Program/verify success marker missing')
        report['flash_programmed_verified'] = True
        run('reload_flash', 1)
        after = run('device_after', 0)
        users = re.findall(r'User Code is:\s*(0x[0-9a-fA-F]+)', after)
        statuses = re.findall(r'Status Code is:\s*(0x[0-9a-fA-F]+)', after)
        report['user_code'] = users
        report['status_code'] = statuses
        if not users or any(int(x,16) != expected_user for x in users):
            raise ValueError('Reloaded Flash UserCode mismatch')
        if not statuses or any(int(x,16) != 0x70022020 for x in statuses):
            raise ValueError('Reloaded Flash status mismatch')
        report['passed'] = True
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['finished_at'] = datetime.now().astimezone().isoformat()
        report['power_cycle_performed'] = False
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        (project/'reports/last_flash.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'passed': report['passed'], 'report': str(out/'summary.json'),
                      'error': report.get('error')}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
