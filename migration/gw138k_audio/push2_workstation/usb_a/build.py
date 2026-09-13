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
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--reuse-synthesis',type=Path);args=ap.parse_args()
    for base,manifest,prefix in [(WORK,'workstation_inputs.json','Prj1'),(USB,'inputs.json','')]:
        hashes=json.loads((base/manifest).read_text())
        assert all(sha(base/prefix/p)==h for p,h in hashes.items()),'frozen inputs changed: '+str(base)
    out=ROOT/'results'/datetime.now().strftime('build_%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    stage=out/'Prj1'
    shutil.copytree(WORK/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','__pycache__','*.user'))
    shutil.copytree(WORK/'reference',out/'reference')
    dest=stage/'src/usb_a';dest.mkdir()
    tree=ET.parse(stage/'Prj1.gprj');fl=tree.find('FileList')
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
    shutil.copy2(ROOT/'rtl/push2_usb_a_control.sv',dest/'push2_usb_a_control.sv')
    for f in sorted(dest.iterdir()):ET.SubElement(fl,'File',path=f.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    ET.indent(tree,space='    ');tree.write(stage/'Prj1.gprj',encoding='utf-8',xml_declaration=True)
    # Keep the accepted Host unchanged except its additional MMIO window.
    p=dest/'iosys2.v';s=p.read_text()
    s=replace(s,'inout             usb_dp        // USB D+','inout             usb_dp,       // USB D+\n    output mmio_select,mmio_write,output [7:0] mmio_address,\n    output [31:0] mmio_wdata,input mmio_ready,input [31:0] mmio_rdata')
    s=replace(s,'localparam string ROM_FILE = "firmware.hex";','localparam ROM_FILE = "push2_usb_a.hex";')
    s=replace(s,'// Interface to USB host controller','''assign mmio_select=dbus_cmd_valid && dbus_cmd_a[31:8]==24'h020002;
assign mmio_write=dbus_cmd_wr;
assign mmio_address=dbus_cmd_a[7:0];
assign mmio_wdata=dbus_cmd_data;
reg mmio_response;
reg [31:0] mmio_result;
always @(posedge clk) begin
    mmio_response<=mmio_select && mmio_ready && !dbus_cmd_wr;
    if(mmio_select && mmio_ready && !dbus_cmd_wr)mmio_result<=mmio_rdata;
end
// Interface to USB host controller''')
    s=replace(s,'usb_sel ? usb_ack :','mmio_select ? mmio_ready : usb_sel ? usb_ack :')
    s=replace(s,'wire [31:0] dbus_rdata = dbus_mem_ready ? mem_rdata :','wire [31:0] dbus_rdata = mmio_response ? mmio_result : dbus_mem_ready ? mem_rdata :')
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
    push2_usb_a_control u_push(.clk(usb_clk),.reset_n(usb_reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .feedback_clk(clk_50m),.feedback_reset_n(reset_n),.performance_words(push_snapshot),
        .select(mmio_select),.write(mmio_write),.address(mmio_address),.wdata(mmio_wdata),.ready(mmio_ready),.rdata(mmio_rdata),
        .audio_valid(all_usb_valid),.audio_ready(all_usb_ready),.audio_event(all_usb_event),.telemetry(usb_words));
'''+s[end:]
    s=replace(s,'.push_words(push_words),','.push_words(224\'d0),');p.write_text(s)
    # Reuse existing USB->50MHz telemetry snapshot for the new P138 record.
    p=stage/'src/push2/gw138k_push_performance_uart.sv';s=p.read_text()
    s=replace(s,'payload<={usb_snapshot,sequence_count-32\'d1};','payload<={224\'d0,sequence_count-32\'d1};')
    s=replace(s,'payload<={push_words,sequence_count-32\'d1};','payload<={usb_snapshot,sequence_count-32\'d1};');p.write_text(s)
    p=stage/'constraints/tang_mega_138k.cst';s=p.read_text()
    p.write_text('\n'.join(line for line in s.splitlines() if '"push_' not in line)+'\n')
    p=stage/'constraints/tang_mega_138k.sdc';s=p.read_text().split('# CH569 HSPI16')[0]
    s='\n'.join(line for line in s.splitlines() if 'u_usb_host/u_fifo' not in line)+'\n'
    # Same reset and opposite-direction mailbox can share local release FFs.
    s=s.replace('u_runtime/u_usb_cdc/source_release*/CLEAR u_runtime/u_usb_cdc/destination_release*/CLEAR',
        'u_runtime/u_usb_cdc/source_release*/CLEAR u_runtime/u_usb_cdc/destination_release*/CLEAR u_push/feedback/source_release*/CLEAR u_push/feedback/destination_release*/CLEAR')
    s+=(ROOT/'usb_a.sdc').read_text();p.write_text(s)
    fw=out/'firmware';shutil.copytree(USB/'firmware',fw,ignore=shutil.ignore_patterns('*.o','*.elf','*.bin'))
    shutil.copy2(ROOT/'firmware.c',fw/'firmware.c')
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
