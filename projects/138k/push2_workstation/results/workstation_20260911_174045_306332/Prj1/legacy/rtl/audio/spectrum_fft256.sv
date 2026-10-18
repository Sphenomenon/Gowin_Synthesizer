`timescale 1ns/1ps
`ifndef AUDIO_FFT_HANN_MEM_FILE
`define AUDIO_FFT_HANN_MEM_FILE "sim/data/audio_chain/fft_hann.mem"
`define AUDIO_FFT_TW_RE_MEM_FILE "sim/data/audio_chain/fft_tw_re.mem"
`define AUDIO_FFT_TW_IM_MEM_FILE "sim/data/audio_chain/fft_tw_im.mem"
`endif
// Non-blocking visualization tap. Capture 256 frames, run a scaled radix-2
// FFT, stream bins 0..127, then capture a new frame. Audio never waits for it.
// Input/output Q1.23, Hann window Q0.15, FFT normalized by 1/256.
module spectrum_fft256 (
    input logic clk_i,rst_ni,sample_valid_i,
    input logic signed[31:0] sample_i,
    output logic bin_valid_o,
    output logic[7:0] bin_o,
    output logic signed[23:0] real_o,imag_o,
    output logic[31:0] frame_o
);
  import audio_math_pkg::*;
  (* ram_style="block",syn_ramstyle="block_ram" *) logic signed[23:0] re_mem[0:255],im_mem[0:255];
  logic signed[15:0] tw_re[0:127],tw_im[0:127];
  logic[15:0] window[0:255];
  logic[3:0] state;
  logic[7:0] capture_index,emit_index;
  logic[3:0] level;
  logic[8:0] group_base,offset;
  logic[8:0] half_size,full_size;
  logic[7:0] address_a,address_b,twiddle_index;
  logic signed[23:0] ar,ai,br,bi;
  logic signed[15:0] wr,wi;
  logic signed[39:0] p0,p1,p2,p3;
  logic signed[63:0] tr,ti;
  logic signed[23:0] result_ar,result_ai,result_br,result_bi;
  logic[7:0] capture_address;
  logic[7:0] port_a_address;
  logic port_a_write;
  logic signed[23:0] port_a_re,port_a_im;
  logic capture_v1,capture_v2;
  logic[7:0] capture_addr1,capture_addr2;
  logic signed[23:0] capture_sample;
  logic signed[16:0] capture_window;
  logic signed[40:0] capture_product;
  initial begin
    $readmemh(`AUDIO_FFT_TW_RE_MEM_FILE,tw_re);
    $readmemh(`AUDIO_FFT_TW_IM_MEM_FILE,tw_im);
    $readmemh(`AUDIO_FFT_HANN_MEM_FILE,window);
  end
  function automatic logic[7:0] reverse8(input logic[7:0] v);
    for(integer j=0;j<8;j=j+1) reverse8[j]=v[7-j];
  endfunction
  assign half_size=9'd1 << (level-1'b1);
  assign full_size=half_size << 1;
  assign address_a=8'(group_base+offset);
  assign address_b=8'(group_base+offset+half_size);
  assign twiddle_index=8'(offset << (8-level));
  assign capture_address=reverse8(capture_index);
  assign port_a_address=capture_v2 ? capture_addr2 : state==6 ? emit_index : address_a;
  assign port_a_write=capture_v2 || state==5;
  assign port_a_re=capture_v2
      ? 24'(rshift(capture_product,15))
      : result_ar;
  assign port_a_im=capture_v2 ? 24'sd0 : result_ai;
  // Separate window lookup, multiplication and rounded RAM write. Drain the
  // final capture before starting butterflies; input throughput stays 1/clock.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin capture_v1<=0;capture_v2<=0;end
    else begin
      capture_v1<=state==0 && sample_valid_i;
      capture_v2<=capture_v1;
    end
  end
  always_ff @(posedge clk_i) begin
    if(state==0 && sample_valid_i) begin
      capture_sample<=sample_i[31:8];capture_window<=$signed({1'b0,window[capture_index]});
      capture_addr1<=capture_address;
    end
    if(capture_v1) begin
      capture_product<=capture_sample*capture_window;capture_addr2<=capture_addr1;
    end
  end
  // Explicit true-dual-port template: input capture, butterflies and readout
  // share port A; port B supplies the other butterfly operand.
  always_ff @(posedge clk_i) begin
    if(port_a_write) begin
      re_mem[port_a_address]<=port_a_re;im_mem[port_a_address]<=port_a_im;
    end
    ar<=re_mem[port_a_address];ai<=im_mem[port_a_address];
  end
  always_ff @(posedge clk_i) begin
    if(state==5) begin
      re_mem[address_b]<=result_br;im_mem[address_b]<=result_bi;
    end
    br<=re_mem[address_b];bi<=im_mem[address_b];
    if(state==1) begin wr<=tw_re[twiddle_index];wi<=tw_im[twiddle_index];end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      state<=0;capture_index<=0;emit_index<=0;level<=1;group_base<=0;offset<=0;
      p0<=0;p1<=0;p2<=0;p3<=0;tr<=0;ti<=0;
      result_ar<=0;result_ai<=0;result_br<=0;result_bi<=0;
      bin_valid_o<=0;bin_o<=0;real_o<=0;imag_o<=0;frame_o<=0;
    end else begin
      bin_valid_o<=0;
      case(state)
        0: if(sample_valid_i) begin
          if(capture_index==255) begin
            state<=8;level<=1;group_base<=0;offset<=0;capture_index<=0;
          end else capture_index<=capture_index+1'b1;
        end
        1: state<=2;
        2: begin p0<=br*wr;p1<=bi*wi;p2<=br*wi;p3<=bi*wr;state<=3;end
        3: begin tr<=rshift($signed(p0)-$signed(p1),15);ti<=rshift($signed(p2)+$signed(p3),15);state<=4;end
        4: begin
          result_ar<=24'(rshift($signed(ar)+tr,1));result_ai<=24'(rshift($signed(ai)+ti,1));
          result_br<=24'(rshift($signed(ar)-tr,1));result_bi<=24'(rshift($signed(ai)-ti,1));state<=5;
        end
        5: begin
          if(offset+1 < half_size) begin offset<=offset+1'b1;state<=1;end
          else if(group_base+full_size < 256) begin group_base<=group_base+full_size;offset<=0;state<=1;end
          else if(level<8) begin level<=level+1'b1;group_base<=0;offset<=0;state<=1;end
          else begin emit_index<=0;state<=6;frame_o<=frame_o+1;end
        end
        6: state<=7;
        7: begin
          bin_valid_o<=1;bin_o<=emit_index;real_o<=ar;imag_o<=ai;
          if(emit_index==127) state<=0;else begin emit_index<=emit_index+1'b1;state<=6;end
        end
        8: if(capture_v2 && capture_addr2==255) state<=1;
        default: state<=0;
      endcase
    end
  end
endmodule
