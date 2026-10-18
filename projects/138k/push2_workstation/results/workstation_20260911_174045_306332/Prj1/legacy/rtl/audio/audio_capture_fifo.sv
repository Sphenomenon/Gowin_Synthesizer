`timescale 1ns/1ps
// Recorder DMA/host boundary. A stalled consumer cannot backpressure audio.
// Packet includes sequence number so a consumer can detect every dropped frame.
module audio_capture_fifo #(parameter integer ADDRESS_BITS=8) (
    input logic clk_i,rst_ni,enable_i,sample_valid_i,
    input logic signed[31:0] left_i,right_i,
    output logic valid_o,input logic ready_i,
    output logic[95:0] packet_o,
    output logic[31:0] drop_count_o
);
  localparam integer DEPTH=1 << ADDRESS_BITS;
  // Synchronous read maps to block RAM on both Xilinx and Gowin. Forward
  // write/read collisions explicitly; do not depend on a vendor RAM mode.
  (* ram_style="block" *) logic[95:0] mem[0:DEPTH-1];
  logic[ADDRESS_BITS-1:0] rd,wr;
  logic[ADDRESS_BITS:0] count;
  logic[31:0] sequence_number;
  logic[95:0] ram_packet,forward_packet;
  logic forward_valid;
  wire pop=valid_o && ready_i;
  wire push=enable_i && sample_valid_i && (count<DEPTH || pop);
  assign valid_o=count!=0;
  wire[ADDRESS_BITS-1:0] next_rd=rd + {{(ADDRESS_BITS-1){1'b0}},pop};
  assign packet_o=forward_valid ? forward_packet : ram_packet;
  always_ff @(posedge clk_i) begin
    if(rst_ni && push) mem[wr]<={sequence_number,left_i,right_i};
    ram_packet<=mem[next_rd];
    forward_packet<={sequence_number,left_i,right_i};
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) forward_valid<=0;
    else forward_valid<=push && ((count==0) || (count==1 && pop));
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin rd<=0;wr<=0;count<=0;sequence_number<=0;drop_count_o<=0;end
    else begin
      if(sample_valid_i) sequence_number<=sequence_number+1;
      if(enable_i && sample_valid_i && !push) drop_count_o<=drop_count_o+1;
      if(push) wr<=wr+1'b1;
      if(pop) rd<=rd+1'b1;
      case({push,pop})
        2'b10:count<=count+1'b1;
        2'b01:count<=count-1'b1;
        default:begin end
      endcase
    end
  end
endmodule
