`timescale 1ns/1ps
`default_nettype none
module midi_usb2_events(
 input wire clk,reset,enabled,protocol_active,
 input wire[2:0]phy_state,input wire[7:0]pad_input,
 input wire[1:0]utmi_line,input wire[7:0]utmi_data,
 input wire dir,nxt,rxvalid,rxactive,rxerror,txvalid,txready,
 output wire[31:0]history,output wire[191:0]statistics
);
 reg previous_dir=0;
 reg[7:0]states_seen=0,rx_bytes=0,last_rxcmd=0;
 reg[3:0]lines_seen=0,flags_seen=0;
 reg[1:0]raw_line=0;
 reg raw_valid=0,raw_armed=0,utmi_armed=0;
 reg[23:0]raw_run=0,utmi_run=0,raw_max=0,utmi_max=0;
 reg[23:0]rxcmd_count=0,phy_bytes=0,utmi_bytes=0,link_nxt_count=0;
 reg[7:0]raw_runs=0,utmi_runs=0,last_phy_data=0,last_utmi_data=0;
 wire rxcmd_valid=dir&&previous_dir&&!nxt;
 wire[1:0]raw_line_now=rxcmd_valid?pad_input[1:0]:raw_line;
 wire active=enabled&&protocol_active;
 wire fs_tracking=active&&(phy_state==1||phy_state==4);
 wire raw_se0=fs_tracking&&raw_armed&&(raw_valid||rxcmd_valid)&&raw_line_now==0;
 wire utmi_se0=fs_tracking&&utmi_armed&&utmi_line==0;
 always @(posedge clk or posedge reset)
  if(reset)begin
   previous_dir<=0;
   states_seen<=0;rx_bytes<=0;last_rxcmd<=0;lines_seen<=0;flags_seen<=0;
   raw_line<=0;raw_valid<=0;raw_armed<=0;utmi_armed<=0;
   raw_run<=0;utmi_run<=0;raw_max<=0;utmi_max<=0;
   rxcmd_count<=0;phy_bytes<=0;utmi_bytes<=0;link_nxt_count<=0;
   raw_runs<=0;utmi_runs<=0;last_phy_data<=0;last_utmi_data<=0;
  end else begin
   previous_dir<=dir;
   if(enabled)begin
    states_seen<=states_seen|(8'b1<<phy_state);
    flags_seen<=flags_seen|{rxerror,txvalid,rxactive,txready};
    if(rxvalid&&rx_bytes!=255)rx_bytes<=rx_bytes+1'b1;
    if(rxcmd_valid)begin
     last_rxcmd<=pad_input;
     lines_seen<=lines_seen|(4'b1<<pad_input[1:0]);
     raw_line<=pad_input[1:0];raw_valid<=1;
    end
   end
   if(fs_tracking&&(raw_valid||rxcmd_valid)&&raw_line_now==1)raw_armed<=1;
   if(fs_tracking&&utmi_line==1)utmi_armed<=1;
   if(raw_se0)begin
    if(raw_run!=24'hffffff)begin
     raw_run<=raw_run+1'b1;
     if(raw_run>=raw_max)raw_max<=raw_run+1'b1;
    end
    if(raw_run==0&&raw_runs!=255)raw_runs<=raw_runs+1'b1;
   end else raw_run<=0;
   if(utmi_se0)begin
    if(utmi_run!=24'hffffff)begin
     utmi_run<=utmi_run+1'b1;
     if(utmi_run>=utmi_max)utmi_max<=utmi_run+1'b1;
    end
    if(utmi_run==0&&utmi_runs!=255)utmi_runs<=utmi_runs+1'b1;
   end else utmi_run<=0;
   if(active)begin
    if(rxcmd_valid&&rxcmd_count!=24'hffffff)rxcmd_count<=rxcmd_count+1'b1;
    if(dir&&previous_dir&&nxt)begin
     if(phy_bytes!=24'hffffff)phy_bytes<=phy_bytes+1'b1;
     last_phy_data<=pad_input;
    end
    if(rxvalid)begin
     if(utmi_bytes!=24'hffffff)utmi_bytes<=utmi_bytes+1'b1;
     last_utmi_data<=utmi_data;
    end
    if(!dir&&!previous_dir&&nxt&&link_nxt_count!=24'hffffff)link_nxt_count<=link_nxt_count+1'b1;
   end
  end
 assign history={states_seen,lines_seen,flags_seen,rx_bytes,last_rxcmd};
 assign statistics={{raw_line,utmi_line,raw_valid,raw_armed,utmi_armed,active},link_nxt_count,
  last_utmi_data,utmi_bytes,last_phy_data,phy_bytes,last_rxcmd,rxcmd_count,
  utmi_runs,utmi_max,raw_runs,raw_max};
endmodule
`default_nettype wire
