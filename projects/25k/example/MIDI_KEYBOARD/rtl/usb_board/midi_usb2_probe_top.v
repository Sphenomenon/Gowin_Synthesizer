`timescale 1ns/1ps
`include "usb2_debug_profile.vh"
`ifdef MIDI_USB2_PROBE
`default_nettype none
module midi_usb2_probe_top #(parameter integer ATTACH_DELAY_CYCLES=12500000)(
 input wire clk_50mhz,clk_ulpi60,
 inout wire[7:0]ulpi_data,input wire ulpi_dir,ulpi_nxt,
 output wire ulpi_stp,led_ready,led_done
);
 reg[12:0]powerup=0;
 wire reset=!powerup[12];
 always @(posedge clk_50mhz)if(reset)powerup<=powerup+1'b1;
 wire midi_valid,midi_ready,online,control_reset,hs_active;
 wire[31:0]midi_data,usb_status,probe_history,event_status;
 wire[191:0]probe_statistics,statistics_status;
 midi_usb2_link #(.ATTACH_DELAY_CYCLES(ATTACH_DELAY_CYCLES)) usb(
  .clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),.reset(reset),
  .ulpi_data(ulpi_data),.ulpi_dir(ulpi_dir),.ulpi_nxt(ulpi_nxt),.ulpi_stp(ulpi_stp),
  .midi_tx_valid(midi_valid),.midi_tx_ready(midi_ready),.midi_tx_data(midi_data),
  .midi_rx_valid(midi_valid),.midi_rx_ready(midi_ready),.midi_rx_data(midi_data),
  .control_tx_valid(1'b0),.control_tx_ready(),.control_tx_data(8'd0),
  .control_rx_valid(),.control_rx_ready(1'b1),.control_rx_data(),
  .online(online),.control_reset(control_reset),.hs_active(hs_active),
  .debug_status(usb_status),.probe_history(probe_history),.probe_statistics(probe_statistics));
 midi_usb2_debug event_monitor(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .source_status(probe_history),.local_snapshot(32'd0),
  .local_flags({online,hs_active,!control_reset}),.status_50mhz(event_status));
 midi_usb2_debug raw_se0_monitor(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .source_status(probe_statistics[31:0]),.local_snapshot(32'd0),
  .local_flags({online,hs_active,!control_reset}),.status_50mhz(statistics_status[31:0]));
 midi_usb2_debug utmi_se0_monitor(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .source_status(probe_statistics[63:32]),.local_snapshot(32'd0),
  .local_flags({online,hs_active,!control_reset}),.status_50mhz(statistics_status[63:32]));
 midi_usb2_debug rxcmd_monitor(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .source_status(probe_statistics[95:64]),.local_snapshot(32'd0),
  .local_flags({online,hs_active,!control_reset}),.status_50mhz(statistics_status[95:64]));
 midi_usb2_debug phy_rx_monitor(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .source_status(probe_statistics[127:96]),.local_snapshot(32'd0),
  .local_flags({online,hs_active,!control_reset}),.status_50mhz(statistics_status[127:96]));
 midi_usb2_debug utmi_rx_monitor(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .source_status(probe_statistics[159:128]),.local_snapshot(32'd0),
  .local_flags({online,hs_active,!control_reset}),.status_50mhz(statistics_status[159:128]));
 midi_usb2_debug link_nxt_monitor(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .source_status(probe_statistics[191:160]),.local_snapshot(32'd0),
  .local_flags({online,hs_active,!control_reset}),.status_50mhz(statistics_status[191:160]));
 reg[255:0]status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
 always @(posedge clk_50mhz)status_50mhz<={statistics_status,event_status,usb_status};
 assign led_ready=!reset;
 assign led_done=online;
endmodule
`default_nettype wire
`endif
