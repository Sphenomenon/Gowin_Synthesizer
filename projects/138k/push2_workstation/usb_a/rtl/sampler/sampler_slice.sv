`timescale 1ns/1ps
// Manual markers persist in configuration registers; endpoints are exclusive.
module sampler_slice(
  input logic clk,rst_n,manual_write,input logic [3:0] marker_index,
  input logic [31:0] marker_frame,
  input logic manual,input logic [3:0] slice_index,
  input logic [31:0] trim_start,trim_end,
  output logic [31:0] slice_start,slice_end,output logic valid
);
  logic [31:0] markers[16];logic [15:0] present;
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin present<=0;for(int i=0;i<16;i++) markers[i]<=0;end
    else if(manual_write) begin markers[marker_index]<=marker_frame;present[marker_index]<=1;end
  end
  always_comb begin
    slice_start=trim_start+((trim_end-trim_start)*int'(slice_index))/16;
    slice_end=trim_start+((trim_end-trim_start)*(int'(slice_index)+1))/16;
    valid=trim_end>trim_start && slice_end>slice_start;
    if(manual) begin
      slice_start=markers[slice_index];slice_end=slice_index==15 ? trim_end : markers[slice_index+1];
      valid=present[slice_index] && (slice_index==15 || present[slice_index+1]) &&
        slice_start>=trim_start && slice_end<=trim_end && slice_end>slice_start;
    end
  end
endmodule
