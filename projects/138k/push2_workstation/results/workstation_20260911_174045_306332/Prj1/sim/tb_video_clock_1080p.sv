`timescale 1ns/1fs
module tb_video_clock_1080p;
    reg reference_clk = 0;
    always #10 reference_clk = ~reference_clk;
    reg reset_n = 0;
    wire pixel_clk, serial_clk, pixel_reset_n, source_reset_n, locked, serializer_reset_n;
    video_clock_1080p #(.SIMULATION(1)) dut (
        .clk_50m(reference_clk), .reset_n(reset_n), .pixel_clk(pixel_clk),
        .serial_clk(serial_clk), .pixel_reset_n(pixel_reset_n),
        .serializer_reset_n(serializer_reset_n),
        .video_source_reset_n(source_reset_n), .pll_locked(locked)
    );
    reg raw_lock = 0;
    wire stable_lock;
    video_pll_lock_filter #(.STABLE_CYCLES(4)) u_filter (
        .clk(reference_clk), .reset_n(reset_n), .raw_lock(raw_lock),
        .stable_lock(stable_lock)
    );
    realtime t0, period;
    realtime serializer_release_time;
    reg startup_lock=0;
    wire startup_reset_n,startup_enable;
    video_serializer_startup u_startup (
        .clk(reference_clk),.reset_n(reset_n),.qualified_lock(startup_lock),
        .serializer_reset_n(startup_reset_n),.clock_enable(startup_enable)
    );
    always @(posedge serializer_reset_n) serializer_release_time=$realtime;
    always @(posedge serial_clk) begin
        if(!serializer_reset_n || ($realtime-serializer_release_time)<79.999)
            $fatal(1,"serializer clock started before 80ns reset settling window");
    end
    integer serial_edges, pixel_edges;
    initial begin
        #21; reset_n=1;
        // Exercise the actual hardware qualification/reset module independently
        // of the ideal PLL model, including a sub-cycle loss-of-lock pulse.
        @(negedge reference_clk); raw_lock=1;
        repeat (5) @(negedge reference_clk);
        if (stable_lock) $fatal(1,"PLL qualifier released before synchronization plus 4 cycles");
        repeat (2) @(negedge reference_clk);
        if (!stable_lock) $fatal(1,"PLL qualifier never released");
        #1; raw_lock=0; #1;
        if (stable_lock) $fatal(1,"PLL lock loss was not asynchronous");
        raw_lock=1;
        repeat (5) @(negedge reference_clk);
        if (stable_lock) $fatal(1,"PLL qualifier did not restart after glitch");

        // Exercise the actual hardware stop-clock/reset/start-clock sequencer.
        startup_lock=1;
        @(posedge reference_clk); #0.01;
        if(!startup_reset_n || startup_enable) $fatal(1,"serializer reset startup phase");
        repeat(3) begin @(posedge reference_clk); #0.01;
            if(startup_enable) $fatal(1,"clock enabled before four reset settling cycles");
        end
        @(posedge reference_clk); #0.01;
        if(!startup_enable) $fatal(1,"clock enable never asserted");
        #1; startup_lock=0; #0.01;
        if(startup_enable || startup_reset_n) $fatal(1,"lock-loss restart was not asynchronous");
        #1; startup_lock=1;
        repeat(4) begin @(posedge reference_clk); #0.01;
            if(startup_enable) $fatal(1,"restart skipped reset settling window");
        end
        @(posedge reference_clk); #0.01;
        if(!startup_enable) $fatal(1,"clock restart never completed");
        if(pixel_clk || serial_clk || pixel_reset_n || source_reset_n || locked)
            $fatal(1,"model released clocks before PLL qualification");
        wait(serializer_reset_n);
        #60;
        if(pixel_clk || serial_clk || locked) $fatal(1,"model did not keep clocks stopped during reset release");
        @(posedge pixel_clk); t0=$realtime;
        repeat (100) @(posedge pixel_clk);
        period=($realtime-t0)/100.0;
        // Ten rounded 1fs half-periods plus realtime subtraction tolerance.
        if (period < 6.73399 || period > 6.73402) $fatal(1,"pixel clock frequency incorrect: %f ns",period);
        @(posedge serial_clk); t0=$realtime;
        repeat (500) @(posedge serial_clk);
        period=($realtime-t0)/500.0;
        if (period < 1.3468 || period > 1.34681) $fatal(1,"serial clock frequency incorrect: %f ns",period);
        wait(locked);
        wait(pixel_reset_n && source_reset_n);
        #1; reset_n=0; #0.01;
        if (pixel_reset_n || source_reset_n || locked || serializer_reset_n || serial_clk)
            $fatal(1,"destination reset assertion failed");
        $display("PASS tb_video_clock_1080p: 148.5/742.5 MHz, lock qualification, gated-clock reset/restart");
        $finish;
    end
    initial begin #4100000; $fatal(1,"clock model test timeout"); end
endmodule
