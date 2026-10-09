`timescale 1ns/1ps
module tb_ddr_boot_gate;
    parameter integer HOLD=8;
    reg clk=0,rst=0,aux=0;
    wire memory_reset_n;
    always #10 clk=~clk;
    basic_pitch_ddr_boot_gate #(.HOLD_CYCLES(HOLD)) dut(.clk_i(clk),.rst_ni(rst),.aux_ready_i(aux),.memory_rst_no(memory_reset_n));
    task tick;begin @(posedge clk);#1;end endtask
    initial begin
        repeat(3)tick();rst=1;
        repeat(5)begin tick();if(memory_reset_n)$fatal(1,"released with no auxiliary locks");end
        // A brief early LOCK pulse must not open the DDR platform.
        aux=1;tick();aux=0;
        if(HOLD>2)repeat(HOLD+4)begin tick();if(memory_reset_n)$fatal(1,"released after short lock pulse");end
        else repeat(4)tick();
        rst=0;#1;if(memory_reset_n)$fatal(1,"global reset failed to assert asynchronously");tick();rst=1;aux=1;
        for(integer i=0;i<HOLD;i=i+1)begin tick();if(memory_reset_n)$fatal(1,"released earlier than minimum settling wait");end
        repeat(4)tick();if(!memory_reset_n)$fatal(1,"did not release after settling");
        aux=0;repeat(HOLD+4)begin tick();if(!memory_reset_n)$fatal(1,"aux loss incorrectly reset active DDR");end
        // Global reset must re-arm the initial sequence, including without a clock.
        @(negedge clk);#3;rst=0;#1;if(memory_reset_n)$fatal(1,"late global reset not immediate");
        repeat(3)tick();rst=1;aux=0;repeat(4)tick();if(memory_reset_n)$fatal(1,"reset failed to rearm gate");
        aux=1;repeat(HOLD+4)tick();if(!memory_reset_n)$fatal(1,"second startup failed");
        $display("PASS DDR boot gate HOLD=%0d",HOLD);$finish;
    end
endmodule
