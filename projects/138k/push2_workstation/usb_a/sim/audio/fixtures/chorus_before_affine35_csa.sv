`timescale 1ns/1ps
// Independent native runtime Chorus; no profile currently selects this module.
// Config/history requests clear logical history while retaining wet gain and
// LFO phase. Legacy clear aborts and resets wet gain, preserving legacy phase.
module workstation_runtime_chorus_effect #(
    parameter integer CHORUS_BITS=10,
    parameter integer CHORUS_BASE=480,
    parameter integer CHORUS_DEPTH=96
) (
    input logic clk_i,rst_ni,clear_i,valid_i,enabled_i,
    input logic signed [31:0] left_i,right_i,
    output logic ready_o,valid_o,active_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o,
    input logic config_valid_i,rate_44100_i,history_clear_i,
    output logic config_ready_o,config_applied_o,history_ready_o,history_done_o,
    output logic quiescent_o,applied_rate_44100_o
);
  import audio_math_pkg::*;
  localparam integer DEPTH=1<<CHORUS_BITS;
  (* ram_style="block",syn_ramstyle="block_ram" *) logic signed [31:0] memory_l[0:DEPTH-1],memory_r[0:DEPTH-1];
  logic [CHORUS_BITS-1:0] pointer,read_address;
  logic [31:0] frames;
  logic [2:0] state;
  logic [15:0] gain,triangle,chorus_delay;
  logic [23:0] lfo;
  logic signed [31:0] input_l,input_r,read_l,read_r;
  logic signed [48:0] product_l,product_r;
  logic signed [63:0] mixed_l,mixed_r;
  initial begin
    if(CHORUS_BITS!=10 || CHORUS_BASE!=480 || CHORUS_DEPTH!=96)
      $fatal(1,"runtime Chorus requires the audited1024-slot480+96 baseline");
  end
  logic [7:0] gain_remainder,lfo_remainder;
  wire [7:0] gain_fraction_sum=gain_remainder+8'd47;
  wire [8:0] lfo_fraction_sum={1'b0,lfo_remainder}+9'd127;
  wire [15:0] gain_delta=applied_rate_44100_o ?
      16'd139+{15'd0,gain_fraction_sum>=8'd147} : 16'd128;
  wire [23:0] lfo_delta=applied_rate_44100_o ?
      24'd379+{23'd0,lfo_fraction_sum>=9'd147} : 24'd349;
  wire config_accept=config_valid_i && config_ready_o;
  wire history_accept=history_clear_i && history_ready_o;
  wire local_history_clear=clear_i || config_accept || history_accept;
  assign quiescent_o=state==0 && !valid_o && !clear_i;
  assign config_ready_o=quiescent_o && !valid_i;
  assign history_ready_o=config_ready_o && !config_valid_i;
  assign ready_o=state==0 && !local_history_clear;
  function automatic [15:0] wet_slew(input [15:0] value,target,delta);
    logic [15:0] upper,lower;
    begin
      upper=value>16'hffff-delta ? 16'hffff : value+delta;
      lower=value<delta ? 16'd0 : value-delta;
      if(target>upper)wet_slew=upper;
      else if(target<lower)wet_slew=lower;
      else wet_slew=target;
    end
  endfunction
  function automatic [15:0] rate_delay(input [15:0] triangle_value,input logic rate44);
    logic [34:0] rounded_phase44;
    logic [17:0] triangle_times3;
    begin
      // Exact over all 16-bit triangles: preserve every nearest-rounded tap
      // while replacing the serial divide by5 with one affine product/shift.
      // The complete product and sum fit35 unsigned bits; sampling is unchanged.
      if(rate44)begin
        rounded_phase44=35'(triangle_value)*35'd361267+35'd134225920;
        rate_delay=16'd441+16'(rounded_phase44>>28);
      end else begin
        //48k: floor(96*t/65536) == floor(3*t/2048), preserving every tap.
        triangle_times3=18'(triangle_value)*18'd3;
        rate_delay=16'd480+16'(triangle_times3>>11);
      end
    end
  endfunction
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin
      applied_rate_44100_o<=0;config_applied_o<=0;history_done_o<=0;
      gain_remainder<=0;lfo_remainder<=0;
    end else begin
      config_applied_o<=config_accept;history_done_o<=config_accept || history_accept;
      if(config_accept)applied_rate_44100_o<=rate_44100_i;
      if(clear_i)gain_remainder<=0;
      else if(state==0 && valid_i && ready_o && applied_rate_44100_o)
        gain_remainder<=gain_fraction_sum>=8'd147 ? gain_fraction_sum-8'd147 : gain_fraction_sum;
      if(!local_history_clear && state==4 && applied_rate_44100_o)
        lfo_remainder<=8'(lfo_fraction_sum>=9'd147 ? lfo_fraction_sum-9'd147 : lfo_fraction_sum);
    end
  end
  assign active_o=gain!=0||enabled_i;
  assign triangle=lfo[23]?~lfo[22:7]:lfo[22:7];
  wire [15:0] next_chorus_delay=rate_delay(triangle,applied_rate_44100_o);
  always_ff @(posedge clk_i) begin
    if(!local_history_clear && state==1) begin read_l<=memory_l[read_address];read_r<=memory_r[read_address];end
    if(!local_history_clear && state==3) begin memory_l[pointer]<=input_l;memory_r[pointer]<=input_r;end
    // Scratch products are consumed only in state3 after this state2 write.
    // Reset/clear cancels the state, so stale DSP data cannot become an output.
    if(!local_history_clear && state==2) begin
      product_l<=$signed(frames>=chorus_delay?read_l:32'sd0)*$signed({1'b0,gain});
      product_r<=$signed(frames>=chorus_delay?read_r:32'sd0)*$signed({1'b0,gain});
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      pointer<=0;read_address<=0;frames<=0;state<=0;gain<=0;lfo<=0;chorus_delay<=CHORUS_BASE;
      valid_o<=0;clip_o<=0;input_l<=0;input_r<=0;
      mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;
    end else begin
      valid_o<=0;clip_o<=0;
      if(local_history_clear) begin
        pointer<=0;read_address<=0;frames<=0;state<=0;if(clear_i)gain<=0;valid_o<=0;clip_o<=0;
      end else case(state)
        0:if(valid_i && ready_o) begin
          input_l<=left_i;input_r<=right_i;chorus_delay<=next_chorus_delay;
          read_address<=pointer-CHORUS_BITS'(next_chorus_delay);gain<=wet_slew(gain,enabled_i?16'd8192:16'd0,gain_delta);state<=1;
        end
        1:state<=2;
        2:state<=3;
        3:begin mixed_l<=$signed(input_l)+rshift(product_l,15);mixed_r<=$signed(input_r)+rshift(product_r,15);state<=4;end
        4:begin
          left_o<=sat31(mixed_l);right_o<=sat31(mixed_r);valid_o<=1;
          clip_o<=mixed_l>64'sd2147483647||mixed_l< -64'sd2147483648||mixed_r>64'sd2147483647||mixed_r< -64'sd2147483648;
          pointer<=pointer+1'b1;if(frames!=32'hffffffff)frames<=frames+1'b1;lfo<=lfo+lfo_delta;state<=0;
        end
        default:state<=0;
      endcase
    end
  end
endmodule
