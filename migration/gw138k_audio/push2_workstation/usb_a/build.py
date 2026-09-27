#!/usr/bin/env python3
"""Offline merge of frozen 3BE2 audio workstation and accepted 8FC3 USB-A Host.
No programming, UART, or board discovery operations are performed.
"""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,os,shutil,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
TF_AUDIO=ROOT/'rtl/tf_audio'
WORK=ROOT.parent/'results/workstation_20260911_174045_306332'
USB=ROOT/'vendor/usb_host_fs_8fc3'
WORKSTATION_MANIFEST=ROOT/'vendor/workstation_inputs.json'
DDR_REFERENCE=ROOT/'vendor/ddr3_reference/ddr3_memory_interface.vo'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen_sha(p):
    data=p.read_bytes()
    if b'\0' not in data:data=data.replace(b'\r\n',b'\n')
    return hashlib.sha256(data).hexdigest()
def replace(s,a,b):
    assert s.count(a)==1,('ambiguous source edit',a)
    return s.replace(a,b)
def replace_n(s,a,b,count):
    assert s.count(a)==count,('unexpected source edit count',a,s.count(a),count)
    return s.replace(a,b)
def replace_between(s,start,end,a,b):
    first=s.index(start);last=s.index(end,first) if end else len(s)
    return s[:first]+replace(s[first:last],a,b)+s[last:]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--reuse-synthesis',type=Path)
    ap.add_argument('--no-update-latest',action='store_true',help='Keep the local latest-build pointer unchanged')
    ap.add_argument('--tf-audio-kind',choices=['mp3','wav','flac'],default='wav',
                    help='TF decoder profile to elaborate (default: wav)')
    ap.add_argument('--user-code',help='Optional eight hexadecimal digits identifying a release without changing RTL')
    args=ap.parse_args()
    tf_audio_kind={'mp3':1,'wav':2,'flac':3}[args.tf_audio_kind]
    if args.user_code is not None:
        if len(args.user_code)!=8 or any(c not in '0123456789abcdefABCDEF' for c in args.user_code):
            ap.error('--user-code requires eight hexadecimal digits')
    for base,manifest in [(WORK/'Prj1',WORKSTATION_MANIFEST),(USB,USB/'inputs.json')]:
        hashes=json.loads(manifest.read_text())
        assert all(frozen_sha(base/p)==h for p,h in hashes.items()),'frozen inputs changed: '+str(base)
    out=ROOT/'results'/datetime.now().strftime('build_%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    stage=out/'Prj1'
    shutil.copytree(WORK/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','__pycache__','*.user'))
    ddr_ip=stage/'vendor/gowin_ddr3/ddr3_memory_interface.v'
    ddr_ip.write_bytes(ddr_ip.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
    assert sha(ddr_ip)=='4a6e26d2ccb8d01221103df4cdf71f3517d2700614020e0c414aafec04a495bc'
    if args.user_code is not None:
        tcl=stage/'scripts/build.tcl'
        tcl.write_text(replace(tcl.read_text(),'set flow all',
            'set_option -user_code '+args.user_code.upper()+'\nset flow all'))
    reference=out/'reference';reference.mkdir()
    shutil.copy2(ddr_ip,reference/'ddr3_memory_interface.v')
    shutil.copy2(DDR_REFERENCE,reference/'ddr3_memory_interface.vo')
    # Display-data overlays are kept outside the frozen workstation
    # source tree. The P10 baseline remains hash-checked and untouched.
    display_overlay={
        'src/video/output_audio_analysis.v':'output_audio_analysis.v',
        'src/video/feedback_renderer.v':'feedback_renderer.v',
        'src/video/hdmi_display.v':'hdmi_display.v',
        'src/memory/display_data_writer.v':'display_data_writer.v',
        'src/memory/display_data_reader.v':'display_data_reader.v',
        'src/ae350/gw138k_ddr_arbiter.sv':'gw138k_ddr_arbiter.sv',
        'src/push2/push2_surface_pixels.sv':'push2_surface_pixels.sv',
    }
    for rel,name in display_overlay.items():
        shutil.copy2(ROOT/'rtl/display_data'/name,stage/rel)
    # C-mode voice allocator/storage overlay.  The frozen P10/P13 workstation
    # tree remains hash-checked; this local copy is the only source changed by
    # the 32-voice experiment.
    audio_overlay={
        'legacy/rtl/audio/unified_oscillator_engine.sv': ROOT/'rtl/audio/unified_oscillator_engine.sv',
        'src/ae350/gw138k_event_workstation.sv': ROOT/'rtl/audio/gw138k_event_workstation.sv',
        'src/push2/push2_controls.sv': ROOT/'rtl/audio/push2_controls.sv',
        'src/push2/push2_lights.sv': ROOT/'rtl/push2/push2_lights.sv',
        'src/push2/push2_led_tx.sv': ROOT/'rtl/push2/push2_led_tx.sv',
    }
    for rel,src in audio_overlay.items():
        shutil.copy2(src,stage/rel)
    # Self-contained TF/FAT audio subsystem.  Do not reach back into the
    # separate Mega_138K/Dev working tree: the staged project and Git checkout
    # must contain the exact same RTL, decoder tables and license records.
    storage_dest=stage/'src/storage'
    shutil.copytree(TF_AUDIO/'storage',storage_dest)
    shutil.copy2(ROOT/'rtl/ddr_address_map.vh',stage/'src/memory/ddr_address_map.vh')
    shutil.copy2(ROOT/'rtl/ddr_address_map_guard.v',stage/'src/memory/ddr_address_map_guard.v')
    shutil.copy2(TF_AUDIO/'tf_async_pcm_fifo.v',stage/'src/storage/tf_async_pcm_fifo.v')
    shutil.copy2(TF_AUDIO/'tf_workstation_audio_bridge.v',stage/'src/storage/tf_workstation_audio_bridge.v')
    shutil.copy2(TF_AUDIO/'pt8211_tx.v',stage/'src/audio/tf_rate_pt8211_tx.v')
    # Bind legacy workstation clients to the shared map without changing their
    # protocols or page sizes.
    p=stage/'src/memory/ddr3_bist.v';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'parameter integer BURSTS = 262144, // 8 MiB',
        'parameter integer BURSTS = `PRJ1_DDR_BIST_BEATS, // 8 MiB')
    p.write_text(s)
    p=stage/'src/memory/ddr_frame_writer.v';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'parameter integer FRAME_STRIDE_WORDS=1048576',
        'parameter integer FRAME_STRIDE_WORDS=`PRJ1_DDR_VIDEO_FRAME_APP_WORDS')
    s=replace(s,'req_addr<=29\'d2097152;',
        'req_addr<=`PRJ1_DDR_DISPLAY_DATA_APP_BASE;')
    p.write_text(s)
    p=stage/'src/video/video_ddr_scanout.v';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'parameter integer FRAME_STRIDE_WORDS = 1048576,',
        'parameter integer FRAME_STRIDE_WORDS = `PRJ1_DDR_VIDEO_FRAME_APP_WORDS,')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_view_select.sv';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'?29\'d1048576:29\'d0;',
        '?`PRJ1_DDR_VIDEO_FRAME1_APP_BASE:`PRJ1_DDR_VIDEO_FRAME0_APP_BASE;')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_ui_services.sv';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'front_address[22]?29\'h0500000:29\'h0400000',
        'front_address[22]?`PRJ1_DDR_WORK_PAGE1_APP_BASE:`PRJ1_DDR_WORK_PAGE0_APP_BASE')
    s=replace(s,'staged_address[22]?29\'h0500000:29\'h0400000',
        'staged_address[22]?`PRJ1_DDR_WORK_PAGE1_APP_BASE:`PRJ1_DDR_WORK_PAGE0_APP_BASE')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_ahb_ddr.sv';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'assign req_address=29\'d4194304+{8\'d0,byte_address[22:5],3\'b000};',
        'assign req_address=`PRJ1_DDR_WORK_PAGE0_APP_BASE+{8\'d0,byte_address[22:5],3\'b000};')
    p.write_text(s)
    # P24 preserves every profile's harmonic ratios and applies one fixed row
    # scale while loading the existing gain ROM.  The scale is independent of
    # active voice count, so notes do not pump when polyphony changes.
    level_config=json.loads((ROOT/'rtl/audio/p24_mode_gain_scale.json').read_text())
    level_scale=level_config['scale_q16']
    assert len(level_scale)==3 and all(len(row)==5 for row in level_scale)
    gain_mem=stage/'sim/matlab/output/stage15_unified_modes/stage15_mode_gain_q15.mem'
    gain_words=[int(word,16) for word in gain_mem.read_text().split()]
    assert len(gain_words)==3*5*32
    for mode in range(3):
        for profile in range(5):
            scale=level_scale[mode][profile]
            assert 0<scale<2**18
            base=(mode*5+profile)*32
            for partial in range(32):
                value=(gain_words[base+partial]*scale+32768)//65536
                gain_words[base+partial]=min(value,32767)
    gain_mem.write_text(''.join(f'{value:04X}\n' for value in gain_words))
    # P23 PANIC carries a compact epoch in the previously-zero upper bits of
    # control_pitch.  Pitch remains the unchanged low 22-bit Q20 value.
    p=stage/'src/ae350/gw138k_controlled_adapter.sv';s=p.read_text()
    s=replace(s,'assign control_pitch_o={10\'d0,pitch};',
        'wire [9:0] panic_epoch;\n    assign control_pitch_o={panic_epoch,pitch};')
    s=replace(s,'.held_notes_o(held_notes_o),.applied_events_o(applied_events_o),.pc_overflow_o(pc_overflow),.control_options_o(control_options_o),',
        '.held_notes_o(held_notes_o),.applied_events_o(applied_events_o),.pc_overflow_o(pc_overflow),.control_options_o(control_options_o),.panic_epoch_o(panic_epoch),')
    s=replace(s,'output wire [31:0] applied_events_o,pc_health_o,',
        'output wire [31:0] applied_events_o,pc_health_o,\n    output wire panel_event_valid_o,output wire [6:0] panel_command_o,')
    s=replace(s,'.control_options_o(control_options_o),.panic_epoch_o(panic_epoch),.cpu_event_valid_i(cpu_event_valid_i),',
        '.control_options_o(control_options_o),.panic_epoch_o(panic_epoch),\n        .panel_event_valid_o(panel_event_valid_o),.panel_command_o(panel_command_o),.cpu_event_valid_i(cpu_event_valid_i),')
    p.write_text(s)
    # P27 keeps the Push panel commands inside the accepted event stream.  The
    # workstation emits a one-cycle pulse only after kind 6 reaches dispatch;
    # the existing audio-domain service remains the single score/record owner.
    p=stage/'src/ae350/gw138k_controlled_services.sv';s=p.read_text()
    s=replace(s,'input wire cpu_event_ready,',
        'input wire cpu_event_ready,\n    input wire panel_event_valid,input wire [6:0] panel_command,output wire panel_event_ready,')
    s=replace(s,'logic [8:0] loaded;\n    wire event_address=command_address==12\'h180;',
        '''logic [8:0] loaded;
    assign panel_event_ready=1'b1;
    wire panel_score_toggle=panel_event_valid && panel_command==0;
    wire panel_record_toggle=panel_event_valid && panel_command==1;
    wire event_address=command_address==12'h180;''')
    s=replace(s,'assign score_start=legal_write && command_address==SCORE_START;\n    assign score_stop=legal_write && command_address==SCORE_STOP;',
        '''assign score_start=(legal_write && command_address==SCORE_START) ||
        (panel_score_toggle && !score_running && score_length!=0 && score_length<=loaded);
    assign score_stop=(legal_write && command_address==SCORE_STOP) ||
        (panel_score_toggle && score_running);''')
    s=replace(s,'12\'h180: response_error=command_data[31:18]!=0 || command_data[17:14]>4 ||\n                    (command_data[17:14]==1 && command_data[6:0]==0);',
        '''12'h180: response_error=command_data[31:18]!=0 || command_data[17:14]>6 ||
                    (command_data[17:14]==1 && command_data[6:0]==0) ||
                    (command_data[17:14]==6 && command_data[13:7]>1);''')
    s=replace(s,'if(score_done) done_sticky<=1;\n            if(legal_write) case(command_address)',
        '''if(score_done) done_sticky<=1;
            if(score_start) done_sticky<=0;
            if(panel_record_toggle) record_enable<=~record_enable;
            if(legal_write) case(command_address)''')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_controlled_audio.sv';s=p.read_text()
    s=replace(s,'.cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),',
        '.cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),\n        .panel_event_valid(1\'b0),.panel_command(7\'d0),.panel_event_ready(),')
    p.write_text(s)
    p=stage/'src/usb_host/gw138k_usb_controlled_audio.sv';s=p.read_text()
    s=replace(s,'output wire score_running_o, score_done_o,',
        'output wire score_running_o, score_done_o,record_enabled_o,')
    s=replace(s,'wire record_enable,record_valid,record_ready,score_write,score_start,score_stop;',
        '''wire record_enable,record_valid,record_ready,score_write,score_start,score_stop;
    wire panel_event_valid,panel_event_ready;wire [6:0] panel_command;
    assign record_enabled_o=record_enable;''')
    s=replace(s,'.cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),',
        '.cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),\n        .panel_event_valid(panel_event_valid),.panel_command(panel_command),.panel_event_ready(panel_event_ready),')
    s=replace(s,'.pc_uart_rx_i(pc_uart_rx_i),.held_notes_o(held_notes),.applied_events_o(applied_events),.pc_health_o(pc_health),',
        '.pc_uart_rx_i(pc_uart_rx_i),.held_notes_o(held_notes),.applied_events_o(applied_events),.pc_health_o(pc_health),\n        .panel_event_valid_o(panel_event_valid),.panel_command_o(panel_command),')
    # The effect status enters the always-running 50 MHz display domain.  Its
    # old reset came directly from the audio clock domain and left six
    # synchronous RESET endpoints outside STA.  These registers are only a
    # display mirror, so initialize both stages and let audio-domain reset
    # state propagate through the ordinary two-stage data path.
    s=replace(s,
        '''    (* ASYNC_REG="TRUE" *) reg [2:0] effect_mask_meta, effect_mask_sync;
    (* ASYNC_REG="TRUE" *) reg [5:0] effect_order_meta=6'b10_01_00, effect_order_sync=6'b10_01_00;
    always @(posedge clk_50m) begin
        if(!reset_n) begin effect_mask_meta<=0; effect_mask_sync<=0; end
        else begin effect_mask_meta<=effect_mask_audio; effect_mask_sync<=effect_mask_meta; end''',
        '''    wire [2:0] effect_mask_sample /* synthesis syn_keep=1 */;
    assign effect_mask_sample=effect_mask_audio;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [2:0] effect_mask_meta=0, effect_mask_sync=0;
    (* ASYNC_REG="TRUE" *) reg [5:0] effect_order_meta=6'b10_01_00, effect_order_sync=6'b10_01_00;
    always @(posedge clk_50m) begin
        effect_mask_meta<=effect_mask_sample; effect_mask_sync<=effect_mask_meta;''')
    p.write_text(s)
    # Clear effect state without resetting BSRAM contents.  Resetting each
    # history length/pointer makes old RAM words unreachable until replaced.
    p=stage/'legacy/rtl/audio/stereo_effects.sv';s=p.read_text()
    s=replace_n(s,'input logic clk_i,rst_ni,valid_i,enabled_i,',
        'input logic clk_i,rst_ni,clear_i,valid_i,enabled_i,',3)
    s=replace(s,'input logic clk_i,rst_ni,valid_i,\n    input logic signed [31:0] synth_i,pcm_left_i,pcm_right_i,',
        'input logic clk_i,rst_ni,clear_i,valid_i,\n    input logic signed [31:0] synth_i,pcm_left_i,pcm_right_i,')
    s=replace_n(s,'if(state==1) begin','if(!clear_i && state==1) begin',3)
    s=replace(s,'if(state==4) begin memory_l[pointer]<=feedback_l;memory_r[pointer]<=feedback_r;end',
        'if(!clear_i && state==4) begin memory_l[pointer]<=feedback_l;memory_r[pointer]<=feedback_r;end')
    s=replace(s,'if(state==3) begin memory_l[pointer]<=input_l;memory_r[pointer]<=input_r;end',
        'if(!clear_i && state==3) begin memory_l[pointer]<=input_l;memory_r[pointer]<=input_r;end')
    s=replace(s,'if(state==6) begin comb_a[pointer]<=feedback_a;comb_b[pointer]<=feedback_b;end',
        'if(!clear_i && state==6) begin comb_a[pointer]<=feedback_a;comb_b[pointer]<=feedback_b;end')
    s=replace_n(s,'.clk_i,.rst_ni,.valid_i(','.clk_i,.rst_ni,.clear_i,.valid_i(',3)
    stage_body='''end else begin
      valid_o<=0;clip_o<=0;
      case(state)'''
    stage_clear='''end else begin
      valid_o<=0;clip_o<=0;
      if(clear_i) begin
        pointer<=0;frames<=0;state<=0;gain<=0;valid_o<=0;clip_o<=0;
      end else case(state)'''
    s=replace_between(s,'module serial_delay_effect','module serial_chorus_effect',stage_body,stage_clear)
    s=replace_between(s,'module serial_chorus_effect','module serial_reverb_effect',stage_body,stage_clear)
    reverb_clear=stage_clear.replace('valid_o<=0;clip_o<=0;\n      end else case(state)',
        'valid_o<=0;clip_o<=0;damping_a<=0;damping_b<=0;\n      end else case(state)')
    s=replace_between(s,'module serial_reverb_effect','module stereo_effects',stage_body,reverb_clear)
    top_clear='''end else begin
      valid_o<=0;clip_o<=0;
      if(clear_i) begin
        state<=IDLE;valid_o<=0;clip_o<=0;
      end else case(state)'''
    s=replace_between(s,'module stereo_effects',None,stage_body,top_clear)
    p.write_text(s)
    # Rebuild the existing AE350 UI ROM from a staged copy.  A new PANIC epoch
    # clears its local gate and blocks an already-down touch until release.
    p=stage/'firmware/ui_model.h';s=p.read_text()
    s=replace(s,'unsigned mode,sound,route,gate,sw,note,keyboard,old_down;',
        'unsigned mode,sound,route,gate,sw,note,keyboard,old_down,panic_epoch,panic_latched;')
    s=replace(s,'static inline unsigned ui_touch(ui_model*m,unsigned x,unsigned y,unsigned down) {\n unsigned result=0;int hit=ui_hit(x,y);',
        '''static inline unsigned ui_touch(ui_model*m,unsigned x,unsigned y,unsigned down) {
 unsigned result=0;int hit=ui_hit(x,y);
 if(m->panic_latched) {m->old_down=!!down;if(!down)m->panic_latched=0;return 0;}''')
    s=replace(s,'static inline unsigned ui_active(const ui_model*m,unsigned note) {',
        '''static inline unsigned ui_panic(ui_model*m,unsigned epoch) {
 if(m->panic_epoch==epoch)return 0;
 m->panic_epoch=epoch;m->gate=0;m->keyboard=0;m->panic_latched=m->old_down;
 return UI_CHANGED;
}
static inline unsigned ui_active(const ui_model*m,unsigned note) {''')
    p.write_text(s)
    p=stage/'firmware/ui_main.c';s=p.read_text()
    s=replace(s,'unsigned sequence=a138_read(AUDIO_BASE,0x1a0),state=a138_read(AUDIO_BASE,0x184),options=a138_read(AUDIO_BASE,0x18c);',
        'unsigned sequence=a138_read(AUDIO_BASE,0x1a0),state=a138_read(AUDIO_BASE,0x184),pitch=a138_read(AUDIO_BASE,0x188),options=a138_read(AUDIO_BASE,0x18c);')
    s=replace(s,'unsigned changed=m->pc_faults!=faults||m->mode!=((state>>3)&3u)||m->sound!=((state>>7)&7u)||m->route!=((state>>5)&3u)||m->sw!=sw||m->voices!=((state>>10)&63u);',
        'unsigned changed=ui_panic(m,pitch>>22)|(m->pc_faults!=faults)||m->mode!=((state>>3)&3u)||m->sound!=((state>>7)&7u)||m->route!=((state>>5)&3u)||m->sw!=sw||m->voices!=((state>>10)&63u);')
    s=replace(s,'ddr_checks();audio_checks();model_check();',
        '''ddr_checks();audio_checks();model_check();
    // Reload a visible LED-only guide after the short service self-test.  It
    // remains stopped until Push Play (CC85) and never creates note/PCM data.
    static const a138_cue guide[9]={{0,0x0000000f},{24000,0x000000f0},
        {48000,0x00000f00},{72000,0x0000f000},{96000,0x000f0000},
        {120000,0x00f00000},{144000,0x0f000000},{168000,0xf0000000},
        {192000,0}};
    if(!a138_score_load(AUDIO_BASE,guide,9))fail(0xbad03107);''')
    p.write_text(s)
    ui_cc=str(Path.home()/'.local/opt/amd/2025.2.1/gnu/riscv/lin/bin/riscv64-unknown-elf')
    with (out/'ui_firmware_build.log').open('w') as log:
        subprocess.run([ui_cc+'-gcc','-march=rv32im_zicsr','-mabi=ilp32','-msmall-data-limit=0','-O2','-ffreestanding',
            '-Wall','-Wextra','-Werror','-Wno-unused-function','-nostdlib','-nostartfiles','-Wl,--build-id=none','-Wl,-T,firmware/boot.ld',
            '-o','firmware/boot.elf','firmware/start.S','firmware/ui_main.c','firmware/ui_render.c','firmware/ui_runtime.c'],
            cwd=stage,stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run([ui_cc+'-objcopy','-O','binary','firmware/boot.elf','firmware/boot.bin'],cwd=stage,
            stdout=log,stderr=subprocess.STDOUT,check=True)
    ui_binary=(stage/'firmware/boot.bin').read_bytes();assert len(ui_binary)<=16384,'AE350 UI ROM overflow'
    ui_binary=ui_binary.ljust(16384,b'\0')
    (stage/'firmware/boot.mem').write_text(''.join(f'{int.from_bytes(ui_binary[i:i+4],"little"):08x}\n' for i in range(0,len(ui_binary),4)))
    shutil.copy2(ROOT/'rtl/display_data_layout_pkg.svh',stage/'src/memory/display_data_layout_pkg.sv')
    dest=stage/'src/usb_a';dest.mkdir()
    tree=ET.parse(stage/'Prj1.gprj');fl=tree.find('FileList')
    fl.insert(0,ET.Element('File',path='src/memory/display_data_layout_pkg.sv',type='file.verilog',enable='1'))
    tf_sources=[stage/'src/memory/ddr_address_map_guard.v',stage/'src/audio/tf_rate_pt8211_tx.v']
    tf_sources+=sorted(storage_dest.rglob('*.v'))
    for source in tf_sources:
        ET.SubElement(fl,'File',path=source.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    shutil.copy2(ROOT/'p11.gsc',stage/'constraints/p11.gsc')
    ET.SubElement(fl,'File',path='constraints/p11.gsc',type='file.gsc',enable='1')
    kept_push={'gw138k_push_performance_uart.sv','gw138k_push_workstation_top.v','push2_controls.sv',
               'push2_midi_rx.sv','push2_surface_pixels.sv','push2_led_tx.sv','push2_lights.sv'}
    kept_usb={'gw138k_usb_controlled_audio.sv','gw138k_usb_event_fifo.v'}
    for f in list(fl):
        name=f.get('path','');p=Path(name)
        if (name.startswith('src/push2/') and p.name not in kept_push) or (name.startswith('src/usb_host/') and p.name not in kept_usb):
            fl.remove(f)
    for f in sorted((USB/'src').glob('*')):
        if f.suffix not in ['.v','.sv'] or f.name in ['reference_top.v','gw138k_cpu_pll_cell.v','reset_release.v','video_pll_init.v']:continue
        shutil.copy2(f,dest/f.name)
    ET.SubElement(fl,'File',path='src/memory/display_data_writer.v',type='file.verilog',enable='1')
    ET.SubElement(fl,'File',path='src/memory/display_data_reader.v',type='file.verilog',enable='1')
    shutil.copy2(ROOT/'rtl/push2_usb_a_control.sv',dest/'push2_usb_a_control.sv')
    shutil.copy2(ROOT/'rtl/push2_screen_packet_loader.sv',dest/'push2_screen_packet_loader.sv')
    shutil.copy2(ROOT/'rtl/push2_screen_fifo_streamer.sv',dest/'push2_screen_fifo_streamer.sv')
    # The screen streamer and USB FIFO share the 48 MHz host clock.  Give the
    # staged USB core a direct byte input so the existing FIFO need not route
    # every pixel byte through the CPU register acknowledge protocol.
    p=dest/'usbh_core.sv';s=p.read_text()
    s=replace(s,'    input logic [3:0]       reg_be,',
        '    input logic [3:0]       reg_be,\n    input logic             screen_fifo_push_i,\n    input logic [7:0]       screen_fifo_data_i,')
    s=replace(s,'    .data_i(usb_wr_data_data_out_w),\n    .push_i(usb_wr_data_wr_req_w),',
        '    .data_i(screen_fifo_push_i ? screen_fifo_data_i : usb_wr_data_data_out_w),\n    .push_i(screen_fifo_push_i || usb_wr_data_wr_req_w),')
    p.write_text(s)
    for f in sorted(dest.iterdir()):ET.SubElement(fl,'File',path=f.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    ET.indent(tree,space='    ');tree.write(stage/'Prj1.gprj',encoding='utf-8',xml_declaration=True)
    # Add the Push MMIO window and a same-clock screen packet bus master.
    p=dest/'iosys2.v';s=p.read_text()
    s=replace(s,'inout             usb_dp        // USB D+','inout             usb_dp,       // USB D+\n    output mmio_select,mmio_write,output [7:0] mmio_address,\n    output [31:0] mmio_wdata,input mmio_ready,input [31:0] mmio_rdata')
    s=replace(s,'localparam string ROM_FILE = "firmware.hex";','localparam ROM_FILE = "push2_usb_a.hex";')
    s=replace(s,'// Interface to USB host controller','''wire screen_load=dbus_cmd_valid && dbus_cmd_wr && dbus_cmd_a==32'h02000250;
wire screen_active,screen_done,screen_read,screen_write;
wire [7:0] screen_byte;
push2_screen_fifo_streamer screen_loader(
    .clk(clk),.reset_n(resetn),.start(screen_load),
    .pixel_read(screen_read),.pixel_ready(mmio_ready),.pixel_data(mmio_rdata),
    .fifo_push(screen_write),.fifo_data(screen_byte),
    .active(screen_active),.done(screen_done));
assign mmio_select=screen_active?screen_read:
    dbus_cmd_valid && dbus_cmd_a[31:8]==24'h020002 && !screen_load;
assign mmio_write=screen_active?1'b0:dbus_cmd_wr;
assign mmio_address=screen_active?8'h2c:dbus_cmd_a[7:0];
assign mmio_wdata=dbus_cmd_data;
reg mmio_response;
reg [31:0] mmio_result;
always @(posedge clk) begin
    mmio_response<=mmio_select && mmio_ready && !dbus_cmd_wr && !screen_active;
    if(mmio_select && mmio_ready && !dbus_cmd_wr && !screen_active)mmio_result<=mmio_rdata;
end
// Interface to USB host controller''')
    s=replace(s,'usb_sel ? usb_ack :','screen_load ? screen_done : mmio_select ? mmio_ready : usb_sel ? usb_ack :')
    s=replace(s,'wire [31:0] dbus_rdata = dbus_mem_ready ? mem_rdata :','wire [31:0] dbus_rdata = mmio_response ? mmio_result : dbus_mem_ready ? mem_rdata :')
    s=replace(s,'.reg_wdata(dbus_cmd_data), .reg_be(mem_wstrb),',
        '.reg_wdata(dbus_cmd_data), .reg_be(mem_wstrb),\n    .screen_fifo_push_i(screen_write),.screen_fifo_data_i(screen_byte),')
    p.write_text(s)
    p=stage/'src/push2/gw138k_push_workstation_top.v';s=p.read_text()
    start=s.index('    output wire push_htclk');end=s.index('    inout wire usb1_dp',start);s=s[:start]+s[end:]
    start=s.index('    wire usb_event_valid');end=s.index('    wire [31:0] output_pcm',start)
    s=s[:start]+'''    wire mmio_select,mmio_write,mmio_ready;
    wire [7:0] mmio_address;wire [31:0] mmio_wdata,mmio_rdata;
    wire [223:0] usb_words;
    iosys2 u_usb_host(.clk(usb_clk),.resetn(usb_reset_n),.uart_rx(1'b1),.uart_tx(),
        .usb_dp(usb1_dp),.usb_dm(usb1_dn),.mmio_select(mmio_select),.mmio_write(mmio_write),
        .mmio_address(mmio_address),.mmio_wdata(mmio_wdata),.mmio_ready(mmio_ready),.mmio_rdata(mmio_rdata));
'''+s[end:]
    start=s.index('    wire push_valid');end=s.index('    gw138k_usb_controlled_audio u_managed',start)
    s=s[:start]+'''    wire all_usb_valid,all_usb_ready;wire [17:0] all_usb_event;
    wire [447:0] push_snapshot;
    wire [31:0] score_led_mask;wire score_running,record_enabled;
    wire [33:0] service_state_usb;wire service_state_usb_valid;
    gw138k_stream_cdc #(.WIDTH(34)) u_service_push_cdc(
        .reset_n(reset_n && audio_reset_n && usb_reset_n),.source_clk(audio_clk),.destination_clk(usb_clk),
        .source_valid(audio_sample_valid),.source_data({record_enabled,score_running,score_led_mask}),
        .destination_valid(service_state_usb_valid),.destination_data(service_state_usb));
    wire [63:0] display_summary,display_summary_usb;wire display_summary_valid,display_summary_usb_valid;
    gw138k_stream_cdc #(.WIDTH(64)) u_display_push_cdc(
        .reset_n(reset_n && memory_reset_n && usb_reset_n),.source_clk(memory_clk),.destination_clk(usb_clk),
        .source_valid(display_summary_valid),.source_data(display_summary),
        .destination_valid(display_summary_usb_valid),.destination_data(display_summary_usb));
    push2_usb_a_control u_push(.clk(usb_clk),.reset_n(usb_reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .feedback_clk(clk_50m),.feedback_reset_n(reset_n),.performance_words(push_snapshot),
        .display_meta_data(display_summary_usb),.display_meta_valid(display_summary_usb_valid),
        .service_state_data(service_state_usb),.service_state_valid(service_state_usb_valid),
        .select(mmio_select),.write(mmio_write),.address(mmio_address),.wdata(mmio_wdata),.ready(mmio_ready),.rdata(mmio_rdata),
        .audio_valid(all_usb_valid),.audio_ready(all_usb_ready),.audio_event(all_usb_event),.telemetry(usb_words));
'''+s[end:]
    s=replace(s,'.app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),\n        .sample_data(output_mid)',
             '.app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),\n        .push_display_summary(display_summary),.push_display_summary_valid(display_summary_valid),\n        .sample_data(output_mid)')
    s=replace(s,'.pc_uart_rx_i(pc_uart_rx_i),.performance_words_o(performance_words),',
        '.pc_uart_rx_i(pc_uart_rx_i),.performance_words_o(performance_words),\n        .led_mask_o(score_led_mask),.score_running_o(score_running),.record_enabled_o(record_enabled),')
    s=replace(s,'.push_words(push_words),','.push_words(224\'d0),')
    s=replace(s,'module gw138k_push_workstation_top (',f'''module gw138k_push_workstation_top #(
    parameter integer TF_AUDIO_KIND={tf_audio_kind}
) (''')
    s=replace(s,'    input wire pc_uart_rx_i,',
        '''    input wire pc_uart_rx_i,
    input wire sd_miso,
    output wire sd_mosi,sd_sck,sd_cs_n,''')
    s=replace(s,'    wire [31:0] output_pcm,output_reference,active_voices,display_status;',
        '''    wire [31:0] output_pcm,output_reference,active_voices,display_status;
    wire synth_hp_bck,synth_hp_ws,synth_hp_din,synth_pa_en;''')
    s=replace(s,'.hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),',
        '.hp_bck(synth_hp_bck),.hp_ws(synth_hp_ws),.hp_din(synth_hp_din),.pa_en(synth_pa_en),')
    s=replace(s,'    wire [31:0] app_wmask;\n    ddr3_platform u_memory (',
        '''    wire [31:0] app_wmask;
    wire audio_ddr_req,audio_ddr_write,audio_ddr_ready,audio_ddr_response;
    wire [28:0] audio_ddr_address;wire [255:0] audio_ddr_data;
    wire signed [31:0] tf_pcm_left,tf_pcm_right;
    wire tf_pcm_valid,tf_source_active,tf_format_ready,tf_unsupported,tf_ddr_error;
    wire [19:0] tf_sample_rate;wire [31:0] tf_file_size;wire [4:0] tf_track_count;
    wire tf_sample_ce,tf_hp_bck,tf_hp_ws,tf_hp_din,tf_pa_en;
    tf_workstation_audio_bridge #(
        .AUDIO_KIND(TF_AUDIO_KIND),
        .FILE_EXT(TF_AUDIO_KIND==1 ? "MP3" : (TF_AUDIO_KIND==3 ? "FLA" : "WAV"))
    ) u_tf_audio(
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_ready(memory_calibrated && memory_reset_n),.restart(1'b0),.track_index(4'd0),
        .sd_miso(sd_miso),.sd_cs_n(sd_cs_n),.sd_sck(sd_sck),.sd_mosi(sd_mosi),
        .sample_ce(tf_sample_ce),.pcm_left(tf_pcm_left),.pcm_right(tf_pcm_right),
        .pcm_active(tf_pcm_valid),.source_active(tf_source_active),
        .sample_rate_hz(tf_sample_rate),.format_ready(tf_format_ready),.unsupported(tf_unsupported),
        .ddr_error(tf_ddr_error),.file_size(tf_file_size),.track_count(tf_track_count),
        .ddr_valid(audio_ddr_req),.ddr_write(audio_ddr_write),.ddr_address(audio_ddr_address),
        .ddr_data(audio_ddr_data),.ddr_ready(audio_ddr_ready),.ddr_response(audio_ddr_response),
        .ddr_response_data(app_rdata));
    wire [19:0] tf_dac_rate=(tf_format_ready && !tf_unsupported &&
        tf_sample_rate>=20'd8000 && tf_sample_rate<=20'd96000) ? tf_sample_rate : 20'd0;
    tf_rate_pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1),.RATE_MUL(916260)) u_tf_dac(
        .clk(audio_clk),.reset_n(audio_reset_n),.sample_data(tf_pcm_left),.sample_right(tf_pcm_right),
        .sample_valid(tf_pcm_valid),.rate_hz(tf_dac_rate),.sample_tick(tf_sample_ce),
        .hp_bck(tf_hp_bck),.hp_ws(tf_hp_ws),.hp_din(tf_hp_din),.pa_en(tf_pa_en),
        .underrun_count(),.frame_count(),.sample_revision(24'd0),.sample_nonzero_voices(32'd0),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(32'd0),.frame_trigger_reference());
    assign hp_bck=tf_source_active ? tf_hp_bck : synth_hp_bck;
    assign hp_ws=tf_source_active ? tf_hp_ws : synth_hp_ws;
    assign hp_din=tf_source_active ? tf_hp_din : synth_hp_din;
    assign pa_en=tf_source_active ? tf_pa_en : synth_pa_en;
    ddr_address_map_guard u_ddr_address_map_guard();
    ddr3_platform u_memory (''')
    s=replace(s,'.cpu_data(cpu_mem_data),.cpu_mask(cpu_mem_mask),.cpu_ready(cpu_mem_ready),.cpu_response(cpu_mem_response),',
        '''.cpu_data(cpu_mem_data),.cpu_mask(cpu_mem_mask),.cpu_ready(cpu_mem_ready),.cpu_response(cpu_mem_response),
        .audio_req(audio_ddr_req),.audio_write(audio_ddr_write),.audio_address(audio_ddr_address),
        .audio_data(audio_ddr_data),.audio_ready(audio_ddr_ready),.audio_response(audio_ddr_response),''')
    p.write_text(s)
    # Reuse existing USB->50MHz telemetry snapshot for the new P138 record.
    p=stage/'src/push2/gw138k_push_performance_uart.sv';s=p.read_text()
    s=replace(s,'payload<={usb_snapshot,sequence_count-32\'d1};','payload<={224\'d0,sequence_count-32\'d1};')
    s=replace(s,'payload<={push_words,sequence_count-32\'d1};','payload<={usb_snapshot,sequence_count-32\'d1};');p.write_text(s)
    p=stage/'constraints/tang_mega_138k.cst';s=p.read_text()
    p.write_text('\n'.join(line for line in s.splitlines() if '"push_' not in line)+'\n'+(ROOT/'p11.cst').read_text())
    p=stage/'constraints/tang_mega_138k.sdc';s=p.read_text().split('# CH569 HSPI16')[0]
    s='\n'.join(line for line in s.splitlines() if 'u_usb_host/u_fifo' not in line)+'\n'
    s=replace(s,'set_false_path -to [get_pins {u_managed/effect_mask_sync*/RESET u_managed/effect_mask_meta*/RESET}]\n','')
    # Same reset and opposite-direction mailbox can share local release FFs.
    s=s.replace('u_runtime/u_usb_cdc/source_release*/CLEAR u_runtime/u_usb_cdc/destination_release*/CLEAR',
        'u_runtime/u_usb_cdc/source_release*/CLEAR u_runtime/u_usb_cdc/destination_release*/CLEAR u_push/feedback/source_release*/CLEAR u_push/feedback/destination_release*/CLEAR')
    s+=(ROOT/'usb_a.sdc').read_text();p.write_text(s)
    fw=out/'firmware';shutil.copytree(USB/'firmware',fw,ignore=shutil.ignore_patterns('*.o','*.elf','*.bin'))
    shutil.copy2(ROOT/'firmware.c',fw/'firmware.c')
    # Split the original driver's buffer loading from its unchanged token,
    # response and PID handling. The screen loader supplies the same TX FIFO.
    p=fw/'usb/usb_hw.c';s=p.read_text()
    signature='int usbhw_transfer_out(uint8_t pid, int device_addr, int endpoint, int handshake, uint8_t request, uint8_t *tx, int tx_length)'
    preloaded='int usbhw_transfer_out_preloaded(uint8_t pid, int device_addr, int endpoint, int handshake, uint8_t request, int tx_length)'
    wrapper=signature+'''\n{
    for (int l=0;l<tx_length;l++)usbhw_reg_write(USB_WR_DATA, tx[l]);
    return usbhw_transfer_out_preloaded(pid,device_addr,endpoint,handshake,request,tx_length);
}
'''
    s=replace(s,signature,wrapper+'\n'+preloaded)
    s=replace(s,'    int l;\n    uint32_t ctrl = 0;','    uint32_t ctrl = 0;')
    begin=s.index('    // Load DATAx transfer into address 0+')
    end=s.index('    // Transfer data length',begin)
    s=s[:begin]+s[end:];p.write_text(s)
    p=fw/'usb/usb_hw.h';s=p.read_text()
    s=replace(s,'void usbhw_init(uint32_t base);',preloaded+';\nvoid usbhw_init(uint32_t base);');p.write_text(s)
    prefix=str(Path.home()/'.local/opt/amd/2025.2.1/gnu/riscv/lin/bin/riscv64-unknown-elf')
    with (out/'firmware_build.log').open('w') as log:
        def run(cmd):subprocess.run(cmd,cwd=fw,stdout=log,stderr=subprocess.STDOUT,check=True)
        objects=[]
        for name in ['start.S','firmware.c','minlibc.c','usb/usb_core.c','usb/usb_hw.c']:
            obj=str(Path(name).with_suffix('.o'));objects.append(obj)
            run([prefix+'-gcc','-Wall','-O2','-g','-mabi=ilp32','-march=rv32i','-ffreestanding','-Iusb','-I.','-c',name,'-o',obj])
        run([prefix+'-gcc','-mabi=ilp32','-march=rv32i','-Wl,--build-id=none,-Bstatic,-T,baremetal.ld','-nostdlib',*objects,'-lgcc','-o','firmware.elf'])
        run([prefix+'-objcopy','-O','binary','firmware.elf','firmware.bin'])
        run([prefix+'-size','firmware.elf'])
    binary=(fw/'firmware.bin').read_bytes();assert len(binary)<60000,'leave stack space in 64 KiB RAM'
    binary=binary.ljust(65536,b'\0');hexdata=''.join(f'{int.from_bytes(binary[i:i+4],"little"):08x}\n' for i in range(0,len(binary),4))
    (stage/'push2_usb_a.hex').write_text(hexdata);(dest/'push2_usb_a.hex').write_text(hexdata)
    hashes={str(p.relative_to(stage)):sha(p) for p in stage.rglob('*') if p.is_file()}
    (out/'workstation_inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
    origins=dict(
        workstation=WORK.relative_to(ROOT.parents[3]).as_posix(),
        usb_host=USB.relative_to(ROOT.parents[3]).as_posix(),hardware_tested=False,
        usb_host_implementation='VexRiscv firmware + RTL PHY/Host; no CH569',
        sources={str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*') if p.is_file() and 'results' not in p.relative_to(ROOT).parts and '__pycache__' not in p.parts})
    (out/'origins.json').write_text(json.dumps(origins,indent=2)+'\n');print(out,flush=True)
    if not args.no_update_latest:
        (ROOT/'LATEST_BUILD.txt').write_text(out.relative_to(ROOT).as_posix()+'\n')
    if args.prepare_only:return
    if args.reuse_synthesis:
        previous=args.reuse_synthesis.resolve();old=json.loads((previous/'workstation_inputs.json').read_text())
        # boot.elf carries linker metadata and is not a Gowin project input;
        # boot.mem is the exact synthesized ROM image and remains compared.
        assert all(old.get(p)==h and sha(previous/'Prj1'/p)==h for p,h in hashes.items()
                   if not p.startswith('constraints/') and not p.endswith('.elf')),'changed RTL/firmware cannot reuse synthesis'
        shutil.copytree(previous/'Prj1/impl/gwsynthesis',stage/'impl/gwsynthesis')
        (out/'reused_synthesis.json').write_text(json.dumps(dict(source=str(previous),non_constraint_inputs_identical=True),indent=2)+'\n')
    with (out/'gowin.log').open('w') as log:
        r=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,env=dict(os.environ,PRJ1_FLOW='pnr' if args.reuse_synthesis else 'all'),stdout=log,stderr=subprocess.STDOUT)
    changed=[p for p,h in hashes.items() if sha(stage/p)!=h]
    (out/'tool_result.json').write_text(json.dumps(dict(exit_code=r.returncode,inputs_unchanged=not changed,changed=changed,hardware_tested=False),indent=2)+'\n')
    print('Gowin exit',r.returncode,'changed inputs',changed,flush=True)
    if r.returncode or changed:raise SystemExit(1)
if __name__=='__main__':main()
