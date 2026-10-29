`timescale 1ns/1ps
`default_nettype none
// Power-of-two dual-clock FIFO. Common async reset asserts in both domains;
// release is synchronized separately. Payload remains a complete transfer
// unit (32-bit MIDI event or 8-bit vendor byte) across the CDC boundary.
module midi_usb_async_fifo #(
 parameter integer WIDTH=32, parameter integer ADDR_BITS=6
)(
 input wire reset,
 input wire wr_clk, input wire wr_valid, output wire wr_ready,
 input wire[WIDTH-1:0]wr_data,
 input wire rd_clk, output wire rd_valid, input wire rd_ready,
 output wire[WIDTH-1:0]rd_data
);
 localparam integer DEPTH=1<<ADDR_BITS;
 (* ram_style="block" *) reg[WIDTH-1:0]memory[0:DEPTH-1];
 reg[WIDTH-1:0]rd_data_q;
 reg[ADDR_BITS:0]wr_bin,wr_gray,rd_bin,rd_gray;
 (* ASYNC_REG="TRUE" *) reg[ADDR_BITS:0]rd_gray_w1,rd_gray_w2,wr_gray_r1,wr_gray_r2;
 (* ASYNC_REG="TRUE" *) reg[1:0]wr_release,rd_release;
 always @(posedge wr_clk or posedge reset)
  if(reset)wr_release<=0;else wr_release<={wr_release[0],1'b1};
 always @(posedge rd_clk or posedge reset)
  if(reset)rd_release<=0;else rd_release<={rd_release[0],1'b1};
 wire wr_reset=!wr_release[1],rd_reset=!rd_release[1];
 wire full=wr_gray=={~rd_gray_w2[ADDR_BITS:ADDR_BITS-1],rd_gray_w2[ADDR_BITS-2:0]};
 assign wr_ready=wr_release[1]&&!full;
 assign rd_valid=rd_release[1]&&(rd_gray!=wr_gray_r2);
 assign rd_data=rd_data_q;
 wire[ADDR_BITS:0]wr_next=wr_bin+1'b1,rd_next=rd_bin+1'b1;
 // Prefetch the next head on a pop. The synchronized write pointer does not
 // expose a newly written word until this synchronous read has completed.
 wire[ADDR_BITS-1:0]read_address=rd_valid&&rd_ready?rd_next[ADDR_BITS-1:0]:rd_bin[ADDR_BITS-1:0];
 always @(posedge wr_clk)
  if(wr_valid&&wr_ready)memory[wr_bin[ADDR_BITS-1:0]]<=wr_data;
 always @(posedge rd_clk)rd_data_q<=memory[read_address];
 always @(posedge wr_clk or posedge wr_reset)begin
  if(wr_reset)begin wr_bin<=0;wr_gray<=0;rd_gray_w1<=0;rd_gray_w2<=0;end
  else begin
   rd_gray_w1<=rd_gray;rd_gray_w2<=rd_gray_w1;
   if(wr_valid&&wr_ready)begin
    wr_bin<=wr_next;wr_gray<=(wr_next>>1)^wr_next;
   end
  end
 end
 always @(posedge rd_clk or posedge rd_reset)begin
  if(rd_reset)begin rd_bin<=0;rd_gray<=0;wr_gray_r1<=0;wr_gray_r2<=0;end
  else begin
   wr_gray_r1<=wr_gray;wr_gray_r2<=wr_gray_r1;
   if(rd_valid&&rd_ready)begin rd_bin<=rd_next;rd_gray<=(rd_next>>1)^rd_next;end
  end
 end
endmodule
`default_nettype wire
