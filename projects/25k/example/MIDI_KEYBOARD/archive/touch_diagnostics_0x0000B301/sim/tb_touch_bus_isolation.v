`timescale 1ns / 1ps
`include "sim/tb_touch_i2c_model.v"
`timescale 1ns / 1ps

// Exercise the two physical open-drain buses while the shared CHANGE signal
// is active. Slider status bytes deliberately carry the raw G/H key pattern.
module tb_touch_bus_isolation;
    reg clk = 0;
    always #10 clk = ~clk;
    reg reset = 1, change_n = 1;
    tri1 k_scl, k_sda, s_scl, s_sda;
    wire [15:0] raw_keys, logical_keys, errors;
    wire key_update, slider_valid, slider_touch, keypad_ready, slider_ready;
    wire [7:0] slider_position;
    localparam QUIET = 1, TRANSITION = 2, HELD = 3;
    integer phase = 0;
    integer key_samples = 0, slider_samples = 0;
    integer quiet_key_samples = 0, held_key_samples = 0;
    integer quiet_cycles = 0, held_cycles = 0;
    integer i;

    midi_touch_frontend #(
        .STARTUP_CYCLES(20), .CALIBRATION_CYCLES(100),
        .MIN_SCAN_CYCLES(30000), .POLL_CYCLES(40000),
        .HALF_CYCLES(5), .BUS_FREE_CYCLES(8), .TIMEOUT_CYCLES(200)
    ) dut (
        .clk(clk), .reset(reset), .change_n(change_n), .slider_scan_pause(1'b0),
        .touch1_scl(k_scl), .touch1_sda(k_sda),
        .touch2_scl(s_scl), .touch2_sda(s_sda),
        .key_bitmap(raw_keys), .key_update(key_update),
        .slider_valid(slider_valid), .slider_position(slider_position),
        .slider_touch(slider_touch), .keypad_ready(keypad_ready),
        .slider_ready(slider_ready), .errors(errors)
    );
    midi_key_layout layout (.raw_keys(raw_keys), .key_bitmap(logical_keys));
    midi_i2c_slave_model key_device (
        .scl(k_scl), .sda(k_sda), .nack_all(1'b0));
    midi_i2c_slave_model slider_device (
        .scl(s_scl), .sda(s_sda), .nack_all(1'b0));

    // Check every clock, including gaps between key_update pulses. Waiting
    // for the eventual expected bitmap would miss a transient false press.
    always @(posedge clk) begin
        #1;
        if (!reset && phase != 0) begin
            if (errors || !keypad_ready || !slider_ready)
                $fatal(1,"Isolation test lost a configured device errors=%h", errors);
            if (key_update) key_samples = key_samples + 1;
            if (slider_valid) slider_samples = slider_samples + 1;
            if (phase == QUIET) begin
                quiet_cycles = quiet_cycles + 1;
                if (key_update) quiet_key_samples = quiet_key_samples + 1;
                if (raw_keys !== 16'h0000 || logical_keys !== 16'h0000)
                    $fatal(1,"Slider leaked into idle keys raw=%h logical=%h", raw_keys, logical_keys);
            end else if (phase == HELD) begin
                held_cycles = held_cycles + 1;
                if (key_update) held_key_samples = held_key_samples + 1;
                if (raw_keys !== 16'h8200 || logical_keys !== 16'h00c0)
                    $fatal(1,"Slider altered real G/H raw=%h logical=%h", raw_keys, logical_keys);
            end
        end
    end

    // Change bytes during real transactions, rather than forcing internal
    // data. The unrelated U2 key bytes alternate 0x8200 and 0xffff.
    task slider_epoch(input integer position, input integer index, input integer toggle_change);
        integer clocks;
        begin
            @(negedge clk);
            slider_device.mem[2] = index[0] ? 8'h01 : 8'h00;
            slider_device.mem[3] = index[1] ? 8'hff : 8'h00;
            slider_device.mem[4] = index[1] ? 8'hff : 8'h82;
            slider_device.mem[5] = position[7:0];
            if (!toggle_change) change_n = 0;
            for (clocks = 0; clocks < 2000; clocks = clocks + 1) begin
                @(negedge clk);
                if (toggle_change && clocks % 7 == 0) change_n = !change_n;
            end
        end
    endtask

    task wait_keys(input [15:0] expected);
        integer attempts;
        begin : awaiting
            for (attempts = 0; attempts < 5; attempts = attempts + 1) begin
                @(posedge key_update); #1;
                if (raw_keys === expected) disable awaiting;
            end
            $fatal(1,"Raw bitmap %h expected %h", raw_keys, expected);
        end
    endtask

    initial begin
        repeat (5) @(negedge clk);
        reset = 0;
        wait(keypad_ready && slider_ready);
        @(negedge clk); phase = QUIET;
        // Every position in both directions, with held-low then rapidly
        // changing shared CHANGE. U1 key status remains exactly zero.
        for (i = 0; i < 256; i = i + 1) slider_epoch(i, i, 0);
        for (i = 0; i < 256; i = i + 1) slider_epoch(255-i, i, 1);

        // A real simultaneous G/H press must survive continued slider use.
        // The model supplies signal=1000/reference=1100 for every electrode.
        @(negedge clk); phase = TRANSITION;
        key_device.mem[3] = 0;
        key_device.mem[4] = 8'h82;
        wait_keys(16'h8200);
        @(negedge clk);
        if (logical_keys !== 16'h00c0)
            $fatal(1,"Raw G/H did not map only to logical G/H");
        phase = HELD;
        for (i = 0; i < 128; i = i + 1) slider_epoch(i*2, i, 0);
        for (i = 0; i < 128; i = i + 1) slider_epoch(255-i*2, i, 1);

        @(negedge clk); phase = TRANSITION;
        key_device.mem[4] = 0;
        wait_keys(16'h0000);
        @(negedge clk); phase = QUIET;
        for (i = 0; i < 64; i = i + 1) slider_epoch(i*4, i, 1);
        if (quiet_key_samples < 25 || held_key_samples < 10 || slider_samples < 40 ||
            quiet_cycles < 1000000 || held_cycles < 500000)
            $fatal(1,"Insufficient cross-bus isolation coverage key=%0d/%0d slider=%0d",
                   quiet_key_samples, held_key_samples, slider_samples);
        $display("PASS touch bus isolation: independent real I2C, U2 8200/ffff status and position/touch sweeps, shared CHANGE held/toggling, idle raw/logical keys always zero, real G/H retained and released; quiet=%0d held=%0d slider=%0d samples",
                 quiet_key_samples, held_key_samples, slider_samples);
        $finish;
    end
    initial begin
        #100_000_000;
        $fatal(1,"Touch isolation timeout phase=%0d raw=%h errors=%h", phase, raw_keys, errors);
    end
endmodule
