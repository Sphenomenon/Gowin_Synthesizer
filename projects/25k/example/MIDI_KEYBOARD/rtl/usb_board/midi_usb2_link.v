`timescale 1ns/1ps
`default_nettype none
// Physical USB3300 link. DATA ownership uses the same registered drive arm
// plus immediate DIR inhibit as the hardware-verified USB3300_HS reference.
module midi_usb2_link(
 input wire clk_50mhz,reset,clk_ulpi60,
 inout wire[7:0]ulpi_data,input wire ulpi_dir,ulpi_nxt,output wire ulpi_stp,
 input wire midi_tx_valid,output wire midi_tx_ready,input wire[31:0]midi_tx_data,
 output wire midi_rx_valid,input wire midi_rx_ready,output wire[31:0]midi_rx_data,
 input wire control_tx_valid,output wire control_tx_ready,input wire[7:0]control_tx_data,
 output wire control_rx_valid,input wire control_rx_ready,output wire[7:0]control_rx_data,
 output wire online,control_reset,hs_active
);
 (* ASYNC_REG="TRUE" *)reg[2:0]reset_sync=3'b111;
 always @(posedge clk_ulpi60 or posedge reset)
  if(reset)reset_sync<=3'b111;else reset_sync<={reset_sync[1:0],1'b0};
 wire reset60=reset_sync[2];
 wire boot_done,boot_error,boot_oe,boot_stp,boot_drive;
 wire[7:0]boot_data,pad_input,link_data;
 wire link_stp;
 midi_usb2_boot boot(.clk_ulpi60(clk_ulpi60),.reset_n(!reset60),.data_i(pad_input),
  .data_o(boot_data),.data_oe(boot_oe),.drive_ready(boot_drive),
  .dir(ulpi_dir),.nxt(ulpi_nxt),.stp(boot_stp),.done(boot_done),.error(boot_error),
  .stage(),.vid(),.pid());
 wire protocol_reset=reset60||!boot_done||boot_error;
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
 midi_usb_bridge bridge(.clk_50mhz(clk_50mhz),.reset(protocol_reset),.clk_ulpi60(clk_ulpi60),.enable(!protocol_reset),
  .utmi_rxdata(utmi_rxdata),.utmi_rxvalid(utmi_rxvalid),.utmi_rxactive(utmi_rxactive),.utmi_rxerror(utmi_rxerror),
  .utmi_linestate(line_state),.utmi_txready(utmi_txready),.utmi_txdata(utmi_txdata),.utmi_txvalid(utmi_txvalid),
  .utmi_opmode(opmode),.utmi_xcvr(xcvr),.utmi_termsel(termsel),.utmi_dppd(dppd),.utmi_dmpd(dmpd),
  .midi_tx_valid(midi_tx_valid),.midi_tx_ready(midi_tx_ready),.midi_tx_data(midi_tx_data),
  .midi_rx_valid(midi_rx_valid),.midi_rx_ready(midi_rx_ready),.midi_rx_data(midi_rx_data),
  .control_tx_valid(control_tx_valid),.control_tx_ready(control_tx_ready),.control_tx_data(control_tx_data),
  .control_rx_valid(control_rx_valid),.control_rx_ready(control_rx_ready),.control_rx_data(control_rx_data),
  .online(online),.control_reset(control_reset),.hs_active(hs_active),.phy_state(),.device_address());
endmodule
`default_nettype wire
