`timescale 1ns/1ps
module tb_gw138k_encoder_detents;
 reg clk=0;always #10 clk=~clk;
 reg reset=1;reg[1:0]ab=3;
 wire pulse;wire signed[1:0]direction;wire signed[15:0]position;
 wire[15:0]invalid;integer count=0;
 encoder_input #(.DETENTS_PER_STEP(1),.AB_FILTER_CYCLES(4),.KEY_FILTER_CYCLES(4)) dut(
  .clk(clk),.reset(reset),.a(ab[1]),.b(ab[0]),.key_n(1'b1),.position(position),
  .press_count(),.invalid_count(invalid),.ab_state(),.key_pressed(),.direction(direction),.step_pulse(pulse),.press_pulse());
 always @(posedge clk)if(!reset && pulse)count=count+1;
 task move(input[1:0]value);begin @(negedge clk);ab=value;repeat(14)@(negedge clk);end endtask
 initial begin
  repeat(5)@(negedge clk);reset=0;move(3);
  move(2);move(0);if(count!=1 || position!=1 || direction!=1)$fatal(1,"first detent");
  move(1);move(3);if(count!=2 || position!=2)$fatal(1,"second detent");
  move(1);move(0);if(count!=3 || position!=1 || direction!=-1)$fatal(1,"reverse detent");
  move(2);move(3);if(count!=4 || position!=0)$fatal(1,"reverse second");
  move(2);move(3);if(count!=4 || position!=0)$fatal(1,"contact reversal must cancel");
  move(0);if(count!=4 || invalid!=1)$fatal(1,"invalid phase generated step");
  move(1);move(3);if(count!=5 || position!=1)$fatal(1,"recovery detent");
  $display("PASS tb_gw138k_encoder_detents: one step per physical detent, reversal, bounce, invalid phase");$finish;
 end
endmodule
