`timescale 1ns/1ps
`default_nettype none
// Registered RAM read with a separate output slot. OUT readiness reserves a
// whole 512-byte packet: the packet core cannot backpressure individual bytes.
module usb2_hs_echo #(parameter ADDR_WIDTH=11)(
 input wire clk, reset_n, clear,
 input wire rx_valid, input wire [7:0] rx_data,
 output wire rx_space,
 output wire tx_valid, output wire [7:0] tx_data, input wire tx_accept,
 output reg [31:0] rx_count=0, tx_count=0,
 output reg [15:0] overflow_count=0,
 output wire [15:0] occupancy
);
 localparam DEPTH=(1<<ADDR_WIDTH);
 reg [7:0] memory[0:DEPTH-1];
 reg [ADDR_WIDTH-1:0] wr=0, rd=0;
 reg [ADDR_WIDTH:0] queued=0;
 reg front_valid=0;
 reg [7:0] front_data=0;
 wire load_front=(!front_valid || tx_accept) && queued!=0;
 wire store=rx_valid && queued<DEPTH;
 assign occupancy=queued+front_valid;
 assign rx_space=occupancy <= DEPTH-512;
 assign tx_valid=front_valid;
 assign tx_data=front_data;
 always @(posedge clk) begin
  if(store) memory[wr]<=rx_data;
  if(load_front) front_data<=memory[rd];
 end
 always @(posedge clk or negedge reset_n) begin
  if(!reset_n) begin wr<=0;rd<=0;queued<=0;front_valid<=0;rx_count<=0;tx_count<=0;overflow_count<=0; end
  else if(clear) begin wr<=0;rd<=0;queued<=0;front_valid<=0; end
  else begin
   if(store) wr<=wr+1'b1;
   if(load_front) begin rd<=rd+1'b1;front_valid<=1;end
   else if(front_valid && tx_accept) front_valid<=0;
   case({store,load_front})
    2'b10:queued<=queued+1'b1;
    2'b01:queued<=queued-1'b1;
   endcase
   if(rx_valid) begin
    if(rx_count!=32'hffffffff)rx_count<=rx_count+1'b1;
    if(!store && overflow_count!=16'hffff)overflow_count<=overflow_count+1'b1;
   end
   if(front_valid && tx_accept && tx_count!=32'hffffffff)tx_count<=tx_count+1'b1;
  end
 end
endmodule
`default_nettype wire
