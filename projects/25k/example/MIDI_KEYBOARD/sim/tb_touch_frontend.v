`timescale 1ns / 1ps
`include "sim/tb_touch_i2c_model.v"
`timescale 1ns / 1ps
module tb_touch_frontend;
    reg clk = 0; always #10 clk = ~clk;
    reg reset = 1, change_n = 1, key_nack = 0, slider_nack = 0;
    tri1 k_scl, k_sda, s_scl, s_sda;
    wire [15:0] keys, errors;
    wire key_update, slider_valid, slider_touch, keypad_ready, slider_ready;
    wire [7:0] slider_position;
    midi_touch_frontend #(.STARTUP_CYCLES(20), .CALIBRATION_CYCLES(20),
        .POLL_CYCLES(100), .MIN_SCAN_CYCLES(100), .HALF_CYCLES(5), .BUS_FREE_CYCLES(8),
        .TIMEOUT_CYCLES(200)) dut (
        .clk(clk), .reset(reset), .change_n(change_n),
        .touch1_scl(k_scl), .touch1_sda(k_sda), .touch2_scl(s_scl), .touch2_sda(s_sda),
        .key_bitmap(keys), .key_update(key_update), .slider_valid(slider_valid),
        .slider_position(slider_position), .slider_touch(slider_touch),
        .keypad_ready(keypad_ready), .slider_ready(slider_ready), .errors(errors));
    midi_i2c_slave_model key_device(.scl(k_scl), .sda(k_sda), .nack_all(key_nack));
    midi_i2c_slave_model slider_device(.scl(s_scl), .sda(s_sda), .nack_all(slider_nack));
    integer key_frames = 0, slider_frames = 0;
    always @(posedge clk) begin
        if (key_update) key_frames = key_frames + 1;
        if (slider_valid) slider_frames = slider_frames + 1;
    end
    task wait_keys(input [15:0] expected);
        integer tries;
        begin : awaiting
            for (tries = 0; tries < 5; tries = tries + 1) begin
                @(posedge key_update); #1;
                if (keys === expected) disable awaiting;
            end
            $fatal(1,"Key bitmap %04h expected %04h",keys,expected);
        end
    endtask
    task hold_keys(input [15:0] expected);
        integer frames;
        begin
            // Require several complete transactions, rather than accepting
            // an unchanged snapshot that was already in flight.
            for (frames = 0; frames < 3; frames = frames + 1) begin
                @(posedge key_update); #1;
                if (keys !== expected) $fatal(1,"Unstable keys %04h expected %04h",keys,expected);
            end
        end
    endtask
    task wait_slider(input [7:0] expected_position, input expected_touch);
        integer tries;
        begin : awaiting
            for (tries = 0; tries < 5; tries = tries + 1) begin
                @(posedge slider_valid); #1;
                if (slider_position === expected_position && slider_touch === expected_touch) disable awaiting;
            end
            $fatal(1,"Slider %d/%b expected %d/%b",slider_position,slider_touch,expected_position,expected_touch);
        end
    endtask
    task key_delta(input integer channel, input integer delta);
        integer reference_value;
        begin
            reference_value = 1000 + delta;
            key_device.mem[132+channel*2] = reference_value & 255;
            key_device.mem[133+channel*2] = (reference_value >> 8) & 255;
        end
    endtask
    integer electrode;
    initial begin
        repeat (5) @(negedge clk); reset = 0;
        wait(keypad_ready && slider_ready); #1;
        if (keys !== 0 || errors !== 0) $fatal(1,"Bad startup state");
        if (key_device.mem[12] !== 1 || key_device.mem[13] !== 1 ||
            key_device.mem[17] !== 1 || key_device.mem[20] !== 0 ||
            key_device.mem[38] !== 12 || key_device.mem[54] !== 4 || key_device.mem[10] !== 1)
            $fatal(1,"Keypad configuration not actually written");
        if (slider_device.mem[12] !== 1 || slider_device.mem[13] !== 1 ||
            slider_device.mem[17] !== 3 || slider_device.mem[38] !== 12 ||
            slider_device.mem[20] !== 8'h28 || slider_device.mem[21] !== 0 ||
            slider_device.mem[22] !== 1 || slider_device.mem[29] !== 1 ||
            slider_device.mem[54] !== 8 || slider_device.mem[62] !== 0)
            $fatal(1,"Slider configuration not actually written");
        for (electrode = 0; electrode < 16; electrode = electrode + 1) begin
            if (key_device.mem[38+electrode] !== 12 || key_device.mem[54+electrode] !== 4)
                $fatal(1,"Keypad electrode %0d not configured",electrode);
            if (slider_device.mem[54+electrode] !== (electrode < 8 ? 8 : 0))
                $fatal(1,"Slider electrode %0d not configured",electrode);
        end
        // Complete bitmap semantics include releases and all sixteen notes.
        // A stable press is published by the first complete snapshot;
        // the host must not add another multi-frame detection integrator.
        wait(dut.keypad.state == 10); @(negedge clk);
        key_device.mem[3] = 8'h81; key_device.mem[4] = 8'h81;
        change_n = 0; @(posedge key_update); #1;
        if (keys !== 16'h8181) $fatal(1,"Stable press delayed beyond its first complete snapshot");
        change_n = 1;
        key_device.mem[3] = 8'hff; key_device.mem[4] = 8'hff;
        wait_keys(16'hffff);
        // Held-key hysteresis: bit0 delta=10 passes, bit1 delta=9 fails;
        // bit2 signal exceeds reference and must never wrap into a press.
        key_delta(0,10); key_delta(1,9);
        key_device.mem[136] = 0; key_device.mem[137] = 0;
        wait_keys(16'hfff9);
        key_device.mem[3] = 0; key_device.mem[4] = 0; wait_keys(0);
        // New presses need the full threshold: weak raw detect bits must
        // not re-trigger a key using the lower release threshold.
        key_delta(0,10); key_delta(1,11); key_delta(2,12);
        key_device.mem[3] = 7; wait_keys(4); hold_keys(4);
        key_delta(2,10); wait_keys(4); hold_keys(4);
        key_delta(2,9); wait_keys(0);
        key_delta(2,11); wait_keys(0); hold_keys(0);
        key_delta(2,12); wait_keys(4);
        key_device.mem[3] = 0; wait_keys(0);
        slider_device.mem[2] = 1; slider_device.mem[5] = 0; wait_slider(0,1);
        slider_device.mem[5] = 128; wait_slider(128,1);
        slider_device.mem[5] = 255; wait_slider(255,1);
        // Exercise filtering through real I2C, including small jitter,
        // a one-sample outlier and confirmed endpoint movement.
        slider_device.mem[5] = 254; wait_slider(255,1);
        slider_device.mem[5] = 0;
        @(posedge slider_valid); #1;
        if (slider_position !== 255 || !slider_touch) $fatal(1,"Single slider spike passed");
        slider_device.mem[5] = 255; wait_slider(255,1);
        slider_device.mem[2] = 0; wait_slider(255,0);
        // A key which changed between the bracketing status reads must not
        // generate a press from stale signal/reference data.
        key_device.mem[3] = 8'h80;
        wait(dut.keypad.state == 5); key_device.mem[3] = 0;
        wait_keys(0);
        key_device.mem[3] = 8'h80; wait_keys(16'h0080);
        key_nack = 1;
        @(posedge key_update); #1;
        if (keys !== 0 || keypad_ready || errors[7:0] == 0)
            $fatal(1,"Key NACK did not publish release");
        key_nack = 0; key_device.mem[3] = 0;
        wait(keypad_ready); wait_keys(0);
        slider_device.mem[2] = 1; wait_slider(255,1);
        slider_nack = 1; @(posedge slider_valid); #1;
        if (slider_touch || slider_ready || errors[15:8] == 0)
            $fatal(1,"Slider NACK retained touch");
        slider_nack = 0; slider_device.mem[2] = 0;
        wait(slider_ready); wait_slider(255,0);
        // Runtime device reset is rejected, first power-on reset is cleared.
        key_device.mem[2] = 8'h80;
        @(posedge key_update); #1;
        if (keys || keypad_ready || errors[7:0] !== 7) $fatal(1,"Runtime reset not detected");
        key_device.mem[2] = 0; wait(keypad_ready);
        @(negedge clk); reset = 1; @(negedge clk);
        if (keys || keypad_ready || slider_touch || slider_ready || !k_scl || !s_scl)
            $fatal(1,"Synchronous reset did not clear/release peripherals");
        if (key_frames < 9 || slider_frames < 10 || key_device.final_nacks < 10)
            $fatal(1,"Insufficient transaction coverage");
        $display("PASS touch: independent configuration/readback, both buses, 16-key press/release, 12/10 press/release hysteresis, coherent snapshots, slider jitter/spike rejection, endpoints, NACK and reset release");
        $finish;
    end
    initial begin #20_000_000; $fatal(1,"Touch timeout key_state=%d slider_state=%d keys=%h errors=%h",dut.keypad.state,dut.slider.state,keys,errors); end
endmodule
