#!/usr/bin/env python3
"""Verify the single-clock task3 transaction hub; no board or wire assumptions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out):
    root = Path(__file__).resolve().parents[2]
    sources = [root / 'rtl/workstation/workstation_task3_channel_mux.sv',
               root / 'sim/workstation/tb_task3_channel_mux.sv']
    tracked = sources + [Path(__file__).resolve()]
    before = {str(p): sha(p) for p in tracked}
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, source_sha256=before,
                  scope='single-clock bounded logical channels; no LCD wire, CDC, hardware, or throughput acceptance',
                  bitstream=None, hardware_tested=False)
    try:
        argv = ['verilator', '--binary', '--timing', '--build-jobs', '4', '-Wno-fatal',
                '--top-module', 'tb_task3_channel_mux', '--Mdir', str(out / 'obj'),
                *map(str, sources)]
        report['build_argv'] = argv
        with (out / 'build.log').open('w') as log:
            built = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT)
        report['build_exit'] = built.returncode
        report['build_log_sha256'] = sha(out / 'build.log')
        if built.returncode:
            raise RuntimeError('build failed: ' + str(out / 'build.log'))
        result = subprocess.run([str(out / 'obj/Vtb_task3_channel_mux')], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (out / 'run.log').write_text(result.stdout)
        report.update(run_exit=result.returncode, run_log_sha256=sha(out / 'run.log'), log=result.stdout)
        report['source_unchanged'] = before == {str(p): sha(p) for p in tracked}
        if result.returncode or 'PASS all task3_channel_mux geometries' not in result.stdout or not report['source_unchanged']:
            raise RuntimeError('task3 channel verification failed: ' + str(out / 'run.log'))
        report['passed'] = True
        print(result.stdout, end='')
    finally:
        (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
