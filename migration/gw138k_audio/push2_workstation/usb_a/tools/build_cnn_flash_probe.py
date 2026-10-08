#!/usr/bin/env python3
"""Offline build of a temporary SRAM-only Flash/local-RAM diagnostic, never DDR proof."""
import argparse,hashlib,json,re,shutil,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
from build_workstation_flash_boot import ROOT,BASE,CST,used_codes

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport',choices=('direct','serial'),default='serial')
    p.add_argument('--flow',choices=('prepare','syn','all'),default='prepare')
    p.add_argument('--user-code')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.flow=='all':
        if not a.user_code or not re.fullmatch('[0-9A-Fa-f]{8}',a.user_code) or int(a.user_code,16)==0:
            p.error('Full bitstream requires a new nonzero eight-hex-digit UserCode')
        if int(a.user_code,16) in used_codes():p.error('UserCode already recorded')
    elif a.user_code:p.error('Prepare/SYN assign no UserCode')
    out=a.output.resolve();stage=out/'Prj1'
    assert not out.exists(),'preserve existing evidence'
    files=['sim/model_flash/flash_pin_probe.sv']+[f'rtl/music/{n}' for n in
        ('basic_pitch_flash_model_loader.sv','basic_pitch_flash_serial_boot.sv','basic_pitch_uart_model_loader.sv',
         'basic_pitch_uart_rx.sv','basic_pitch_flash_io_guard.sv','basic_pitch_link_uart.sv',
         'basic_pitch_ddr_map.svh','basic_pitch_flash_map.svh')]
    for rel in files:
        target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,target)
    probe=stage/files[0]
    if a.transport=='serial':probe.write_text(probe.read_text().replace("parameter bit SERIAL_TRANSPORT=1'b0","parameter bit SERIAL_TRANSPORT=1'b1"))
    tx=stage/'src/control/uart_tx.v';tx.parent.mkdir(parents=True);shutil.copy2(BASE/'Prj1/src/control/uart_tx.v',tx)
    (stage/'constraints').mkdir();(stage/'scripts').mkdir()
    (stage/'constraints/probe.cst').write_text('''IO_LOC "clk_50m" V22;
IO_PORT "clk_50m" IO_TYPE=LVCMOS33;
IO_LOC "button1_n" AB13;
IO_PORT "button1_n" IO_TYPE=LVCMOS33 PULL_MODE=UP;
IO_LOC "debug_uart_tx" U15;
IO_PORT "debug_uart_tx" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8;
'''+CST)
    (stage/'constraints/probe.sdc').write_text('create_clock -name clk_50m -period 20.000 [get_ports {clk_50m}]\nset_input_delay 15.000 -clock [get_clocks {clk_50m}] [get_ports {flash_miso}]\n')
    project=ET.Element('Project');ET.SubElement(project,'Template').text='FPGA';ET.SubElement(project,'Version').text='5'
    ET.SubElement(project,'Device',name='GW5AST-138C',pn='GW5AST-LV138PG484AC2/I1').text='gw5ast138c-006'
    fl=ET.SubElement(project,'FileList')
    for rel in files+['src/control/uart_tx.v','constraints/probe.cst','constraints/probe.sdc']:
        if rel.endswith('.svh'):continue
        typ='file.cst' if rel.endswith('.cst') else 'file.sdc' if rel.endswith('.sdc') else 'file.verilog'
        ET.SubElement(fl,'File',path=rel,type=typ,enable='1')
    ET.ElementTree(project).write(stage/'Prj1.gprj',encoding='UTF-8',xml_declaration=True)
    tcl='''set root [file normalize [file join [file dirname [info script]] ..]]
cd $root
open_project [file join $root Prj1.gprj]
set_option -top_module flash_pin_probe
set_option -output_base_name Prj1
set_option -verilog_std sysv2017
set_option -use_mspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -timing_driven 1
set_option -correct_hold_violation 1
set_option -route_option 0
set_option -gen_text_timing_rpt 1
'''
    if a.user_code:tcl+='set_option -user_code '+a.user_code.upper()+'\n'
    tcl+='run '+('syn' if a.flow=='syn' else 'all')+'\n';(stage/'scripts/build.tcl').write_text(tcl)
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    inputs={str(f.relative_to(stage)):sha(f) for f in stage.rglob('*') if f.is_file()}
    (out/'workstation_inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    (out/'build_metadata.json').write_text(json.dumps(dict(user_code='0x'+a.user_code.upper() if a.user_code else None,
        full_workstation=False,temporary_sram_only=True,flash_configuration_never_program=True,transport=a.transport,
        purpose='Physical Flash/internal protocol/local RAM CRC, not DDR or Flash configuration proof'),indent=2)+'\n')
    if a.flow=='prepare':return
    with (out/'gowin_all.log').open('w') as log:
        run=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,stdout=log,stderr=subprocess.STDOUT)
    changed=[f for f,h in inputs.items() if sha(stage/f)!=h]
    (out/'tool_result.json').write_text(json.dumps(dict(exit_code=run.returncode,inputs_unchanged=not changed,changed=changed,hardware_tested=False),indent=2)+'\n')
    assert run.returncode==0 and not changed,'probe build/input drift failed'
    print(out)
if __name__=='__main__':main()
