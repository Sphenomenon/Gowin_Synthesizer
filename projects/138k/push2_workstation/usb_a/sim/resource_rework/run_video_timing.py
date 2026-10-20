#!/usr/bin/env python3
"""Isolated implementation of the repacked dual-clock video line store."""
from pathlib import Path
import subprocess,json,hashlib,xml.etree.ElementTree as ET,re,sys
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/resource_video_timing'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 files=['rtl/memory/workstation_sdp.sv','rtl/display_data/video_ddr_scanout.v']
 for path in files:
  dest=OUT/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/path).read_bytes())
 inc=OUT/'src/memory/ddr_address_map.vh';inc.parent.mkdir(parents=True,exist_ok=True)
 inc.write_bytes((ROOT/'results/timing_p27_uart_cdc_route1_20261018_142516_456857/Prj1/src/memory/ddr_address_map.vh').read_bytes())
 header=(ROOT/'rtl/display_data/video_ddr_scanout.v').read_text().split('    localparam integer LINE_BEATS')[0]
 header=header.replace('module video_ddr_scanout #(', 'module video_timing_probe #(').replace('input wire [255:0] rsp_data', 'input wire [31:0] rsp_data')
 ports='clk rst_n enabled new_frame_pending new_frame_base new_composite new_analysis_base frame_swap front_bank front_valid req_valid req_ready req_addr rsp_valid fetch_fault underruns pixel_clk pixel_rst_n pixel_x pixel_y data_enable hsync vsync vblank_start rgb out_de out_hsync out_vsync'.split()
 wrapper=header+"    reg [255:0] response_data;\n    always @(posedge clk) response_data <= {response_data[223:0],rsp_data};\n    video_ddr_scanout #(.EXPLICIT_BASE(1)) dut("+','.join('.'+v+'('+v+')' for v in ports)+",.rsp_data(response_data));\nendmodule\n"
 (OUT/'video_timing_probe.v').write_text(wrapper)
 files.append('video_timing_probe.v')
 tree=ET.parse(ROOT/'out/resource_sdp_probe_20261020/probe.gprj');fl=tree.find('FileList');fl.clear()
 for path in files:ET.SubElement(fl,'File',path=path,type='file.verilog',enable='1')
 ET.SubElement(fl,'File',path='target.sdc',type='file.sdc',enable='1');tree.write(OUT/'video.gprj',encoding='UTF-8',xml_declaration=True)
 (OUT/'target.sdc').write_text('create_clock -name memory_100 -period 10 [get_ports {clk}]\ncreate_clock -name pixel_148m5 -period 6.734007 [get_ports {pixel_clk}]\nset_clock_groups -asynchronous -group {memory_100} -group {pixel_148m5}\n')
 (OUT/'build.tcl').write_text('''open_project video.gprj
set_option -top_module video_timing_probe
set_option -output_base_name video
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
 result=dict(tool_passed=passed,exit_code=p.returncode,full_workstation=False,hardware_tested=False,target_pixel_mhz=148.5,target_memory_mhz=100)
 rpt=OUT/'impl/pnr/video.rpt.txt'
 if rpt.exists():
  m=re.search(r'\bBSRAM\s*\|\s*(\d+)/340',rpt.read_text());result['physical_bsram']=int(m[1]) if m else None
 tr=OUT/'impl/pnr/video_tr_content.html'
 if tr.exists():
  sys.path.insert(0,str(ROOT/'tools'));from audit_clk50_timing import TimingTables
  parser=TimingTables();parser.feed(tr.read_text());result['frequency_rows']=[r for cmd,rows in parser.tables if rows and 'Actual Fmax' in rows[0] for r in rows[1:]]
 result['input_sha256']={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='summary.json' and 'impl' not in p.relative_to(OUT).parts and p.name!='gowin.log'}
 (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(ROOT/'reports/resource_rework_20261020/video_isolated_timing.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 if not passed:raise SystemExit(1)
if __name__=='__main__':main()
