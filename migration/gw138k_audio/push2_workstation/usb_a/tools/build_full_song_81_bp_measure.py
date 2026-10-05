#!/usr/bin/env python3
"""0x81: CNN throughput measurement build (telemetry only, no behaviour change).

- basic_pitch_pcm_pipeline gains eight per-state dwell cycle counters; a
  25M-cycle divider latches each 0.5 s window total and rotates the reported
  page through debug_dwell_o = {page[1:0], cycles[24:11]}.
- basic_pitch_workstation_link carries that page in the B138 NN word low half,
  replacing sample_rate[15:0] (redundant: the TF word already carries it).
- Decode: state=(nn>>26)&0x3f unchanged; page=(nn>>14)&3; cycles=nn&0x3fff
  times 2048.  Host tool: tools/capture_bp_dwell.py.

Baseline is the 0x80 staging tree (delay DDR migration, board-accepted).
No TB gate runs here: the only changed modules are Basic Pitch telemetry,
which no TB exercises; the delay-DDR equivalence gate covers untouched logic.
"""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full80_20261005_045703'

# Hashes of the pre-edit 0x80 files; the staged tree must still carry them.
BASELINE_SHA = {
    'rtl/music/basic_pitch_pcm_pipeline.sv':
        '1d33a03065140420f2252c119c76c3a218677998442fafc95da32c88b7228835',
    'rtl/music/basic_pitch_workstation_link.sv':
        '980577612d9d1f41f84a7f8029430724c4ee07cfaa5025183187c0b3639e3474',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full81_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))

    # The staged tree must be the untouched 0x80 baseline, then take the live
    # (telemetry-instrumented) copies.
    for live, baseline_sha in BASELINE_SHA.items():
        staged = stage / live
        assert sha(staged) == baseline_sha, f'staged baseline drifted: {live}'
        shutil.copy2(ROOT / live, staged)

    tcl = stage / 'scripts/build.tcl'
    old = tcl.read_text()
    assert old.count('set_option -user_code 00000080') == 1
    tcl.write_text(old.replace('set_option -user_code 00000080',
                               'set_option -user_code 00000081'))

    inputs = {str(path.relative_to(stage)): sha(path)
              for path in stage.rglob('*') if path.is_file()}
    (output / 'workstation_inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    print(output, flush=True)
    if '--dry-run' in sys.argv:
        print('dry run: patches applied, synthesis skipped', flush=True)
        return
    with (output / 'gowin.log').open('w') as log:
        result = subprocess.run([str(Path.home() / '.local/bin/gw_sh'), 'scripts/build.tcl'],
                                cwd=stage, env=dict(os.environ, PRJ1_FLOW='all'),
                                stdout=log, stderr=subprocess.STDOUT)
    changed = [path for path, digest in inputs.items() if sha(stage / path) != digest]
    (output / 'tool_result.json').write_text(json.dumps({
        'exit_code': result.returncode, 'inputs_unchanged': not changed,
        'changed': changed, 'baseline': str(BASE), 'hardware_tested': False}, indent=2) + '\n')
    print('Gowin exit', result.returncode, 'changed inputs', changed, flush=True)
    if result.returncode or changed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
