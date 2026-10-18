`timescale 1ns / 1ps
module tb_ws2812;
    reg clk = 0; always #10 clk = ~clk;
    reg reset = 1;
    reg [15:0] keys = 16'h0001;
    reg [7:0] brightness = 8'ha5;
    wire data_out;
    midi_ws2812 dut(.clk(clk), .reset(reset), .key_bitmap(keys), .brightness(brightness), .data_out(data_out));
    // Independent board-order oracle, indexed from the first DIN pixel.
    localparam [127:0] CHAIN = "ABCDHGFEIJKLPONM";
    integer frame = 0, bit_number, pixel, logical_key, k;
    reg [383:0] decoded;
    reg [23:0] expected;
    time rose_at, prior_rose = 0, prior_fall = 0, frame_start;
    time high_time;
    function [23:0] key_color;
        input integer key_number;
        input [7:0] level;
        begin
            case (key_number % 8)
                0: key_color = {8'd0,level,8'd0};
                1: key_color = {level >> 1,level,8'd0};
                2: key_color = {level,level,8'd0};
                3: key_color = {level,16'd0};
                4: key_color = {level,8'd0,level};
                5: key_color = {16'd0,level};
                6: key_color = {8'd0,level >> 1,level};
                7: key_color = {8'd0,level,level};
            endcase
        end
    endfunction
    task receive_frame;
        input [15:0] expected_keys;
        input [7:0] expected_brightness;
        input integer mutate;
        begin
            decoded = 0;
            for (bit_number = 0; bit_number < 384; bit_number = bit_number + 1) begin
                @(posedge data_out); rose_at = $time;
                if (bit_number == 0) begin
                    if (rose_at - prior_fall < 300_000) $fatal(1,"WS reset pulse shorter than 300 us");
                    frame_start = rose_at;
                end else if (rose_at - prior_rose != 1240 && rose_at - prior_rose != 1260)
                    $fatal(1,"WS bit period %0t is not a 62/63-clock cell",rose_at - prior_rose);
                prior_rose = rose_at;
                @(negedge data_out); high_time = $time - rose_at; prior_fall = $time;
                if (high_time != 340 && high_time != 840) $fatal(1,"WS high pulse %0t",high_time);
                decoded[383-bit_number] = high_time == 840;
                if (mutate == 1 && bit_number == 30) begin keys = 16'h8000; brightness = 8'h3c; end
                if (mutate == 2 && bit_number == 30) begin keys = 0; brightness = 0; end
            end
            for (pixel = 0; pixel < 16; pixel = pixel + 1) begin
                logical_key = CHAIN[127-pixel*8 -: 8] - 65;
                expected = expected_keys[logical_key] ? key_color(logical_key,expected_brightness) : 24'd0;
                if (decoded[383-pixel*24 -: 24] !== expected)
                    $fatal(1,"WS frame%0d chain pixel%0d key%0d %06h expected %06h",frame,pixel,logical_key,decoded[383-pixel*24 -: 24],expected);
            end
            // 383 prior bit periods sum to 478740 ns at 50 MHz.
            if (prior_rose - frame_start !== 478740) $fatal(1,"WS average rate is not 800 kbit/s");
            frame = frame + 1;
        end
    endtask
    initial begin
        repeat (5) @(negedge clk); reset = 0;
        // Changes mid-frame must wait for the next complete snapshot.
        receive_frame(16'h0001,8'ha5,1);
        receive_frame(16'h8000,8'h3c,2);
        receive_frame(16'h0000,8'h00,0);
        // Exercise every logical key independently on the actual wire.
        for (k = 0; k < 16; k = k + 1) begin
            keys = 16'h0001 << k; brightness = 8'ha5;
            receive_frame(16'h0001 << k,8'ha5,0);
        end
        keys = 0; receive_frame(16'h0000,8'ha5,0);
        @(negedge clk); reset = 1; @(negedge clk);
        if (data_out !== 0) $fatal(1,"WS reset output must be low");
        $display("PASS WS2812: all 16 logical keys map to ABCDHGFEIJKLPONM, GRB colors/release, per-frame snapshot, 340/840 ns pulses, exact average 800 kbit/s, 300 us reset");
        $finish;
    end
    initial begin #20_000_000; $fatal(1,"WS timeout"); end
endmodule
