#!/usr/bin/env python3
"""Start TF file capture only after the user selects a track."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full73_20261004_024739'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full74_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))
    tcl = stage / 'scripts/build.tcl'
    old = tcl.read_text()
    shutil.copy2(ROOT / 'rtl/tf_audio/storage/tf_audio_ddr_path.v',
                 stage / 'src/storage/tf_audio_ddr_path.v')
    shutil.copy2(ROOT / 'rtl/tf_audio/tf_workstation_audio_bridge.v',
                 stage / 'src/storage/tf_workstation_audio_bridge.v')
    top = stage / 'src/push2/gw138k_push_workstation_top.v'
    top_text = top.read_text()
    old_bridge = '.FILE_EXT(TF_AUDIO_KIND==1 ? "MP3" : (TF_AUDIO_KIND==3 ? "FLA" : "WAV"))'
    assert top_text.count(old_bridge) == 1
    top.write_text(top_text.replace(old_bridge,
        old_bridge + ',.CAPTURE_ON_ANALYSIS(1)'))
    assert old.count('set_option -user_code 00000073') == 1
    tcl.write_text(old.replace('set_option -user_code 00000073',
                               'set_option -user_code 00000074'))
    inputs = {str(path.relative_to(stage)): sha(path)
              for path in stage.rglob('*') if path.is_file()}
    (output / 'workstation_inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    print(output, flush=True)
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
