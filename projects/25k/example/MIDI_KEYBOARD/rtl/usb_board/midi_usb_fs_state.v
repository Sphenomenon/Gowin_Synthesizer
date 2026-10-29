`timescale 1ns/1ps
`default_nettype none
module midi_usb_fs_state #(
 parameter integer CLOCK_HZ=48000000
)(
 input wire clk,reset,enable,bus_active,
 input wire[1:0]line_state,
 output wire bus_reset,suspended
);
 localparam integer RESET_COUNT=CLOCK_HZ/400000;
 localparam integer SUSPEND_COUNT=CLOCK_HZ/1000*3;
 localparam[7:0]RESET_CYCLES=RESET_COUNT[7:0];
 localparam[17:0]SUSPEND_CYCLES=SUSPEND_COUNT[17:0];
 reg[7:0]se0_count;
 reg[17:0]idle_count;
 always @(posedge clk or posedge reset)
  if(reset)begin se0_count<=0;idle_count<=0;end
  else begin
   if(!enable||line_state!=0)se0_count<=0;
   else if(se0_count<RESET_CYCLES)se0_count<=se0_count+1'b1;
   if(!enable||bus_active||line_state!=2'b01)idle_count<=0;
   else if(idle_count<SUSPEND_CYCLES)idle_count<=idle_count+1'b1;
  end
 assign bus_reset=!enable||se0_count>=RESET_CYCLES;
 assign suspended=idle_count>=SUSPEND_CYCLES;
endmodule
`default_nettype wire
