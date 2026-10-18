`timescale 1ns/1ps
`default_nettype none
// Experimental 480Mbps CDC. USB3300 CLKOUT is an INPUT, always 60MHz.
module usb2_device_top(
 input wire clk_50mhz, clk_ulpi60,
 inout wire [7:0] ulpi_data,
 input wire ulpi_dir, ulpi_nxt,
 output wire ulpi_stp,led_ready,led_done
);
 reg [12:0] powerup=0;
 always @(posedge clk_50mhz) if(!powerup[12])powerup<=powerup+1'b1;
 (* ASYNC_REG="TRUE" *) reg [2:0] reset_release=0;
 always @(posedge clk_ulpi60) reset_release<={reset_release[1:0],powerup[12]};
 wire reset_n=reset_release[2];
 wire boot_done,boot_error,boot_oe,boot_stp,boot_drive_ready;
 wire [7:0] boot_data,boot_stage;
 wire [15:0] vid,pid;
 usb2_hs_boot u_boot(.clk_ulpi60(clk_ulpi60),.reset_n(reset_n),
  .data_i(pad_input),.data_o(boot_data),.data_oe(boot_oe),.drive_ready(boot_drive_ready),
  .dir(ulpi_dir),.nxt(ulpi_nxt),.stp(boot_stp),.done(boot_done),
  .error(boot_error),.stage(boot_stage),.vid(vid),.pid(pid));
 wire protocol_reset=!reset_n || !boot_done || boot_error;
 wire [7:0] link_data,utmi_rxdata,utmi_txdata,pad_input;
 wire link_stp,utmi_txvalid,utmi_txready,utmi_rxvalid,utmi_rxactive,utmi_rxerror;
 wire [1:0] line_state,opmode,xcvr;
 wire termsel,dppd,dmpd;
 reg wrapper_drive=0;
 always @(posedge clk_ulpi60) wrapper_drive<=!protocol_reset && !ulpi_dir;
 wire drive_arm=boot_done ? wrapper_drive : boot_drive_ready;
 wire [7:0] pad_data=boot_done ? link_data : boot_data;
 genvar i;
 generate for(i=0;i<8;i=i+1)begin:pads
  wire disabled;
  LUT2 #(.INIT(4'hB)) gate /* synthesis syn_dont_touch=1 */ (.I0(ulpi_dir),.I1(drive_arm),.F(disabled));
  IOBUF b(.I(pad_data[i]),.O(pad_input[i]),.OEN(disabled),.IO(ulpi_data[i]));
 end endgenerate
 assign ulpi_stp=boot_done ? link_stp : boot_stp;
 ulpi_wrapper u_ulpi(.ulpi_clk60_i(clk_ulpi60),.ulpi_rst_i(protocol_reset),
  .ulpi_data_out_i(pad_input),.ulpi_dir_i(ulpi_dir),.ulpi_nxt_i(ulpi_nxt),
  .ulpi_data_in_o(link_data),.ulpi_stp_o(link_stp),
  .utmi_data_out_i(utmi_txdata),.utmi_txvalid_i(utmi_txvalid),
  .utmi_op_mode_i(opmode),.utmi_xcvrselect_i(xcvr),.utmi_termselect_i(termsel),
  .utmi_dppulldown_i(dppd),.utmi_dmpulldown_i(dmpd),
  .utmi_data_in_o(utmi_rxdata),.utmi_txready_o(utmi_txready),
  .utmi_rxvalid_o(utmi_rxvalid),.utmi_rxactive_o(utmi_rxactive),
  .utmi_rxerror_o(utmi_rxerror),.utmi_linestate_o(line_state));
 wire stream_valid,stream_space,echo_valid,echo_accept;
 wire [7:0] stream_data,echo_data;
 wire hs_active,configured,usb_reset,chirp_active;
 wire [2:0] hs_state;
 wire [6:0] device_address;
 usb_cdc_core #(.USB_SPEED_HS("True")) u_cdc(
  .clk_i(clk_ulpi60),.rst_i(protocol_reset),.enable_i(!protocol_reset),
  .utmi_data_in_i(utmi_rxdata),.utmi_txready_i(utmi_txready),
  .utmi_rxvalid_i(utmi_rxvalid),.utmi_rxactive_i(utmi_rxactive),.utmi_rxerror_i(utmi_rxerror),
  .utmi_linestate_i(line_state),.utmi_data_out_o(utmi_txdata),.utmi_txvalid_o(utmi_txvalid),
  .utmi_op_mode_o(opmode),.utmi_xcvrselect_o(xcvr),.utmi_termselect_o(termsel),
  .utmi_dppulldown_o(dppd),.utmi_dmpulldown_o(dmpd),
  .inport_valid_i(echo_valid),.inport_data_i(echo_data),.inport_accept_o(echo_accept),
  .outport_valid_o(stream_valid),.outport_data_o(stream_data),.outport_accept_i(stream_space),
  .hs_active_o(hs_active),.configured_o(configured),.usb_reset_o(usb_reset),
  .chirp_active_o(chirp_active),.hs_state_o(hs_state),.device_address_o(device_address));
 wire [31:0] rx_count,tx_count;
 wire [15:0] overflow_count,occupancy;
 usb2_hs_echo u_echo(.clk(clk_ulpi60),.reset_n(!protocol_reset),.clear(usb_reset),
  .rx_valid(stream_valid),.rx_data(stream_data),.rx_space(stream_space),
  .tx_valid(echo_valid),.tx_data(echo_data),.tx_accept(echo_accept),
  .rx_count(rx_count),.tx_count(tx_count),.overflow_count(overflow_count),.occupancy(occupancy));
 reg rxerror_seen=0,chirp_seen=0,hs_seen=0;
 reg [7:0] reset_count=0;
 reg reset_prev=0;
 always @(posedge clk_ulpi60)begin
  if(protocol_reset)begin rxerror_seen<=0;chirp_seen<=0;hs_seen<=0;reset_count<=0;reset_prev<=0;end
  else begin
   if(utmi_rxerror)rxerror_seen<=1;
   if(chirp_active)chirp_seen<=1;
   if(hs_active)hs_seen<=1;
   reset_prev<=usb_reset;
   if(usb_reset && !reset_prev && reset_count!=255)reset_count<=reset_count+1'b1;
  end
 end
 // Four coherent pages: PHY ID; current mode and sticky handshake flags;
 // byte RX count with standard observer flags; echo count/drop count.
 wire [7:0] mode_byte={opmode,xcvr,termsel,line_state,chirp_active};
 wire [7:0] flags_byte={hs_seen,chirp_seen,rxerror_seen,boot_error,boot_done,hs_active,configured,(overflow_count!=0)};
 wire [127:0] live_snapshot={vid,pid,
  mode_byte,{1'b0,device_address},reset_count,flags_byte,
  boot_stage,{hs_state,1'b0,boot_done,hs_active,configured,boot_error},rx_count[15:0],
  tx_count[15:0],overflow_count};
 wire [63:0] status_raw;
 wire [3:0] result_flags;
 wire clock_alive;
 usb2_status_50mhz u_observer(.clk_50mhz(clk_50mhz),.clk_ulpi60(clk_ulpi60),
  .live_snapshot(live_snapshot),.status_50mhz(status_raw),.result_flags(result_flags),.clock_alive(clock_alive));
 reg [63:0] status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
 always @(posedge clk_50mhz)status_50mhz<=status_raw;
 assign led_ready=clock_alive;
 assign led_done=result_flags[3] && result_flags[2] && result_flags[1] && !result_flags[0];
endmodule
`default_nettype wire
