`timescale 1ns/1ps
module tb_ddr_recovery_guard;
    reg clk=0,reset_n=0,pll_locked=0,calibrated=0;
    always #10 clk=~clk;
    wire controller_reset_n,lock_stable;
    ddr_recovery_guard #(.RESET_CYCLES(8)) dut(.*);
    integer cycles;
    task tick; begin @(posedge clk);#1;end endtask
    task expect_reset_width;
        begin
            cycles=0;
            while(!controller_reset_n) begin
                tick();cycles=cycles+1;
                if(cycles>8) $fatal(1,"controller reset failed to release");
            end
            if(cycles!=8) $fatal(1,"controller reset width %0d cycles, expected 8",cycles);
        end
    endtask
    initial begin
        #1;reset_n=1;#1;reset_n=0;
        repeat(3) tick();
        @(negedge clk);reset_n=1;
        expect_reset_width();
        // PLL search before first calibration is allowed to acquire/lose lock.
        repeat(3) begin
            @(negedge clk);pll_locked=1;repeat(4) tick();
            @(negedge clk);pll_locked=0;repeat(3) tick();
            if(!controller_reset_n) $fatal(1,"unarmed PLL search caused reset loop");
        end
        @(negedge clk);pll_locked=1;calibrated=1;
        repeat(7) tick();
        if(!lock_stable || !controller_reset_n) $fatal(1,"initial calibration did not arm");
        // Both edges occur between clock edges: the loss must not be missed.
        @(negedge clk);#2;pll_locked=0;#1;
        if(lock_stable) $fatal(1,"short lock loss did not close the UI gate");
        #1;pll_locked=1;
        tick();
        if(controller_reset_n) $fatal(1,"short lock loss did not restart PHY");
        calibrated=0;
        expect_reset_width();
        repeat(5) tick();
        if(!controller_reset_n) $fatal(1,"waiting for new calibration caused reset loop");
        @(negedge clk);calibrated=1;repeat(5) tick();
        @(negedge clk);pll_locked=0;
        tick();
        if(controller_reset_n) $fatal(1,"second, sustained lock loss was not detected");
        calibrated=0;
        expect_reset_width();
        repeat(4) tick();
        if(lock_stable) $fatal(1,"missing PLL lock was reported stable");
        @(negedge clk);reset_n=0;#1;
        if(controller_reset_n) $fatal(1,"external reset did not assert asynchronously");
        @(negedge clk);reset_n=1;pll_locked=1;
        expect_reset_width();
        // Calibration is fresh and has not yet traversed its synchronizer.
        @(negedge clk);calibrated=1;#2;pll_locked=0;#2;pll_locked=1;
        tick();
        if(controller_reset_n) $fatal(1,"calibration/lock-loss boundary was missed");
        calibrated=0;expect_reset_width();
        $display("PASS DDR recovery guard: initial search, sub-cycle lock loss, complete reset width, rearm, sustained loss and external reset");
        $finish;
    end
    initial begin #10000;$fatal(1,"recovery test timeout");end
endmodule
