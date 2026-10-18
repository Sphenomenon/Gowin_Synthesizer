`timescale 1ns/1ps
module tb_ble_midi_codec;
    reg clk = 1'b0;
    always #5 clk = !clk;
    reg reset = 1'b1;
    reg tx_valid = 1'b0;
    wire tx_ready;
    reg [23:0] tx_message = 24'd0;
    reg [1:0] tx_length = 2'd0;
    reg [12:0] timestamp_ms = 13'd0;
    wire value_tx_valid;
    reg value_tx_ready = 1'b1;
    wire [39:0] value_tx_data;
    wire [2:0] value_tx_length;
    reg value_rx_valid = 1'b0;
    wire value_rx_ready;
    reg [39:0] value_rx_data = 40'd0;
    reg [2:0] value_rx_length = 3'd0;
    wire rx_valid;
    reg rx_ready = 1'b1;
    wire [23:0] rx_message;
    wire [1:0] rx_length;
    wire [12:0] rx_timestamp;
    wire [15:0] tx_errors;
    wire [15:0] rx_errors;
    integer checks = 0;
    integer expected_tx_errors = 0;
    integer expected_rx_errors = 0;
    integer status;
    integer n;
    reg [1:0] length;
    reg [7:0] sys_status [0:9];
    reg [39:0] expected_value;
    reg [39:0] held_value;
    reg [23:0] held_message;

    ble_midi_codec dut (
        .clk(clk), .reset(reset),
        .tx_valid(tx_valid), .tx_ready(tx_ready),
        .tx_message(tx_message), .tx_length(tx_length),
        .timestamp_ms(timestamp_ms),
        .value_tx_valid(value_tx_valid), .value_tx_ready(value_tx_ready),
        .value_tx_data(value_tx_data), .value_tx_length(value_tx_length),
        .value_rx_valid(value_rx_valid), .value_rx_ready(value_rx_ready),
        .value_rx_data(value_rx_data), .value_rx_length(value_rx_length),
        .rx_valid(rx_valid), .rx_ready(rx_ready), .rx_message(rx_message),
        .rx_length(rx_length), .rx_timestamp(rx_timestamp),
        .tx_errors(tx_errors), .rx_errors(rx_errors)
    );

    task tick;
        begin @(posedge clk); #1; end
    endtask

    task check;
        input condition;
        input [767:0] label;
        begin
            checks = checks + 1;
            if (condition !== 1'b1) $fatal(1, "%0s (check %0d, t=%0t)", label, checks, $time);
        end
    endtask

    function [39:0] pack_value;
        input [23:0] message;
        input [1:0] midi_length;
        input [12:0] stamp;
        begin
            pack_value = {
                (midi_length == 3 ? message[7:0] : 8'd0),
                (midi_length >= 2 ? message[15:8] : 8'd0),
                message[23:16], {1'b1, stamp[6:0]}, {2'b10, stamp[12:7]}
            };
        end
    endfunction

    task good_tx;
        input [23:0] message;
        input [1:0] midi_length;
        input [12:0] stamp;
        input [39:0] encoded;
        begin
            @(negedge clk);
            tx_valid = 1'b1;
            tx_message = message;
            tx_length = midi_length;
            timestamp_ms = stamp;
            value_tx_ready = 1'b0;
            check(tx_ready, "empty TX slot ready");
            tick;
            check(value_tx_valid && value_tx_data === encoded &&
                  value_tx_length == midi_length + 3'd2, "TX exact BLE bytes and length");
            check(tx_errors == expected_tx_errors, "valid TX leaves error count");
            @(negedge clk); tx_valid = 1'b0; value_tx_ready = 1'b1;
            tick;
            check(!value_tx_valid, "TX output consumed once");
        end
    endtask

    task good_rx;
        input [39:0] encoded;
        input [2:0] encoded_length;
        input [23:0] message;
        input [1:0] midi_length;
        input [12:0] stamp;
        begin
            @(negedge clk);
            value_rx_valid = 1'b1;
            value_rx_data = encoded;
            value_rx_length = encoded_length;
            rx_ready = 1'b0;
            check(value_rx_ready, "empty RX slot ready");
            tick;
            check(rx_valid && rx_message === message && rx_length == midi_length &&
                  rx_timestamp == stamp, "RX exact decoded message and timestamp");
            check(rx_errors == expected_rx_errors, "valid RX leaves error count");
            @(negedge clk); value_rx_valid = 1'b0; rx_ready = 1'b1;
            tick;
            check(!rx_valid, "RX output consumed once");
        end
    endtask

    task bad_tx;
        input [23:0] message;
        input [1:0] midi_length;
        begin
            @(negedge clk);
            tx_valid = 1'b1; tx_message = message; tx_length = midi_length;
            value_tx_ready = 1'b1;
            check(tx_ready, "invalid TX accepted by available slot");
            tick;
            expected_tx_errors = expected_tx_errors + 1;
            check(!value_tx_valid && tx_errors == expected_tx_errors, "invalid TX counted once without output");
            @(negedge clk); tx_valid = 1'b0;
            tick;
            check(tx_errors == expected_tx_errors, "idle TX does not repeat invalid event");
        end
    endtask

    task bad_rx;
        input [39:0] encoded;
        input [2:0] encoded_length;
        begin
            @(negedge clk);
            value_rx_valid = 1'b1; value_rx_data = encoded; value_rx_length = encoded_length;
            rx_ready = 1'b1;
            check(value_rx_ready, "invalid RX accepted by available slot");
            tick;
            expected_rx_errors = expected_rx_errors + 1;
            check(!rx_valid && rx_errors == expected_rx_errors, "invalid RX counted once without output");
            @(negedge clk); value_rx_valid = 1'b0;
            tick;
            check(rx_errors == expected_rx_errors, "idle RX does not repeat invalid event");
        end
    endtask

    initial begin
        sys_status[0] = 8'hf1; sys_status[1] = 8'hf2; sys_status[2] = 8'hf3;
        sys_status[3] = 8'hf6; sys_status[4] = 8'hf8; sys_status[5] = 8'hfa;
        sys_status[6] = 8'hfb; sys_status[7] = 8'hfc; sys_status[8] = 8'hfe;
        sys_status[9] = 8'hff;
        tick; tick;
        check(!value_tx_valid && !rx_valid && tx_ready && value_rx_ready &&
              tx_errors == 0 && rx_errors == 0, "reset clears both directions");
        @(negedge clk); reset = 1'b0;

        // Literal wire values independently establish byte order and wrap.
        good_tx(24'h903c7f, 3, 8191, 40'h7f3c90ffbf);
        good_tx(24'h903c7f, 3, 0, 40'h7f3c908080);
        good_tx(24'hc207ff, 2, 128, 40'h0007c28081);
        good_tx(24'hf8ffff, 1, 127, 40'h0000f8ff80);
        good_rx(40'h7f3c90ffbf, 5, 24'h903c7f, 3, 8191);
        good_rx(40'h7f3c908080, 5, 24'h903c7f, 3, 0);
        good_rx(40'hff07c28081, 4, 24'hc20700, 2, 128); // ignored padding
        good_rx(40'hfffff8ff80, 3, 24'hf80000, 1, 127);

        // Every channel status, including 2-byte Cn/Dn, and supported system status.
        for (status = 8'h80; status <= 8'hef; status = status + 1) begin
            length = ((status >> 4) == 12 || (status >> 4) == 13) ? 2 : 3;
            expected_value = pack_value({status[7:0], 8'h12, 8'h34}, length, status * 17);
            good_tx({status[7:0], 8'h12, 8'h34}, length, status * 17, expected_value);
            good_rx(expected_value, length + 3'd2,
                    {status[7:0], 8'h12, (length == 3 ? 8'h34 : 8'h00)}, length, status * 17);
        end
        for (n = 0; n < 10; n = n + 1) begin
            length = sys_status[n] == 8'hf2 ? 3 :
                     (sys_status[n] == 8'hf1 || sys_status[n] == 8'hf3 ? 2 : 1);
            expected_value = pack_value({sys_status[n], 8'h45, 8'h67}, length, n * 997);
            good_tx({sys_status[n], 8'h45, 8'h67}, length, n * 997, expected_value);
            good_rx(expected_value, length + 3'd2,
                    {sys_status[n], (length >= 2 ? 8'h45 : 8'h00),
                    (length == 3 ? 8'h67 : 8'h00)}, length, (n * 997) & 8191);
        end

        // Unsupported statuses, bad lengths and high data bits in either direction.
        bad_tx(24'h003c7f, 3); bad_tx(24'h7f3c7f, 3);
        bad_tx(24'hf00000, 1); bad_tx(24'hf40000, 1);
        bad_tx(24'hf50000, 1); bad_tx(24'hf70000, 1);
        bad_tx(24'hf90000, 1); bad_tx(24'hfd0000, 1);
        bad_tx(24'h903c7f, 0); bad_tx(24'h903c7f, 1);
        bad_tx(24'h903c7f, 2); bad_tx(24'hc03c00, 3);
        bad_tx(24'h90807f, 3); bad_tx(24'h903c80, 3);
        bad_tx(24'hf18000, 2); bad_tx(24'hf20080, 3);
        bad_rx(40'h7f3c008080, 5); bad_rx(40'h7f3c7f8080, 5);
        bad_rx(40'h0000f08080, 3); bad_rx(40'h0000f48080, 3);
        bad_rx(40'h0000f58080, 3); bad_rx(40'h0000f78080, 3);
        bad_rx(40'h0000f98080, 3); bad_rx(40'h0000fd8080, 3);
        bad_rx(40'h7f3c908000, 5); // header bit7 clear
        bad_rx(40'h7f3c9080c0, 5); // reserved header bit6 set
        bad_rx(40'h7f3c900080, 5); // timestamp bit7 clear
        bad_rx(40'h7f3c908080, 0); bad_rx(40'h7f3c908080, 1);
        bad_rx(40'h7f3c908080, 2); bad_rx(40'h7f3c908080, 3);
        bad_rx(40'h7f3c908080, 4); bad_rx(40'h7f3c908080, 6);
        bad_rx(40'h7f3c908080, 7); bad_rx(40'h7f80c08080, 4);
        bad_rx(40'h7f80908080, 5); bad_rx(40'h803c908080, 5);
        bad_rx(40'h0080f18080, 4); bad_rx(40'h8000f28080, 5);
        bad_rx(40'hf881f88080, 5); // two realtime events in one value

        // TX stall captures timestamp and prevents premature acceptance of an error.
        @(negedge clk);
        tx_valid = 1'b1; tx_message = 24'h913d40; tx_length = 3;
        timestamp_ms = 8191; value_tx_ready = 1'b0;
        tick;
        held_value = value_tx_data;
        check(held_value == 40'h403d91ffbf, "TX stall starts with captured bytes");
        @(negedge clk); tx_message = 24'hf00000; tx_length = 1;
        for (n = 0; n < 5; n = n + 1) begin
            timestamp_ms = n;
            tick;
            check(value_tx_valid && !tx_ready && value_tx_data === held_value &&
                  value_tx_length == 5 && tx_errors == expected_tx_errors,
                  "stalled TX data timestamp and error counter stable");
            @(negedge clk);
        end
        value_tx_ready = 1'b1;
        tick;
        expected_tx_errors = expected_tx_errors + 1;
        check(!value_tx_valid && tx_errors == expected_tx_errors, "blocked invalid TX consumed exactly once");
        @(negedge clk); tx_valid = 1'b0;
        tick;
        check(tx_errors == expected_tx_errors, "blocked invalid TX not repeated");

        // RX has independent backpressure and the same once-per-transfer rule.
        @(negedge clk);
        value_rx_valid = 1'b1; value_rx_data = 40'h7f3c90ffbf;
        value_rx_length = 5; rx_ready = 1'b0;
        tick; held_message = rx_message;
        @(negedge clk); value_rx_data = 40'h0000f08080; value_rx_length = 3;
        for (n = 0; n < 5; n = n + 1) begin
            tick;
            check(rx_valid && !value_rx_ready && rx_message === held_message &&
                  rx_length == 3 && rx_timestamp == 8191 && rx_errors == expected_rx_errors,
                  "stalled RX message timestamp and error counter stable");
            @(negedge clk);
        end
        rx_ready = 1'b1;
        tick;
        expected_rx_errors = expected_rx_errors + 1;
        check(!rx_valid && rx_errors == expected_rx_errors, "blocked invalid RX consumed exactly once");
        @(negedge clk); value_rx_valid = 1'b0;
        tick;
        check(rx_errors == expected_rx_errors, "blocked invalid RX not repeated");

        // Both elastic slots can be replaced on the cycle their old output is taken.
        @(negedge clk);
        tx_valid = 1'b1; tx_message = 24'hf8ffff; tx_length = 1; timestamp_ms = 1;
        value_rx_valid = 1'b1; value_rx_data = 40'h7f3c908080; value_rx_length = 5;
        value_tx_ready = 1'b0; rx_ready = 1'b0;
        tick;
        @(negedge clk);
        value_tx_ready = 1'b1; rx_ready = 1'b1;
        tx_message = 24'hc009ff; tx_length = 2; timestamp_ms = 128;
        value_rx_data = 40'hfffff8ffbf; value_rx_length = 3;
        #1;
        check(tx_ready && value_rx_ready, "replacement ready while outputs consumed");
        tick;
        check(value_tx_valid && value_tx_data == 40'h0009c08081 && value_tx_length == 4,
              "TX same-cycle replacement preserves new event");
        check(rx_valid && rx_message == 24'hf80000 && rx_length == 1 && rx_timestamp == 8191,
              "RX same-cycle replacement preserves new event");
        @(negedge clk); tx_valid = 1'b0; value_rx_valid = 1'b0;
        tick;
        check(!value_tx_valid && !rx_valid, "replacement outputs drain once");

        // Saturation is reached by real input handshakes, without internal force.
        @(negedge clk);
        tx_valid = 1'b1; tx_message = 24'hf00000; tx_length = 1;
        value_rx_valid = 1'b1; value_rx_data = 40'h0000f08080; value_rx_length = 3;
        repeat (65540) tick;
        check(tx_errors == 16'hffff && rx_errors == 16'hffff, "error counters saturate without wrap");
        @(negedge clk); tx_valid = 1'b0; value_rx_valid = 1'b0;
        tick;
        check(tx_errors == 16'hffff && rx_errors == 16'hffff, "saturated counters hold idle");

        // Reset must flush pending/stalled outputs, payloads, timestamps and errors.
        @(negedge clk);
        tx_valid = 1'b1; tx_message = 24'h903c7f; tx_length = 3; timestamp_ms = 1234;
        value_rx_valid = 1'b1; value_rx_data = 40'h7f3c90ffbf; value_rx_length = 5;
        value_tx_ready = 1'b0; rx_ready = 1'b0;
        tick;
        check(value_tx_valid && rx_valid, "both outputs pending before reset");
        @(negedge clk); reset = 1'b1;
        tick;
        check(!value_tx_valid && value_tx_data == 0 && value_tx_length == 0 &&
              !rx_valid && rx_message == 0 && rx_length == 0 && rx_timestamp == 0 &&
              tx_errors == 0 && rx_errors == 0 && tx_ready && value_rx_ready,
              "reset flushes both directions and counters while stalled");
        @(negedge clk); reset = 1'b0; tx_valid = 1'b0; value_rx_valid = 1'b0;
        value_tx_ready = 1'b1; rx_ready = 1'b1;
        expected_tx_errors = 0; expected_rx_errors = 0;
        good_tx(24'h803c00, 3, 0, 40'h003c808080);
        good_rx(40'h003c808080, 5, 24'h803c00, 3, 0);

        $display("PASS tb_ble_midi_codec: %0d checks", checks);
        $finish;
    end

    initial begin
        #2000000;
        $fatal(1, "tb_ble_midi_codec timeout");
    end
endmodule
