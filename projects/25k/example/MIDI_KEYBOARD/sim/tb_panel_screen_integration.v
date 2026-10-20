`timescale 1ns/1ps
// Imported legacy control policy integration; 138K panel controls have a
// separate production application test in tb_gw138k_panel_controls.
// Integration of the actual shared USB control path and musical application.
// The renderer handshake/RAM consumer is bounded here; physical SPI and both
// rotations are independently decoded in tb_remote_tile_display.
module tb_panel_screen_integration;
 reg clk=0,reset=1,control_reset=0;
 always #5 clk=~clk;
 reg rx_valid=0,tx_ready=1;
 reg [7:0] rx_data=0;
 wire rx_ready,tx_valid;
 wire [7:0] tx_data;
 wire mk_rv,mk_rr,mk_tv,mk_tr,mk_reset,pl_rv,pl_rr,pl_tv,pl_tr,pl_reset;
 wire [7:0] mk_rd,mk_td,pl_rd,pl_td;
 screen_stream_router #(.CLK_HZ(1000),.TIMEOUT_MS(3000)) router(
  .clk(clk),.reset(reset||control_reset),.rx_valid(rx_valid),.rx_ready(rx_ready),.rx_data(rx_data),
  .tx_valid(tx_valid),.tx_ready(tx_ready),.tx_data(tx_data),
  .mk_rx_valid(mk_rv),.mk_rx_ready(mk_rr),.mk_rx_data(mk_rd),
  .mk_tx_valid(mk_tv),.mk_tx_ready(mk_tr),.mk_tx_data(mk_td),.mk_reset(mk_reset),
  .pl_rx_valid(pl_rv),.pl_rx_ready(pl_rr),.pl_rx_data(pl_rd),
  .pl_tx_valid(pl_tv),.pl_tx_ready(pl_tr),.pl_tx_data(pl_td),.pl_reset(pl_reset));
 reg e1_pressed=0,e2_press=0;
 wire e1_short,e1_long;
 encoder_button_gestures #(.CLK_HZ(1000),.LONG_PRESS_MS(1000)) gestures(
  .clk(clk),.reset(reset),.pressed(e1_pressed),.short_press(e1_short),.long_press(e1_long));
 wire remote_enable,manual_settings,redraw_required,tile_valid,tile_ready;
 wire [15:0] panel_errors,tile_read_data;
 wire [8:0] tile_x,tile_width;
 wire [7:0] tile_y,tile_height;
 reg [7:0] tile_read_addr=0;
 reg tile_done=0;
 panel_display_endpoint #(.CLK_HZ(1000),.HEARTBEAT_MS(5000)) panel(
  .clk(clk),.reset(reset),.link_reset(control_reset||pl_reset),
  .rx_valid(pl_rv),.rx_ready(pl_rr),.rx_data(pl_rd),
  .tx_valid(pl_tv),.tx_ready(pl_tr),.tx_data(pl_td),.settings_toggle(e1_long),
  .remote_enable(remote_enable),.manual_settings(manual_settings),.redraw_required(redraw_required),
  .protocol_errors(panel_errors),.tile_valid(tile_valid),.tile_ready(tile_ready),
  .tile_x(tile_x),.tile_y(tile_y),.tile_width(tile_width),.tile_height(tile_height),
  .tile_read_addr(tile_read_addr),.tile_read_data(tile_read_data),.tile_done(tile_done));
 reg [15:0] keys=0;
 wire midi_valid,midi_ready;
 wire [31:0] midi_data,status_flags;
 wire [3:0] channel;
 wire [1:0] slider_mode;
 wire [15:0] active_keys;
 wire panic_busy;
 midi_keyboard_application #(.CLK_HZ(1000),.HOST_PANEL_CONTROLS(0)) app(
  .clk(clk),.reset(reset),.control_reset(control_reset||mk_reset),.usb_online(1'b1),.ble_online(1'b0),
  .key_bitmap(keys),.keypad_ready(1'b1),.slider_valid(1'b0),.slider_touch(1'b0),.slider_position(8'd0),
  .enc1_step(1'b0),.enc1_press(e1_short&&!remote_enable),.enc1_direction(2'sd1),
  .enc2_step(1'b0),.enc2_press(e2_press),.enc2_direction(2'sd1),
  .usb_packet_tx_valid(midi_valid),.usb_packet_tx_ready(1'b1),.usb_packet_tx_data(midi_data),
  .usb_packet_rx_valid(1'b0),.usb_packet_rx_ready(),.usb_packet_rx_data(32'd0),
  .ble_value_tx_valid(),.ble_value_tx_ready(1'b1),.ble_value_tx_data(),.ble_value_tx_length(),
  .ble_value_rx_valid(1'b0),.ble_value_rx_ready(),.ble_value_rx_data(40'd0),.ble_value_rx_length(3'd0),
  .control_rx_valid(mk_rv),.control_rx_ready(mk_rr),.control_rx_data(mk_rd),
  .control_tx_valid(mk_tv),.control_tx_ready(mk_tr),.control_tx_data(mk_td),
  .midi_channel(channel),.transpose(),.velocity(),.program_number(),.slider_mode(slider_mode),
  .brightness(),.strip_value(),.focus(),.active_keys(active_keys),.lamp_keys(),.panic_busy(panic_busy),
  .theme_rgb565(),.clear_rgb565(),.screen_page(),.screen_update(),.status_flags(status_flags),.emitted_events());

 // A synchronous RAM client accepts only complete tiles and deliberately
 // holds completion independently of the request/reply transport.
 reg render_accept=0,render_release=0,render_busy=0,render_data_done=0;
 reg [8:0] render_x=0;
 integer read_wait=0,render_index=0,draws=0,render_starts=0;
 assign tile_ready=render_accept&&!render_busy&&remote_enable;
 function [15:0] expected_pixel;
  input integer x,index;
  begin
   if(x==12)expected_pixel=index==0 ? 16'h4b4d : 16'h4c50;
   else if(x==13)expected_pixel=index==0 ? 16'h1357 : 16'h2468;
   else expected_pixel=index==0 ? 16'hf81f : 16'h07e0;
  end
 endfunction
 always @(posedge clk)begin
  tile_done<=0;
  if(reset)begin
   render_busy<=0;render_data_done<=0;tile_read_addr<=0;read_wait<=0;
   render_index<=0;draws<=0;render_starts<=0;
  end else begin
   if(tile_valid&&tile_ready)begin
    if(tile_width!=2 || tile_height!=1 || tile_y!=7)$fatal(1,"Incorrect tile metadata through integration");
    render_busy<=1;render_data_done<=0;render_x<=tile_x;
    render_index<=0;tile_read_addr<=0;read_wait<=2;render_starts<=render_starts+1;
   end
   if(render_busy)begin
    if(!render_data_done)begin
     if(read_wait!=0)read_wait<=read_wait-1;
     else begin
      if(tile_read_data!==expected_pixel(render_x,render_index))
       $fatal(1,"Synchronous tile RAM changed/wrong data x%0d index%0d got%04h",render_x,render_index,tile_read_data);
      if(render_index==1)render_data_done<=1;
      else begin render_index<=1;tile_read_addr<=1;read_wait<=2;end
     end
    end else if(tile_read_data!==expected_pixel(render_x,1))
     $fatal(1,"In-flight tile RAM overwritten before tile_done");
    if(render_data_done&&render_release)begin
     tile_done<=1;render_busy<=0;draws<=draws+1;
    end
   end
  end
 end

 reg [7:0] request[0:527],reply[0:8191];
 integer reply_count=0,midi_count=0,note_on_count=0,panic_count=0;
 integer short_count=0,long_count=0,mk_bytes=0,pl_bytes=0,router_resets=0;
 integer checks=0,i,base,mk_before,midi_before,panic_before,control_seq=11,display_seq=0;
 always @(posedge clk)if(!reset)begin
  if(tx_valid&&tx_ready)begin reply[reply_count]=tx_data;reply_count=reply_count+1;end
  if(mk_rv&&mk_rr)mk_bytes=mk_bytes+1;
  if(pl_rv&&pl_rr)pl_bytes=pl_bytes+1;
  if(mk_reset||pl_reset)router_resets=router_resets+1;
  if(midi_valid)begin
   midi_count=midi_count+1;
   if(midi_data[15:12]==9 && midi_data[31:24]!=0)begin
    if(midi_data[15:8]!=8'h94 || midi_data[23:16]!=48)$fatal(1,"Wrong touch note during display stall");
    note_on_count=note_on_count+1;
   end
   if((midi_data[15:12]==11 && (midi_data[23:16]==120 || midi_data[23:16]==123)) ||
       midi_data[15:12]==14)panic_count=panic_count+1;
  end
  if(e1_short)short_count=short_count+1;
  if(e1_long)long_count=long_count+1;
 end
 task check;
  input condition;input [767:0] message;
  begin checks=checks+1;if(condition!==1'b1)$fatal(1,"%0s at %0t",message,$time);end
 endtask
 task tick;
  input integer n;
  begin repeat(n)@(posedge clk);#1;end
 endtask
 task send_request;
  input integer length;integer n;
  begin
   for(n=0;n<length;n=n+1)begin
    @(negedge clk);rx_data=request[n];rx_valid=1;
    @(posedge clk);while(!rx_ready)@(posedge clk);#1;
   end
   @(negedge clk);rx_valid=0;
  end
 endtask
 task pl_header;
  input [7:0] kind,flags;input [31:0] session;
  input integer seq,length;
  begin
   request[0]=8'h50;request[1]=8'h4c;request[2]=1;request[3]=kind;
   request[4]=session;request[5]=session>>8;request[6]=session>>16;request[7]=session>>24;
   request[8]=seq;request[9]=seq>>8;request[10]=0;request[11]=0;
   request[12]=length;request[13]=length>>8;request[14]=flags;request[15]=1;
  end
 endtask
 task expect_pl;
  input integer start,kind,seq,length,status;
  begin
   wait(reply_count>=start+16+length);tick(2);
   check(reply_count==start+16+length,"PL response has exact bounded length");
   check(reply[start]==8'h50&&reply[start+1]==8'h4c&&reply[start+2]==1&&reply[start+3]==kind,
    "PL response magic/version/type preserved by router");
   check(reply[start+8]==(seq&255)&&reply[start+9]==(seq>>8)&&
    reply[start+10]==(seq&255)&&reply[start+11]==(seq>>8),"PL response seq and ack echo request");
   check(reply[start+12]==length&&reply[start+13]==0,"PL response payload length");
   if(length==8)check(reply[start+16]==status,"PL response status");
  end
 endtask
 task hello;
  input [31:0] session;input integer seq;
  begin
   base=reply_count;pl_header(1,1,session,seq,0);send_request(16);expect_pl(base,8'h81,seq,12,0);
   check({reply[base+17],reply[base+16]}==428&&{reply[base+19],reply[base+18]}==142&&
    reply[base+20]==1&&{reply[base+23],reply[base+22]}==248&&
    {reply[base+25],reply[base+24]}==512,"CAPS actual landscape dimensions and tile bounds");
  end
 endtask
 task health;
  begin
   base=reply_count;pl_header(2,1,32'h12345678,control_seq,0);send_request(16);
   expect_pl(base,8'h82,control_seq,8,0);control_seq=control_seq+1;
  end
 endtask
 task tile;
  input [31:0] session;input integer seq,x,expected_status;
  begin
   pl_header(8'h20,3,session,seq,20);
   request[16]=2;request[17]=0;request[18]=0;request[19]=0;
   request[20]=8'h44;request[21]=8'h33;request[22]=8'h22;request[23]=8'h11;
   request[24]=x;request[25]=0;request[26]=7;request[27]=0;
   request[28]=2;request[29]=0;request[30]=1;request[31]=0;
   request[32]=expected_pixel(x,0);request[33]=expected_pixel(x,0)>>8;
   request[34]=expected_pixel(x,1);request[35]=expected_pixel(x,1)>>8;
   base=reply_count;send_request(36);expect_pl(base,8'ha0,seq,8,expected_status);
  end
 endtask
 task frame_end_request;
  input [31:0] session;input integer seq;
  begin
   pl_header(8'h21,3,session,seq,8);
   request[16]=2;request[17]=0;request[18]=0;request[19]=0;
   request[20]=8'h44;request[21]=8'h33;request[22]=8'h22;request[23]=8'h11;
   send_request(24);
  end
 endtask
 function [15:0] crc_byte;
  input [15:0] previous;input [7:0] value;reg [15:0] work;integer b;
  begin work=previous^{value,8'd0};for(b=0;b<8;b=b+1)
   if(work[15])work=(work<<1)^16'h1021;else work=work<<1;crc_byte=work;end
 endfunction
 task mk_request;
  input [7:0] opcode;input [31:0] value;input integer seq;
  reg [15:0] crc;integer n,start;
  begin
   request[0]=8'h4d;request[1]=8'h4b;request[2]=1;request[3]=opcode;
   request[4]=seq;request[5]=seq>>8;
   request[6]=value;request[7]=value>>8;request[8]=value>>16;request[9]=value>>24;
   request[10]=0;request[11]=0;request[12]=0;request[13]=0;crc=16'hffff;
   for(n=0;n<14;n=n+1)crc=crc_byte(crc,request[n]);request[14]=crc;request[15]=crc>>8;
   start=reply_count;send_request(16);wait(reply_count>=start+16);tick(2);
   check(reply_count==start+16&&reply[start]==8'h4d&&reply[start+1]==8'h4b&&
    reply[start+3]==(opcode|8'h80),"MK reply remains independently framed");
   check({reply[start+9],reply[start+8],reply[start+7],reply[start+6]}==0,"MK status success");
   if(opcode==1)check(reply[start+10][0]&&!reply[start+10][1],"MK status reports USB online/BLE offline");
   else check({reply[start+13],reply[start+12],reply[start+11],reply[start+10]}==value,"MK write reply result");
   crc=16'hffff;for(n=0;n<14;n=n+1)crc=crc_byte(crc,reply[start+n]);
   check({reply[start+15],reply[start+14]}==crc,"MK response CRC survives shared path");
  end
 endtask
 task long_gesture;
  begin
   @(negedge clk);e1_pressed=1;
   tick(1000);check(!e1_long,"one-second gesture never fires early");
   tick(2);@(negedge clk);e1_pressed=0;tick(3);
  end
 endtask
 task finish_render;
  begin
   wait(render_busy&&render_data_done);@(negedge clk);render_release=1;
   tick(2);@(negedge clk);render_release=0;tick(2);
  end
 endtask

 initial begin
  tick(3);@(negedge clk);reset=0;tick(300);
  check(!remote_enable&&!manual_settings&&redraw_required,"no host input preserves local page");
  hello(32'h12345678,10);health;
  check(!remote_enable&&!tile_valid,"HELLO and HEALTH alone do not enter input page");
  mk_request(1,0,1);mk_request(8'h10,4,2);tick(30);
  check(channel==4&&!remote_enable,"MK settings coexist while local page remains active");
  mk_before=mk_bytes;
  tile(32'h12345678,display_seq,12,0);display_seq=display_seq+1;
  check(remote_enable&&tile_valid&&draws==0&&reply[base+15]==0,"TILE ACK precedes drawing and reserves credit");
  check(mk_bytes==mk_before&&channel==4,"embedded MK and PL pixel bytes never reroute");
  // LCD boot/initial clear can outlast the transport's normal interbyte
  // timeout. A tile not yet handed to the renderer must not monopolize the
  // router while FRAME_END waits: BUSY leaves its sequence available.
  base=reply_count;frame_end_request(32'h12345678,display_seq);
  expect_pl(base,8'ha0,display_seq,8,2);
  tick(350);health;
  check(tile_valid&&render_starts==0&&remote_enable&&router_resets==0,
   "startup FRAME_END BUSY releases router so HEALTH survives slow LCD readiness");
  @(negedge clk);render_accept=1;wait(render_busy&&render_data_done);
  base=reply_count;frame_end_request(32'h12345678,display_seq);tick(30);
  check(reply_count==base&&!tx_valid,"FRAME_END has no DRAWN reply before renderer completion");
  finish_render;expect_pl(base,8'ha1,display_seq,8,0);display_seq=display_seq+1;
  check(!redraw_required&&remote_enable&&reply[base+15]==1,"DRAWN releases credit after tile_done");
  repeat(3)begin tick(1200);health;check(remote_enable&&draws==1,"HEALTH maintains unchanged input page");end

  // An unconsumed screen response can exceed the router timeout; touch notes
  // and E2 panic still drain through the separate MIDI event pipeline.
  @(negedge clk);tx_ready=0;
  base=reply_count;pl_header(2,1,32'h12345678,control_seq,0);send_request(16);tick(20);
  check(tx_valid&&tx_data==8'h50,"screen response offered while host stalls");
  midi_before=midi_count;panic_before=panic_count;
  @(negedge clk);keys=1;tick(30);
  check(note_on_count==1&&active_keys==1,"touch produces USB note while screen host stalled");
  @(negedge clk);e2_press=1;tick(1);@(negedge clk);e2_press=0;tick(220);
  check(panic_count==panic_before+48&&!panic_busy&&active_keys==0,"E2 panic sends all-channel cleanup during screen stall");
  @(negedge clk);keys=0;tick(3000);
  check(tx_valid&&tx_data==8'h50&&reply_count==base&&router_resets==0&&midi_count>midi_before,
   "screen backpressure preserves offered byte without resetting or blocking MIDI");
  @(negedge clk);tx_ready=1;expect_pl(base,8'h82,control_seq,8,0);control_seq=control_seq+1;
  health;

  long_gesture;
  check(manual_settings&&!remote_enable&&long_count==1&&short_count==0&&slider_mode==0,
   "one-second E1 enters settings exactly once and suppresses short action");
  tile(32'h12345678,display_seq,13,1);display_seq=display_seq+1;
  check(manual_settings&&!remote_enable&&render_starts==1,"continued valid host tile cannot escape manual settings");
  health;long_gesture;
  check(!manual_settings&&!remote_enable&&redraw_required&&long_count==2&&short_count==0&&slider_mode==0,
   "second long press exits override but requires fresh tile");
  health;check(!remote_enable,"heartbeat does not restore stale canvas after override exit");
  tile(32'h12345678,display_seq,13,0);display_seq=display_seq+1;finish_render;
  base=reply_count;frame_end_request(32'h12345678,display_seq);expect_pl(base,8'ha1,display_seq,8,0);
  display_seq=display_seq+1;check(remote_enable&&draws==2,"fresh tile resumes remote page after settings");
  tick(5001);check(!remote_enable&&!manual_settings&&redraw_required,"heartbeat expiry falls back to local page");

  // Mirror top-level control_reset wiring: a USB control reset drops only
  // protocol/session state and cannot free a renderer's in-flight RAM lock.
  hello(32'h01020304,0);tile(32'h01020304,0,12,0);wait(render_busy&&render_data_done);
  @(negedge clk);control_reset=1;tick(2);@(negedge clk);control_reset=0;tick(2);
  check(!remote_enable&&render_busy,"control reset drops remote mode but retains physical renderer work");
  hello(32'h05060708,0);tile(32'h05060708,0,14,2);
  check(render_busy&&render_starts==3,"new session cannot overwrite old in-flight tile RAM");
  finish_render;tile(32'h05060708,0,14,0);finish_render;
  base=reply_count;frame_end_request(32'h05060708,1);expect_pl(base,8'ha1,1,8,0);
  check(remote_enable&&draws==4&&render_starts==4&&panel_errors==0&&router_resets==0,
   "same display sequence succeeds after BUSY and all subsystems recover from link reset");
  mk_request(1,0,3);check(channel==4,"control reset and PL sessions preserve MIDI settings");
  $display("PASS panel integration: %0d checks; real router+PL+MK+MIDI+one-second gestures, host-input page policy, heartbeat/expiry/manual override/fresh redraw, embedded magic, ACK vs physical completion, independent MIDI/panic under display stalls, link-reset RAM ownership",checks);
  $finish;
 end
 initial begin #1000000;$fatal(1,"Panel integration timeout router%0d panel%0d replies%0d",router.state,panel.state,reply_count);end
endmodule
