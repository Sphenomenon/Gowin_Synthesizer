`timescale 1ns/1ps
`default_nettype none
module midi_keyboard_application #(
 parameter integer CLK_HZ=50000000,
 parameter integer FIFO_DEPTH=32,
 parameter integer HOST_PANEL_CONTROLS=1,
 parameter integer PLUCK_ENABLED=0
)(
 input wire clk,reset,control_reset,
 input wire usb_online,ble_online,
 input wire [799:0] touch_diagnostics,
 input wire [511:0] pluck_diagnostics,
 input wire [511:0] pluck_noise_diagnostics,
 input wire pluck_diagnostics_valid,
 output wire input_config_write,
 output wire [7:0] input_config_opcode,
 output wire [31:0] input_config_value,
 input wire [15:0] key_bitmap,
 input wire keypad_ready,slider_valid,slider_touch,
 input wire [7:0] slider_position,
 input wire enc1_step,enc1_press,enc2_step,enc2_press,
 input wire signed [1:0] enc1_direction,enc2_direction,
 output wire usb_packet_tx_valid,input wire usb_packet_tx_ready,output wire [31:0]usb_packet_tx_data,
 input wire usb_packet_rx_valid,output wire usb_packet_rx_ready,input wire [31:0]usb_packet_rx_data,
 output wire ble_value_tx_valid,input wire ble_value_tx_ready,output wire[39:0]ble_value_tx_data,output wire[2:0]ble_value_tx_length,
 input wire ble_value_rx_valid,output wire ble_value_rx_ready,input wire[39:0]ble_value_rx_data,input wire[2:0]ble_value_rx_length,
 input wire control_rx_valid,output wire control_rx_ready,input wire[7:0]control_rx_data,
 output wire control_tx_valid,input wire control_tx_ready,output wire[7:0]control_tx_data,
 output wire[3:0]midi_channel,output wire signed[7:0]transpose,
 output wire[6:0]velocity,program_number,output wire[1:0]slider_mode,
 output wire[7:0]brightness,strip_value,output wire[2:0]focus,
 output wire[15:0]active_keys,output wire[15:0]lamp_keys,
 output wire panic_busy,output wire[15:0]theme_rgb565,clear_rgb565,
 output wire[3:0]screen_page,output wire screen_update,
 output wire[31:0]status_flags,emitted_events
);
 localparam integer MS_TICKS=CLK_HZ/1000;
 reg[31:0]ms_count;
 reg[12:0]timestamp_ms;
 always @(posedge clk)begin
  if(reset)begin ms_count<=0;timestamp_ms<=0;end
  else if(ms_count==MS_TICKS-1)begin ms_count<=0;timestamp_ms<=timestamp_ms+1'b1;end
  else ms_count<=ms_count+1'b1;
 end
 wire cfg_write;wire[7:0]cfg_opcode;wire[31:0]cfg_value;
 assign input_config_write=cfg_write;
 assign input_config_opcode=cfg_opcode;
 assign input_config_value=cfg_value;
 wire[15:0]control_errors;
 screen_control_endpoint #(.PLUCK_ENABLED(PLUCK_ENABLED),.PLUCK_VPP_CONTROL(PLUCK_ENABLED),
                           .PLUCK_NOISE_DIAGNOSTICS(PLUCK_ENABLED)) controls(
  .pluck_diagnostics(pluck_diagnostics),
  .pluck_noise_diagnostics(pluck_noise_diagnostics),
  .pluck_diagnostics_valid(pluck_diagnostics_valid),
  .clk(clk),.reset(reset||control_reset),.rx_valid(control_rx_valid),.rx_ready(control_rx_ready),.rx_data(control_rx_data),
  .tx_valid(control_tx_valid),.tx_ready(control_tx_ready),.tx_data(control_tx_data),.status_flags(status_flags),.touch_diagnostics(touch_diagnostics),
  .midi_channel(),.transpose(),.screen_page(screen_page),.theme_rgb565(theme_rgb565),.clear_rgb565(clear_rgb565),
  .screen_update(screen_update),.protocol_errors(control_errors),
  .config_write(cfg_write),.config_opcode(cfg_opcode),.config_value(cfg_value));
 wire event_valid,event_ready;wire[23:0]event_message;wire[1:0]event_length,event_targets;wire[12:0]event_timestamp;
 generate if(HOST_PANEL_CONTROLS)begin:host_panel
 gw138k_panel_performance performance(
  .clk(clk),.reset(reset),.key_bitmap(key_bitmap),.keypad_ready(keypad_ready),
  .slider_valid(slider_valid),.slider_touch(slider_touch),.slider_position(slider_position),
  .enc1_step(enc1_step),.enc1_press(enc1_press),.enc2_step(enc2_step),.enc2_press(enc2_press),
  .enc1_direction(enc1_direction),.enc2_direction(enc2_direction),
  .config_write(cfg_write),.config_opcode(cfg_opcode),.config_value(cfg_value),
  .online({ble_online,usb_online}),.timestamp_ms(timestamp_ms),
  .event_valid(event_valid),.event_ready(event_ready),.event_message(event_message),
  .event_length(event_length),.event_timestamp(event_timestamp),.event_targets(event_targets),
  .midi_channel(midi_channel),.transpose(transpose),.velocity(velocity),.slider_mode(slider_mode),
  .program_number(program_number),.brightness(brightness),.focus(focus),.active_keys(active_keys),
  .strip_value(strip_value),.panic_busy(panic_busy),.emitted_events(emitted_events));
 end else begin:legacy_controls
 midi_performance performance(
  .clk(clk),.reset(reset),.key_bitmap(key_bitmap),.keypad_ready(keypad_ready),
  .slider_valid(slider_valid),.slider_touch(slider_touch),.slider_position(slider_position),
  .enc1_step(enc1_step),.enc1_press(enc1_press),.enc2_step(enc2_step),.enc2_press(enc2_press),
  .enc1_direction(enc1_direction),.enc2_direction(enc2_direction),
  .config_write(cfg_write),.config_opcode(cfg_opcode),.config_value(cfg_value),
  .online({ble_online,usb_online}),.timestamp_ms(timestamp_ms),
  .event_valid(event_valid),.event_ready(event_ready),.event_message(event_message),
  .event_length(event_length),.event_timestamp(event_timestamp),.event_targets(event_targets),
  .midi_channel(midi_channel),.transpose(transpose),.velocity(velocity),.slider_mode(slider_mode),
  .program_number(program_number),.brightness(brightness),.focus(focus),.active_keys(active_keys),
  .strip_value(strip_value),.panic_busy(panic_busy),.emitted_events(emitted_events));
 end endgenerate
 wire u_valid,u_ready,b_valid,b_ready,u_full,b_full;
 wire[23:0]u_message,b_message;wire[1:0]u_length,b_length;wire[12:0]u_timestamp,b_timestamp;
 wire[15:0]unrouted;
 midi_event_router #(.FIFO_DEPTH(FIFO_DEPTH),.PANEL_EVENTS(HOST_PANEL_CONTROLS)) router(
  .clk(clk),.reset(reset),.in_valid(event_valid),.in_ready(event_ready),
  .in_message(event_message),.in_length(event_length),.in_timestamp(event_timestamp),.in_targets(event_targets),
  .usb_online(usb_online),.ble_online(ble_online),
  .usb_valid(u_valid),.usb_ready(u_ready),.usb_message(u_message),.usb_length(u_length),.usb_timestamp(u_timestamp),
  .ble_valid(b_valid),.ble_ready(b_ready),.ble_message(b_message),.ble_length(b_length),.ble_timestamp(b_timestamp),
  .usb_full(u_full),.ble_full(b_full),.unrouted_events(unrouted));
 wire urx_valid,urx_ready,brx_valid,brx_ready;
 wire[23:0]urx_message,brx_message;wire[1:0]urx_length,brx_length;wire[12:0]brx_timestamp;
 wire[15:0]utx_errors,urx_errors,btx_errors,brx_errors;
 wire utx_valid_internal,urx_ready_internal,btx_valid_internal,brx_ready_internal;
 wire ureset=reset||!usb_online,breset=reset||!ble_online;
 assign usb_packet_tx_valid=utx_valid_internal&&!ureset;
 assign usb_packet_rx_ready=urx_ready_internal&&!ureset;
 assign ble_value_tx_valid=btx_valid_internal&&!breset;
 assign ble_value_rx_ready=brx_ready_internal&&!breset;
 wire usb_send_valid,usb_send_ready;
 wire [23:0] usb_send_message;wire [1:0] usb_send_length;
 midi_ble_usb_bridge ble_usb(
  .clk(clk),.reset(reset),.usb_online(usb_online),.ble_online(ble_online),
  .local_valid(u_valid),.local_ready(u_ready),.local_message(u_message),.local_length(u_length),
  .phone_valid(brx_valid&&!breset),.phone_ready(brx_ready),.phone_message(brx_message),.phone_length(brx_length),
  .out_valid(usb_send_valid),.out_ready(usb_send_ready),.out_message(usb_send_message),.out_length(usb_send_length));
 usb_midi_codec ucodec(
  .clk(clk),.reset(ureset),.tx_valid(usb_send_valid),.tx_ready(usb_send_ready),.tx_message(usb_send_message),.tx_length(usb_send_length),
  .packet_tx_valid(utx_valid_internal),.packet_tx_ready(usb_packet_tx_ready),.packet_tx_data(usb_packet_tx_data),
  .packet_rx_valid(usb_packet_rx_valid&&!ureset),.packet_rx_ready(urx_ready_internal),.packet_rx_data(usb_packet_rx_data),
  .rx_valid(urx_valid),.rx_ready(urx_ready),.rx_message(urx_message),.rx_length(urx_length),
  .tx_errors(utx_errors),.rx_errors(urx_errors));
 ble_midi_codec bcodec(
  .clk(clk),.reset(breset),.tx_valid(b_valid),.tx_ready(b_ready),.tx_message(b_message),.tx_length(b_length),.timestamp_ms(b_timestamp),
  .value_tx_valid(btx_valid_internal),.value_tx_ready(ble_value_tx_ready),.value_tx_data(ble_value_tx_data),.value_tx_length(ble_value_tx_length),
  .value_rx_valid(ble_value_rx_valid&&!breset),.value_rx_ready(brx_ready_internal),.value_rx_data(ble_value_rx_data),.value_rx_length(ble_value_rx_length),
  .rx_valid(brx_valid),.rx_ready(brx_ready),.rx_message(brx_message),.rx_length(brx_length),.rx_timestamp(brx_timestamp),
  .tx_errors(btx_errors),.rx_errors(brx_errors));
 assign urx_ready=1'b1;
 wire host_usb=urx_valid&&!ureset;
 wire host_ble=brx_valid&&brx_ready&&!breset;
 reg[15:0]remote_usb,remote_ble;
 reg[3:0]previous_channel;
 reg signed[7:0]previous_transpose;
 function [15:0] feedback;
  input [15:0] previous;
  input [23:0] message;
  integer note_index;
  begin
   feedback=previous;
   note_index=$signed({1'b0,message[14:8]})-48-$signed(transpose);
   if(message[19:16]==midi_channel)begin
    if(message[23:20]==4'hb && (message[15:8]==120 || message[15:8]==123))feedback=0;
    else if(note_index>=0 && note_index<16 && (message[23:20]==9 || message[23:20]==8))
     feedback[note_index]=message[23:20]==9 && message[6:0]!=0;
   end
  end
 endfunction
 always @(posedge clk)begin
  if(reset)begin remote_usb<=0;remote_ble<=0;previous_channel<=0;previous_transpose<=0;end
  else begin
   previous_channel<=midi_channel;previous_transpose<=transpose;
   if(previous_channel!=midi_channel || previous_transpose!=transpose)begin remote_usb<=0;remote_ble<=0;end
   else begin
    if(!usb_online)remote_usb<=0;
    if(!ble_online)remote_ble<=0;
    if(host_usb)remote_usb<=feedback(remote_usb,urx_message);
    if(host_ble)remote_ble<=feedback(remote_ble,brx_message);
   end
  end
 end
 assign lamp_keys=key_bitmap|remote_usb|remote_ble;
 assign status_flags={20'd0,(btx_errors!=0),(utx_errors!=0),(brx_errors!=0),(urx_errors!=0),
  (control_errors!=0),(unrouted!=0),panic_busy,(active_keys!=0),b_full,u_full,ble_online,usb_online};
endmodule
`default_nettype wire
