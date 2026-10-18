`timescale 1ns/1ps
// Independent host BFM exercises actual token/PID/CRC paths at UTMI and a
// distinct 50MHz application clock. No internal state is forced.
module tb_usb_board_device #(parameter integer HIGH_SPEED=1);
 localparam integer BULK_BYTES=HIGH_SPEED?512:64;
 reg clk=0,appclk=0;always #8.333 clk=~clk;always #10 appclk=~appclk;
 reg reset=1,enable=0;reg[7:0]rxdata=0;reg rxvalid=0,rxactive=0,rxerror=0;
 reg[1:0]linestate=1;wire[7:0]txdata;wire txvalid;reg txready=1;
 wire[1:0]opmode,xcvr;wire term,dpdown,dmdown,online,control_reset,hs;
 wire[2:0]hsstate;wire[6:0]address;
 reg midi_tx_valid=0;wire midi_tx_ready;reg[31:0]midi_tx_data=0;
 wire midi_rx_valid;reg midi_rx_ready=0;wire[31:0]midi_rx_data;
 reg control_tx_valid=0;wire control_tx_ready;reg[7:0]control_tx_data=0;
 wire control_rx_valid;reg control_rx_ready=0;wire[7:0]control_rx_data;
 midi_usb_bridge dut(.clk_50mhz(appclk),.reset(reset),.clk_ulpi60(clk),.enable(enable),
  .utmi_rxdata(rxdata),.utmi_rxvalid(rxvalid),.utmi_rxactive(rxactive),.utmi_rxerror(rxerror),
  .utmi_linestate(linestate),.utmi_txready(txready),.utmi_txdata(txdata),.utmi_txvalid(txvalid),
  .utmi_opmode(opmode),.utmi_xcvr(xcvr),.utmi_termsel(term),.utmi_dppd(dpdown),.utmi_dmpd(dmdown),
  .midi_tx_valid(midi_tx_valid),.midi_tx_ready(midi_tx_ready),.midi_tx_data(midi_tx_data),
  .midi_rx_valid(midi_rx_valid),.midi_rx_ready(midi_rx_ready),.midi_rx_data(midi_rx_data),
  .control_tx_valid(control_tx_valid),.control_tx_ready(control_tx_ready),.control_tx_data(control_tx_data),
  .control_rx_valid(control_rx_valid),.control_rx_ready(control_rx_ready),.control_rx_data(control_rx_data),
  .online(online),.control_reset(control_reset),.hs_active(hs),.phy_state(hsstate),.device_address(address));
 integer checks=0;
 task check(input condition,input[8*120-1:0]text);
  begin checks=checks+1;if(condition!==1'b1)$fatal(1,"USB board: %0s at %0t",text,$time);end
 endtask
 reg[31:0]expected_midi[0:2047];reg[7:0]expected_control[0:8191];
 integer midi_put=0,midi_get=0,control_put=0,control_seen=0;
 always @(posedge appclk)if(!reset)begin
  if(midi_rx_valid&&midi_rx_ready)begin
   check(midi_get<midi_put,"unexpected MIDI OUT/duplicate/bad CRC leaked");
   check(midi_rx_data===expected_midi[midi_get],"MIDI complete-event CDC order");midi_get=midi_get+1;
  end
  if(control_rx_valid&&control_rx_ready)begin
   check(control_seen<control_put,"unexpected vendor OUT/duplicate/bad CRC leaked");
   check(control_rx_data===expected_control[control_seen],"vendor byte CDC order");control_seen=control_seen+1;
  end
 end
 reg[7:0]host_bytes[0:2047],payload[0:1023],response[0:2047],collected[0:2047],packet_bytes[0:2047];
 integer response_len=0,response_count=0,tx_count=0,current_address=0,total=0;
 integer i,j,base,before_count;
 reg collecting=0;reg corrupt_crc=0,corrupt_token_crc=0;
 reg[7:0]held_tx_byte;
 always @(posedge clk)if(collecting)begin
  if(txvalid&&txready)begin packet_bytes[tx_count]=txdata;tx_count=tx_count+1;end
  else if(!txvalid&&tx_count!=0)begin
   response_len=tx_count;for(integer k=0;k<tx_count;k=k+1)response[k]=packet_bytes[k];
   response_count=response_count+1;tx_count=0;
  end
 end
 function automatic[15:0]crc16_byte(input[15:0]oldcrc,input[7:0]b);
  reg[15:0]c;integer k;begin c=oldcrc;
   for(k=0;k<8;k=k+1)c=(c[0]^b[k])?((c>>1)^16'ha001):(c>>1);crc16_byte=c;end
 endfunction
 task idle(input integer n);begin repeat(n)@(negedge clk);end endtask
 task send_packet(input integer n);
  begin idle(8);rxactive=1;linestate=1;rxvalid=1;
   for(integer k=0;k<n;k=k+1)begin rxdata=host_bytes[k];@(negedge clk);end
   rxvalid=0;rxactive=0;rxdata=0;linestate=HIGH_SPEED?0:1;idle(8);end
 endtask
 task token(input[3:0]pid,input integer ep);
  reg[10:0]b;reg[4:0]c;reg[15:0]bits16;
  begin b={ep[3:0],current_address[6:0]};c=5'h1f;
   for(integer k=0;k<11;k=k+1)c=(c[0]^b[k])?((c>>1)^5'h14):(c>>1);
   bits16={~c,b};if(corrupt_token_crc)bits16=bits16^16'h0800;
   host_bytes[0]={~pid,pid};host_bytes[1]=bits16[7:0];host_bytes[2]=bits16[15:8];send_packet(3);end
 endtask
 task data_packet(input[3:0]pid,input integer n);
  reg[15:0]c;begin c=16'hffff;host_bytes[0]={~pid,pid};
   for(integer k=0;k<n;k=k+1)begin host_bytes[k+1]=payload[k];c=crc16_byte(c,payload[k]);end
   c=~c;host_bytes[n+1]=c[7:0]^{7'd0,corrupt_crc};host_bytes[n+2]=c[15:8];send_packet(n+3);end
 endtask
 task host_ack;begin host_bytes[0]=8'hd2;send_packet(1);end endtask
 task wait_response(input integer old_count);
  integer timeout;begin timeout=0;
   while(response_count==old_count&&timeout<10000)begin @(negedge clk);timeout=timeout+1;end
   if(timeout==10000)$fatal(1,"USB response timeout PHY=%0d ep=%0d req=%02x",hsstate,dut.device.token_ep,dut.device.request);
  end
 endtask
 task check_handshake(input integer old_count,input[7:0]expected);
  begin wait_response(old_count);
   if(response_len!=1||response[0]!=expected)
    $display("Handshake mismatch expected=%02x actual=%02x length=%0d endpoint=%0d",expected,response[0],response_len,dut.device.token_ep);
   check(response_len==1&&response[0]==expected,"expected USB handshake");end
 endtask
 task check_data;
  reg[15:0]c;begin check(response_len>=3&&(response[0]==8'hc3||response[0]==8'h4b),"DATA response");
   c=16'hffff;for(integer k=1;k<response_len;k=k+1)c=crc16_byte(c,response[k]);check(c==16'hb001,"device DATA CRC16");end
 endtask
 task setup(input[7:0]bm,input[7:0]req,input[15:0]value,input[15:0]idx,input[15:0]n);
  integer old_count;begin token(4'hd,0);
   payload[0]=bm;payload[1]=req;payload[2]=value[7:0];payload[3]=value[15:8];
   payload[4]=idx[7:0];payload[5]=idx[15:8];payload[6]=n[7:0];payload[7]=n[15:8];
   old_count=response_count;data_packet(4'h3,8);check_handshake(old_count,8'hd2);idle(12);end
 endtask
 task control_get(input[7:0]bm,input[7:0]req,input[15:0]value,input[15:0]idx,input[15:0]n,input integer expected);
  integer old_count,bytes,rounds;begin setup(bm,req,value,idx,n);total=0;rounds=0;
   begin:packets forever begin
    old_count=response_count;token(4'h9,0);wait_response(old_count);check_data;
    check(response[0]==(rounds[0]?8'hc3:8'h4b),"EP0 data toggle");bytes=response_len-3;
    for(integer k=0;k<bytes;k=k+1)collected[total+k]=response[k+1];
    total=total+bytes;rounds=rounds+1;host_ack;
    if(bytes<64||total>=n)disable packets;
    if(rounds>40)$fatal(1,"endless control response");
   end end
   check(total==expected,"control response exact bounded length");
   token(4'h1,0);old_count=response_count;data_packet(4'hb,0);check_handshake(old_count,8'hd2);idle(12);
  end
 endtask
 task control_set(input[7:0]bm,input[7:0]req,input[15:0]value,input[15:0]idx);
  integer old_count;begin setup(bm,req,value,idx,0);old_count=response_count;
   token(4'h9,0);wait_response(old_count);check_data;check(response_len==3,"control status ZLP");
   if(req==5)check(address==current_address,"SET_ADDRESS waits for status ACK");
   host_ack;idle(12);if(req==5)begin current_address=value;check(address==value,"address commits after ACK");end
  end
 endtask
 task app_midi(input[31:0]word);
  begin @(negedge appclk);midi_tx_valid=1;midi_tx_data=word;
   while(!midi_tx_ready)@(negedge appclk);
   @(posedge appclk);@(negedge appclk);midi_tx_valid=0;end
 endtask
 task app_control(input[7:0]value);
  begin @(negedge appclk);control_tx_valid=1;control_tx_data=value;
   while(!control_tx_ready)@(negedge appclk);
   @(posedge appclk);@(negedge appclk);control_tx_valid=0;end
 endtask
 initial begin
  idle(10);reset=0;enable=1;
  wait(hsstate==1);idle(10);linestate=0;wait(hsstate==3);
  if(HIGH_SPEED)begin
   for(i=0;i<6;i=i+1)begin linestate=i[0]?1:2;idle(2400);end
   check(hsstate==5,"high speed negotiation");
  end else begin wait(hsstate==4);check(!hs,"full speed fallback");end
  linestate=HIGH_SPEED?0:1;idle(20);collecting=1;
  control_get(8'h80,6,16'h0100,0,64,18);
  check(collected[4]==0&&collected[7]==64&&collected[8]==8'h9a&&collected[10]==8'h9b,"composite device descriptor");
  control_get(8'h80,6,16'h0200,0,255,124);
  check(collected[2]==124&&collected[4]==3,"configuration length/interfaces");
  begin:walk integer p,eps,interfaces; p=0;eps=0;interfaces=0;
   while(p<total)begin
    check(collected[p]>=2,"descriptor length nonzero");
    if(collected[p+1]==4)interfaces=interfaces+1;
    if(collected[p+1]==5)begin
     case(eps)0:check(collected[p+2]==1,"MIDI OUT01");1:check(collected[p+2]==8'h81,"MIDI IN81");
      2:check(collected[p+2]==2,"screen OUT02");3:check(collected[p+2]==8'h82,"screen IN82");endcase
     check(collected[p+4]==(HIGH_SPEED?0:64)&&collected[p+5]==(HIGH_SPEED?2:0),"speed-specific bulk packet size");eps=eps+1;
    end p=p+collected[p];
   end check(eps==4&&interfaces==3,"descriptor walk complete");
  end
  control_get(8'h80,6,16'h0200,0,9,9);
  control_get(8'h80,6,16'h0600,0,255,10);check(collected[7]==64,"qualifier EP0 size64");
  control_get(8'h80,6,16'h0700,0,255,124);check(collected[1]==7,"other speed config");
  control_get(8'h80,6,16'h0302,16'h0409,255,36);
  setup(8'h80,6,16'h9900,0,32);base=response_count;token(4'h9,0);check_handshake(base,8'h1e);
  setup(8'h21,8'h22,3,0,0);base=response_count;token(4'h9,0);check_handshake(base,8'h1e);
  control_get(8'h80,8,0,0,1,1);check(collected[0]==0,"unconfigured");
  control_set(0,5,7,0);control_set(0,9,1,0);idle(20);
  check(online&&!control_reset&&(hs==HIGH_SPEED),"configured state crossed to application");
  control_get(8'h81,10,0,2,1,1);check(collected[0]==0,"vendor interface alternate0");

  // MIDI OUT contains 128 complete events in one 512-byte packet. Vendor
  // OUT concurrently fills its separate endpoint while application is stalled.
  for(i=0;i<BULK_BYTES/4;i=i+1)begin
   payload[i*4]=9;payload[i*4+1]=8'h90;payload[i*4+2]=i;payload[i*4+3]=100;
   expected_midi[midi_put]={8'd100,i[7:0],8'h90,8'h09};midi_put=midi_put+1;
  end
  token(4'h1,1);base=response_count;data_packet(4'h3,BULK_BYTES);check_handshake(base,8'hd2);
  for(i=0;i<BULK_BYTES;i=i+1)begin payload[i]=(i*37+19)&255;expected_control[control_put]=payload[i];control_put=control_put+1;end
  token(4'h1,2);base=response_count;data_packet(4'h3,BULK_BYTES);check_handshake(base,8'hd2);
  idle(300);check(midi_rx_valid&&control_rx_valid,"both endpoint CDC outputs stalled independently");
  // Neither a duplicate nor a NAKed new packet may become a second delivery.
  token(4'h1,2);base=response_count;data_packet(4'h3,BULK_BYTES);check_handshake(base,8'hd2);
  if(HIGH_SPEED)begin
   token(4'h1,2);base=response_count;data_packet(4'hb,BULK_BYTES);check_handshake(base,8'h5a);
  end
  midi_rx_ready=1;control_rx_ready=1;
  while(midi_get<midi_put||control_seen<control_put)idle(1);
  idle(20);check(!midi_rx_valid&&!control_rx_valid,"OUT data drained without duplicate");
  for(i=0;i<4;i=i+1)payload[i]=i+20;
  corrupt_crc=1;token(4'h1,1);base=response_count;data_packet(4'hb,4);idle(40);
  check(response_count==base&&!midi_rx_valid,"bad CRC packet silently rejected before CDC");corrupt_crc=0;
  token(4'h1,1);base=response_count;rxerror=1;data_packet(4'hb,4);idle(40);
  check(response_count==base&&!midi_rx_valid,"PHY errored packet rejected before CDC");rxerror=0;
  token(4'h1,1);base=response_count;data_packet(4'h7,4);idle(40);
  check(response_count==base&&!midi_rx_valid,"DATA2 cannot enter a bulk endpoint");
  corrupt_token_crc=1;base=response_count;token(4'h9,1);idle(40);
  check(response_count==base,"bad token CRC5 produces no transaction");corrupt_token_crc=0;
  expected_midi[midi_put]=32'h17161514;midi_put=midi_put+1;
  token(4'h1,1);base=response_count;data_packet(4'hb,4);check_handshake(base,8'hd2);
  while(midi_get<midi_put)idle(1);

  // Aggregate application events/bytes, preserve separate packet buffers,
  // resend identical payload/toggle when ACK is lost.
  for(i=0;i<12;i=i+1)app_midi({8'd90,i[7:0],8'h91,8'h09});
  for(i=0;i<16;i=i+1)app_control(i+80);
  idle(80);base=response_count;token(4'h9,1);
  txready=0;#1;held_tx_byte=txdata;
  repeat(5)begin idle(1);check(txvalid&&txdata===held_tx_byte,"UTMI TX data stable while PHY backpressures");end
  txready=1;wait_response(base);check_data;
  check(response_len==51&&response[0]==8'hc3,"aggregated twelve MIDI events");
  for(i=0;i<12;i=i+1)begin check(response[1+i*4]==9&&response[2+i*4]==8'h91&&response[3+i*4]==i&&response[4+i*4]==90,"MIDI aggregate order");end
  base=response_count;token(4'h9,1);wait_response(base);check_data;
  check(response_len==51&&response[0]==8'hc3,"unACKed MIDI packet retransmits same length/toggle");host_ack;
  base=response_count;token(4'h9,1);check_handshake(base,8'h5a);
  base=response_count;token(4'h9,2);wait_response(base);check_data;check(response_len==19,"vendor IN aggregation independent");
  for(i=0;i<16;i=i+1)check(response[i+1]==i+80,"vendor IN byte order");host_ack;

  // A real host suspend leaves FS idle J. An HS PHY first observes SE0,
  // then restores FS termination at 3ms so idle resolves to J. Preserve
  // address, configuration, both IN packet buffers and stalled OUT queues.
  app_midi(32'h5a3d9409);app_control(8'hb7);idle(60);
  midi_rx_ready=0;control_rx_ready=0;
  expected_midi[midi_put]=32'h402e9509;midi_put=midi_put+1;
  payload[0]=9;payload[1]=8'h95;payload[2]=8'h2e;payload[3]=8'h40;
  token(4'h1,1);base=response_count;data_packet(4'h3,4);check_handshake(base,8'hd2);
  expected_control[control_put]=8'h6d;control_put=control_put+1;
  payload[0]=8'h6d;token(4'h1,2);base=response_count;data_packet(4'hb,1);check_handshake(base,8'hd2);
  idle(80);before_count=response_count;
  if(HIGH_SPEED)begin
   linestate=0;wait(hsstate==6);check(xcvr==1&&term,"HS suspend restores FS termination");
   linestate=1;
  end
  idle(600000); // 10ms idle with no SOF or host transactions
  check(online&&!control_reset&&address==7&&(hs==HIGH_SPEED),"suspend retains address/configuration/negotiated speed");
  check(midi_rx_valid&&midi_rx_data==32'h402e9509&&control_rx_valid&&control_rx_data==8'h6d,
        "suspend preserves both stalled OUT CDC heads");
  check(response_count==before_count&&!txvalid,"suspended device does not originate remote resume or packets");
  // Host resumes with K for 20ms and a terminating SE0 EOP.
  linestate=2;idle(1200000);linestate=0;idle(12);linestate=HIGH_SPEED?0:1;idle(60);
  check(online&&!control_reset&&address==7&&(hs==HIGH_SPEED),"host resume restores existing session");
  if(HIGH_SPEED)check(hsstate==5&&xcvr==0&&!term,"resume EOP restores HS receiver");
  midi_rx_ready=1;control_rx_ready=1;
  while(midi_get<midi_put||control_seen<control_put)idle(1);
  base=response_count;token(4'h9,1);wait_response(base);check_data;
  check(response_len==7&&{response[4],response[3],response[2],response[1]}==32'h5a3d9409,
        "MIDI IN queued before suspend resumes intact");host_ack;
  base=response_count;token(4'h9,2);wait_response(base);check_data;
  check(response_len==4&&response[1]==8'hb7,"screen IN queued before suspend resumes intact");host_ack;

  // SET_INTERFACE resets only the selected interface, including its CDC
  // buffers. Opening the screen interface must not discard queued MIDI.
  app_midi(32'h643f9209);app_control(8'h55);idle(60);
  control_set(1,11,0,2);idle(30);
  check(online&&!control_reset,"vendor alternate0 leaves MIDI session available");
  base=response_count;token(4'h9,2);check_handshake(base,8'h5a);
  base=response_count;token(4'h9,1);wait_response(base);check_data;
  check(response_len==7&&{response[4],response[3],response[2],response[1]}==32'h643f9209,
        "screen interface reset preserves queued MIDI");host_ack;
  app_midi(32'h64409309);app_control(8'h56);idle(60);
  control_set(1,11,0,1);idle(30);
  base=response_count;token(4'h9,1);check_handshake(base,8'h5a);
  base=response_count;token(4'h9,2);wait_response(base);check_data;
  check(response_len==4&&response[1]==8'h56,"MIDI interface reset preserves vendor queue");host_ack;

  // Endpoint halt is per direction; clear halt resets the data toggle.
  control_set(2,3,0,16'h0081);control_get(8'h82,0,0,16'h0081,2,2);check(collected[0]==1,"GET_STATUS endpoint halt");
  base=response_count;token(4'h9,1);check_handshake(base,8'h1e);
  control_set(2,1,0,16'h0081);app_midi(32'h003c8008);idle(50);
  base=response_count;token(4'h9,1);wait_response(base);check_data;
  check(response[0]==8'hc3&&response_len==7,"clear halt restores DATA0");host_ack;

  // Deconfiguration is a real session boundary, clearing queued data in both
  // clocks, then fresh configuration starts empty.
  app_midi(32'h643c9009);app_control(8'haa);idle(50);
  control_set(0,9,0,0);idle(20);check(!online&&control_reset&&!midi_tx_ready,"deconfiguration flushes app interface");
  control_set(0,9,1,0);idle(30);
  base=response_count;token(4'h9,1);check_handshake(base,8'h5a);
  base=response_count;token(4'h9,2);check_handshake(base,8'h5a);
  // Real bus reset and a fresh speed negotiation must clear address,
  // configuration, bulk toggles, both CDC directions, and partial controls.
  linestate=0;idle(650000);
  check(!online&&control_reset&&address==0,"USB bus reset clears the complete session");
  wait(hsstate==3);
  if(HIGH_SPEED)begin
   for(i=0;i<6;i=i+1)begin linestate=i[0]?1:2;idle(2400);end
   check(hsstate==5,"HS renegotiates after reset");
  end else begin wait(hsstate==4);check(!hs,"FS fallback repeats after reset");end
  linestate=HIGH_SPEED?0:1;idle(20);current_address=0;
  control_get(8'h80,6,16'h0100,0,18,18);
  control_set(0,5,9,0);control_set(0,9,1,0);idle(20);
  check(online&&address==9,"new session enumerates after bus reset");
  base=response_count;token(4'h9,1);check_handshake(base,8'h5a);
  base=response_count;token(4'h9,2);check_handshake(base,8'h5a);
  $display("PASS USB board UTMI + 50/60MHz CDC speed=%0d: %0d checks MIDI_OUT=%0d vendor_OUT=%0d, descriptors, independent endpoints, aggregation, CRC rollback, duplicate OUT, lost-ACK retry, halt, suspend/resume, session reset",HIGH_SPEED?480:12,checks,midi_get,control_seen);
  $finish;
 end
 initial begin #100000000;$fatal(1,"USB board simulation timeout");end
endmodule
