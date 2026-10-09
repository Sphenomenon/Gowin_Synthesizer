#!/usr/bin/env python3
"""Build the complete deployed full85 workstation with CNN Flash boot added.

Never operates hardware or edits LATEST_WORKSTATION. Prepare/SYN use no
UserCode. Full builds require a fresh explicit UserCode and retain the frozen
DDR/display/audio sources, clock constraints and timing checks.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from build_full_song_83_bp_ddr_isolation import FROZEN
from workstation_memory import audit
from cnn_ddr_pipeline_patch import patch_hdmi,patch_top,HDMI,PIPELINE,patch_delay_fifo,DELAY,SYNC_FIFO,TF_DMA,retime_tf_write_buffer,CLIENT_QUEUES,TF_BUFFER,TMDS,retime_tf_buffer_enable,retime_tf_capture_limit,retime_display_enable,retime_tmds_statistics,DASHBOARD,RENDERER,predecode_dashboard,align_renderer_predecode,predecode_dashboard_text_coordinates,DELAY_DMA,parallel_delay_rptr,power_two_tf_ring,parallel_dashboard_cards,lut_tmds_popcount,predecode_dashboard_background,register_arbiter_tag_flags,MODEL_MEMORY_READY_BLOCK,retime_model_memory_ready,predecode_dashboard_wave_heights,narrow_feature_read_slot,PIXEL_SKID,patch_hdmi_pixel_skid,parallel_tf_byte_counters,predecode_dashboard_dynamic_ink,BIST,retime_bist_expected_pattern,retime_tf_read_total,parallel_renderer_spectrum_address,shallow_dashboard_card_select,fast_tf_read_availability,quiet_shared_analysis_column,pipeline_bist_compare,mask_tf_write_epoch,registered_tf_read_response,pipeline_tf_read_return
from build_cnn_flash_image import build_image,load_words,pack_flash,gowin_data_fs
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1'
BASE_FS_SHA='7f96a42b0adf4e87863089d610a454e570876a78c7917d892949116918015444'
OVERLAYS=[f'rtl/music/{name}' for name in (
    'basic_pitch_pcm_pipeline.sv','basic_pitch_workstation_link.sv',
    'basic_pitch_uart_model_loader.sv','basic_pitch_flash_model_loader.sv',
    'basic_pitch_boot_model_loader.sv','basic_pitch_flash_map.svh','basic_pitch_flash_io_guard.sv')]
CST='''// SOM configuration Flash, x1 SPI after FPGA configuration (MSPI-as-GPIO).
// GW5AST-LV138PG484AC2/I1; board PCB nets and UG986 PG484A agree.
IO_LOC "flash_clk" L12;
IO_PORT "flash_clk" IO_TYPE=LVCMOS33 PULL_MODE=DOWN DRIVE=8 BANK_VCCIO=3.3;
IO_LOC "flash_cs_n" T19;
IO_PORT "flash_cs_n" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8 BANK_VCCIO=3.3;
IO_LOC "flash_mosi" P22;
IO_PORT "flash_mosi" IO_TYPE=LVCMOS33 PULL_MODE=NONE DRIVE=8 BANK_VCCIO=3.3;
IO_LOC "flash_miso" R22;
IO_PORT "flash_miso" IO_TYPE=LVCMOS33 PULL_MODE=UP BANK_VCCIO=3.3;
// IO2/WP and IO3/HOLD released high for read-only x1 SPI. Board pull-ups also
// keep them high during configuration and before user logic takes ownership.
IO_LOC "flash_wp_n" P21;
IO_PORT "flash_wp_n" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8 BANK_VCCIO=3.3;
IO_LOC "flash_hold_n" R21;
IO_PORT "flash_hold_n" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8 BANK_VCCIO=3.3;
'''
SDC='''
# New calibration level CDC; only the first sampling D pin is asynchronous.
set_false_path -to [get_pins {u_music/model_memory_meta*/D}]
# Conservatively constrain the NOR input relative to the 50-MHz sampling clock.
# SPI toggles every 4 clk50 cycles (6.25 MHz); 15 ns allows NOR tCLQV+PCB flight.
# No blanket input false-path or relaxation of existing workstation clocks.
set_input_delay 15.000 -clock [get_clocks {clk_50m}] [get_ports {flash_miso}]
'''

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_json(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def used_codes():
    codes=set()
    for p in list(ROOT.glob('*.json'))+list((ROOT/'reports').glob('*.json'))+list((ROOT/'results').rglob('*metadata.json')):
        # A failed attempt that emitted no bitstream did not release a code.
        status=p.parent/'tool_result.json'
        if status.exists() and not (p.parent/'Prj1/impl/pnr/Prj1.fs').exists():
            try:
                if json.loads(status.read_text())['exit_code']!=0:continue
            except (KeyError,ValueError):pass
        try:codes.update(int(s,16) for s in re.findall(r'0x([0-9A-Fa-f]{8})',p.read_text()))
        except (OSError,UnicodeError):continue
    return codes

def expected_hdmi(metadata):
    text=patch_hdmi((BASE/'Prj1'/HDMI).read_text(),metadata.get('buffered_ddr_clients',False))
    if metadata.get('retimed_display_enable'):text=retime_display_enable(text)
    return patch_hdmi_pixel_skid(text) if metadata.get('registered_pixel_ready') else text

def expected_tf_dma(metadata):
    text=retime_tf_write_buffer((BASE/'Prj1'/TF_DMA).read_text())
    if metadata.get('retimed_tf_capture_limit'):text=retime_tf_capture_limit(text)
    if metadata.get('power_two_tf_ring'):text=power_two_tf_ring(text)
    if metadata.get('parallel_tf_byte_counters'):text=parallel_tf_byte_counters(text)
    if metadata.get('retimed_tf_read_total'):text=retime_tf_read_total(text)
    if metadata.get('fast_tf_read_availability'):text=fast_tf_read_availability(text)
    if metadata.get('masked_tf_write_epoch'):text=mask_tf_write_epoch(text)
    if metadata.get('registered_tf_response'):text=registered_tf_read_response(text)
    return pipeline_tf_read_return(text) if metadata.get('pipelined_tf_read_return') else text

def audit_serial_compatibility(output):
    stage=output/'Prj1'
    paths=['rtl/music/basic_pitch_pcm_pipeline.sv','rtl/music/basic_pitch_uart_model_loader.sv',
        'rtl/music/basic_pitch_ddr16_port.sv','rtl/music/basic_pitch_ddr_command_buffer.sv',
        'rtl/music/music_async_fifo.sv','src/video/hdmi_display.v','firmware/boot.mem',
        'vendor/gowin_ddr3/ddr3_memory_interface.v']
    metadata=json.loads((output/'build_metadata.json').read_text())
    pipelined=metadata.get('pipelined_ddr_arbiter',False)
    if pipelined:
        assert (stage/HDMI).read_text()==expected_hdmi(metadata),'display changed beyond registered DDR bus boundary'
        pipeline=(ROOT/PIPELINE).read_text()
        if metadata.get('registered_arbiter_tag_flags'):pipeline=register_arbiter_tag_flags(pipeline)
        assert (stage/PIPELINE).read_text()==pipeline,'shared pipeline source drift'
    if metadata.get('retimed_bist_expected_pattern'):
        bist=retime_bist_expected_pattern((BASE/'Prj1'/BIST).read_text())
        if metadata.get('pipelined_bist_compare'):bist=pipeline_bist_compare(bist)
        assert (stage/BIST).read_text()==bist,'BIST source differs from explicitly verified transforms'
    if metadata.get('registered_pixel_ready'):assert sha(stage/PIXEL_SKID)==sha(ROOT/PIXEL_SKID),'pixel skid source drift'
    if metadata.get('buffered_ddr_clients'):
        assert sha(stage/CLIENT_QUEUES)==sha(ROOT/CLIENT_QUEUES),'client queue source drift'
    if metadata.get('retimed_tf_write_buffer'):
        assert (stage/TF_DMA).read_text()==expected_tf_dma(metadata),'TF changed beyond local staging register update'
    if metadata.get('retimed_tf_buffer_enable'):
        assert (stage/TF_BUFFER).read_text()==retime_tf_buffer_enable((BASE/'Prj1'/TF_BUFFER).read_text()),'TF buffer retime drift'
    if metadata.get('registered_tf_response'):
        assert metadata.get('buffered_ddr_clients') and metadata.get('pipelined_ddr_arbiter') and metadata.get('retimed_tf_buffer_enable'),'registered TF response requires complete registered DDR boundary'
        core=(stage/PIPELINE).read_text()
        assert 'response_valid<=pop;' in core and 'assign audio_response=response_valid && response_owner==4;' in core,'TF response is not registered/tag owned'
        assert 'basic_pitch_ddr_client_queues u_arbiter(' in (stage/HDMI).read_text(),'missing client queues'
        top=(stage/'src/push2/gw138k_push_workstation_top.v').read_text()
        assert '.audio_response(audio_ddr_response)' in top and '.ddr_response(audio_ddr_response)' in top and 'tf_audio_ddr_command_buffer u_audio_command_buffer(' in top,'TF response/command topology drift'
    if metadata.get('retimed_tmds_statistics'):
        tmds=retime_tmds_statistics((BASE/'Prj1'/TMDS).read_text())
        if metadata.get('lut_tmds_popcount'):tmds=lut_tmds_popcount(tmds)
        assert (stage/TMDS).read_text()==tmds,'TMDS changed beyond equivalent statistics'
    if metadata.get('predecoded_dashboard'):
        dashboard=predecode_dashboard((BASE/'Prj1'/DASHBOARD).read_text())
        if metadata.get('predecoded_text_coordinates'):dashboard=predecode_dashboard_text_coordinates(dashboard)
        if metadata.get('parallel_dashboard_cards'):dashboard=parallel_dashboard_cards(dashboard)
        if metadata.get('predecoded_background_coordinates'):dashboard=predecode_dashboard_background(dashboard,metadata.get('complete_background_coordinates',False))
        if metadata.get('predecoded_wave_heights'):dashboard=predecode_dashboard_wave_heights(dashboard)
        if metadata.get('predecoded_dynamic_background_ink'):dashboard=predecode_dashboard_dynamic_ink(dashboard)
        if metadata.get('shallow_card_select'):dashboard=shallow_dashboard_card_select(dashboard)
        assert (stage/DASHBOARD).read_text()==dashboard,'dashboard predecode source drift'
        renderer=align_renderer_predecode((BASE/'Prj1'/RENDERER).read_text())
        if metadata.get('parallel_renderer_spectrum_address'):renderer=parallel_renderer_spectrum_address(renderer)
        if metadata.get('quiet_shared_analysis_column'):renderer=quiet_shared_analysis_column(renderer)
        assert (stage/RENDERER).read_text()==renderer,'renderer changed beyond audited latency/address transformations'
    paths += [str(p.relative_to(BASE/'Prj1')) for p in (BASE/'Prj1').rglob('gw138k_ddr_arbiter.sv')]
    evidence={p:dict(unchanged=sha(BASE/'Prj1'/p)==sha(stage/p),sha256=sha(stage/p)) for p in paths}
    if metadata.get('parallel_delay_pointer'):
        assert (stage/DELAY_DMA).read_text()==parallel_delay_rptr((BASE/'Prj1'/DELAY_DMA).read_text()),'delay DMA changed beyond bit-exact read pointer increment'
    if metadata.get('synchronous_delay_write_fifo'):
        assert (stage/DELAY).read_text()==patch_delay_fifo((BASE/'Prj1'/DELAY).read_text(),metadata.get('synchronous_delay_read_fifo',False)),'delay changed beyond input FIFO type'
        assert sha(stage/SYNC_FIFO)==sha(ROOT/SYNC_FIFO),'sync FIFO source drift'
    if pipelined:evidence[HDMI].update(unchanged=True,normalization='Only native DDR boundary and paired registered consumer bus; image/raster code unchanged')
    if json.loads((output/'build_metadata.json').read_text()).get('retimed_cache_read'):
        pipeline='rtl/music/basic_pitch_pcm_pipeline.sv'
        text=(stage/pipeline).read_text().replace(
            '            for (integer i=0;i<8;i=i+1)\n                if (dwell_bucket(state)==i) dwell_count[i] <= dwell_count[i] + 1\'b1;',
            '            dwell_count[dwell_bucket(state)] <= dwell_count[dwell_bucket(state)] + 1\'b1;')
        if metadata.get('narrowed_feature_read_slot'):
            assert text.count('$unsigned(feature_read_rel[2:0])')==3,'feature slot overlay drift'
            text=text.replace('$unsigned(feature_read_rel[2:0])','$unsigned(feature_read_rel)')
        assert text==(BASE/'Prj1'/pipeline).read_text(),'CNN changed beyond dwell telemetry unrolling'
        evidence[pipeline]['unchanged']=True;evidence[pipeline]['normalization']='Equivalent parallel dwell-counter update'+('; formally equal bounded slot address decoder' if metadata.get('narrowed_feature_read_slot') else '')+'; CNN data/arithmetic/cycles exact'
        assert sha(stage/'rtl/music/basic_pitch_weight_cache.sv')==sha(ROOT/'rtl/music/basic_pitch_weight_cache.sv'),'cache retiming source drift'
    assert all(v['unchanged'] for v in evidence.values()),'serial transport changed proven CNN/DDR/firmware'
    original=(BASE/'Prj1/rtl/music/basic_pitch_workstation_link.sv').read_text()
    link=(stage/'rtl/music/basic_pitch_workstation_link.sv').read_text()
    credit_enabled=json.loads((output/'build_metadata.json').read_text()).get('registered_response_credit',False)
    if credit_enabled:
        guarded=register_response_credit(original)
        start=guarded.index('    wire ddr_read_credit;')
        stop=guarded.index('    basic_pitch_ddr16_port u_ddr16 (',start)
        wrapper=guarded[start:stop]
        assert link.count(wrapper)==1,'credit reservation wrapper drift'
        link=link.replace(wrapper,'').replace('(ddr_cmd_data[48] || ddr_read_credit)','(ddr_cmd_data[48] || ddr_rsp_fifo_ready)')
        assert sha(stage/'rtl/music/basic_pitch_ddr_read_credit.sv')==sha(ROOT/'rtl/music/basic_pitch_ddr_read_credit.sv'),'credit source drift'
    if metadata.get('retimed_model_memory_ready'):
        assert link.count(MODEL_MEMORY_READY_BLOCK)==1,'localmemory-ready wrapper drift'
        link=link.replace(MODEL_MEMORY_READY_BLOCK,'').replace('req_valid_i(ddr_cmd_valid && model_memory_ready &&','req_valid_i(ddr_cmd_valid && memory_calibrated &&')
    link=link.replace('    input wire [1:0] model_boot_source,model_boot_error,\n','')
    link=link.replace("{score_count,score_first,score_last,model_boot_source,\n                             (model_status==0 && model_boot_source==2 ? model_boot_error : model_error_stage),",
                      "{score_count,score_first,score_last,2'd0,model_error_stage,")
    assert link==original,'serial native-memory link changed beyond diagnostics'
    write_json(output/'serial_compatibility_source_audit.json',dict(passed=True,
        baseline=str(BASE.relative_to(ROOT)),candidate=str(output),unchanged_sources=evidence,
        registered_response_credit=credit_enabled,pipelined_ddr_arbiter=pipelined,link_change_only='Diagnostic fields plus explicit read-slot reservation wrapper when enabled; native DDR16/FIFO/parser source unchanged'))

def retime_start_delay(text):
    """Register the zero predicate of the existing countdown with exact next-state priority."""
    declaration='    reg [21:0] music_restart_delay;'
    assert text.count(declaration)==1
    text=text.replace(declaration,declaration+'\n    reg music_delay_expired;')
    expression='music_restart_delay==0 && !music_analysis_restart'
    assert text.count(expression)==1
    text=text.replace(expression,'music_delay_expired && !music_analysis_restart')
    anchor='    assign debug_uart_tx=music_report_sending ? music_report_serial : runtime_serial;'
    assert text.count(anchor)==1
    predicate="""    // Predicate equals the post-edge countdown value, including all original
    // load/cancel priorities. No added start latency or CNN arithmetic change.
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) music_delay_expired<=1'b1;
        else if(tf_scope_cancel || tf_card_lost) music_delay_expired<=1'b1;
        else if(tf_recover && playlist_scan_done && tf_track_count!=0)
            music_delay_expired<=1'b0;
        else if(!tf_recover && !(song_cmd_valid && !tf_mode_50) &&
                song_pending && music_model_ready && !tf_mode_50)
            music_delay_expired<=1'b0;
        else if(tf_restart) music_delay_expired<=1'b0;
        else if(music_restart_delay==1) music_delay_expired<=1'b1;
    end
"""
    return text.replace(anchor,predicate+anchor)

def retime_video_frame_telemetry(text):
    """One pixel-cycle telemetry event pipeline; no scanout/pixel/DDR changes."""
    anchor='    wire pixel_frame_reset_n = pixel_reset_n;'
    assert text.count(anchor)==1 and text.count('            if (vblank_start) begin')==1
    text=text.replace(anchor,anchor+"""
    reg frame_advance_q;
    always @(posedge pixel_clk or negedge pixel_frame_reset_n) begin
        if(!pixel_frame_reset_n) frame_advance_q<=1'b0;
        else frame_advance_q<=vblank_start;
    end""")
    return text.replace('            if (vblank_start) begin','            if (frame_advance_q) begin')

def register_response_credit(text):
    anchor="    basic_pitch_ddr16_port u_ddr16 ("
    assert text.count(anchor)==1
    text=text.replace(anchor,"""    wire ddr_read_credit;
    basic_pitch_ddr_read_credit u_ddr_read_credit (
        .clk_i(memory_clk),.rst_ni(memory_reset_n),
        .fifo_ready_i(ddr_rsp_fifo_ready),
        .read_accept_i(ddr_cmd_ready && !ddr_cmd_data[48]),
        .response_valid_i(ddr_rsp_valid),.credit_o(ddr_read_credit));
"""+anchor)
    old="(ddr_cmd_data[48] || ddr_rsp_fifo_ready)"
    assert text.count(old)==1
    return text.replace(old,"(ddr_cmd_data[48] || ddr_read_credit)")

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--retime-bist-expected-pattern',action='store_true',help='same-cycle BIST expected pattern captured during original request beat, no self-test waiver')
    ap.add_argument('--pipeline-bist-compare',action='store_true',help='capture8 lane comparisons at response, account next cycle; startup +5.243ms for8MiB')
    ap.add_argument('--predecode-dynamic-background-ink',action='store_true',help='wave/spectrum/peak ink predicates at existing A edge, same B result/cycles')
    ap.add_argument('--parallel-tf-byte-counters',action='store_true',help='exact32bit+6bit sums with parallel byte carries')
    ap.add_argument('--retime-tf-read-total',action='store_true',help='prepare exact next byte count at accepted read; preserve same-cycle response')
    ap.add_argument('--fast-tf-read-availability',action='store_true',help='exact modulo byte delta<32 via grouped count comparison; zero extra cycles')
    ap.add_argument('--mask-tf-write-epoch',action='store_true',help='same-cycle byte-valid mask zeros instead of256-bit data epoch clear')
    ap.add_argument('--registered-tf-response',action='store_true',help='specialize audited queued DDR to nonzero-cycle returns; generic frozen TF stays unchanged')
    ap.add_argument('--pipeline-tf-read-return',action='store_true',help='register qualified TF response/data together; support zero-cycle native, consume1UIcyclelater')
    ap.add_argument('--parallel-renderer-spectrum-address',action='store_true',help='precompute both spectrum columns before final advance select; zero added cycles')
    ap.add_argument('--quiet-shared-analysis-column',action='store_true',help='shared-render FFT readback follows actual snapshot exporter address; direct mode unchanged')
    ap.add_argument('--shallow-card-select',action='store_true',help='resolve original card priority once, mask parallel relative/text payloads; exact0extra cycles')
    ap.add_argument('--complete-background-coordinates',action='store_true',help='predecode sized-literal geometry/diamond/arrow coordinates in existing stage')
    ap.add_argument('--register-pixel-ready',action='store_true',help='two-beat register skid before frozen frame writer; same ordered pixels/metadata, done after drain')
    ap.add_argument('--retime-model-memory-ready',action='store_true',help='local1memory-clockcalibrationlevel capture before provenDDR16 request gate')
    ap.add_argument('--predecode-wave-heights',action='store_true',help='wave shift/clamp in existing predecode stage, bit-exact raster')
    ap.add_argument('--narrow-feature-read-slot',action='store_true',help='formally identical feature-cache address decoder, zero extra cycles; bounded relative slots use3bits')
    ap.add_argument('--tighten-feature-read-route',action='store_true',help='physical19ns bound on observed conv-kh to feature-cache address; originalCNN/clock unchanged')
    ap.add_argument('--register-arbiter-tag-flags',action='store_true',help='same-edge predicted tag full/empty avoids native-en/count ready feedback')
    ap.add_argument('--predecode-background-coordinates',action='store_true',help='pure background coordinate predicates computed on precedingA edge; no extra pixel latency')
    ap.add_argument('--lut-tmds-popcount',action='store_true',help='parallel4-bit LUT population counters; identical10-bitTMDS every cycle')
    ap.add_argument('--parallel-dashboard-cards',action='store_true',help='parallel constant animation targets and carry-save card text geometry; frame/cycle-exact')
    ap.add_argument('--locate-reference-pll-helper',action='store_true',help='physical-only primitive group near reference PLL bottom-left; unchanged official helper RTL/clock/10ns audit')
    ap.add_argument('--predecode-text-coordinates',action='store_true',help='refine one-stage raster predecode with parallel constant font arithmetic and animated-card hit')
    ap.add_argument('--parallel-delay-pointer',action='store_true',help='bit-exact parallel byte-group rptr+4,all32-bit carry/wrap values')
    ap.add_argument('--power-two-tf-ring',action='store_true',help='constant-mask ring increment for power-of-two capacity; preserve generic nonpower-of-two arithmetic')
    ap.add_argument('--predecode-dashboard',action='store_true',help='one stopped raster predecode stage,bit-exactpixel/ordering with1enabledcycle latency')
    ap.add_argument('--tighten-pll-setting-route',action='store_true',help='4.5ns exactRomDreg-Q toICPSEL/LPFRES route for independent full10nsPLL budget')
    ap.add_argument('--tighten-remaining-ddr-video',action='store_true',help='physical8ns budgets on observed DDR UI rendering/ring paths and6ns PLL control endpoint; all original clocks/hold checks remain')
    ap.add_argument('--sync-delay-read-fifo',action='store_true',help='use synchronous FIFO for return history too; explicit physical budget268')
    ap.add_argument('--retime-tf-buffer-enable',action='store_true',help='keep TF command payload CE local to idle occupancy; valid data/commands exact')
    ap.add_argument('--retime-tf-capture-limit',action='store_true',help='register terminal capture-count predicate ahead of TF byte staging')
    ap.add_argument('--retime-display-enable',action='store_true',help='register startup/fault display permission one memory cycle; raster/data algorithm unchanged')
    ap.add_argument('--retime-tmds-statistics',action='store_true',help='unconditionally compute masked input ones; encoded10-bit codes cycle-exact')
    ap.add_argument('--buffer-ddr-clients',action='store_true',help='per-client one-entry stable request slots with registered arbitration selection; no BSRAM')
    ap.add_argument('--retime-tf-write-buffer',action='store_true',help='equivalent local TF byte staging with delayed clearing after accepted DDR beat')
    ap.add_argument('--sync-delay-write-fifo',action='store_true',help='replace only delay maintenance write FIFO with synchronous65x512 BSRAM read; physical budget264')
    ap.add_argument('--pipeline-ddr-arbiter',action='store_true',help='register shared native DDR command and return-data boundaries;32 read tags')
    ap.add_argument('--register-response-credit',action='store_true',help='reserve return FIFO slot with registered read credit; break DDR arbitration feedback')
    ap.add_argument('--replicate-resources',action='store_true',help='enable documented timing-driven high-fanout register replication during PNR')
    ap.add_argument('--retime-cache-read',action='store_true',help='equivalent one-cycle cache range mask plus parallel dwell counters; no CNN arithmetic change')
    ap.add_argument('--retime-video-telemetry',action='store_true',help='pipeline diagnostic-only vblank count by one pixel cycle; unchanged image and DDR path')
    ap.add_argument('--retime-start-delay',action='store_true',help='cycle-exact registered countdown-zero predicate; no start latency change')
    ap.add_argument('--defer-ddr-startup',action='store_true',help='experimental100ms settling after audio/video lock before initial DDR reset release; no PHY/data/recovery changes')
    ap.add_argument('--transport',choices=('serial','direct'),default='serial',help='serial preserves the full85 CNN/native-DDR hierarchy; direct is the earlier diagnostic')
    ap.add_argument('--flow',choices=('prepare','syn','all','pnr'),default='syn')
    ap.add_argument('--output',type=Path)
    ap.add_argument('--user-code')
    ap.add_argument('--synthesis-from',type=Path,help='reuse identical successful RTL synthesis after a CST-only failure')
    ap.add_argument('--incremental-baseline',action='store_true',help='reuse verified full85 .p placement with fresh synthesis and fresh routing; reject any unrouted net')
    ap.add_argument('--incremental-mode',choices=('place','pnr'),default='place',help='fresh synthesis; place uses .p, pnr defaults to .pr per SUG100; both paired references are hash-checked')
    ap.add_argument('--incremental-pnr-entry',choices=('p','pr'),help='explicit pnr entry format; SUG100 says pr while SUG1220 says p; experimental comparison')
    ap.add_argument('--route-option',type=int,choices=(0,1,2),default=1,help='Gowin route search option, recorded per isolated candidate')
    ap.add_argument('--place-option',type=int,choices=(0,1,2,3),default=2,help='placement search; default retains full85 option2')
    ap.add_argument('--tighten-video-control',action='store_true',help='6ns physical max-delay for pixel reset and frame telemetry; keep original148.5MHz and hold checks')
    ap.add_argument('--tighten-cache-reset',action='store_true',help='tighten existing synchronous weight-cache RESET endpoint max delay to 18 ns')
    args=ap.parse_args()
    if args.incremental_pnr_entry is not None and (not args.incremental_baseline or args.incremental_mode!='pnr'):
        ap.error('--incremental-pnr-entry requires --incremental-baseline --incremental-mode pnr')
    reference_suffix=(args.incremental_pnr_entry or 'pr') if args.incremental_mode=='pnr' else 'p'
    if args.defer_ddr_startup and args.transport!='serial':ap.error('--defer-ddr-startup requires serial transport with startup history alignment')
    if args.retime_model_memory_ready and args.transport!='serial':ap.error('--retime-model-memory-ready requires serial')
    if args.register_pixel_ready and not args.pipeline_ddr_arbiter:ap.error('--register-pixel-ready requires --pipeline-ddr-arbiter')
    if args.parallel_tf_byte_counters and not args.power_two_tf_ring:ap.error('--parallel-tf-byte-counters requires --power-two-tf-ring')
    if args.retime_tf_read_total and not args.parallel_tf_byte_counters:ap.error('--retime-tf-read-total requires --parallel-tf-byte-counters')
    if args.fast_tf_read_availability and not args.retime_tf_read_total:ap.error('--fast-tf-read-availability requires --retime-tf-read-total')
    if args.mask_tf_write_epoch and not (args.fast_tf_read_availability and args.retime_tf_capture_limit):ap.error('--mask-tf-write-epoch requires --fast-tf-read-availability and --retime-tf-capture-limit')
    if args.registered_tf_response and not (args.mask_tf_write_epoch and args.buffer_ddr_clients and args.retime_tf_buffer_enable):ap.error('--registered-tf-response requires --mask-tf-write-epoch --buffer-ddr-clients --retime-tf-buffer-enable')
    if args.pipeline_tf_read_return and (not args.mask_tf_write_epoch or args.registered_tf_response):ap.error('--pipeline-tf-read-return requires --mask-tf-write-epoch and is exclusive with --registered-tf-response')
    if args.parallel_renderer_spectrum_address and not args.predecode_dashboard:ap.error('--parallel-renderer-spectrum-address requires --predecode-dashboard')
    if args.quiet_shared_analysis_column and not args.predecode_dashboard:ap.error('--quiet-shared-analysis-column requires --predecode-dashboard')
    if args.pipeline_bist_compare and not args.retime_bist_expected_pattern:ap.error('--pipeline-bist-compare requires --retime-bist-expected-pattern')
    if args.complete_background_coordinates and not args.predecode_background_coordinates:ap.error('--complete-background-coordinates requires --predecode-background-coordinates')
    if args.predecode_dynamic_background_ink and not args.complete_background_coordinates:ap.error('--predecode-dynamic-background-ink requires --complete-background-coordinates')
    if args.narrow_feature_read_slot and not args.retime_cache_read:ap.error('--narrow-feature-read-slot requires --retime-cache-read')
    if args.predecode_wave_heights and not args.predecode_text_coordinates:ap.error('--predecode-wave-heights requires --predecode-text-coordinates')
    if args.register_arbiter_tag_flags and not args.pipeline_ddr_arbiter:ap.error('--register-arbiter-tag-flags requires --pipeline-ddr-arbiter')
    if args.predecode_background_coordinates and not args.predecode_text_coordinates:ap.error('--predecode-background-coordinates requires --predecode-text-coordinates')
    if args.lut_tmds_popcount and not args.retime_tmds_statistics:ap.error('--lut-tmds-popcount requires --retime-tmds-statistics')
    if args.parallel_dashboard_cards and not args.predecode_text_coordinates:ap.error('--parallel-dashboard-cards requires --predecode-text-coordinates')
    if args.shallow_card_select and not args.parallel_dashboard_cards:ap.error('--shallow-card-select requires --parallel-dashboard-cards')
    if args.predecode_text_coordinates and not args.predecode_dashboard:ap.error('--predecode-text-coordinates requires --predecode-dashboard')
    if args.parallel_delay_pointer and not args.pipeline_ddr_arbiter:ap.error('--parallel-delay-pointer requires --pipeline-ddr-arbiter')
    if args.power_two_tf_ring and not args.retime_tf_write_buffer:ap.error('--power-two-tf-ring requires --retime-tf-write-buffer')
    if args.sync_delay_read_fifo and not args.sync_delay_write_fifo:ap.error('--sync-delay-read-fifo requires --sync-delay-write-fifo')
    if args.retime_tf_capture_limit and not args.retime_tf_write_buffer:ap.error('--retime-tf-capture-limit requires --retime-tf-write-buffer')
    if args.retime_display_enable and not args.pipeline_ddr_arbiter:ap.error('--retime-display-enable requires --pipeline-ddr-arbiter')
    if args.buffer_ddr_clients and not args.pipeline_ddr_arbiter:ap.error('--buffer-ddr-clients requires --pipeline-ddr-arbiter')
    if args.retime_tf_write_buffer and not args.pipeline_ddr_arbiter:ap.error('--retime-tf-write-buffer requires --pipeline-ddr-arbiter')
    if args.sync_delay_write_fifo and not args.pipeline_ddr_arbiter:ap.error('--sync-delay-write-fifo requires --pipeline-ddr-arbiter')
    if args.pipeline_ddr_arbiter and args.transport!='serial':ap.error('--pipeline-ddr-arbiter requires serial transport')
    if args.register_response_credit and args.transport!='serial':ap.error('--register-response-credit requires serial transport')
    if args.retime_cache_read and args.transport!='serial':ap.error('--retime-cache-read currently requires serial transport')
    if args.synthesis_from and args.flow!='all':ap.error('--synthesis-from requires --flow all')
    if args.incremental_mode=='pnr' and not args.incremental_baseline:ap.error('--incremental-mode pnr requires --incremental-baseline')
    if args.incremental_baseline and (args.flow!='all' or args.synthesis_from):
        ap.error('--incremental-baseline requires a fresh --flow all, without --synthesis-from')
    if args.flow=='all' and (not args.user_code or not re.fullmatch('[0-9A-Fa-f]{8}',args.user_code) or int(args.user_code,16)==0):
        ap.error('--flow all requires a fresh nonzero eight-hex-digit --user-code')
    if args.flow in ('prepare','syn') and args.user_code:ap.error('Prepare/SYN assign no UserCode')
    if args.flow=='all' and int(args.user_code,16) in used_codes():ap.error('UserCode already recorded')
    if args.flow=='pnr' and (args.output is None or args.user_code):ap.error('PNR needs existing --output, keeps its original UserCode')
    output=(args.output or ROOT/'results'/datetime.now().strftime('workstation_flash_boot_%Y%m%d_%H%M%S_%f')).resolve()
    stage=output/'Prj1'
    overlays=OVERLAYS if args.transport=='direct' else [f'rtl/music/{n}' for n in ('basic_pitch_flash_model_loader.sv','basic_pitch_flash_map.svh','basic_pitch_flash_io_guard.sv','basic_pitch_flash_serial_boot.sv')]
    if args.buffer_ddr_clients:overlays += [CLIENT_QUEUES]
    if args.register_pixel_ready:overlays += [PIXEL_SKID]
    if args.sync_delay_write_fifo:overlays += [SYNC_FIFO]
    if args.pipeline_ddr_arbiter:overlays += [PIPELINE]
    if args.register_response_credit:overlays += ['rtl/music/basic_pitch_ddr_read_credit.sv']
    if args.retime_cache_read:overlays += ['rtl/music/basic_pitch_weight_cache.sv']
    if args.defer_ddr_startup:overlays += ['rtl/music/basic_pitch_ddr_boot_gate.sv','rtl/music/basic_pitch_startup_panic.sv']
    if args.flow!='pnr':
        assert sha(BASE/'Prj1/impl/pnr/Prj1.fs')==BASE_FS_SHA,'deployed bitstream drift'
        originals=json.loads((BASE/'workstation_inputs.json').read_text())
        assert all(sha(BASE/'Prj1'/p)==h for p,h in originals.items()),'deployed source drift'
        assert not output.exists(),'refusing to overwrite candidate'
        shutil.copytree(BASE/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','*.user','__pycache__'))
        for rel in overlays:shutil.copy2(ROOT/rel,stage/rel)
        if args.register_arbiter_tag_flags:
            arbiter=stage/PIPELINE;arbiter.write_text(register_arbiter_tag_flags(arbiter.read_text()))
        if args.retime_cache_read:
            pipeline=stage/'rtl/music/basic_pitch_pcm_pipeline.sv';text=pipeline.read_text()
            original='            dwell_count[dwell_bucket(state)] <= dwell_count[dwell_bucket(state)] + 1\'b1;'
            assert text.count(original)==1
            text=text.replace(original,'            for (integer i=0;i<8;i=i+1)\n                if (dwell_bucket(state)==i) dwell_count[i] <= dwell_count[i] + 1\'b1;')
            if args.narrow_feature_read_slot:text=narrow_feature_read_slot(text)
            pipeline.write_text(text)
        top=stage/'src/push2/gw138k_push_workstation_top.v';s=top.read_text()
        if args.defer_ddr_startup:
            anchor='    ddr3_platform u_memory (';assert s.count(anchor)==1
            s=s.replace(anchor,'''    wire memory_boot_reset_n;
    basic_pitch_ddr_boot_gate u_memory_boot_gate (
        .clk_i(clk_50m),.rst_ni(reset_n),.aux_ready_i(audio_locked && memory_flags[7]),
        .memory_rst_no(memory_boot_reset_n));
'''+anchor)
            anchor='.clk_50m(clk_50m),.rst_n(reset_n),.ui_clk(memory_clk)';assert s.count(anchor)==1
            s=s.replace(anchor,'.clk_50m(clk_50m),.rst_n(memory_boot_reset_n),.ui_clk(memory_clk)')
        assert s.count('    input wire sd_miso,')==1
        s=s.replace('    input wire sd_miso,','''    input wire flash_miso,
    output wire flash_clk,flash_cs_n,flash_mosi,flash_wp_n,flash_hold_n,
    input wire sd_miso,''')
        assert s.count('    basic_pitch_workstation_link u_music (')==1
        guard = '''    wire flash_spi_cs_n,flash_spi_clk,flash_spi_mosi;
    basic_pitch_flash_io_guard u_model_flash_io (
        .spi_cs_n_i(flash_spi_cs_n),.spi_clk_i(flash_spi_clk),.spi_mosi_i(flash_spi_mosi),
        .flash_cs_n_o(flash_cs_n),.flash_clk_o(flash_clk),.flash_mosi_o(flash_mosi),
        .flash_wp_n_o(flash_wp_n),.flash_hold_n_o(flash_hold_n),.owned_o());
'''
        anchor='.memory_calibrated(memory_calibrated),.model_serial(pc_uart_rx_i),'
        assert s.count(anchor)==1
        if args.transport=='direct':
            s=s.replace('    basic_pitch_workstation_link u_music (',guard+'    basic_pitch_workstation_link #(.USE_FLASH_WEIGHTS(1\'b1)) u_music (')
            s=s.replace(anchor,anchor+'\n        .flash_miso(flash_miso),.flash_cs_n(flash_spi_cs_n),.flash_clk(flash_spi_clk),.flash_mosi(flash_spi_mosi),')
        else:
            # Keep the proven parser, reset fanout, CNN and native DDR client.
            # CPU UI marker is published only after DDR/audio/UI startup tests.
            bridge = '''    wire model_boot_serial;
    wire [1:0] model_boot_source,model_boot_error;
    wire [3:0] model_boot_state;
    wire model_system_ready=signature==32'h43505531 && ram_result==32'h50415353 &&
        ui_report[31:16]==16'h5549 && memory_calibrated && memory_reset_n;
    basic_pitch_flash_serial_boot u_model_flash_source (
        .clk_i(clk_50m),.rst_ni(reset_n),.boot_ready_i(model_system_ready),
        .serial_i(pc_uart_rx_i),.flash_miso_i(flash_miso),.model_status_i(music_model_status),
        .serial_o(model_boot_serial),.flash_cs_n_o(flash_spi_cs_n),
        .flash_clk_o(flash_spi_clk),.flash_mosi_o(flash_spi_mosi),
        .source_o(model_boot_source),.error_stage_o(model_boot_error),.state_o(model_boot_state));
'''
            if args.defer_ddr_startup:
                original_audio_input="(music_model_status==4'd14 || tf_scope_control_audio[12]) ? pc_uart_rx_i : 1'b1"
                original='.pc_uart_rx_i('+original_audio_input+')';assert s.count(original)==1
                s=s.replace(original,'.pc_uart_rx_i(startup_audio_serial)')
                bridge=bridge.replace('    basic_pitch_flash_serial_boot u_model_flash_source (',
                    '    wire startup_audio_serial,startup_panic_done;\n'
                    '    basic_pitch_startup_panic u_startup_panic (\n'
                    '        .clk_i(clk_50m),.rst_ni(reset_n),.system_ready_i(model_system_ready),\n'
                    '        .serial_i('+original_audio_input+'),.serial_o(startup_audio_serial),.done_o(startup_panic_done));\n'
                    '    basic_pitch_flash_serial_boot u_model_flash_source (')
                bridge=bridge.replace('.boot_ready_i(model_system_ready)', '.boot_ready_i(model_system_ready && startup_panic_done)')
            s=s.replace('    basic_pitch_workstation_link u_music (',guard+bridge+'    basic_pitch_workstation_link u_music (')
            s=s.replace(anchor,'.memory_calibrated(memory_calibrated),.model_serial(model_boot_serial),\n        .model_boot_source(model_boot_source),.model_boot_error(model_boot_error),')
            link=stage/'rtl/music/basic_pitch_workstation_link.sv';text=link.read_text()
            text=text.replace('    input wire model_serial,','    input wire model_serial,\n    input wire [1:0] model_boot_source,model_boot_error,')
            old="{score_count,score_first,score_last,2'd0,model_error_stage,"
            assert text.count(old)==1
            text=text.replace(old,"{score_count,score_first,score_last,model_boot_source,\n                             (model_status==0 && model_boot_source==2 ? model_boot_error : model_error_stage),")
            if args.register_response_credit:text=register_response_credit(text)
            if args.retime_model_memory_ready:text=retime_model_memory_ready(text)
            link.write_text(text)
        if args.retime_start_delay:s=retime_start_delay(s)
        if args.retime_tf_write_buffer:
            tf=stage/TF_DMA;tf.write_text(retime_tf_capture_limit(retime_tf_write_buffer(tf.read_text())) if args.retime_tf_capture_limit else retime_tf_write_buffer(tf.read_text()))
        if args.power_two_tf_ring:
            tf=stage/TF_DMA;tf.write_text(power_two_tf_ring(tf.read_text()))
        if args.parallel_delay_pointer:
            dma=stage/DELAY_DMA;dma.write_text(parallel_delay_rptr(dma.read_text()))
        if args.sync_delay_write_fifo:
            delay=stage/DELAY;delay.write_text(patch_delay_fifo(delay.read_text(),args.sync_delay_read_fifo))
        if args.pipeline_ddr_arbiter:
            s=patch_top(s)
            display=stage/HDMI;display.write_text(retime_display_enable(patch_hdmi(display.read_text(),args.buffer_ddr_clients)) if args.retime_display_enable else patch_hdmi(display.read_text(),args.buffer_ddr_clients))
        if args.register_pixel_ready:
            display=stage/HDMI;display.write_text(patch_hdmi_pixel_skid(display.read_text()))
        if args.retime_bist_expected_pattern:
            bist=stage/BIST;bist.write_text(retime_bist_expected_pattern(bist.read_text()))
        if args.pipeline_bist_compare:
            bist=stage/BIST;bist.write_text(pipeline_bist_compare(bist.read_text()))
        if args.parallel_tf_byte_counters:
            tfdma=stage/TF_DMA;tfdma.write_text(parallel_tf_byte_counters(tfdma.read_text()))
        if args.retime_tf_read_total:
            tfdma=stage/TF_DMA;tfdma.write_text(retime_tf_read_total(tfdma.read_text()))
        if args.fast_tf_read_availability:
            tfdma=stage/TF_DMA;tfdma.write_text(fast_tf_read_availability(tfdma.read_text()))
        if args.mask_tf_write_epoch:
            tfdma=stage/TF_DMA;tfdma.write_text(mask_tf_write_epoch(tfdma.read_text()))
        if args.registered_tf_response:
            tfdma=stage/TF_DMA;tfdma.write_text(registered_tf_read_response(tfdma.read_text()))
        if args.pipeline_tf_read_return:
            tfdma=stage/TF_DMA;tfdma.write_text(pipeline_tf_read_return(tfdma.read_text()))
        if args.retime_tf_buffer_enable:
            tfbuffer=stage/TF_BUFFER;tfbuffer.write_text(retime_tf_buffer_enable(tfbuffer.read_text()))
        if args.retime_tmds_statistics:
            tmds=stage/TMDS;text=retime_tmds_statistics(tmds.read_text())
            tmds.write_text(lut_tmds_popcount(text) if args.lut_tmds_popcount else text)
        if args.predecode_dashboard:
            dash=stage/DASHBOARD;dashboard=predecode_dashboard(dash.read_text())
            if args.predecode_text_coordinates:dashboard=predecode_dashboard_text_coordinates(dashboard)
            if args.parallel_dashboard_cards:dashboard=parallel_dashboard_cards(dashboard)
            if args.predecode_background_coordinates:dashboard=predecode_dashboard_background(dashboard,args.complete_background_coordinates)
            if args.predecode_wave_heights:dashboard=predecode_dashboard_wave_heights(dashboard)
            if args.predecode_dynamic_background_ink:dashboard=predecode_dashboard_dynamic_ink(dashboard)
            if args.shallow_card_select:dashboard=shallow_dashboard_card_select(dashboard)
            dash.write_text(dashboard)
            renderer=stage/RENDERER;renderer_text=align_renderer_predecode(renderer.read_text())
            if args.parallel_renderer_spectrum_address:renderer_text=parallel_renderer_spectrum_address(renderer_text)
            if args.quiet_shared_analysis_column:renderer_text=quiet_shared_analysis_column(renderer_text)
            renderer.write_text(renderer_text)
        top.write_text(s)
        if args.retime_video_telemetry:
            diagnostics=stage/'src/video/video_runtime_diagnostics.v'
            diagnostics.write_text(retime_video_frame_telemetry(diagnostics.read_text()))
        tree=ET.parse(stage/'Prj1.gprj');fl=tree.find('FileList');present={f.attrib['path'] for f in fl}
        for rel in overlays:
            if rel not in present and not rel.endswith('.svh'):
                ET.SubElement(fl,'File',path=rel,type='file.cst' if rel.endswith('.cst') else 'file.verilog',enable='1')
        tree.write(stage/'Prj1.gprj',encoding='UTF-8',xml_declaration=True)
        # Gowin supports one active CST; a second CST replaces the first.
        cst_files=[f.attrib['path'] for f in fl if f.attrib['type']=='file.cst' and f.attrib.get('enable')=='1']
        assert cst_files==['constraints/tang_mega_138k.cst'],'baseline must have one complete pin CST'
        cst=stage/cst_files[0];cst.write_text(cst.read_text()+'\n'+CST)
        if args.locate_reference_pll_helper:
            cst.write_text(cst.read_text()+"""
// Physical-only locality after AF routed SDF showed5.9ns helper-toPLL route.
// SUG935 primitive GROUP+GRP_LOC, nonexclusive; official helper unchanged.
GROUP cnn_reference_pll_helper = { "u_video/u_clock/g_hardware.u_pll/u_reference/u_pll_init/*" };
GRP_LOC cnn_reference_pll_helper R[100:108]C[24:44];
""")
        sdc=stage/'constraints/tang_mega_138k.sdc';sdc.write_text(sdc.read_text()+(SDC if args.transport=='direct' else SDC.replace('u_music/model_memory_meta*/D','u_model_flash_source/ready_meta*/D')))
        if args.register_response_credit or args.pipeline_ddr_arbiter:
            with sdc.open('a') as f:f.write('\n# Audit real same-clock DDR UI setup/hold, independently of Fmax summary.\nreport_timing -setup -from_clock [get_clocks {ddr_ui100}] -to_clock [get_clocks {ddr_ui100}] -max_paths 100\nreport_timing -hold -from_clock [get_clocks {ddr_ui100}] -to_clock [get_clocks {ddr_ui100}] -max_paths 100\n')
        if args.tighten_feature_read_route:
            with sdc.open('a') as f:f.write('''
# Physical budget on exact observed clk50 conv-kh to feature BSRAM address.
# Stricter than original20ns, no false/multicycle/clock/algorithm change.
set_max_delay 19.000 -from [get_regs {u_music/u_basic_pitch/u_reduce/kh* u_music/u_basic_pitch/u_note_out/kh* u_music/u_basic_pitch/u_onset_out/kh*}] -to [get_pins {u_music/u_basic_pitch/g_ddr_features.u_feature_ddr/cache_cache*/ADB*}]
''')
        if args.tighten_cache_reset:
            sdc.write_text(sdc.read_text()+'''
# Stricter budget for the existing synchronous cache RESET cone;
# original 20-ns clocks, hold checks and all pre-existing paths retained.
set_max_delay 18.000 -to [get_pins {u_music/u_basic_pitch/g_ddr_weights.u_weight_cache/cache_cache*/RESET}]
''')
        if args.defer_ddr_startup:
            with sdc.open('a') as f:f.write('\n# Only the auxiliary-lock first synchronizer entry is asynchronous.\nset_false_path -to [get_pins {u_memory_boot_gate/ready_meta*/D}]\nset_false_path -to [get_pins {u_startup_panic/ready_meta*/D}]\n')
        if args.tighten_video_control:
            with sdc.open('a') as f:f.write('''
# Tighten known pixel-domain control routes; no display RTL/clock/hold change.
set_max_delay 6.000 -from [get_pins {u_video/pixel_reset_pipe_2_s0/Q}] -to [get_regs {u_video/u_dvi/*/input_ones*}]
set_max_delay 6.000 -from [get_regs {u_video/u_timing/vertical* u_video/u_timing/horizontal*}] -to [get_regs {u_video/u_diagnostics/frame_advance_q* u_video/u_diagnostics/pixel_frame_count* u_video/u_scanout/under_count*}]
''')
        if args.tighten_remaining_ddr_video:
            with sdc.open('a') as f:f.write("""
# Physical optimization of observed legacy paths; no false/multicycle waiver.
# These bounds are STRICTER than the original DDR UI10ns clock.
set_max_delay 8.000 -to [get_pins {u_video/u_renderer/u_*/a_text_line*/D u_video/u_renderer/u_*/a_font_row*/D u_video/u_renderer/u_*/a_text_index*/D u_video/u_renderer/g_analysis.u_analysis/column_registered*/D u_video/u_data_reader/spectrum_address_q*/D u_tf_audio/u_path/u_dma/read_ring_offset*/D u_delay_ddr_dma/rptr*/D}]
# Include the full helper clock/cell/net distribution in the independent SDF
# PLL10ns audit; constrain the endpoint budget more tightly for physical PNR.
set_max_delay 6.000 -to [get_pins {u_video/u_clock/g_hardware.u_pll/u_reference/PLL_inst/ICPSEL* u_video/u_clock/g_hardware.u_pll/u_reference/PLL_inst/LPFRES* u_video/u_clock/g_hardware.u_pll/u_reference/PLL_inst/RESET u_video/u_clock/g_hardware.u_pll/u_tmds/PLL_inst/ICPSEL* u_video/u_clock/g_hardware.u_pll/u_tmds/PLL_inst/LPFRES* u_video/u_clock/g_hardware.u_pll/u_tmds/PLL_inst/RESET}]
""")
        if args.tighten_pll_setting_route:
            with sdc.open('a') as f:f.write("""
# Independent VO/SDF checks include IBUF+clock route+C2Q before this net.
# Exact RomDreg Q -> analog control routing must fit remaining4.5ns.
set_max_delay 4.500 -from [get_pins {u_video/u_clock/g_hardware.u_pll/*/u_pll_init/RomDreg*/Q}] -to [get_pins {u_video/u_clock/g_hardware.u_pll/*/PLL_inst/ICPSEL* u_video/u_clock/g_hardware.u_pll/*/PLL_inst/LPFRES*}]
""")
        tcl=stage/'scripts/build.tcl';s=tcl.read_text()
        assert 'set_option -use_mspi_as_gpio 1' in s and 'set_option -use_cpu_as_gpio 1' in s
        s=re.sub(r'(?m)^set_option -(?:user_code|inc_pnr|inc_place).*\n','',s)
        s=re.sub(r'(?m)^set_option -route_option .*$',f'set_option -route_option {args.route_option}',s)
        s=re.sub(r'(?m)^set_option -place_option .*$',f'set_option -place_option {args.place_option}',s)
        if args.replicate_resources:s=s.replace('set flow all','set_option -replicate_resources 1\nset flow all')
        if args.user_code:s=s.replace('set flow all','set_option -user_code '+args.user_code.upper()+'\nset flow all')
        if args.incremental_baseline:
            s=s.replace('set flow all',f'set_option -inc_{args.incremental_mode} [file join $root build full85_reference.{reference_suffix}]\nset flow all')
        tcl.write_text(s)
        inputs={str(p.relative_to(stage)):sha(p) for p in stage.rglob('*') if p.is_file()}
        changed=sorted(p for p,h in inputs.items() if originals.get(p)!=h)
        allowed=set(overlays+([BIST] if args.retime_bist_expected_pattern else [])+(['rtl/music/basic_pitch_workstation_link.sv'] if args.transport=='serial' else [])+(['rtl/music/basic_pitch_pcm_pipeline.sv'] if args.retime_cache_read else [])+(['src/video/video_runtime_diagnostics.v'] if args.retime_video_telemetry else [])+([DASHBOARD,RENDERER] if args.predecode_dashboard else [])+([TF_BUFFER] if args.retime_tf_buffer_enable else [])+([TMDS] if args.retime_tmds_statistics else [])+([TF_DMA] if args.retime_tf_write_buffer else [])+([HDMI] if args.pipeline_ddr_arbiter else [])+([DELAY] if args.sync_delay_write_fifo else [])+([DELAY_DMA] if args.parallel_delay_pointer else [])+['src/push2/gw138k_push_workstation_top.v','Prj1.gprj','scripts/build.tcl',
                             'constraints/tang_mega_138k.cst','constraints/tang_mega_138k.sdc'])
        assert set(changed)==allowed,(changed,allowed)
        write_json(output/'workstation_inputs.json',inputs)
        write_json(output/'build_metadata.json',dict(baseline=str(BASE.relative_to(ROOT)),baseline_fs_sha256=BASE_FS_SHA,
            user_code=('0x'+args.user_code.upper()) if args.user_code else None,changed_from_base=changed,
            git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            hardware_tested=False,flash_model_base='0x00600000',full_workstation=True,transport=args.transport,reference_pll_helper_region="R[100:108]C[24:44]" if args.locate_reference_pll_helper else None,predecoded_dashboard=args.predecode_dashboard,predecoded_text_coordinates=args.predecode_text_coordinates,parallel_dashboard_cards=args.parallel_dashboard_cards,predecoded_background_coordinates=args.predecode_background_coordinates,parallel_delay_pointer=args.parallel_delay_pointer,power_two_tf_ring=args.power_two_tf_ring,raster_enabled_latency_added=1 if args.predecode_dashboard else 0,PLL_settings_route_max_delay_ns=4.5 if args.tighten_pll_setting_route else None,remaining_ddr_video_physical_budgets=args.tighten_remaining_ddr_video,retimed_tf_buffer_enable=args.retime_tf_buffer_enable,retimed_tf_capture_limit=args.retime_tf_capture_limit,retimed_tmds_statistics=args.retime_tmds_statistics,lut_tmds_popcount=args.lut_tmds_popcount,retimed_display_enable=args.retime_display_enable,synchronous_delay_read_fifo=args.sync_delay_read_fifo,buffered_ddr_clients=args.buffer_ddr_clients,retimed_tf_write_buffer=args.retime_tf_write_buffer,synchronous_delay_write_fifo=args.sync_delay_write_fifo,physical_bsram_limit=268 if args.sync_delay_read_fifo else (264 if args.sync_delay_write_fifo else 260),retimed_bist_expected_pattern=args.retime_bist_expected_pattern,pipelined_bist_compare=args.pipeline_bist_compare,bist_extra_startup_ms=5.24288 if args.pipeline_bist_compare else 0,predecoded_dynamic_background_ink=args.predecode_dynamic_background_ink,parallel_tf_byte_counters=args.parallel_tf_byte_counters,retimed_tf_read_total=args.retime_tf_read_total,fast_tf_read_availability=args.fast_tf_read_availability,masked_tf_write_epoch=args.mask_tf_write_epoch,registered_tf_response=args.registered_tf_response,pipelined_tf_read_return=args.pipeline_tf_read_return,tf_read_return_cycles_added=1 if args.pipeline_tf_read_return else 0,parallel_renderer_spectrum_address=args.parallel_renderer_spectrum_address,quiet_shared_analysis_column=args.quiet_shared_analysis_column,shallow_card_select=args.shallow_card_select,complete_background_coordinates=args.complete_background_coordinates,registered_pixel_ready=args.register_pixel_ready,pipelined_ddr_arbiter=args.pipeline_ddr_arbiter,registered_arbiter_tag_flags=args.register_arbiter_tag_flags,registered_response_credit=args.register_response_credit,replicate_resources=args.replicate_resources,retimed_cache_read=args.retime_cache_read,retimed_start_delay=args.retime_start_delay,retimed_model_memory_ready=args.retime_model_memory_ready,predecoded_wave_heights=args.predecode_wave_heights,narrowed_feature_read_slot=args.narrow_feature_read_slot,feature_read_route_max_delay_ns=19.0 if args.tighten_feature_read_route else None,video_diagnostic_pixel_latency_added=1 if args.retime_video_telemetry else 0,ddr_initial_aux_settle_ms=100 if args.defer_ddr_startup else None,startup_panic_aligns_delay_history=args.defer_ddr_startup,
            route_option=args.route_option,place_option=args.place_option,video_control_max_delay_ns=6.0 if args.tighten_video_control else None,cache_reset_max_delay_ns=18.0 if args.tighten_cache_reset else None))
        image,manifest=build_image(load_words(stage/'rtl/music/weights/cnn_ddr_blob.mem'))
        assert manifest['word_count']==52239 and manifest['payload_crc32']=='AF01A61B'
        (output/'cnn_model.bin').write_bytes(image);(output/'cnn_model.data.fs').write_text(gowin_data_fs(image));write_json(output/'cnn_model.json',manifest)
    else:
        inputs=json.loads((output/'workstation_inputs.json').read_text())
        assert json.loads((output/'build_metadata.json').read_text())['user_code'],'PNR release needs assigned code'
    if args.synthesis_from:
        previous=args.synthesis_from.resolve();old_inputs=json.loads((previous/'workstation_inputs.json').read_text())
        assert all(sha(previous/'Prj1'/p)==h for p,h in old_inputs.items()),'old synthesis input drift'
        exceptions={'Prj1.gprj','constraints/cnn_flash.cst','constraints/tang_mega_138k.cst'}
        assert {p:h for p,h in inputs.items() if p not in exceptions}=={p:h for p,h in old_inputs.items() if p not in exceptions},'synthesis reuse requires exact RTL/IP/memory/options'
        oldsyn=previous/'Prj1/impl/gwsynthesis'
        assert 'GowinSynthesis finish' in (previous/'gowin_all.log').read_text() and (oldsyn/'Prj1.vg').exists()
        assert not (previous/'Prj1/impl/pnr/Prj1.fs').exists(),'CST repair reuse is for unreleased failure only'
        shutil.copytree(oldsyn,stage/'impl/gwsynthesis')
        m=json.loads((output/'build_metadata.json').read_text());m['synthesis_from']=str(previous.relative_to(ROOT));m['cst_repair']='append Flash pins to the single original complete CST';write_json(output/'build_metadata.json',m)
    reference=None;reference_sha=None;route_reference=None;route_reference_sha=None
    if args.incremental_baseline:
        old_result=json.loads((BASE/'tool_result.json').read_text())
        assert old_result['exit_code']==0 and old_result['inputs_unchanged'],'incremental baseline incomplete'
        old_p=BASE/'Prj1/impl/pnr/Prj1.p';assert old_p.is_file(),'missing verified placement .p reference'
        reference=stage/'build/full85_reference.p';reference.parent.mkdir(exist_ok=True)
        shutil.copy2(old_p,reference);reference_sha=sha(old_p)
        assert sha(reference)==reference_sha,'reference copy drift'
        m=json.loads((output/'build_metadata.json').read_text())
        m['incremental_reference']=dict(build=str(BASE.relative_to(ROOT)),placement_p_sha256=reference_sha,
            file='build/full85_reference.p',entry_file='build/full85_reference.'+reference_suffix,command='inc_'+args.incremental_mode,fresh_synthesis=True,fresh_routing=args.incremental_mode=='place')
        if args.incremental_mode=='pnr':
            old_pr=BASE/'Prj1/impl/pnr/Prj1.pr';route_reference=stage/'build/full85_reference.pr';route_reference_sha=sha(old_pr)
            shutil.copy2(old_pr,route_reference);assert sha(route_reference)==route_reference_sha
            m['incremental_reference'].update(route_file='build/full85_reference.pr',routed_pr_sha256=route_reference_sha)
        write_json(output/'build_metadata.json',m)
    elif args.flow=='pnr':
        recorded_reference=json.loads((output/'build_metadata.json').read_text()).get('incremental_reference')
        if recorded_reference:
            assert recorded_reference.get('command') in ('inc_place','inc_pnr') and 'placement_p_sha256' in recorded_reference,'unpaired legacy reference is not eligible; prepare a fresh hash-checked reference pair'
            reference=stage/recorded_reference['file'];reference_sha=recorded_reference['placement_p_sha256']
            assert sha(reference)==reference_sha,'incremental reference drift before reroute'
            if recorded_reference['command']=='inc_pnr':
                route_reference=stage/recorded_reference['route_file'];route_reference_sha=recorded_reference['routed_pr_sha256']
                assert sha(route_reference)==route_reference_sha,'incremental routed partner drift before reroute'
    if json.loads((output/'build_metadata.json').read_text()).get('transport')=='serial':audit_serial_compatibility(output)
    frozen_meta=json.loads((output/'build_metadata.json').read_text())
    for rel,(staged,h) in FROZEN.items():
        normalized=(frozen_meta.get('pipelined_ddr_arbiter') and staged==HDMI and
            (stage/staged).read_text()==expected_hdmi(frozen_meta)) or (
            frozen_meta.get('synchronous_delay_write_fifo') and staged==DELAY and
            (stage/staged).read_text()==patch_delay_fifo((BASE/'Prj1'/staged).read_text(),frozen_meta.get('synchronous_delay_read_fifo',False)))
        normalized=normalized or (frozen_meta.get('parallel_delay_pointer') and staged==DELAY_DMA and
            (stage/staged).read_text()==parallel_delay_rptr((BASE/'Prj1'/staged).read_text()))
        assert sha(ROOT/rel)==h and (sha(stage/staged)==h or normalized),rel
    assert all(sha(stage/p)==h for p,h in inputs.items()),'candidate input drift'
    print(output,flush=True)
    if args.flow=='prepare':return
    actual_flow='pnr' if args.synthesis_from else args.flow
    with (output/('gowin_'+args.flow+'.log')).open('w') as log:
        run=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,
                           env=dict(os.environ,PRJ1_FLOW=actual_flow),stdout=log,stderr=subprocess.STDOUT)
    changed=[p for p,h in inputs.items() if sha(stage/p)!=h]
    if reference and sha(reference)!=reference_sha:changed.append(str(reference.relative_to(stage)))
    if route_reference and sha(route_reference)!=route_reference_sha:changed.append(str(route_reference.relative_to(stage)))
    record=dict(exit_code=run.returncode,flow=args.flow,inputs_unchanged=not changed,changed=changed,hardware_tested=False)
    write_json(output/'tool_result.json',record)
    if run.returncode or changed:raise SystemExit('build/input check failed: '+str(output))
    report=audit(output,'full' if args.flow in ('all','pnr') else 'synthesis_only')
    print('SYN BSRAM',report['bsram'],'PNR BSRAM',report.get('pnr_bsram'),flush=True)
    if args.flow in ('all','pnr'):
        physical_limit=json.loads((output/'build_metadata.json').read_text()).get('physical_bsram_limit',260)
        assert physical_limit in (260,264,268) and report['pnr_available'] and report['pnr_bsram']<=physical_limit,'explicit BSRAM budget exceeded'
        fs=stage/'impl/pnr/Prj1.fs';binary=stage/'impl/pnr/Prj1.bin'
        code=json.loads((output/'build_metadata.json').read_text())['user_code']
        assert re.search(r'//UserCode: (0x[0-9A-Fa-f]{8})',fs.read_text()[:1000])[1].lower()==code.lower()
        packed,manifest=pack_flash(binary.read_bytes(),(output/'cnn_model.bin').read_bytes())
        (output/'workstation_with_cnn.bin').write_bytes(packed)
        manifest.update(bitstream_fs_sha256=sha(fs),bitstream_bin_sha256=sha(binary),user_code=code,
                        boot_image_sha256=sha(output/'workstation_with_cnn.bin'))
        write_json(output/'flash_bundle.json',manifest)
        print('FLASH BUNDLE',output/'workstation_with_cnn.bin',flush=True)
if __name__=='__main__':main()
