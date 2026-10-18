#!/usr/bin/env python3
"""Build TF playlist/Push guide on the hardware-tested 0x52 workstation."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/score_guidance_4d_20261002_194539_384123'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(data, old, new):
    assert data.count(old) == 1, (old, data.count(old))
    return data.replace(old, new)


def main():
    baseline = json.loads((BASE / 'workstation_inputs.json').read_text())
    assert all(sha(BASE / 'Prj1' / path) == digest for path, digest in baseline.items())
    output = ROOT / 'results' / datetime.now().strftime('song_guide_52_%Y%m%d_%H%M%S_%f')
    stage = output / 'Prj1'
    shutil.copytree(BASE / 'Prj1', stage, ignore=shutil.ignore_patterns('impl', 'build', '*.user'))
    sources = {
        'rtl/music/basic_pitch_pcm_pipeline.sv':'rtl/music/basic_pitch_pcm_pipeline.sv',
        'rtl/music/basic_pitch_workstation_link.sv':'rtl/music/basic_pitch_workstation_link.sv',
        'rtl/music/basic_pitch_44100_to_48000.sv':'rtl/music/basic_pitch_44100_to_48000.sv',
        'rtl/music/tf_playlist_bridge.sv':'rtl/music/tf_playlist_bridge.sv',
        'rtl/tf_audio/storage/tf_audio_ddr_path.v':'src/storage/tf_audio_ddr_path.v',
        'rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v':'src/storage/tang_mp3/sd/tf_sd_file_reader.v',
        'rtl/tf_audio/tf_workstation_audio_bridge.v':'src/storage/tf_workstation_audio_bridge.v',
        'rtl/audio/push2_controls.sv':'src/push2/push2_controls.sv',
        'rtl/push2/push2_score_guide.sv':'src/usb_a/push2_score_guide.sv',
        'rtl/push2/push2_song_menu.sv':'src/usb_a/push2_song_menu.sv',
        'rtl/push2/push2_song_screen.sv':'src/push2/push2_song_screen.sv',
        'rtl/push2_usb_a_control.sv':'src/usb_a/push2_usb_a_control.sv',
        'rtl/display_data/push2_surface_pixels.sv':'src/push2/push2_surface_pixels.sv',
    }
    for src,dst in sources.items():
        shutil.copy2(ROOT / src, stage / dst)
    top = stage / 'src/push2/gw138k_push_workstation_top.v'
    data = top.read_text()
    data = replace_once(data, '    wire music_score_valid,music_score_ready,score_usb_valid,score_usb_ready;', '''    wire music_score_valid,music_score_ready,score_usb_valid,score_usb_ready;
    wire playlist_scan_done,playlist_usb_valid,playlist_usb_ready;
    wire [7:0] playlist_name_addr,playlist_name_data;
    wire [15:0] playlist_usb_word;
    wire push_track_launch;
    wire [3:0] push_track_index;
    wire song_cmd_valid;
    wire [3:0] song_cmd_index;
    wire [4:0] tf_track_count;
    reg song_pending;
    tf_playlist_bridge u_playlist_bridge(
        .clk_50m(clk_50m),.reset_n(reset_n),.usb_clk(usb_clk),.usb_reset_n(usb_reset_n),
        .scan_done(playlist_scan_done),.track_count(tf_track_count),
        .name_addr(playlist_name_addr),.name_data(playlist_name_data),
        .playlist_valid(playlist_usb_valid),.playlist_ready(playlist_usb_ready),
        .playlist_word(playlist_usb_word));
    gw138k_stream_cdc #(.WIDTH(4)) u_song_command_cdc(
        .reset_n(reset_n && usb_reset_n),.source_clk(usb_clk),.destination_clk(clk_50m),
        .source_valid(push_track_launch),.source_data(push_track_index),.drop_count(),
        .destination_valid(song_cmd_valid),.destination_data(song_cmd_index));''')
    data = replace_once(data,
        '        .score_valid(score_usb_valid),.score_ready(score_usb_ready),.score_note(score_usb_note),',
        '''        .score_valid(score_usb_valid),.score_ready(score_usb_ready),.score_note(score_usb_note),
        .playlist_valid(playlist_usb_valid),.playlist_ready(playlist_usb_ready),
        .playlist_word(playlist_usb_word),.track_launch(push_track_launch),
        .track_index(push_track_index),''')
    data = replace_once(data,
        '.write_valid_i(music_score_valid),.write_ready_o(music_score_ready),',
        '.write_valid_i(music_score_valid && !song_pending && !song_cmd_valid),.write_ready_o(music_score_ready),')
    start = data.index('    wire music_report_sending,music_report_serial,runtime_serial;')
    end = data.index('    assign debug_uart_tx=music_report_sending ? music_report_serial : runtime_serial;', start)
    data = data[:start] + '''    wire music_report_sending,music_report_serial,runtime_serial;
    wire music_pcm_ready;
    wire music_analysis_done;
    reg music_model_ready_q;
    reg [21:0] music_restart_delay;
    reg [2:0] music_run_reset_count;
    reg music_song_started,tf_song_restart;
    reg [3:0] tf_selected_track,pending_track;
    wire music_model_ready=music_model_status==4'd14;
    wire tf_restart=music_model_ready && !music_model_ready_q;
    wire music_analysis_restart=music_run_reset_count!=0;
    wire music_analysis_enable=music_model_ready_q && music_song_started &&
        music_restart_delay==0 && !music_analysis_restart;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin
            music_model_ready_q<=0;music_restart_delay<=0;music_run_reset_count<=0;
            music_song_started<=0;tf_song_restart<=0;song_pending<=0;
            tf_selected_track<=0;pending_track<=0;
        end else begin
            music_model_ready_q<=music_model_ready;
            tf_song_restart<=0;
            if(music_run_reset_count!=0) music_run_reset_count<=music_run_reset_count-1'b1;
            if(tf_restart) music_restart_delay<=22'd2_500_000;
            else if(music_restart_delay!=0) music_restart_delay<=music_restart_delay-1'b1;
            if(tf_card_lost) begin
                song_pending<=0;music_song_started<=0;tf_selected_track<=0;
                music_run_reset_count<=3'd4;music_restart_delay<=0;
            end else if(song_cmd_valid) begin song_pending<=1;pending_track<=song_cmd_index;end
            else if(song_pending && music_model_ready &&
                    (!music_song_started || music_analysis_done)) begin
                song_pending<=0;music_song_started<=1;
                tf_selected_track<=pending_track;tf_song_restart<=1;
                music_run_reset_count<=3'd4;
                music_restart_delay<=22'd2_500_000;
            end
        end
    end
''' + data[end:]
    data = replace_once(data,
        '    wire [19:0] tf_sample_rate;wire [31:0] tf_file_size;wire [4:0] tf_track_count;',
        '    wire [19:0] tf_sample_rate;wire [31:0] tf_file_size;wire tf_card_lost;')
    data = replace_once(data,
        '.memory_ready(memory_calibrated && memory_reset_n),.restart(tf_restart),.track_index(4\'d0),',
        '.memory_ready(memory_calibrated && memory_reset_n),.restart(tf_restart || tf_song_restart),.track_index(tf_selected_track),')
    data = replace_once(data,
        '.analysis_hold_i(music_model_ready_q && !music_analysis_done),',
        '''.playback_hold_i(1'b1),
        .analysis_hold_i(music_model_ready_q && music_song_started && !music_analysis_done),''')
    data = replace_once(data,
        '.ddr_error(tf_ddr_error),.file_size(tf_file_size),.track_count(tf_track_count),',
        '''.ddr_error(tf_ddr_error),.file_size(tf_file_size),.track_count(tf_track_count),
        .card_lost(tf_card_lost),
        .playlist_ready(playlist_scan_done),.playlist_name_addr(playlist_name_addr),
        .playlist_name_data(playlist_name_data),''')
    data = replace_once(data,
        '        .analysis_enable(music_analysis_enable),',
        '        .analysis_enable(music_analysis_enable),.analysis_restart(music_analysis_restart),')
    top.write_text(data)
    project = stage / 'Prj1.gprj'
    tree = ET.parse(project)
    for path in ('rtl/music/tf_playlist_bridge.sv','rtl/music/basic_pitch_44100_to_48000.sv',
                 'src/usb_a/push2_song_menu.sv',
                 'src/push2/push2_song_screen.sv'):
        ET.SubElement(tree.find('FileList'), 'File', path=path, type='file.verilog', enable='1')
    tree.write(project, encoding='utf-8', xml_declaration=True)
    tcl = stage / 'scripts/build.tcl'
    tcl.write_text(replace_once(tcl.read_text(),
                                'set_option -user_code 00000052',
                                'set_option -user_code 00000053'))
    sdc = stage / 'constraints/tang_mega_138k.sdc'
    constraints = sdc.read_text()
    constraints = replace_once(constraints,
        'set_false_path -to [get_pins {u_runtime/u_usb_cdc/source_release*/CLEAR u_runtime/u_usb_cdc/destination_release*/CLEAR u_push/feedback/source_release*/CLEAR u_push/feedback/destination_release*/CLEAR}]\n',
        '')
    constraints = replace_once(constraints,
        'set_false_path -to [get_pins {u_push/feedback/req_meta*/D u_push/feedback/ack_meta*/D}]\n',
        '')
    sdc.write_text(constraints)
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
    assert result.returncode == 0 and not changed


if __name__ == '__main__':
    main()
