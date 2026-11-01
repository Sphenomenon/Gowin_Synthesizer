`timescale 1ns/1ps
`default_nettype none
module midi_pluck_pwm #(
 parameter integer CLK_HZ=50000000
)(
 input wire clk,reset,enable,
 output wire [4:0] pwm
);
 function integer width_for;
  input integer maximum;
  integer remaining;
  begin
   remaining=maximum;width_for=0;
   while(remaining>0)begin width_for=width_for+1;remaining=remaining>>1;end
   if(width_for<1)width_for=1;
  end
 endfunction
 genvar channel;
 generate for(channel=0;channel<5;channel=channel+1)begin:channels
  localparam integer FREQUENCY=channel==0 ? 1660 : channel==1 ? 3400 :
                              channel==2 ? 6970 : channel==3 ? 1000 : 4860;
  localparam integer HALF_CYCLES=(CLK_HZ+FREQUENCY)/(2*FREQUENCY);
  reg [width_for(HALF_CYCLES-1)-1:0] counter;
  reg level;
  assign pwm[channel]=!reset && enable && level;
  always @(posedge clk)begin
   if(reset || !enable)begin counter<=0;level<=0;end
   else if(counter==HALF_CYCLES-1)begin counter<=0;level<=!level;end
   else counter<=counter+1'b1;
  end
`ifndef SYNTHESIS
  initial if(HALF_CYCLES<1)$fatal(1,"Pluck PWM clock is below twice the requested carrier frequency");
`endif
 end endgenerate
endmodule
`default_nettype wire
