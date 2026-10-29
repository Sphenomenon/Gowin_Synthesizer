`timescale 1ns/1ps
`include "usb2_debug_profile.vh"
`default_nettype none
// Physical USB3300 link. DATA ownership uses the same registered drive arm
// plus immediate DIR inhibit as the hardware-verified USB3300_HS reference.
module midi_usb2_link #(parameter integer ATTACH_DELAY_CYCLES=0)(
 input wire clk_50mhz,reset,clk_ulpi60,
 inout wire[7:0]ulpi_data,input wire ulpi_dir,ulpi_nxt,output wire ulpi_stp,
 input wire midi_tx_valid,output wire midi_tx_ready,input wire[31:0]midi_tx_data,
 output wire midi_rx_valid,input wire midi_rx_ready,output wire[31:0]midi_rx_data,
 input wire control_tx_valid,output wire control_tx_ready,input wire[7:0]control_tx_data,
 output wire control_rx_valid,input wire control_rx_ready,output wire[7:0]control_rx_data,
 output wire online,control_reset,hs_active
`ifdef MIDI_USB2_DIAGNOSTICS
 ,output wire[31:0]debug_status
`endif
`ifdef MIDI_USB2_PROBE
 ,output wire[31:0]probe_history
 ,output wire[191:0]probe_statistics
`endif
);
 (* ASYNC_REG="TRUE" *)reg[2:0]reset_sync=3'b111;
 always @(posedge clk_ulpi60 or posedge reset)
  if(reset)reset_sync<=3'b111;else reset_sync<={reset_sync[1:0],1'b0};
 wire reset60=reset_sync[2];
 wire boot_done,boot_error,boot_oe,boot_stp,boot_drive;
 wire[7:0]boot_data,pad_input,link_data;
 wire[7:0]boot_stage;
 wire[15:0]phy_vid,phy_pid;
 wire[2:0]phy_state;
 wire[6:0]device_address;
 wire link_stp;
 midi_usb2_boot boot(.clk_ulpi60(clk_ulpi60),.reset_n(!reset60),.data_i(pad_input),
  .data_o(boot_data),.data_oe(boot_oe),.drive_ready(boot_drive),
  .dir(ulpi_dir),.nxt(ulpi_nxt),.stp(boot_stp),.done(boot_done),.error(boot_error),
  .stage(boot_stage),.vid(phy_vid),.pid(phy_pid));
 wire protocol_reset=reset60||!boot_done||boot_error;
 wire bridge_reset;
 generate if(ATTACH_DELAY_CYCLES==0)begin:no_attach_delay
 assign bridge_reset=protocol_reset;
 end else begin:attach_delay
  reg[24:0]attach_count=0;
  reg attach_ready=0;
  (* ASYNC_REG="TRUE" *)reg[1:0]reset_release=0;
  always @(posedge clk_50mhz or posedge protocol_reset)
   if(protocol_reset)reset_release<=0;else reset_release<={reset_release[0],1'b1};
  wire attach_reset=!reset_release[1];
  always @(posedge clk_50mhz or posedge attach_reset)
   if(attach_reset)begin attach_count<=0;attach_ready<=0;end
   else if(!attach_ready)begin
    if(attach_count==ATTACH_DELAY_CYCLES-1)attach_ready<=1;
    else attach_count<=attach_count+1'b1;
   end
  (* ASYNC_REG="TRUE" *)reg[1:0]ready_sync=0;
  always @(posedge clk_ulpi60 or posedge protocol_reset)
   if(protocol_reset)ready_sync<=0;else ready_sync<={ready_sync[0],attach_ready};
  assign bridge_reset=protocol_reset||!ready_sync[1];
 end endgenerate
 reg wrapper_drive=0;
 always @(posedge clk_ulpi60)wrapper_drive<=!protocol_reset&&!ulpi_dir;
 wire drive_arm=boot_done?wrapper_drive:boot_drive;
 wire[7:0]pad_data=boot_done?link_data:boot_data;
 genvar i;
 generate for(i=0;i<8;i=i+1)begin:pads
  wire disabled;
  LUT2 #(.INIT(4'hB)) safety_gate(.I0(ulpi_dir),.I1(drive_arm),.F(disabled));
  IOBUF pad(.I(pad_data[i]),.O(pad_input[i]),.OEN(disabled),.IO(ulpi_data[i]));
 end endgenerate
 assign ulpi_stp=boot_done?link_stp:boot_stp;
 wire[7:0]utmi_rxdata,utmi_txdata;
 wire utmi_rxvalid,utmi_rxactive,utmi_rxerror,utmi_txready,utmi_txvalid;
 wire[1:0]line_state,opmode,xcvr;
 wire termsel,dppd,dmpd;
 midi_ulpi_wrapper ulpi(.ulpi_clk60_i(clk_ulpi60),.ulpi_rst_i(protocol_reset),
  .ulpi_data_out_i(pad_input),.ulpi_dir_i(ulpi_dir),.ulpi_nxt_i(ulpi_nxt),
  .ulpi_data_in_o(link_data),.ulpi_stp_o(link_stp),
  .utmi_data_out_i(utmi_txdata),.utmi_txvalid_i(utmi_txvalid),.utmi_txready_o(utmi_txready),
  .utmi_op_mode_i(opmode),.utmi_xcvrselect_i(xcvr),.utmi_termselect_i(termsel),
  .utmi_dppulldown_i(dppd),.utmi_dmpulldown_i(dmpd),
  .utmi_data_in_o(utmi_rxdata),.utmi_rxvalid_o(utmi_rxvalid),.utmi_rxactive_o(utmi_rxactive),
  .utmi_rxerror_o(utmi_rxerror),.utmi_linestate_o(line_state));
 midi_usb_bridge bridge(.clk_50mhz(clk_50mhz),.reset(bridge_reset),.clk_ulpi60(clk_ulpi60),.enable(!bridge_reset),
  .utmi_rxdata(utmi_rxdata),.utmi_rxvalid(utmi_rxvalid),.utmi_rxactive(utmi_rxactive),.utmi_rxerror(utmi_rxerror),
  .utmi_linestate(line_state),.utmi_txready(utmi_txready),.utmi_txdata(utmi_txdata),.utmi_txvalid(utmi_txvalid),
  .utmi_opmode(opmode),.utmi_xcvr(xcvr),.utmi_termsel(termsel),.utmi_dppd(dppd),.utmi_dmpd(dmpd),
  .midi_tx_valid(midi_tx_valid),.midi_tx_ready(midi_tx_ready),.midi_tx_data(midi_tx_data),
  .midi_rx_valid(midi_rx_valid),.midi_rx_ready(midi_rx_ready),.midi_rx_data(midi_rx_data),
  .control_tx_valid(control_tx_valid),.control_tx_ready(control_tx_ready),.control_tx_data(control_tx_data),
  .control_rx_valid(control_rx_valid),.control_rx_ready(control_rx_ready),.control_rx_data(control_rx_data),
  .online(online),.control_reset(control_reset),.hs_active(hs_active),.phy_state(phy_state),.device_address(device_address));
`ifdef MIDI_USB2_DIAGNOSTICS
 reg[15:0]midi_tx_words=0,midi_rx_words=0;
 always @(posedge clk_50mhz)begin
  if(midi_tx_valid&&midi_tx_ready)midi_tx_words<=midi_tx_words+1'b1;
  if(midi_rx_valid&&midi_rx_ready)midi_rx_words<=midi_rx_words+1'b1;
 end
 wire[31:0]phy_status={boot_stage,phy_state,device_address,
  boot_done,boot_error,protocol_reset,ulpi_dir,ulpi_nxt,ulpi_stp,
  line_state,utmi_rxactive,utmi_rxerror,utmi_txvalid,utmi_txready,drive_arm,!reset60};
 midi_usb2_debug debug_monitor(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .source_status(phy_status),
  .local_snapshot({midi_tx_words,midi_rx_words}),
 .local_flags({online,hs_active,!control_reset}),.status_50mhz(debug_status));
`endif
`ifdef MIDI_USB2_PROBE
 midi_usb2_events probe_events(.clk(clk_ulpi60),.reset(reset60),.enabled(boot_done&&!boot_error),
  .protocol_active(!bridge_reset),.utmi_line(line_state),.utmi_data(utmi_rxdata),
  .phy_state(phy_state),.pad_input(pad_input),.dir(ulpi_dir),.nxt(ulpi_nxt),
  .rxvalid(utmi_rxvalid),.rxactive(utmi_rxactive),.rxerror(utmi_rxerror),
  .txvalid(utmi_txvalid),.txready(utmi_txready),.history(probe_history),.statistics(probe_statistics));
`endif
endmodule
`default_nettype wire
