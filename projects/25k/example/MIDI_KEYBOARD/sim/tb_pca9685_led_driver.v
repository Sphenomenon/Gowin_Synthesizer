`timescale 1ns / 1ps
`include "sim/tb_touch_i2c_model.v"
`timescale 1ns / 1ps
module tb_pca9685_led_driver;
    reg clk = 0; always #10 clk = ~clk;
    reg reset = 1, nack_all = 0;
    reg [15:0] leds = 16'h8001;
    reg [7:0] brightness = 8'h80;
    reg use_slider = 0, slider_enabled = 1;
    reg [7:0] slider_position = 0;
    wire [15:0] slider_leds;
    midi_slider_led_map slider(.enabled(slider_enabled), .position(slider_position), .led_bitmap(slider_leds));
    tri1 scl, sda;
    wire ready;
    wire [15:0] errors;
    pca9685_led_driver #(.STARTUP_CYCLES(10), .OSC_SETTLE_CYCLES(40),
        .RETRY_CYCLES(100), .REFRESH_CYCLES(200), .HALF_CYCLES(5),
        .BUS_FREE_CYCLES(8), .TIMEOUT_CYCLES(200)) dut (
        .clk(clk), .reset(reset), .scl(scl), .sda(sda), .led_bitmap(use_slider ? slider_leds : leds),
        .brightness(brightness), .ready(ready), .errors(errors));
    midi_i2c_slave_model #(.ADDRESS(7'h40)) device (.scl(scl), .sda(sda), .nack_all(nack_all));
    integer config_step = 0, prior_stops = 0, frames = 0;
    time woke_at;
    // Observe bytes actually received from the pins, including init order.
    always @(device.stops) if (device.stops != prior_stops) begin
        prior_stops = device.stops;
        if (device.last_data_bytes == 1 && config_step < 5) begin
            case (config_step)
                0: if (device.mem[0] !== 8'h30) $fatal(1,"MODE1 must enter sleep + AI");
                1: if (device.mem[1] !== 8'h04) $fatal(1,"MODE2 must source grounded-cathode LEDs and latch at STOP");
                2: if (device.mem[8'hfe] !== 8'd30 || !device.mem[0][4]) $fatal(1,"Prescale must be written asleep");
                3: begin
                    if (device.mem[0] !== 8'h20) $fatal(1,"Wake must keep AI enabled");
                    woke_at = $time;
                end
                4: begin
                    if (device.mem[0] !== 8'ha0 || $time - woke_at < 800)
                        $fatal(1,"RESTART must follow oscillator settle");
                end
            endcase
            config_step = config_step + 1;
        end
        if (device.last_data_bytes > 1) begin
            if (device.last_data_bytes != 64) $fatal(1,"All 16 PWM values must latch on one STOP");
            frames = frames + 1;
        end
    end
    task check_frame(input [15:0] expected_leds, input [7:0] level);
        integer c;
        reg [31:0] got, expected;
        reg [11:0] duty;
        begin
            duty = {level,level[7:4]};
            for (c = 0; c < 16; c = c + 1) begin
                got = {device.mem[9+c*4],device.mem[8+c*4],device.mem[7+c*4],device.mem[6+c*4]};
                expected = !expected_leds[c] || level == 0 ? 32'h10000000 :
                    (level == 255 ? 32'h00001000 : {4'b0,duty,16'b0});
                if (got !== expected) $fatal(1,"PWM channel%0d %08h expected %08h",c,got,expected);
            end
        end
    endtask
    task wait_frame;
        integer previous;
        begin
            previous = frames; wait(frames > previous);
            repeat (4) @(negedge clk);
        end
    endtask
    initial begin
        repeat (5) @(negedge clk); reset = 0;
        wait(ready); #1;
        if (config_step != 5 || errors) $fatal(1,"Missing actual PCA initialization");
        check_frame(16'h8001,8'h80);
        // Change input during transmission: a frame must retain its snapshot.
        wait(dut.state == 4 && dut.waiting && dut.bus.byte_index == 8);
        leds = 16'h00f0; brightness = 255;
        wait_frame(); check_frame(16'h8001,8'h80);
        wait_frame(); check_frame(16'h00f0,255);
        leds = 16'hffff; brightness = 0;
        wait_frame(); check_frame(16'hffff,0);
        leds = 16'ha55a; brightness = 1;
        wait_frame(); check_frame(16'ha55a,1);
        // An ACK failure invalidates readiness and runs the real init again.
        nack_all = 1; wait(!ready); #1;
        if (!errors) $fatal(1,"Missing PCA ACK error");
        config_step = 0; nack_all = 0; wait(ready); #1;
        if (config_step != 5 || errors) $fatal(1,"PCA did not reinitialize after NACK");
        check_frame(16'ha55a,1);
        // The physical PCA bank is the slider bar. Decode its real I2C PWM
        // writes for zero, first segment, center, full and disabled positions.
        use_slider = 1; brightness = 8'h60;
        // An already-started periodic frame may finish first.
        wait_frame(); wait_frame(); check_frame(16'h0000,8'h60);
        slider_position = 1; wait_frame(); wait_frame(); check_frame(16'h0001,8'h60);
        slider_position = 128; wait_frame(); wait_frame(); check_frame(16'h00ff,8'h60);
        slider_position = 255; wait_frame(); wait_frame(); check_frame(16'hffff,8'h60);
        slider_enabled = 0; wait_frame(); wait_frame(); check_frame(16'h0000,8'h60);
        @(negedge clk); reset = 1; @(negedge clk);
        if (ready || errors || !scl || !sda) $fatal(1,"PCA reset did not release bus");
        $display("PASS PCA9685: address 0x40, sleep/prescale/wake/restart, OUTDRV, 64-byte STOP latch, coherent frame, full-off/on, NACK reinit/reset, real slider bar PWM writes");
        $finish;
    end
    initial begin #10_000_000; $fatal(1,"PCA timeout state=%d busstate=%d errors=%h",dut.state,dut.bus.state,errors); end
endmodule
