`timescale 1ns/1ps
// The vendor FAT reader has no backpressure. Buffer a full sector and report
// overflow explicitly. Keep all source files in rtl/tf_audio/ unchanged.
module sampler_tf_source #(
  parameter integer FILE_NAME_LEN=10,
  parameter [415:0] FILE_NAME="SAMPLE.WAV", parameter integer FIFO_BITS=11
)(
  input logic clk,rst_n,enable,restart,sd_miso,
  output wire sd_cs_n,sd_sck,sd_mosi,
  output logic valid,input logic ready,output logic [7:0] data,output logic last,
  output logic overflow,
  output wire [1:0] card_type,filesystem_type,
  output wire [3:0] card_status,output wire [2:0] filesystem_status,
  output wire file_found,output wire [31:0] file_size
);
  logic [8:0] fifo[1<<FIFO_BITS];logic [FIFO_BITS:0] wr,rd,occupancy;
  wire raw_valid;wire [7:0] raw_byte;logic [31:0] byte_count;
  third_party_sd_spi_file_reader #(.FILE_NAME_LEN(FILE_NAME_LEN),.FILE_NAME(FILE_NAME),.SPI_CLK_DIV(100)) u_fat(
    .rstn(rst_n && enable && !restart && !overflow),.clk(clk),
    .spi_ssn(sd_cs_n),.spi_sck(sd_sck),.spi_mosi(sd_mosi),.spi_miso(sd_miso),
    .card_type(card_type),.card_stat(card_status),.filesystem_type(filesystem_type),
    .filesystem_stat(filesystem_status),.file_found(file_found),.file_size_o(file_size),
    .outen(raw_valid),.outbyte(raw_byte));
  assign occupancy=wr-rd;
  assign valid=(wr!=rd) && !overflow;assign {last,data}=fifo[rd[FIFO_BITS-1:0]];
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin wr<=0;rd<=0;byte_count<=0;overflow<=0;end
    else if(restart || !enable) begin wr<=0;rd<=0;byte_count<=0;overflow<=0;end
    else begin
      if(valid && ready) rd<=rd+1'b1;
      if(raw_valid) begin
        if(occupancy==(FIFO_BITS+1)'(1<<FIFO_BITS)) overflow<=1;
        else begin
          fifo[wr[FIFO_BITS-1:0]]<={file_size!=0 && byte_count==file_size-1,raw_byte};
          wr<=wr+1'b1;byte_count<=byte_count+1;
        end
      end
    end
  end
endmodule
