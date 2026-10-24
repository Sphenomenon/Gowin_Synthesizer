`timescale 1ns/1ps
// Digital ADC handshake model. This does not simulate ADC analog accuracy.
module vccio5_adc(output reg adcrdy=1,output reg [13:0] adcvalue=14'd999,
    input drstn,adcreqi,input [9:0] fscal_value,input [11:0] offset_value);
    reg hang=0;
    integer conversions=0;
    always @(posedge adcreqi) if(!hang) begin
        if(fscal_value!=653 || offset_value!=0) $fatal(1,"ADC calibration parameters");
        adcrdy=0;
        #100;adcvalue=14'd840+(conversions%5);
        #20;adcrdy=1;conversions=conversions+1;
    end
endmodule
module tb_vccio5_monitor;
    reg clk=0,rst_n=0;
    always #5 clk=~clk;
    wire [13:0] last,minimum,maximum;
    wire [31:0] count,timeouts,age,duration;
    wire [7:0] flags;
    reg [31:0] before_count;
    vccio5_monitor #(.CLK_HZ(100000)) dut (.*);
    initial begin
        #20;rst_n=1;
        repeat(7000) @(negedge clk);
        if(count<5 || minimum!=840 || maximum!=844 || timeouts!=0) $fatal(1,"ADC normal conversions/min/max");
        if(last<840 || last>844 || !flags[0]) $fatal(1,"ADC result validity");
        wait(dut.state==0);@(negedge clk);
        dut.adc.hang=1;before_count=count;
        repeat(8000) @(negedge clk);
        if(timeouts==0 || count!=before_count || !flags[2]) $fatal(1,"Stale ready must time out, not count");
        rst_n=0;#20;
        if(count || timeouts || flags[0]) $fatal(1,"ADC monitor reset");
        $display("PASS ADC conversion handshake, stale-ready rejection, timeout and reset");$finish;
    end
endmodule
