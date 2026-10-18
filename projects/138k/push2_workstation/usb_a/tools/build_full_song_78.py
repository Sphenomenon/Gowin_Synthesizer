#!/usr/bin/env python3
"""0x78: absorb consumer-card maintenance silences (4 s no-answer threshold)
and give the in-place recovery a window that outlasts a slow card wakeup."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full77_20261004_125442'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(data, old, new):
    assert data.count(old) == 1, 'expected exactly one occurrence: ' + old[:80]
    return data.replace(old, new)


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full78_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))
    shutil.copy2(ROOT / 'rtl/tf_audio/storage/tf_audio_ddr_path.v',
                 stage / 'src/storage/tf_audio_ddr_path.v')
    shutil.copy2(ROOT / 'rtl/push2_usb_a_control.sv',
                 stage / 'src/usb_a/push2_usb_a_control.sv')
    shutil.copy2(ROOT / 'rtl/push2/push2_playlist_hold.sv',
                 stage / 'src/push2/push2_playlist_hold.sv')

    top = stage / 'src/push2/gw138k_push_workstation_top.v'
    data = top.read_text()
    data = replace_once(data,
        '    reg [26:0] tf_recover_wait;\n',
        '    reg [28:0] tf_recover_wait;\n')
    data = replace_once(data,
        'tf_recover<=music_song_started;tf_recover_wait<=27\'d96_000_000;\n',
        'tf_recover<=music_song_started;tf_recover_wait<=29\'d480_000_000;\n')
    top.write_text(data)

    tcl = stage / 'scripts/build.tcl'
    old = tcl.read_text()
    assert old.count('set_option -user_code 00000077') == 1
    tcl.write_text(old.replace('set_option -user_code 00000077',
                               'set_option -user_code 00000078'))
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
