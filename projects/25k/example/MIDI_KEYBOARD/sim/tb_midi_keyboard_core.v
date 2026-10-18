`timescale 1ns/1ps
module tb_midi_keyboard_core;
    reg clk = 0;
    always #5 clk = !clk;
    reg reset = 1, control_reset = 0;
    reg usb_online = 0, ble_online = 0;
    reg key_valid = 0, key_down = 0;
    reg [6:0] key_note = 0, key_velocity = 0;
    wire key_ready;
    wire usb_packet_tx_valid;
    reg usb_packet_tx_ready = 1;
    wire [31:0] usb_packet_tx_data;
    reg usb_packet_rx_valid = 0;
    wire usb_packet_rx_ready;
    reg [31:0] usb_packet_rx_data = 0;
    wire usb_midi_rx_valid;
    reg usb_midi_rx_ready = 0;
    wire [23:0] usb_midi_rx_message;
    wire [1:0] usb_midi_rx_length;
    wire ble_value_tx_valid;
    reg ble_value_tx_ready = 1;
    wire [39:0] ble_value_tx_data;
    wire [2:0] ble_value_tx_length;
    reg ble_value_rx_valid = 0;
    wire ble_value_rx_ready;
    reg [39:0] ble_value_rx_data = 0;
    reg [2:0] ble_value_rx_length = 0;
    wire ble_midi_rx_valid;
    reg ble_midi_rx_ready = 0;
    wire [23:0] ble_midi_rx_message;
    wire [1:0] ble_midi_rx_length;
    wire [12:0] ble_midi_rx_timestamp;
    reg control_rx_valid = 0;
    wire control_rx_ready;
    reg [7:0] control_rx_data = 0;
    wire control_tx_valid;
    reg control_tx_ready = 0;
    wire [7:0] control_tx_data;
    wire [3:0] midi_channel, screen_page;
    wire signed [7:0] transpose;
    wire [15:0] theme_rgb565, clear_rgb565;
    wire screen_update;
    wire [12:0] timestamp_ms;
    wire [7:0] active_notes;
    wire [31:0] status_flags;
    wire usb_queue_full, ble_queue_full;
    wire [15:0] ignored_key_events, unrouted_events, control_errors;
    wire [15:0] usb_tx_errors, usb_rx_errors, ble_tx_errors, ble_rx_errors;
    midi_keyboard_core #(.CLOCK_HZ(4000), .FIFO_DEPTH(2)) dut (.*);

    integer checks = 0;
    task check;
        input ok;
        input [255:0] text;
        begin
            checks = checks + 1;
            if (ok !== 1'b1) $fatal(1, "core check failed: %0s at %0t", text, $time);
        end
    endtask
    reg [31:0] expected_usb [0:255];
    reg [39:0] expected_ble [0:255];
    integer usb_put = 0, usb_get = 0, ble_put = 0, ble_get = 0;
    integer screen_updates = 0;
    always @(posedge clk) begin
        if (!reset) begin
            if (screen_update) screen_updates = screen_updates + 1;
            if (usb_packet_tx_valid && usb_packet_tx_ready) begin
                check(usb_get < usb_put, "unexpected USB output");
                check(usb_packet_tx_data === expected_usb[usb_get], "USB output bytes/order");
                usb_get = usb_get + 1;
            end
            if (ble_value_tx_valid && ble_value_tx_ready) begin
                check(ble_get < ble_put, "unexpected BLE output");
                check(ble_value_tx_length == 5, "BLE output length");
                check(ble_value_tx_data === expected_ble[ble_get], "BLE bytes/timestamp/order");
                ble_get = ble_get + 1;
            end
        end
    end
    task send_key;
        input down;
        input [6:0] note_number;
        input [6:0] velocity;
        input [23:0] message;
        reg [12:0] stamp;
        begin
            @(negedge clk);
            key_valid = 1; key_down = down;
            key_note = note_number; key_velocity = velocity;
            while (!key_ready) @(negedge clk);
            @(posedge clk);
            stamp = timestamp_ms;
            if (usb_online) begin
                expected_usb[usb_put] = {message[7:0], message[15:8], message[23:16],
                                          4'd0, message[23:20]};
                usb_put = usb_put + 1;
            end
            if (ble_online) begin
                expected_ble[ble_put] = {message[7:0], message[15:8], message[23:16],
                                        1'b1, stamp[6:0], 2'b10, stamp[12:7]};
                ble_put = ble_put + 1;
            end
            @(negedge clk); key_valid = 0;
        end
    endtask
    task drain;
        begin
            while (usb_get != usb_put || ble_get != ble_put) @(negedge clk);
            repeat (5) @(negedge clk);
            check(!usb_packet_tx_valid && !ble_value_tx_valid, "outputs drained");
        end
    endtask
    function [15:0] crc_byte;
        input [15:0] crc;
        input [7:0] value;
        reg [15:0] work;
        integer bit_index;
        begin
            work = crc ^ {value, 8'd0};
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                if (work[15]) work = (work << 1) ^ 16'h1021;
                else work = work << 1;
            crc_byte = work;
        end
    endfunction
    function [15:0] frame_crc;
        input [127:0] frame;
        reg [15:0] work;
        integer j;
        begin
            work = 16'hffff;
            for (j = 0; j < 14; j = j + 1) work = crc_byte(work, frame[j*8 +: 8]);
            frame_crc = work;
        end
    endfunction
    integer sequence_number = 0;
    task control_request;
        input [7:0] opcode;
        input [31:0] arg0;
        input [31:0] expected_result;
        reg [127:0] request, response;
        reg [7:0] held_byte;
        integer j;
        begin
            sequence_number = sequence_number + 1;
            request = {16'd0, 32'd0, arg0, sequence_number[15:0], opcode, 8'h01, 16'h4b4d};
            request[127:112] = frame_crc(request);
            for (j = 0; j < 16; j = j + 1) begin
                @(negedge clk);
                control_rx_data = request[j*8 +: 8]; control_rx_valid = 1;
                while (!control_rx_ready) @(negedge clk);
                @(posedge clk);
            end
            @(negedge clk); control_rx_valid = 0;
            while (!control_tx_valid) @(negedge clk);
            held_byte = control_tx_data;
            repeat (4) begin
                @(negedge clk);
                check(control_tx_valid && control_tx_data == held_byte, "control reply stalled");
            end
            response = 0;
            control_tx_ready = 1;
            for (j = 0; j < 16; j = j + 1) begin
                @(posedge clk);
                check(control_tx_valid, "control reply uninterrupted");
                response[j*8 +: 8] = control_tx_data;
            end
            @(negedge clk); control_tx_ready = 0;
            check(response[15:0] == 16'h4b4d && response[23:16] == 1, "control magic/version");
            check(response[31:24] == (opcode | 8'h80), "control response opcode");
            check(response[47:32] == sequence_number[15:0], "control response sequence");
            check(response[79:48] == 0, "control response status");
            check(response[111:80] == expected_result, "control response result");
            check(response[127:112] == frame_crc(response), "control response CRC");
        end
    endtask
    task inject_host_messages;
        begin
            @(negedge clk);
            usb_packet_rx_data = 32'h6407b00b; usb_packet_rx_valid = 1;
            ble_value_rx_data = 40'h6407b0d289; ble_value_rx_length = 5; ble_value_rx_valid = 1;
            check(usb_packet_rx_ready && ble_value_rx_ready, "RX slots initially ready");
            @(posedge clk);
            @(negedge clk); usb_packet_rx_valid = 0; ble_value_rx_valid = 0;
            repeat (5) begin
                check(usb_midi_rx_valid && usb_midi_rx_message == 24'hb00764 &&
                      usb_midi_rx_length == 3, "USB inbound CC stable");
                check(ble_midi_rx_valid && ble_midi_rx_message == 24'hb00764 &&
                      ble_midi_rx_length == 3 && ble_midi_rx_timestamp == 1234,
                      "BLE inbound CC/timestamp stable");
                @(negedge clk);
            end
            usb_midi_rx_ready = 1; ble_midi_rx_ready = 1;
            @(negedge clk); usb_midi_rx_ready = 0; ble_midi_rx_ready = 0;
            check(!usb_midi_rx_valid && !ble_midi_rx_valid, "RX consumed once");
            usb_packet_rx_data = 32'h6407b01b; usb_packet_rx_valid = 1; // unsupported cable
            ble_value_rx_data = 40'h6407b0d209; ble_value_rx_valid = 1; // bad header
            @(negedge clk); usb_packet_rx_valid = 0; ble_value_rx_valid = 0;
            check(usb_rx_errors == 1 && ble_rx_errors == 1, "RX errors counted");
            check(!usb_midi_rx_valid && !ble_midi_rx_valid, "malformed RX discarded");
        end
    endtask

    integer usb_before, ble_before;
    reg [12:0] stamp_before;
    initial begin
        repeat (3) @(negedge clk);
        check(!key_ready, "reset gates key input");
        reset = 0; usb_online = 1; ble_online = 1;
        @(negedge clk);
        check(midi_channel == 0 && transpose == 0 && screen_page == 0 &&
              theme_rgb565 == 16'h07ff && clear_rgb565 == 0, "default settings");
        check(status_flags == 3, "online status");
        send_key(1, 60, 100, 24'h903c64);
        send_key(0, 60, 0, 24'h803c00);
        drain;
        usb_before = usb_get; ble_before = ble_get;
        inject_host_messages;
        repeat (5) @(negedge clk);
        check(usb_get == usb_before && ble_get == ble_before, "host RX not echoed");

        send_key(1, 60, 100, 24'h903c64);
        drain;
        check(active_notes == 1, "held note tracked");
        control_request(8'h10, 5, 5);
        control_request(8'h11, 12, 12);
        check(midi_channel == 5 && transpose == 12, "MIDI controls connected");
        send_key(0, 60, 0, 24'h803c00); // release original mapping
        send_key(1, 61, 90, 24'h95495a);
        send_key(1, 61, 0, 24'h854900); // zero velocity means release
        drain;
        control_request(8'h20, 3, 3);
        control_request(8'h21, 32'hf81f, 32'hf81f);
        control_request(8'h22, 32'h001f, 32'h001f);
        check(screen_page == 3 && theme_rgb565 == 16'hf81f && clear_rgb565 == 16'h001f &&
              screen_updates == 3, "screen settings and one-shot pulses");
        control_request(8'h01, 0, status_flags);

        ble_online = 0;
        repeat (2) @(negedge clk);
        ble_before = ble_get;
        send_key(1, 65, 100, 24'h954d64);
        send_key(0, 65, 0, 24'h854d00);
        drain;
        check(ble_get == ble_before && !ble_value_rx_ready, "offline BLE cannot block USB");

        ble_online = 1; ble_value_tx_ready = 0;
        repeat (2) @(negedge clk);
        send_key(1, 62, 100, 24'h954a64);
        send_key(0, 62, 0, 24'h854a00);
        send_key(1, 63, 100, 24'h954b64);
        send_key(0, 63, 0, 24'h854b00);
        repeat (5) @(negedge clk);
        check(ble_queue_full && !key_ready, "full online BLE backpressures keys");
        control_request(8'h20, 4, 4); // endpoint independent of MIDI congestion
        check(!key_ready && screen_page == 4, "control works while MIDI stalled");
        ble_value_tx_ready = 1;
        drain;

        // Disconnect/reconnect one link while an event is still in the mapper,
        // blocked by the other link. It must not leak into the new session.
        ble_value_tx_ready = 0;
        send_key(1, 68, 100, 24'h955064);
        send_key(1, 69, 100, 24'h955164);
        send_key(1, 70, 100, 24'h955264);
        send_key(1, 71, 100, 24'h955364);
        repeat (8) @(negedge clk);
        check(!key_ready && usb_get == usb_put - 1, "mapper event blocked before disconnect");
        usb_online = 0;
        usb_put = usb_put - 1; // fourth event loses its old USB-session target
        repeat (3) @(negedge clk);
        usb_online = 1;
        repeat (3) @(negedge clk);
        check(!key_ready, "healthy BLE queue still holds event");
        ble_value_tx_ready = 1;
        drain; // all four BLE events, only the first three USB events
        send_key(0, 68, 0, 24'h855000);
        send_key(0, 69, 0, 24'h855100);
        send_key(0, 70, 0, 24'h855200);
        send_key(0, 71, 0, 24'h855300);
        drain;

        usb_packet_tx_ready = 0; ble_value_tx_ready = 0;
        send_key(1, 64, 100, 24'h954c64);
        repeat (6) @(negedge clk);
        check(usb_packet_tx_valid && ble_value_tx_valid, "pending codec slots exist");
        usb_online = 0; ble_online = 0;
        #1;
        check(!usb_packet_tx_valid && !ble_value_tx_valid &&
              !usb_packet_rx_ready && !ble_value_rx_ready, "offline gates ports immediately");
        usb_put = usb_get; ble_put = ble_get; // expected session discard
        repeat (3) @(negedge clk);
        usb_online = 1; ble_online = 1;
        usb_packet_tx_ready = 1; ble_value_tx_ready = 1;
        repeat (5) @(negedge clk);
        check(!usb_packet_tx_valid && !ble_value_tx_valid, "reconnect has no stale note-on");
        check(usb_rx_errors == 0 && ble_rx_errors == 0, "codec errors scoped to link session");
        send_key(0, 64, 0, 24'h854c00);
        drain;

        usb_online = 0; ble_online = 0;
        repeat (2) @(negedge clk);
        send_key(1, 66, 100, 24'h954e64);
        send_key(0, 66, 0, 24'h854e00);
        repeat (5) @(negedge clk);
        check(unrouted_events == 2 && active_notes == 0 && status_flags[6], "offline event policy");
        usb_online = 1; ble_online = 1;
        repeat (2) @(negedge clk);
        send_key(1, 60, 100, 24'h954864);
        drain;
        control_rx_valid = 1; control_rx_data = 8'h4d;
        @(negedge clk); control_rx_data = 8'h4b;
        @(negedge clk); control_rx_valid = 0; control_reset = 1;
        repeat (2) @(negedge clk);
        control_reset = 0;
        @(negedge clk);
        check(midi_channel == 0 && transpose == 0 && screen_page == 0 &&
              active_notes == 1 && control_rx_ready, "control reset preserves held key mapping");
        send_key(0, 60, 0, 24'h854800);
        send_key(1, 60, 100, 24'h903c64);
        send_key(0, 60, 0, 24'h803c00);
        drain;
        check(ignored_key_events == 0 && usb_tx_errors == 0 && ble_tx_errors == 0 &&
              control_errors == 0, "generated messages well formed");

        stamp_before = timestamp_ms;
        repeat (4) @(negedge clk);
        check(timestamp_ms == ((stamp_before + 1) & 13'h1fff), "ms divider period");
        while (timestamp_ms != 8191) @(negedge clk);
        repeat (4) @(negedge clk);
        check(timestamp_ms == 0, "13-bit timestamp wraps");
        reset = 1;
        repeat (2) @(negedge clk);
        check(active_notes == 0 && timestamp_ms == 0 && unrouted_events == 0 &&
              !usb_packet_tx_valid && !ble_value_tx_valid, "global reset clears application");
        $display("PASS tb_midi_keyboard_core: %0d checks, USB=%0d BLE=%0d", checks, usb_get, ble_get);
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "core simulation timeout");
    end
endmodule
