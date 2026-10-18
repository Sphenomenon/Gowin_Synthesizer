`timescale 1ns/1ps
`default_nettype none
// Synthesizable application/UTMI integration; also the host-BFM test boundary.
module midi_usb_bridge(
 input wire clk_50mhz,reset,clk_ulpi60,enable,
 input wire[7:0]utmi_rxdata,input wire utmi_rxvalid,utmi_rxactive,utmi_rxerror,
 input wire[1:0]utmi_linestate,input wire utmi_txready,
 output wire[7:0]utmi_txdata,output wire utmi_txvalid,
 output wire[1:0]utmi_opmode,utmi_xcvr,
 output wire utmi_termsel,utmi_dppd,utmi_dmpd,
 input wire midi_tx_valid,output wire midi_tx_ready,input wire[31:0]midi_tx_data,
 output wire midi_rx_valid,input wire midi_rx_ready,output wire[31:0]midi_rx_data,
 input wire control_tx_valid,output wire control_tx_ready,input wire[7:0]control_tx_data,
 output wire control_rx_valid,input wire control_rx_ready,output wire[7:0]control_rx_data,
 output wire online,control_reset,hs_active,
 output wire[2:0]phy_state,output wire[6:0]device_address
);
 wire configured,usb_session_reset,midi_session_reset,control_session_reset,usb_hs;
 wire mt_valid,mt_ready,mr_valid,mr_ready,ct_valid,ct_ready,cr_valid,cr_ready;
 wire[31:0]mt_data,mr_data;wire[7:0]ct_data,cr_data;
 wire midi_flush=reset||midi_session_reset,control_flush=reset||control_session_reset;
 (* ASYNC_REG="TRUE" *)reg[1:0]online_release,control_release,hs_sync;
 always @(posedge clk_50mhz or posedge midi_flush)
  if(midi_flush)online_release<=0;else online_release<={online_release[0],1'b1};
 always @(posedge clk_50mhz or posedge control_flush)
  if(control_flush)control_release<=0;else control_release<={control_release[0],1'b1};
 always @(posedge clk_50mhz or posedge reset)
  if(reset)hs_sync<=0;else hs_sync<={hs_sync[0],usb_hs};
 assign online=online_release[1];
 // Held high while unavailable; asserts asynchronously, releases in app clk.
 // This clears partial vendor frames and response bytes across USB sessions.
 wire control_online=control_release[1];
 assign control_reset=!control_online;
 assign hs_active=hs_sync[1];
 wire mt_space,ct_space,mr_available,cr_available;
 assign midi_tx_ready=online&&mt_space;
 assign control_tx_ready=control_online&&ct_space;
 assign midi_rx_valid=online&&mr_available;
 assign control_rx_valid=control_online&&cr_available;
 midi_usb_async_fifo #(.WIDTH(32),.ADDR_BITS(6)) midi_to_usb(
  .reset(midi_flush),.wr_clk(clk_50mhz),.wr_valid(midi_tx_valid&&online),.wr_ready(mt_space),.wr_data(midi_tx_data),
  .rd_clk(clk_ulpi60),.rd_valid(mt_valid),.rd_ready(mt_ready),.rd_data(mt_data));
 midi_usb_async_fifo #(.WIDTH(32),.ADDR_BITS(6)) midi_from_usb(
  .reset(midi_flush),.wr_clk(clk_ulpi60),.wr_valid(mr_valid),.wr_ready(mr_ready),.wr_data(mr_data),
  .rd_clk(clk_50mhz),.rd_valid(mr_available),.rd_ready(midi_rx_ready&&online),.rd_data(midi_rx_data));
 midi_usb_async_fifo #(.WIDTH(8),.ADDR_BITS(8)) control_to_usb(
  .reset(control_flush),.wr_clk(clk_50mhz),.wr_valid(control_tx_valid&&control_online),.wr_ready(ct_space),.wr_data(control_tx_data),
  .rd_clk(clk_ulpi60),.rd_valid(ct_valid),.rd_ready(ct_ready),.rd_data(ct_data));
 midi_usb_async_fifo #(.WIDTH(8),.ADDR_BITS(8)) control_from_usb(
  .reset(control_flush),.wr_clk(clk_ulpi60),.wr_valid(cr_valid),.wr_ready(cr_ready),.wr_data(cr_data),
  .rd_clk(clk_50mhz),.rd_valid(cr_available),.rd_ready(control_rx_ready&&control_online),.rd_data(control_rx_data));
 midi_usb_device device(
  .clk(clk_ulpi60),.reset(reset),.enable(enable),
  .utmi_rxdata(utmi_rxdata),.utmi_rxvalid(utmi_rxvalid),.utmi_rxactive(utmi_rxactive),.utmi_rxerror(utmi_rxerror),
  .utmi_linestate(utmi_linestate),.utmi_txready(utmi_txready),
  .utmi_txdata(utmi_txdata),.utmi_txvalid(utmi_txvalid),.utmi_opmode(utmi_opmode),.utmi_xcvr(utmi_xcvr),
  .utmi_termsel(utmi_termsel),.utmi_dppd(utmi_dppd),.utmi_dmpd(utmi_dmpd),
  .midi_tx_valid(mt_valid),.midi_tx_ready(mt_ready),.midi_tx_data(mt_data),
  .midi_rx_valid(mr_valid),.midi_rx_ready(mr_ready),.midi_rx_data(mr_data),
  .control_tx_valid(ct_valid),.control_tx_ready(ct_ready),.control_tx_data(ct_data),
  .control_rx_valid(cr_valid),.control_rx_ready(cr_ready),.control_rx_data(cr_data),
  .configured(configured),.session_reset(usb_session_reset),.midi_session_reset(midi_session_reset),
  .control_session_reset(control_session_reset),.hs_active(usb_hs),
  .phy_state(phy_state),.device_address(device_address));
endmodule
`default_nettype wire
