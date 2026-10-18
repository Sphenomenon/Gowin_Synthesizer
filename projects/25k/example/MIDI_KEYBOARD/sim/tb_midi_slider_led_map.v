`timescale 1ns / 1ps

module tb_midi_slider_led_map;
    reg enabled = 0;
    reg [7:0] position = 0;
    wire [15:0] led_bitmap;
    integer value, led, lit_count;
    reg [15:0] expected, previous;

    midi_slider_led_map dut (
        .enabled(enabled),
        .position(position),
        .led_bitmap(led_bitmap)
    );

    // Integer arithmetic avoids an eight-bit addition wrapping near 255.
    // Build the expected bar from ceil(value / 16), independently of the DUT's
    // channel-by-channel comparisons.
    function [15:0] expected_bar;
        input integer sample;
        integer count, bit_number;
        begin
            count = (sample + 15) / 16;
            expected_bar = 0;
            for (bit_number = 0; bit_number < count; bit_number = bit_number + 1)
                expected_bar[bit_number] = 1'b1;
        end
    endfunction

    task check_marker;
        input [7:0] sample;
        input [15:0] marker;
        begin
            position = sample;
            #1;
            if (led_bitmap !== marker)
                $fatal(1, "Slider marker at %0d: got %04h, expected %04h", sample, led_bitmap, marker);
        end
    endtask

    initial begin
        previous = 0;
        enabled = 1;
        for (value = 0; value < 256; value = value + 1) begin
            position = value;
            expected = expected_bar(value);
            #1;
            if (led_bitmap !== expected)
                $fatal(1, "Slider bar at %0d: got %04h, expected %04h", value, led_bitmap, expected);
            if ((led_bitmap & previous) !== previous)
                $fatal(1, "Slider bar lost lit channels at rising position %0d", value);
            lit_count = 0;
            for (led = 0; led < 16; led = led + 1)
                if (led_bitmap[led]) lit_count = lit_count + 1;
            if (lit_count != (value + 15) / 16)
                $fatal(1, "Slider bar count %0d at position %0d", lit_count, value);
            previous = led_bitmap;

            // Disabling must extinguish every possible position immediately.
            enabled = 0;
            #1;
            if (led_bitmap !== 16'h0000)
                $fatal(1, "Disabled slider must be dark at position %0d", value);
            enabled = 1;
            #1;
            if (led_bitmap !== expected)
                $fatal(1, "Re-enabled slider did not restore position %0d", value);
        end

        // Explicit bin edges, half/full scale, and the 8-bit upper boundary.
        check_marker(8'd0,   16'h0000);
        check_marker(8'd1,   16'h0001);
        check_marker(8'd16,  16'h0001);
        check_marker(8'd17,  16'h0003);
        check_marker(8'd127, 16'h00ff);
        check_marker(8'd128, 16'h00ff);
        check_marker(8'd129, 16'h01ff);
        check_marker(8'd240, 16'h7fff);
        check_marker(8'd241, 16'hffff);
        check_marker(8'd254, 16'hffff);
        check_marker(8'd255, 16'hffff);
        check_marker(8'd0,   16'h0000);

        $display("PASS slider LED map: all 256 positions, disable/restore, monotonic fill, zero/half/full markers and 8-bit boundary");
        $finish;
    end
endmodule
