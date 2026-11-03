`timescale 1ns/1ps
`default_nettype none
module midi_pluck_emitter_guard #(parameter integer LEASE_CYCLES=100000000)(
 input wire clk,reset,control_reset,online,
 input wire config_write,
 input wire [7:0] config_opcode,
 input wire [31:0] config_value,
 output wire armed
);
 function integer width_for;
  input integer depth;
  integer remaining;
  begin
   remaining=depth;width_for=0;
   while(remaining>0)begin width_for=width_for+1;remaining=remaining>>1;end
   if(width_for<1)width_for=1;
  end
 endfunction
 reg [width_for(LEASE_CYCLES)-1:0] remaining=0;
 assign armed=remaining!=0 && online && !reset && !control_reset;
 always @(posedge clk)begin
  if(reset || control_reset || !online)remaining<=0;
  else if(config_write && config_opcode==8'h04)
   remaining<=config_value==1 ? LEASE_CYCLES : 0;
  else if(remaining!=0)remaining<=remaining-1'b1;
 end
endmodule
`default_nettype wire
