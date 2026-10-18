`timescale 1ns/1ps
module tb_keyboard_event_mapper;
    reg clk = 1'b0;
    always #5 clk = !clk;
    reg reset = 1'b1;
    reg key_valid = 1'b0;
    wire key_ready;
    reg key_down = 1'b0;
    reg [6:0] key_note = 7'd0;
    reg [6:0] key_velocity = 7'd0;
    reg [3:0] midi_channel = 4'd0;
    reg signed [7:0] transpose = 8'sd0;
    reg [12:0] timestamp_ms = 13'd0;
    wire event_valid;
    reg event_ready = 1'b1;
    wire [23:0] event_message;
    wire [1:0] event_length;
    wire [12:0] event_timestamp;
    wire [7:0] active_notes;
    wire [15:0] ignored_events;

    keyboard_event_mapper dut (
        .clk(clk), .reset(reset), .key_valid(key_valid), .key_ready(key_ready),
        .key_down(key_down), .key_note(key_note), .key_velocity(key_velocity),
        .midi_channel(midi_channel), .transpose(transpose), .timestamp_ms(timestamp_ms),
        .event_valid(event_valid), .event_ready(event_ready), .event_message(event_message),
        .event_length(event_length), .event_timestamp(event_timestamp),
        .active_notes(active_notes), .ignored_events(ignored_events)
    );

    integer model_active [0:127];
    integer model_note [0:127];
    integer model_channel [0:127];
    integer model_count = 0;
    integer model_ignored = 0;
    reg model_valid = 1'b0;
    reg [23:0] model_message = 24'd0;
    reg [1:0] model_length = 2'd0;
    reg [12:0] model_timestamp = 13'd0;
    integer checks = 0;
    integer accepted_keys = 0;
    integer emitted_events = 0;
    integer delivered_events = 0;
    integer stalled_cycles = 0;
    integer replacements = 0;
    integer map_integer;
    integer transpose_integer;
    integer i;
    integer n;
    integer random_seed = 32'h37296a11;
    reg [31:0] random_word;
    reg expected_ready;
    reg was_valid;
    reg last_key_accepted = 1'b0;

    task check;
        input condition;
        input [767:0] label;
        begin
            checks = checks + 1;
            if (condition !== 1'b1)
                $fatal(1, "%0s (check %0d, t=%0t)", label, checks, $time);
        end
    endtask

    // Independent integer reference model checks every clock, including stalls,
    // ignored input transfers, output replacement and reset with pending work.
    always @(posedge clk) begin
        expected_ready = !reset && (!model_valid || event_ready);
        check(key_ready === expected_ready, "input ready/reset gating agrees with reference");
        last_key_accepted = key_valid && expected_ready;
        was_valid = model_valid;
        if (reset) begin
            for (i = 0; i < 128; i = i + 1) model_active[i] = 0;
            model_count = 0;
            model_ignored = 0;
            model_valid = 1'b0;
            model_message = 24'd0;
            model_length = 2'd0;
            model_timestamp = 13'd0;
        end else begin
            if (model_valid && event_ready) delivered_events = delivered_events + 1;
            if (model_valid && !event_ready) stalled_cycles = stalled_cycles + 1;
            if (expected_ready) begin
                model_valid = 1'b0;
                if (key_valid) begin
                    accepted_keys = accepted_keys + 1;
                    if (!key_down || key_velocity == 0) begin
                        if (model_active[key_note] != 0) begin
                            model_message = (128 + model_channel[key_note]) * 65536 +
                                            model_note[key_note] * 256;
                            model_active[key_note] = 0;
                            model_count = model_count - 1;
                            model_valid = 1'b1;
                        end else if (model_ignored < 65535) model_ignored = model_ignored + 1;
                    end else begin
                        transpose_integer = $signed(transpose);
                        map_integer = key_note + transpose_integer;
                        if (model_active[key_note] == 0 && transpose_integer >= -48 &&
                            transpose_integer <= 48 && map_integer >= 0 && map_integer <= 127) begin
                            model_note[key_note] = map_integer;
                            model_channel[key_note] = midi_channel;
                            model_active[key_note] = 1;
                            model_count = model_count + 1;
                            model_message = (144 + midi_channel) * 65536 + map_integer * 256 + key_velocity;
                            model_valid = 1'b1;
                        end else if (model_ignored < 65535) model_ignored = model_ignored + 1;
                    end
                    if (model_valid) begin
                        model_length = 3;
                        model_timestamp = timestamp_ms;
                        emitted_events = emitted_events + 1;
                        if (was_valid) replacements = replacements + 1;
                    end
                end
            end
        end
        #1;
        check(event_valid === model_valid, "output valid agrees with reference");
        check(event_message === model_message && event_length === model_length &&
              event_timestamp === model_timestamp, "payload/length/timestamp stable or correctly replaced");
        check(active_notes == model_count, "accepted active-key count agrees with reference");
        check(ignored_events == model_ignored, "ignored transfer saturation agrees with reference");
        check(active_notes <= 128, "active count bounded by physical-key count");
    end

    task tick;
        begin @(posedge clk); #2; end
    endtask

    task drive;
        input valid;
        input down;
        input [6:0] note_id;
        input [6:0] velocity;
        input [3:0] channel;
        input signed [7:0] shift;
        input [12:0] stamp;
        input ready;
        begin
            @(negedge clk);
            key_valid = valid; key_down = down; key_note = note_id; key_velocity = velocity;
            midi_channel = channel; transpose = shift; timestamp_ms = stamp; event_ready = ready;
            tick;
        end
    endtask

    task clear_state;
        begin
            @(negedge clk);
            reset = 1'b1;
            key_valid = 1'b1; key_down = 1'b1; key_note = 127; key_velocity = 127;
            midi_channel = 15; transpose = 0; timestamp_ms = 8191;
            #1; check(!key_ready, "reset immediately gates input ready before next clock");
            tick;
            check(!event_valid && event_message == 0 && event_length == 0 &&
                  event_timestamp == 0 && active_notes == 0 && ignored_events == 0,
                  "reset flushes output, timestamps, active keys and ignored counter");
            @(negedge clk); reset = 1'b0; key_valid = 1'b0; event_ready = 1'b1;
            tick;
        end
    endtask

    initial begin
        tick; tick;
        clear_state;

        // Literal 0/127 notes, channel 0/15, velocities 1/127 and timestamp wrap.
        drive(1, 1, 0, 1, 15, 0, 8191, 1);
        check(event_message == 24'h9f0001 && event_timestamp == 8191 && active_notes == 1,
              "lowest note/channel15 exact NoteOn");
        drive(0, 0, 0, 127, 0, 127, 0, 1); // config changes while held
        drive(1, 0, 0, 127, 0, 127, 0, 1);
        check(event_message == 24'h8f0000 && event_timestamp == 0 && active_notes == 0,
              "release preserves original channel despite invalid current config");
        drive(1, 1, 127, 127, 0, 0, 0, 1);
        check(event_message == 24'h907f7f, "highest note/velocity exact NoteOn");
        drive(1, 1, 127, 0, 15, -128, 1, 1);
        check(event_message == 24'h807f00 && active_notes == 0,
              "zero-velocity down releases original note and channel");

        // Both allowed transpose endpoints reach exact output-note endpoints.
        drive(1, 1, 48, 64, 3, -48, 2, 1);
        check(event_message == 24'h930040, "negative transpose endpoint maps to zero");
        drive(1, 0, 48, 99, 8, 48, 3, 1);
        check(event_message == 24'h830000, "negative endpoint release uses saved mapping");
        drive(1, 1, 79, 64, 4, 48, 4, 1);
        check(event_message == 24'h947f40, "positive transpose endpoint maps to 127");
        drive(1, 0, 79, 99, 9, -48, 5, 1);
        check(event_message == 24'h847f00, "positive endpoint release uses saved mapping");

        drive(1, 1, 0, 64, 0, -1, 6, 1);
        drive(1, 1, 127, 64, 0, 1, 7, 1);
        drive(1, 1, 60, 64, 0, 49, 8, 1);
        drive(1, 1, 60, 64, 0, -49, 9, 1);
        drive(1, 1, 60, 64, 0, 127, 10, 1);
        drive(1, 1, 60, 64, 0, -128, 11, 1);
        check(active_notes == 0 && ignored_events == 6, "out-of-range shifts and notes rejected");

        drive(1, 1, 60, 80, 2, 12, 12, 1);
        check(event_message == 24'h924850 && active_notes == 1, "press captures pitch/channel");
        drive(1, 1, 60, 127, 7, -12, 13, 1);
        check(!event_valid && active_notes == 1 && ignored_events == 7, "duplicate press ignored");
        drive(1, 1, 60, 0, 7, -12, 14, 1);
        check(event_message == 24'h824800 && active_notes == 0, "zero velocity closes original mapped note");
        drive(1, 0, 60, 100, 0, 0, 15, 1);
        drive(1, 1, 60, 0, 0, 0, 16, 1);
        check(ignored_events == 9, "inactive release and inactive zero-velocity press ignored");

        // The identity is the physical key, so two keys may map to the same pitch.
        drive(1, 1, 60, 99, 3, 12, 17, 1);
        drive(1, 1, 72, 99, 3, 0, 18, 1);
        check(active_notes == 2, "aliased mapped notes retain distinct physical identities");
        drive(1, 0, 60, 99, 0, 0, 19, 1);
        check(active_notes == 1 && event_message == 24'h834800, "first alias releases independently");
        drive(1, 0, 72, 99, 0, 0, 20, 1);
        check(active_notes == 0 && event_message == 24'h834800, "second alias releases independently");

        // Full 128-key state tests high-ID indexing and 8-bit active count (128).
        for (n = 0; n < 128; n = n + 1)
            drive(1, 1, n, 1 + n % 127, n % 16, 0, n, 1);
        check(active_notes == 128, "all 128 physical keys may be active");
        for (n = 127; n >= 0; n = n - 1)
            drive(1, n % 2, n, 0, 15 - n % 16, 127, 8191 - n, 1);
        check(active_notes == 0, "128 saved mappings release despite invalid changed transpose");
        drive(0, 0, 0, 0, 0, 0, 0, 1);

        // Output stall holds the first event; release timestamp is captured only
        // when that release is eventually accepted, never from the earlier press.
        drive(1, 1, 30, 64, 1, 2, 8191, 0);
        check(event_message == 24'h912040 && event_timestamp == 8191 && active_notes == 1,
              "backpressured NoteOn still updates accepted active count");
        for (n = 0; n < 8; n = n + 1)
            drive(1, 0, 30, 99, 15, 127, n, 0);
        check(event_message == 24'h912040 && event_timestamp == 8191 && active_notes == 1,
              "stalled event stable while waiting release/config/timestamp vary");
        drive(1, 0, 30, 99, 15, 127, 123, 1);
        check(event_message == 24'h812000 && event_timestamp == 123 && active_notes == 0,
              "same-cycle pop/release replacement captures release handshake timestamp");
        drive(1, 1, 100, 55, 4, 0, 124, 0);
        // Previous release is still pending, so the new press has not been accepted.
        check(active_notes == 0 && !key_ready, "full slot blocks new physical event");
        drive(1, 1, 100, 55, 4, 0, 124, 1);
        drive(1, 1, 100, 55, 9, -12, 125, 0);
        for (n = 0; n < 5; n = n + 1)
            drive(1, 1, 100, 55, 9, -12, 125, 0);
        drive(1, 1, 100, 55, 9, -12, 125, 1);
        check(!event_valid && active_notes == 1 && ignored_events == 10,
              "stalled duplicate only increments ignored count at one accepted transfer");
        drive(0, 0, 0, 0, 0, 0, 0, 1);
        check(ignored_events == 10, "duplicate does not count again while valid is low");

        clear_state;
        // Real transfers reach saturation without hierarchical force/set.
        drive(1, 0, 0, 64, 0, 0, 0, 1);
        repeat (65540) tick;
        check(ignored_events == 16'hffff && active_notes == 0 && !event_valid,
              "ignored input counter saturates across real accepted transfers");
        drive(1, 1, 0, 1, 5, 0, 1, 1);
        drive(1, 1, 0, 1, 5, 0, 2, 1);
        check(ignored_events == 16'hffff && active_notes == 1, "saturation does not inhibit valid note processing");
        drive(1, 0, 0, 127, 0, -128, 3, 1);
        check(event_message == 24'h850000 && active_notes == 0, "release still works after error saturation");

        drive(1, 1, 77, 1, 8, 4, 77, 1);
        drive(0, 0, 0, 0, 0, 0, 0, 0);
        check(event_valid && active_notes == 1, "reset test starts with held note and stalled event");
        clear_state;
        drive(1, 0, 77, 0, 8, 4, 78, 1);
        check(!event_valid && ignored_events == 1, "reset discards old active-key mask despite stale array contents");
        drive(1, 1, 77, 2, 1, -4, 79, 1);
        drive(1, 0, 77, 127, 8, 4, 80, 1);
        check(event_message == 24'h814900, "new press overwrites stale saved mapping after reset");

        // Reproducible randomized input with a source that holds its pending key
        // until acceptance. Downstream backpressure and config cover all bits.
        for (n = 0; n < 15000; n = n + 1) begin
            @(negedge clk);
            random_word = $random(random_seed);
            event_ready = random_word[0] || random_word[1];
            if (!key_valid || last_key_accepted) begin
                key_valid = random_word[2] || random_word[3];
                key_down = random_word[4];
                key_note = random_word[11:5];
                key_velocity = random_word[13:12] == 0 ? 0 : random_word[20:14] | 7'd1;
                midi_channel = random_word[24:21];
                case (random_word[26:25])
                    0: transpose = 0;
                    1: transpose = 12;
                    2: transpose = -12;
                    3: transpose = random_word[31:24];
                endcase
                timestamp_ms = n;
            end
            tick;
        end
        // Complete any source transfer held at the end of random generation.
        if (key_valid && !last_key_accepted) begin
            @(negedge clk); event_ready = 1'b1;
            tick;
        end
        drive(0, 0, 0, 0, 0, 0, 0, 1);
        for (n = 0; n < 128; n = n + 1)
            drive(1, 0, n, 127, 15, 127, n, 1);
        drive(0, 0, 0, 0, 0, 0, 0, 1);
        check(active_notes == 0 && !event_valid, "all random held notes close with changed config");
        check(stalled_cycles > 100 && replacements > 100 && emitted_events > 1000,
              "random/direct coverage includes substantial stalls replacements and valid events");
        $display("PASS tb_keyboard_event_mapper: %0d checks, %0d accepted keys, %0d emitted, %0d delivered, %0d stalls, %0d replacements",
                 checks, accepted_keys, emitted_events, delivered_events, stalled_cycles, replacements);
        $finish;
    end

    initial begin
        #3000000;
        $fatal(1, "tb_keyboard_event_mapper timeout");
    end
endmodule
