#!/usr/bin/env python3
"""Cycle compare complete event workstations while exercising existing scenarios."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
build=Path(sys.argv[1]).resolve();stage=build/'Prj1';out=build/'dispatch_ab';out.mkdir(exist_ok=True)
old=ROOT/'results/resource_rework_final_route0_20261020_041042/Prj1/src/ae350/gw138k_event_workstation.sv'
ref=out/'gw138k_event_workstation_reference.sv'
ref.write_text(old.read_text().replace('module gw138k_event_workstation','module gw138k_event_workstation_reference',1))
source_bench=ROOT/'sim/scope_vec/tb_scope_workstation.sv';text=source_bench.read_text()
start=text.index('    gw138k_event_workstation #');end=text.index('));',start)+3
instance=text[start:end]
outputs=['cpu_ready','valid','synth_valid','clip','left','right','synth','active','deadline','overflow','dropped','scope_status','tf_control','count','effects','epoch']
reference_instance=instance.replace('gw138k_event_workstation #','gw138k_event_workstation_reference #',1).replace(' dut(',' reference_dut(',1)
for name in outputs:reference_instance=re.sub(r'\('+name+r'\)', '('+name+'_ref)',reference_instance)
declarations='''
    wire cpu_ready_ref,valid_ref,synth_valid_ref,clip_ref;
    wire signed [31:0] left_ref,right_ref,synth_ref;
    wire [31:0] active_ref,deadline_ref,overflow_ref,dropped_ref,scope_status_ref,tf_control_ref;
    wire [5:0] count_ref;wire [2:0]effects_ref;wire [9:0]epoch_ref;
    integer compared=0;
'''
joined=','.join(outputs);reference_joined=','.join(x+'_ref' for x in outputs)
checks=f'''
    always @(negedge clk) begin
      #1;
      if(rst_n)begin
        compared=compared+1;
        if({{{joined}}}!=={{{reference_joined}}})$fatal(1,"dispatch output mismatch cycle %0d",compared);
        if({{dut.dispatch,dut.event_ready,dut.core_ce,dut.event_valid,dut.event_data}}!==
           {{reference_dut.dispatch,reference_dut.event_ready,reference_dut.core_ce,reference_dut.event_valid,reference_dut.event_data}})
          $fatal(1,"dispatch internal handshake mismatch %0d",compared);
      end
    end
'''
text=text[:end]+declarations+reference_instance+checks+text[end:]
text=text.replace('$finish;', '$display("PASS dispatch cycle AB: %0d cycles, outputs and handshake exact",compared);$finish;')
bench=out/'tb.sv';bench.write_text(text)
sources=[stage/f.get('path') for f in ET.parse(stage/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
exclude=['vendor/','src/memory/','src/storage/','src/platform/','src/top/','src/usb_a/','rtl/music/','src/ae350/riscv_','workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v']
inputs=[p for p in sources if not any(x in p.relative_to(stage).as_posix() for x in exclude)]
inputs += [stage/'rtl/music/music_async_fifo.sv']+[p for p in sources if p.name=='gw138k_usb_lifecycle_merge.sv']+[ref,bench]
inputs=list(dict.fromkeys(inputs));hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
binary=out/'obj/Vtb_scope_workstation';passed=False
commands=[['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_scope_workstation','--Mdir',str(binary.parent),'-I'+str(stage),*map(str,inputs)],[str(binary)]]
for label,command in zip(('compile','run'),commands):
 with (out/(label+'.log')).open('w') as log:p=subprocess.run(command,cwd=stage,stdout=log,stderr=subprocess.STDOUT)
 if p.returncode:break
log=(out/(label+'.log')).read_text();passed=p.returncode==0 and 'PASS dispatch cycle AB:' in log
passed=passed and all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
(out/'verification.json').write_text(json.dumps(dict(passed=passed,source_sha256=hashes,hardware_tested=False),indent=2)+'\n')
print(log[-3500:])
if not passed:raise SystemExit(1)
