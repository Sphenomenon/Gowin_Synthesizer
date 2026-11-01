`timescale 1ns/1ps
module tb_pluck_emitters;
 reg clk=0;
 always #5 clk=!clk;
 reg reset=1,control_reset=0,online=1,guard_write=0;
 reg [7:0] guard_opcode=4;
 reg [31:0] guard_value=0;
 wire armed;
 midi_pluck_emitter_guard #(.LEASE_CYCLES(8)) guard(
  .clk(clk),.reset(reset),.control_reset(control_reset),.online(online),
  .config_write(guard_write),.config_opcode(guard_opcode),.config_value(guard_value),.armed(armed));
 reg rx_valid=0,tx_ready=0;
 reg [7:0] rx_data=0;
 wire [1:0] rx_ready,tx_valid,config_write;
 wire [7:0] enabled_data,disabled_data;
 wire [7:0] config_opcode;
 wire [31:0] config_value;
 integer write_count=0;
 screen_control_endpoint #(.PLUCK_ENABLED(1),.PLUCK_EMITTER_CONTROL(1),.PLUCK_VPP_CONTROL(1)) enabled_endpoint(
  .clk(clk),.reset(reset),.rx_valid(rx_valid),.rx_ready(rx_ready[0]),.rx_data(rx_data),
  .tx_valid(tx_valid[0]),.tx_ready(tx_ready),.tx_data(enabled_data),.status_flags(32'd0),
  .touch_diagnostics(800'd0),.pluck_diagnostics(512'd0),.pluck_diagnostics_valid(1'b1),
  .config_write(config_write[0]),.config_opcode(config_opcode),.config_value(config_value));
 screen_control_endpoint #(.PLUCK_ENABLED(1)) disabled_endpoint(
  .clk(clk),.reset(reset),.rx_valid(rx_valid),.rx_ready(rx_ready[1]),.rx_data(rx_data),
  .tx_valid(tx_valid[1]),.tx_ready(tx_ready),.tx_data(disabled_data),.status_flags(32'd0),
  .touch_diagnostics(800'd0),.pluck_diagnostics(512'd0),.pluck_diagnostics_valid(1'b1),.config_write(config_write[1]));
 always @(posedge clk)if(!reset)begin
  if(config_write[1])$fatal(1,"full keyboard admitted probe-only emitter control");
  if(config_write[0])begin
   if(config_opcode==4 && config_value>1)$fatal(1,"invalid emitter write escaped validation");
   if(config_opcode==5 && config_value[15:0]<=config_value[31:16])$fatal(1,"invalid Vpp thresholds escaped validation");
   if(config_opcode!=4 && config_opcode!=5)$fatal(1,"unexpected probe write");
   write_count=write_count+1;
  end
 end
 function [15:0] crc;
  input [111:0] payload;
  reg [15:0] work;
  integer byte_number,bit_number;
  begin
   work=16'hffff;
   for(byte_number=0;byte_number<14;byte_number=byte_number+1)begin
    work=work^{payload[byte_number*8+:8],8'd0};
    for(bit_number=0;bit_number<8;bit_number=bit_number+1)
     work=work[15] ? (work<<1)^16'h1021 : work<<1;
   end
   crc=work;
  end
 endfunction
 task command;
  input [7:0] opcode;
  input [31:0] value,reserved,expected_status;
  input corrupt;
  reg [127:0] request,enabled_reply,disabled_reply;
  integer byte_number;
  begin
   request={16'd0,reserved,value,16'h1234,opcode,8'h01,16'h4b4d};
   request[127:112]=crc(request[111:0])^corrupt;
   for(byte_number=0;byte_number<16;byte_number=byte_number+1)begin
    @(negedge clk);rx_data=request[byte_number*8+:8];rx_valid=1;
    @(posedge clk);if(rx_ready!=3)$fatal(1,"endpoints not jointly ready");
    @(negedge clk);rx_valid=0;
   end
   wait(tx_valid==3);
   for(byte_number=0;byte_number<16;byte_number=byte_number+1)begin
    @(negedge clk);tx_ready=1;
    @(posedge clk);enabled_reply[byte_number*8+:8]=enabled_data;disabled_reply[byte_number*8+:8]=disabled_data;
    @(negedge clk);tx_ready=0;
   end
   if(enabled_reply[127:112]!==crc(enabled_reply[111:0]) || enabled_reply[79:48]!==expected_status)
    $fatal(1,"probe emitter command status/CRC incorrect");
   if(expected_status==0 && enabled_reply[111:80]!==value)$fatal(1,"probe command did not echo accepted value");
   if(disabled_reply[79:48]!=(corrupt ? 3 : 1))$fatal(1,"full keyboard must reject emitter opcode");
  end
 endtask
 task renew;
  input [31:0] value;
  begin
   @(negedge clk);guard_write=1;guard_value=value;
   @(negedge clk);guard_write=0;
  end
 endtask
 initial begin #100000;$fatal(1,"emitter safety timeout");end
 initial begin
  repeat(3)@(negedge clk);reset=0;
  if(armed)$fatal(1,"emitters enabled at startup");
  renew(1);if(!armed)$fatal(1,"explicit arm failed");
  repeat(5)@(negedge clk);renew(1);
  repeat(7)@(negedge clk);if(!armed)$fatal(1,"renewed lease expired early");
  @(negedge clk);if(armed)$fatal(1,"abandoned host did not time out");
  renew(1);renew(0);if(armed)$fatal(1,"explicit disable failed");
  renew(1);control_reset=1;#1;if(armed)$fatal(1,"control reset did not immediately disable");
  @(negedge clk);control_reset=0;if(armed)$fatal(1,"control reset retained arm");
  renew(1);online=0;#1;if(armed)$fatal(1,"link loss did not immediately disable");
  @(negedge clk);online=1;if(armed)$fatal(1,"reconnect silently rearmed");
  renew(1);reset=1;@(negedge clk);reset=0;if(armed)$fatal(1,"reset retained arm");
  guard_opcode=8'h10;renew(1);if(armed)$fatal(1,"unrelated common parameter armed emitter");
  command(4,1,0,0,0);command(4,0,0,0,0);
  command(4,2,0,2,0);command(4,1,1,2,0);command(4,1,0,3,1);
  command(5,32'h00200040,0,0,0);command(5,1,0,0,0);command(5,32'hfffeffff,0,0,0);
  command(5,0,0,2,0);command(5,32'h00400040,0,2,0);command(5,32'h00410040,0,2,0);
  command(5,32'h00200040,1,2,0);command(5,32'h00200040,0,3,1);
  command(6,0,0,1,0);
  if(write_count!=5)$fatal(1,"rejected requests caused probe state changes");
  $display("PASS tb_pluck_emitters default OFF, lease/renewal/expiry, reset/link fail-close, diagnostic-only opcode and validation");$finish;
 end
endmodule
