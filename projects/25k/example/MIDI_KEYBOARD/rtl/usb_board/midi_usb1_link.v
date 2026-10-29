`timescale 1ns/1ps
`default_nettype none
module midi_usb1_link(
 input wire clk_50mhz,reset,
 inout wire usb1_dp,usb1_dm,
 input wire midi_tx_valid,output wire midi_tx_ready,input wire[31:0]midi_tx_data,
 output wire midi_rx_valid,input wire midi_rx_ready,output wire[31:0]midi_rx_data,
 input wire control_tx_valid,output wire control_tx_ready,input wire[7:0]control_tx_data,
 output wire control_rx_valid,input wire control_rx_ready,output wire[7:0]control_rx_data,
 output wire online,control_reset
);
 wire clk_usb,clock_ready;
 midi_usb1_clock clock(.clk_50m(clk_50mhz),.clk_48m(clk_usb),.locked_o(),.reset_n_o(clock_ready));
 wire reset_request=reset||!clock_ready;
 (* ASYNC_REG="TRUE",syn_preserve=1 *)reg[2:0]release_q=0;
 always @(posedge clk_usb or posedge reset_request)
  if(reset_request)release_q<=0;else release_q<={release_q[1:0],1'b1};
 wire reset_usb=!release_q[2];
 wire[7:0]rx_data,tx_data;
 wire rx_valid,rx_active,rx_error,tx_valid,tx_ready;
 wire[1:0]line_state,opmode,xcvr;
 wire termsel,dppd,dmpd;
 workstation_usb1_phy phy(.clk_usb(clk_usb),.reset_n(!reset_usb),.usb_dp(usb1_dp),.usb_dm(usb1_dm),
  .tx_data_i(tx_data),.tx_valid_i(tx_valid),.tx_ready_o(tx_ready),
  .rx_data_o(rx_data),.rx_valid_o(rx_valid),.rx_active_o(rx_active),.rx_error_o(rx_error),
  .line_state_o(line_state),.op_mode_i(opmode),.xcvr_select_i(xcvr),
  .term_select_i(termsel),.dp_pulldown_i(dppd),.dm_pulldown_i(dmpd));
 midi_usb_bridge #(.FULL_SPEED_ONLY(1)) bridge(
  .clk_50mhz(clk_50mhz),.reset(reset_usb),.clk_ulpi60(clk_usb),.enable(!reset_usb),
  .utmi_rxdata(rx_data),.utmi_rxvalid(rx_valid),.utmi_rxactive(rx_active),.utmi_rxerror(rx_error),
  .utmi_linestate(line_state),.utmi_txready(tx_ready),.utmi_txdata(tx_data),.utmi_txvalid(tx_valid),
  .utmi_opmode(opmode),.utmi_xcvr(xcvr),.utmi_termsel(termsel),.utmi_dppd(dppd),.utmi_dmpd(dmpd),
  .midi_tx_valid(midi_tx_valid),.midi_tx_ready(midi_tx_ready),.midi_tx_data(midi_tx_data),
  .midi_rx_valid(midi_rx_valid),.midi_rx_ready(midi_rx_ready),.midi_rx_data(midi_rx_data),
  .control_tx_valid(control_tx_valid),.control_tx_ready(control_tx_ready),.control_tx_data(control_tx_data),
  .control_rx_valid(control_rx_valid),.control_rx_ready(control_rx_ready),.control_rx_data(control_rx_data),
  .online(online),.control_reset(control_reset),.hs_active(),.phy_state(),.device_address());
endmodule
`default_nettype wire
