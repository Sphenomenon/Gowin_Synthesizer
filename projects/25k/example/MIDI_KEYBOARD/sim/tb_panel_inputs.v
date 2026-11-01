`timescale 1ns/1ps
module tb_panel_inputs;
 reg clk=0;
 always #10 clk=!clk;
 reg reset=1,control_reset=0,adc_present=0,busy=0,douta=0,doutb=0,phase=0;
 reg touch_ready=0,touch_slider_valid=0,touch_slider_touch=0;
 reg [15:0] touch_keys=0;
 reg [7:0] touch_slider_position=128;
 reg [63:0] source_a=64'h13880fa00bb807d0,source_b=64'h03e804d200000000,serial_a,serial_b;
 wire convst,cs_n,sclk,ready,slider_valid,slider_touch,diagnostics_valid;
 wire [7:0] slider_position,config_opcode;
 wire [4:0] emitters;
 wire [15:0] keys;
 wire [511:0] diagnostics,noise_diagnostics;
 wire config_write;
 wire [31:0] config_value;
 wire [3:0] midi_channel;
 wire signed [7:0] transpose;
 wire packet_valid;
 reg packet_ready=1;
 wire [31:0] packet;
 reg control_rx_valid=0,control_tx_ready=0;
 reg [7:0] control_rx_data=0;
 wire control_rx_ready,control_tx_valid;
 wire [7:0] control_tx_data;
 reg [31:0] packets[0:127];
 reg [127:0] request,response;
 reg [31:0] result;
 reg [127:0] voices=0;
 integer packet_count=0,byte_index,channel;
 midi_panel_inputs #(.CLK_HZ(1000000),.SAMPLE_HZ(1000)) inputs(
  .clk(clk),.reset(reset),.control_reset(control_reset),.touch_keys(touch_keys),.touch_ready(touch_ready),
  .touch_slider_valid(touch_slider_valid),.touch_slider_touch(touch_slider_touch),.touch_slider_position(touch_slider_position),
  .adc_busy(busy),.adc_douta(douta),.adc_doutb(doutb),.config_write(config_write),.config_opcode(config_opcode),.config_value(config_value),
  .midi_channel(midi_channel),.transpose(transpose),.adc_convst(convst),.adc_cs_n(cs_n),.adc_sclk(sclk),.emitters(emitters),
  .key_bitmap(keys),.ready(ready),.slider_valid(slider_valid),.slider_touch(slider_touch),.slider_position(slider_position),
  .diagnostics(diagnostics),.noise_diagnostics(noise_diagnostics),.diagnostics_valid(diagnostics_valid));
 defparam inputs.pluck.adc.HALF_CYCLES=5;
 midi_keyboard_application #(.CLK_HZ(1000000),.PLUCK_ENABLED(1)) app(
  .clk(clk),.reset(reset),.control_reset(control_reset),.usb_online(1'b1),.ble_online(1'b0),
  .touch_diagnostics(800'd0),.pluck_diagnostics(diagnostics),.pluck_noise_diagnostics(noise_diagnostics),
  .pluck_diagnostics_valid(diagnostics_valid),.input_config_write(config_write),.input_config_opcode(config_opcode),.input_config_value(config_value),
  .key_bitmap(keys),.keypad_ready(ready),.slider_valid(slider_valid),.slider_touch(slider_touch),.slider_position(slider_position),
  .enc1_step(1'b0),.enc1_press(1'b0),.enc2_step(1'b0),.enc2_press(1'b0),.enc1_direction(2'd0),.enc2_direction(2'd0),
  .usb_packet_tx_valid(packet_valid),.usb_packet_tx_ready(packet_ready),.usb_packet_tx_data(packet),
  .usb_packet_rx_valid(1'b0),.usb_packet_rx_data(32'd0),
  .ble_value_tx_ready(1'b1),.ble_value_rx_valid(1'b0),.ble_value_rx_data(40'd0),.ble_value_rx_length(3'd0),
  .control_rx_valid(control_rx_valid),.control_rx_ready(control_rx_ready),.control_rx_data(control_rx_data),
  .control_tx_valid(control_tx_valid),.control_tx_ready(control_tx_ready),.control_tx_data(control_tx_data),
  .midi_channel(midi_channel),.transpose(transpose));
 always @(posedge convst)if(!reset && adc_present)begin #45;busy=1;#4200;busy=0;end
 always @(negedge cs_n)begin
  phase=!phase;serial_a=phase ? source_a : 0;serial_b=phase ? source_b : 0;
  #35;douta=serial_a[63];doutb=serial_b[63];
 end
 always @(posedge sclk)if(!cs_n)begin
  serial_a=serial_a<<1;serial_b=serial_b<<1;#39;douta=serial_a[63];doutb=serial_b[63];
 end
 always @(posedge clk)if(!reset && packet_valid && packet_ready)begin
  if(packet_count==128)$fatal(1,"Integrated input MIDI flood");
  packets[packet_count]=packet;packet_count=packet_count+1;
  if(packet[15:12]==9)begin
   if(voices[packet[22:16]])$fatal(1,"Duplicate active note after source switch");
   voices[packet[22:16]]=1;
  end else if(packet[15:12]==8)voices[packet[22:16]]=0;
 end
 function [15:0] crc;
  input [111:0] payload;
  reg [15:0] work;
  integer byte_number,bit_number;
  begin
   work=16'hffff;
   for(byte_number=0;byte_number<14;byte_number=byte_number+1)begin
    work=work^{payload[byte_number*8+:8],8'd0};
    for(bit_number=0;bit_number<8;bit_number=bit_number+1)work=work[15] ? (work<<1)^16'h1021 : work<<1;
   end
   crc=work;
  end
 endfunction
 task query;
  input [7:0] opcode;
  input [31:0] value,expected_status;
  begin
   request={16'd0,32'd0,value,16'h4321,opcode,8'h01,16'h4b4d};request[127:112]=crc(request[111:0]);
   for(byte_index=0;byte_index<16;byte_index=byte_index+1)begin
    @(negedge clk);control_rx_data=request[byte_index*8+:8];control_rx_valid=1;
    @(posedge clk);while(!control_rx_ready)@(posedge clk);
    @(negedge clk);control_rx_valid=0;
   end
   wait(control_tx_valid);
   for(byte_index=0;byte_index<16;byte_index=byte_index+1)begin
    @(negedge clk);control_tx_ready=1;
    @(posedge clk);response[byte_index*8+:8]=control_tx_data;
    @(negedge clk);control_tx_ready=0;
   end
   if(response[127:112]!==crc(response[111:0]) || response[79:48]!==expected_status)
    $fatal(1,"Integrated MK reply failed: %h",response);
   result=response[111:80];
  end
 endtask
 initial begin
  repeat(4)@(negedge clk);reset=0;
  wait(inputs.pluck.timeouts!=0);@(negedge clk);
  if(ready || emitters!=0 || packet_count!=0)$fatal(1,"Missing accessory created input/PWM");
  touch_ready=1;touch_keys=16'h8001;
  wait(packet_count==2);@(negedge clk);
  if(packets[0]!==32'h64309009 || packets[1]!==32'h643f9009)$fatal(1,"Touch A/P MIDI mapping changed");
  touch_slider_touch=1;touch_slider_position=255;touch_slider_valid=1;
  @(negedge clk);touch_slider_valid=0;wait(packet_count==3);@(negedge clk);
  if(packets[2]!==32'h7f7fe00e)$fatal(1,"Touch pitch bend path changed");
  touch_ready=0;wait(packet_count==6);repeat(20)@(negedge clk);
  if(voices!=0 || packets[5]!==32'h4000e00e || ready || emitters!=0)
   $fatal(1,"Touch unplug did not release notes and center bend");
  packet_count=0;adc_present=1;
  wait(ready);@(negedge clk);
  if(!diagnostics[47] || diagnostics[46] || diagnostics[38] || !diagnostics[39] ||
     noise_diagnostics[175:96]!=={16'd5000,16'd4000,16'd3000,16'd2000,16'd1000})
   $fatal(1,"Complete carrier configuration/reference mismatch");
  repeat(10)@(posedge inputs.pluck.frame_valid);@(negedge clk);
  if(packet_count!=0)$fatal(1,"Open carrier caused MIDI");
  query(3,0,0);if(result!==32'h314b4c50)$fatal(1,"PLK1 unavailable in complete application");
  query(3,1,0);if(!result[15] || result[6])$fatal(1,"Complete application confused with diagnostic-only probe");
  query(6,0,0);if(result!==32'h314f4e50)$fatal(1,"PNO1 unavailable in complete application");
  query(6,2,0);if(result[12:8]!=31 || !result[3])$fatal(1,"Carrier reference validity missing");
  query(4,1,1);
  source_a=0;source_b=0;wait(packet_count==5);@(negedge clk);adc_present=0;
  wait(!diagnostics[32]);wait(packet_count==10);repeat(20)@(negedge clk);
  if(voices!=0 || emitters!=0 || ready)$fatal(1,"ADC loss did not disable PWM and release notes");
  for(channel=0;channel<5;channel=channel+1)
   if(packets[channel]!==32'h64309009+(channel<<16) || packets[channel+5]!==32'h00308008+(channel<<16))
    $fatal(1,"CHN%0d did not share touch A..E MIDI mapping",channel+1);
  source_a=64'h13880fa00bb807d0;source_b=64'h03e804d200000000;adc_present=1;
  wait(ready);@(negedge clk);
  touch_ready=1;touch_keys=0;repeat(40)@(negedge clk);
  if(emitters!=0 || keys!=0 || !ready)$fatal(1,"Touch did not take priority over a connected ADC");
  query(5,{16'd48,16'd96},0);
  if(inputs.on_threshold!=96 || inputs.off_threshold!=48)$fatal(1,"Threshold command did not reach input owner");
  control_reset=1;@(negedge clk);control_reset=0;repeat(5)@(negedge clk);
  if(inputs.on_threshold!=64 || inputs.off_threshold!=32 || emitters!=0)$fatal(1,"Control reset failed input defaults/isolation");
  $display("PASS tb_panel_inputs complete application: touch A/P/slider, automatic ADC/PWM, five carrier MIDI, PLK1/PNO1, source priority, fault release and settings reset");
  $finish;
 end
 initial begin #150000000;$fatal(1,"Integrated panel inputs timeout");end
endmodule
