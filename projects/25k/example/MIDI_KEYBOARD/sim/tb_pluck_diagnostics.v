`timescale 1ns/1ps
module tb_pluck_diagnostics;
 parameter integer NOISE=0;
 localparam [7:0] OPCODE=NOISE ? 8'h06 : 8'h03;
 reg [7:0] current_opcode=OPCODE;
 reg clk=0;
 always #5 clk=!clk;
 reg reset=1,rx_valid=0,tx_ready=0;
 reg [7:0] rx_data=0;
 wire rx_ready,tx_valid,config_write;
 wire [7:0] tx_data;
 reg [511:0] diagnostics=0;
 reg diagnostics_valid=1;
 reg [31:0] reserved=0;
 reg corrupt_crc=0;
 reg [127:0] request,response;
 reg [31:0] result;
 integer byte_index,word_index;
 screen_control_endpoint #(.PLUCK_ENABLED(1),.PLUCK_NOISE_DIAGNOSTICS(1)) dut(
  .clk(clk),.reset(reset),.rx_valid(rx_valid),.rx_ready(rx_ready),.rx_data(rx_data),
  .tx_valid(tx_valid),.tx_ready(tx_ready),.tx_data(tx_data),.status_flags(32'd0),
  .touch_diagnostics(800'd0),.pluck_diagnostics(diagnostics),.pluck_noise_diagnostics(diagnostics),
  .pluck_diagnostics_valid(diagnostics_valid),.config_write(config_write));
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
 task query;
  input [31:0] word_number,expected_status;
  begin
   request={16'd0,reserved,word_number,16'h1234,current_opcode,8'h01,16'h4b4d};
   request[127:112]=crc(request[111:0])^corrupt_crc;
   for(byte_index=0;byte_index<16;byte_index=byte_index+1)begin
    @(negedge clk);rx_data=request[byte_index*8+:8];rx_valid=1;
    @(posedge clk);while(!rx_ready)@(posedge clk);
    @(negedge clk);rx_valid=0;
   end
   wait(tx_valid);
   repeat(5)begin @(negedge clk);if(!tx_valid || rx_ready)$fatal(1,"reply backpressure failed");end
   for(byte_index=0;byte_index<16;byte_index=byte_index+1)begin
    @(negedge clk);tx_ready=1;
    @(posedge clk);response[byte_index*8+:8]=tx_data;
    @(negedge clk);tx_ready=0;
   end
   if(response[127:112]!==crc(response[111:0]) || response[79:48]!==expected_status || response[31:24]!=(current_opcode|8'h80))
    $fatal(1,"bad diagnostic reply %h",response);
   result=response[111:80];
  end
 endtask
 always @(posedge clk)if(!reset && config_write)$fatal(1,"read-only diagnostics produced setting write");
 initial begin #100000;$fatal(1,"diagnostic test timeout");end
 initial begin
  diagnostics[31:0]=32'h314b4c50;diagnostics[63:32]=32'h12345678;
  diagnostics[511:480]=32'hfeedbeef;
  repeat(3)@(negedge clk);reset=0;
  query(1,0);if(result!==0)$fatal(1,"uninitialized snapshot escaped before first capture");
  query(15,0);if(result!==0)$fatal(1,"uninitialized last word escaped before first capture");
  fork
   begin diagnostics_valid=0;#2000;diagnostics_valid=1;end
   begin query(0,0);if(result!=32'h314b4c50)$fatal(1,"missing version signature");end
  join
  diagnostics[63:32]=32'hbad0bad0;
  query(1,0);if(result!=32'h12345678)$fatal(1,"snapshot torn across queries");
  current_opcode=NOISE ? 8'h03 : 8'h06;query(0,0);current_opcode=OPCODE;
  query(1,0);if(result!=32'h12345678)$fatal(1,"other diagnostic bank replaced locked snapshot");
  reserved=1;query(0,2);reserved=0;
  corrupt_crc=1;query(0,3);corrupt_crc=0;
  query(1,0);if(result!=32'h12345678)$fatal(1,"invalid request recaptured live diagnostics");
  query(15,0);if(result!=32'hfeedbeef)$fatal(1,"last word inaccessible");
  query(16,2);if(result!=0)$fatal(1,"invalid word returned data");
  query(1,0);if(result!=32'h12345678)$fatal(1,"invalid query replaced the snapshot");
  query(0,0);query(1,0);if(result!=32'hbad0bad0)$fatal(1,"new snapshot not captured");
  @(negedge clk);reset=1;repeat(3)@(negedge clk);reset=0;
  query(1,0);if(result!=0)$fatal(1,"session reset retained stale snapshot");
  diagnostics_valid=0;
  fork : canceled_capture
   begin query(0,0);$fatal(1,"canceled capture produced a reply");end
   begin
    repeat(70)@(negedge clk);
    if(tx_valid)$fatal(1,"invalid diagnostic window produced a reply");
    reset=1;repeat(3)@(negedge clk);reset=0;
   end
  join_any
  disable canceled_capture;
  diagnostics_valid=1;
  query(1,0);if(result!==0)$fatal(1,"reset during capture restored a stale snapshot");
  fork
   begin
    wait(dut.state==3 && dut.capture_index==8);
    @(negedge clk);diagnostics_valid=0;diagnostics[63:32]=32'h88776655;
    repeat(3)@(negedge clk);diagnostics_valid=1;
   end
   begin query(0,0);end
  join
  query(1,0);if(result!==32'h88776655)$fatal(1,"Interrupted RAM capture was not restarted atomically");
  for(word_index=1;word_index<16;word_index=word_index+1)
   diagnostics[word_index*32+:32]=32'h11223344^word_index;
  query(0,0);
  diagnostics=0;
  for(word_index=1;word_index<16;word_index=word_index+1)begin
   query(word_index,0);
   if(result!==(32'h11223344^word_index))$fatal(1,"snapshot word mapping failed at %0d",word_index);
  end
  $display("PASS tb_pluck_diagnostics read-only atomic snapshots, bounds, CRC, backpressure, all words and reset fencing");$finish;
 end
endmodule
