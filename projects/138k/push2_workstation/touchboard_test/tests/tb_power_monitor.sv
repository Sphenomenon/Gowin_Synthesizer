`timescale 1ns/1ps
module test_power_monitor;
    reg clk=0,rst=0;
    always #5 clk=~clk;
    wire [13:0] last,minimum,maximum;
    wire [31:0] count,timeouts,age,duration;
    wire [7:0] flags;
    tb_power_monitor #(.CLK_HZ(1000000)) dut(.clk(clk),.rst_n(rst),.last(last),.minimum(minimum),.maximum(maximum),
      .count(count),.timeouts(timeouts),.age(age),.duration(duration),.flags(flags));
    initial begin
      #100;rst=1;
      wait(count==3);
      @(negedge clk);
      if(minimum!=820 || maximum!=870 || last!=870 || timeouts!=0 || duration<190 || duration>220 || !flags[0]) $fatal(1,"conversion extrema/timing");
      dut.adc.stuck=1;
      wait(timeouts==1);
      @(negedge clk);
      if(count!=3 || !flags[2]) $fatal(1,"stale ready-high accepted as a new conversion");
      dut.adc.stuck=0;
      wait(count==4);
      @(negedge clk);
      if(last!=820 || age>4) $fatal(1,"timeout recovery");
      $display("PASS power monitor: ready-low/high guard, synchronized value, extrema, age, timeout, recovery");
      $finish;
    end
    initial begin #3000000;$fatal(1,"timeout count=%d error=%d",count,timeouts);end
endmodule
