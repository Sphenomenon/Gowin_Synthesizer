`timescale 1ns/1ps
module tb_pluck_pwm;
 reg clk=0;
 always #10 clk=!clk;
 reg reset=1,enable=0;
 wire [4:0] pwm;
 reg [4:0] previous=0;
 integer elapsed=0,channel;
 integer half_cycles[0:4];
 integer last_edge[0:4];
 integer edges[0:4];
 midi_pluck_pwm dut(.clk(clk),.reset(reset),.enable(enable),.pwm(pwm));
 always @(posedge clk)begin
  #1;
  if(reset || !enable)begin
   if(pwm!==0)$fatal(1,"PWM active while reset/disarmed");
   previous=0;elapsed=0;
   for(channel=0;channel<5;channel=channel+1)begin last_edge[channel]=0;edges[channel]=0;end
  end else begin
   elapsed=elapsed+1;
   for(channel=0;channel<5;channel=channel+1)if(pwm[channel]!=previous[channel])begin
    if(elapsed-last_edge[channel]!=half_cycles[channel])$fatal(1,"PWM%0d frequency/duty/enable phase mismatch",channel+1);
    last_edge[channel]=elapsed;edges[channel]=edges[channel]+1;
   end
   previous=pwm;
  end
 end
 initial begin
  half_cycles[0]=15060;half_cycles[1]=7353;half_cycles[2]=3587;half_cycles[3]=25000;half_cycles[4]=5144;
  repeat(4)@(negedge clk);reset=0;
  repeat(30000)@(negedge clk);
  enable=1;
  repeat(1000000)@(negedge clk);
  for(channel=0;channel<5;channel=channel+1)
   if(edges[channel]!=1000000/half_cycles[channel])$fatal(1,"PWM%0d missing/extra edges",channel+1);
  #7;enable=0;#1;if(pwm!==0)$fatal(1,"Safety disable not immediate");
  repeat(4)@(negedge clk);enable=1;
  repeat(30000)@(negedge clk);
  #7;reset=1;#1;if(pwm!==0)$fatal(1,"Safety reset not immediate");
  repeat(4)@(negedge clk);reset=0;
  repeat(30000)@(negedge clk);
  $display("PASS tb_pluck_pwm CHN1..5 1660/3400/6970/1000/4860 Hz rounded half-periods, 50%% duty, phase restart, immediate OFF/reset");$finish;
 end
 initial begin #30000000;$fatal(1,"PWM test timeout");end
endmodule
