`timescale 1ns / 1ps
`include "sim/tb_touch_i2c_model.v"
`timescale 1ns / 1ps

// Exercise the public tuning parameters through two real open-drain buses.
// Corrupt the slider's NDIL only after its write has completed, so rejection
// proves configuration readback rather than an implementation-side constant.
module tb_touch_tuning;
    reg clk = 0;
    always #10 clk = ~clk;
    reg reset = 1;
    tri1 k_scl, k_sda, s_scl, s_sda;
    wire [15:0] keys, errors;
    wire key_update, slider_valid, slider_touch, keypad_ready, slider_ready;
    wire [7:0] slider_position;
    integer electrode;
    integer key_ndil_reads = 0, slider_ndil_reads = 0;
    integer slider_failed_readbacks = 0;
    reg injected = 0;

    midi_touch_frontend #(
        .STARTUP_CYCLES(20), .CALIBRATION_CYCLES(20),
        .POLL_CYCLES(100), .MIN_SCAN_CYCLES(100), .HALF_CYCLES(5), .BUS_FREE_CYCLES(8),
        .TIMEOUT_CYCLES(200),
        .KEY_NEGATIVE_THRESHOLD(14), .KEY_DETECT_INTEGRATOR(5),
        .KEY_BURST_LENGTH(5),
        .SLIDER_NEGATIVE_THRESHOLD(13), .SLIDER_DETECT_INTEGRATOR(4),
        .SLIDER_BURST_LENGTH(9)
    ) dut (
        .clk(clk), .reset(reset), .change_n(1'b1),
        .touch1_scl(k_scl), .touch1_sda(k_sda),
        .touch2_scl(s_scl), .touch2_sda(s_sda),
        .key_bitmap(keys), .key_update(key_update),
        .slider_valid(slider_valid), .slider_position(slider_position),
        .slider_touch(slider_touch), .keypad_ready(keypad_ready),
        .slider_ready(slider_ready), .errors(errors)
    );
    midi_i2c_slave_model key_device (
        .scl(k_scl), .sda(k_sda), .nack_all(1'b0));
    midi_i2c_slave_model slider_device (
        .scl(s_scl), .sda(s_sda), .nack_all(1'b0));

    // These completions contain bytes decoded from the physical bus model.
    always @(posedge clk) begin
        if (!reset && dut.keypad.state == 2 && dut.keypad.waiting &&
            dut.keypad.transaction_done && dut.keypad.config_index == 7) begin
            key_ndil_reads = key_ndil_reads + 1;
            if (dut.keypad.read_data[7:0] !== 5)
                $fatal(1,"Key NDIL readback ignored its independent override");
        end
        if (!reset && dut.slider.state == 2 && dut.slider.waiting &&
            dut.slider.transaction_done && dut.slider.config_index == 6) begin
            slider_ndil_reads = slider_ndil_reads + 1;
            if (dut.slider.read_data[7:0] === 29)
                slider_failed_readbacks = slider_failed_readbacks + 1;
            else if (dut.slider.read_data[7:0] !== 4)
                $fatal(1,"Unexpected slider NDIL readback");
        end
    end

    initial begin
        repeat (5) @(negedge clk);
        reset = 0;
        // The writing phase ends at index 4; index 6 is the NDIL readback.
        // Change the slave on a falling FPGA clock edge before request rises.
        wait(dut.slider.state == 2 && dut.slider.config_index == 6 &&
             !dut.slider.waiting);
        @(negedge clk);
        if (slider_device.mem[17] !== 4 || slider_device.mem[10] !== 0)
            $fatal(1,"Slider NDIL was not written before verification/calibration");
        slider_device.mem[17] = 29;
        injected = 1;

        wait(errors[15:8] === 8'h06);
        #1;
        if (slider_ready || dut.raw_slider_touch || !dut.raw_slider_valid)
            $fatal(1,"Configuration mismatch did not invalidate/publish release");
        if (slider_device.mem[10] !== 0)
            $fatal(1,"Unverified slider configuration was calibrated");
        @(posedge slider_valid);
        #1;
        if (slider_touch || slider_ready)
            $fatal(1,"Slider filter retained touch after configuration failure");

        // Retry must rewrite NDIL, verify it, calibrate, and become ready.
        wait(keypad_ready && slider_ready);
        #1;
        if (errors !== 0 || keys !== 0 || slider_touch)
            $fatal(1,"Bad state after tuning configuration recovery");
        if (key_device.mem[12] !== 1 || key_device.mem[13] !== 1 ||
            key_device.mem[17] !== 5 || key_device.mem[10] !== 1)
            $fatal(1,"Key LP/BREP/NDIL/calibration not written");
        if (slider_device.mem[12] !== 1 || slider_device.mem[13] !== 1 ||
            slider_device.mem[17] !== 4 || slider_device.mem[10] !== 1)
            $fatal(1,"Slider LP/BREP/NDIL/calibration not restored");
        for (electrode = 0; electrode < 16; electrode = electrode + 1) begin
            if (key_device.mem[38+electrode] !== 14 ||
                key_device.mem[54+electrode] !== 5)
                $fatal(1,"Key electrode %0d tuning override not written",electrode);
            if (slider_device.mem[54+electrode] !== (electrode < 8 ? 9 : 0))
                $fatal(1,"Slider electrode %0d BL override/disable missing",electrode);
            if (electrode < 8 && slider_device.mem[38+electrode] !== 13)
                $fatal(1,"Slider electrode %0d threshold override missing",electrode);
        end
        if (!injected || key_ndil_reads != 1 || slider_ndil_reads != 2 ||
            slider_failed_readbacks != 1)
            $fatal(1,"Incomplete independent readback/retry coverage");
        if (key_device.final_nacks < 6 || slider_device.final_nacks < 8)
            $fatal(1,"Insufficient real I2C read transactions");
        $display("PASS touch tuning: six independent overrides written/read back, all electrode settings, LP/BREP, calibration, slider NDIL mismatch release and retry recovery");
        $finish;
    end

    initial begin
        #20_000_000;
        $fatal(1,"Touch tuning timeout key_state=%0d slider_state=%0d index=%0d errors=%h",
            dut.keypad.state,dut.slider.state,dut.slider.config_index,errors);
    end
endmodule
