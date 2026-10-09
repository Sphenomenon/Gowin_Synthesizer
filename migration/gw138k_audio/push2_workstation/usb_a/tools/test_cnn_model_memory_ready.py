#!/usr/bin/env python3
"""Test actual local model calibration wrapper against its one-edge contract."""
from pathlib import Path
import argparse,tempfile,subprocess,json,hashlib,re
from cnn_ddr_pipeline_patch import retime_model_memory_ready,MODEL_MEMORY_READY_BLOCK
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);args=p.parse_args()
link=retime_model_memory_ready((BASE/'rtl/music/basic_pitch_workstation_link.sv').read_text())
expr=re.search(r'\.req_valid_i\((ddr_cmd_valid && model_memory_ready &&\s*\([^)]*\))\)',link)[1].replace('ddr_rsp_fifo_ready','ddr_read_credit')
tb='''`timescale 1ns/1ps
module tb;
reg memory_clk=0,memory_reset_n=0,memory_calibrated=0,ddr_cmd_valid=0,ddr_read_credit=0;
reg [48:0] ddr_cmd_data=0;reg expected=0;reg [31:0] random_state=32'hf7644a3b;integer checked=0;
always #5 memory_clk=~memory_clk;
'''+MODEL_MEMORY_READY_BLOCK+'wire request='+expr+''';
always @(negedge memory_reset_n)expected=0;
always @(posedge memory_clk)begin
 expected=memory_reset_n && memory_calibrated;
 #1;if(model_memory_ready!==expected)$fatal(1,"local calibration capture mismatch");
 if(request!==(ddr_cmd_valid && expected && (ddr_cmd_data[48] || ddr_read_credit)))$fatal(1,"write bypass/read credit changed");checked=checked+1;
end
initial begin
 repeat(5)@(negedge memory_clk);memory_reset_n=1;
 // No model can arrive until boot-readyCPU/BIST/UI. Normal calibration is
 // already stable; then cover adversarial level edges and memory resets.
 repeat(3)@(negedge memory_clk);memory_calibrated=1;
 repeat(3)@(negedge memory_clk);ddr_cmd_valid=1;ddr_cmd_data[48]=1;
 for(integer i=0;i<100000;i=i+1)begin
  @(negedge memory_clk);random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
  memory_calibrated=random_state[0];ddr_cmd_valid=random_state[1];ddr_cmd_data[48]=random_state[2];ddr_read_credit=random_state[3];
  if(i%811==0)begin #2;memory_reset_n=0;#1;if(model_memory_ready!==0 || request!==0)$fatal(1,"asynchronous reset did not inhibit request");#1;memory_reset_n=1;end
 end
 $display("PASS localcalibration100000level/write/readcredit combinations andasynchronousreset,one-memory-edge contract");$finish;
end
endmodule'''
with tempfile.TemporaryDirectory(prefix='cnn_local_memory_ready_') as temp:
 folder=Path(temp);(folder/'tb.sv').write_text(tb);exe=folder/'sim'
 c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(exe),str(folder/'tb.sv')],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
 v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30);assert v.returncode==0 and 'PASS localcalibration' in v.stdout,v.stdout+v.stderr
 result=dict(passed=True,hardware_tested=False,pcm_saved=False,scope='actual calibration wrapper/request expression; one memory-clock startup/level delay, global memory reset immediate; not DDR-PHY recovery proof',link_sha256=hashlib.sha256(link.encode()).hexdigest(),wrapper_sha256=hashlib.sha256(MODEL_MEMORY_READY_BLOCK.encode()).hexdigest(),log=v.stdout.strip())
 if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
