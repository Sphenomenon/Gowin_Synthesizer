#!/usr/bin/env python3
"""Offline merge of frozen 3BE2 audio workstation and accepted 8FC3 USB-A Host.
No programming, UART, or board discovery operations are performed.
"""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,os,shutil,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent/'results/workstation_20260911_174045_306332'
USB=ROOT.parents[2]/'midi_device_reference/push2_usb_host/results/fs_surface_build_20260911_200312_216160'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
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
    ap.add_argument('--user-code',help='Optional eight hexadecimal digits identifying a release without changing RTL')
    args=ap.parse_args()
    if args.user_code is not None:
        if len(args.user_code)!=8 or any(c not in '0123456789abcdefABCDEF' for c in args.user_code):
            ap.error('--user-code requires eight hexadecimal digits')
    for base,manifest,prefix in [(WORK,'workstation_inputs.json','Prj1'),(USB,'inputs.json','')]:
        hashes=json.loads((base/manifest).read_text())
        assert all(sha(base/prefix/p)==h for p,h in hashes.items()),'frozen inputs changed: '+str(base)
    out=ROOT/'results'/datetime.now().strftime('build_%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    stage=out/'Prj1'
    shutil.copytree(WORK/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','__pycache__','*.user'))
    if args.user_code is not None:
        tcl=stage/'scripts/build.tcl'
        tcl.write_text(replace(tcl.read_text(),'set flow all',
            'set_option -user_code '+args.user_code.upper()+'\nset flow all'))
    shutil.copytree(WORK/'reference',out/'reference')
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
    wire [63:0] display_summary,display_summary_usb;wire display_summary_valid,display_summary_usb_valid;
    gw138k_stream_cdc #(.WIDTH(64)) u_display_push_cdc(
        .reset_n(reset_n && memory_reset_n && usb_reset_n),.source_clk(memory_clk),.destination_clk(usb_clk),
        .source_valid(display_summary_valid),.source_data(display_summary),
        .destination_valid(display_summary_usb_valid),.destination_data(display_summary_usb));
    push2_usb_a_control u_push(.clk(usb_clk),.reset_n(usb_reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .feedback_clk(clk_50m),.feedback_reset_n(reset_n),.performance_words(push_snapshot),
        .display_meta_data(display_summary_usb),.display_meta_valid(display_summary_usb_valid),
        .select(mmio_select),.write(mmio_write),.address(mmio_address),.wdata(mmio_wdata),.ready(mmio_ready),.rdata(mmio_rdata),
        .audio_valid(all_usb_valid),.audio_ready(all_usb_ready),.audio_event(all_usb_event),.telemetry(usb_words));
'''+s[end:]
    s=replace(s,'.app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),\n        .sample_data(output_mid)',
             '.app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),\n        .push_display_summary(display_summary),.push_display_summary_valid(display_summary_valid),\n        .sample_data(output_mid)')
    s=replace(s,'.push_words(push_words),','.push_words(224\'d0),');p.write_text(s)
    # Reuse existing USB->50MHz telemetry snapshot for the new P138 record.
    p=stage/'src/push2/gw138k_push_performance_uart.sv';s=p.read_text()
    s=replace(s,'payload<={usb_snapshot,sequence_count-32\'d1};','payload<={224\'d0,sequence_count-32\'d1};')
    s=replace(s,'payload<={push_words,sequence_count-32\'d1};','payload<={usb_snapshot,sequence_count-32\'d1};');p.write_text(s)
    p=stage/'constraints/tang_mega_138k.cst';s=p.read_text()
    p.write_text('\n'.join(line for line in s.splitlines() if '"push_' not in line)+'\n'+(ROOT/'p11.cst').read_text())
    p=stage/'constraints/tang_mega_138k.sdc';s=p.read_text().split('# CH569 HSPI16')[0]
    s='\n'.join(line for line in s.splitlines() if 'u_usb_host/u_fifo' not in line)+'\n'
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
    origins=dict(workstation=str(WORK),usb_host=str(USB),hardware_tested=False,
        usb_host_implementation='VexRiscv firmware + RTL PHY/Host; no CH569',
        sources={str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*') if p.is_file() and 'results' not in p.relative_to(ROOT).parts and '__pycache__' not in p.parts})
    (out/'origins.json').write_text(json.dumps(origins,indent=2)+'\n');print(out,flush=True)
    (ROOT/'LATEST_BUILD.txt').write_text(str(out)+'\n')
    if args.prepare_only:return
    if args.reuse_synthesis:
        previous=args.reuse_synthesis.resolve();old=json.loads((previous/'workstation_inputs.json').read_text())
        assert all(old.get(p)==h and sha(previous/'Prj1'/p)==h for p,h in hashes.items() if not p.startswith('constraints/')),'changed RTL/firmware cannot reuse synthesis'
        shutil.copytree(previous/'Prj1/impl/gwsynthesis',stage/'impl/gwsynthesis')
        (out/'reused_synthesis.json').write_text(json.dumps(dict(source=str(previous),non_constraint_inputs_identical=True),indent=2)+'\n')
    with (out/'gowin.log').open('w') as log:
        r=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,env=dict(os.environ,PRJ1_FLOW='pnr' if args.reuse_synthesis else 'all'),stdout=log,stderr=subprocess.STDOUT)
    changed=[p for p,h in hashes.items() if sha(stage/p)!=h]
    (out/'tool_result.json').write_text(json.dumps(dict(exit_code=r.returncode,inputs_unchanged=not changed,changed=changed,hardware_tested=False),indent=2)+'\n')
    print('Gowin exit',r.returncode,'changed inputs',changed,flush=True)
    if r.returncode or changed:raise SystemExit(1)
if __name__=='__main__':main()
