`timescale 1ns/1ps
module tb_workstation_xy_panic;
 reg source_clk=0,memory_clk=0,run_memory=1,reset_n=0,valid=0,trust=1;
 reg [9:0] epoch=0;
 always #10 source_clk=~source_clk;
 always #5 if(run_memory)memory_clk=~memory_clk;
 wire marked; wire [31:0] drops,destination_drops,destination_gray;
 wire destination_valid;wire [203:0] destination_data;
 workstation_xy_panic_observation dut(.clk_i(source_clk),.reset_ni(reset_n),.sample_valid_i(valid),.trusted_i(trust),.panic_epoch_i(epoch),.trusted_o(marked));
 gw138k_stream_cdc #(.WIDTH(204)) observation(.reset_n(reset_n),.source_clk(source_clk),.destination_clk(memory_clk),.source_valid(valid),.source_data({marked,203'd0}),.drop_count(drops),.destination_valid(destination_valid),.destination_data(destination_data));
 gw138k_counter_cdc counter(.reset_n(reset_n),.source_clk(source_clk),.destination_clk(memory_clk),.source_count(drops),.destination_count(destination_drops),.destination_gray(destination_gray));
 integer revoked=0,received=0,checks=0;reg [31:0] old_gray=0;
 always @(posedge memory_clk) if(reset_n)begin
   if(destination_valid)begin received=received+1;if(!destination_data[203])revoked=revoked+1;end
   if(destination_gray!=old_gray)revoked=revoked+1;
   old_gray=destination_gray;
 end
 task check(input bit condition,input [255:0] why);begin checks=checks+1;if(!condition)$fatal(1,"XY panic contract %s",why);end endtask
 task send(input [9:0] next_epoch,input bit expected_trust);
 begin @(negedge source_clk);epoch=next_epoch;valid=1;#1;check(marked===expected_trust,"mark on actual sample");@(negedge source_clk);valid=0;#1;check(marked===trust,"no unsampled revoke");end endtask
 integer i,before_revoke;reg [31:0] before_drop;
 initial begin
  #81;reset_n=1;repeat(20)@(negedge source_clk);
  epoch=10'd17;#1;check(marked===1,"unsampled parameter");
  before_revoke=revoked;send(17,0);repeat(20)@(negedge source_clk);check(revoked>before_revoke,"accepted tuple revoke");
  before_revoke=revoked;send(17,1);repeat(20)@(negedge source_clk);check(revoked==before_revoke,"held epoch no re-trigger");
  send(0,0);repeat(20)@(negedge source_clk);
  for(i=0;i<10;i=i+1)begin before_revoke=revoked;send(10'b1<<i,0);repeat(20)@(negedge source_clk);check(revoked>before_revoke,"all epoch bits");send(0,0);repeat(20)@(negedge source_clk);end
  send(1023,0);repeat(20)@(negedge source_clk);send(0,0);repeat(20)@(negedge source_clk);
  // Stop the consumer with an ordinary word held, then lose a PANIC-marked
  // physical sample. Revoke must arrive through the actual drop-counter CDC.
  @(negedge memory_clk);run_memory=0;send(0,1);before_drop=drops;before_revoke=revoked;send(1,0);check(drops==before_drop+1,"busy mailbox counts panic loss");
  repeat(20)@(negedge source_clk);run_memory=1;repeat(30)@(negedge source_clk);check(destination_drops==drops,"drop count delivered");check(revoked>before_revoke,"dropped tuple reliable revoke");
  trust=0;send(1,0);repeat(20)@(negedge source_clk);trust=1;
  #1;reset_n=0;#41;epoch=0;reset_n=1;repeat(20)@(negedge source_clk);send(0,1);repeat(20)@(negedge source_clk);
  $display("PASS XY panic checks=%0d received=%0d accepted_and_dropped_revoke=1 wrap=1 no_extra_mailbox=1",checks,received);$finish;
 end
 initial begin #100000;$fatal(1,"timeout");end
endmodule
