"""Prepare only a small HDMI diagnostic from hash-checked existing inputs."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
PARENT='out/workstation_integration_20261025_a23_v5'
MANIFEST_SHA='88af98466644d04b5cd1b70d1e0695571530e3201abf6beb371f258d7dfb7863'
FILES=('src/platform/reset_release.v','src/platform/video_clock_1080p.v',
       'src/video/video_timing_1080p.v','src/control/uart_tx.v',
       'vendor/sipeed_dvi/video_pll_1080p_gw5a.v','vendor/sipeed_dvi/video_pll_init.v',
       'vendor/sipeed_dvi/dvi_tx_tmds_enc.v','rtl/display_data/workstation_custom_dvi.sv')


def digest(source):
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def prepare(output,user_code):
    output=Path(output).resolve()
    if (output.exists() or not re.fullmatch(r'[0-9A-F]{8}',user_code) or
            user_code in ('C1102515','C11025D1','C11025D2')):
        raise ValueError('new output and a separate eight-digit diagnostic UserCode are required')
    parent=ROOT/PARENT
    if digest(parent/'integration_inputs.json')!=MANIFEST_SHA:
        raise ValueError('validated parent input identity changed')
    metadata=json.loads((parent/'integration_inputs.json').read_text())
    stage=parent/'workstation/Prj1'
    for relative in FILES:
        if digest(stage/relative)!=metadata['staged_input_sha256'][relative]:
            raise ValueError('cached HDMI source changed: '+relative)
    constraints=ROOT/'out/workstation_physical_20261025_c1102515/physical.cst'
    sdc=ROOT/'out/workstation_physical_20261025_c1102515/physical.sdc'
    physical=json.loads((constraints.parent/'physical_inputs.json').read_text())
    for relative in ('physical.cst','physical.sdc'):
        if digest(constraints.parent/relative)!=physical['input_sha256'][relative]:
            raise ValueError('reference constraints changed')
    output.mkdir(parents=True)
    project=ET.Element('Project')
    ET.SubElement(project,'Template').text='FPGA'
    ET.SubElement(project,'Version').text='5'
    ET.SubElement(project,'Device',name='GW5AST-138C',pn='GW5AST-LV138PG484AC2/I1').text='gw5ast138c-006'
    files=ET.SubElement(project,'FileList')
    for relative in FILES:
        destination=output/Path(relative).name
        shutil.copyfile(stage/relative,destination)
        ET.SubElement(files,'File',path=destination.name,type='file.verilog',enable='1')
    top=Path(__file__).with_name('hdmi_usb3_diagnostic.sv')
    shutil.copyfile(top,output/top.name)
    ET.SubElement(files,'File',path=top.name,type='file.verilog',enable='1')
    selected=[]
    ports={'clk_50m','debug_uart_tx','hdmi_hpd','hdmi_cec','tmds_clk_p',
           'tmds_data_p[0]','tmds_data_p[1]','tmds_data_p[2]',
           'flash_clk','flash_cs_n','flash_mosi','flash_wp_n','flash_hold_n'}
    for line in constraints.read_text().splitlines():
        match=re.match(r'IO_(?:LOC|PORT) "([^"]+)"',line)
        if match and match[1] in ports:
            selected.append(line)
    if len(selected)!=len(ports)*2:
        raise ValueError('diagnostic constraint inventory changed')
    (output/'diagnostic.cst').write_text('\n'.join(selected)+'\n')
    clocks=[line.replace('u_video/','') for line in sdc.read_text().splitlines()
            if line.startswith('create_clock -name clk_50m ') or
            any(line.startswith('create_generated_clock -name '+name+' ') for name in
                ('video_ref49','video_serial742','video_pixel148'))]
    if len(clocks)!=4:
        raise ValueError('reference video clock inventory changed')
    (output/'diagnostic.sdc').write_text('\n'.join(clocks)+'\n'+
        'set_false_path -to [get_pins {status_meta_q*/D}]\n'+
        'set_max_delay 2.000 -from [get_pins {status_meta_q*/Q}] -to [get_pins {status_sync_q*/D}]\n')
    for name,kind in (('diagnostic.cst','file.cst'),('diagnostic.sdc','file.sdc')):
        ET.SubElement(files,'File',path=name,type=kind,enable='1')
    ET.ElementTree(project).write(output/'diagnostic.gprj',encoding='UTF-8',xml_declaration=True)
    script=('set root [file normalize [file dirname [info script]]]\ncd $root\n'
            'open_project diagnostic.gprj\nset_option -top_module hdmi_usb3_diagnostic\n'
            'set_option -output_base_name hdmi_usb3_diagnostic\nset_option -verilog_std sysv2017\n'
            'set_option -use_mspi_as_gpio 1\nset_option -use_cpu_as_gpio 1\n'
            f'set_option -user_code {user_code}\n'
            'set_option -bit_security 0\nset_option -secure_mode 0\nset_option -bit_encrypt 0\n'
            'set_option -bit_compress 0\nset_option -gen_text_timing_rpt 1\nset_option -gen_sdf 1\n'
            'set_option -gen_verilog_sim_netlist 1\nset_option -timing_driven 1\n'
            'set_option -correct_hold_violation 1\nset_option -place_option 2\n'
            'set_option -route_option 0\nrun all\n')
    (output/'run.tcl').write_text(script)
    record=dict(identity='hdmi-usb3-isolation-'+user_code,user_code='0x'+user_code,
        source_policy='eight hash-checked cached HDMI/control inputs; new isolated diagnostic top only',
        preparation_script_sha256=digest(__file__),
        entire_workstation_resynthesized=False,incremental_synthesis_claimed=False,
        diagnostic_subset_synthesized=True,reference_source_manifest_sha256=MANIFEST_SHA,
        reference_physical_inputs_sha256=digest(constraints.parent/'physical_inputs.json'),
        cached_source_sha256={relative:digest(stage/relative) for relative in FILES},
        input_sha256={path.name:digest(path) for path in output.iterdir() if path.is_file()},
        full_workstation=False,ddr_required=False,audio_available=False,usb_host_available=False,
        hdmi_polarity_compensated=True,hotplug_gates_video=False,flash_cs_always_high=True,
        startup_sequence=dict(reference_user_code='0xC11025D2',clock_hz=50000000,
            original_power_reset_preserved=True,restart_after_cycles=25000000,
            restart_hold_cycles=1000000,restart_count=1,registered_reset=True,
            timer_reset_source='power_reset_n; independent of downstream reset_n',
            purpose='startup-only A/B against the historical post-S3 observation; not a proven fix'),
        uart_status_bits=dict(restart_done=5,pixel_activity=4,hpd=3,
                              serializer_reset_released=2,pixel_reset_released=1,clock_ready=0),
        hardware_tested=False,sram_programmed=False,flash_programmed=False,release_ready=False,
        rollback='SRAM reload of C1102515 only; never use this diagnostic for Flash deployment')
    (output/'inputs.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--user-code',required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output,args.user_code),indent=2))
