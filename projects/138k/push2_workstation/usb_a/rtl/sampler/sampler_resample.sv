`timescale 1ns/1ps
// Explicit single-voice bus capture. Pattern/song captures are refused by policy.
// Reserve a fresh descriptor, freeze sequencer transport, and require exactly one
// voice throughout capture. The resulting PCM is still played through voices.
module sampler_resample(
  input logic clk,rst_n,restart,start,stop,
  input logic approved_single_note,sequencer_running,
  input logic [5:0] active_voices,
  input logic sample_valid,input logic signed [15:0] pcm_l,pcm_r,
  input logic [31:0] base_bytes,capacity_bytes,max_frames,
  output logic write_valid,input logic write_ready,
  output logic [31:0] write_address,write_base,write_capacity,
  output logic [255:0] write_data,
  input logic response_valid,input logic [7:0] response_error,
  output logic busy,done,output logic [7:0] error,
  output logic [31:0] frames,crc32
);
  import sampler_pkg::*;
  logic waiting,ending;integer fill;logic [31:0] offset,crc,limit;
  logic signed [16:0] mono;
  assign write_address=base_bytes+offset;assign write_base=base_bytes;assign write_capacity=capacity_bytes;
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin busy<=0;done<=0;error<=0;frames<=0;crc32<=0;crc<=32'hffffffff;
      waiting<=0;ending<=0;fill<=0;offset<=0;write_valid<=0;write_data<=0;limit<=0;end
    else begin
      done<=0;
      if(restart) begin busy<=0;write_valid<=0;waiting<=0;end
      else if(start) begin
        frames<=0;crc<=32'hffffffff;crc32<=0;offset<=0;fill<=0;waiting<=0;ending<=0;
        write_valid<=0;write_data<=0;limit<=max_frames;error<=OK;
        if(!approved_single_note || sequencer_running || active_voices!=1 || max_frames==0 || max_frames>288000)
          begin busy<=0;done<=1;error<=E_POLICY;end
        else if(base_bytes[4:0] || max_frames>capacity_bytes/2 || capacity_bytes<32)
          begin busy<=0;done<=1;error<=E_BOUNDS;end
        else busy<=1;
      end else if(busy) begin
        if(stop || frames==limit) ending<=1;
        if(write_valid && write_ready) begin write_valid<=0;waiting<=1;end
        if(waiting && response_valid) begin
          waiting<=0;fill<=0;offset<=offset+32;write_data<=0;
          if(response_error!=OK) begin busy<=0;done<=1;error<=response_error;end
        end
        if(ending && !write_valid && !waiting) begin
          if(fill!=0) write_valid<=1;
          else begin busy<=0;done<=1;crc32<=~crc;if(frames==0) error<=E_TRUNCATED;end
        end else if(sample_valid && !ending && !stop && frames<limit) begin
          if(!approved_single_note || sequencer_running || active_voices!=1) begin busy<=0;done<=1;error<=E_POLICY;write_valid<=0;end
          else if(write_valid || waiting) begin busy<=0;done<=1;error<=E_OVERFLOW;end
          else begin
            mono=($signed(pcm_l)+$signed(pcm_r))>>>1;
            write_data[fill*16+:16]<=mono[15:0];fill<=fill+1;frames<=frames+1;
            crc<=crc_byte(crc_byte(crc,mono[7:0]),mono[15:8]);
            if(fill==15) write_valid<=1;
          end
        end
      end
    end
  end
endmodule
