`timescale 1ns/1ps
module tb_usb1_clock;
    reg clk_50mhz = 1'b0;
    always #10 clk_50mhz = ~clk_50mhz;
    wire clk_usb60, pll_locked, reset_60mhz_n;
    usb1_clock_60m dut (
        .clk_50mhz(clk_50mhz), .clk_usb60(clk_usb60),
        .pll_locked(pll_locked), .reset_60mhz_n(reset_60mhz_n)
    );

    realtime t_start, t_period, t_high, t_edge;
    integer i;
    task check_release;
        integer edge_number;
        begin
            @(posedge pll_locked);
            if (reset_60mhz_n !== 1'b0)
                $fatal(1, "reset released at LOCK, before three clock edges");
            for (edge_number = 1; edge_number <= 3; edge_number = edge_number + 1) begin
                @(posedge clk_usb60);
                #0.001;
                if (edge_number < 3 && reset_60mhz_n !== 1'b0)
                    $fatal(1, "reset released too early");
                if (edge_number == 3 && reset_60mhz_n !== 1'b1)
                    $fatal(1, "reset did not release on third 60 MHz edge");
            end
        end
    endtask

    initial begin
        #1;
        if (reset_60mhz_n !== 1'b0) $fatal(1, "reset not asserted at power-up");
        check_release;
        $display("PASS power-up calibration and 3-edge reset release at %0.3f ns", $realtime);
        @(posedge clk_usb60);
        t_start = $realtime;
        repeat (600) @(posedge clk_usb60);
        t_period = ($realtime - t_start) / 600.0;
        if (t_period < 16.665 || t_period > 16.668)
            $fatal(1, "clock period is %0.6f ns", t_period);
        @(posedge clk_usb60);
        t_edge = $realtime;
        @(negedge clk_usb60);
        t_high = $realtime - t_edge;
        if (t_high < 8.332 || t_high > 8.335)
            $fatal(1, "high pulse is %0.6f ns", t_high);
        $display("PASS frequency %0.6f MHz, period %0.6f ns, high pulse %0.6f ns", 1000.0/t_period, t_period, t_high);

        // Force a raw LOCK failure between edges to test the reset path itself.
        @(negedge clk_usb60);
        #1;
        force dut.pll_lock_raw = 1'b0;
        #0.001;
        if (reset_60mhz_n !== 1'b0)
            $fatal(1, "LOCK loss did not assert reset asynchronously");
        #1000;
        release dut.pll_lock_raw;
        check_release;
        $display("PASS asynchronous LOCK-loss reset and synchronized relock release");
        $display("PASS usb1_clock_60m (official GW5A PLLA model, full PLL_INIT timing)");
        $finish;
    end

    initial begin
        #10000000;
        $fatal(1, "timed out waiting for calibrated PLL LOCK");
    end
endmodule
