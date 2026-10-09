#!/usr/bin/env python3
"""Build an isolated Flash->actual DDR diagnostic, temporary SRAM only."""
import argparse,hashlib,json,re,shutil,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
from build_workstation_flash_boot import ROOT,BASE,CST,used_codes

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--flow',choices=('prepare','syn','all'),default='prepare');p.add_argument('--user-code');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.flow=='all':
        if not a.user_code or not re.fullmatch('[0-9A-Fa-f]{8}',a.user_code) or int(a.user_code,16)==0:p.error('new eight-hex-digit nonzero UserCode required')
        if int(a.user_code,16) in used_codes():p.error('UserCode already recorded')
    elif a.user_code:p.error('Prepare/SYN assigns no UserCode')
    out=a.output.resolve();stage=out/'Prj1';assert not out.exists(),'preserve previous evidence'
    files=['sim/model_flash/flash_ddr_probe.sv']+[f'rtl/music/{n}' for n in ('basic_pitch_flash_model_loader.sv','basic_pitch_flash_serial_boot.sv','basic_pitch_uart_model_loader.sv','basic_pitch_uart_rx.sv','basic_pitch_flash_io_guard.sv','basic_pitch_link_uart.sv','basic_pitch_ddr16_port.sv','basic_pitch_ddr_command_buffer.sv','music_async_fifo.sv','basic_pitch_ddr_map.svh','basic_pitch_flash_map.svh')]
    for rel in files:
        dst=stage/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,dst)
    originals=['src/control/uart_tx.v','src/memory/ddr3_platform.v','src/memory/ddr_recovery_guard.v']+[str(f.relative_to(BASE/'Prj1')) for f in (BASE/'Prj1/vendor/gowin_ddr3').glob('*.v')]
    for rel in originals:
        dst=stage/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(BASE/'Prj1'/rel,dst)
    files+=originals
    (stage/'constraints').mkdir();(stage/'scripts').mkdir()
    original=(BASE/'Prj1/constraints/tang_mega_138k.cst').read_text()
    cst='\n'.join(line for line in original.splitlines() if (line.startswith(('IO_LOC','IO_PORT')) and re.search(r'"(?:ddr_[^"]+|clk_50m|button1_n)"',line)) or (line.startswith('INS_LOC') and 'u_memory/' in line))+'\nIO_LOC "debug_uart_tx" U15;\nIO_PORT "debug_uart_tx" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8;\n'+CST
    (stage/'constraints/probe.cst').write_text(cst)
    base_sdc=(BASE/'Prj1/constraints/tang_mega_138k.sdc').read_text()
    lines=[]
    for line in base_sdc.splitlines():
        if line.startswith('create_') and any(n in line for n in ('-name clk_50m ','-name ddr_mem400 ','-name ddr_ui100 ')):lines.append(line)
        elif line.startswith(('set_false_path','set_max_delay')) and 'u_memory/' in line and 'u_video/' not in line:lines.append(line)
    lines += ['set_false_path -from [get_ports {button1_n}]','set_input_delay 15.000 -clock [get_clocks {clk_50m}] [get_ports {flash_miso}]','set_false_path -to [get_pins {flags_meta*/D u_transport/ready_meta*/D}]']
    for fifo in ['u_req_cdc','u_rsp_cdc']:
        for origin,meta in [('write_gray','write_gray_meta'),('read_gray','read_gray_meta')]:
            lines += [f'set_max_delay 10.000 -from [get_regs {{{fifo}/{origin}*}}] -to [get_regs {{{fifo}/{meta}*}}]',f'set_false_path -hold -from [get_regs {{{fifo}/{origin}*}}] -to [get_regs {{{fifo}/{meta}*}}]']
    lines += ['report_timing -setup -max_paths 50','report_timing -hold -max_paths 50']
    (stage/'constraints/probe.sdc').write_text('\n'.join(lines)+'\n');files+=['constraints/probe.cst','constraints/probe.sdc']
    project=ET.Element('Project');ET.SubElement(project,'Template').text='FPGA';ET.SubElement(project,'Version').text='5';ET.SubElement(project,'Device',name='GW5AST-138C',pn='GW5AST-LV138PG484AC2/I1').text='gw5ast138c-006';fl=ET.SubElement(project,'FileList')
    for rel in (f for f in files if not f.endswith('.svh')):ET.SubElement(fl,'File',path=rel,type='file.cst' if rel.endswith('.cst') else 'file.sdc' if rel.endswith('.sdc') else 'file.verilog',enable='1')
    ET.ElementTree(project).write(stage/'Prj1.gprj',encoding='UTF-8',xml_declaration=True)
    tcl='''set root [file normalize [file join [file dirname [info script]] ..]]
cd $root
open_project [file join $root Prj1.gprj]
set_option -top_module flash_ddr_probe
set_option -output_base_name Prj1
set_option -verilog_std sysv2017
set_option -use_mspi_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -timing_driven 1
set_option -correct_hold_violation 1
set_option -route_option 0
set_option -gen_text_timing_rpt 1
set_option -gen_sdf 1
set_option -gen_verilog_sim_netlist 1
'''
    if a.user_code:tcl+='set_option -user_code '+a.user_code.upper()+'\n'
    tcl+='run '+('syn' if a.flow=='syn' else 'all')+'\n';(stage/'scripts/build.tcl').write_text(tcl)
    sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest();inputs={str(q.relative_to(stage)):sha(q) for q in stage.rglob('*') if q.is_file()}
    (out/'workstation_inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');(out/'build_metadata.json').write_text(json.dumps(dict(user_code='0x'+a.user_code.upper() if a.user_code else None,full_workstation=False,temporary_sram_only=True,flash_configuration_never_program=True,actual_external_ddr=True,purpose='isolate DDR PHY/native model port from full workstation concurrent clients'),indent=2)+'\n')
    print(out,flush=True)
    if a.flow=='prepare':return
    with (out/'gowin_all.log').open('w') as log:run=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,stdout=log,stderr=subprocess.STDOUT)
    changed=[f for f,h in inputs.items() if sha(stage/f)!=h];(out/'tool_result.json').write_text(json.dumps(dict(exit_code=run.returncode,inputs_unchanged=not changed,changed=changed,hardware_tested=False),indent=2)+'\n')
    assert not run.returncode and not changed,'probe build failed'
    print('PASS isolated diagnostic build; no hardware operations performed',flush=True)
if __name__=='__main__':main()
