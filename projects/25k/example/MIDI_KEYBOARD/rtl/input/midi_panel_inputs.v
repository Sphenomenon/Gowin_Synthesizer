`timescale 1ns/1ps
`default_nettype none
module midi_panel_inputs #(
 parameter integer CLK_HZ=50000000,
 parameter integer SAMPLE_HZ=25000
)(
 input wire clk,reset,control_reset,
 input wire [15:0] touch_keys,
 input wire touch_ready,touch_slider_valid,touch_slider_touch,
 input wire [7:0] touch_slider_position,
 input wire adc_busy,adc_douta,adc_doutb,
 input wire config_write,
 input wire [7:0] config_opcode,
 input wire [31:0] config_value,
 input wire [3:0] midi_channel,
 input wire signed [7:0] transpose,
 output wire adc_convst,adc_cs_n,adc_sclk,
 output wire [4:0] emitters,
 output wire [15:0] key_bitmap,
 output wire ready,slider_valid,slider_touch,
 output wire [7:0] slider_position,
 output wire [511:0] diagnostics,noise_diagnostics,
 output wire diagnostics_valid
);
 wire [15:0] pluck_keys;
 wire pluck_ready;
 wire emitter_arm=diagnostics[32] && !touch_ready;
 wire recalibrate=config_write && config_opcode==8'h05;
 reg [15:0] on_threshold=64,off_threshold=32;
 reg previous_touch_ready;
 always @(posedge clk)begin
  if(reset || control_reset)begin on_threshold<=64;off_threshold<=32;end
  else if(recalibrate)begin on_threshold<=config_value[15:0];off_threshold<=config_value[31:16];end
  if(reset)previous_touch_ready<=0;
  else previous_touch_ready<=touch_ready;
 end
 midi_pluck_frontend #(.CLK_HZ(CLK_HZ),.SAMPLE_HZ(SAMPLE_HZ),.DIAGNOSTIC_DETAILS(1),
                      .DIAGNOSTIC_ONLY(1),.VPP_MODE(1),.CARRIER_MODE(1),.PROBE_IDENTITY(0),.SERIAL_CARRIER(1)) pluck(
  .clk(clk),.reset(reset),.emitter_arm(emitter_arm),.on_threshold(on_threshold),.off_threshold(off_threshold),
  .recalibrate(recalibrate || control_reset),.midi_channel(midi_channel),.transpose(transpose),
  .adc_busy(adc_busy),.adc_douta(adc_douta),.adc_doutb(adc_doutb),
  .adc_convst(adc_convst),.adc_cs_n(adc_cs_n),.adc_sclk(adc_sclk),.emitter_enable(emitters),
  .key_bitmap(pluck_keys),.ready(pluck_ready),.diagnostics(diagnostics),
  .noise_diagnostics(noise_diagnostics),.diagnostics_valid(diagnostics_valid));
 assign key_bitmap=touch_ready!=previous_touch_ready ? 16'd0 : touch_ready ? touch_keys : pluck_keys;
 assign ready=touch_ready==previous_touch_ready && (touch_ready || pluck_ready);
 assign slider_valid=(touch_ready && touch_slider_valid) || (previous_touch_ready && !touch_ready);
 assign slider_touch=touch_ready && touch_slider_touch;
 assign slider_position=touch_ready ? touch_slider_position : 8'd128;
endmodule
`default_nettype wire
