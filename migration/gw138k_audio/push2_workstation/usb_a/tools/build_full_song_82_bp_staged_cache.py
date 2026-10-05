#!/usr/bin/env python3
"""0x82: CNN throughput fix - staged per-frame caches instead of per-MAC DDR
fetches (the 0x81 measurement build's telemetry confirmed the split).

- workstation_link: USE_ALL_DDR 1->0, USE_EXTERNAL_WEIGHTS/FEATURES 1.
  Weights load per frame into the 8-block weight cache (S_LOAD_WEIGHT),
  activation row windows stage through feature_ddr (7x88x32 shared cache),
  the stacked CQT plane stages through plane_cache (5 rows) per frame; the
  conv2d engines then run at BSRAM speed (~2 cycles/MAC) instead of two DDR
  round trips per MAC.  CQT signal/coefficients, front coefficients, NormLog
  plane and Viterbi DP history all stay DDR-backed.
- pcm_pipeline: g_ddr_weights swaps the distributed-ROM model loader for the
  UART loader (BPN1 + CRC, board flow), and USE_DDR_SIGNAL decouples the CQT
  signal storage from USE_ALL_DDR (stays in DDR).

Baseline is the 0x81 (telemetry) staging tree; dwell telemetry is unchanged,
so the post-fix distribution is directly comparable to the baseline.
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
BASE = ROOT / 'results/song_guide_full81_20261005_133345'

# The 0x81 telemetry files as committed (0687fb3); the staged tree must
# still carry them before the live fixed copies replace them.
BASELINE_SHA = {
    'rtl/music/basic_pitch_pcm_pipeline.sv':
        '714e7d1e86d86d6035068a685b6448c405b7713ac0009faeb2aaa982ec4f3a07',
    'rtl/music/basic_pitch_workstation_link.sv':
        'c0a3c42b143b091a28123c8a91926ec975ede8ba99d4ca5f849df3d948929dbf',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full82_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))

    for live, baseline_sha in BASELINE_SHA.items():
        staged = stage / live
        assert sha(staged) == baseline_sha, f'staged baseline drifted: {live}'
        shutil.copy2(ROOT / live, staged)

    tcl = stage / 'scripts/build.tcl'
    old = tcl.read_text()
    assert old.count('set_option -user_code 00000081') == 1
    tcl.write_text(old.replace('set_option -user_code 00000081',
                               'set_option -user_code 00000082'))

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
