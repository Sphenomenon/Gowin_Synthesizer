`timescale 1ns/1ps
module tb_pluck_carrier_midi;
 reg clk=0;
 always #10 clk=!clk;
 reg reset=1,busy=0,douta=0,doutb=0,emitter_arm=0,phase=0,packet_ready=1;
 reg [63:0] source_a=64'h13880fa00bb807d0,source_b=64'h03e804d200000000,serial_a,serial_b;
 wire convst,cs_n,sclk,ready,event_valid,event_ready,packet_valid;
 wire [4:0] emitters;
 wire [15:0] keys;
 wire [511:0] diagnostics,reference_data;
 wire [23:0] message;
 wire [1:0] length;
 wire [31:0] packet;
 reg [31:0] packets[0:31];
 reg [31:0] held_packet;
 integer packet_count=0,channel;
 midi_pluck_frontend #(.CLK_HZ(2000000),.SAMPLE_HZ(1000),.DIAGNOSTIC_ONLY(1),.DIAGNOSTIC_DETAILS(1),.VPP_MODE(1),.CARRIER_MODE(1)) frontend(
  .clk(clk),.reset(reset),.emitter_arm(emitter_arm),.adc_busy(busy),.adc_douta(douta),.adc_doutb(doutb),
  .on_threshold(16'd64),.off_threshold(16'd32),.recalibrate(1'b0),.midi_channel(4'd0),.transpose(8'sd0),
  .adc_convst(convst),.adc_cs_n(cs_n),.adc_sclk(sclk),.emitter_enable(emitters),.key_bitmap(keys),.ready(ready),
  .diagnostics(diagnostics),.noise_diagnostics(reference_data));
 gw138k_panel_performance performance(
  .clk(clk),.reset(reset),.key_bitmap(keys),.keypad_ready(ready),.slider_valid(1'b0),.slider_touch(1'b0),.slider_position(8'd128),
  .enc1_step(1'b0),.enc1_press(1'b0),.enc2_step(1'b0),.enc2_press(1'b0),.enc1_direction(2'd0),.enc2_direction(2'd0),
  .config_write(1'b0),.config_opcode(8'd0),.config_value(32'd0),.online(2'b01),.timestamp_ms(13'd0),
  .event_valid(event_valid),.event_ready(event_ready),.event_message(message),.event_length(length));
 usb_midi_codec codec(.clk(clk),.reset(reset),.tx_valid(event_valid),.tx_ready(event_ready),.tx_message(message),.tx_length(length),
  .packet_tx_valid(packet_valid),.packet_tx_ready(packet_ready),.packet_tx_data(packet),.packet_rx_valid(1'b0),.packet_rx_data(32'd0),.rx_ready(1'b1));
 always @(posedge convst)if(!reset)begin #45;busy=1;#4200;busy=0;end
 always @(negedge cs_n)begin
  phase=!phase;serial_a=phase ? source_a : 0;serial_b=phase ? source_b : 0;
  #35;douta=serial_a[63];doutb=serial_b[63];
 end
 always @(posedge sclk)if(!cs_n)begin
  serial_a=serial_a<<1;serial_b=serial_b<<1;#39;douta=serial_a[63];doutb=serial_b[63];
 end
 always @(posedge clk)if(!reset && packet_valid && packet_ready)begin
  if(packet_count==32)$fatal(1,"Unexpected MIDI flood");
  packets[packet_count]=packet;packet_count=packet_count+1;
 end
 initial begin
  repeat(4)@(negedge clk);reset=0;
  repeat(8)@(posedge frontend.sample_valid);
  @(negedge clk);
  if(ready || emitters!=0 || packet_count!=0)$fatal(1,"Carrier probe did not start OFF");
  emitter_arm=1;wait(ready);@(negedge clk);
  if(!diagnostics[47] || diagnostics[46] || !reference_data[66] || !reference_data[67] || diagnostics[511:496]!=2)
   $fatal(1,"Carrier probe capability/window/enable readback mismatch");
  if(reference_data[175:96]!=={16'd5000,16'd4000,16'd3000,16'd2000,16'd1000})
   $fatal(1,"Serial ADC V5,V4,V3,V2,V1 to physical carrier references reversed");
  repeat(10)@(posedge frontend.frame_valid);@(negedge clk);
  if(packet_count!=0)$fatal(1,"Unblocked carriers produced MIDI");
  packet_ready=0;source_a=0;source_b=0;
  wait(packet_valid);held_packet=packet;
  repeat(30)begin @(negedge clk);if(!packet_valid || packet!==held_packet)$fatal(1,"Carrier MIDI USB backpressure changed event");end
  packet_ready=1;wait(packet_count==10);@(negedge clk);
  for(channel=0;channel<5;channel=channel+1)begin
   if(packets[channel]!==32'h64309009+(channel<<16) || packets[channel+5]!==32'h00308008+(channel<<16))
    $fatal(1,"Carrier CHN%0d is not mapped to shared MIDI A..E On/Off",channel+1);
  end
  repeat(50)@(posedge frontend.frame_valid);@(negedge clk);
  if(packet_count!=10 || diagnostics[319:288]!=5)$fatal(1,"Held all-five blockage repeated notes");
  source_a=64'h13880fa00bb807d0;source_b=64'h03e804d200000000;
  repeat(10)@(posedge frontend.frame_valid);@(negedge clk);
  source_b[63:48]=0;wait(packet_count==11);@(negedge clk);
  if(packets[10]!==32'h64309009)$fatal(1,"Restored CHN1 failed to rearm");
  emitter_arm=0;wait(!ready);wait(packet_count==12);@(negedge clk);
  if(emitters!=0 || keys!=0 || packets[11]!==32'h00308008)$fatal(1,"Disarm failed PWM/Note cancellation");
  $display("PASS tb_pluck_carrier_midi delayed dual serial -> V5..V1 physical references -> falling-Vpp debounce -> shared MIDI A..E, backpressure, no held-block retrigger and OFF cancellation");$finish;
 end
 initial begin #100000000;$fatal(1,"Carrier MIDI timeout packets=%0d samples=%0d calibrated=%b progress=%0d",packet_count,diagnostics[95:64],ready,reference_data[495:480]);end
endmodule
