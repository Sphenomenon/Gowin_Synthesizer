`timescale 1ns/1ps
module tb_push_decimal;
  reg clk=0,rst=1;
  always #5 clk=~clk;
  reg [15:0] value=0;
  wire [19:0] digits;
  push2_decimal16 dut(.clk(clk),.rst(rst),.value_i(value),.digits_o(digits));
  function automatic [19:0] oracle(input integer number);
    oracle={4'((number/10000)%10),4'((number/1000)%10),4'((number/100)%10),4'((number/10)%10),4'(number%10)};
  endfunction
  integer i,j;
  initial begin
    repeat(4)@(negedge clk);rst=0;
    for(i=0;i<65536;i=i+1)begin
      @(negedge clk);value=i[15:0];repeat(17)@(negedge clk);
      if(digits!==oracle(i))$fatal(1,"decimal value=%0d got=%h expected=%h",i,digits,oracle(i));
    end
    for(i=0;i<100;i=i+1)begin
      for(j=0;j<37;j=j+1)begin @(negedge clk);value=$random;end
      repeat(34)@(negedge clk);
      if(digits!==oracle(value))$fatal(1,"changing-input conversion did not settle");
    end
    @(negedge clk);rst=1;@(negedge clk);
    if(digits!==0)$fatal(1,"decimal reset");
    $display("PASS push_decimal: all 65536 inputs, 100 update bursts, 34-cycle convergence and reset");
    $finish;
  end
  initial begin #30000000;$fatal(1,"decimal timeout");end
endmodule
