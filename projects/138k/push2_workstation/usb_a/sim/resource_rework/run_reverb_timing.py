#!/usr/bin/env python3
"""Isolated GW5A implementation of the new reverb at the real 76.8-MHz target."""
from pathlib import Path
import subprocess,json,hashlib,xml.etree.ElementTree as ET,re,sys
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/resource_reverb_timing'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 files=['rtl/memory/workstation_sdp.sv','rtl/memory/workstation_sdp_banked.sv','rtl/audio/serial_spatial_reverb.sv','rtl/audio/spatial_room_preset.svh']
 for path in files:
  dest=OUT/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/path).read_bytes())
 pkg=ROOT/'results/timing_p27_uart_cdc_route1_20261018_142516_456857/Prj1/legacy/rtl/audio/audio_math_pkg.sv'
 (OUT/'rtl/audio/audio_math_pkg.sv').write_bytes(pkg.read_bytes())
 tree=ET.parse(ROOT/'out/resource_sdp_probe_20261020/probe.gprj');fl=tree.find('FileList');fl.clear()
 for path in ['rtl/audio/audio_math_pkg.sv']+[p for p in files if p.endswith('.sv')]:ET.SubElement(fl,'File',path=path,type='file.verilog',enable='1')
 ET.SubElement(fl,'File',path='target.sdc',type='file.sdc',enable='1');tree.write(OUT/'reverb.gprj',encoding='UTF-8',xml_declaration=True)
 (OUT/'target.sdc').write_text('create_clock -name audio_76m8 -period 13.020833 [get_ports {clk_i}]\n')
 (OUT/'build.tcl').write_text('''open_project reverb.gprj
set_option -top_module serial_spatial_reverb
set_option -output_base_name reverb
set_option -verilog_std sysv2017
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -timing_driven 1
set_option -correct_hold_violation 1
set_option -route_option 0
set_option -gen_text_timing_rpt 1
set_option -gen_verilog_sim_netlist 1
run all
''')
 with (OUT/'gowin.log').open('w') as log:p=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'build.tcl'],cwd=OUT,stdout=log,stderr=subprocess.STDOUT)
 text=(OUT/'gowin.log').read_text();passed=p.returncode==0 and not re.search(r'^ERROR',text,re.M)
 result=dict(tool_passed=passed,exit_code=p.returncode,full_workstation=False,hardware_tested=False,target_mhz=76.8)
 rpt=OUT/'impl/pnr/reverb.rpt.txt'
 if rpt.exists():
  m=re.search(r'\bBSRAM\s*\|\s*(\d+)/340',rpt.read_text());result['physical_bsram']=int(m[1]) if m else None
 tr=OUT/'impl/pnr/reverb_tr_content.html'
 if tr.exists():
  sys.path.insert(0,str(ROOT/'tools'));from audit_clk50_timing import TimingTables
  parser=TimingTables();parser.feed(tr.read_text());result['frequency_rows']=[r for cmd,rows in parser.tables if rows and 'Actual Fmax' in rows[0] for r in rows[1:]]
 result['input_sha256']={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='summary.json' and 'impl' not in p.relative_to(OUT).parts and p.name!='gowin.log'}
 (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(ROOT/'reports/resource_rework_20261020/reverb_isolated_timing.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 if not passed:raise SystemExit(1)
if __name__=='__main__':main()
