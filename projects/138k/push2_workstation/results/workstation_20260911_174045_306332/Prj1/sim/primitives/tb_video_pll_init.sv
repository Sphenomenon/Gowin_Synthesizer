`timescale 1ns/1ps
// Actual video wrapper, official initialization helper, lock filters and startup.
// The runner supplies declaration-compatible inert PLL/CLKDIV stubs. Only raw
// LOCK is injected below; analog PLL behavior and output frequency are excluded.
// Test-only CLK_PERIOD overrides shorten the helper's wait-counter width; the
// production wrapper fixes both initialization clocks to clk50 / 20 ns.
module tb_video_pll_init;
    reg clk50=0, reset_n=0;
    always #10 clk50=~clk50;
    reg reference_available=1, tmds_available=1;
    wire pixel_clk, serial_clk, serializer_reset_n, serializer_reset, locked;
    video_pll_1080p_gw5a #(.LOCK_STABLE_CYCLES(4)) dut (
        .clk_50m(clk50),.reset_n(reset_n),.pixel_clk(pixel_clk),.serial_clk(serial_clk),
        .serializer_reset_n(serializer_reset_n),.serializer_reset(serializer_reset),.locked(locked)
    );
    defparam dut.u_reference.u_pll_init.CLK_PERIOD=250000;
    defparam dut.u_tmds.u_pll_init.CLK_PERIOD=250000;
    wire reference_raw=reference_available && !dut.u_reference.pll_reset;
    wire tmds_raw=tmds_available && !dut.u_tmds.pll_reset;

    // A fractional MULTI_FAC comparison must select the same ROM as integer24.
    wire helper24_reset,helperfrac_reset,helper24_lock,helperfrac_lock;
    wire [5:0] helper24_icp,helperfrac_icp;
    wire [2:0] helper24_lpf,helperfrac_lpf;
    video_pll_init #(.CLK_PERIOD(250000),.MULTI_FAC(24)) helper24 (
        clk50,!reset_n,reference_available,helper24_reset,helper24_icp,helper24_lpf,helper24_lock
    );
    video_pll_init #(.CLK_PERIOD(250000),.MULTI_FAC(24.75)) helperfrac (
        clk50,!reset_n,reference_available,helperfrac_reset,helperfrac_icp,helperfrac_lpf,helperfrac_lock
    );
    integer reference_resets=0,tmds_resets=0,startups=0;
    realtime released_at;
    always @(posedge dut.u_reference.pll_reset) reference_resets=reference_resets+1;
    always @(posedge dut.u_tmds.pll_reset) tmds_resets=tmds_resets+1;
    always @(negedge serializer_reset) released_at=$realtime;
    always @(posedge locked) begin
        if(!dut.reference_ready || !dut.tmds_ready || serializer_reset || !serializer_reset_n)
            $fatal(1,"serializer opened before both initialized PLLs qualified");
        if($realtime-released_at<79.999)
            $fatal(1,"serializer reset was not released 80ns before output gate");
        startups=startups+1;
    end
    always @(negedge clk50) if(reset_n) begin
        if({helper24_reset,helper24_icp,helper24_lpf,helper24_lock} !==
           {helperfrac_reset,helperfrac_icp,helperfrac_lpf,helperfrac_lock})
            $fatal(1,"MULTI_FAC 24 and 24.75 selected different analog search tables");
        if(!dut.reference_ready && (!dut.u_tmds.reset || !dut.u_tmds.pll_reset || dut.tmds_lock))
            $fatal(1,"second PLL initialization escaped unstable-reference reset");
        if(dut.u_reference.PLL_inst.ICPSEL !== dut.u_reference.u_pll_init.ICPSEL ||
           dut.u_reference.PLL_inst.LPFRES !== dut.u_reference.u_pll_init.LPFRES ||
           dut.u_tmds.PLL_inst.ICPSEL !== dut.u_tmds.u_pll_init.ICPSEL ||
           dut.u_tmds.PLL_inst.LPFRES !== dut.u_tmds.u_pll_init.LPFRES)
            $fatal(1,"PLL analog control ports bypassed initialization helper");
        if(dut.u_reference.PLL_inst.RESET !== dut.u_reference.u_pll_init.O_RST ||
           dut.u_tmds.PLL_inst.RESET !== dut.u_tmds.u_pll_init.O_RST ||
           dut.u_reference.PLL_inst.ENCLK0 !== 1'b1 || dut.u_tmds.PLL_inst.ENCLK0 !== locked)
            $fatal(1,"PLL reset or dedicated output gate wiring changed");
    end
    task expect_stopped;
        begin
            #0.01;
            if(locked || serializer_reset_n || !serializer_reset)
                $fatal(1,"loss/reset did not immediately stop serializer and assert reset");
        end
    endtask
    task await_startup;
        integer cycles;
        begin
            cycles=0;
            while(!locked && cycles<1000) begin @(negedge clk50); cycles=cycles+1; end
            if(!locked) $fatal(1,"initialized PLL cascade never restarted");
        end
    endtask
    integer old_reference_resets,old_tmds_resets;
    initial begin
        force dut.u_reference.pll_raw_lock=reference_raw;
        force dut.u_tmds.pll_raw_lock=tmds_raw;
        if(dut.u_reference.u_pll_init.MULTI_FAC!=24 || dut.u_tmds.u_pll_init.MULTI_FAC!=15 ||
           dut.u_reference.PLL_inst.MDIV_SEL!=24 || dut.u_reference.PLL_inst.MDIV_FRAC_SEL!=6 ||
           dut.u_tmds.PLL_inst.MDIV_SEL!=15 || dut.u_tmds.PLL_inst.MDIV_FRAC_SEL!=0 ||
           dut.u_reference.PLL_inst.DYN_ICP_SEL!="TRUE" || dut.u_reference.PLL_inst.DYN_LPF_SEL!="TRUE" ||
           dut.u_tmds.PLL_inst.DYN_ICP_SEL!="TRUE" || dut.u_tmds.PLL_inst.DYN_LPF_SEL!="TRUE")
            $fatal(1,"video PLL ratio/analog initialization parameters changed");
        #41;reset_n=1;
        repeat(20) @(negedge clk50);
        if(dut.reference_ready || locked) $fatal(1,"raw LOCK bypassed initialization search");
        await_startup;
        if(reference_resets<7 || tmds_resets<7)
            $fatal(1,"initialization did not scan analog configurations");

        // A sub-cycle PLL2 lock glitch retains its chosen analog values, but
        // must immediately stop clocks and repeat the complete lock qualifier.
        old_tmds_resets=tmds_resets;
        #3;tmds_available=0;expect_stopped;
        #1;tmds_available=1;
        repeat(5) @(negedge clk50);
        if(locked) $fatal(1,"short lock loss skipped requalification");
        await_startup;
        if(tmds_resets!=old_tmds_resets)
            $fatal(1,"PLL2 lock glitch unexpectedly restarted vendor analog search");

        // Losing PLL1 invalidates PLL2's reference and restarts PLL2's helper.
        old_reference_resets=reference_resets;old_tmds_resets=tmds_resets;
        #3;reference_available=0;expect_stopped;
        repeat(3) @(negedge clk50);
        if(!dut.u_tmds.pll_reset || dut.u_tmds.u_pll_init.state!=0)
            $fatal(1,"reference loss did not reset second initialization FSM");
        reference_available=1;
        await_startup;
        if(reference_resets!=old_reference_resets || tmds_resets<old_tmds_resets+7)
            $fatal(1,"cascade recovery did not rerun exactly the dependent helper");

        old_reference_resets=reference_resets;old_tmds_resets=tmds_resets;
        #3;reset_n=0;expect_stopped;
        repeat(3) @(negedge clk50);reset_n=1;
        await_startup;
        if(reference_resets<old_reference_resets+7 || tmds_resets<old_tmds_resets+7 || startups!=4)
            $fatal(1,"external reset did not fully initialize both stages again");
        $display("PASS tb_video_pll_init: actual wrapper, vendor analog search, 24/24.75 table equivalence, staged initialization, sub-cycle lock loss, cascade and external reset recovery, 80ns serializer gate");
        $finish;
    end
    initial begin #100000;$fatal(1,"PLL initialization test timeout");end
endmodule
