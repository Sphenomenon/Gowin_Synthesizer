`timescale 1ns/1ps
`default_nettype none
module tb_usb_midi_codec;
    reg clk = 0;
    always #5 clk = !clk;
    reg reset = 1;
    reg tx_valid = 0;
    wire tx_ready;
    reg [23:0] tx_message = 0;
    reg [1:0] tx_length = 0;
    wire packet_tx_valid;
    reg packet_tx_ready = 1;
    wire [31:0] packet_tx_data;
    reg packet_rx_valid = 0;
    wire packet_rx_ready;
    reg [31:0] packet_rx_data = 0;
    wire rx_valid;
    reg rx_ready = 1;
    wire [23:0] rx_message;
    wire [1:0] rx_length;
    wire [15:0] tx_errors, rx_errors;
    integer checks = 0;
    integer packets = 0;
    integer c, family, s, i;
    reg [7:0] status;
    reg [1:0] len;
    reg [3:0] cin;
    reg [31:0] held_packet;
    reg [23:0] held_message;
    reg [1:0] held_length;
    reg [15:0] before_tx_errors, before_rx_errors;

    usb_midi_codec dut (
        .clk(clk), .reset(reset), .tx_valid(tx_valid), .tx_ready(tx_ready),
        .tx_message(tx_message), .tx_length(tx_length),
        .packet_tx_valid(packet_tx_valid), .packet_tx_ready(packet_tx_ready),
        .packet_tx_data(packet_tx_data), .packet_rx_valid(packet_rx_valid),
        .packet_rx_ready(packet_rx_ready), .packet_rx_data(packet_rx_data),
        .rx_valid(rx_valid), .rx_ready(rx_ready), .rx_message(rx_message),
        .rx_length(rx_length), .tx_errors(tx_errors), .rx_errors(rx_errors)
    );

    task check;
        input condition;
        input [8*120-1:0] description;
        begin
            checks = checks + 1;
            if (condition !== 1'b1) begin
                $display("FAIL: %0s at t=%0t", description, $time);
                $fatal(1);
            end
        end
    endtask

    task tick;
        begin @(posedge clk); #1; end
    endtask

    task valid_pair;
        input [23:0] message;
        input [1:0] length;
        input [31:0] packet;
        input [23:0] canonical_message;
        begin
            @(negedge clk);
            tx_message = message; tx_length = length; tx_valid = 1;
            packet_rx_data = packet; packet_rx_valid = 1;
            check(tx_ready && packet_rx_ready, "valid pair accepted");
            tick;
            check(packet_tx_valid && packet_tx_data === packet,
                  "exact USB-MIDI event packet, first byte in bits 7:0");
            check(rx_valid && rx_message === canonical_message && rx_length === length,
                  "exact decoded MIDI message and length");
            packets = packets + 1;
            @(negedge clk); tx_valid = 0; packet_rx_valid = 0;
            tick;
            check(!packet_tx_valid && !rx_valid, "one input beat produces exactly one output");
        end
    endtask

    task invalid_pair;
        input [23:0] message;
        input [1:0] length;
        input [31:0] packet;
        begin
            @(negedge clk);
            before_tx_errors = tx_errors; before_rx_errors = rx_errors;
            tx_message = message; tx_length = length; tx_valid = 1;
            packet_rx_data = packet; packet_rx_valid = 1;
            check(tx_ready && packet_rx_ready, "invalid pair consumed on handshake");
            tick;
            check(!packet_tx_valid && !rx_valid, "invalid input produces no output");
            check(tx_errors == before_tx_errors + 1 && rx_errors == before_rx_errors + 1,
                  "each accepted invalid beat increments each counter once");
            @(negedge clk); tx_valid = 0; packet_rx_valid = 0;
            repeat (2) tick;
            check(tx_errors == before_tx_errors + 1 && rx_errors == before_rx_errors + 1,
                  "idle cycles do not repeat invalid-input errors");
        end
    endtask

    initial begin
        repeat (2) tick;
        check(!tx_ready && !packet_rx_ready, "reset deasserts input ready");
        check(!packet_tx_valid && !rx_valid && tx_errors == 0 && rx_errors == 0,
              "reset clears outputs and counters");
        @(negedge clk); reset = 0;

        // Every channel for all seven channel-voice types. C/D carry two bytes.
        for (family = 8; family <= 14; family = family + 1) begin
            for (c = 0; c < 16; c = c + 1) begin
                status = (family << 4) | c;
                len = ((family == 12) || (family == 13)) ? 2 : 3;
                valid_pair({status, 8'h25, (len == 3) ? 8'h67 : 8'hff}, len,
                           {(len == 3) ? 8'h67 : 8'h00, 8'h25, status, 4'd0, status[7:4]},
                           {status, 8'h25, (len == 3) ? 8'h67 : 8'h00});
            end
        end
        valid_pair(24'hf17f00, 2, 32'h007ff102, 24'hf17f00);
        valid_pair(24'hf2007f, 3, 32'h7f00f203, 24'hf2007f);
        valid_pair(24'hf30100, 2, 32'h0001f302, 24'hf30100);
        valid_pair(24'hf6ffff, 1, 32'h0000f605, 24'hf60000);
        valid_pair(24'hf8ffff, 1, 32'h0000f80f, 24'hf80000);
        valid_pair(24'hfaffff, 1, 32'h0000fa0f, 24'hfa0000);
        valid_pair(24'hfbffff, 1, 32'h0000fb0f, 24'hfb0000);
        valid_pair(24'hfcffff, 1, 32'h0000fc0f, 24'hfc0000);
        valid_pair(24'hfeffff, 1, 32'h0000fe0f, 24'hfe0000);
        valid_pair(24'hffffff, 1, 32'h0000ff0f, 24'hff0000);
        check(tx_errors == 0 && rx_errors == 0, "all supported types leave counters clear");

        // Full-duplex fill; then hold a second upstream beat while both outputs stall.
        @(negedge clk);
        packet_tx_ready = 0; rx_ready = 0;
        tx_valid = 1; tx_message = 24'h903c7f; tx_length = 3;
        packet_rx_valid = 1; packet_rx_data = 32'h01408008;
        tick;
        held_packet = packet_tx_data; held_message = rx_message; held_length = rx_length;
        check(packet_tx_valid && rx_valid, "both output slots filled");
        @(negedge clk);
        tx_message = 24'hb10700; tx_length = 3;
        packet_rx_data = 32'h007fc20c;
        repeat (5) begin
            check(!tx_ready && !packet_rx_ready, "full output slots apply backpressure");
            tick;
            check(packet_tx_valid && packet_tx_data === held_packet,
                  "TX valid and data stable throughout stall");
            check(rx_valid && rx_message === held_message && rx_length === held_length,
                  "RX valid, message and length stable throughout stall");
        end
        @(negedge clk); packet_tx_ready = 1; rx_ready = 1;
        #1;
        check(tx_ready && packet_rx_ready, "ready permits replacement in same cycle");
        tick;
        check(packet_tx_valid && packet_tx_data === 32'h0007b10b,
              "TX pop and push have no bubble or duplicate");
        check(rx_valid && rx_message === 24'hc27f00 && rx_length == 2,
              "RX pop and push have no bubble or duplicate");
        @(negedge clk); tx_valid = 0; packet_rx_valid = 0;
        tick;
        check(!packet_tx_valid && !rx_valid, "replacement beats drain once");

        // One stalled direction must not stop the opposite direction.
        @(negedge clk);
        packet_tx_ready = 0; tx_valid = 1; tx_message = 24'h903c01; tx_length = 3;
        tick;
        @(negedge clk); tx_valid = 0; packet_rx_valid = 1; packet_rx_data = 32'h0000f80f;
        repeat (4) begin
            check(!tx_ready && packet_rx_ready, "RX independent of stalled TX");
            tick;
            check(rx_valid && rx_message == 24'hf80000, "RX flows while TX stalled");
        end
        @(negedge clk); packet_rx_valid = 0; packet_tx_ready = 1;
        tick;
        @(negedge clk);
        rx_ready = 0; packet_rx_valid = 1; packet_rx_data = 32'h0000fa0f;
        tick;
        @(negedge clk); packet_rx_valid = 0; tx_valid = 1; tx_message = 24'hfb0000; tx_length = 1;
        repeat (4) begin
            check(tx_ready && !packet_rx_ready, "TX independent of stalled RX");
            tick;
            check(packet_tx_valid && packet_tx_data == 32'h0000fb0f, "TX flows while RX stalled");
        end
        @(negedge clk); tx_valid = 0; rx_ready = 1;
        tick;

        // Reject every unsupported status, including running-status data bytes.
        for (s = 0; s < 256; s = s + 1) begin
            if ((s < 128) || s == 240 || s == 244 || s == 245 ||
                s == 247 || s == 249 || s == 253) begin
                status = s;
                invalid_pair({status, 16'd0}, 1, {16'd0, status, 8'h0f});
            end
        end
        invalid_pair(24'h903c7f, 0, 32'h7f3c9008); // bad length / CIN
        invalid_pair(24'h903c7f, 1, 32'h7f3c9019); // bad length / cable
        invalid_pair(24'h903c7f, 2, 32'h7fbc9009); // bad length / data1 MSB
        invalid_pair(24'h90bc7f, 3, 32'hff3c9009); // data1 / data2 MSB
        invalid_pair(24'h903cff, 3, 32'h017fc00c); // data2 / 2-byte padding
        invalid_pair(24'hc00100, 3, 32'h0001f80f); // 2-byte length / 1-byte padding1
        invalid_pair(24'hd08000, 2, 32'h0100f80f); // 2-byte MSB / 1-byte padding2
        invalid_pair(24'hf18000, 2, 32'h0000f601); // system data / unsupported CIN
        invalid_pair(24'hf20180, 3, 32'h0000f602); // system data / CIN mismatch
        invalid_pair(24'hf60000, 2, 32'h0000f70f); // system length / SysEx end

        // Invalid input behind a stalled valid output waits, then counts once.
        @(negedge clk);
        packet_tx_ready = 0; rx_ready = 0;
        tx_valid = 1; tx_message = 24'h903c7f; tx_length = 3;
        packet_rx_valid = 1; packet_rx_data = 32'h7f3c9009;
        tick;
        @(negedge clk); tx_message = 0; tx_length = 0; packet_rx_data = 0;
        before_tx_errors = tx_errors; before_rx_errors = rx_errors;
        repeat (3) tick;
        check(tx_errors == before_tx_errors && rx_errors == before_rx_errors,
              "unaccepted invalid inputs do not increment counters");
        @(negedge clk); packet_tx_ready = 1; rx_ready = 1;
        tick;
        check(!packet_tx_valid && !rx_valid && tx_errors == before_tx_errors + 1 &&
              rx_errors == before_rx_errors + 1, "invalid replacement consumed exactly once");
        @(negedge clk); tx_valid = 0; packet_rx_valid = 0;
        tick;

        // Counter saturation through real accepted invalid traffic, without forcing DUT state.
        @(negedge clk); tx_valid = 1; tx_message = 0; tx_length = 0;
        packet_rx_valid = 1; packet_rx_data = 0;
        repeat (65540) tick;
        check(tx_errors == 16'hffff && rx_errors == 16'hffff,
              "error counters saturate at 65535 without wraparound");
        @(negedge clk); tx_valid = 0; packet_rx_valid = 0;
        tick;

        // Reset clears saturated counters and both pending, stalled outputs.
        @(negedge clk); packet_tx_ready = 0; rx_ready = 0;
        tx_valid = 1; tx_message = 24'h903c7f; tx_length = 3;
        packet_rx_valid = 1; packet_rx_data = 32'h7f3c9009;
        tick;
        check(packet_tx_valid && rx_valid, "pending data before reset");
        @(negedge clk); reset = 1;
        tick;
        check(!packet_tx_valid && !rx_valid && packet_tx_data == 0 &&
              rx_message == 0 && rx_length == 0 && tx_errors == 0 && rx_errors == 0,
              "reset flushes pending data and saturated counters");
        @(negedge clk); tx_valid = 0; packet_rx_valid = 0; reset = 0;
        packet_tx_ready = 1; rx_ready = 1;
        tick;
        valid_pair(24'h804000, 3, 32'h00408008, 24'h804000);
        $display("PASS: usb_midi_codec %0d checks, %0d exact valid pairs, all statuses, backpressure, reset and saturation", checks, packets);
        $finish;
    end

    initial begin
        #10000000;
        $fatal(1, "usb_midi_codec simulation timeout");
    end
endmodule
`default_nettype wire
