`timescale 1ns/1ps
// Independent USB-host packet BFM at the standard 8-bit UTMI boundary.
// Exercises actual PID/token/CRC16 paths; no force of internal protocol state.
module tb_usb2_hs_control;
reg clk=0;
always #8.333 clk=~clk;
reg rst=1, enable=0;
reg [7:0] rxdata=0;
reg rxvalid=0, rxactive=0, rxerror=0;
reg [1:0] linestate=1;
wire [7:0] txdata;
wire txvalid;
reg txready=1;
wire [1:0] opmode,xcvr;
wire term,dpdown,dmdown,hs,configured,usbreset,chirp;
wire [2:0] hsstate;
wire [6:0] requested_address;
wire in_accept,out_valid;
wire [7:0] out_data;
reg [7:0] fifo[0:2047];
integer wr=0,rd=0,count=0;
wire in_valid=count!=0;
wire [7:0] in_data=fifo[rd];
wire out_accept=count<=1536; // Reserve a complete 512-byte OUT packet.
wire push=out_valid;
wire pop=in_valid&&in_accept;
always @(posedge clk) begin
    if(rst) begin wr<=0;rd<=0;count<=0;end
    else begin
        if(push)begin fifo[wr]<=out_data;wr<=(wr+1)%2048;end
        if(pop)rd<=(rd+1)%2048;
        case({push,pop})2'b10:count<=count+1;2'b01:count<=count-1;default:;endcase
        if(push && count==2048)$fatal(1,"loopback FIFO overflow");
    end
end
usb_cdc_core #(.USB_SPEED_HS("True")) dut(
 .clk_i(clk),.rst_i(rst),.enable_i(enable),
 .utmi_data_in_i(rxdata),.utmi_txready_i(txready),.utmi_rxvalid_i(rxvalid),
 .utmi_rxactive_i(rxactive),.utmi_rxerror_i(rxerror),.utmi_linestate_i(linestate),
 .inport_valid_i(in_valid),.inport_data_i(in_data),.outport_accept_i(out_accept),
 .utmi_data_out_o(txdata),.utmi_txvalid_o(txvalid),.utmi_op_mode_o(opmode),
 .utmi_xcvrselect_o(xcvr),.utmi_termselect_o(term),.utmi_dppulldown_o(dpdown),
 .utmi_dmpulldown_o(dmdown),.inport_accept_o(in_accept),.outport_valid_o(out_valid),
 .outport_data_o(out_data),.hs_active_o(hs),.configured_o(configured),
 .usb_reset_o(usbreset),.chirp_active_o(chirp),.hs_state_o(hsstate),
 .device_address_o(requested_address));

reg [7:0] host_bytes[0:2047];
reg [7:0] payload[0:1023];
reg [7:0] response[0:2047];
reg [7:0] collected[0:2047];
integer response_len=0,response_count=0,tx_count=0,current_address=0;
integer total=0,i,j,base,chirp_cycles=0;
integer warm_reset_chirp_index;
reg [7:0] packet_bytes[0:2047];
reg collecting_enabled=0;
always @(posedge clk)begin
 if(collecting_enabled)begin
  if(txvalid&&txready)begin
   packet_bytes[tx_count]=txdata;tx_count=tx_count+1;
   if(tx_count>=2048)$fatal(1,"overlong device UTMI packet");
  end else if(!txvalid&&tx_count!=0)begin
   response_len=tx_count;
   for(integer k=0;k<tx_count;k=k+1)response[k]=packet_bytes[k];
   response_count=response_count+1;tx_count=0;
  end
 end
end
function automatic [15:0] crc16_byte(input [15:0] oldcrc,input [7:0] b);
 reg [15:0] c;integer k;
 begin c=oldcrc;for(k=0;k<8;k=k+1)c=(c[0]^b[k])?((c>>1)^16'ha001):(c>>1);crc16_byte=c;end
endfunction
task automatic idle(input integer n);
 begin repeat(n)@(negedge clk);end
endtask
task automatic send_packet(input integer n);
 begin
  idle(8);rxactive=1;linestate=1;rxvalid=1;
  for(integer k=0;k<n;k=k+1)begin rxdata=host_bytes[k];@(negedge clk);end
  rxvalid=0;rxactive=0;rxdata=0;linestate=0;idle(8);
 end
endtask
task automatic token(input [3:0] pid,input integer ep);
 reg [10:0] b;reg [4:0] c;reg [15:0] bits16;
 begin
  b={ep[3:0],current_address[6:0]};c=5'h1f;
  for(integer k=0;k<11;k=k+1)c=(c[0]^b[k])?((c>>1)^5'h14):(c>>1);
  bits16={~c,b};host_bytes[0]={~pid,pid};host_bytes[1]=bits16[7:0];host_bytes[2]=bits16[15:8];send_packet(3);
 end
endtask
task automatic data_packet(input [3:0] pid,input integer n);
 reg [15:0] c;
 begin
  c=16'hffff;host_bytes[0]={~pid,pid};
  for(integer k=0;k<n;k=k+1)begin host_bytes[k+1]=payload[k];c=crc16_byte(c,payload[k]);end
  c=~c;host_bytes[n+1]=c[7:0];host_bytes[n+2]=c[15:8];send_packet(n+3);
 end
endtask
task automatic host_ack;
 begin host_bytes[0]=8'hd2;send_packet(1);end
endtask
task automatic wait_response(input integer old_count);
 integer timeout;
 begin
  timeout=0;
  while(response_count==old_count&&timeout<10000)begin @(negedge clk);timeout=timeout+1;end
  if(timeout==10000)$fatal(1,"response timeout state=%0d SIE=%0d",hsstate,dut.u_core.state_q);
 end
endtask
task automatic check_ack(input integer old_count);
 begin wait_response(old_count);if(response_len!=1||response[0]!=8'hd2)$fatal(1,"expected ACK len=%0d pid=%02x",response_len,response[0]);end
endtask
task automatic check_data;
 reg [15:0] c;
 begin
  if(response_len<3||(response[0]!=8'hc3&&response[0]!=8'h4b))$fatal(1,"expected DATA packet len=%0d pid=%02x",response_len,response[0]);
  c=16'hffff;for(integer k=1;k<response_len;k=k+1)c=crc16_byte(c,response[k]);
  if(c!=16'hb001)$fatal(1,"device DATA CRC failed %04x",c);
 end
endtask
task automatic setup(input [7:0] bm,input [7:0] req,input [15:0] value,input [15:0] idx,input [15:0] n);
 integer old_count;
 begin
  token(4'hd,0);
  payload[0]=bm;payload[1]=req;payload[2]=value[7:0];payload[3]=value[15:8];
  payload[4]=idx[7:0];payload[5]=idx[15:8];payload[6]=n[7:0];payload[7]=n[15:8];
  old_count=response_count;data_packet(4'h3,8);check_ack(old_count);idle(12);
 end
endtask
task automatic control_get(input [7:0] bm,input [7:0] req,input [15:0] value,input [15:0] idx,input [15:0] n,input integer expected);
 integer old_count,bytes,rounds;
 begin
  setup(bm,req,value,idx,n);total=0;rounds=0;
  begin: packets
   forever begin
    old_count=response_count;token(4'h9,0);wait_response(old_count);check_data();
    if(response[0]!=(rounds[0]?8'hc3:8'h4b))$fatal(1,"EP0 DATA toggle wrong");
    bytes=response_len-3;
    for(integer k=0;k<bytes;k=k+1)collected[total+k]=response[k+1];
    total=total+bytes;rounds=rounds+1;host_ack();
    if(bytes<64||total>=n)disable packets;
    if(rounds>40)$fatal(1,"control response never terminates");
   end
  end
  if(total!=expected)$fatal(1,"GET req=%02x value=%04x length=%0d expected=%0d",req,value,total,expected);
  token(4'h1,0);old_count=response_count;data_packet(4'hb,0);check_ack(old_count);idle(12);
 end
endtask
task automatic control_set(input [7:0] bm,input [7:0] req,input [15:0] value,input [15:0] idx);
 integer old_count;
 begin
  setup(bm,req,value,idx,0);old_count=response_count;token(4'h9,0);wait_response(old_count);check_data();
  if(response_len!=3)$fatal(1,"control status not ZLP");
  if(req==5&&dut.u_core.current_addr_q!=current_address)$fatal(1,"address committed before status ACK");
  host_ack();idle(12);
  if(req==5)begin current_address=value; if(dut.u_core.current_addr_q!=value)$fatal(1,"address not committed after status ACK");end
 end
endtask
initial begin
 idle(10);rst=0;enable=1;
 wait(hsstate==1);idle(10);linestate=0;
 wait(chirp);if(opmode!=2||xcvr!=0||term!=1)$fatal(1,"bad device chirp PHY mode");
 while(chirp)begin @(negedge clk);chirp_cycles=chirp_cycles+1;end
 if(chirp_cycles<60000||chirp_cycles>120000)$fatal(1,"chirp duration %0d",chirp_cycles);
 // Sub-2.5us glitches and SE1 must not qualify as host chirps.
 for(i=0;i<8;i=i+1)begin linestate=i[0]?1:2;idle(10);end
 linestate=3;idle(200);if(hs)$fatal(1,"invalid/glitch chirps entered HS");
 for(i=0;i<6;i=i+1)begin linestate=i[0]?1:2;idle(2400);end
 if(!hs||opmode!=0||xcvr!=0||term!=0)$fatal(1,"HS handshake failed state=%0d",hsstate);
 linestate=0;idle(20);collecting_enabled=1;
 control_get(8'h80,6,16'h0100,0,64,18);
 if(collected[7]!=64||collected[8]!=8'h9a||collected[9]!=8'hfb||collected[10]!=8'h9b||collected[11]!=8'hfb)$fatal(1,"device descriptor");
 control_get(8'h80,6,16'h0200,0,255,67);
 if(collected[0]!=9||collected[1]!=2||collected[2]!=67||collected[57]!=0||collected[58]!=2||collected[64]!=0||collected[65]!=2)$fatal(1,"HS config descriptor");
 control_get(8'h80,6,16'h0200,0,9,9); // Host header-only request.
 // Unsupported descriptor must STALL rather than leak ROM bytes.
 setup(8'h80,6,16'h9900,0,32);base=response_count;token(4'h9,0);wait_response(base);
 if(response_len!=1||response[0]!=8'h1e)$fatal(1,"unsupported descriptor did not STALL");
 control_get(8'h80,6,16'h0600,0,255,10);
 if(collected[0]!=10||collected[1]!=6||collected[7]!=8)$fatal(1,"device qualifier");
 control_get(8'h80,6,16'h0700,0,255,67);
 if(collected[1]!=7||collected[57]!=64||collected[58]!=0||collected[64]!=64||collected[65]!=0)$fatal(1,"other-speed config");
 control_get(8'h80,6,16'h0302,16'h0409,255,26);
 if(collected[0]!=26||collected[2]!="G"||collected[24]!="S")$fatal(1,"product string");
 control_get(8'h80,0,0,0,2,2);if(collected[0]!=0||collected[1]!=0)$fatal(1,"GET_STATUS");
 control_get(8'h80,8,0,0,1,1);if(collected[0]!=0)$fatal(1,"GET_CONFIGURATION before SET");
 control_set(0,5,7,0);
 control_set(0,9,1,0);if(!configured)$fatal(1,"SET_CONFIGURATION");
 linestate=0;idle(30000);
 if(!hs||usbreset||!configured||requested_address!=7)$fatal(1,"legal 500us HS idle cleared device state");
 control_get(8'h80,8,0,0,1,1);if(collected[0]!=1)$fatal(1,"GET_CONFIGURATION after SET");
 control_get(8'h81,10,0,1,1,1);if(collected[0]!=0)$fatal(1,"GET_INTERFACE");
 control_get(8'ha1,8'h21,0,0,7,7);if(collected[0]!=0||collected[1]!=8'hc2||collected[6]!=8)$fatal(1,"CDC line coding");
 control_set(8'h21,8'h22,3,0);
 // One full high-speed bulk packet through real SIE RX, FIFO and SIE TX.
 for(i=0;i<512;i=i+1)payload[i]=(i*37+19)&255;
 token(4'h1,1);base=response_count;data_packet(4'h3,512);check_ack(base);idle(20);
 base=response_count;token(4'h9,2);wait_response(base);check_data();
 if(response_len!=515)$fatal(1,"HS bulk length=%0d expected515",response_len);
 for(i=0;i<512;i=i+1)if(response[i+1]!=((i*37+19)&255))$fatal(1,"HS bulk mismatch at %0d got%02x",i,response[i+1]);
 host_ack();idle(20);
 collecting_enabled=0;linestate=0;idle(185000);
 if(hs||opmode!=0||xcvr!=1||term!=1||chirp)$fatal(1,"HS reset must revert to FS after 3ms and wait for settling");
 idle(4000);
 if(!chirp)$fatal(1,"HS warm reset did not begin device chirp after FS settling");
 while(chirp)@(negedge clk);
 for(warm_reset_chirp_index=0;warm_reset_chirp_index<6;warm_reset_chirp_index=warm_reset_chirp_index+1)begin
  linestate=warm_reset_chirp_index[0]?1:2;idle(3000);
 end
 if(!hs||configured||requested_address!=0)$fatal(1,"HS warm reset did not clear and renegotiate device");
 current_address=0;linestate=0;idle(20);collecting_enabled=1;
 control_get(8'h80,6,16'h0100,0,18,18);
 $display("PASS USB2 HS UTMI: filtered chirp, descriptors/min lengths/qualifier/other-speed, address status ACK, configuration, CDC, 512-byte binary loopback, 500us idle preservation, 3ms HS warm reset and re-enumeration");
 $finish;
end
initial begin #50000000;$fatal(1,"test global timeout");end
endmodule
