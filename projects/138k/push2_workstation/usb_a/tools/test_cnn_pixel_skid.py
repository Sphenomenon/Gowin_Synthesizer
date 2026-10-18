#!/usr/bin/env python3
"""Independent sequence/stall/reset/completion checks for the two-beat pixel skid."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--source',type=Path,default=ROOT/'src/video/feedback_pixel_skid.v');args=p.parse_args()
tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,valid=0,ready=0,done=0;always #5 clk=~clk;
wire in_ready,out_valid,out_done;wire [63:0] out_data;
integer accepted=0,returned=0,seed,epochs=0,checks=0,done_count=0;
reg [31:0] random_state=7;reg stalled=0;reg [63:0] prior,input_data=0;
function [63:0] item(input integer n);
 item={32'h3f5a91e7^(n*32'h80704031),32'haf0383c5^(n*32'h1d009e77)};
endfunction
feedback_pixel_skid dut(.clk(clk),.rst_n(rst),.source_valid(valid),.source_ready(in_ready),
 .source_data(input_data),.source_done(done),.sink_valid(out_valid),.sink_ready(ready),
 .sink_data(out_data),.sink_done(out_done));
always @(posedge clk)if(rst)begin
 if(stalled && (!out_valid || out_data!==prior))$fatal(1,"held output changed under stall");
 stalled=out_valid&&!ready;prior=out_data;
 if(out_valid&&ready)begin
  if(out_data!==item(returned))$fatal(1,"sequence/data mismatch %0d",returned);
  returned=returned+1;
 end
 if(valid&&in_ready)accepted=accepted+1;
 #1;
 if(returned>accepted || accepted-returned>2)$fatal(1,"lost/overflow");
 if(in_ready!==(accepted-returned<2))$fatal(1,"ready not exact registered occupancy");
 if(out_done)begin
  if(accepted!=returned || out_valid)$fatal(1,"completion before pixel drain");
  done_count=done_count+1;
 end
 checks=checks+1;
end
initial begin
 if(!$value$plusargs("SEED=%d",seed))seed=7;random_state=seed;
 for(integer cycle=0;cycle<100000;cycle=cycle+1)begin
  @(negedge clk);
  if(cycle%4096==0)begin rst=0;valid=0;ready=0;done=0;accepted=0;returned=0;stalled=0;epochs=epochs+1;end
  else begin
   rst=1;random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
   valid=random_state[1]|random_state[0];ready=(cycle%4096>=257)&&(random_state[5]|random_state[4]);
  end
  input_data=item(accepted);
 end
 @(negedge clk);valid=0;ready=1;done=1;
 @(negedge clk);done=0;
 repeat(8)@(negedge clk);
 if(accepted!=returned || done_count!=1)$fatal(1,"final drain/completion mismatch");
 $display("PASS pixel skid seed=%0d cycles=%0d resetepochs=%0d sequence64bits,longstalls,full,pop/push,completion after drain",seed,checks,epochs);$finish;
end
endmodule'''
checks=[]
with tempfile.TemporaryDirectory(prefix='cnn_pixel_skid_') as temp:
 folder=Path(temp);(folder/'tb.sv').write_text(tb)
 r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(folder/'sim'),str(folder/'tb.sv'),str(args.source)],capture_output=True,text=True)
 assert r.returncode==0,r.stdout+r.stderr
 for seed in (7,31,127):
  r=subprocess.run(['vvp',str(folder/'sim'),f'+SEED={seed}'],capture_output=True,text=True,timeout=60)
  assert r.returncode==0 and 'PASS pixel skid' in r.stdout,r.stdout+r.stderr
  checks.append(dict(seed=seed,passed=True,log=r.stdout.strip()))
result=dict(passed=True,hardware_tested=False,pcm_saved=False,bsram_added=0,
 source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),checks=checks)
if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
