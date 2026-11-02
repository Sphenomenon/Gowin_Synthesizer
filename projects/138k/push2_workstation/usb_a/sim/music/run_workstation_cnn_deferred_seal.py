#!/usr/bin/env python3
"""Check the real task storage/CRC/lifecycle; CNN is an explicit test sink."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / 'sim/music/tb_workstation_cnn_deferred_seal.sv',
             *[ROOT / 'rtl/music' / name for name in
               ('music_async_fifo.sv', 'workstation_cnn_ddr_broker.sv', 'workstation_cnn_task_service.sv',
                'workstation_task3_cnn_stream_w.sv')]]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = {str(p): sha(p) for p in [*paths, ROOT / 'rtl/ddr_address_map.vh', Path(__file__)]}
    result = dict(passed=False, real_task_service=True, real_broker_and_staging_fifos=True,
                  cnn='explicit deterministic sink; no model/recognition assertion',
                  physical_memory=False, profile_selected=False, source_sha256=inputs)
    try:
        argv = ['verilator', '--binary', '--timing', '-Wno-fatal', '--build-jobs', '4',
                '--top-module', 'tb_workstation_cnn_deferred_seal', '--Mdir', str(output / 'obj'),
                '-I' + str(ROOT), *map(str, paths)]
        with (output / 'build.log').open('w') as log:
            result['build_exit'] = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        if result['build_exit']:
            raise RuntimeError('build failed')
        process = subprocess.run([str(output / 'obj/Vtb_workstation_cnn_deferred_seal')], cwd=ROOT,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (output / 'run.log').write_text(process.stdout)
        print(process.stdout)
        result.update(run_exit=process.returncode, run_log_sha256=sha(output / 'run.log'))
        if process.returncode or 'PASS deferred_seal_storage_lifecycle' not in process.stdout:
            raise RuntimeError('deferred seal test failed')
        result['source_unchanged'] = inputs == {p: sha(Path(p)) for p in inputs}
        result['passed'] = result['source_unchanged']
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output.resolve())
