`timescale 1ns/1ps
module tb_controls;
 reg clk=0,rst=1,connected=1,v=0,er=1;always #10 clk=~clk;
 reg[3:0]k=0,cable=0,ch=0;reg[6:0]a=0,b=0;wire ready,ev;wire[17:0]ed;wire[63:0]held;wire[6:0]note,vel;wire[31:0]mapped,ignored;
 push2_controls dut(clk,rst,connected,v,ready,k,cable,ch,a,b,32'h64000010,32'h02000000,ev,er,ed,held,note,vel,mapped,ignored);
 reg[17:0]expected[0:511];integer wp=0,rp=0;
 always @(posedge clk)if(ev&&er)begin
  if(rp>=wp || ed!==expected[rp])$fatal(1,"mapping %d got %h expected %h",rp,ed,expected[rp]);rp=rp+1;
 end
 task send(input[3:0]kind,input[6:0]aa,bb,input integer output_expected,input[17:0]out);
  begin
   if(output_expected)begin expected[wp]=out;wp=wp+1;end
   @(negedge clk);k=kind;a=aa;b=bb;v=1;do @(posedge clk);while(!ready);@(negedge clk);v=0;
  end
 endtask
 initial begin
  #100;rst=0;
  for(integer n=36;n<100;n=n+1)begin
   send(9,7'(n),100,1,{4'd1,7'(n),7'd100});
   send(9,7'(n),100,0,0); // a repeated held press never retriggers
   send(8,7'(n),0,1,{4'd0,7'(n),7'd0});
  end
  for(integer n=0;n<12;n=n+1)send(9,7'(n),127,0,0); // encoder touch is not a musical note
  send(14,1,65,1,{4'd4,7'd1,7'd65});send(8,12,0,1,{4'd4,7'd0,7'd64});
  for(integer n=102;n<105;n=n+1)begin
   send(11,7'(n),127,1,{4'd2,7'd80,7'(n-102)});send(11,7'(n),127,0,0);send(11,7'(n),0,0,0);
  end
  send(11,105,127,1,{4'd3,7'd73,7'd0});send(11,106,127,1,{4'd3,7'd40,7'd0});
  send(11,107,127,1,{4'd3,7'd56,7'd0});send(11,108,127,1,{4'd3,7'd12,7'd0});send(11,109,127,1,{4'd3,7'd0,7'd0});
  send(11,20,127,1,{4'd2,7'd81,7'd1});send(11,20,0,0,0);send(11,21,127,1,{4'd2,7'd81,7'd3});send(11,22,127,1,{4'd2,7'd81,7'd7});
  for(integer n=23;n<27;n=n+1)send(11,7'(n),127,1,{4'd2,7'd82,7'(n-23)});
  send(11,71,1,1,{4'd2,7'd7,7'd101});send(11,79,127,1,{4'd2,7'd7,7'd100});
  send(11,72,127,1,{4'd2,7'd1,7'd0});send(11,72,63,1,{4'd2,7'd1,7'd63});
  send(11,73,63,1,{4'd2,7'd5,7'd63});send(11,73,63,1,{4'd2,7'd5,7'd126});send(11,73,63,1,{4'd2,7'd5,7'd127});
  @(negedge clk);er=0;
  send(9,60,88,1,{4'd1,7'd60,7'd88});repeat(15)@(posedge clk);
  if(!ev || ed!==expected[rp])$fatal(1,"backpressure not held");
  @(negedge clk);er=1;expected[wp]={4'd2,7'd123,7'd0};wp=wp+1;connected=0;
  repeat(30)@(posedge clk);if(rp!=wp||held!=0)$fatal(1,"disconnect cleanup fail");
  $display("PASS 64 pads/velocity/held filtering, sensor exclusion, ABC, 5 timbres, FX/routes, signed knobs/saturation, bend, backpressure, disconnect panic (%0d mapped)",rp);$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
