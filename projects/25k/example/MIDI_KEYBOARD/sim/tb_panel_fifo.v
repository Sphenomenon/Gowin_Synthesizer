`timescale 1ns/1ps
module tb_panel_fifo;
 reg clk=0;
 always #5 clk=!clk;
 reg reset=1,clear=0,in_valid=0,out_ready=0;
 reg [23:0] in_message=24'h903064;
 reg [1:0] in_length=3;
 reg [12:0] in_timestamp=0;
 reg [31:0] random_state=32'hb201f1f0;
 integer cycle,kind;
 reg [3:0] channel;
 reg [6:0] data_first,data_second;
 wire [3:0] in_ready,out_valid,full;
 wire [23:0] out_message[0:3];
 wire [1:0] out_length[0:3];
 wire [12:0] out_timestamp[0:3];
 wire [3:0] reference_ready,reference_valid,reference_full;
 wire [23:0] reference_message[0:3];
 wire [1:0] reference_length[0:3];
 wire [12:0] reference_timestamp[0:3];
 genvar depth_index;
 generate for(depth_index=0;depth_index<4;depth_index=depth_index+1)begin:depths
  localparam integer DEPTH=depth_index==0 ? 1 : depth_index==1 ? 3 : depth_index==2 ? 8 : 32;
  midi_event_fifo #(.DEPTH(DEPTH),.PANEL_EVENTS(1)) dut(
   .clk(clk),.reset(reset),.clear(clear),.in_valid(in_valid),.in_ready(in_ready[depth_index]),
   .in_message(in_message),.in_length(in_length),.in_timestamp(in_timestamp),
   .out_valid(out_valid[depth_index]),.out_ready(out_ready),.out_message(out_message[depth_index]),
   .out_length(out_length[depth_index]),.out_timestamp(out_timestamp[depth_index]),.full(full[depth_index]));
  midi_event_fifo #(.DEPTH(DEPTH)) reference(
   .clk(clk),.reset(reset),.clear(clear),.in_valid(in_valid),.in_ready(reference_ready[depth_index]),
   .in_message(in_message),.in_length(in_length),.in_timestamp(in_timestamp),
   .out_valid(reference_valid[depth_index]),.out_ready(out_ready),.out_message(reference_message[depth_index]),
   .out_length(reference_length[depth_index]),.out_timestamp(reference_timestamp[depth_index]),.full(reference_full[depth_index]));
  always @(posedge clk)if(!reset)
   if({in_ready[depth_index],out_valid[depth_index],full[depth_index],out_message[depth_index],out_length[depth_index],out_timestamp[depth_index]} !==
      {reference_ready[depth_index],reference_valid[depth_index],reference_full[depth_index],reference_message[depth_index],reference_length[depth_index],reference_timestamp[depth_index]})
    $fatal(1,"Packed panel FIFO cycle equivalence failed depth=%0d cycle=%0d",DEPTH,cycle);
 end endgenerate
 initial begin
  repeat(4)@(negedge clk);reset=0;
  for(cycle=0;cycle<30000;cycle=cycle+1)begin
   random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
   in_valid=cycle%256<64 ? 1 : random_state[0];
   out_ready=cycle%256<64 ? 0 : random_state[1];
   clear=cycle%401==400;in_timestamp=random_state[31:19];
   channel=random_state[18:15];data_first=random_state[14:8];data_second=random_state[7:1];
   kind=cycle%7;in_length=3;
   case(kind)
    0:in_message={4'h9,channel,1'b0,data_first,8'd100};
    1:in_message={4'h8,channel,1'b0,data_first,8'd0};
    2:in_message={4'hb,channel,8'd7,1'b0,data_second};
    3:in_message={4'hb,channel,8'd88,1'b0,data_second};
    4:in_message={4'hb,channel,8'd89,1'b0,data_second};
    5:begin in_message={4'hc,channel,1'b0,data_first,8'd0};in_length=2;end
    6:in_message={4'he,channel,1'b0,data_first,1'b0,data_second};
   endcase
   @(negedge clk);
  end
  clear=1;@(negedge clk);
  $display("PASS tb_panel_fifo 120000 cycle/depth comparisons: exact MIDI/length/13-bit timestamps, depth 1/3/8/32, full push/pop, empty bypass, wrap, stalls and clear");
  $finish;
 end
endmodule
