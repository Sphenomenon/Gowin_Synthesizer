#!/usr/bin/env python3
"""Independent accepted-event scoreboard for lifecycle bypass and elastic queue."""
from pathlib import Path
import hashlib,json,subprocess,sys
build=Path(sys.argv[1]).resolve();out=build/'lifecycle_scoreboard';out.mkdir(exist_ok=True)
source=build/'Prj1/src/usb_a/gw138k_usb_lifecycle_merge.sv';tb=out/'tb.sv'
tb.write_text('''`timescale 1ns/1ps
module tb;reg c=0,r=0;always #5 c=~c;
reg[2:0]iv=0;wire[2:0]ir;reg[17:0]d0=0,d1=0,d2=0;reg life=0,cancel=0,ready=0;
wire valid;wire[17:0]data;reg[31:0]seed=32'h78316ac5;integer head=0,tail=0,accepted=0,played=0,canceled=0,lifechecks=0;
reg[17:0]expected[0:200000];integer cycle=0;
gw138k_usb_lifecycle_merge #(.EXPLICIT_LIFECYCLE(1)) dut(c,r,iv[0],iv[1],iv[2],d0,d1,d2,life,cancel,ir[0],ir[1],ir[2],valid,data,ready);
always @(posedge c)if(r)begin
 if(iv[0] && life)begin
  if(!valid || data!==d0 || ir[0]!==ready || ir[1] || ir[2])$fatal(1,"lifecycle bypass/CPU backpressure");
  lifechecks=lifechecks+1;
  if(cancel)begin canceled=canceled+(tail-head);head=tail;end
 end else begin
  if(valid && ready)begin
   if(head==tail || data!==expected[head])$fatal(1,"event order/loss/duplication cycle=%0d",cycle);
   head=head+1;played=played+1;
  end
  if(iv[0] && ir[0])begin expected[tail]=d0;tail=tail+1;accepted=accepted+1;end
  if(iv[1] && ir[1])begin expected[tail]=d1;tail=tail+1;accepted=accepted+1;end
  if(iv[2] && ir[2])begin expected[tail]=d2;tail=tail+1;accepted=accepted+1;end
  if(tail-head>2)$fatal(1,"elastic queue overflow");
 end
end
initial begin
 repeat(4)@(negedge c);r=1;
 for(cycle=0;cycle<100000;cycle=cycle+1)begin
  @(negedge c);seed={seed[30:0],seed[31]^seed[21]^seed[1]^seed[0]};
  // Producers hold a normal word until accepted; lifecycle can cancel it.
  if(!iv[0] || ir[0] || life)begin iv[0]=seed[0];d0={2'd0,16'(cycle)};end
  if(!iv[1] || ir[1])begin iv[1]=seed[1];d1={2'd1,16'(cycle)};end
  if(!iv[2] || ir[2])begin iv[2]=seed[2];d2={2'd2,16'(cycle)};end
  ready=seed[3] && cycle%73>19;life=cycle%997<4;cancel=life && cycle%997<2;
  if(life)begin iv[0]=1;d0={4'd15,7'd0,cancel?7'd0:7'd3};end
 end
 @(negedge c);iv=0;life=0;cancel=0;ready=1;repeat(12)@(negedge c);
 if(head!=tail || valid || accepted!=played+canceled || lifechecks<200)$fatal(1,"incomplete event accounting %0d/%0d/%0d",accepted,played,canceled);
 $display("PASS lifecycle scoreboard: %0d accepted, %0d played, %0d canceled, %0d direct lifecycle cycles, three sources/stalls/fair rotation",accepted,played,canceled,lifechecks);$finish;
end
endmodule
''')
log=''
for cmd in (['iverilog','-g2012','-s','tb','-o',str(out/'test'),str(source),str(tb)],['vvp',str(out/'test')]):
 p=subprocess.run(cmd,capture_output=True,text=True);log+=p.stdout+p.stderr
 if p.returncode:break
(out/'run.log').write_text(log);print(log[-2200:]);passed=p.returncode==0 and 'PASS lifecycle scoreboard' in log
(out/'verification.json').write_text(json.dumps(dict(passed=passed,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,tb)},hardware_tested=False),indent=2)+'\n')
if not passed:raise SystemExit(1)
