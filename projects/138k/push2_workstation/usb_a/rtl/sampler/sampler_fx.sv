`timescale 1ns/1ps
// Momentary CC 20=crush,21=drive,22=existing P10 delay send. Zero releases.
module sampler_fx(
  input logic clk,rst_n,panic,cc_valid,input logic [6:0] cc,value,
  input logic pcm_valid,input logic signed [15:0] pcm_l,pcm_r,
  output logic out_valid,output logic signed [15:0] out_l,out_r,
  output logic [6:0] delay_send
);
  import sampler_pkg::*;
  logic [6:0] crush,drive;integer shift;
  function automatic logic signed [15:0] process(input logic signed [15:0] x);
    logic signed [63:0] amplified,quantized;
    amplified=($signed(x)*$signed(12'(128+int'(drive)*8)))>>>7;
    quantized=($signed(sat16(amplified))>>>shift)<<<shift;
    return sat16(quantized);
  endfunction
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin crush<=0;drive<=0;delay_send<=0;out_valid<=0;out_l<=0;out_r<=0;end
    else begin
      out_valid<=pcm_valid;shift=int'(crush)*12/127;
      if(pcm_valid) begin out_l<=process(pcm_l);out_r<=process(pcm_r);end
      if(cc_valid) case(cc)
        20:crush<=value;21:drive<=value;22:delay_send<=value;default:begin end
      endcase
      if(panic) begin crush<=0;drive<=0;delay_send<=0;out_l<=0;out_r<=0;out_valid<=0;end
    end
  end
endmodule
module sampler_click(
  input logic clk,rst_n,panic,sample_tick,trigger,enable,
  output logic signed [15:0] pcm
);
  logic [10:0] remaining;logic [5:0] phase;
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin remaining<=0;phase<=0;pcm<=0;end
    else if(panic || !enable) begin remaining<=0;pcm<=0;end
    else begin
      if(trigger) begin remaining<=480;phase<=0;end
      if(sample_tick) begin
        phase<=phase+1;
        if(remaining!=0) begin remaining<=remaining-1;pcm<=phase[4] ? -16'(remaining*8) : 16'(remaining*8);end
        else pcm<=0;
      end
    end
  end
endmodule
