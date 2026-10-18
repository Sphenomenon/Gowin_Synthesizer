#!/usr/bin/env python3
"""0x77: tolerate slow TF tokens, hold the playlist through a rescan, and
restart the same song in place after a recovered transport fault."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_full76_20261004_041101'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(data, old, new):
    assert data.count(old) == 1, 'expected exactly one occurrence: ' + old[:80]
    return data.replace(old, new)


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full77_%Y%m%d_%H%M%S')
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
        '    reg music_song_started,tf_song_restart;\n',
        '    reg music_song_started,tf_song_restart;\n'
        '    reg tf_recover;\n'
        '    reg [26:0] tf_recover_wait;\n')
    data = replace_once(data,
        '            if(tf_card_lost) begin\n'
        '                song_pending<=0;music_song_started<=0;tf_selected_track<=0;\n'
        '                music_run_reset_count<=3\'d4;music_restart_delay<=0;\n'
        '            end else if(song_cmd_valid) begin song_pending<=1;pending_track<=song_cmd_index;end\n',
        '            if(tf_card_lost) begin\n'
        '                song_pending<=0;music_song_started<=0;\n'
        '                music_run_reset_count<=3\'d4;music_restart_delay<=0;\n'
        '                // A TF transport fault resets the reader and rescans. If\n'
        '                // the playlist returns, restart the same song in place;\n'
        '                // a card that stays missing lets the recovery expire into\n'
        '                // this teardown and the held playlist count drops to menu.\n'
        '                tf_recover<=music_song_started;tf_recover_wait<=27\'d96_000_000;\n'
        '            end else if(tf_recover) begin\n'
        '                if(playlist_scan_done && tf_track_count!=0) begin\n'
        '                    tf_recover<=0;music_song_started<=1;\n'
        '                    music_run_reset_count<=3\'d4;\n'
        '                    music_restart_delay<=22\'d2_500_000;\n'
        '                end else if(tf_recover_wait==0) tf_recover<=0;\n'
        '                else tf_recover_wait<=tf_recover_wait-1\'b1;\n'
        '            end else if(song_cmd_valid) begin song_pending<=1;pending_track<=song_cmd_index;end\n')
    top.write_text(data)

    project = stage / 'Prj1.gprj'
    project_text = project.read_text()
    insert = ('        <File path="src/push2/push2_playlist_hold.sv" '
              'type="file.verilog" enable="1" />\n')
    assert insert not in project_text
    assert project_text.count('</FileList>') == 1
    project.write_text(project_text.replace('</FileList>', insert + '    </FileList>'))

    tcl = stage / 'scripts/build.tcl'
    old = tcl.read_text()
    assert old.count('set_option -user_code 00000076') == 1
    tcl.write_text(old.replace('set_option -user_code 00000076',
                               'set_option -user_code 00000077'))
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
