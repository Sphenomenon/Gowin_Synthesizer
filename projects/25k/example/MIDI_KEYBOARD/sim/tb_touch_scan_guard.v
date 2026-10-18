`timescale 1ns / 1ps
`include "sim/tb_touch_i2c_model.v"
`timescale 1ns / 1ps

// Real open-drain transactions with accelerated waits and SCL timing. The
// scan guard remains substantially longer than a complete key acquisition.
module tb_touch_scan_guard;
    localparam integer MIN_SCAN_CYCLES = 30000;
    localparam integer POLL_CYCLES = 50000;
    reg clk = 0;
    always #10 clk = ~clk;
    reg reset = 1, change_n = 1, slider_nack = 0;
    tri1 k_scl, k_sda, s_scl, s_sda;
    wire [15:0] keys, errors;
    wire key_update, slider_valid, slider_touch, keypad_ready, slider_ready;
    wire [7:0] slider_position, slider_raw_position;
    wire [7:0] slider_general_status, slider_sample_count;
    wire slider_overrun;
    integer cycle = 0, last_key_scan = -1, last_slider_scan = -1;
    integer key_scans = 0, slider_scans = 0, successful_slider_samples = 0;
    integer clear_reads = 0;
    integer epoch_raw_spikes = 0;
    reg check_epoch_spike = 0;
    reg [7:0] expected_slider_count = 0;

    midi_touch_frontend #(
        .STARTUP_CYCLES(20), .CALIBRATION_CYCLES(100),
        .MIN_SCAN_CYCLES(MIN_SCAN_CYCLES), .POLL_CYCLES(POLL_CYCLES),
        .HALF_CYCLES(5), .BUS_FREE_CYCLES(8), .TIMEOUT_CYCLES(200)
    ) dut (
        .clk(clk), .reset(reset), .change_n(change_n),
        .touch1_scl(k_scl), .touch1_sda(k_sda),
        .touch2_scl(s_scl), .touch2_sda(s_sda),
        .key_bitmap(keys), .key_update(key_update),
        .slider_valid(slider_valid), .slider_position(slider_position),
        .slider_touch(slider_touch), .keypad_ready(keypad_ready),
        .slider_ready(slider_ready), .errors(errors),
        .slider_raw_position(slider_raw_position),
        .slider_general_status(slider_general_status),
        .slider_sample_count(slider_sample_count), .slider_overrun(slider_overrun)
    );
    midi_i2c_slave_model key_device (
        .scl(k_scl), .sda(k_sda), .nack_all(1'b0));
    midi_i2c_slave_model slider_device (
        .scl(s_scl), .sda(s_sda), .nack_all(slider_nack));
    // Keep a default instance in reset to check production units without
    // spending simulated time waiting through production initialization.
    midi_qt2160_client default_parameters (
        .clk(clk), .reset(1'b1), .change_n(1'b1),
        .scl_in(1'b1), .sda_in(1'b1));

    // The general-status RESET latch clears after it has been read. The
    // model has already latched the current byte before these falling edges.
    always @(negedge k_scl)
        if (key_device.active && key_device.state == 2 && key_device.pointer == 2)
            key_device.mem[2][7] = 0;
    always @(negedge s_scl)
        if (slider_device.active && slider_device.state == 2 && slider_device.pointer == 2)
            slider_device.mem[2][7] = 0;

    // Observe request launches, not the DUT's counters. All three CHANGE
    // patterns are subject to the same minimum start-to-start interval.
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (reset) begin
            last_key_scan = -1;
            last_slider_scan = -1;
            expected_slider_count = 0;
        end else begin
            if (dut.keypad.request && dut.keypad.read_request &&
                dut.keypad.register_address == 2 && dut.keypad.state == 4) begin
                if (last_key_scan >= 0 && cycle-last_key_scan < MIN_SCAN_CYCLES)
                    $fatal(1,"Shared CHANGE bypassed keypad minimum scan interval");
                last_key_scan = cycle;
                key_scans = key_scans + 1;
            end
            if (dut.slider.request && dut.slider.read_request &&
                dut.slider.register_address == 2 && dut.slider.state == 4) begin
                if (last_slider_scan >= 0 && cycle-last_slider_scan < MIN_SCAN_CYCLES)
                    $fatal(1,"Shared CHANGE bypassed slider minimum scan interval");
                last_slider_scan = cycle;
                slider_scans = slider_scans + 1;
            end
            if (dut.slider.state == 12 && dut.slider.transaction_done) begin
                clear_reads = clear_reads + 1;
                if (dut.raw_slider_valid || slider_ready)
                    $fatal(1,"Clearing the startup RESET published a slider sample");
            end
            if (dut.raw_slider_valid) begin
                if (check_epoch_spike && slider_ready && slider_raw_position == 220)
                    epoch_raw_spikes = epoch_raw_spikes + 1;
                if (slider_ready && errors[15:8] == 0) begin
                    expected_slider_count = expected_slider_count + 1'b1;
                    successful_slider_samples = successful_slider_samples + 1;
                end
                if (slider_sample_count !== expected_slider_count)
                    $fatal(1,"Slider sample counter counted a failure or missed a good frame");
            end
            if (slider_ready && slider_device.mem[20] !== 8'h28)
                $fatal(1,"Slider became ready after its mode configuration was lost");
        end
    end

    task next_slider_scan;
        begin : waiting_for_status
            forever begin
                @(posedge dut.slider.request);
                if (dut.slider.state == 4 && dut.slider.read_request &&
                    dut.slider.register_address == 2)
                    disable waiting_for_status;
            end
        end
    endtask
    task check_slider_spacing(input integer expected_cycles);
        integer earlier, gap, n, minimum_gap, maximum_gap;
        begin
            // Discard a scan already scheduled before the CHANGE transition.
            next_slider_scan(); next_slider_scan();
            earlier = cycle;
            minimum_gap = 32'h7fffffff; maximum_gap = 0;
            for (n = 0; n < 3; n = n + 1) begin
                next_slider_scan(); gap = cycle-earlier; earlier = cycle;
                if (gap < minimum_gap) minimum_gap = gap;
                if (gap > maximum_gap) maximum_gap = gap;
                if (gap < expected_cycles || gap > expected_cycles+8)
                    $fatal(1,"Slider start interval %0d expected %0d..%0d",gap,
                           expected_cycles,expected_cycles+8);
            end
            $display("Scan spacing expected=%0d measured=%0d..%0d cycles",
                     expected_cycles,minimum_gap,maximum_gap);
        end
    endtask
    task wait_general(input [7:0] expected);
        integer attempts;
        begin : awaiting_general
            for (attempts = 0; attempts < 5; attempts = attempts + 1) begin
                @(posedge slider_valid); #1;
                if (slider_ready && slider_general_status === expected)
                    disable awaiting_general;
            end
            $fatal(1,"Slider general status %02h expected %02h",
                   slider_general_status,expected);
        end
    endtask

    reg [7:0] count_before_fault, general_before_fault;
    integer n, epoch_start;
    initial begin
        repeat (5) @(negedge clk);
        key_device.mem[2] = 8'h80;
        slider_device.mem[2] = 8'h80;
        reset = 0;
        wait(keypad_ready && slider_ready); #1;
        if (errors || slider_general_status || slider_overrun || clear_reads != 1)
            $fatal(1,"Startup RESET was not cleared before configuring the devices");

        // A held shared interrupt cannot turn either client into an unlimited
        // reader. No interrupt uses the slower fallback, measured from start.
        @(negedge clk); change_n = 0;
        check_slider_spacing(MIN_SCAN_CYCLES);
        @(negedge clk); change_n = 1;
        check_slider_spacing(POLL_CYCLES);
        fork
            begin
                for (n = 0; n < 25000; n = n + 1) begin
                    repeat (7) @(negedge clk); change_n = !change_n;
                end
                change_n = 1;
            end
            begin repeat (4) next_slider_scan(); end
        join

        // Keep a bad position in the chip for a whole simulated matrix
        // epoch, rather than only one bus read. This controlled slave update
        // model has explicit epochs; the actual ASIC exposes no epoch ID, so
        // a minimum polling interval alone cannot prove distinct ASIC scans.
        @(negedge clk); change_n = 0;
        slider_device.mem[2] = 1; slider_device.mem[5] = 100;
        wait_general(1);
        if (slider_position !== 100 || !slider_touch)
            $fatal(1,"Missing slider baseline before epoch-spike test");
        @(negedge clk);
        check_epoch_spike = 1;
        slider_device.mem[5] = 220;
        epoch_start = cycle;
        fork
            begin
                repeat (MIN_SCAN_CYCLES) @(negedge clk);
                slider_device.mem[5] = 100;
            end
            begin
                while (cycle-epoch_start <= MIN_SCAN_CYCLES) begin
                    @(posedge clk); #1;
                    if (slider_valid && slider_position !== 100)
                        $fatal(1,"One sensor epoch was accepted through duplicate reads");
                end
            end
        join
        repeat (2) begin
            @(posedge slider_valid); #1;
            if (slider_position !== 100 || !slider_touch)
                $fatal(1,"One-epoch position spike escaped filtering");
        end
        check_epoch_spike = 0;
        if (epoch_raw_spikes != 1)
            $fatal(1,"Epoch test did not expose exactly one sensor spike: %0d",epoch_raw_spikes);

        slider_device.mem[2] = 8'h41;
        slider_device.mem[5] = 8'd200;
        wait_general(8'h41);
        if (!slider_overrun || slider_raw_position !== 200)
            $fatal(1,"Raw slider position or CYCLE OVERRUN diagnostics were hidden");
        slider_device.mem[2] = 8'h01;
        wait_general(8'h01);
        if (!slider_overrun)
            $fatal(1,"Overrun history cleared when the current status recovered");

        // A failed bus read publishes a release, retains the last valid
        // diagnostic byte, and does not count as a successful acquisition.
        @(negedge clk);
        count_before_fault = slider_sample_count;
        general_before_fault = slider_general_status;
        slider_nack = 1;
        wait(!slider_ready && errors[15:8] != 0); #1;
        if (slider_sample_count !== count_before_fault ||
            slider_general_status !== general_before_fault || !slider_overrun)
            $fatal(1,"NACK damaged the last good diagnostics or counted a sample");
        @(posedge slider_valid); #1;
        if (slider_touch) $fatal(1,"NACK did not release filtered slider touch");
        slider_nack = 0; slider_device.mem[2] = 0;
        wait(slider_ready); #1;
        if (errors[15:8] || slider_device.mem[20] !== 8'h28 || !slider_overrun)
            $fatal(1,"NACK recovery failed to rewrite slider mode or retain history");

        // Reproduce the former post-readback RESET hole. This reset happens
        // after configuration, rather than being the old startup RESET latch.
        @(negedge clk); reset = 1;
        repeat (3) @(negedge clk);
        reset = 0;
        wait(dut.slider.state == 3);
        @(negedge clk);
        slider_device.mem[2] = 8'h81;
        slider_device.mem[20] = 0;
        wait(errors[15:8] === 8'h07); #1;
        if (slider_ready || dut.raw_slider_touch || slider_sample_count !== 0 ||
            slider_overrun)
            $fatal(1,"CAL_WAIT RESET was accepted as a valid configured sample");
        wait(slider_ready); #1;
        if (slider_device.mem[20] !== 8'h28 || errors[15:8] ||
            slider_sample_count !== 1 || slider_general_status !== 1)
            $fatal(1,"Post-calibration RESET did not reconfigure and recover");
        if (key_scans < 10 || slider_scans < 20 || clear_reads < 4 ||
            successful_slider_samples < 15)
            $fatal(1,"Incomplete scan guard/recovery coverage");
        $display("PASS touch scan guard: minimum and fallback start spacing, shared/frequent CHANGE, startup/post-config RESET, mode rewrite, raw/general/sticky-overrun diagnostics, successful-only count and NACK recovery");
        $finish;
    end
    initial begin
        if (default_parameters.CLK_HZ != 50000000 ||
            default_parameters.MIN_SCAN_CYCLES != 800000 ||
            default_parameters.POLL_CYCLES != 1000000 ||
            default_parameters.HALF_CYCLES != 250 ||
            default_parameters.BUS_FREE_CYCLES != 5000)
            $fatal(1,"Production defaults are not 16/20 ms and 100 kHz/100 us");
        #40_000_000;
        $fatal(1,"Scan guard timeout keypad=%0d slider=%0d errors=%h samples=%0d",
               dut.keypad.state,dut.slider.state,errors,slider_sample_count);
    end
endmodule
