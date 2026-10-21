#!/usr/bin/env python3
"""Verify the exact staged UART trace patch and its two-cycle level receiver."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
from workstation_cnn_cdc import transform,LINK
from workstation_sources import verify_cnn_inputs
from workstation_baselines import load_baseline
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('build',type=Path);a=p.parse_args();build=a.build.resolve();stage=build/'Prj1'
source=stage/LINK;baseline=load_baseline(ROOT,'timing85');fixed=baseline.read_bytes(LINK)
assert source.read_text()==transform(fixed.decode()),'patch exceeds exact diagnostic substitution'
meta=json.loads((build/'build_metadata.json').read_text());verify_cnn_inputs(stage,meta['music_sha256'])
text=source.read_text();start=text.index('    // UART samples levels, not event counts.');end=text.index('    wire [10:0] tf_trace',start);snippet=text[start:end]
assert "model_status,ddr_trace_sync[0],1'b1};" in text
assert "model_status,memory_calibrated,1'b1};" not in text
sd_start=text.index('    wire [31:0] sd_report =')
sd_end=text.index('    basic_pitch_link_uart u_report',sd_start)
status_snippet=text[sd_start:sd_end]
out=build/datetime.now().strftime('cnn_trace_cdc_%Y%m%d_%H%M%S_%f');out.mkdir(exist_ok=False)
bench='''`timescale 1ns/1ps
module tb;
reg clk_50m=0,reset_n=0;always #10 clk_50m=~clk_50m;
reg[6:0] raw=0;
reg bp_mem_req=0,bp_mem_ready=0,ddr_rsp_fifo_valid=0;
wire memory_reset_n=raw[1],memory_calibrated=raw[0];
wire ddr_cmd_valid=raw[6],ddr_cmd_ready=raw[5],ddr_req=raw[4],ddr_ready=raw[3],ddr_rsp_valid=raw[2];
reg [7:0] score_count=0;reg [6:0] score_first=0,score_last=0;
reg [1:0] model_error_stage=0;reg [3:0] model_status=0;
'''+snippet+status_snippet+'''
reg[6:0] expected_meta=0,expected_sync=0;
integer samples=0;integer i;
always @(posedge clk_50m or negedge reset_n)
 if(!reset_n)begin expected_meta<=0;expected_sync<=0;end
 else begin expected_meta<=raw;expected_sync<=expected_meta;end
always @(negedge clk_50m)begin
 #1;
 if(ddr_trace_sync!==expected_sync)$fatal(1,"trace two-cycle mismatch");
 if(model_path_trace!=={bp_mem_req,bp_mem_ready,expected_sync[6:2],ddr_rsp_fifo_valid,expected_sync[1:0]})
  $fatal(1,"UART bit layout changed");
 if(sd_report!=={score_count,score_first,score_last,2'd0,model_error_stage,model_status,expected_sync[0],1'b1})
  $fatal(1,"UART calibration status or unrelated fields changed");
 samples++;
end
initial begin
 // Offset the stimulus from clock edges; delta-cycle races do not model CDC.
 repeat(3)@(negedge clk_50m);#1.25;reset_n=1;
 for(i=0;i<2048;i++)begin
  #13;raw=7'(i*17+i/32);bp_mem_req=i%2;bp_mem_ready=i%3==0;
  ddr_rsp_fifo_valid=i%5==0;
  score_count=8'(i*19);score_first=7'(i*5);score_last=7'(i*13);model_status=4'(i/7);model_error_stage=2'(i/11);
 end
 #3;reset_n=0;#2;if(ddr_trace_sync!==0)$fatal(1,"asynchronous reset failed");
 #18;reset_n=1;repeat(4)@(negedge clk_50m);
 $display("PASS cnn_trace_cdc: %0d clock checks, all128 level patterns, unrelated phases, exact UART bit positions, reset",samples);
 $finish;
end
endmodule
'''
(out/'tb.sv').write_text(bench);inputs=[source,baseline.manifest,stage/'rtl/timing/gw138k_level_cdc.sv',Path(__file__).resolve(),ROOT/'tools/workstation_cnn_cdc.py',out/'tb.sv']
hashes={str(x):sha(x) for x in inputs}
subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'simv'),str(stage/'rtl/timing/gw138k_level_cdc.sv'),str(out/'tb.sv')],check=True)
r=subprocess.run(['vvp',str(out/'simv')],text=True,capture_output=True,check=True);assert 'PASS cnn_trace_cdc:' in r.stdout
assert hashes=={str(x):sha(x) for x in inputs}
assert fixed==load_baseline(ROOT,'timing85').read_bytes(LINK)
(out/'verification.json').write_text(json.dumps(dict(passed=True,source_bound=True,hardware_tested=False,log=r.stdout),indent=2)+'\n');(out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n');print(r.stdout)
