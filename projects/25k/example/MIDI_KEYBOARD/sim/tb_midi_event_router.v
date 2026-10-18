`timescale 1ns/1ps
`default_nettype none

// Three independent reference-model runs exercise depth 1, non-power-of-two 3,
// and the production default 16. Every accepted event is tracked separately
// for USB/BLE, including its timestamp, across stalls and connection changes.
module midi_event_router_checker #(
    parameter integer DEPTH = 16,
    parameter integer RANDOM_SEED = 1
) (output reg done = 0);
    reg clk = 0;
    always #5 clk = !clk;
    reg reset = 1;
    reg in_valid = 0;
    wire in_ready;
    reg [23:0] in_message = 0;
    reg [1:0] in_length = 0;
    reg [12:0] in_timestamp = 0;
    reg [1:0] in_targets = 2'b11;
    reg usb_online = 0, ble_online = 0;
    wire usb_valid, ble_valid;
    reg usb_ready = 0, ble_ready = 0;
    wire [23:0] usb_message, ble_message;
    wire [1:0] usb_length, ble_length;
    wire [12:0] usb_timestamp, ble_timestamp;
    wire usb_full, ble_full;
    wire [15:0] unrouted_events;

    reg [38:0] usb_expected [0:DEPTH-1];
    reg [38:0] ble_expected [0:DEPTH-1];
    integer usb_count = 0, ble_count = 0;
    integer usb_read = 0, usb_write = 0, ble_read = 0, ble_write = 0;
    integer expected_unrouted = 0;
    integer checks = 0, accepted = 0, usb_delivered = 0, ble_delivered = 0;
    integer blocked_cycles = 0, full_replacements = 0, offline_flushes = 0;
    integer i, sequence_number = 0;
    integer seed = RANDOM_SEED;
    reg source_pending = 0;
    reg source_transferred;
    reg [38:0] pending_event;
    reg [1:0] pending_targets;
    reg random_usb_online, random_ble_online;
    reg random_usb_ready, random_ble_ready, random_reset;
    reg [31:0] random_word;

    midi_event_router #(.FIFO_DEPTH(DEPTH)) dut (
        .clk(clk), .reset(reset), .in_valid(in_valid), .in_ready(in_ready),
        .in_message(in_message), .in_length(in_length), .in_timestamp(in_timestamp),
        .in_targets(in_targets),
        .usb_online(usb_online), .ble_online(ble_online),
        .usb_valid(usb_valid), .usb_ready(usb_ready), .usb_message(usb_message),
        .usb_length(usb_length), .usb_timestamp(usb_timestamp),
        .ble_valid(ble_valid), .ble_ready(ble_ready), .ble_message(ble_message),
        .ble_length(ble_length), .ble_timestamp(ble_timestamp),
        .usb_full(usb_full), .ble_full(ble_full), .unrouted_events(unrouted_events)
    );

    function [38:0] event_for;
        input integer number;
        reg [12:0] stamp;
        reg [1:0] length;
        reg [23:0] message;
        begin
            stamp = (number * 373) & 8191; // wraps timestamp many times
            length = (number % 3) + 1;
            message = 24'h800000 | (number & 24'h7fffff);
            event_for = {stamp, length, message};
        end
    endfunction

    task check;
        input condition;
        input [8*100-1:0] description;
        begin
            checks = checks + 1;
            if (condition !== 1'b1) begin
                $display("FAIL: router depth=%0d %0s t=%0t USB=%0d BLE=%0d", DEPTH,
                         description, $time, usb_count, ble_count);
                $fatal(1);
            end
        end
    endtask

    task inspect;
        reg expected_ready;
        begin
            expected_ready = !reset &&
                (!in_targets[0] || !usb_online || usb_count < DEPTH || (usb_count > 0 && usb_ready)) &&
                (!in_targets[1] || !ble_online || ble_count < DEPTH || (ble_count > 0 && ble_ready));
            check(in_ready === expected_ready, "atomic input ready matches available queues");
            check(usb_valid === (!reset && usb_online && usb_count > 0), "USB valid and online gate");
            check(ble_valid === (!reset && ble_online && ble_count > 0), "BLE valid and online gate");
            check(usb_full === (!reset && usb_online && usb_count == DEPTH), "USB full reflects occupancy");
            check(ble_full === (!reset && ble_online && ble_count == DEPTH), "BLE full reflects occupancy");
            check(unrouted_events === expected_unrouted[15:0], "unrouted counter matches accepted events without an effective target");
            if (usb_valid)
                check({usb_timestamp, usb_length, usb_message} === usb_expected[usb_read],
                      "USB exact ordered event with timestamp, stable under stall");
            if (ble_valid)
                check({ble_timestamp, ble_length, ble_message} === ble_expected[ble_read],
                      "BLE exact ordered event with timestamp, stable under stall");
        end
    endtask

    task step_targets;
        input reset_value;
        input usb_online_value;
        input ble_online_value;
        input usb_ready_value;
        input ble_ready_value;
        input source_valid_value;
        input [1:0] source_targets;
        input [38:0] source_event;
        begin
            @(negedge clk);
            reset = reset_value;
            usb_online = usb_online_value; ble_online = ble_online_value;
            usb_ready = usb_ready_value; ble_ready = ble_ready_value;
            in_valid = source_valid_value;
            in_targets = source_targets;
            {in_timestamp, in_length, in_message} = source_event;
            #1;
            // Counter resets at the clock edge, unlike combinational valid gates.
            inspect;
            source_transferred = in_valid && in_ready;
            if (reset) begin
                usb_count = 0; ble_count = 0;
                usb_read = 0; usb_write = 0; ble_read = 0; ble_write = 0;
                expected_unrouted = 0;
            end else begin
                if (in_valid && !in_ready) blocked_cycles = blocked_cycles + 1;
                if (!usb_online) begin
                    if (usb_count != 0) offline_flushes = offline_flushes + 1;
                    usb_count = 0; usb_read = 0; usb_write = 0;
                end else if (usb_count > 0 && usb_ready) begin
                    if (usb_count == DEPTH && source_transferred && in_targets[0])
                        full_replacements = full_replacements + 1;
                    usb_count = usb_count - 1;
                    usb_read = (usb_read + 1) % DEPTH;
                    usb_delivered = usb_delivered + 1;
                end
                if (!ble_online) begin
                    if (ble_count != 0) offline_flushes = offline_flushes + 1;
                    ble_count = 0; ble_read = 0; ble_write = 0;
                end else if (ble_count > 0 && ble_ready) begin
                    if (ble_count == DEPTH && source_transferred && in_targets[1])
                        full_replacements = full_replacements + 1;
                    ble_count = ble_count - 1;
                    ble_read = (ble_read + 1) % DEPTH;
                    ble_delivered = ble_delivered + 1;
                end
                if (source_transferred) begin
                    accepted = accepted + 1;
                    if (usb_online && in_targets[0]) begin
                        check(usb_count < DEPTH, "USB never overflows");
                        usb_expected[usb_write] = source_event;
                        usb_count = usb_count + 1;
                        usb_write = (usb_write + 1) % DEPTH;
                    end
                    if (ble_online && in_targets[1]) begin
                        check(ble_count < DEPTH, "BLE never overflows");
                        ble_expected[ble_write] = source_event;
                        ble_count = ble_count + 1;
                        ble_write = (ble_write + 1) % DEPTH;
                    end
                    if (!(usb_online && in_targets[0]) && !(ble_online && in_targets[1]) &&
                        expected_unrouted < 65535)
                        expected_unrouted = expected_unrouted + 1;
                end
            end
            @(posedge clk); #1;
            inspect;
        end
    endtask

    // Legacy broadcast scenarios use both targets by default.
    task step;
        input reset_value;
        input usb_online_value;
        input ble_online_value;
        input usb_ready_value;
        input ble_ready_value;
        input source_valid_value;
        input [38:0] source_event;
        begin
            step_targets(reset_value, usb_online_value, ble_online_value,
                         usb_ready_value, ble_ready_value, source_valid_value,
                         2'b11, source_event);
        end
    endtask

    initial begin
        step(1, 0, 0, 0, 0, 0, 0);
        step(0, 0, 0, 0, 0, 1, event_for(1));
        step(0, 0, 0, 0, 0, 0, 0);
        check(unrouted_events == 1, "both offline consume and count exactly once");

        // Fill both, drain only USB while BLE is full, and hold one source beat.
        for (i = 0; i < DEPTH; i = i + 1)
            step(0, 1, 1, 0, 0, 1, event_for(10 + i));
        repeat (DEPTH + 3)
            step(0, 1, 1, 1, 0, 1, event_for(100));
        check(usb_count == 0 && ble_count == DEPTH,
              "blocked BLE prevents repeated copies from entering drained USB");
        step(0, 1, 1, 1, 1, 1, event_for(100));
        check(source_transferred, "full BLE pop and atomic broadcast push share one edge");
        repeat (DEPTH + 1) step(0, 1, 1, 1, 1, 0, 0);
        check(usb_count == 0 && ble_count == 0, "all accepted broadcast events drain once");

        // Both queues full: each can replace its head at full throughput.
        for (i = 0; i < DEPTH; i = i + 1)
            step(0, 1, 1, 0, 0, 1, event_for(200 + i));
        repeat (DEPTH + 4) step(0, 1, 1, 1, 1, 1, event_for(300));
        check(usb_count == DEPTH && ble_count == DEPTH, "full queues sustain simultaneous pop and push");

        // Offline queue is flushed and never backpressures the live link.
        step(0, 1, 0, 1, 0, 1, event_for(400));
        check(source_transferred && ble_count == 0, "disconnect flushes BLE and removes its backpressure");
        step(0, 0, 1, 0, 0, 0, 0);
        check(usb_count == 0 && ble_count == 0 && !ble_valid,
              "reconnect does not replay queued events from before disconnect");
        step(0, 0, 1, 0, 1, 1, event_for(401));
        step(0, 0, 1, 0, 1, 0, 0);
        check(ble_count == 0, "new events flow after reconnect");

        // Reset pending events while both sinks stall.
        step(0, 1, 1, 0, 0, 1, event_for(500));
        step(1, 1, 1, 0, 0, 1, event_for(501));
        step(0, 1, 1, 1, 1, 0, 0);
        check(usb_count == 0 && ble_count == 0 && unrouted_events == 0,
              "reset flushes queues and clears offline counter");

        // A mask selects queue recipients independently of online status.
        for (i = 0; i < DEPTH; i = i + 1)
            step_targets(0, 1, 1, 0, 0, 1, 2'b10, event_for(600 + i));
        check(usb_count == 0 && ble_count == DEPTH, "BLE-only mask excludes online USB");
        repeat (DEPTH + 4) begin
            step_targets(0, 1, 1, 1, 0, 1, 2'b01, event_for(650));
            check(source_transferred && ble_count == DEPTH,
                  "excluded full online BLE does not backpressure USB-only input");
        end
        // The USB-only stream left one item; now fill the rest without draining.
        for (i = 1; i < DEPTH; i = i + 1)
            step_targets(0, 1, 1, 0, 0, 1, 2'b01, event_for(700 + i));
        check(usb_count == DEPTH && ble_count == DEPTH, "both online queues full before zero mask");
        step_targets(0, 1, 1, 0, 0, 1, 2'b00, event_for(750));
        check(source_transferred && usb_count == DEPTH && ble_count == DEPTH && unrouted_events == 1,
              "zero mask consumes/counts without touching or waiting on either full queue");
        step_targets(0, 0, 1, 0, 0, 1, 2'b01, event_for(751));
        check(source_transferred && usb_count == 0 && ble_count == DEPTH && unrouted_events == 2,
              "offline selected USB and excluded full BLE have empty effective intersection");
        // Symmetric case: refill USB only, exclude it while sending to BLE.
        for (i = 0; i < DEPTH; i = i + 1)
            step_targets(0, 1, 0, 0, 0, 1, 2'b01, event_for(800 + i));
        step_targets(0, 1, 1, 0, 1, 1, 2'b10, event_for(850));
        check(source_transferred && usb_count == DEPTH && ble_count == 1,
              "excluded full online USB does not backpressure BLE-only input");
        step_targets(0, 1, 0, 0, 0, 1, 2'b10, event_for(851));
        check(source_transferred && usb_count == DEPTH && ble_count == 0 && unrouted_events == 3,
              "offline selected BLE and excluded full USB have empty effective intersection");
        step_targets(0, 1, 1, 0, 0, 0, 2'b00, 0);
        check(usb_count == DEPTH && unrouted_events == 3,
              "changing targets does not flush an online queue or count an idle beat");
        repeat (DEPTH + 2) step(0, 1, 1, 1, 1, 0, 0);
        check(usb_count == 0 && ble_count == 0, "masked traffic drains with exact recipient ordering");

        // Seeded stress respects upstream ready/valid: keep a blocked source
        // beat unchanged, while independently varying sinks and online state.
        source_pending = 0;
        for (i = 0; i < 7000; i = i + 1) begin
            random_word = $random(seed);
            random_usb_online = random_word[1:0] != 0;
            random_ble_online = random_word[3:2] != 0;
            random_usb_ready = random_word[4];
            random_ble_ready = random_word[5];
            random_reset = random_word[15:6] == 0;
            if (!source_pending && random_word[7:6] != 0) begin
                sequence_number = sequence_number + 1;
                pending_event = event_for(sequence_number + 1000);
                pending_targets = random_word[17:16];
                source_pending = 1;
            end
            step_targets(random_reset, random_usb_online, random_ble_online,
                 random_usb_ready, random_ble_ready, source_pending, pending_targets, pending_event);
            if (source_transferred || random_reset) source_pending = 0;
        end
        if (source_pending)
            step_targets(0, 1, 1, 1, 1, 1, pending_targets, pending_event);
        repeat (DEPTH + 2) step(0, 1, 1, 1, 1, 0, 0);
        check(usb_count == 0 && ble_count == 0, "random traffic drains without duplicates or loss");
        check(blocked_cycles > 5 && full_replacements > 0 && offline_flushes > 0,
              "stress covers stalls, full replacement and offline flush");

        // Saturation is exercised by actual accepted traffic, not forced state.
        step(1, 0, 0, 0, 0, 0, 0);
        repeat (65540) step(0, 0, 0, 0, 0, 1, event_for(9000));
        check(unrouted_events == 16'hffff, "unrouted counter saturates without wraparound");
        step(0, 0, 0, 0, 0, 0, 0);
        step(1, 0, 0, 0, 0, 0, 0);
        check(unrouted_events == 0, "reset clears saturated counter");
        $display("PASS: midi_event_router depth=%0d checks=%0d accepted=%0d delivered USB/BLE=%0d/%0d stalls=%0d full_replacements=%0d flushes=%0d",
                 DEPTH, checks, accepted, usb_delivered, ble_delivered,
                 blocked_cycles, full_replacements, offline_flushes);
        done = 1;
    end
endmodule

module tb_midi_event_router;
    wire done1, done3, done16;
    midi_event_router_checker #(.DEPTH(1), .RANDOM_SEED(73)) depth1 (.done(done1));
    midi_event_router_checker #(.DEPTH(3), .RANDOM_SEED(821)) depth3 (.done(done3));
    midi_event_router_checker #(.DEPTH(16), .RANDOM_SEED(1907)) depth16 (.done(done16));
    initial begin
        wait (done1 && done3 && done16);
        $display("PASS: midi_event_router all directed and seeded random scoreboards");
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "midi_event_router simulation timeout");
    end
endmodule

`default_nettype wire
