#!/usr/bin/env python3
"""M chunk/source/atomic score lifecycle with an explicit deterministic worker."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / 'sim/music/tb_workstation_task3_analysis_framework.sv',
             *[ROOT / 'rtl/music' / name for name in
               ('workstation_task3_tf_analysis_source.sv', 'workstation_task3_score_commit_m.sv')]]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = {str(p): sha(p) for p in [*paths, Path(__file__)]}
    result = dict(passed=False, real_M_source_and_score_collector=True,
                  W_worker='explicit deterministic responder; no actual CNN claim',
                  file_source='held ready/valid deterministic PCM cursor, 23 frames in 16+7 clips; not SPI/card',
                  queue_frames=8, score_capacity=4, source_sha256=inputs,
                  physical_link=False, hardware_tested=False, profile_selected=False)
    try:
        argv = ['verilator', '--binary', '--timing', '-Wno-fatal', '--build-jobs', '4',
                '--top-module', 'tb_workstation_task3_analysis_framework', '--Mdir', str(output / 'obj'), *map(str, paths)]
        with (output / 'build.log').open('w') as log:
            result['build_exit'] = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        if result['build_exit']:
            raise RuntimeError('build failed')
        p = subprocess.run([str(output / 'obj/Vtb_workstation_task3_analysis_framework')], cwd=ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (output / 'run.log').write_text(p.stdout)
        print(p.stdout)
        result.update(run_exit=p.returncode, run_log_sha256=sha(output / 'run.log'))
        if p.returncode or 'PASS task3_analysis_logic' not in p.stdout:
            raise RuntimeError('M analysis lifecycle failed')
        result['source_unchanged'] = inputs == {p: sha(Path(p)) for p in inputs}
        result['passed'] = result['source_unchanged']
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output.resolve())
