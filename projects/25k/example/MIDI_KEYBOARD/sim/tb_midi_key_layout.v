`timescale 1ns/1ps
`default_nettype none
module tb_midi_key_layout;
    reg clk = 0;
    always #10 clk = ~clk;
    reg reset = 1;
    reg [15:0] raw_keys = 0;
    wire [15:0] key_bitmap;
    wire event_valid;
    wire [23:0] event_message;
    wire [1:0] event_length, event_targets;
    wire [15:0] active_keys;
    wire panic_busy;
    wire [31:0] emitted_events;
    integer raw_for_key [0:15];
    reg [15:0] expected_bitmap;
    reg [23:0] messages [0:255];
    integer events = 0;
    integer pattern, key, mark;

    midi_key_layout dut (
        .raw_keys(raw_keys),
        .key_bitmap(key_bitmap)
    );
    midi_performance performance (
        .clk(clk), .reset(reset), .key_bitmap(key_bitmap), .keypad_ready(1'b1),
        .slider_valid(1'b0), .slider_touch(1'b0), .slider_position(8'd0),
        .enc1_step(1'b0), .enc1_press(1'b0),
        .enc2_step(1'b0), .enc2_press(1'b0),
        .enc1_direction(2'sd1), .enc2_direction(2'sd1),
        .config_write(1'b0), .config_opcode(8'd0), .config_value(32'd0),
        .online(2'b01), .timestamp_ms(13'd0),
        .event_valid(event_valid), .event_ready(1'b1),
        .event_message(event_message), .event_length(event_length),
        .event_targets(event_targets), .active_keys(active_keys),
        .panic_busy(panic_busy), .emitted_events(emitted_events)
    );

    always @(posedge clk) begin
        if (!reset && event_valid) begin
            if (events >= 256) $fatal(1, "Unexpected event overflow");
            if (event_length !== 2'd3 || event_targets !== 2'b01)
                $fatal(1, "Mapped MIDI event length/target incorrect");
            messages[events] = event_message;
            events = events + 1;
        end
    end

    task drain;
        integer quiet, limit;
        begin : draining
            quiet = 0;
            for (limit = 0; limit < 1000; limit = limit + 1) begin
                @(negedge clk);
                if (!event_valid && !panic_busy) quiet = quiet + 1;
                else quiet = 0;
                if (quiet == 12) disable draining;
            end
            $fatal(1, "Mapped MIDI event stream did not drain");
        end
    endtask

    task check_event;
        input integer index;
        input [7:0] status;
        input integer logical_key;
        input [7:0] velocity;
        reg [7:0] note;
        begin
            note = 48 + logical_key;
            if (messages[index] !== {status, note, velocity})
                $fatal(1, "Key %0d event %0d got %06h expected %06h",
                    logical_key, index, messages[index], {status, note, velocity});
        end
    endtask

    initial begin
        // Independent oracle copied in A--P order from the measured board
        // mapping. No DUT constants, functions or internal signals are used.
        raw_for_key[0] = 5;   raw_for_key[1] = 3;
        raw_for_key[2] = 1;   raw_for_key[3] = 7;
        raw_for_key[4] = 13;  raw_for_key[5] = 11;
        raw_for_key[6] = 9;   raw_for_key[7] = 15;
        raw_for_key[8] = 4;   raw_for_key[9] = 2;
        raw_for_key[10] = 0;  raw_for_key[11] = 6;
        raw_for_key[12] = 12; raw_for_key[13] = 10;
        raw_for_key[14] = 8;  raw_for_key[15] = 14;

        // All combinations include idle/fault-clear, every chord and all-on.
        for (pattern = 0; pattern < 65536; pattern = pattern + 1) begin
            raw_keys = pattern;
            expected_bitmap = 0;
            for (key = 0; key < 16; key = key + 1)
                expected_bitmap[key] = raw_keys[raw_for_key[key]];
            #1;
            if (key_bitmap !== expected_bitmap)
                $fatal(1, "Raw %04h maps to %04h expected %04h",
                    raw_keys, key_bitmap, expected_bitmap);
        end

        raw_keys = 0;
        repeat (3) @(negedge clk);
        reset = 0;
        drain();
        for (key = 0; key < 16; key = key + 1) begin
            mark = events;
            raw_keys = 16'h0001 << raw_for_key[key];
            drain();
            if (active_keys !== (16'h0001 << key) || events != mark + 1)
                $fatal(1, "Physical key %0d did not yield one logical Note On", key);
            check_event(mark, 8'h90, key, 8'd100);

            mark = events;
            raw_keys = 0;
            drain();
            if (active_keys !== 0 || events != mark + 1)
                $fatal(1, "Physical key %0d did not yield one Note Off", key);
            check_event(mark, 8'h80, key, 8'd0);
        end

        mark = events;
        raw_keys = 16'hffff;
        drain();
        if (active_keys !== 16'hffff || events != mark + 16)
            $fatal(1, "Sixteen-key mapped chord lost Note Ons");
        for (key = 0; key < 16; key = key + 1)
            check_event(mark + key, 8'h90, key, 8'd100);
        mark = events;
        raw_keys = 0;
        drain();
        if (active_keys !== 0 || events != mark + 16)
            $fatal(1, "Sixteen-key mapped chord lost Note Offs");
        for (key = 0; key < 16; key = key + 1)
            check_event(mark + key, 8'h80, key, 8'd0);
        if (emitted_events !== events)
            $fatal(1, "Mapped MIDI event accounting disagrees");
        $display("PASS key layout: 65536 snapshots; A--P single-key Note On 48+i/Note Off; 16-key chord and release");
        $finish;
    end
    initial begin
        #500000;
        $fatal(1, "Key layout test timeout");
    end
endmodule
`default_nettype wire
