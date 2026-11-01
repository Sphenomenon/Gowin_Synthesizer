`timescale 1ns/1ps
`default_nettype none
module midi_pluck_probe_top #(
 parameter integer ATTACH_DELAY_CYCLES=12500000
)(
 input wire clk_50mhz,clk_ulpi60,
 inout wire [7:0] ulpi_data,
 input wire ulpi_dir,ulpi_nxt,
 output wire ulpi_stp,led_ready,led_done,
 input wire pluck_busy,pluck_douta,pluck_doutb,
 output wire pluck_convst,pluck_cs_n,pluck_sclk,pluck_ws2812,
 output wire [4:0] pluck_emitters
);
 reg [19:0] powerup=0;
 wire reset=!(&powerup);
 always @(posedge clk_50mhz)if(reset)powerup<=powerup+1'b1;
 wire online,control_reset,hs_active;
 wire packet_valid,packet_ready;
 wire [31:0] packet;
 wire control_rx_valid,control_rx_ready,control_tx_valid,control_tx_ready;
 wire [7:0] control_rx_data,control_tx_data;
 wire config_write;
 wire [7:0] config_opcode;
 wire [31:0] config_value;
 wire [3:0] channel;
 wire signed [7:0] transpose;
 wire [15:0] keys;
 wire ready,diagnostics_valid;
 wire [511:0] diagnostics;
 wire [511:0] noise_diagnostics;
 wire [15:0] protocol_errors,tx_errors,active_keys;
 wire panic_busy;
 wire [31:0] status_flags={20'd0,1'b0,(tx_errors!=0),2'd0,(protocol_errors!=0),
                          1'b0,panic_busy,(active_keys!=0),3'd0,online};
 wire emitter_arm;
 reg [15:0] on_threshold=64,off_threshold=32;
 wire recalibrate=config_write && config_opcode==8'h05;
 always @(posedge clk_50mhz)begin
  if(reset || control_reset || !online)begin on_threshold<=64;off_threshold<=32;end
  else if(recalibrate)begin on_threshold<=config_value[15:0];off_threshold<=config_value[31:16];end
 end
 midi_pluck_emitter_guard emitter_guard(
  .clk(clk_50mhz),.reset(reset),.control_reset(control_reset),.online(online && diagnostics[32]),
  .config_write(config_write),.config_opcode(config_opcode),.config_value(config_value),.armed(emitter_arm));
 midi_pluck_frontend #(.SAMPLE_HZ(25000),.DIAGNOSTIC_DETAILS(1),.DIAGNOSTIC_ONLY(1),.VPP_MODE(1),.CARRIER_MODE(1)) pluck(
  .clk(clk_50mhz),.reset(reset),.emitter_arm(emitter_arm),
  .on_threshold(on_threshold),.off_threshold(off_threshold),.recalibrate(recalibrate),
  .adc_busy(pluck_busy),.adc_douta(pluck_douta),.adc_doutb(pluck_doutb),
  .adc_convst(pluck_convst),.adc_cs_n(pluck_cs_n),.adc_sclk(pluck_sclk),.emitter_enable(pluck_emitters),
  .midi_channel(channel),.transpose(transpose),.key_bitmap(keys),.ready(ready),
  .diagnostics(diagnostics),.noise_diagnostics(noise_diagnostics),.diagnostics_valid(diagnostics_valid));
 assign pluck_ws2812=0;
 screen_control_endpoint #(.PLUCK_ENABLED(1),.PLUCK_EMITTER_CONTROL(1),.PLUCK_VPP_CONTROL(1),.PLUCK_NOISE_DIAGNOSTICS(1)) controls(
  .clk(clk_50mhz),.reset(reset || control_reset || !online),
  .rx_valid(control_rx_valid),.rx_ready(control_rx_ready),.rx_data(control_rx_data),
  .tx_valid(control_tx_valid),.tx_ready(control_tx_ready),.tx_data(control_tx_data),
  .status_flags(status_flags),.touch_diagnostics(800'd0),.protocol_errors(protocol_errors),
  .pluck_diagnostics(diagnostics),.pluck_diagnostics_valid(diagnostics_valid),
  .pluck_noise_diagnostics(noise_diagnostics),
  .config_write(config_write),.config_opcode(config_opcode),.config_value(config_value));
 wire event_valid,event_ready;
 wire [23:0] event_message;
 wire [1:0] event_length;
 gw138k_panel_performance performance(
  .clk(clk_50mhz),.reset(reset),.key_bitmap(keys),.keypad_ready(ready),
  .slider_valid(1'b0),.slider_touch(1'b0),.slider_position(8'd128),
  .enc1_step(1'b0),.enc1_press(1'b0),.enc2_step(1'b0),.enc2_press(1'b0),
  .enc1_direction(2'd0),.enc2_direction(2'd0),
  .config_write(config_write),.config_opcode(config_opcode),.config_value(config_value),
  .online({1'b0,online}),.timestamp_ms(13'd0),
  .event_valid(event_valid),.event_ready(event_ready),.event_message(event_message),.event_length(event_length),
  .midi_channel(channel),.transpose(transpose),.active_keys(active_keys),.panic_busy(panic_busy));
 usb_midi_codec codec(
  .clk(clk_50mhz),.reset(reset || control_reset),
  .tx_valid(event_valid && online),.tx_ready(event_ready),.tx_message(event_message),.tx_length(event_length),
  .packet_tx_valid(packet_valid),.packet_tx_ready(packet_ready),.packet_tx_data(packet),
  .packet_rx_valid(1'b0),.packet_rx_data(32'd0),.rx_ready(1'b1),.tx_errors(tx_errors));
 midi_usb2_link #(.ATTACH_DELAY_CYCLES(ATTACH_DELAY_CYCLES)) usb(
  .clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),.reset(reset),
  .ulpi_data(ulpi_data),.ulpi_dir(ulpi_dir),.ulpi_nxt(ulpi_nxt),.ulpi_stp(ulpi_stp),
  .midi_tx_valid(packet_valid),.midi_tx_ready(packet_ready),.midi_tx_data(packet),
  .midi_rx_valid(),.midi_rx_ready(1'b1),.midi_rx_data(),
  .control_tx_valid(control_tx_valid),.control_tx_ready(control_tx_ready),.control_tx_data(control_tx_data),
  .control_rx_valid(control_rx_valid),.control_rx_ready(control_rx_ready),.control_rx_data(control_rx_data),
  .online(online),.control_reset(control_reset),.hs_active(hs_active));
 assign led_ready=ready;
 assign led_done=online;
endmodule
`default_nettype wire
