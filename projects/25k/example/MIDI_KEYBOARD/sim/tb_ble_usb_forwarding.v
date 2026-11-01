`timescale 1ns/1ps
module tb_ble_usb_forwarding;
 reg clk=0;always #10 clk=~clk;
 reg reset=1,control_reset=0,usb_online=0,ble_online=0;
 reg [15:0] key_bitmap=0;
 reg enc1_press=0;
 wire usb_packet_tx_valid;reg usb_packet_tx_ready=1;wire [31:0] usb_packet_tx_data;
 reg usb_packet_rx_valid=0;wire usb_packet_rx_ready;reg [31:0] usb_packet_rx_data=0;
 wire ble_value_tx_valid;wire [39:0] ble_value_tx_data;wire [2:0] ble_value_tx_length;
 reg ble_value_rx_valid=0;wire ble_value_rx_ready;reg [39:0] ble_value_rx_data=0;
 reg [2:0] ble_value_rx_length=0;
 wire [15:0] lamp_keys;
 midi_keyboard_application #(.CLK_HZ(1000000),.FIFO_DEPTH(2)) dut(
  .clk(clk),.reset(reset),.control_reset(control_reset),.usb_online(usb_online),.ble_online(ble_online),
  .touch_diagnostics(800'd0),.pluck_diagnostics(512'd0),.pluck_noise_diagnostics(512'd0),.pluck_diagnostics_valid(1'b1),
  .input_config_write(),.input_config_opcode(),.input_config_value(),
  .key_bitmap(key_bitmap),.keypad_ready(1'b1),.slider_valid(1'b0),.slider_touch(1'b0),.slider_position(8'd128),
  .enc1_step(1'b0),.enc1_press(enc1_press),.enc2_step(1'b0),.enc2_press(1'b0),.enc1_direction(2'sd1),.enc2_direction(2'sd1),
  .usb_packet_tx_valid(usb_packet_tx_valid),.usb_packet_tx_ready(usb_packet_tx_ready),.usb_packet_tx_data(usb_packet_tx_data),
  .usb_packet_rx_valid(usb_packet_rx_valid),.usb_packet_rx_ready(usb_packet_rx_ready),.usb_packet_rx_data(usb_packet_rx_data),
  .ble_value_tx_valid(ble_value_tx_valid),.ble_value_tx_ready(1'b1),.ble_value_tx_data(ble_value_tx_data),.ble_value_tx_length(ble_value_tx_length),
  .ble_value_rx_valid(ble_value_rx_valid),.ble_value_rx_ready(ble_value_rx_ready),.ble_value_rx_data(ble_value_rx_data),.ble_value_rx_length(ble_value_rx_length),
  .control_rx_valid(1'b0),.control_rx_ready(),.control_rx_data(8'd0),.control_tx_valid(),.control_tx_ready(1'b1),.control_tx_data(),
  .midi_channel(),.transpose(),.velocity(),.program_number(),.slider_mode(),.brightness(),.strip_value(),.focus(),
  .active_keys(),.lamp_keys(lamp_keys),.panic_busy(),.theme_rgb565(),.clear_rgb565(),.screen_page(),.screen_update(),.status_flags(),.emitted_events());
 reg [23:0] messages[0:8191];reg [3:0] kinds[0:8191];
 integer received=0,ble_received=0,mark,ble_mark,index,channel,cleanup_mark,ordered;
 reg stalled=0;reg [31:0] held_packet;
 reg bridge_stalled=0;reg [23:0] held_bridge;reg [1:0] held_length;
 always @(posedge clk)begin
  if(reset)begin stalled=0;bridge_stalled=0;end
  else begin
   if(bridge_stalled && usb_online && (!dut.ble_usb.out_valid || dut.ble_usb.out_message!==held_bridge || dut.ble_usb.out_length!==held_length))$fatal(1,"Arbiter changed a stalled message");
   bridge_stalled=usb_online&&dut.ble_usb.out_valid&&!dut.ble_usb.out_ready;
   held_bridge=dut.ble_usb.out_message;held_length=dut.ble_usb.out_length;
   if(stalled && usb_online && (!usb_packet_tx_valid || usb_packet_tx_data!==held_packet))$fatal(1,"USB changed under backpressure");
   stalled=usb_online&&usb_packet_tx_valid&&!usb_packet_tx_ready;held_packet=usb_packet_tx_data;
   if(usb_packet_tx_valid&&usb_packet_tx_ready)begin
    if(usb_packet_tx_data[7:4]!==0)$fatal(1,"Unexpected cable");
    messages[received]={usb_packet_tx_data[15:8],usb_packet_tx_data[23:16],usb_packet_tx_data[31:24]};
    kinds[received]=usb_packet_tx_data[3:0];received=received+1;
   end
   if(ble_value_tx_valid)ble_received=ble_received+1;
  end
 end
 task ticks(input integer cycles);repeat(cycles)@(negedge clk);endtask
 task phone(input [23:0] message,input [1:0] length);
  integer limit;
  begin
   @(negedge clk);ble_value_rx_data={message[7:0],message[15:8],message[23:16],8'hb7,8'h91};
   ble_value_rx_length={1'b0,length}+3'd2;ble_value_rx_valid=1;
   limit=0;while(!ble_value_rx_ready)begin @(negedge clk);limit=limit+1;if(limit>20000)$fatal(1,"BLE RX stalled indefinitely");end
   @(posedge clk);@(negedge clk);ble_value_rx_valid=0;
  end
 endtask
 task expect_one(input [23:0] message,input [1:0] length,input [3:0] cin);
  integer start,limit,prior_ble;
  begin
   start=received;prior_ble=ble_received;phone(message,length);
   limit=0;while(received==start && limit<600)begin ticks(1);limit=limit+1;end
   if(received!=start+1 || messages[start]!==message || kinds[start]!==cin)$fatal(1,"BLE -> USB missing/corrupt: wanted %06h CIN%h count%0d",message,cin,received-start);
   ticks(6);if(ble_received!=prior_ble)$fatal(1,"Phone MIDI echoed back to BLE");
  end
 endtask
 function integer count_message(input integer first,input [23:0] message);
  integer offset;
  begin count_message=0;for(offset=first;offset<received;offset=offset+1)if(messages[offset]===message)count_message=count_message+1;end
 endfunction
 task usb_feedback(input [23:0] message);
  begin
   @(negedge clk);usb_packet_rx_data={message[7:0],message[15:8],message[23:16],4'd0,message[23:20]};usb_packet_rx_valid=1;
   while(!usb_packet_rx_ready)@(negedge clk);
   @(posedge clk);@(negedge clk);usb_packet_rx_valid=0;
  end
 endtask
 initial begin
  ticks(5);reset=0;usb_online=1;ble_online=1;ticks(300);
  expect_one(24'h903046,3,9);if(lamp_keys!==1)$fatal(1,"BLE forwarding lost lamp feedback");
  expect_one(24'h803017,3,8);
  for(channel=0;channel<16;channel=channel+1)begin
   expect_one({4'h9,channel[3:0],8'd127,8'd37},3,9);
   expect_one({4'h9,channel[3:0],8'd127,8'd0},3,9);
   expect_one({4'hc,channel[3:0],8'd73,8'd0},2,12);
   expect_one({4'hd,channel[3:0],8'd29,8'd0},2,13);
   expect_one({4'ha,channel[3:0],8'd0,8'd45},3,10);
   expect_one({4'hb,channel[3:0],8'd74,8'd91},3,11);
   expect_one({4'he,channel[3:0],8'd127,8'd126},3,14);
  end
  expect_one(24'hf11300,2,2);expect_one(24'hf20102,3,3);expect_one(24'hf30300,2,2);
  expect_one(24'hf60000,1,5);expect_one(24'hf80000,1,15);expect_one(24'hfa0000,1,15);
  expect_one(24'hfb0000,1,15);expect_one(24'hfc0000,1,15);expect_one(24'hfe0000,1,15);
  expect_one(24'h930145,3,9);expect_one(24'hb37b00,3,11);
  expect_one(24'h940245,3,9);expect_one(24'hb47800,3,11);
  expect_one(24'hb5407f,3,11);expect_one(24'hb57900,3,11);
  expect_one(24'h950345,3,9);expect_one(24'hff0000,1,15);ticks(300);
  mark=received;ble_online=0;ticks(3000);if(received!=mark)$fatal(1,"Channel/system reset left stale cleanup ownership");
  ble_online=1;ticks(20);
  for(channel=0;channel<16;channel=channel+1)for(index=0;index<128;index=index+1)begin
   expect_one({4'h9,channel[3:0],index[7:0],8'd85},3,9);
   if(!index[0])expect_one({4'h8,channel[3:0],index[7:0],8'd12},3,8);
  end
  cleanup_mark=received;ble_online=0;ticks(3000);
  if(received!=cleanup_mark+1024)$fatal(1,"2048-note ownership map cleanup count mismatch");
  for(channel=0;channel<16;channel=channel+1)for(index=0;index<128;index=index+1)
   if(count_message(cleanup_mark,{4'h8,channel[3:0],index[7:0],8'd0})!=(index[0]?1:0))$fatal(1,"Ownership RAM byte/bit/channel alias");
  ble_online=1;ticks(20);
  mark=received;ble_value_rx_valid=1;ble_value_rx_length=5;ble_value_rx_data=40'h6430908000;
  ticks(1);ble_value_rx_valid=0;ticks(15);if(received!=mark)$fatal(1,"Malformed BLE reached USB");
  mark=received;ble_mark=ble_received;
  usb_feedback(24'h903164);ticks(10);
  if(received!=mark || ble_received!=ble_mark || lamp_keys!==2)$fatal(1,"USB feedback was echoed or not displayed");
  fork usb_feedback(24'h903264);phone(24'h903351,3);join
  ticks(20);if(lamp_keys!==14 || received!=mark+1)$fatal(1,"Simultaneous USB/BLE RX lost an event");
  usb_feedback(24'h803100);usb_feedback(24'h803200);expect_one(24'h803300,3,8);
  mark=received;ble_mark=ble_received;usb_packet_tx_ready=0;
  phone(24'h90402d,3);ticks(12);key_bitmap=1;ticks(20);
  fork
   begin for(index=0;index<24;index=index+1)phone({8'hb3,8'd74,index[7:0]},3);end
   begin ticks(70);usb_packet_tx_ready=1;end
  join
  ticks(500);
  if(count_message(mark,24'h90402d)!=1 || count_message(mark,24'h903064)!=1)$fatal(1,"Local/phone arbitration lost Note On");
  for(index=0;index<24;index=index+1)if(count_message(mark,{8'hb3,8'd74,index[7:0]})!=1)$fatal(1,"Phone burst lost/duplicated CC");
  ordered=0;
  for(index=mark;index<received;index=index+1)if(messages[index][23:8]==16'hb34a)begin
   if(messages[index][7:0]!==ordered[7:0])$fatal(1,"Phone burst reordered");ordered=ordered+1;
  end
  if(ble_received!=ble_mark+1)$fatal(1,"BLE RX burst leaked back to phone");
  expect_one(24'h91413d,3,9);expect_one(24'hb1407f,3,11);expect_one(24'h9f0055,3,9);
  expect_one(24'h924222,3,9);expect_one(24'h824200,3,8);
  mark=received;ble_online=0;ticks(3000);
  if(count_message(mark,24'h804000)!=1 || count_message(mark,24'h814100)!=1 || count_message(mark,24'h8f0000)!=1 || count_message(mark,24'hb14000)!=1)$fatal(1,"BLE disconnect failed exact-note/sustain cleanup");
  if(count_message(mark,24'h824200)!=0 || count_message(mark,24'h803000)!=0)$fatal(1,"BLE cleanup released unrelated/already released note");
  ble_online=1;ticks(30);expect_one(24'h903c35,3,9);
  usb_packet_tx_ready=0;phone(24'h903d36,3);ticks(20);ble_online=0;ticks(10);ble_online=1;
  fork phone(24'h903d37,3);begin ticks(50);usb_packet_tx_ready=1;end join
  ticks(3000);
  if(messages[received-1]!==24'h903d37)$fatal(1,"Old BLE cleanup crossed the new session");
  expect_one(24'h803d00,3,8);
  usb_packet_tx_ready=0;phone(24'h903e31,3);ticks(20);usb_online=0;ticks(5);key_bitmap=0;
  phone(24'h903f32,3);ticks(10);mark=received;usb_online=1;usb_packet_tx_ready=1;ticks(400);
  if(received!=mark)$fatal(1,"USB reconnect replayed old/offline phone MIDI");
  expect_one(24'h904031,3,9);control_reset=1;ticks(5);control_reset=0;expect_one(24'h804000,3,8);
  mark=received;ble_online=0;ticks(3000);if(received!=mark)$fatal(1,"USB old-session note tracking survived reset");
  $display("PASS BLE -> USB application: all channels/types, original velocity, lamps, no echo, backpressure/fairness, exact disconnect cleanup and session fencing");$finish;
 end
 initial begin #10000000;$fatal(1,"BLE -> USB forwarding timeout");end
endmodule
