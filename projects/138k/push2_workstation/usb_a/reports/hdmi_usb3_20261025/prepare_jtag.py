"""Prepare a temporary post-synthesis GAO probe without resynthesizing video RTL."""

from pathlib import Path
import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'out/hdmi_usb3_diagnostic_20261025_c11025d3'
PARENT_INPUT_SHA='4f90d273063b032dd2c4b5dd65131cac643bd1583ed1835b45dd969865ba40b2'
PARENT_NETLIST_SHA='012f162c0c92f8ac0467740a452c1fa3a4d908d16bde1addb4770df27d4f7284'
PARENT_NETLIST=Path('impl/gwsynthesis/hdmi_usb3_diagnostic.vg')
NETLIST=Path('hdmi_usb3_diagnostic.vg')
SIGNALS=('power_reset_n','reset_n_Z','restart_done_Z','pixel_seen','report_active',
         'debug_uart_tx_d',*(f'status_sync_q[{bit}]' for bit in range(4,-1,-1)),
         *(f'report_flags[{bit}]' for bit in range(5,-1,-1)),
         *(f'report_timer[{bit}]' for bit in range(25,17,-1)),
         'u_clock/g_hardware.u_pll/reference_ready','u_clock/g_hardware.u_pll/tmds_ready')


def digest(source):
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def prepare(output,parent=PARENT):
    output=Path(output).resolve()
    parent=Path(parent).resolve()
    if output.exists():
        raise ValueError('a new experiment output is required')
    if digest(parent/'inputs.json')!=PARENT_INPUT_SHA or digest(parent/PARENT_NETLIST)!=PARENT_NETLIST_SHA:
        raise ValueError('D3 source or synthesis-netlist identity changed')
    inputs=json.loads((parent/'inputs.json').read_text())
    for relative,expected in inputs['input_sha256'].items():
        if digest(parent/relative)!=expected:
            raise ValueError('D3 input changed: '+relative)
    output.mkdir(parents=True)
    for relative in inputs['input_sha256']:
        if relative not in ('diagnostic.gprj','run.tcl'):
            shutil.copyfile(parent/relative,output/relative)
    shutil.copyfile(parent/PARENT_NETLIST,output/NETLIST)
    configuration=ET.Element('GAO_CONFIG')
    ET.SubElement(configuration,'Version').text='3.0'
    ET.SubElement(configuration,'Mode').text='Standard'
    core=ET.SubElement(configuration,'AoCore',index='0',sample_clock='clk_50m_d',
        trig_type='0',storage_depth='1024',window_num='1',capture_amount='1024',
        implementation='0',trigger_pos='0',module_name='hdmi_usb3_diagnostic',
        force_trigger_by_falling_edge='false',capture_init_data_enabled='false')
    capture=ET.SubElement(core,'SignalList')
    for signal in SIGNALS:
        ET.SubElement(capture,'Signal',capture_enable='true').text=signal
    triggers=ET.SubElement(core,'Triggers')
    for index in range(16):
        trigger=ET.SubElement(triggers,'Trigger',index=str(index))
        if index==0:
            ET.SubElement(ET.SubElement(trigger,'SignalList'),'Signal').text='power_reset_n'
    matches=ET.SubElement(core,'MatchUnits')
    for index in range(16):
        match=ET.SubElement(matches,'MatchUnit',index=str(index),enabled='1' if index==0 else '0',
            match_type='0',counter_enable='0',counter_width='2',counter='2',
            countinuous='0',func='0',value0='1' if index==0 else '',value1='1' if index==0 else '')
        if index==0:
            match.set('trigger','0')
    ET.SubElement(ET.SubElement(core,'Expressions',type='Static'),'Expression').text='M0'
    ET.SubElement(configuration,'GAO_ID').text='0010010111010101'
    ET.ElementTree(configuration).write(output/'diagnostic.gao',encoding='UTF-8',xml_declaration=True)
    script=('set root [file normalize [file dirname [info script]]]\ncd $root\n'
        'set_device GW5AST-LV138PG484AC2/I1 -device_version C\n'
        'set_option -synthesis_tool gowinsynthesis\n'
        'set_option -top_module hdmi_usb3_diagnostic\n'
        'set_option -output_base_name hdmi_usb3_diagnostic\n'
        'set_option -verilog_std sysv2017\n'
        'set_option -use_mspi_as_gpio 1\nset_option -use_cpu_as_gpio 1\n'
        'add_file -type cst [file join $root diagnostic.cst]\n'
        'add_file -type sdc [file join $root diagnostic.sdc]\n'
        'add_file -type netlist [file join $root hdmi_usb3_diagnostic.vg]\n'
        'add_file -type gao [file join $root diagnostic.gao]\n'
        'set_option -user_code C11025D5\n'
        'set_option -bit_security 0\nset_option -secure_mode 0\n'
        'set_option -bit_encrypt 0\nset_option -bit_compress 0\n'
        'set_option -gen_text_timing_rpt 1\nset_option -gen_sdf 1\n'
        'set_option -gen_verilog_sim_netlist 1\nset_option -timing_driven 1\n'
        'set_option -correct_hold_violation 1\nset_option -place_option 2\n'
        'set_option -route_option 0\nrun pnr\n')
    (output/'run.tcl').write_text(script)
    record=dict(inputs,identity='hdmi-usb3-jtag-observation-C11025D5',user_code='0xC11025D5',
        source_policy='reuse exact D3 synthesis netlist; insert post-synthesis GAO; P&R only',
        preparation_script_sha256=digest(__file__),parent_input_manifest_sha256=PARENT_INPUT_SHA,
        reused_synthesis_netlist_sha256=PARENT_NETLIST_SHA,diagnostic_subset_synthesized=False,
        post_synthesis_gao_requested=True,signals=list(SIGNALS),sample_clock='clk_50m_d',
        hardware_tested=False,sram_programmed=False,flash_programmed=False,release_ready=False,
        rollback='retain D3 on board; SRAM reload only with explicit authorization; never write Flash',
        retirement='remove GAO probe after locating the failing stage; not a production source profile')
    record['input_sha256']={str(source.relative_to(output)):digest(source)
                            for source in sorted(output.rglob('*')) if source.is_file()}
    (output/'inputs.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output),indent=2))
