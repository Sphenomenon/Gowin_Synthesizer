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

def audit_serial_compatibility(output):
    stage=output/'Prj1'
    paths=['rtl/music/basic_pitch_pcm_pipeline.sv','rtl/music/basic_pitch_uart_model_loader.sv',
        'rtl/music/basic_pitch_ddr16_port.sv','rtl/music/basic_pitch_ddr_command_buffer.sv',
        'rtl/music/music_async_fifo.sv','src/video/hdmi_display.v','firmware/boot.mem',
        'vendor/gowin_ddr3/ddr3_memory_interface.v']
    paths += [str(p.relative_to(BASE/'Prj1')) for p in (BASE/'Prj1').rglob('gw138k_ddr_arbiter.sv')]
    evidence={p:dict(unchanged=sha(BASE/'Prj1'/p)==sha(stage/p),sha256=sha(stage/p)) for p in paths}
    if json.loads((output/'build_metadata.json').read_text()).get('retimed_cache_read'):
        pipeline='rtl/music/basic_pitch_pcm_pipeline.sv'
        text=(stage/pipeline).read_text().replace(
            '            for (integer i=0;i<8;i=i+1)\n                if (dwell_bucket(state)==i) dwell_count[i] <= dwell_count[i] + 1\'b1;',
            '            dwell_count[dwell_bucket(state)] <= dwell_count[dwell_bucket(state)] + 1\'b1;')
        assert text==(BASE/'Prj1'/pipeline).read_text(),'CNN changed beyond dwell telemetry unrolling'
        evidence[pipeline]['unchanged']=True;evidence[pipeline]['normalization']='Only equivalent parallel dwell-counter update; CNN datapath exact'
        assert sha(stage/'rtl/music/basic_pitch_weight_cache.sv')==sha(ROOT/'rtl/music/basic_pitch_weight_cache.sv'),'cache retiming source drift'
    assert all(v['unchanged'] for v in evidence.values()),'serial transport changed proven CNN/DDR/firmware'
    original=(BASE/'Prj1/rtl/music/basic_pitch_workstation_link.sv').read_text()
    link=(stage/'rtl/music/basic_pitch_workstation_link.sv').read_text()
    link=link.replace('    input wire [1:0] model_boot_source,model_boot_error,\n','')
    link=link.replace("{score_count,score_first,score_last,model_boot_source,\n                             (model_status==0 && model_boot_source==2 ? model_boot_error : model_error_stage),",
                      "{score_count,score_first,score_last,2'd0,model_error_stage,")
    assert link==original,'serial native-memory link changed beyond diagnostics'
    write_json(output/'serial_compatibility_source_audit.json',dict(passed=True,
        baseline=str(BASE.relative_to(ROOT)),candidate=str(output),unchanged_sources=evidence,
        link_change_only='Two diagnostic inputs and B138 source/error fields; native memory and CDC source unchanged'))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--retime-cache-read',action='store_true',help='equivalent one-cycle cache range mask plus parallel dwell counters; no CNN arithmetic change')
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
    if args.retime_cache_read:overlays += ['rtl/music/basic_pitch_weight_cache.sv']
    if args.defer_ddr_startup:overlays += ['rtl/music/basic_pitch_ddr_boot_gate.sv','rtl/music/basic_pitch_startup_panic.sv']
    if args.flow!='pnr':
        assert sha(BASE/'Prj1/impl/pnr/Prj1.fs')==BASE_FS_SHA,'deployed bitstream drift'
        originals=json.loads((BASE/'workstation_inputs.json').read_text())
        assert all(sha(BASE/'Prj1'/p)==h for p,h in originals.items()),'deployed source drift'
        assert not output.exists(),'refusing to overwrite candidate'
        shutil.copytree(BASE/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','*.user','__pycache__'))
        for rel in overlays:shutil.copy2(ROOT/rel,stage/rel)
        if args.retime_cache_read:
            pipeline=stage/'rtl/music/basic_pitch_pcm_pipeline.sv';text=pipeline.read_text()
            original='            dwell_count[dwell_bucket(state)] <= dwell_count[dwell_bucket(state)] + 1\'b1;'
            assert text.count(original)==1
            text=text.replace(original,'            for (integer i=0;i<8;i=i+1)\n                if (dwell_bucket(state)==i) dwell_count[i] <= dwell_count[i] + 1\'b1;')
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
            link.write_text(text)
        top.write_text(s)
        tree=ET.parse(stage/'Prj1.gprj');fl=tree.find('FileList');present={f.attrib['path'] for f in fl}
        for rel in overlays:
            if rel not in present and not rel.endswith('.svh'):
                ET.SubElement(fl,'File',path=rel,type='file.cst' if rel.endswith('.cst') else 'file.verilog',enable='1')
        tree.write(stage/'Prj1.gprj',encoding='UTF-8',xml_declaration=True)
        # Gowin supports one active CST; a second CST replaces the first.
        cst_files=[f.attrib['path'] for f in fl if f.attrib['type']=='file.cst' and f.attrib.get('enable')=='1']
        assert cst_files==['constraints/tang_mega_138k.cst'],'baseline must have one complete pin CST'
        cst=stage/cst_files[0];cst.write_text(cst.read_text()+'\n'+CST)
        sdc=stage/'constraints/tang_mega_138k.sdc';sdc.write_text(sdc.read_text()+(SDC if args.transport=='direct' else SDC.replace('u_music/model_memory_meta*/D','u_model_flash_source/ready_meta*/D')))
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
set_max_delay 6.000 -from [get_regs {u_video/u_timing/vertical*}] -to [get_regs {u_video/u_diagnostics/pixel_frame_count*}]
''')
        tcl=stage/'scripts/build.tcl';s=tcl.read_text()
        assert 'set_option -use_mspi_as_gpio 1' in s and 'set_option -use_cpu_as_gpio 1' in s
        s=re.sub(r'(?m)^set_option -(?:user_code|inc_pnr|inc_place).*\n','',s)
        s=re.sub(r'(?m)^set_option -route_option .*$',f'set_option -route_option {args.route_option}',s)
        s=re.sub(r'(?m)^set_option -place_option .*$',f'set_option -place_option {args.place_option}',s)
        if args.user_code:s=s.replace('set flow all','set_option -user_code '+args.user_code.upper()+'\nset flow all')
        if args.incremental_baseline:
            s=s.replace('set flow all',f'set_option -inc_{args.incremental_mode} [file join $root build full85_reference.{reference_suffix}]\nset flow all')
        tcl.write_text(s)
        inputs={str(p.relative_to(stage)):sha(p) for p in stage.rglob('*') if p.is_file()}
        changed=sorted(p for p,h in inputs.items() if originals.get(p)!=h)
        allowed=set(overlays+(['rtl/music/basic_pitch_workstation_link.sv'] if args.transport=='serial' else [])+(['rtl/music/basic_pitch_pcm_pipeline.sv'] if args.retime_cache_read else [])+['src/push2/gw138k_push_workstation_top.v','Prj1.gprj','scripts/build.tcl',
                             'constraints/tang_mega_138k.cst','constraints/tang_mega_138k.sdc'])
        assert set(changed)==allowed,(changed,allowed)
        write_json(output/'workstation_inputs.json',inputs)
        write_json(output/'build_metadata.json',dict(baseline=str(BASE.relative_to(ROOT)),baseline_fs_sha256=BASE_FS_SHA,
            user_code=('0x'+args.user_code.upper()) if args.user_code else None,changed_from_base=changed,
            git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            hardware_tested=False,flash_model_base='0x00600000',full_workstation=True,transport=args.transport,retimed_cache_read=args.retime_cache_read,ddr_initial_aux_settle_ms=100 if args.defer_ddr_startup else None,startup_panic_aligns_delay_history=args.defer_ddr_startup,
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
    for rel,(staged,h) in FROZEN.items():assert sha(ROOT/rel)==sha(stage/staged)==h,rel
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
        assert report['pnr_available'] and report['pnr_bsram']<=260,'Flash boot added BSRAM'
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
