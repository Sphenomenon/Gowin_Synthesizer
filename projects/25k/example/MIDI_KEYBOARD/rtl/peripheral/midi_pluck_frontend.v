`timescale 1ns/1ps
`default_nettype none
module midi_pluck_frontend #(
 parameter integer CLK_HZ=50000000,
 parameter integer SAMPLE_HZ=4000,
 parameter integer DIAGNOSTIC_DETAILS=0,
 parameter integer DIAGNOSTIC_ONLY=0,
 parameter integer VPP_MODE=0,
 parameter integer ADAPTIVE_NOISE=0,
 parameter integer CARRIER_MODE=0,
 parameter integer PROBE_IDENTITY=DIAGNOSTIC_ONLY,
 parameter integer SERIAL_CARRIER=0
)(
 input wire clk,reset,adc_busy,adc_douta,adc_doutb,
 input wire emitter_arm,
 input wire [15:0] on_threshold,off_threshold,
 input wire recalibrate,
 input wire [3:0] midi_channel,
 input wire signed [7:0] transpose,
 output wire adc_convst,adc_cs_n,adc_sclk,
 output wire [4:0] emitter_enable,
 output wire [15:0] key_bitmap,
 output wire ready,
 output wire [511:0] diagnostics,
 output wire [511:0] noise_diagnostics,
 output wire diagnostics_valid
);
 wire sample_valid,online,busy_observed,calibrated;
 wire [127:0] adc_samples;
 wire [95:0] physical_samples={adc_samples[95:80],adc_samples[15:0],adc_samples[31:16],
                              adc_samples[47:32],adc_samples[63:48],adc_samples[79:64]};
 wire [31:0] sample_count,trigger_count;
 wire [15:0] timeouts;
 wire [4:0] gates;
 wire frame_valid,sample_ready;
 reg [4:0] committed_gates;
 wire [15:0] overruns;
 wire [79:0] amplitudes,trigger_counts;
 wire [79:0] noise_floor,on_levels,off_levels,current_vpp;
 wire [4:0] valid_channels;
 wire [15:0] calibration_windows_done;
 localparam [15:0] RATE=SAMPLE_HZ;
 localparam DETAILS_ENABLED=DIAGNOSTIC_DETAILS!=0;
 localparam PROBE_ENABLED=PROBE_IDENTITY!=0;
 localparam VPP_ENABLED=VPP_MODE!=0;
 localparam NOISE_ENABLED=VPP_MODE!=0 && ADAPTIVE_NOISE!=0;
 localparam CARRIER_ENABLED=VPP_MODE!=0 && CARRIER_MODE!=0;
 localparam [15:0] CALIBRATION_LENGTH=CARRIER_MODE ? 500 : ADAPTIVE_NOISE ? 100 : 16;
 localparam [15:0] WINDOW_LENGTH=VPP_MODE ? SAMPLE_HZ/(CARRIER_MODE ? 500 : 100) : 0;
 wire [15:0] active_on=VPP_MODE ? on_threshold : 16'd1024;
 wire [15:0] active_off=VPP_MODE ? off_threshold : 16'd512;
 wire emitters_on=!reset && (!DIAGNOSTIC_ONLY || emitter_arm);
 reg previous_emitters_on,previous_online;
 always @(posedge clk)begin
  if(reset)begin previous_emitters_on<=0;previous_online<=0;end
  else begin previous_emitters_on<=emitters_on;previous_online<=online;end
 end
 midi_pluck_adc #(.CLK_HZ(CLK_HZ),.SAMPLE_HZ(SAMPLE_HZ)) adc(
  .clk(clk),.reset(reset),.adc_busy(adc_busy),.adc_douta(adc_douta),.adc_doutb(adc_doutb),
  .adc_convst(adc_convst),.adc_cs_n(adc_cs_n),.adc_sclk(adc_sclk),
  .sample_valid(sample_valid),.online(online),.samples(adc_samples),
  .sample_count(sample_count),.timeouts(timeouts),.busy_observed(busy_observed));
 generate if(VPP_MODE && CARRIER_MODE && SERIAL_CARRIER)begin:serial_carrier
 midi_pluck_carrier_engine #(.WINDOW_SAMPLES(WINDOW_LENGTH),.STABLE_INPUT(1)) detector(
  .clk(clk),.reset(reset),.online(online),.enable(!DIAGNOSTIC_ONLY || emitter_arm),.recalibrate(recalibrate),
  .sample_valid(sample_valid),.samples(physical_samples[79:0]),.on_threshold(active_on),.off_threshold(active_off),
  .calibrated(calibrated),.frame_valid(frame_valid),.sample_ready(sample_ready),.overruns(overruns),
  .noise_floor(noise_floor),.on_levels(on_levels),.off_levels(off_levels),.current_vpp(current_vpp),
  .valid_channels(valid_channels),.calibration_windows_done(calibration_windows_done),
  .gates(gates),.amplitudes(amplitudes),.trigger_counts(trigger_counts),.trigger_count(trigger_count));
 end else if(VPP_MODE)begin:vpp_mode
 midi_pluck_vpp_detector #(.WINDOW_SAMPLES(WINDOW_LENGTH),.CALIBRATION_WINDOWS(CALIBRATION_LENGTH),
                         .QUIET_WINDOWS(CARRIER_MODE ? 5 : ADAPTIVE_NOISE ? 3 : 1),.ADAPTIVE_NOISE(ADAPTIVE_NOISE),
                         .CARRIER_MODE(CARRIER_MODE),.SETTLE_WINDOWS(CARRIER_MODE ? 50 : 10),
                         .HOLD_WINDOWS(CARRIER_MODE ? 25 : 5),.DISPLAY_WINDOWS(CARRIER_MODE ? 100 : 20)) detector(
  .clk(clk),.reset(reset),.online(online),.enable(!DIAGNOSTIC_ONLY || emitter_arm),.recalibrate(recalibrate),
  .sample_valid(sample_valid),.samples(physical_samples[79:0]),.on_threshold(active_on),.off_threshold(active_off),
  .calibrated(calibrated),.frame_valid(frame_valid),.sample_ready(sample_ready),.overruns(overruns),
  .noise_floor(noise_floor),.on_levels(on_levels),.off_levels(off_levels),.current_vpp(current_vpp),
  .valid_channels(valid_channels),.calibration_windows_done(calibration_windows_done),
  .gates(gates),.amplitudes(amplitudes),.trigger_counts(trigger_counts),.trigger_count(trigger_count));
 end else begin:deviation_mode
 assign noise_floor=0;assign on_levels=0;assign off_levels=0;assign current_vpp=0;
 assign valid_channels=0;assign calibration_windows_done=0;
 midi_pluck_detector #(.SAMPLE_HZ(SAMPLE_HZ),.DIAGNOSTIC_DETAILS(DIAGNOSTIC_DETAILS)) detector(
  .clk(clk),.reset(reset),.online(online && (!DIAGNOSTIC_ONLY || emitter_arm)),.sample_valid(sample_valid),.samples(physical_samples[79:0]),
  .calibrated(calibrated),.frame_valid(frame_valid),.sample_ready(sample_ready),.overruns(overruns),.gates(gates),.amplitudes(amplitudes),
  .trigger_counts(trigger_counts),.trigger_count(trigger_count));
 end endgenerate
 midi_pluck_pwm #(.CLK_HZ(CLK_HZ)) emitters(.clk(clk),.reset(reset),.enable(emitters_on),.pwm(emitter_enable));
 assign ready=online&&calibrated;
 assign key_bitmap={11'd0,committed_gates} & {16{ready}};
 assign diagnostics_valid=!sample_valid && sample_ready && !frame_valid && !recalibrate &&
                          emitters_on==previous_emitters_on && online==previous_online;
 always @(posedge clk)begin
  if(reset)committed_gates<=0;
  else if(frame_valid)committed_gates<=gates;
 end
 assign diagnostics={WINDOW_LENGTH,overruns,16'd0,trigger_counts[79:64],trigger_counts[63:0],
                     RATE,transpose,4'd0,midi_channel,active_off,active_on,trigger_count,
                     16'd0,amplitudes,physical_samples,sample_count,
                     timeouts,CARRIER_ENABLED,NOISE_ENABLED,VPP_ENABLED,committed_gates,emitters_on,PROBE_ENABLED,DETAILS_ENABLED,adc_sclk,adc_cs_n,busy_observed,calibrated,online,
                     32'h314b4c50};
 assign noise_diagnostics={CALIBRATION_LENGTH,calibration_windows_done,
                           16'd0,current_vpp,16'd0,off_levels,16'd0,on_levels,16'd0,noise_floor,
                           19'd0,valid_channels,4'd0,CARRIER_ENABLED,emitters_on,calibrated,online,
                           sample_count,32'h314f4e50};
endmodule
`default_nettype wire
