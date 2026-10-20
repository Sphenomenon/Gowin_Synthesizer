#!/usr/bin/env python3
"""Merge scope playback into accepted full83; build only, no board I/O.

The accepted complete staging tree is immutable and supplies CNN staged caches,
DDR delay, TF recovery and song guidance. Overlays fix scope entry wiring and
bind the live USB-A PL display/MIDI feedback adapter to its rebuilt ROM.
CNN files come from the accepted manifest. --cnn-timing85 selects six pinned
full85 timing fixes; live CNN differences are recorded and never overlaid.
Prepare/SYN assign no UserCode. Full builds require an explicit release UserCode.
LATEST_WORKSTATION.json is never changed by the builder.
"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from workstation_memory import audit
from workstation_timing_constraints import constraints as timing_constraints,physical_constraints,timing_reports
from workstation_bus_timing import apply as apply_bus_timing
from workstation_cnn_cdc import select as select_diagnostic_cdc,transform as patch_diagnostic_cdc,LINK as TRACE_LINK
from stage_usb_firmware import stage_usb_firmware
from workstation_sources import accepted_cnn_inputs, cnn_source_audit, verify_cnn_inputs, timing85_cnn_inputs, TIMING85_BUILD, TIMING85_OVERLAYS, TIMING85_MANIFEST_SHA256
from build_full_song_83_bp_ddr_isolation import FROZEN
BASE=ROOT/'results/song_guide_full83_20261006_203125_607466'
ACCEPTED_COMMIT='d0c92a0'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text,old,new):
    if text.count(old)!=1:
        raise ValueError('expected one merge anchor: '+old[:100])
    return text.replace(old,new)


def patch(path,old,new):
    path.write_text(once(path.read_text(),old,new))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-only',action='store_true')
    mode.add_argument('--synthesis-only',action='store_true')
    mode.add_argument('--full',action='store_true',help='Synthesis, P&R and bitstream; no programming')
    parser.add_argument('--cnn-timing85',action='store_true',help='Apply only six pinned full85 CNN timing fixes to full83')
    parser.add_argument('--user-code',help='Required eight hexadecimal digits for --full only')
    parser.add_argument('--riscv-prefix',help='GNU bare-metal RISC-V prefix before -gcc; also GW138K_RISCV_PREFIX')
    args=parser.parse_args()
    if args.full:
        if args.user_code is None or len(args.user_code)!=8 or any(c not in '0123456789abcdefABCDEF' for c in args.user_code):
            parser.error('--full requires --user-code with eight hexadecimal digits')
        if int(args.user_code,16) in (0,0x83):
            parser.error('full release must use a nonzero UserCode distinct from accepted 0x83')
    elif args.user_code is not None:
        parser.error('--user-code is only supported with --full')
    if not (BASE/'Prj1/Prj1.gprj').is_file() or not (BASE/'workstation_inputs.json').is_file():
        parser.error('accepted full83 staging tree is missing: '+str(BASE)+
                     '; restore the accepted baseline before preparing or building')
    acceptance=json.loads((ROOT/'reports/CNN_83_ACCEPTANCE_20261006.json').read_text())
    if acceptance['status']!='accepted_by_user' or acceptance['board']['user_code']!='0x00000083':
        raise ValueError('full83 acceptance record does not identify the accepted baseline')
    originals=json.loads((BASE/'workstation_inputs.json').read_text())
    music=accepted_cnn_inputs(BASE/'Prj1',originals)
    for live,(staged,digest) in FROZEN.items():
        if sha(ROOT/live)!=digest or sha(BASE/'Prj1'/staged)!=digest:
            raise ValueError('accepted DDR input drift: '+live)
    accepted_music=music.copy()
    if args.cnn_timing85:
        music=timing85_cnn_inputs(ROOT,accepted_music)
    local_cnn_transforms=[]
    if args.cnn_timing85:
        music,trace_patch=select_diagnostic_cdc(ROOT,music);local_cnn_transforms.append(trace_patch)
    cnn_sources=cnn_source_audit(ROOT,music)
    if args.cnn_timing85:
        cnn_sources.update(policy='full83_plus_clk50_timing85',accepted_full83_sha256=accepted_music,
                           timing_snapshot=TIMING85_BUILD,timing_manifest_sha256=TIMING85_MANIFEST_SHA256,
                           timing_overlays=list(TIMING85_OVERLAYS),local_transforms=local_cnn_transforms)
    prefix='workstation_scope83_timing85_' if args.cnn_timing85 else 'workstation_scope83_'
    output=ROOT/'results'/datetime.now().strftime(prefix+'%Y%m%d_%H%M%S_%f')
    stage=output/'Prj1'
    shutil.copytree(BASE/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','*.user','__pycache__'))
    if args.cnn_timing85:
        for name in TIMING85_OVERLAYS:
            shutil.copy2(ROOT/TIMING85_BUILD/'Prj1'/name,stage/name)
        trace=stage/TRACE_LINK;trace.write_text(patch_diagnostic_cdc(trace.read_text()))
    overlays={
        'rtl/audio/gw138k_event_workstation.sv':'src/ae350/gw138k_event_workstation.sv',
        'rtl/display_data/feedback_renderer.v':'src/video/feedback_renderer.v',
        'rtl/display_data/feedback_capture.v':'src/video/feedback_capture.v',
        'rtl/display_data/output_audio_analysis.v':'src/video/output_audio_analysis.v',
        # Explicit live adapter overlay; all accepted DDR/CNN checks above remain.
        'rtl/push2_usb_a_control.sv':'src/usb_a/push2_usb_a_control.sv',
        'rtl/audio/push2_controls.sv':'src/push2/push2_controls.sv',
        'rtl/audio/gw138k_usb_lifecycle_merge.sv':'src/usb_a/gw138k_usb_lifecycle_merge.sv',
        'rtl/audio/unified_oscillator_engine.sv':'legacy/rtl/audio/unified_oscillator_engine.sv',
        'rtl/push2/push2_song_screen.sv':'src/push2/push2_song_screen.sv',
        'rtl/display_data/push2_surface_pixels.sv':'src/push2/push2_surface_pixels.sv',
    }
    for live,dest in overlays.items():shutil.copy2(ROOT/live,stage/dest)
    scope=stage/'rtl/audio/scope_vec'
    shutil.copytree(ROOT/'rtl/audio/scope_vec',scope,dirs_exist_ok=True)
    tree=ET.parse(stage/'Prj1.gprj');files=tree.find('FileList')
    names={f.get('path') for f in files}
    for path in sorted(scope.glob('*.sv')):
        name=path.relative_to(stage).as_posix()
        if name not in names: ET.SubElement(files,'File',path=name,type='file.verilog',enable='1')
    ET.SubElement(files,'File',path='src/usb_a/gw138k_usb_lifecycle_merge.sv',type='file.verilog',enable='1')
    for path in sorted((ROOT/'rtl/timing').glob('*.sv')):
        dest=stage/'rtl/timing'/path.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(path,dest)
        ET.SubElement(files,'File',path=dest.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    tree.write(stage/'Prj1.gprj',encoding='UTF-8',xml_declaration=True)
    # Forward control words and DAC-frame metadata through accepted wrappers.
    adapter=stage/'src/ae350/gw138k_controlled_adapter.sv'
    patch(adapter,'    output wire sample_ce_o, sample_valid_o,',
          '    output wire [31:0] scope_status_o,tf_scope_control_o,\n'
          '    output wire [31:0] dac_reference_o,dac_voices_o,dac_health_o,\n'
          '    output wire sample_ce_o, sample_valid_o,')
    patch(adapter,'.scope_status_o(),','.scope_status_o(scope_status_o),.tf_scope_control_o(tf_scope_control_o),')
    patch(adapter,'    wire [31:0] core_faults=deadline_miss_o+midi_overflow_o+note_drop_o;',
          '    wire [31:0] core_faults=deadline_miss_o+midi_overflow_o+note_drop_o;\n'
          '    assign dac_reference_o=frame_reference;assign dac_voices_o=frame_voices;\n'
          '    assign dac_health_o={underrun_count_o[15:0],core_faults[15:0]};')
    managed=stage/'src/usb_host/gw138k_usb_controlled_audio.sv'
    patch(managed,'gw138k_three_event_arbiter u_usb_cpu_events(',
          'gw138k_usb_lifecycle_merge #(.EXPLICIT_LIFECYCLE(1)) u_usb_cpu_events(')
    patch(managed,'    input wire usb_event_valid,','    input wire usb_event_valid,usb_lifecycle,usb_cancel,')
    patch(managed,'.g1_valid(usb_event_valid),','.g1_valid(usb_event_valid),.g1_lifecycle(usb_lifecycle),.g1_cancel(usb_cancel),')
    patch(managed,'    output wire sample_ce_o, sample_valid_o,',
          '    output wire [31:0] scope_status_o,tf_scope_control_o,\n'
          '    output wire [31:0] dac_reference_o,dac_voices_o,dac_health_o,\n'
          '    output wire sample_ce_o, sample_valid_o,')
    patch(managed,'.control_options_o(control_options),',
          '.control_options_o(control_options),.scope_status_o(scope_status_o),.tf_scope_control_o(tf_scope_control_o),'
          '.dac_reference_o(dac_reference_o),.dac_voices_o(dac_voices_o),.dac_health_o(dac_health_o),')
    standalone=stage/'src/ae350/gw138k_controlled_audio.sv'
    patch(standalone,'.control_options_o(control_options),',
          '.control_options_o(control_options),.scope_status_o(),.tf_scope_control_o(),'
          '.dac_reference_o(),.dac_voices_o(),.dac_health_o(),')
    top=stage/'src/push2/gw138k_push_workstation_top.v'
    s=top.read_text()
    # Break the CPU address -> MMIO ready -> CPU stall path in USB clk.
    # The existing streamer shares this same registered transaction boundary.
    s=once(s,'    wire [223:0] usb_words;',
'''    wire host_mmio_select,host_mmio_write,host_mmio_ready;
    wire [7:0] host_mmio_address;
    wire [31:0] host_mmio_wdata,host_mmio_rdata;
    gw138k_mmio_pipeline u_usb_mmio_pipeline(
        .clk(usb_clk),.reset_n(usb_reset_n),
        .select_i(host_mmio_select),.write_i(host_mmio_write),.address_i(host_mmio_address),.wdata_i(host_mmio_wdata),
        .ready_o(host_mmio_ready),.rdata_o(host_mmio_rdata),
        .select_o(mmio_select),.write_o(mmio_write),.address_o(mmio_address),.wdata_o(mmio_wdata),
        .ready_i(mmio_ready),.rdata_i(mmio_rdata));
    wire [223:0] usb_words;''')
    for port in ['select','write','address','wdata','ready','rdata']:
        s=once(s,f'.mmio_{port}(mmio_{port})',f'.mmio_{port}(host_mmio_{port})')
    s=once(s,'    wire synth_hp_bck,synth_hp_ws,synth_hp_din,synth_pa_en;',
'''    wire synth_hp_bck,synth_hp_ws,synth_hp_din,synth_pa_en,synth_sample_ce;
    wire [31:0] scope_status_audio,tf_scope_control_audio,tf_scope_control_50;
    wire tf_control_valid,tf_mode_50,tf_run_50,tf_scope_restart,tf_scope_cancel,tf_scope_error;
    wire [3:0] tf_scope_track;
    reg [4:0] tf_control_divider;
    always @(posedge audio_clk or negedge audio_reset_n)
        if(!audio_reset_n) tf_control_divider<=0;else tf_control_divider<=tf_control_divider+1'b1;
    gw138k_stream_cdc #(.WIDTH(32)) u_tf_control_cdc(
        .reset_n(reset_n && audio_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(&tf_control_divider),.source_data(tf_scope_control_audio),.drop_count(),
        .destination_valid(tf_control_valid),.destination_data(tf_scope_control_50));
    scope_tf_transport u_tf_scope_transport(
        .clk_i(clk_50m),.rst_ni(reset_n),.control_valid_i(tf_control_valid),.control_i(tf_scope_control_50),
        .song_valid_i(song_cmd_valid),.song_track_i(song_cmd_index),
        .playlist_ready_i(playlist_scan_done),.track_count_i(tf_track_count),.card_lost_i(tf_card_lost),
        .mode_o(tf_mode_50),.run_o(tf_run_50),.track_o(tf_scope_track),
        .restart_o(tf_scope_restart),.cancel_analysis_o(tf_scope_cancel),.error_o(tf_scope_error));
    reg tf_run_meta,tf_run_audio;
    always @(posedge audio_clk or negedge audio_reset_n)
        if(!audio_reset_n) begin tf_run_meta<=0;tf_run_audio<=0;end
        else begin tf_run_meta<=tf_run_50;tf_run_audio<=tf_run_meta;end
    wire final_switching,final_sample_valid,final_tf_selected;
    wire [31:0] final_pcm,final_reference,synth_dac_reference,synth_dac_voices,synth_dac_health;
    wire synth_display_valid;
    wire [31:0] synth_display_pcm,synth_display_reference,synth_display_voices,synth_display_status;
    pt8211_observer u_final_output_observer(
        .clk(audio_clk),.reset_n(audio_reset_n && !final_switching),.bck(hp_bck),.ws(hp_ws),.din(hp_din),
        .frame_reference(final_tf_selected ? 32'd0 : synth_dac_reference),
        .pcm_pair(final_pcm),.sample_valid(final_sample_valid),.trigger_reference(final_reference));
    gw138k_stream_cdc #(.WIDTH(128)) u_final_output_cdc(
        .reset_n(reset_n && audio_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(final_sample_valid && !final_switching),
        .source_data({final_pcm,final_reference,final_tf_selected ? 32'd0 : synth_dac_voices,synth_dac_health}),
        .drop_count(),.destination_valid(output_sample_valid),
        .destination_data({output_pcm,output_reference,active_voices,display_status}));''')
    s=once(s,'music_restart_delay==0 && !music_analysis_restart;',
          'music_restart_delay==0 && !music_analysis_restart && !tf_mode_50;')
    s=once(s,'            tf_selected_track<=0;pending_track<=0;',
          '            tf_selected_track<=0;pending_track<=0;tf_recover<=0;tf_recover_wait<=0;')
    s=once(s,'            if(tf_card_lost) begin',
'''            if(tf_scope_cancel) begin
                // Fresh recognition on exit: no mixed tracks/windows. Keep the
                // model and staged CNN caches; a later menu launch rearms it.
                song_pending<=0;music_song_started<=0;tf_recover<=0;
                music_run_reset_count<=3'd4;music_restart_delay<=0;
            end else if(tf_card_lost) begin''')
    s=once(s,'else if(song_cmd_valid) begin','else if(song_cmd_valid && !tf_mode_50) begin')
    s=once(s,'else if(song_pending && music_model_ready) begin','else if(song_pending && music_model_ready && !tf_mode_50) begin')
    s=once(s,".pc_uart_rx_i(music_model_status==4'd14 ? pc_uart_rx_i : 1'b1)",
          ".pc_uart_rx_i((music_model_status==4'd14 || tf_scope_control_audio[12]) ? pc_uart_rx_i : 1'b1)")
    s=once(s,'        .sample_valid_o(audio_sample_valid),',
          '        .scope_status_o(scope_status_audio),.tf_scope_control_o(tf_scope_control_audio),\n'
          '        .dac_reference_o(synth_dac_reference),.dac_voices_o(synth_dac_voices),.dac_health_o(synth_dac_health),\n'
          '        .sample_ce_o(synth_sample_ce),.sample_valid_o(audio_sample_valid),')
    s=once(s,'.display_valid_o(output_sample_valid),.display_pcm_o(output_pcm),.display_reference_o(output_reference),',
          '.display_valid_o(synth_display_valid),.display_pcm_o(synth_display_pcm),.display_reference_o(synth_display_reference),')
    s=once(s,'.display_voices_o(active_voices),.display_status_o(display_status),',
          '.display_voices_o(synth_display_voices),.display_status_o(synth_display_status),')
    # Keep the original adapter CDC observable for independent health telemetry.
    s=once(s,'.audio_status(display_status)', '.audio_status(synth_display_status)')
    s=once(s,'.restart(tf_restart || tf_song_restart),.track_index(tf_selected_track),',
          '.restart(tf_scope_restart || (!tf_mode_50 && (tf_restart || tf_song_restart))),\n        .track_index(tf_mode_50 ? tf_scope_track : tf_selected_track),')
    s=once(s,".playback_hold_i(1'b1),",'.playback_hold_i(!tf_mode_50 || !tf_run_50),')
    s=once(s,'.analysis_hold_i(music_model_ready_q && music_song_started && !music_analysis_done),',
          '.analysis_hold_i(!tf_mode_50 && music_model_ready_q && music_song_started && !music_analysis_done),')
    # Existing bridge uses analysis_enable to gate SD capture. Share this gate
    # for playback, but never assert NN's enable or valid during TF scope mode.
    s=once(s,'.analysis_enable_i(music_analysis_enable),',
          '.analysis_enable_i(music_analysis_enable || (tf_mode_50 && tf_run_50)),')
    s=once(s,'.pcm_valid(analysis_pcm_valid),.pcm_end(analysis_pcm_end),',
          '.pcm_valid(analysis_pcm_valid && !tf_mode_50),.pcm_end(analysis_pcm_end && !tf_mode_50),')
    s=once(s,'.sample_data(tf_pcm_left),.sample_right(tf_pcm_right),\n        .sample_valid(tf_pcm_valid),',
''' .sample_data(tf_run_audio ? tf_pcm_left : 32'sd0),.sample_right(tf_run_audio ? tf_pcm_right : 32'sd0),
        .sample_valid((tf_pcm_valid && tf_run_audio) || (tf_scope_control_audio[12] && !tf_run_audio)),''')
    s=once(s,'''    assign hp_bck=tf_source_active ? tf_hp_bck : synth_hp_bck;
    assign hp_ws=tf_source_active ? tf_hp_ws : synth_hp_ws;
    assign hp_din=tf_source_active ? tf_hp_din : synth_hp_din;
    assign pa_en=tf_source_active ? tf_pa_en : synth_pa_en;''',
'''    scope_dac_select u_scope_output(
        .clk_i(audio_clk),.rst_ni(audio_reset_n),.scope_enable_i(scope_status_audio[8]),
        .tf_source_active_i(tf_scope_control_audio[12]),
        .synth_frame_tick_i(synth_sample_ce),.tf_frame_tick_i(tf_sample_ce),
        .synth_bck_i(synth_hp_bck),.synth_ws_i(synth_hp_ws),.synth_din_i(synth_hp_din),.synth_pa_i(synth_pa_en),
        .tf_bck_i(tf_hp_bck),.tf_ws_i(tf_hp_ws),.tf_din_i(tf_hp_din),.tf_pa_i(tf_pa_en),
        .hp_bck_o(hp_bck),.hp_ws_o(hp_ws),.hp_din_o(hp_din),.pa_en_o(pa_en),
        .tf_selected_o(final_tf_selected),.switching_o(final_switching));''')
    # TF playback status is generated in audio_clk, while the CNN's UART
    # diagnostic trace lives in clk_50m. Synchronize these two level flags;
    # PCM/model/CNN datapaths remain the accepted full83 bytes.
    s=once(s,'    basic_pitch_workstation_link u_music (',
'''    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg tf_format_meta50,tf_format_sync50;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg tf_source_meta50,tf_source_sync50;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin
            tf_format_meta50<=0;tf_format_sync50<=0;tf_source_meta50<=0;tf_source_sync50<=0;
        end else begin
            tf_format_meta50<=tf_format_ready;tf_format_sync50<=tf_format_meta50;
            tf_source_meta50<=tf_source_active;tf_source_sync50<=tf_source_meta50;
        end
    end
    basic_pitch_workstation_link u_music (''')
    s=once(s,'.format_ready(tf_format_ready),.source_active(tf_source_active),',
          '.format_ready(tf_format_sync50),.source_active(tf_source_sync50),')
    s=once(s,'    push2_usb_a_control u_push(',
        '    wire usb_lifecycle,usb_cancel;\n    push2_usb_a_control u_push(')
    s=once(s,'.audio_event(all_usb_event),',
        '.audio_event(all_usb_event),.audio_lifecycle(usb_lifecycle),.audio_cancel(usb_cancel),')
    s=once(s,'.usb_event_valid(all_usb_valid),',
        '.usb_event_valid(all_usb_valid),.usb_lifecycle(usb_lifecycle),.usb_cancel(usb_cancel),')
    s,bus_timing=apply_bus_timing(ROOT,stage,s)
    top.write_text(s)
    # Existing accepted constraints remain, except merged local-release cells
    # now retained in this equivalent new mailbox rather than telemetry.
    sdc=stage/'constraints/tang_mega_138k.sdc'
    s=sdc.read_text().replace(
        'u_runtime/u_performance_cdc/source_release*/CLEAR u_runtime/u_performance_cdc/destination_release*/CLEAR',
        'u_tf_control_cdc/source_release*/CLEAR u_tf_control_cdc/destination_release*/CLEAR')
    s+='\n# Scope transport and final output: acknowledged audio -> 50m mailboxes.\n'
    for inst in ['u_tf_control_cdc','u_final_output_cdc']:
        s+=f'set_max_delay 20.000 -from [get_regs {{{inst}/held_data*}}] -to [get_regs {{{inst}/destination_data*}}]\n'
        s+=f'set_false_path -hold -from [get_regs {{{inst}/held_data*}}] -to [get_regs {{{inst}/destination_data*}}]\n'
        s+=f'set_false_path -to [get_pins {{{inst}/req_meta*/D {inst}/ack_meta*/D}}]\n'
    s+='set_false_path -to [get_pins {tf_run_meta*/D}]\n'
    sdc.write_text(s+timing_constraints(diagnostic_cdc=args.cnn_timing85)+timing_reports())
    cst=stage/'constraints/tang_mega_138k.cst'
    cst.write_text(cst.read_text()+physical_constraints())
    tcl=stage/'scripts/build.tcl'
    tcl.write_text(once(tcl.read_text(),'set_option -user_code 00000083\n',
                        'set_option -user_code '+args.user_code.upper()+'\n' if args.full else ''))
    usb_firmware=stage_usb_firmware(ROOT,stage,output,args.riscv_prefix)
    (output/'usb_firmware_metadata.json').write_text(json.dumps(usb_firmware,indent=2)+'\n')
    verify_cnn_inputs(stage,music)
    (output/'cnn_source_audit.json').write_text(json.dumps(cnn_sources,indent=2)+'\n')
    inputs={str(p.relative_to(stage)):sha(p) for p in stage.rglob('*') if p.is_file()}
    changed_from_base=sorted(name for name,digest in inputs.items() if originals.get(name)!=digest)
    metadata=dict(baseline=BASE.relative_to(ROOT).as_posix(),accepted_commit=ACCEPTED_COMMIT,
                  git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  build_mode='prepare_only' if args.prepare_only else 'full' if args.full else 'synthesis_only',
                  changed_from_base=changed_from_base,music_sha256=music,usb_firmware=usb_firmware,
                  cnn_source_policy=cnn_sources['policy'],bus_timing=bus_timing,
                  cnn_source_audit_sha256=sha(output/'cnn_source_audit.json'),
                  live_usb_control_sha256=sha(ROOT/'rtl/push2_usb_a_control.sv'),
                  frozen_sha256={live:digest for live,(_,digest) in FROZEN.items()},
                  user_code_assigned=args.full,user_code='0x'+args.user_code.upper() if args.full else None,
                  hardware_tested=False)
    (output/'workstation_inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    (output/'build_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(output,flush=True)
    print('CNN inputs:',cnn_sources['policy']+',',len(music),'files; live differences excluded:',
          len(cnn_sources['changed']),'changed,',len(cnn_sources['added']),'added,',
          len(cnn_sources['missing']),'missing; see cnn_source_audit.json',flush=True)
    if args.prepare_only:return
    with (output/'gowin.log').open('w') as log:
        result=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,
                              env=dict(os.environ,PRJ1_FLOW='all' if args.full else 'syn'),stdout=log,stderr=subprocess.STDOUT)
    verify_cnn_inputs(stage,music)
    changes=[name for name,digest in inputs.items() if sha(stage/name)!=digest]
    (output/'tool_result.json').write_text(json.dumps(dict(exit_code=result.returncode,inputs_unchanged=not changes,
                                                        changed=changes,build_mode=metadata['build_mode'],hardware_tested=False),indent=2)+'\n')
    if result.returncode or changes:raise SystemExit('Gowin/input check failed; see '+str(output/'gowin.log'))
    report=audit(output,'full' if args.full else 'synthesis_only')
    for instance in ['u_scope_output','u_final_output_observer','u_final_output_cdc',
                     'u_tf_control_cdc','u_tf_scope_transport','u_delay_ddr_dma']:
        assert instance in report['hierarchy'],'missing merged feature: '+instance
    print('Complete workstation SYN BSRAM',report['bsram'],'/',report['bsram_capacity'],flush=True)
    if args.full:
        assert report['pnr_available'],'full build missing P&R resource evidence'
        print('Complete workstation P&R BSRAM',report['pnr_bsram'],'/',report['bsram_capacity'],flush=True)
        from audit_workstation_timing import audit as audit_timing
        from audit_workstation_cdc import audit as audit_cdc
        sys.path.insert(0,str(stage/'scripts'))
        from check_video_pll_init import inspect_video_pll_init
        timing=audit_timing(output)
        (output/'workstation_timing.json').write_text(json.dumps(timing,indent=2)+'\n')
        if not timing['timing_closed']:raise ValueError('routed timing failed: '+repr(timing['problems']))
        # The strict accepted83 source is retained for historical comparisons.
        # Only the current timing source has the added diagnostic receivers.
        if args.cnn_timing85:
            cdc=audit_cdc(output)
            (output/'workstation_cdc.json').write_text(json.dumps(cdc,indent=2)+'\n')
            if not cdc['passed']:raise ValueError('routed CDC failed: '+repr(cdc['errors']))
        errors,evidence=inspect_video_pll_init((stage/'impl/pnr/Prj1.sdf').read_text(),(stage/'impl/pnr/Prj1.vo').read_text(),stage)
        (output/'pll_init_audit.json').write_text(json.dumps(dict(errors=errors,evidence=evidence),indent=2)+'\n')
        if errors:raise ValueError('PLL_INIT propagation failed: '+repr(errors))
        subprocess.run([sys.executable,str(ROOT/'tools/audit_scope_routes.py'),str(output),'--output',str(output/'scope_routes.json')],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        scope=json.loads((output/'scope_routes.json').read_text())
        if not scope['passed']:raise ValueError('scope CDC failed: '+repr(scope['errors']))

    print('Board state unchanged; programming and acceptance require separate recorded operations.',flush=True)


if __name__=='__main__':main()
