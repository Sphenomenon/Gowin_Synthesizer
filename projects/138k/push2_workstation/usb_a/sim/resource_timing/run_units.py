#!/usr/bin/env python3
"""Targeted equivalence and bus-transaction tests for measured setup fixes."""
from pathlib import Path
import argparse,json,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'results/resource_rework_final_route0_20261020_041042/Prj1'

def main():
 a=argparse.ArgumentParser();a.add_argument('build',type=Path);args=a.parse_args();project=args.build.resolve()/'Prj1';out=args.build.resolve()/'timing_units';out.mkdir(exist_ok=True)
 tests=[]
 def reference(rel,name):
  p=out/(name+'_reference.sv');p.write_text((BASE/rel).read_text().replace(name,name+'_reference'));return p
 fifo=r'''`timescale 1ns/1ps
module tb;
reg wc=0,rc=0,wrst=0,rrst=0,wv=0,rr=0;reg[31:0] wd=0,ws=32'h91a25463,rs=32'h1273fa39;
always #5 wc=~wc;always #6.51 rc=~rc;
wire ready,readyr,valid,validr;wire[31:0] data,datar;
music_async_fifo #(.WIDTH(32),.ADDRESS_BITS(5)) dut(wc,wrst,wv,ready,wd,rc,rrst,valid,rr,data);
music_async_fifo_reference #(.WIDTH(32),.ADDRESS_BITS(5)) refdut(wc,wrst,wv,readyr,wd,rc,rrst,validr,rr,datar);
integer wcycles=0,popped=0;
always @(negedge wc)if(wrst)begin
 wcycles=wcycles+1;ws={ws[30:0],ws[31]^ws[21]^ws[1]^ws[0]};wv=wcycles<200 || (wcycles<40000 && ws[0]);wd=ws;
end
always @(negedge rc)if(rrst)begin rs={rs[30:0],rs[31]^rs[21]^rs[1]^rs[0]};rr=wcycles>300 && rs[2];end
always @(posedge wc)if(wrst)begin #1;if(ready!==readyr)$fatal(1,"write mismatch");end
always @(posedge rc)if(rrst)begin
 if(valid && rr)popped=popped+1;
 #1;if(valid!==validr || (valid && data!==datar))$fatal(1,"read mismatch");
end
initial begin repeat(6)@(negedge wc);wrst=1;rrst=1;
 repeat(45000)@(negedge wc);if(popped<1000)$fatal(1,"coverage");
 $display("PASS music FIFO cycle equivalence: %0d pops, random stalls/full/empty/wrap",popped);$finish;end
endmodule
'''
 rel='rtl/music/music_async_fifo.sv';tests.append(('music_fifo',[project/rel,reference(rel,'music_async_fifo')],fifo))
 event=r'''`timescale 1ns/1ps
module tb;
reg wc=0,rc=0,rst=1,wv=0,rr=0;reg[17:0] wd=0;reg[31:0] ws=32'h91a25463,rs=32'h1273fa39;
always #10.4167 wc=~wc;always #6.5104 rc=~rc;
wire ready,readyr,valid,validr;wire[17:0] data,datar;
gw138k_usb_event_fifo dut(rst,rc,wd,wv,rr,ready,data,valid,wc);
gw138k_usb_event_fifo_reference refdut(rst,rc,wd,wv,rr,readyr,datar,validr,wc);
integer wcycles=0,popped=0;
always @(negedge wc)if(!rst)begin
 wcycles=wcycles+1;ws={ws[30:0],ws[31]^ws[21]^ws[1]^ws[0]};wv=wcycles<200 || (wcycles<40000 && ws[0]);wd=ws[17:0];
end
always @(negedge rc)if(!rst)begin rs={rs[30:0],rs[31]^rs[21]^rs[1]^rs[0]};rr=wcycles>300 && rs[2];end
always @(posedge wc)if(!rst)begin #1;if(ready!==readyr)$fatal(1,"event write mismatch");end
always @(posedge rc)if(!rst)begin
 if(valid && rr)popped=popped+1;
 #1;if(valid!==validr || (valid && data!==datar))$fatal(1,"event read mismatch");
end
initial begin repeat(6)@(negedge wc);rst=0;
 repeat(20000)@(negedge wc);rst=1;repeat(6)@(negedge wc);rst=0;
 repeat(25000)@(negedge wc);if(popped<1000)$fatal(1,"event coverage");
 $display("PASS event FIFO cycle equivalence: %0d pops, async reset/reconnect, random stalls/full/empty/wrap",popped);$finish;end
endmodule
'''
 rel='src/usb_host/gw138k_usb_event_fifo.v';tests.append(('event_fifo',[project/rel,reference(rel,'gw138k_usb_event_fifo')],event))
 # Exercise the services after the one local predecode edge guaranteed by APB.
 inputs={'clk':'clk','reset_n':'rst','command_valid':'cv','command_write':'cw','command_address':'ca','command_data':'cd','command_strobes':'cs','cpu_event_ready':'er',
 'panel_event_valid':"1'b0",'panel_command':"7'd0",'sample_valid':"1'b0",'record_valid':"1'b1",'record_packet':"96'h12345678_9abcdef0_87654321",'score_running':"1'b0",'score_done':"1'b0"}
 names='control_state control_pitch control_options applied_events pc_health active_mask deadline_miss midi_overflow note_drop underrun_count midi_cdc_drop observation_drop record_drop led_mask score_frame'.split()
 inputs.update({n:"32'h"+format(0x12340000+i*313,'08x') for i,n in enumerate(names)});inputs['held_notes']="128'h12345678_9abcdef0_01234567_89abcdef"
 outputs={'command_ready':1,'response_data':32,'response_error':1,'cpu_event_valid':1,'cpu_event':18,'panel_event_ready':1,'record_enable':1,'snap_status':32,'snap_left':32,'snap_right':32,'snap_sequence':32,'record_ready':1,'score_write':1,'score_start':1,'score_stop':1,'score_address':8,'score_data':64,'score_length':9}
 service_inputs=inputs.copy();service_inputs.update(score_running='score_run',record_valid='rec_valid')
 common=','.join('.'+n+'('+v+')' for n,v in service_inputs.items());bench='''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,cv=0,cw=0,er=1;reg score_run=0,rec_valid=1;reg[11:0]ca=0;reg[31:0]cd=0,rng=32'h3167a9cd;reg[3:0]cs=15;always #6.51 clk=~clk;
'''
 for n,w in outputs.items():bench+=f'wire [{w-1}:0] {n},{n}_r;\n'
 for suffix,module in [('', 'gw138k_controlled_services'),('_r','gw138k_controlled_services_reference')]:bench+=module+' inst'+suffix+'('+common+','+','.join('.'+n+'('+n+suffix+')' for n in outputs)+');\n'
 bench+='task check;begin #1;\n'
 for n in outputs:bench+=f'if({n}!=={n}_r)$fatal(1,"service mismatch {n} addr=%h write=%b got=%h ref=%h",ca,cw,{n},{n}_r);\n'
 bench+='''end endtask
integer tx=0;
task transact(input bit write_cmd,input[11:0]addr,input[31:0]data,input[3:0]strobes);
begin
 @(negedge clk);cv=0;cw=write_cmd;ca=addr;cd=data;cs=strobes;
 // One decode edge precedes command_valid in the modified mailbox.
 @(negedge clk);cv=1;check();@(negedge clk);cv=0;check();tx=tx+1;
end endtask
initial begin repeat(4)@(negedge clk);rst=1;
 transact(1,12'h010,1,15);transact(1,12'h088,1,15);
 for(integer pass=0;pass<3;pass=pass+1)for(integer a=0;a<512;a=a+1)begin
  transact(0,12'(a),0,15);
  rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  transact(1,12'(a),pass==0?32'd1:pass==1?32'd0:rng,pass==2?4'b0101:4'hf);
 end
 // Fill the complete cue store, exercise monotonic rejection, full guard,
 // valid start/stop/clear and record snapshot release/reacquisition.
 transact(1,12'h120,1,15);
 for(integer cue=0;cue<256;cue=cue+1)begin
  transact(1,12'h100,32'(cue),15);transact(1,12'h104,32'(cue*10),15);
  transact(1,12'h108,32'h93a10000^32'(cue),15);transact(1,12'h10c,1,15);
  if(cue==5)begin transact(1,12'h100,6,15);transact(1,12'h104,1,15);transact(1,12'h10c,1,15);end
 end
 if(inst.loaded!==9'd256 || inst_r.loaded!==9'd256)$fatal(1,"cue upload was not exercised");
 transact(1,12'h10c,1,15);transact(0,12'h12c,0,15);
 transact(1,12'h110,256,15);transact(1,12'h114,1,15);transact(1,12'h118,1,15);
 transact(1,12'h098,1,15);transact(1,12'h088,1,15);transact(1,12'h088,1,15);
 @(negedge clk);score_run=1;
 for(integer busy_addr=12'h100;busy_addr<=12'h120;busy_addr=busy_addr+4)
  transact(1,12'(busy_addr),1,15);
 @(negedge clk);score_run=0;rec_valid=0;
 transact(1,12'h098,1,15);transact(1,12'h088,1,15);
 @(negedge clk);rec_valid=1;
 transact(1,12'h088,1,15);transact(1,12'h098,1,15);
 transact(1,12'h120,1,15);transact(1,12'h114,1,15);
 $display("PASS service predecode: %0d reads/writes, every aligned/unaligned address, valid/invalid data/strobes, full 256-cue upload/monotonic rejection/start/stop/clear/busy guards, record valid/empty release/reacquire",tx);$finish;
end
endmodule
'''
 rel='src/ae350/gw138k_controlled_services.sv';tests.append(('services',[project/rel,reference(rel,'gw138k_controlled_services')],bench))
 # End-to-end APB transactions: independent completion latencies must
 # preserve response words/errors and commit each write exactly once.
 apb_ref=reference('src/migration/gw138k_apb_cdc.sv','gw138k_apb_cdc')
 service_ref=out/'gw138k_controlled_services_reference.sv'
 body="""`timescale 1ns/1ps
module bus_fixture #(parameter OLD=0)(input wire pc,ac,rst,sel,en,wr,er,input wire[11:0]addr,input wire[31:0]data,input wire[3:0]strb,
output wire ready,error,output wire[31:0]rdata,output reg[31:0]commits);
wire crst,cv,cw,cr;wire[11:0]ca;wire[31:0]cd,resp;wire[3:0]cs;wire resp_error;
"""
 apb_ports='.reset_n(rst),.pclk(pc),.audio_clk(ac),.psel(sel),.penable(en),.pwrite(wr),.paddr(addr),.pwdata(data),.pstrb(strb),.pready(ready),.pslverr(error),.prdata(rdata),.command_reset_n(crst),.command_valid(cv),.command_ready(cr),.command_write(cw),.command_address(ca),.command_data(cd),.command_strobes(cs),.response_data(resp),.response_error(resp_error)'
 service_inputs=inputs.copy();service_inputs.update(clk='ac',reset_n='crst')
 sp=','.join('.'+n+'('+v+')' for n,v in service_inputs.items())+','+','.join('.'+n+'('+{'command_ready':'cr','response_data':'resp','response_error':'resp_error'}.get(n,'')+')' for n in outputs)
 for old in [0,1]:
  suffix='_reference' if old else ''
  body+=f'generate if(OLD=={old})begin:g{old}\ngw138k_apb_cdc{suffix} bridge({apb_ports});\ngw138k_controlled_services{suffix} services({sp});\nend endgenerate\n'
 body+="""
always @(posedge ac or negedge crst)if(!crst)commits<=0;else if(cv && cr)commits<=commits+1;
endmodule
module tb;
reg pc=0,ac=0,rst=0,s0=0,s1=0,e0=0,e1=0,wr=0,er=0;
reg[11:0]addr=0;reg[31:0]data=0,seed=32'h9813a57b;reg[3:0]strb=15;
always #10.4167 pc=~pc;always #6.5104 ac=~ac;
wire ready0,ready1,error0,error1;wire[31:0]r0,r1,c0,c1;integer ticks=0,tx=0;
always @(negedge ac)begin ticks=ticks+1;er=ticks%9>3;end
bus_fixture #(.OLD(0)) a(pc,ac,rst,s0,e0,wr,er,addr,data,strb,ready0,error0,r0,c0);
bus_fixture #(.OLD(1)) b(pc,ac,rst,s1,e1,wr,er,addr,data,strb,ready1,error1,r1,c1);
task transact(input bit w,input[11:0]a,input[31:0]d,input[3:0]st);
reg done0,done1,err0,err1;reg[31:0]v0,v1;integer waitcycles;
begin
 @(negedge pc);addr=a;data=d;wr=w;strb=st;s0=1;s1=1;e0=0;e1=0;
 @(negedge pc);e0=1;e1=1;done0=0;done1=0;waitcycles=0;
 while(!done0 || !done1)begin
  @(posedge pc);
  if(ready0 && !done0)begin done0=1;v0=r0;err0=error0;end
  if(ready1 && !done1)begin done1=1;v1=r1;err1=error1;end
  @(negedge pc);if(done0)begin s0=0;e0=0;end if(done1)begin s1=0;e1=0;end
  waitcycles=waitcycles+1;if(waitcycles>100)$fatal(1,"APB timeout %h",a);
 end
 if({v0,err0}!=={v1,err1})$fatal(1,"APB result addr=%h write=%b got=%h/%b expected=%h/%b",a,w,v0,err0,v1,err1);
 repeat(2)@(negedge pc);tx=tx+1;if(c0!=tx || c1!=tx)$fatal(1,"duplicate/lost commit %0d %0d expected %0d",c0,c1,tx);
end endtask
initial begin
 repeat(6)@(negedge pc);rst=1;repeat(6)@(negedge pc);
 transact(1,12'h010,1,15);transact(1,12'h088,1,15);
 for(integer a=0;a<512;a=a+1)begin
  transact(0,12'(a),0,15);seed={seed[30:0],seed[31]^seed[21]^seed[1]^seed[0]};
  transact(1,12'(a),a%2==0?32'd1:seed,a%5==0?4'd1:4'hf);
 end
 // Valid CPU event must wait for the asynchronous ready pulses above.
 transact(1,12'h180,{14'd0,4'd2,7'd7,7'd100},15);
 $display("PASS complete APB path: %0d transactions, asynchronous clocks, event backpressure, exactly-once commits, identical words/errors",tx);$finish;
end
initial begin #30000000;$fatal(1,"APB global timeout");end
endmodule
"""
 tests.append(('apb',[project/'src/migration/gw138k_apb_cdc.sv',apb_ref,project/'src/ae350/gw138k_controlled_services.sv',service_ref],body))
 result={}
 for name,sources,tb in tests:
  path=out/(name+'_tb.sv');path.write_text(tb);sources=sources+[path];log=''
  for command in [['iverilog','-g2012','-s','tb','-o',str(out/name)]+list(map(str,sources)),['vvp',str(out/name)]]:
   p=subprocess.run(command,cwd=project,capture_output=True,text=True);log+=p.stdout+p.stderr
   if p.returncode:break
  (out/(name+'.log')).write_text(log);print(log[-1500:]);passed=p.returncode==0 and 'PASS ' in log
  result[name]=dict(passed=passed,source_sha256={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in sources})
  if not passed:break
 (out/'verification.json').write_text(json.dumps(dict(passed=len(result)==len(tests) and all(x['passed'] for x in result.values()),tests=result,hardware_tested=False),indent=2)+'\n')
 if len(result)!=len(tests) or not all(x['passed'] for x in result.values()):raise SystemExit(1)
if __name__=='__main__':main()
