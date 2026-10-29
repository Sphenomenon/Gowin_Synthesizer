`timescale 1ns/1ps

// Exercise the actual production defaults, in addition to the faster DCS
// composition/phase tests. Frequency windows here are a real nominal 1 ms.
module tb_workstation_audio_clock_monitor;
    reg clk=0,rst_n=0,reference48=0,reference44=0,run48=1,run44=1,restart48=0;
    always #10 clk=~clk;
    initial begin #3.7;forever begin #40.690104;if(run48)reference48=~reference48;end end
    initial begin #17.2;forever begin #29.525699;if(run44)reference44=~reference44;end end
    wire good48,good44,present48,present44,low48,low44;
    wire [31:0] edges48,edges44;
    workstation_audio_clock_monitor mon48 (
        .clk_i(clk),.rst_ni(rst_n),.source_clk_i(reference48),.restart_i(restart48),.expect_44k1_i(1'b0),
        .qualified_o(good48),.clock_present_o(present48),.stopped_low_o(low48),
        .window_valid_o(),.window_good_o(),.window_edges_o(edges48)
    );
    workstation_audio_clock_monitor mon44 (
        .clk_i(clk),.rst_ni(rst_n),.source_clk_i(reference44),.restart_i(1'b0),.expect_44k1_i(1'b1),
        .qualified_o(good44),.clock_present_o(present44),.stopped_low_o(low44),
        .window_valid_o(),.window_good_o(),.window_edges_o(edges44)
    );
    task tick;begin @(posedge clk);#1;end endtask
    task ticks(input integer n);begin repeat(n)tick();end endtask
    integer n;
    reg [31:0] frozen_count,measured48,measured44;
    initial begin
        ticks(5);rst_n=1;ticks(150010);
        if(good48 || good44)$fatal(1,"production qualified before fourth 1ms window");
        n=0;while(!(good48 && good44) && n<50100)begin tick();n=n+1;end
        if(!(good48 && good44) || n<49980 || edges48<12287 || edges48>12289 || edges44<16933 || edges44>16936)
            $fatal(1,"production 4ms frequency qualification: n=%0d edges=%0d/%0d",n,edges48,edges44);
        measured48=edges48;measured44=edges44;
        wait(reference48===1'b1);run48=0;
        wait(reference44===1'b0);run44=0;
        n=0;while((good48 || good44) && n<510)begin tick();n=n+1;end
        if(good48 || good44 || present48 || present44 || n<498 || n>504)
            $fatal(1,"production 10us loss bound n=%0d good=%b%b",n,good48,good44);
        if(low48 || !low44)$fatal(1,"production low-level stop proof");
        frozen_count=mon48.source_binary;
        restart48=1;tick();restart48=0;ticks(20);
        if(mon48.source_binary!=frozen_count || low48 || good48)
            $fatal(1,"restart touched independent source counter or reused high stop");
        $display("PASS production clock monitor: 50000-cycle windows, four consecutive windows, 12.288/16.9344 MHz counts=%0d/%0d, 500-cycle missing-clock bound=%0d, high/low stop and restart",measured48,measured44,n);
        $finish;
    end
    initial begin #5000000;$fatal(1,"production monitor watchdog");end
endmodule
