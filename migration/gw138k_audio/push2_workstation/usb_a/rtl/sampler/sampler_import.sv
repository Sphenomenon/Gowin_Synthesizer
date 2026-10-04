`timescale 1ns/1ps
// Canonical mono WAV -> reserved descriptor. No PCM output exists here.
module sampler_import(
  input logic clk,rst_n,restart,start,
  input logic [1:0] granularity, // 1=single_note, 2=single_hit; all others rejected
  input logic contains_rhythm,contains_melody,contains_arrangement,normalize,
  input logic [31:0] expected_frames,expected_crc,base_bytes,capacity_bytes,
  input logic in_valid,input logic [7:0] in_byte,input logic in_last,output logic in_ready,
  output logic write_valid,input logic write_ready,
  output logic [31:0] write_address,write_base,write_capacity,
  output logic [255:0] write_data,
  input logic response_valid,input logic [7:0] response_error,
  output logic busy,done,output logic [7:0] error,
  output logic [31:0] frames,gain_q16,crc32
);
  import sampler_pkg::*;
  logic dec_ready,header_valid,stereo,pcm_valid,pcm_ready,unsupported;
  logic [19:0] rate;logic [5:0] bits;
  logic signed [15:0] left_pcm,right_pcm;
  logic [31:0] crc,peak,expected,expected_hash,offset;
  logic norm,eof;integer settle,fill;
  logic waiting,normalizing;
  logic [31:0] quotient;
  logic [15:0] remainder,divisor;
  logic [5:0] divide_bit;
  logic [16:0] trial;
  logic [15:0] reduced;
  logic [31:0] next_quotient;
  tf_wav_pcm_decoder u_wav(.clk(clk),.rst_n(rst_n),.restart(restart || start),
    .in_valid(in_valid && in_ready),.in_byte(in_byte),.in_ready(dec_ready),
    .header_valid(header_valid),.sample_rate_hz(rate),.stereo(stereo),.bits_per_sample(bits),
    .pcm_valid(pcm_valid),.pcm_ready(pcm_ready),.pcm_left(left_pcm),.pcm_right(right_pcm),.unsupported(unsupported));
  assign in_ready=busy && !normalizing && !eof && !write_valid && !waiting && dec_ready;
  assign pcm_ready=busy && !normalizing && !write_valid && !waiting && header_valid && !stereo && rate==48000 && !unsupported;
  assign write_base=base_bytes;assign write_capacity=capacity_bytes;
  assign write_address=base_bytes+offset;
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin
      busy<=0;done<=0;error<=0;frames<=0;gain_q16<=65536;crc32<=0;crc<=32'hffffffff;
      peak<=0;expected<=0;expected_hash<=0;offset<=0;norm<=0;eof<=0;settle<=0;fill<=0;
      waiting<=0;normalizing<=0;quotient<=0;remainder<=0;divisor<=1;divide_bit<=0;write_valid<=0;write_data<=0;
    end else begin
      done<=0;
      if(restart) begin busy<=0;write_valid<=0;waiting<=0;fill<=0;eof<=0;normalizing<=0;end
      else if(start) begin
        error<=OK;frames<=0;crc<=32'hffffffff;crc32<=0;peak<=0;offset<=0;
        expected<=expected_frames;expected_hash<=expected_crc;norm<=normalize;
        eof<=0;settle<=0;fill<=0;waiting<=0;normalizing<=0;write_valid<=0;write_data<=0;gain_q16<=65536;
        if((granularity!=1 && granularity!=2) || contains_rhythm || contains_melody || contains_arrangement ||
          expected_frames==0 || expected_frames>(granularity==2 ? 96000 : 288000)) begin
          busy<=0;done<=1;error<=E_POLICY;
        end else if(expected_frames>capacity_bytes/2 || base_bytes[4:0] || capacity_bytes<32) begin
          busy<=0;done<=1;error<=E_BOUNDS;
        end else busy<=1;
      end else if(normalizing) begin
        // Divide (32767 << 16) by peak with one 17-bit subtract each cycle.
        trial={remainder,(divide_bit>=16 && divide_bit<31)};
        reduced=16'(trial>=divisor ? trial-divisor : trial);
        next_quotient=quotient;next_quotient[divide_bit]=trial>=divisor;
        remainder<=reduced;quotient<=next_quotient;
        if(divide_bit==0) begin gain_q16<=next_quotient;busy<=0;done<=1;normalizing<=0;end
        else divide_bit<=divide_bit-1'b1;
      end else if(busy) begin
        if(in_valid && in_ready && in_last) eof<=1;
        if(write_valid && write_ready) begin write_valid<=0;waiting<=1;end
        if(waiting && response_valid) begin
          waiting<=0;fill<=0;write_data<=0;offset<=offset+32;
          if(response_error!=OK) begin busy<=0;done<=1;error<=response_error;end
        end
        if(pcm_valid && pcm_ready) begin
          settle<=0;
          if(frames>=expected || frames>=capacity_bytes/2) begin busy<=0;done<=1;error<=E_BOUNDS;end
          else begin
            write_data[fill*16+:16]<=left_pcm;fill<=fill+1;frames<=frames+1;
            crc<=crc_byte(crc_byte(crc,left_pcm[7:0]),left_pcm[15:8]);
            if((left_pcm<0 ? -32'(left_pcm) : 32'(left_pcm))>peak)
              peak<=left_pcm<0 ? -32'(left_pcm) : 32'(left_pcm);
            if(fill==15) write_valid<=1;
          end
        end else if(eof && !write_valid && !waiting) begin
          if(settle<8) settle<=settle+1;
          else if(!header_valid || unsupported || stereo || rate!=48000 ||
             !(bits==8 || bits==16 || bits==24 || bits==32)) begin busy<=0;done<=1;error<=E_FORMAT;end
          else if(frames!=expected) begin busy<=0;done<=1;error<=E_TRUNCATED;end
          else if(fill!=0) write_valid<=1;
          else begin
            crc32<=~crc;
            if(~crc!=expected_hash) begin busy<=0;done<=1;error<=E_CRC;end
            else if(norm && peak!=0) begin
              normalizing<=1;quotient<=0;remainder<=0;divisor<=peak[15:0];divide_bit<=31;
            end else begin busy<=0;done<=1;end
          end
        end
        if(unsupported || (header_valid && (stereo || rate!=48000))) begin
          busy<=0;done<=1;error<=E_FORMAT;write_valid<=0;
        end
      end
    end
  end
endmodule
