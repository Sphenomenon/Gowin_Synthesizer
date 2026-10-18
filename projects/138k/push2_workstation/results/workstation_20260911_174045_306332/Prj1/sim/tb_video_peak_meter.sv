`timescale 1ns/1ps
module tb_video_peak_meter;
    reg clk=0;
    always #20 clk=~clk;
    reg reset_n=0, valid=0, frame_start=0;
    reg [31:0] sample_data=0;
    wire [31:0] level;
    video_peak_meter dut(clk,reset_n,sample_data,valid,frame_start,level);
    task cycle(input [31:0] value,input v,input f);
        begin
            @(negedge clk); sample_data=value; valid=v; frame_start=f;
            @(posedge clk); #1;
        end
    endtask
    integer i;
    reg [31:0] previous;
    initial begin
        repeat(3) @(negedge clk); reset_n=1;
        cycle(32'hc0000000,1,0);
        cycle(0,0,1);
        if (level!==32'h40000000) $fatal(1,"negative sample magnitude wrong");
        cycle(32'h80000000,1,1);
        if (level!==32'h80000000) $fatal(1,"minimum Q1.31 or frame-boundary sample lost");
        previous=level;
        for(i=0;i<400;i=i+1) begin
            cycle(0,0,1);
            if(level>previous) $fatal(1,"peak decay wrapped/increased");
            previous=level;
        end
        if(level!==0) $fatal(1,"peak decay did not reach exact silence");
        $display("PASS tb_video_peak_meter: signed magnitude, simultaneous frame/sample, monotonic decay");
        $finish;
    end
endmodule
