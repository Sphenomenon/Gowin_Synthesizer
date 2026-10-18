#!/usr/bin/env python3
"""Cycle-exact frozen/new BIST against independent memory, stalls,faults,timeouts."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
from cnn_ddr_pipeline_patch import BIST,retime_bist_expected_pattern
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--build',type=Path);a=p.parse_args()
original=(BASE/BIST).read_text();patched=retime_bist_expected_pattern(original)
if a.build:
 metadata=json.loads((a.build/'build_metadata.json').read_text());assert metadata.get('retimed_bist_expected_pattern')
 assert (a.build/'Prj1'/BIST).read_text()==patched,'BIST frozen source drift'
tb=r"""`timescale 1ns/1ps
module tb;
parameter BURSTS=31,CASE=0;
reg clk=0,rst=0,ready=0,rsp=0;reg [255:0] rdata=0;always #5 clk=~clk;
wire [1:0] valid,write,done,failed;wire [28:0] addr[0:1],first[0:1];wire [255:0] data[0:1];wire [31:0] errors[0:1];
bist_before #(.BURSTS(BURSTS),.TIMEOUT_CYCLES(37)) old(.clk(clk),.rst_n(rst),.req_valid(valid[0]),.req_ready(ready),.req_write(write[0]),.req_addr(addr[0]),.req_wdata(data[0]),.rsp_valid(rsp),.rsp_data(rdata),.done(done[0]),.failed(failed[0]),.error_count(errors[0]),.first_error_addr(first[0]));
ddr3_bist #(.BURSTS(BURSTS),.TIMEOUT_CYCLES(37)) dut(.clk(clk),.rst_n(rst),.req_valid(valid[1]),.req_ready(ready),.req_write(write[1]),.req_addr(addr[1]),.req_wdata(data[1]),.rsp_valid(rsp),.rsp_data(rdata),.done(done[1]),.failed(failed[1]),.error_count(errors[1]),.first_error_addr(first[1]));
reg [255:0] memory[0:BURSTS-1];reg pending=0;reg [255:0] held;
integer cycles=0,wait_cycles=0,read_ordinal=0,compares=0,epochs=0;reg [31:0] random_state=32'h54798ace;
always @(posedge clk)begin
 if(rst)begin
  if(valid[0]!==valid[1] || write[0]!==write[1] || addr[0]!==addr[1] || data[0]!==data[1] || done[0]!==done[1] || failed[0]!==failed[1] || errors[0]!==errors[1] || first[0]!==first[1])$fatal(1,"BIST control/output cycle changed %0d",cycles);
  if(valid[0]&&ready)begin
   if(write[0])memory[addr[0]/8]=data[0];
   else begin
    if(pending)$fatal(1,"more than one read");pending=1;held=memory[addr[0]/8];
    if(CASE==1 && read_ordinal==BURSTS-1)held[255]=!held[255];
    if(CASE==2)held[(read_ordinal%8)*32+(read_ordinal%32)]=!held[(read_ordinal%8)*32+(read_ordinal%32)];
    wait_cycles=(read_ordinal%5);read_ordinal=read_ordinal+1;
   end
  end
  #1;
  if(done[0]!==done[1] || failed[0]!==failed[1] || errors[0]!==errors[1] || first[0]!==first[1])$fatal(1,"BIST post-edge control changed");
  compares=compares+1;
 end
end
initial begin
 for(integer epoch=0;epoch<3;epoch=epoch+1)begin
  @(negedge clk);rst=0;ready=0;rsp=0;pending=0;read_ordinal=0;cycles=0;
  repeat(4)@(negedge clk);rst=1;epochs=epochs+1;
  while(!done[0] && cycles<100000)begin
   @(negedge clk);cycles=cycles+1;
   random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
   ready=CASE==3 ? 0 : (random_state[0]|random_state[1]);rsp=0;
   if(pending)begin
    if(wait_cycles==0 && CASE!=4)begin rsp=1;rdata=held;pending=0;end
    else if(wait_cycles>0)wait_cycles=wait_cycles-1;
   end
  end
  if(!done[0])$fatal(1,"BIST did not finish");
  if(CASE==0 && (failed[0] || errors[0]!=0))$fatal(1,"clean pattern rejected");
  if(CASE==1 && (!failed[0] || errors[0]!=1 || first[0]!=(BURSTS-1)*8))$fatal(1,"final-bit fault not accounted before done");
  if(CASE==2 && (!failed[0] || errors[0]!=2*BURSTS))$fatal(1,"all lanes fault count mismatch");
  if(CASE>=3 && (!failed[0] || errors[0]!=1))$fatal(1,"timeout fault missing");
 end
 $display("PASS frozen/newBIST bursts=%0d case=%0d cycleexact%0d,3resetepochs,maskedfaultlanes/finalbit/readandwritetimeouts/native stalls",BURSTS,CASE,compares);$finish;
end
endmodule"""
checks=[]
with tempfile.TemporaryDirectory(prefix='cnn_bist_expected_') as temp:
 folder=Path(temp);(folder/'old.v').write_text(original.replace('module ddr3_bist #','module bist_before #'));(folder/'new.v').write_text(patched);(folder/'tb.sv').write_text(tb)
 for bursts in (1,31,257):
  for case in range(5):
   c=subprocess.run(['iverilog','-g2012','-I',str(BASE),'-s','tb','-P',f'tb.BURSTS={bursts}','-P',f'tb.CASE={case}','-o',str(folder/'sim'),str(folder/'old.v'),str(folder/'new.v'),str(folder/'tb.sv')],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
   r=subprocess.run(['vvp',str(folder/'sim')],capture_output=True,text=True,timeout=30);assert r.returncode==0 and 'PASS frozen/newBIST' in r.stdout,r.stdout+r.stderr
   checks.append(dict(bursts=bursts,case=case,passed=True,log=r.stdout.strip()))
result=dict(passed=True,source_bound=bool(a.build),build=str(a.build) if a.build else None,hardware_tested=False,pcm_saved=False,bsram_added=0,added_cycles=0,checks=checks,original_sha256=hashlib.sha256(original.encode()).hexdigest(),patched_sha256=hashlib.sha256(patched.encode()).hexdigest())
if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
