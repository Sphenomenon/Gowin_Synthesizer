`timescale 1ns/1ps
// Exercise the wrapper contract around the unmodified vendor source. FAT/SPI
// itself is covered by the existing TF suite; here inject sector byte outputs.
module tb_sampler_tf_source;
  logic clk=0;always #5 clk=~clk;logic rst_n=0,enable=0,restart=0,ready=0;
  wire cs,sck,mosi;wire valid,last,overflow,file_found;wire [7:0] data;
  wire [1:0] card,fs;wire [3:0] card_status;wire [2:0] fs_status;wire [31:0] size;
  logic inject_valid=0;logic [7:0] inject_byte=0;
  sampler_tf_source #(.FIFO_BITS(3)) dut(.clk(clk),.rst_n(rst_n),.enable(enable),.restart(restart),.sd_miso(1'b1),
    .sd_cs_n(cs),.sd_sck(sck),.sd_mosi(mosi),.valid(valid),.ready(ready),.data(data),.last(last),.overflow(overflow),
    .card_type(card),.filesystem_type(fs),.card_status(card_status),.filesystem_status(fs_status),.file_found(file_found),.file_size(size));
  initial begin
    force dut.raw_valid=inject_valid;force dut.raw_byte=inject_byte;force dut.file_size=32'd8;
    repeat(3) @(negedge clk);rst_n=1;enable=1;
    for(int i=0;i<8;i++) begin inject_valid=1;inject_byte=8'(i+40);@(negedge clk);end
    inject_valid=0;ready=1;
    for(int i=0;i<8;i++) begin
      #1;if(!valid || data!=i+40 || last!=(i==7)) $fatal(1,"TF byte FIFO data/EOF %d",i);
      @(negedge clk);
    end
    if(valid || overflow) $fatal(1,"FIFO consumption");ready=0;
    for(int i=0;i<9;i++) begin inject_valid=1;inject_byte=8'(i);@(negedge clk);end
    inject_valid=0;#1;if(!overflow || valid) $fatal(1,"overflow fail-explicit");
    restart=1;@(negedge clk);restart=0;#1;if(valid || overflow || dut.byte_count!=0) $fatal(1,"restart FIFO epoch");
    release dut.raw_valid;release dut.raw_byte;release dut.file_size;
    $display("METRIC tf_fifo_test_bytes=8 overflow_refusals=1 restart_stale_bytes=0");
    $display("PASS tb_sampler_tf_source");$finish;
  end
endmodule
