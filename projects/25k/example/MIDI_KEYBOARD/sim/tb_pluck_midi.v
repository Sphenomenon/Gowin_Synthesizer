`timescale 1ns/1ps
module tb_pluck_midi;
 parameter integer DIAGNOSTIC_ONLY=0;
 parameter integer VPP_MODE=0;
 parameter integer ADAPTIVE_NOISE=0;
 reg clk=0;
 always #10 clk=!clk;
 reg reset=1,busy=0,douta=0,doutb=0;
 reg [63:0] source_a=0,source_b=0,serial_a,serial_b;
 reg [15:0] touch_keys=0;
 reg keypad_ready=0,packet_ready=1;
 reg emitter_arm=0;
 wire [4:0] emitters;
 wire convst,cs_n,sclk,ready,event_valid,event_ready,packet_valid;
 wire [15:0] pluck_keys;
 wire [511:0] diagnostics;
 wire [23:0] event_message;
 wire [1:0] event_length;
 wire [31:0] packet;
 wire [3:0] channel;
 wire signed [7:0] transpose;
 reg [31:0] received[0:31];
 reg [31:0] held;
 integer packet_count=0;
 reg sample_phase=0;
 reg [4:0] pwm_high=0,pwm_low=0;
 midi_pluck_frontend #(.CLK_HZ(1000000),.SAMPLE_HZ(250),.DIAGNOSTIC_ONLY(DIAGNOSTIC_ONLY),.DIAGNOSTIC_DETAILS(VPP_MODE),.VPP_MODE(VPP_MODE),.ADAPTIVE_NOISE(ADAPTIVE_NOISE)) frontend(
  .clk(clk),.reset(reset),.emitter_arm(emitter_arm),.adc_busy(busy),.adc_douta(douta),.adc_doutb(doutb),
  .on_threshold(16'd1024),.off_threshold(16'd512),.recalibrate(1'b0),
  .adc_convst(convst),.adc_cs_n(cs_n),.adc_sclk(sclk),.emitter_enable(emitters),
  .midi_channel(channel),.transpose(transpose),.key_bitmap(pluck_keys),.ready(ready),.diagnostics(diagnostics));
 gw138k_panel_performance performance(
  .clk(clk),.reset(reset),.key_bitmap((touch_keys & {16{keypad_ready}})|pluck_keys),.keypad_ready(keypad_ready||ready),
  .slider_valid(1'b0),.slider_touch(1'b0),.slider_position(8'd128),
  .enc1_step(1'b0),.enc1_press(1'b0),.enc2_step(1'b0),.enc2_press(1'b0),
  .enc1_direction(2'd0),.enc2_direction(2'd0),.config_write(1'b0),.config_opcode(8'd0),.config_value(32'd0),
  .online(2'b01),.timestamp_ms(13'd0),.event_valid(event_valid),.event_ready(event_ready),
  .event_message(event_message),.event_length(event_length),.midi_channel(channel),.transpose(transpose));
 usb_midi_codec codec(.clk(clk),.reset(reset),.tx_valid(event_valid),.tx_ready(event_ready),
  .tx_message(event_message),.tx_length(event_length),.packet_tx_valid(packet_valid),.packet_tx_ready(packet_ready),.packet_tx_data(packet),
  .packet_rx_valid(1'b0),.packet_rx_data(32'd0),.rx_ready(1'b1));
 always @(posedge convst)if(!reset)begin #30;busy=1;#3000;busy=0;end
 always @(negedge cs_n)begin
  sample_phase=!sample_phase;
  serial_a=VPP_MODE && !sample_phase ? 64'd0 : source_a;
  serial_b=VPP_MODE && !sample_phase ? 64'd0 : source_b;
  douta=serial_a[63];doutb=serial_b[63];
 end
 always @(posedge sclk)if(!cs_n)begin serial_a=serial_a<<1;serial_b=serial_b<<1;douta=serial_a[63];doutb=serial_b[63];end
 always @(posedge clk)if(!reset && packet_valid && packet_ready)begin
  received[packet_count]=packet;packet_count=packet_count+1;
 end
 task expect_packet;
  input integer expected_count;
  input [31:0] expected_packet;
  begin
   wait(packet_count==expected_count);@(negedge clk);
   if(received[expected_count-1]!==expected_packet)$fatal(1,"MIDI mapping mismatch %h",received[expected_count-1]);
  end
 endtask
 initial begin #80000000;$fatal(1,"pluck MIDI integration timeout count=%0d",packet_count);end
 initial begin
  repeat(4)@(negedge clk);reset=0;
  if(DIAGNOSTIC_ONLY)begin
   wait(diagnostics[95:64]>=70);@(negedge clk);
   if(ready || emitters!=0 || pluck_keys!=0 || packet_count!=0)$fatal(1,"probe armed/calibrated before explicit enable");
   if(!diagnostics[38] || diagnostics[39])$fatal(1,"probe identity/emitter state incorrect");
   emitter_arm=1;
  end
  wait(ready);repeat(20)@(negedge clk);
  if(!diagnostics[39])$fatal(1,"emitter arm status mismatch");
  repeat(1100)begin @(negedge clk);pwm_high=pwm_high|emitters;pwm_low=pwm_low|~emitters;end
  if(pwm_high!=31 || pwm_low!=31)$fatal(1,"all five emitter outputs must be PWM, not DC");
  if(!VPP_MODE && (diagnostics[37] || diagnostics[287:192]!=0 || diagnostics[479:384]!=0))
   $fatal(1,"compact diagnostic capability or reserved fields incorrect");
  if(VPP_MODE && (!diagnostics[45] || !diagnostics[37] || diagnostics[511:496]!=2))
   $fatal(1,"Vpp capability/window incorrect");
  if(diagnostics[46]!=(ADAPTIVE_NOISE!=0))$fatal(1,"adaptive noise capability incorrect");
  if(packet_count!=0)$fatal(1,"calibration replayed notes");
  source_b[63:48]=3000;
  expect_packet(1,32'h64309009);
  if(keypad_ready || (VPP_MODE ? diagnostics[207:192]!=3000 : diagnostics[111:96]!=3000))$fatal(1,"CHN1 must use V5 independently of touch readiness");
  source_b=0;
  expect_packet(2,32'h00308008);
  repeat(ADAPTIVE_NOISE ? 40000 : 10000)@(negedge clk);
  keypad_ready=1;touch_keys=1;
  expect_packet(3,32'h64309009);
  source_b[63:48]=3000;
  wait(diagnostics[319:288]==2);repeat(20)@(negedge clk);
  if(packet_count!=3)$fatal(1,"overlapping same-note sources emitted duplicate On");
  touch_keys=0;source_b=0;repeat(100)@(negedge clk);
  if(packet_count!=3)$fatal(1,"touch release killed a held pluck note");
  expect_packet(4,32'h00308008);
  repeat(ADAPTIVE_NOISE ? 40000 : 10000)@(negedge clk);
  packet_ready=0;source_a[15:0]=-4000;
  wait(packet_valid);held=packet;
  repeat(20)begin @(negedge clk);if(!packet_valid || packet!==held)$fatal(1,"USB backpressure changed packet");end
  packet_ready=1;
  expect_packet(5,32'h64319009);
  if(VPP_MODE ? diagnostics[223:208]!=4000 : diagnostics[127:112]!=16'hf060)$fatal(1,"CHN2 must use signed V4");
  source_a=0;
  expect_packet(6,32'h00318008);
  repeat(ADAPTIVE_NOISE ? 40000 : 10000)@(negedge clk);
  source_a=64'h1388ec7817700000;
  expect_packet(7,32'h64329009);
  expect_packet(8,32'h64339009);
  expect_packet(9,32'h64349009);
  if(VPP_MODE ? (diagnostics[239:224]!=6000 || diagnostics[255:240]!=5000 || diagnostics[271:256]!=5000) :
                (diagnostics[143:128]!=6000 || diagnostics[159:144]!=16'hec78 || diagnostics[175:160]!=5000))
   $fatal(1,"CHN3..5 physical order must be V3,V2,V1");
  source_a=0;
  expect_packet(10,32'h00328008);
  expect_packet(11,32'h00338008);
  expect_packet(12,32'h00348008);
  if(DIAGNOSTIC_ONLY)begin
   emitter_arm=0;wait(!ready);@(negedge clk);
   if(emitters!=0 || pluck_keys!=0)$fatal(1,"disarming did not inhibit input");
  end
  $display("PASS tb_pluck_midi real serial -> physical channels -> shared touch mapping -> USB On/Off, overlap and backpressure");$finish;
 end
endmodule
