#!/usr/bin/env python3
"""Offline paired configuration owner verification; no board operation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    root = Path(__file__).resolve().parents[2]
    sources = [root / 'rtl/services/workstation_task3_pair_config_service.sv',
               root / 'sim/workstation/tb_task3_pair_config_service.sv']
    tracked = sources + [ Path(__file__).resolve()]
    before = {str(p): sha(p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, source_sha256=before, commands=[],
                  scope='single-clock F808 command admission, nonce/session/generation fences and grant revocation',
                  hardware_operated=False, hardware_tested=False, bitstream=None)
    try:
        for allow in (0, 1):
            obj = output / ('obj_' + str(allow))
            build = ['verilator', '--binary', '--timing', '--build-jobs', '4',
                     '--top-module', 'tb_task3_pair_config_service', '-GTEST_ALLOW_BUSINESS=' + str(allow),
                     '--Mdir', str(obj), *map(str, sources)]
            for kind, argv, marker in [('build', build, None),
                    ('run', [str(obj / 'Vtb_task3_pair_config_service')], 'PASS task3_pair_config_service')]:
                result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=120)
                log = output / (kind + '_' + str(allow) + '.log')
                log.write_text(result.stdout)
                report['commands'].append(dict(argv=argv, exit=result.returncode,
                    log=str(log), log_sha256=sha(log)))
                if result.returncode or (marker and marker not in result.stdout):
                    raise RuntimeError('failed: ' + str(log))
                if kind == 'run':
                    print(result.stdout, end='')
        report['source_unchanged'] = before == {str(p): sha(p) for p in tracked}
        if not report['source_unchanged']:
            raise RuntimeError('inputs changed during verification')
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
