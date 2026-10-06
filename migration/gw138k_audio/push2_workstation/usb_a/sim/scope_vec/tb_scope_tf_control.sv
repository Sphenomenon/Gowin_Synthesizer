`timescale 1ns/1ps
module tb_scope_tf_control;
 reg clk=0,rst_n=0,valid=0,live=0,idle=1;
 reg [6:0] cc=0,value=0;
 wire [31:0] word;
 always #5 clk=~clk;
 scope_tf_control dut(.clk_i(clk),.rst_ni(rst_n),.event_valid_i(valid),.cc_i(cc),.value_i(value),
    .live_enable_i(live),.voices_idle_i(idle),.control_o(word));
 task send(input [6:0] c,v);
  @(negedge clk);cc=c;value=v;valid=1;@(negedge clk);valid=0;
 endtask
 initial begin
  repeat(4) @(negedge clk);rst_n=1;
  idle=0;send(104,127);if(word[12] || !word[15]) $fatal(1,"busy mode switch must fail explicitly");
  idle=1;send(104,64);if(!word[14] || !word[12] || !word[13] || word[31:16]!=1) $fatal(1,"enter/play");
  send(105,64);if(word[13] || word[31:16]!=1) $fatal(1,"pause must retain cursor");
  send(105,64);if(!word[13] || word[31:16]!=1) $fatal(1,"resume must retain cursor");
  send(105,127);if(word[31:16]!=2 || word[7:6]!=3) $fatal(1,"restart epoch");
  send(106,15);if(word[11:8]!=15 || word[31:16]!=3) $fatal(1,"track select");
  send(106,16);if(word[11:8]!=15 || word[31:16]!=3) $fatal(1,"track overflow truncated");
  send(108,127);if(word[7:6]!=1 || word[31:16]!=4) $fatal(1,"directory-aware next command");
  send(108,0);if(word[7:6]!=2 || word[31:16]!=5) $fatal(1,"directory-aware previous command");
  send(120,0);if(word[13] || !word[12]) $fatal(1,"panic must silence selected TF source");
  send(104,64);if(word[12] || word[13] || !word[14]) $fatal(1,"exit must not autoplay TF again");
  send(106,0);send(104,127);send(108,0);if(word[11:8]!=0) $fatal(1,"previous underflow");
  send(90,127);if(word[12] || word[13]) $fatal(1,"live geometry takeover");
  $display("M tf_control_assertions 13");$display("PASS scope_tf_control");$finish;
 end
 initial begin #100000;$fatal(1,"timeout");end
endmodule
