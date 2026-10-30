`timescale 1ns/1ps

// Independent oracle uses behavioral unsigned division. It does not duplicate
// the radix-4 restoring implementation. Fixed latency is the helper contract.
module div147_checker #(parameter integer WIDTH=42, TAG_WIDTH=16)(output reg done_o=0);
  localparam integer PREFIX=6+(WIDTH%2);
  localparam integer STAGES=(WIDTH-PREFIX)/2;
  reg clk=0;
  always #5 clk=~clk;
  reg rst_n=0, flush=0, valid=0;
  reg [WIDTH-1:0] dividend=0;
  reg [TAG_WIDTH-1:0] tag=0;
  wire out_valid, quiet;
  wire [WIDTH-1:0] quotient;
  wire [TAG_WIDTH-1:0] out_tag;
  workstation_runtime_div147 #(.WIDTH(WIDTH),.TAG_WIDTH(TAG_WIDTH)) dut(
    .clk_i(clk),.rst_ni(rst_n),.flush_i(flush),.valid_i(valid),
    .dividend_i(dividend),.tag_i(tag),.valid_o(out_valid),
    .quotient_o(quotient),.tag_o(out_tag),.quiescent_o(quiet));

  reg [STAGES:0] expected_valid=0;
  reg [WIDTH-1:0] expected_quotient[0:STAGES];
  reg [TAG_WIDTH-1:0] expected_tag[0:STAGES];
  reg [63:0] random_state=64'hfc20261030000000+WIDTH;
  reg [63:0] rv;
  integer cycle=0, issued=0, checked=0, flushes=0, k, n, b;
  reg [WIDTH-1:0] x;

  always @(posedge clk) begin
    cycle=cycle+1;
    if (!rst_n || flush) begin
      expected_valid='0;
      if (flush && rst_n) flushes=flushes+1;
    end else begin
      for (k=STAGES;k>0;k=k-1) begin
        expected_valid[k]=expected_valid[k-1];
        expected_quotient[k]=expected_quotient[k-1];
        expected_tag[k]=expected_tag[k-1];
      end
      expected_valid[0]=valid;
      expected_quotient[0]=dividend / 147;
      expected_tag[0]=tag;
      if(valid) issued=issued+1;
    end
    #1;
    if(out_valid !== expected_valid[STAGES])
      $fatal(1,"DIV147_LATENCY width=%0d cycle=%0d valid=%b expected=%b",WIDTH,cycle,out_valid,expected_valid[STAGES]);
    if(quiet !== !(|expected_valid))
      $fatal(1,"DIV147_QUIESCENT width=%0d cycle=%0d quiet=%b pipe=%b",WIDTH,cycle,quiet,expected_valid);
    if(out_valid) begin
      if(quotient !== expected_quotient[STAGES])
        $fatal(1,"DIV147_NUMERIC width=%0d cycle=%0d quotient=%h expected=%h",WIDTH,cycle,quotient,expected_quotient[STAGES]);
      if(out_tag !== expected_tag[STAGES])
        $fatal(1,"DIV147_TAG width=%0d cycle=%0d tag=%h expected=%h",WIDTH,cycle,out_tag,expected_tag[STAGES]);
      checked=checked+1;
    end
  end

  task drive(input [WIDTH-1:0] value,input bit is_valid,input bit do_flush,input [TAG_WIDTH-1:0] input_tag);
    begin
      @(negedge clk);
      dividend=value;valid=is_valid;flush=do_flush;tag=input_tag;
    end
  endtask

  function [63:0] next_random(input [63:0] old);
    reg[63:0] t;
    begin
      t=old^(old<<13);t=t^(t>>7);t=t^(t<<17);
      next_random=t;
    end
  endfunction

  initial begin
    repeat(3) @(negedge clk);
    rst_n=1;
    drive(0,1,0,16'h0000);
    drive(1,1,0,16'h0001);
    drive(146,1,0,16'h0002);
    drive(147,1,0,16'h0003);
    drive(148,1,0,16'h0004);
    drive({WIDTH{1'b1}},1,0,16'h0005);
    drive({WIDTH{1'b1}}-1'b1,1,0,16'h0006);
    for(b=0;b<WIDTH;b=b+1) begin
      x={{(WIDTH-1){1'b0}},1'b1}<<b;
      drive(x-1'b1,1,0,b*3+16'h0100);
      drive(x,1,0,b*3+16'h0101);
      drive(x+1'b1,1,0,b*3+16'h0102);
    end
    // Adjacent divisibility boundaries across the full unsigned range.
    for(n=0;n<1000;n=n+1) begin
      random_state=next_random(random_state);
      x=random_state[WIDTH-1:0];
      x=(x/147)*147;
      drive(x,1,0,n+16'h1000);
      drive(x-1'b1,1,0,n+16'h2000);
      drive(x+1'b1,1,0,n+16'h3000);
    end
    // Variable valid gaps, in-flight flush with new input high, immediate
    // post-flush tag reuse, then common-reset recovery while busy.
    for(n=0;n<5000;n=n+1) begin
      random_state=next_random(random_state);
      drive(random_state[WIDTH-1:0], (n%7)!=2 && (n%11)!=3,
            (n%197)==37 || (n%197)==38, n[15:0]^16'ha5a5);
      if(n==1200) begin
        @(negedge clk);rst_n=0;valid=1;flush=0;
        repeat(2) @(negedge clk);
        rst_n=1;
      end
    end
    drive(0,0,0,0);
    repeat(STAGES+4) @(negedge clk);
    if(checked<5000 || flushes<20 || !quiet)
      $fatal(1,"DIV147_COVERAGE width=%0d checked=%0d flushes=%0d quiet=%b",WIDTH,checked,flushes,quiet);
    $display("DIV147_INDEPENDENT_PASS width=%0d stages=%0d issued=%0d checked=%0d flushes=%0d",WIDTH,STAGES,issued,checked,flushes);
    done_o=1;
  end
endmodule

module tb_runtime_div147_independent;
  wire done42,done32,done43,done25;
  div147_checker #(.WIDTH(42)) c42(done42);
  div147_checker #(.WIDTH(32)) c32(done32);
  div147_checker #(.WIDTH(43)) c43(done43);
  div147_checker #(.WIDTH(25)) c25(done25);
  initial begin
    wait(done42&&done32&&done43&&done25);
    $display("RUNTIME_DIV147_INDEPENDENT_PASS");
    $finish;
  end
  initial begin #2000000; $fatal(1,"DIV147_TIMEOUT"); end
endmodule
