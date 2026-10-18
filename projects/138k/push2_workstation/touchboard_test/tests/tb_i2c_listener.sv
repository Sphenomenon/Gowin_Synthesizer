`timescale 1ns/1ps
module test_i2c_listener;
    reg clk=0,rst=0,scl=1,sda=1;
    always #10 clk=~clk;
    wire [519:0] rise,late;
    wire [64:0] nacks;
    wire [6:0] count;
    wire stop,overflow,disagree;
    wire [31:0] gap;
    tb_i2c_listener dut(.clk(clk),.rst_n(rst),.scl(scl),.sda(sda),
      .bytes_rise(rise),.bytes_late(late),.nack_bits(nacks),.byte_count(count),
      .stopped(stop),.overflow(overflow),.disagreement(disagree),.start_gap(gap));
    task start_bus;
      begin scl=1; sda=1; #2000; sda=0; #2000; scl=0; #2000; end
    endtask
    task put_bit(input reg b);
      begin sda=b; #1000; scl=1; #2000; scl=0; #1000; end
    endtask
    task put_byte(input reg [7:0] b,input reg nack);
      integer j;
      begin for(j=7;j>=0;j=j-1) put_bit(b[j]); put_bit(nack); end
    endtask
    task stop_bus;
      begin sda=0; #1000; scl=1; #2000; sda=1; #2000; end
    endtask
    integer i;
    reg [7:0] expected;
    initial begin
      #200; rst=1; #1000;
      start_bus;
      for(i=0;i<65;i=i+1) put_byte((i*37)^8'ha5,i==64);
      stop_bus;
      if(!stop || count!=65 || overflow || disagree) $fatal(1,"65-byte frame count/flags: %d %b %b %b",count,stop,overflow,disagree);
      for(i=0;i<65;i=i+1) begin
        expected=(i*37)^8'ha5;
        if(rise[i*8 +: 8]!==expected || late[i*8 +: 8]!==expected || nacks[i]!=(i==64)) $fatal(1,"byte %d rise=%x late=%x expected=%x",i,rise[i*8 +: 8],late[i*8 +: 8],expected);
      end
      #200000;
      start_bus; put_byte(8'h1a,0); put_byte(8'h64,0); stop_bus;
      if(count!=2 || rise[15:0]!=16'h641a || late[15:0]!=16'h641a || nacks!=0 || gap<10000) $fatal(1,"pointer transaction/gap");
      start_bus;
      for(i=0;i<66;i=i+1) put_byte(i,0);
      stop_bus;
      if(!overflow || count!=65 || !stop) $fatal(1,"overflow guard");
      $display("PASS passive listener: independent manual bitstream, 65 bytes, ACK/NACK, start/stop, short pointer, gap, overflow");
      $finish;
    end
endmodule
