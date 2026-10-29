`timescale 1ns/1ps
`default_nettype none
// USB 2.0 control + two independent bidirectional bulk endpoints at UTMI.
// Packet storage is transactional: OUT becomes visible only after CRC/PHY
// validation; IN storage is released only by host ACK, allowing retransmit.
// EP1 transports whole USB-MIDI events; EP2 transports vendor bytes.
module midi_usb_device #(
 parameter integer FULL_SPEED_ONLY=0
)(
 input wire clk,reset,enable,
 input wire[7:0]utmi_rxdata,input wire utmi_rxvalid,utmi_rxactive,utmi_rxerror,
 input wire[1:0]utmi_linestate,input wire utmi_txready,
 output wire[7:0]utmi_txdata,output wire utmi_txvalid,
 output wire[1:0]utmi_opmode,utmi_xcvr,
 output wire utmi_termsel,utmi_dppd,utmi_dmpd,
 input wire midi_tx_valid,output wire midi_tx_ready,input wire[31:0]midi_tx_data,
 output wire midi_rx_valid,input wire midi_rx_ready,output wire[31:0]midi_rx_data,
 input wire control_tx_valid,output wire control_tx_ready,input wire[7:0]control_tx_data,
 output wire control_rx_valid,input wire control_rx_ready,output wire[7:0]control_rx_data,
 output reg configured,output wire session_reset,midi_session_reset,control_session_reset,output wire hs_active,
 output wire[2:0]phy_state,output reg[6:0]device_address
);
 reg[14:0]se0_count;
 always @(posedge clk or posedge reset)
  if(reset)se0_count<=0;
  else if(utmi_linestate!=0)se0_count<=0;
  else if(!se0_count[14])se0_count<=se0_count+1'b1;
 wire usb_reset,usb_suspended;
 wire chirp;
 generate if(FULL_SPEED_ONLY!=0)begin:fs_only
  midi_usb_fs_state phy(.clk(clk),.reset(reset),.enable(enable),
   .bus_active(utmi_rxactive||utmi_txvalid),.line_state(utmi_linestate),
   .bus_reset(usb_reset),.suspended(usb_suspended));
  assign utmi_opmode=0;
  assign utmi_xcvr=1;
  assign utmi_termsel=1;
  assign utmi_dppd=0;
  assign utmi_dmpd=0;
  assign chirp=0;
  assign hs_active=0;
  assign phy_state=3'd4;
 end else begin:dual_speed
 midi_usb_hs_phy phy(.clk(clk),.reset(reset),.enable(enable),.se0_reset(se0_count[14]),
  .bus_active(utmi_rxactive||utmi_txvalid),.bus_reset(usb_reset),.suspended(usb_suspended),
  .line_state(utmi_linestate),.opmode(utmi_opmode),.xcvr(utmi_xcvr),
  .termsel(utmi_termsel),.dppd(utmi_dppd),.dmpd(utmi_dmpd),
  .chirp(chirp),.high_speed(hs_active),.state(phy_state));
 end endgenerate
 wire[7:0]pid,rx_byte;wire[3:0]token_ep;
 wire token_valid,handshake_valid,rx_valid,rx_strb,rx_last,rx_crc_error,rx_complete;
 midi_usbf_sie_rx rx(.clk_i(clk),.rst_i(reset),.enable_i(enable&&!usb_reset&&!usb_suspended&&!chirp),
  .utmi_data_i(utmi_rxdata),.utmi_rxvalid_i(utmi_rxvalid),.utmi_rxactive_i(utmi_rxactive),
  .current_addr_i(device_address),.pid_o(pid),.frame_valid_o(),.frame_number_o(),
  .token_valid_o(token_valid),.token_addr_o(),.token_ep_o(token_ep),.token_crc_err_o(),
  .handshake_valid_o(handshake_valid),.data_valid_o(rx_valid),.data_strb_o(rx_strb),
  .data_o(rx_byte),.data_last_o(rx_last),.data_crc_err_o(rx_crc_error),.data_complete_o(rx_complete));

 reg tx_request;reg[7:0]tx_pid;wire tx_accept,tx_byte_accept;
 reg[1:0]tx_endpoint;reg[9:0]tx_index,tx_length;
 wire tx_data_packet=tx_pid==8'hc3||tx_pid==8'h4b;
 wire[7:0]tx_byte;
 midi_usbf_sie_tx tx(.clk_i(clk),.rst_i(reset),.enable_i(enable&&!usb_reset&&!usb_suspended),.chirp_i(chirp),
  .utmi_txready_i(utmi_txready),.tx_valid_i(tx_request),.tx_pid_i(tx_pid),
  .data_valid_i(tx_data_packet),.data_strb_i(tx_length!=0),.data_i(tx_byte),
  .data_last_i(tx_length==0||tx_index+1>=tx_length),.utmi_data_o(utmi_txdata),
  .utmi_txvalid_o(utmi_txvalid),.tx_accept_o(tx_accept),.data_accept_o(tx_byte_accept));

 // A MIDI event is one RAM word; each packet uses a single write and read
 // port. Keep RAM and read registers unreset so Gowin can infer BSRAM.
 (* ram_style="block" *) reg[31:0]in1[0:127],out1[0:127];
 (* ram_style="block" *) reg[7:0]in2[0:511],out2[0:511];
 reg[31:0]in1_q,out1_q;
 reg[7:0]in2_q,out2_q;
 reg[23:0]out1_assembly;
 reg[9:0]in1_count,in2_count,out1_length,out2_length,out1_index,out2_index;
 reg in1_pending,in2_pending,out1_pending,out2_pending;
 reg[4:0]in1_idle,in2_idle;
 reg[2:0]toggle_in,toggle_out;
 reg[2:1]halt_in,halt_out;
 wire[9:0]max_packet=hs_active?10'd512:10'd64;
 reg session_pulse,midi_interface_pulse,control_interface_pulse;
 assign session_reset=reset||usb_reset||!configured||session_pulse;
 assign midi_session_reset=session_reset||midi_interface_pulse;
 assign control_session_reset=session_reset||control_interface_pulse;
 assign midi_tx_ready=!midi_session_reset&&!in1_pending&&in1_count+4<=max_packet&&!halt_in[1];
 assign control_tx_ready=!control_session_reset&&!in2_pending&&in2_count<max_packet&&!halt_in[2];
 assign midi_rx_valid=!midi_session_reset&&out1_pending;
 assign midi_rx_data=out1_q;
 assign control_rx_valid=!control_session_reset&&out2_pending;
 assign control_rx_data=out2_q;

 // Each OUT reserves its endpoint's entire packet buffer before reception.
 reg rx_wait,rx_setup,rx_setup_token,rx_space,rx_phy_error,rx_overflow;
 reg[3:0]rx_endpoint;
 reg[9:0]rx_count;
 reg[63:0]setup_packet;
 reg decode_setup;
 wire[7:0]bm=setup_packet[7:0],request=setup_packet[15:8];
 wire[15:0]value=setup_packet[31:16],index=setup_packet[47:32],requested=setup_packet[63:48];
 wire valid_endpoint=(index==16'h0000||index==16'h0080||index==16'h0001||
  index==16'h0081||index==16'h0002||index==16'h0082);
 wire bulk_endpoint=(index==16'h0001||index==16'h0081||index==16'h0002||index==16'h0082);

 reg ctrl_stall,ctrl_read,ctrl_status,ctrl_rom,ctrl_need_zlp;
 reg[15:0]ctrl_selector,ctrl_offset,ctrl_length,ctrl_fixed;
 reg[3:0]ctrl_action;
 reg[15:0]ctrl_action_value,ctrl_action_index;
 reg ack_wait;reg[1:0]ack_endpoint;reg[9:0]ack_length;
 wire[7:0]rom_byte;wire[15:0]rom_length;wire rom_supported,rom_available;
 // During decode select directly from SETUP; during reads use the saved type.
 wire[15:0]rom_selector=decode_setup?value:ctrl_selector;
 midi_usb_desc_rom descriptors(.hs(hs_active),.selector(rom_selector),
  .offset(ctrl_offset+tx_index),.data(rom_byte),.length(rom_length),.supported(rom_available));
 assign rom_supported=rom_available&&(FULL_SPEED_ONLY==0||(rom_selector[15:8]!=6&&rom_selector[15:8]!=7));
 assign tx_byte=tx_endpoint==1?(in1_q>>(tx_index[1:0]*8)):tx_endpoint==2?in2_q:
  ctrl_rom?rom_byte:(tx_index==0?ctrl_fixed[7:0]:ctrl_fixed[15:8]);

 // Read ahead on each accepted transfer, retaining the head throughout a
 // stall. The IN token precedes PID/payload and primes the first RAM word.
 wire[9:0]in_read_index=token_valid&&pid==8'h69 ? 10'd0:
  tx_byte_accept&&tx_data_packet&&tx_length!=0?tx_index+10'd1:tx_index;
 wire[9:0]out1_read_index=midi_rx_valid&&midi_rx_ready?
  (out1_index+4>=out1_length?10'd0:out1_index+10'd4):out1_index;
 wire[9:0]out2_read_index=control_rx_valid&&control_rx_ready?
  (out2_index+1>=out2_length?10'd0:out2_index+10'd1):out2_index;
 wire packet_rx_byte=rx_wait&&rx_valid&&rx_strb&&rx_space&&!rx_setup&&rx_count<max_packet;
 always @(posedge clk)begin
  if(midi_tx_valid&&midi_tx_ready)in1[in1_count[8:2]]<=midi_tx_data;
  in1_q<=in1[in_read_index[8:2]];
 end
 always @(posedge clk)begin
  if(control_tx_valid&&control_tx_ready)in2[in2_count[8:0]]<=control_tx_data;
  in2_q<=in2[in_read_index[8:0]];
 end
 always @(posedge clk)begin
  if(packet_rx_byte&&rx_endpoint==1)begin
   case(rx_count[1:0])
    0:out1_assembly[7:0]<=rx_byte;
    1:out1_assembly[15:8]<=rx_byte;
    2:out1_assembly[23:16]<=rx_byte;
    3:out1[rx_count[8:2]]<={rx_byte,out1_assembly};
   endcase
  end
  out1_q<=out1[out1_read_index[8:2]];
 end
 always @(posedge clk)begin
  if(packet_rx_byte&&rx_endpoint==2)out2[rx_count[8:0]]<=rx_byte;
  out2_q<=out2[out2_read_index[8:0]];
 end

 // Named actions are committed after the control status packet is ACKed.
 localparam A_NONE=0,A_ADDRESS=1,A_CONFIG=2,A_SET_HALT=3,A_CLEAR_HALT=4,A_INTERFACE=5;
 integer j;
 always @(posedge clk or posedge reset)begin
  if(reset)begin
   configured<=0;device_address<=0;session_pulse<=0;midi_interface_pulse<=0;control_interface_pulse<=0;
   tx_request<=0;tx_pid<=0;tx_endpoint<=0;tx_index<=0;tx_length<=0;
   in1_count<=0;in2_count<=0;in1_pending<=0;in2_pending<=0;in1_idle<=0;in2_idle<=0;
   out1_pending<=0;out2_pending<=0;out1_length<=0;out2_length<=0;out1_index<=0;out2_index<=0;
   toggle_in<=0;toggle_out<=0;halt_in<=0;halt_out<=0;
   rx_wait<=0;rx_setup<=0;rx_setup_token<=0;rx_space<=0;rx_phy_error<=0;rx_overflow<=0;rx_endpoint<=0;rx_count<=0;
   setup_packet<=0;decode_setup<=0;ctrl_stall<=0;ctrl_read<=0;ctrl_status<=0;ctrl_rom<=0;
   ctrl_need_zlp<=0;ctrl_selector<=0;ctrl_offset<=0;ctrl_length<=0;ctrl_fixed<=0;
   ctrl_action<=A_NONE;ctrl_action_value<=0;ctrl_action_index<=0;
   ack_wait<=0;ack_endpoint<=0;ack_length<=0;
  end else if(usb_reset||!enable)begin
   configured<=0;device_address<=0;session_pulse<=1;midi_interface_pulse<=0;control_interface_pulse<=0;
   tx_request<=0;ack_wait<=0;decode_setup<=0;rx_wait<=0;
   ctrl_stall<=0;ctrl_read<=0;ctrl_status<=0;ctrl_action<=A_NONE;
   in1_count<=0;in2_count<=0;in1_pending<=0;in2_pending<=0;in1_idle<=0;in2_idle<=0;
   out1_pending<=0;out2_pending<=0;out1_index<=0;out2_index<=0;
   toggle_in<=0;toggle_out<=0;halt_in<=0;halt_out<=0;
  end else begin
   session_pulse<=0;midi_interface_pulse<=0;control_interface_pulse<=0;decode_setup<=0;
   if(tx_request&&tx_accept)tx_request<=0;
   if(tx_byte_accept&&tx_data_packet&&tx_length!=0)tx_index<=tx_index+1'b1;
   if(utmi_rxerror&&utmi_rxactive)rx_phy_error<=1;

   if(session_pulse||midi_interface_pulse)begin
    in1_count<=0;in1_pending<=0;in1_idle<=0;out1_pending<=0;out1_index<=0;
    toggle_in[1]<=0;toggle_out[1]<=0;halt_in[1]<=0;halt_out[1]<=0;
   end else begin
    if(midi_tx_valid&&midi_tx_ready)begin
     in1_count<=in1_count+4;in1_idle<=0;
     if(in1_count+4==max_packet)in1_pending<=1;
    end else if(in1_count!=0&&!in1_pending)begin
     if(in1_idle==15)in1_pending<=1;else in1_idle<=in1_idle+1'b1;
    end
    if(midi_rx_valid&&midi_rx_ready)begin
     if(out1_index+4>=out1_length)begin out1_pending<=0;out1_index<=0;end
     else out1_index<=out1_index+4;
    end
   end
   if(session_pulse||control_interface_pulse)begin
    in2_count<=0;in2_pending<=0;in2_idle<=0;out2_pending<=0;out2_index<=0;
    toggle_in[2]<=0;toggle_out[2]<=0;halt_in[2]<=0;halt_out[2]<=0;
   end else begin
    if(control_tx_valid&&control_tx_ready)begin
     in2_count<=in2_count+1'b1;in2_idle<=0;
     if(in2_count+1==max_packet)in2_pending<=1;
    end else if(in2_count!=0&&!in2_pending)begin
     if(in2_idle==15)in2_pending<=1;else in2_idle<=in2_idle+1'b1;
    end
    if(control_rx_valid&&control_rx_ready)begin
     if(out2_index+1>=out2_length)begin out2_pending<=0;out2_index<=0;end
     else out2_index<=out2_index+1'b1;
    end
   end

   if(token_valid)begin
    // Any later token supersedes ACK tracking for the previous IN transaction.
    ack_wait<=0;
    if(pid==8'he1||pid==8'h2d)begin // OUT or SETUP
     rx_wait<=1;rx_endpoint<=token_ep;rx_count<=0;rx_overflow<=0;rx_phy_error<=0;
     rx_setup<=pid==8'h2d&&token_ep==0;
     rx_setup_token<=pid==8'h2d;
     rx_space<=token_ep==0||(configured&&((token_ep==1&&!out1_pending)||(token_ep==2&&!out2_pending)));
     if(pid==8'h2d&&token_ep==0)begin
      ctrl_stall<=0;ctrl_read<=0;ctrl_status<=0;ctrl_action<=A_NONE;
      toggle_in[0]<=1;toggle_out[0]<=0;setup_packet<=0;
     end
    end else if(pid==8'h69)begin // IN
     tx_endpoint<=token_ep[1:0];tx_index<=0;tx_length<=0;tx_request<=1;
     if(token_ep==0)begin
      if(ctrl_stall)tx_pid<=8'h1e;
      else if(ctrl_status||ctrl_read)begin
       tx_pid<=toggle_in[0]?8'h4b:8'hc3;ack_wait<=1;ack_endpoint<=0;
       if(ctrl_status||ctrl_offset>=ctrl_length)begin tx_length<=0;ack_length<=0;end
       else if(ctrl_length-ctrl_offset>64)begin tx_length<=64;ack_length<=64;end
       else begin tx_length<=ctrl_length-ctrl_offset;ack_length<=ctrl_length-ctrl_offset;end
      end else tx_pid<=8'h5a;
     end else if(token_ep==1||token_ep==2)begin
      if(!configured||halt_in[token_ep])tx_pid<=8'h1e;
      else if((token_ep==1&&in1_pending)||(token_ep==2&&in2_pending))begin
       tx_pid<=toggle_in[token_ep]?8'h4b:8'hc3;
       tx_length<=token_ep==1?in1_count:in2_count;
       ack_length<=token_ep==1?in1_count:in2_count;
       ack_wait<=1;ack_endpoint<=token_ep[1:0];
      end else tx_pid<=8'h5a;
     end else tx_pid<=8'h1e;
    end else if(pid==8'hb4)begin // PING: reserve availability, no payload
     tx_request<=1;
     if(token_ep==0)tx_pid<=ctrl_stall?8'h1e:8'hd2;
     else if(token_ep==1||token_ep==2)begin
      if(!configured||halt_out[token_ep])tx_pid<=8'h1e;
      else tx_pid<=((token_ep==1&&!out1_pending)||(token_ep==2&&!out2_pending))?8'hd2:8'h5a;
     end else tx_pid<=8'h1e;
    end
   end

   if(rx_wait&&rx_valid&&rx_strb)begin
    if(rx_count>=max_packet)rx_overflow<=1;
    else begin
     if(rx_setup&&rx_count<8)setup_packet[rx_count*8+:8]<=rx_byte;
    end
    if(rx_count<1023)rx_count<=rx_count+1'b1;
   end
   if(rx_wait&&rx_complete)begin
    rx_wait<=0;
    // DATA2/MDATA belong to other transfer modes, never bulk/control.
    if(!rx_crc_error&&!rx_phy_error&&!utmi_rxerror&&!rx_overflow&&(pid==8'hc3||pid==8'h4b))begin
     tx_request<=1;
     if(rx_setup_token&&!rx_setup)tx_pid<=8'h1e;
     else if(rx_setup)begin
      if(rx_count==8&&pid==8'hc3)begin tx_pid<=8'hd2;decode_setup<=1;end
      else tx_pid<=8'h1e;
     end else if(rx_endpoint==0)begin
      if(ctrl_stall)tx_pid<=8'h1e;
      else if(rx_count==0)begin tx_pid<=8'hd2;ctrl_read<=0;end
      else tx_pid<=8'h1e;
     end else if(rx_endpoint==1||rx_endpoint==2)begin
      if(!configured||halt_out[rx_endpoint])tx_pid<=8'h1e;
      else if((pid==8'h4b)!=toggle_out[rx_endpoint])tx_pid<=8'hd2; // duplicate
      else if(!rx_space)tx_pid<=8'h5a;
      else if(rx_endpoint==1&&rx_count[1:0]!=0)tx_pid<=8'h1e;
      else begin
       tx_pid<=8'hd2;toggle_out[rx_endpoint]<=!toggle_out[rx_endpoint];
       if(rx_endpoint==1)begin out1_length<=rx_count;out1_index<=0;out1_pending<=rx_count!=0;end
       else begin out2_length<=rx_count;out2_index<=0;out2_pending<=rx_count!=0;end
      end
     end else tx_pid<=8'h1e;
    end
   end

   if(handshake_valid&&pid==8'hd2&&ack_wait)begin
    ack_wait<=0;toggle_in[ack_endpoint]<=!toggle_in[ack_endpoint];
    if(ack_endpoint==1)begin in1_pending<=0;in1_count<=0;in1_idle<=0;end
    else if(ack_endpoint==2)begin in2_pending<=0;in2_count<=0;in2_idle<=0;end
    else if(ctrl_status)begin
     ctrl_status<=0;
     case(ctrl_action)
      A_ADDRESS:device_address<=ctrl_action_value[6:0];
      A_CONFIG:begin configured<=ctrl_action_value[0];session_pulse<=1;end
      A_INTERFACE:begin
       if(ctrl_action_index==1)midi_interface_pulse<=1;
       if(ctrl_action_index==2)control_interface_pulse<=1;
      end
      A_SET_HALT:if(ctrl_action_index[7])halt_in[ctrl_action_index[1:0]]<=1;
                 else halt_out[ctrl_action_index[1:0]]<=1;
      A_CLEAR_HALT:if(ctrl_action_index[7])begin halt_in[ctrl_action_index[1:0]]<=0;toggle_in[ctrl_action_index[1:0]]<=0;end
                  else begin halt_out[ctrl_action_index[1:0]]<=0;toggle_out[ctrl_action_index[1:0]]<=0;end
      default:;
     endcase
     ctrl_action<=A_NONE;
    end else if(ctrl_read)begin
     ctrl_offset<=ctrl_offset+ack_length;
     if(ctrl_offset+ack_length>=ctrl_length)begin
      if(ctrl_need_zlp&&ack_length!=0)ctrl_need_zlp<=0;
      else ctrl_read<=0;
     end
    end
   end

   if(decode_setup)begin
    ctrl_stall<=1;ctrl_read<=0;ctrl_status<=0;ctrl_offset<=0;ctrl_fixed<=0;ctrl_rom<=0;
    ctrl_need_zlp<=0;ctrl_action<=A_NONE;ctrl_action_value<=value;ctrl_action_index<=index;
    if(bm==8'h80&&request==6&&rom_supported&&
       ((value[15:8]==3&&(index==0||index==16'h0409))||(value[15:8]!=3&&index==0)))begin
     ctrl_stall<=0;ctrl_rom<=1;ctrl_selector<=value;
     ctrl_length<=requested<rom_length?requested:rom_length;
     ctrl_read<=requested!=0;
     ctrl_need_zlp<=rom_length<requested&&rom_length[5:0]==0;
    end else if(bm==0&&request==5&&value<=127&&index==0&&requested==0&&!configured)begin
     ctrl_stall<=0;ctrl_status<=1;ctrl_action<=A_ADDRESS;
    end else if(bm==0&&request==9&&value<=1&&index==0&&requested==0)begin
     ctrl_stall<=0;ctrl_status<=1;ctrl_action<=A_CONFIG;
    end else if(bm==8'h80&&request==8&&value==0&&index==0&&requested==1)begin
     ctrl_stall<=0;ctrl_read<=1;ctrl_length<=1;ctrl_fixed<={15'd0,configured};
    end else if(bm==8'h81&&request==10&&value==0&&index<3&&requested==1&&configured)begin
     ctrl_stall<=0;ctrl_read<=1;ctrl_length<=1;ctrl_fixed<=0;
    end else if(bm==1&&request==11&&value==0&&index<3&&requested==0&&configured)begin
     ctrl_stall<=0;ctrl_status<=1;ctrl_action<=A_INTERFACE;
    end else if(request==0&&value==0&&requested==2&&
       ((bm==8'h80&&index==0)||(bm==8'h81&&index<3&&configured)||
        (bm==8'h82&&valid_endpoint&&(configured||index[3:0]==0))))begin
     ctrl_stall<=0;ctrl_read<=1;ctrl_length<=2;ctrl_fixed<=0;
     if(bm==8'h82&&index[3:0]!=0)
      ctrl_fixed<=index[7]?{15'd0,halt_in[index[1:0]]}:{15'd0,halt_out[index[1:0]]};
    end else if(bm==2&&(request==1||request==3)&&value==0&&bulk_endpoint&&requested==0&&configured)begin
     ctrl_stall<=0;ctrl_status<=1;ctrl_action<=request==1?A_CLEAR_HALT:A_SET_HALT;
    end
   end
  end
 end
endmodule
`default_nettype wire
