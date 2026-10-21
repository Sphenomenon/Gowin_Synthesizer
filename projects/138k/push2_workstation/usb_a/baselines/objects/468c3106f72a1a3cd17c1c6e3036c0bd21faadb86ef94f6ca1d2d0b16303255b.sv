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
  // Three explicit 32-bit SDP blocks retain all 256 packets.
  wire [95:0] ram_packet;
  logic[ADDRESS_BITS-1:0] rd,wr;
  logic[ADDRESS_BITS:0] count;
  logic[31:0] sequence_number;
  logic[95:0] forward_packet;
  logic forward_valid;
  wire pop=valid_o && ready_i;
  wire push=enable_i && sample_valid_i && (count<DEPTH || pop);
  assign valid_o=count!=0;
  wire[ADDRESS_BITS-1:0] next_rd=rd + {{(ADDRESS_BITS-1){1'b0}},pop};
  assign packet_o=forward_valid ? forward_packet : ram_packet;
  wire [95:0] write_packet={sequence_number,left_i,right_i};
  for(genvar bank=0;bank<3;bank=bank+1) begin : g_packet_sdp
    workstation_sdp #(.ADDR_WIDTH(ADDRESS_BITS)) ram(
      .write_clk_i(clk_i),.write_enable_i(rst_ni && push),.write_addr_i(wr),
      .write_data_i(write_packet[bank*32+:32]),.read_clk_i(clk_i),
      .read_enable_i(1'b1),.read_addr_i(next_rd),.read_data_o(ram_packet[bank*32+:32]));
  end
  always_ff @(posedge clk_i) begin
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
