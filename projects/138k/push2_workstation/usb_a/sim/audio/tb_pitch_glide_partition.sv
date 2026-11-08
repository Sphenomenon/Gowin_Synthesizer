`timescale 1ns/1ps
module tb_pitch_partition;
reg clk=0,rst=0,ce=0,rate=0;reg[21:0] target=1048576;reg[15:0] step=0;reg[6:0] depth=0;
wire[21:0] a,b;
workstation_rate_pitch_expression dut(clk,rst,ce,rate,target,step,21'd0,depth,a);
reference_pitch refdut(clk,rst,ce,rate,target,step,depth,b);
integer cases=0,edges=0;reg[31:0] random=32'ha4769e21;reg[15:0] saved_step;reg[7:0] remv;
task check;
begin
 if({a,dut.phase,dut.modulation,dut.glide_ratio,dut.glide_remainder}!=={b,refdut.phase,refdut.modulation,refdut.glide_ratio,refdut.glide_remainder})$fatal(1,"PITCH_STATE cases=%0d edges=%0d",cases,edges);
 if(dut.current_glide_step!==refdut.current_glide_step || dut.next_glide_remainder!==refdut.next_glide_remainder)$fatal(1,"PITCH_FOUR_STATE step=%h rem=%h",step,remv);
end endtask
task reset;
begin clk=0;rst=1;#1;rst=0;#1;check();clk=1;#1;check();clk=0;rst=1;#1;check();end endtask
task next_random;
begin random={random[30:0],random[31]^random[21]^random[1]^random[0]};end endtask
initial begin
 reset();
 for(integer n=0;n<2048;n=n+1)begin
  next_random();saved_step=random[15:0];remv=random[23:16];dut.glide_remainder=remv;refdut.glide_remainder=remv;
  for(integer which=0;which<3;which=which+1)begin
   rate=which==0 ? 1'b0 : which==1 ? 1'b1 : 1'bx;
   for(integer bitn=0;bitn<16;bitn=bitn+1)begin
    step=saved_step;step[bitn]=1'bx;#1;check();cases=cases+1;
    step=saved_step;step[bitn]=1'bz;#1;check();cases=cases+1;
   end
   step=saved_step;
   for(integer bitn=0;bitn<8;bitn=bitn+1)begin
    dut.glide_remainder=remv;refdut.glide_remainder=remv;dut.glide_remainder[bitn]=1'bx;refdut.glide_remainder[bitn]=1'bx;#1;check();cases=cases+1;
    dut.glide_remainder=remv;refdut.glide_remainder=remv;dut.glide_remainder[bitn]=1'bz;refdut.glide_remainder[bitn]=1'bz;#1;check();cases=cases+1;
   end
   dut.glide_remainder=remv;refdut.glide_remainder=remv;
  end
 end
 reset();
 for(integer n=0;n<80000;n=n+1)begin
  next_random();step=random[15:0];target=random[25:4];depth=random[31:25];ce=random[2];rate=random[6];
  if(n%127==0)step[random[19:16]]=1'bx;
  if(n%131==0)step[random[19:16]]=1'bz;
  if(n%137==0)rate=1'bx;
  if(n%139==0)ce=1'bx;
  if(n%149==0)target[random[4:0]%22]=1'bz;
  if(n%151==0)depth[random[2:0]%7]=1'bx;
  #1;check();clk=1;#1;check();edges=edges+1;clk=0;#1;check();edges=edges+1;
  if(n%2048==2047)reset();
 end
 $display("PASS actual_pitch_partition four_state=%0d half_edges=%0d",cases,edges);$finish;
end
endmodule
