#!/usr/bin/env python3
"""Independent async FIFO scoreboard including flush marker, stalls and reset."""
from pathlib import Path
import argparse,subprocess,tempfile,json
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
tb=r'''
`timescale 1ns/1ps
module tb;
parameter BITS=9;
reg wc=0,rc=0,rst=0,wv=0,rr=0;reg [64:0] wd=0;
always #7 wc=~wc;always #5 rc=~rc;
wire wr,rv;wire [64:0] rd;
basic_pitch_ddr_sync_fifo #(.ADDRESS_BITS(BITS)) dut(wc,rst,wv,wr,wd,rc,rst,rv,rr,rd);
reg [64:0] expected[0:50000];integer wi=0,ri=0;reg [64:0] held;reg stalled=0;
always @(posedge wc)if(rst && wv && wr)begin expected[wi]=wd;wi=wi+1;end
always @(posedge rc)if(rst)begin
 if(stalled && (!rv || rd!==held))$fatal(1,"output changed under backpressure");
 stalled=rv && !rr;held=rd;
 if(rv && rr)begin if(ri>=wi || rd!==expected[ri])$fatal(1,"FIFO order/data failure at%0d",ri);ri=ri+1;end
end else stalled=0;
task reset;
 begin rst=0;wv=0;rr=0;repeat(6)@(negedge wc);wi=0;ri=0;rst=1;end
endtask
initial begin
 reset();
 // Full RAM plus one prefetched output slot; no output consumption.
 for(integer k=0;k<(1<<BITS)+20;k=k+1)begin @(negedge wc);wv=1;wd=k;end
 @(negedge wc);wv=0;
 repeat(40)@(negedge rc);if(wr || !rv)$fatal(1,"FIFO did not reach full");
 rr=1;repeat((1<<BITS)*4+100)@(negedge rc);if(ri!=wi)$fatal(1,"full FIFO did not drain");
 for(integer k=0;k<12000;k=k+1)begin
  @(negedge wc);wv=k%13>2;wd={(k%211==0),32'(k),32'(k^32'ha53ce701)};
  rr=k%137<91;
 end
 @(negedge wc);wv=0;rr=1;repeat((1<<BITS)*4+200)@(negedge rc);
 if(wi!=ri || wi<3000)$fatal(1,"random FIFO drain failed %0d/%0d",ri,wi);
 // Flush marker is ordinary bit64 and must retain its position in the stream.
 $display("PASS synchronous DDR FIFO bits=%0d commits=%0d,full/empty/wrap,output stalls,65-bit markers,independent clocks",BITS,wi);
 @(negedge wc);wv=1;wd=65'h10000000000000000;rr=0;repeat(20)@(negedge wc);reset();
 repeat(30)@(negedge rc);if(rv)$fatal(1,"reset retained data");
 @(negedge wc);wv=1;wd=65'h123456789abcdef00;@(negedge wc);wv=0;rr=1;repeat(50)@(negedge rc);
 if(wi!=1 || ri!=1)$fatal(1,"post reset stream failed");$finish;
end
endmodule
'''
cases=[]
with tempfile.TemporaryDirectory(prefix='cnn_ddr_sync_fifo_') as tmp:
 t=Path(tmp)/'tb.sv';t.write_text(tb)
 for bits in [2,4,9]:
  exe=Path(tmp)/'sim';c=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.BITS={bits}','-o',str(exe),str(t),str(ROOT/'rtl/music/basic_pitch_ddr_sync_fifo.sv')],capture_output=True,text=True)
  assert c.returncode==0,c.stdout+c.stderr
  v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=20);assert v.returncode==0 and 'PASS synchronous' in v.stdout,v.stdout+v.stderr
  cases.append(dict(address_bits=bits,passed=True,log=v.stdout.strip()))
r=dict(passed=True,cases=cases,hardware_tested=False,pcm_saved=False)
if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
