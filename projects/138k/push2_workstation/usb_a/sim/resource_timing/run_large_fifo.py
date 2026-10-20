#!/usr/bin/env python3
"""Independent dual-clock scoreboard for the complete 65-bit delay FIFO."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
build=Path(sys.argv[1]).resolve();out=build/'large_fifo';out.mkdir(exist_ok=True)
source=build/'Prj1/rtl/music/music_async_fifo.sv';bench=out/'tb.sv'
bench.write_text('''`timescale 1ns/1ps
module tb;
parameter integer AB=9;localparam integer DEPTH=1<<AB;
reg wc=0,rc=0,rst=0,wv=0,rr=0,random_mode=0;reg [31:0]ws=32'h1927ab03,rs=32'hf4c1a0b3;
always #5 wc=~wc;always #7.3 rc=~rc;
wire ready,valid;wire [64:0]data;integer wi=0,ri=0,total=0,epoch=0;
wire [64:0]sent={1'(wi%19==0),32'(epoch),32'(wi^32'h9a5f3321)};
reg [64:0] oracle[0:300000];
music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(AB)) dut(wc,rst,wv,ready,sent,rc,rst,valid,rr,data);
always @(posedge wc or negedge rst)begin
 if(!rst)wi=0;
 else if(wv && ready)begin oracle[wi]=sent;wi=wi+1;end
end
always @(posedge rc or negedge rst)begin
 if(!rst)ri=0;
 else if(valid && rr)begin
  if(ri>=wi)$fatal(1,"read beyond committed items %0d/%0d",ri,wi);
  if(data!==oracle[ri])$fatal(1,"item mismatch index %0d got=%h expected=%h",ri,data,oracle[ri]);
  ri=ri+1;total=total+1;
 end
end
always @(negedge wc)if(random_mode)begin ws={ws[30:0],ws[31]^ws[21]^ws[1]^ws[0]};wv=ws[2:0]!=0;end
always @(negedge rc)if(random_mode)begin rs={rs[30:0],rs[31]^rs[21]^rs[1]^rs[0]};rr=rs[1:0]!=0;end
task restart;
begin rst=0;wv=0;rr=0;random_mode=0;epoch=epoch+1;repeat(6)@(negedge wc);rst=1;end
endtask
task drain;
integer budget;
begin
 random_mode=0;@(negedge wc);wv=0;@(negedge rc);rr=1;budget=0;
 while(ri!=wi)begin @(negedge rc);budget=budget+1;if(budget>DEPTH+100)$fatal(1,"drain timeout");end
 repeat(12)@(negedge rc);if(valid)$fatal(1,"must be empty after drain");rr=0;
end endtask
initial begin
 restart;
 // Verify complete capacity, all-zero/all-one marker/data combinations and wrap.
 for(integer round=0;round<4;round=round+1)begin
  @(negedge wc);wv=1;rr=0;
  repeat(DEPTH+20)@(negedge wc);
  if(wi-ri!=DEPTH || ready)$fatal(1,"capacity reduced or overflow %0d/%0d",wi-ri,DEPTH);
  wv=0;drain;
 end
 random_mode=1;repeat(60000)@(negedge wc);drain;
 random_mode=1;repeat(5000)@(negedge wc);restart;
 random_mode=1;repeat(60000)@(negedge wc);drain;
 $display("PASS large FIFO: AB=%0d capacity=%0d, %0d checked transfers, dual clocks, stalls, full wraps and reset",AB,DEPTH,total);$finish;
end
initial begin #10000000;$fatal(1,"timeout");end
endmodule
''')
results=[]
for ab in (8,9):
 log='';passed=False
 for cmd in (['iverilog','-g2012','-s','tb',f'-Ptb.AB={ab}','-o',str(out/f'test{ab}'),str(source),str(bench)],['vvp',str(out/f'test{ab}')]):
  p=subprocess.run(cmd,capture_output=True,text=True);log+=p.stdout+p.stderr
  if p.returncode:break
 passed=p.returncode==0 and 'PASS large FIFO:' in log
 (out/f'run{ab}.log').write_text(log);print(log[-1500:]);results.append(dict(address_bits=ab,passed=passed))
 if not passed:break
result=dict(passed=len(results)==2 and all(p['passed'] for p in results),cases=results,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,bench)},hardware_tested=False)
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['passed']:raise SystemExit(1)
