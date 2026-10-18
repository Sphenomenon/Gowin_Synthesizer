`timescale 1ns/1ps
// GATT/SMP integration at the actual synchronous H5 mailbox boundary.
// The controller model returns explicitly supplied HCI results: H5 delivery,
// HCI command completion and ACL completion are deliberately independent.
module tb_ble_pairing_transport;
 reg clk=0,resetn=0;
 always #5 clk=~clk;
 reg rx_valid=0;
 reg [3:0]rx_type=0;
 reg [8:0]rx_length=0;
 wire [8:0]rx_addr;
 reg [7:0]rx_data=0;
 reg [7:0]mailbox[0:279];
 wire rx_consume,tx_start;
 wire [3:0]tx_type;
 wire [8:0]tx_length;
 reg tx_done=0;
 reg [8:0]tx_addr=0;
 wire [7:0]tx_data;
 reg value_valid=0;
 wire value_ready;
 wire connected,subscribed,failed;
 localparam [11:0] HANDLE=12'h345;
 localparam [47:0] LOCAL_ADDRESS=48'h665544332211;
 localparam [47:0] PEER_ADDRESS=48'hc6b5a4938271;
 midi_ble_gatt #(.CLK_HZ(1000000)) dut(
  .clk(clk),.resetn(resetn),.enable(1'b1),.local_address(LOCAL_ADDRESS),
  .rx_valid(rx_valid),.rx_type(rx_type),.rx_length(rx_length),
  .rx_payload_addr(rx_addr),.rx_payload_data(rx_data),.rx_consume(rx_consume),
  .tx_start(tx_start),.tx_type(tx_type),.tx_length(tx_length),
  .tx_ready(1'b1),.tx_done(tx_done),.tx_error(1'b0),
  .tx_payload_addr(tx_addr),.tx_payload_data(tx_data),
  .value_tx_valid(value_valid),.value_tx_ready(value_ready),
  .value_tx_data(40'h403c908080),.value_tx_length(3'd5),
  .value_rx_valid(),.value_rx_ready(1'b1),.value_rx_data(),.value_rx_length(),
  .connected(connected),.subscribed(subscribed),.failed(failed));
 always @(posedge clk)rx_data<=rx_addr<280?mailbox[rx_addr]:8'd0;
 integer transmitted=0,capture_byte;
 reg [3:0]sent_type[0:63];
 integer sent_length[0:63];
 reg [7:0]sent[0:2303];
 // Scan the public payload address port, including AES bytes 32..34.
 // This finishes before the next clock edge; tx_done remains under test control.
 always @(negedge clk)begin
  if(resetn && tx_start)begin
   if(transmitted>=64 || tx_length>36)$fatal(1,"Invalid integration transmit length");
   sent_type[transmitted]=tx_type;sent_length[transmitted]=tx_length;
   for(capture_byte=0;capture_byte<tx_length;capture_byte=capture_byte+1)begin
    tx_addr=capture_byte;#0.01;
    sent[transmitted*36+capture_byte]=tx_data;
    if(^tx_data===1'bx)$fatal(1,"Unknown byte at public transmit address %0d",capture_byte);
   end
   transmitted=transmitted+1;
  end
  if(resetn && failed)$fatal(1,"GATT transport failed during pairing integration");
 end
 integer i;
 task clear_mailbox;
  integer n;
  begin for(n=0;n<280;n=n+1)mailbox[n]=0;end
 endtask
 task send_mailbox;
  input [3:0]typ;input integer length;
  begin
   @(negedge clk);rx_type=typ;rx_length=length;rx_valid=1;
   wait(rx_consume);@(negedge clk);rx_valid=0;
   repeat(8)@(negedge clk);
  end
 endtask
 task wait_transmits;
  input integer expected;
  integer guard;
  begin
   guard=0;
   while(transmitted<expected && guard<5000)begin @(negedge clk);guard=guard+1;end
   if(transmitted!=expected)$fatal(1,"Expected %0d transmissions, observed %0d",expected,transmitted);
  end
 endtask
 task expect_quiet;
  input integer expected;
  begin
   repeat(60)@(negedge clk);
   if(transmitted!=expected)$fatal(1,"Unexpected progress: expected %0d transmissions, observed %0d",expected,transmitted);
  end
 endtask
 task finish_h5;
  begin
   @(negedge clk);tx_done=1;
   @(negedge clk);tx_done=0;
   repeat(4)@(negedge clk);
  end
 endtask
 task connection_event;
  integer n;
  begin
   clear_mailbox();mailbox[0]=8'h3e;mailbox[1]=19;mailbox[2]=1;
   mailbox[4]=HANDLE[7:0];mailbox[5]={4'd0,HANDLE[11:8]};
   mailbox[6]=1;mailbox[7]=1;
   for(n=0;n<6;n=n+1)mailbox[8+n]=PEER_ADDRESS[n*8+:8];
   mailbox[14]=24;mailbox[18]=200;send_mailbox(4,21);
   if(!connected || subscribed)$fatal(1,"Connection or CCCD state incorrect");
  end
 endtask
 task acl_header;
  input integer cid,length;
  begin
   clear_mailbox();mailbox[0]=HANDLE[7:0];mailbox[1]={4'h2,HANDLE[11:8]};
   mailbox[2]=length+4;mailbox[4]=length;mailbox[6]=cid;
  end
 endtask
 task acl_credit;
  begin
   clear_mailbox();mailbox[0]=8'h13;mailbox[1]=5;mailbox[2]=1;
   mailbox[3]=HANDLE[7:0];mailbox[4]={4'd0,HANDLE[11:8]};mailbox[5]=1;
   send_mailbox(4,7);
  end
 endtask
 task hci_complete_count;
  input [15:0]opcode;input integer credits,returned_length;input [127:0]returned_data;
  integer n;
  begin
   clear_mailbox();mailbox[0]=8'h0e;mailbox[1]=4+returned_length;mailbox[2]=credits;
   mailbox[3]=opcode[7:0];mailbox[4]=opcode[15:8];
   for(n=0;n<returned_length;n=n+1)mailbox[6+n]=returned_data[n*8+:8];
   send_mailbox(4,6+returned_length);
  end
 endtask
 task hci_complete;
  input [15:0]opcode;input integer returned_length;input [127:0]returned_data;
  begin hci_complete_count(opcode,1,returned_length,returned_data);end
 endtask
 task check_hci;
  input integer at;input [15:0]opcode;input integer parameters;
  begin
   if(sent_type[at]!==1 || sent_length[at]!==parameters+3 ||
      sent[at*36]!==opcode[7:0] || sent[at*36+1]!==opcode[15:8] ||
      sent[at*36+2]!==parameters)
    $fatal(1,"HCI frame %0d mismatch: type %0d length %0d opcode %02x%02x",at,sent_type[at],sent_length[at],sent[at*36+1],sent[at*36]);
  end
 endtask
 task check_acl;
  input integer at,cid,length;input [7:0]opcode;
  begin
   if(sent_type[at]!==2 || sent_length[at]!==length+8 ||
      sent[at*36]!==HANDLE[7:0] || sent[at*36+1]!=={4'd0,HANDLE[11:8]} ||
      sent[at*36+2]!==length+4 || sent[at*36+3]!==0 ||
      sent[at*36+4]!==length || sent[at*36+5]!==0 ||
      sent[at*36+6]!==cid || sent[at*36+7]!==0 || sent[at*36+8]!==opcode)
    $fatal(1,"ACL frame %0d header mismatch",at);
  end
 endtask
 task check_encrypt;
  input integer at;input [127:0]plaintext;
  integer n;
  begin
   check_hci(at,16'h2017,32);
   for(n=0;n<16;n=n+1)begin
    if(sent[at*36+3+n]!==0)$fatal(1,"Legacy Just Works AES key byte %0d was not zero",n);
    if(sent[at*36+19+n]!==plaintext[n*8+:8])
     $fatal(1,"AES frame %0d plaintext byte %0d: %02x expected %02x",at,n,sent[at*36+19+n],plaintext[n*8+:8]);
   end
  end
 endtask
 task pairing_request;
  begin
   acl_header(6,7);mailbox[8]=1;mailbox[9]=3;mailbox[12]=16;
   send_mailbox(2,15);
  end
 endtask
 task send_smp_128;
  input [7:0]opcode;input [127:0]value;
  integer n;
  begin
   acl_header(6,17);mailbox[8]=opcode;
   for(n=0;n<16;n=n+1)mailbox[9+n]=value[n*8+:8];
   send_mailbox(2,25);
  end
 endtask
 task subscribe;
  begin
   acl_header(4,5);mailbox[8]=8'h52;mailbox[9]=8;mailbox[11]=1;
   send_mailbox(2,13);
   if(!subscribed)$fatal(1,"Original ATT CCCD Write Command no longer works");
  end
 endtask
 task queue_notification;
  integer guard;
  begin
   @(negedge clk);value_valid=1;guard=0;
   while(!value_ready && guard<1000)begin @(negedge clk);guard=guard+1;end
   if(!value_ready)$fatal(1,"MIDI value did not become ready after pairing/cleanup");
   @(negedge clk);value_valid=0;
  end
 endtask
 localparam [55:0] PREQ=56'h00001000000301;
 localparam [55:0] PRES=56'h00001000000302;
 localparam [127:0] P1={PRES,PREQ,8'h00,8'h01};
 localparam [127:0] P2={32'd0,PEER_ADDRESS,LOCAL_ADDRESS};
 localparam [127:0] LOCAL_RANDOM=128'hfedcba98765432100123456789abcdef;
 localparam [127:0] PEER_RANDOM=128'h76543210fedcba989abcdef001234567;
 localparam [127:0] LOCAL_AES_FIRST=128'h102132435465768798a9bacbdcedfe0f;
 localparam [127:0] LOCAL_CONFIRM=128'h00112233445566778899aabbccddeeff;
 localparam [127:0] PEER_AES_FIRST=128'h0123456789abcdeffedcba9876543210;
 localparam [127:0] PEER_CONFIRM=128'hffeeddccbbaa99887766554433221100;
 localparam [127:0] STK=128'h0f1e2d3c4b5a69788796a5b4c3d2e1f0;
 localparam [63:0] DEVICE_NAME="GWK-MIDI";
 // Pairing sequence is below; all messages enter through the public mailbox.
 initial begin
  clear_mailbox();
  repeat(4)@(negedge clk);resetn=1;
  connection_event();
  pairing_request();wait_transmits(1);check_acl(0,6,7,2);
  for(i=0;i<7;i=i+1)if(sent[8+i]!==PRES[i*8+:8])
   $fatal(1,"Pairing Response byte %0d mismatch",i);
  finish_h5();
  // The response used the only ACL credit. HCI crypto must still run.
  send_smp_128(3,PEER_CONFIRM);wait_transmits(2);check_hci(1,16'h2018,0);
  // Command Complete cannot replace H5 delivery, and Num=0 blocks the next command.
  hci_complete_count(16'h2018,0,8,{64'd0,LOCAL_RANDOM[63:0]});expect_quiet(2);
  finish_h5();expect_quiet(2);
  hci_complete(16'h0c03,0,0);wait_transmits(3);check_hci(2,16'h2018,0);
  // H5 delivery cannot replace the actual command result, either.
  finish_h5();expect_quiet(3);
  hci_complete(16'h2018,8,{64'd0,LOCAL_RANDOM[127:64]});
  wait_transmits(4);check_encrypt(3,LOCAL_RANDOM^P1);
  hci_complete(16'h2017,16,LOCAL_AES_FIRST);expect_quiet(4);
  finish_h5();wait_transmits(5);check_encrypt(4,LOCAL_AES_FIRST^P2);
  finish_h5();expect_quiet(5);
  hci_complete(16'h2017,16,LOCAL_CONFIRM);expect_quiet(5);
  // Even after crypto completes, the security ACL must wait for controller credit.
  acl_credit();wait_transmits(6);check_acl(5,6,17,3);
  for(i=0;i<16;i=i+1)if(sent[5*36+9+i]!==LOCAL_CONFIRM[i*8+:8])
   $fatal(1,"SMP Confirm byte %0d mismatch",i);
  finish_h5();
  send_smp_128(4,PEER_RANDOM);wait_transmits(7);check_encrypt(6,PEER_RANDOM^P1);
  finish_h5();hci_complete(16'h2017,16,PEER_AES_FIRST);
  wait_transmits(8);check_encrypt(7,PEER_AES_FIRST^P2);
  finish_h5();hci_complete(16'h2017,16,PEER_CONFIRM);expect_quiet(8);
  acl_credit();wait_transmits(9);check_acl(8,6,17,4);
  for(i=0;i<16;i=i+1)if(sent[8*36+9+i]!==LOCAL_RANDOM[i*8+:8])
   $fatal(1,"SMP Random byte %0d mismatch",i);
  finish_h5();wait_transmits(10);
  check_encrypt(9,{LOCAL_RANDOM[63:0],PEER_RANDOM[63:0]});
  // A concurrent controller LTK request is retained until the STK result exists.
  clear_mailbox();mailbox[0]=8'h3e;mailbox[1]=13;mailbox[2]=5;
  mailbox[3]=HANDLE[7:0];mailbox[4]={4'd0,HANDLE[11:8]};send_mailbox(4,15);
  expect_quiet(10);finish_h5();expect_quiet(10);
  hci_complete(16'h2017,16,STK);wait_transmits(11);check_hci(10,16'h201a,18);
  if(sent[10*36+3]!==HANDLE[7:0] || sent[10*36+4]!=={4'd0,HANDLE[11:8]})
   $fatal(1,"LTK Reply handle mismatch");
  for(i=0;i<16;i=i+1)if(sent[10*36+5+i]!==STK[i*8+:8])
   $fatal(1,"LTK Reply STK byte %0d mismatch",i);
  finish_h5();hci_complete(16'h201a,2,{116'd0,HANDLE});
  clear_mailbox();mailbox[0]=8'h08;mailbox[1]=4;
  mailbox[3]=HANDLE[7:0];mailbox[4]={4'd0,HANDLE[11:8]};mailbox[5]=1;
  send_mailbox(4,6);
  // The old ATT read/CCCD and MIDI notification path shares security's ACL credit.
  acl_header(4,3);mailbox[8]=8'h0a;mailbox[9]=3;send_mailbox(2,11);
  expect_quiet(11);acl_credit();wait_transmits(12);check_acl(11,4,9,8'h0b);
  for(i=0;i<8;i=i+1)if(sent[11*36+9+i]!==DEVICE_NAME[(7-i)*8+:8])
   $fatal(1,"ATT device name byte %0d mismatch",i);
  finish_h5();subscribe();queue_notification();expect_quiet(12);
  acl_credit();wait_transmits(13);check_acl(12,4,8,8'h1b);finish_h5();
  // Abort another pairing while a controller command is outstanding.
  pairing_request();expect_quiet(13);acl_credit();wait_transmits(14);
  check_acl(13,6,7,2);finish_h5();send_smp_128(3,PEER_CONFIRM);
  wait_transmits(15);check_hci(14,16'h2018,0);finish_h5();
  clear_mailbox();mailbox[0]=5;mailbox[1]=4;
  mailbox[3]=HANDLE[7:0];mailbox[4]={4'd0,HANDLE[11:8]};mailbox[5]=8'h13;
  send_mailbox(4,6);
  if(connected || subscribed)$fatal(1,"Disconnect did not clear connection and CCCD");
  expect_quiet(15);
  hci_complete_count(16'h2018,0,8,128'h0123456789abcdef);expect_quiet(15);
  // Command credit survives disconnect; only a positive Num permits re-advertising.
  hci_complete(16'h0c03,0,0);wait_transmits(16);check_hci(15,16'h200a,1);
  if(sent[15*36+3]!==1)$fatal(1,"Advertising was not enabled after disconnect");
  finish_h5();hci_complete(16'h200a,0,0);expect_quiet(16);
  connection_event();subscribe();queue_notification();wait_transmits(17);
  check_acl(16,4,8,8'h1b);finish_h5();
  // Android commonly offers bonding + MITM + SC + CT2 (0x2D). With no local
  // input/output the legacy responder negotiates Just Works and EncKey only.
  acl_header(6,7);mailbox[8]=1;mailbox[9]=3;mailbox[11]=8'h2d;
  mailbox[12]=16;mailbox[13]=7;mailbox[14]=7;send_mailbox(2,15);
  expect_quiet(17);acl_credit();wait_transmits(18);check_acl(17,6,7,2);
  if(sent[17*36+9]!==3 || sent[17*36+10]!==0 || sent[17*36+11]!==1 ||
     sent[17*36+12]!==16 || sent[17*36+13]!==0 || sent[17*36+14]!==1)
   $fatal(1,"Android-style AuthReq did not negotiate Legacy Just Works/EncKey");
  if(value_ready)$fatal(1,"MIDI transmit was not paused during Android-style pairing");
  finish_h5();
  clear_mailbox();mailbox[0]=5;mailbox[1]=4;
  mailbox[3]=HANDLE[7:0];mailbox[4]={4'd0,HANDLE[11:8]};mailbox[5]=8'h13;
  send_mailbox(4,6);wait_transmits(19);check_hci(18,16'h200a,1);
  finish_h5();hci_complete(16'h200a,0,0);
  $display("PASS: BLE GATT/SMP synchronous mailbox routing, 35-byte AES payload/address inputs, independent H5/HCI/ACL credits, encrypted pairing, Android AuthReq negotiation, ATT/MIDI compatibility and disconnect cleanup/re-advertising");
  $finish;
 end
 initial begin #2000000;$fatal(1,"Pairing transport watchdog");end
endmodule
