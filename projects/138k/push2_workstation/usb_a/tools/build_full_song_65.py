#!/usr/bin/env python3
"""Build continuous TF/CNN score guidance from the board-tested 0x64 image."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/song_guide_hotplug64_20261003'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(data, old, new):
    if data.count(old) != 1:
        raise ValueError(f'expected one occurrence of {old!r}, got {data.count(old)}')
    return data.replace(old, new)


def main():
    output = ROOT / 'results' / datetime.now().strftime('song_guide_full65_%Y%m%d_%H%M%S')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user'))
    sources = {
        'rtl/music/basic_pitch_viterbi.sv': 'rtl/music/basic_pitch_viterbi.sv',
        'rtl/music/basic_pitch_cnn_streaming.sv': 'rtl/music/basic_pitch_cnn_streaming.sv',
        'rtl/music/basic_pitch_cqt_frontend.sv': 'rtl/music/basic_pitch_cqt_frontend.sv',
        'rtl/music/basic_pitch_pcm_pipeline.sv': 'rtl/music/basic_pitch_pcm_pipeline.sv',
        'rtl/music/basic_pitch_workstation_link.sv': 'rtl/music/basic_pitch_workstation_link.sv',
        'rtl/tf_audio/storage/tf_audio_ddr_path.v': 'src/storage/tf_audio_ddr_path.v',
        'rtl/tf_audio/tf_workstation_audio_bridge.v': 'src/storage/tf_workstation_audio_bridge.v',
        'rtl/push2/push2_score_guide.sv': 'src/usb_a/push2_score_guide.sv',
        'rtl/push2/push2_song_screen.sv': 'src/push2/push2_song_screen.sv',
        'rtl/push2_usb_a_control.sv': 'src/usb_a/push2_usb_a_control.sv',
        'rtl/display_data/push2_surface_pixels.sv': 'src/push2/push2_surface_pixels.sv',
    }
    for src, dst in sources.items():
        shutil.copy2(ROOT / src, stage / dst)
    top = stage / 'src/push2/gw138k_push_workstation_top.v'
    data = top.read_text()
    data = replace_once(data, '    wire analysis_pcm_valid;',
                        '    wire analysis_pcm_valid,analysis_pcm_end;')
    data = replace_once(data, '.analysis_pcm_valid(analysis_pcm_valid),',
                        '.analysis_pcm_valid(analysis_pcm_valid),.analysis_pcm_end(analysis_pcm_end),')
    data = replace_once(data, '.pcm_valid(analysis_pcm_valid),.pcm_left(analysis_pcm_left),',
                        '.pcm_valid(analysis_pcm_valid),.pcm_end(analysis_pcm_end),\n'
                        '        .pcm_left(analysis_pcm_left),')
    data = replace_once(data,
                        '.score_valid(score_usb_valid),.score_ready(score_usb_ready),.score_note(score_usb_note),',
                        '.score_valid(score_usb_valid),.score_ready(score_usb_ready),.score_note(score_usb_note),\n'
                        '        .analysis_done(music_analysis_done),')
    data = replace_once(data,
                        'else if(song_pending && music_model_ready &&\n'
                        '                    (!music_song_started || music_analysis_done)) begin',
                        'else if(song_pending && music_model_ready) begin')
    top.write_text(data)
    tcl = stage / 'scripts/build.tcl'
    tcl.write_text(replace_once(tcl.read_text(),
                                'set_option -user_code 00000064',
                                'set_option -user_code 00000065'))
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
