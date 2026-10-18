`timescale 1ns/1ps
module tb_screen_stream_router;
    reg clk = 0;
    always #5 clk = !clk;
    reg reset = 1;
    reg rx_valid = 0;
    wire rx_ready;
    reg [7:0] rx_data = 0;
    wire tx_valid;
    reg tx_ready = 1;
    wire [7:0] tx_data;
    wire mk_rx_valid, pl_rx_valid;
    reg mk_rx_ready = 1, pl_rx_ready = 1;
    wire [7:0] mk_rx_data, pl_rx_data;
    reg mk_tx_valid = 0, pl_tx_valid = 0;
    wire mk_tx_ready, pl_tx_ready;
    reg [7:0] mk_tx_data = 0, pl_tx_data = 0;
    wire mk_reset, pl_reset;
    integer checks = 0;
    integer mk_count = 0, pl_count = 0, tx_count = 0;
    integer mk_resets = 0, pl_resets = 0;
    integer mk_base, pl_base, tx_base, mk_reset_base, pl_reset_base;
    integer i;
    reg previous_mk_reset = 0, previous_pl_reset = 0;
    reg [7:0] mk_bytes [0:4095];
    reg [7:0] pl_bytes [0:4095];
    reg [7:0] tx_bytes [0:4095];

    // 20 clocks per interbyte timeout keeps failure cases practical to run.
    screen_stream_router #(.CLK_HZ(10000), .TIMEOUT_MS(2)) dut (
        .clk(clk), .reset(reset),
        .rx_valid(rx_valid), .rx_ready(rx_ready), .rx_data(rx_data),
        .tx_valid(tx_valid), .tx_ready(tx_ready), .tx_data(tx_data),
        .mk_rx_valid(mk_rx_valid), .mk_rx_ready(mk_rx_ready), .mk_rx_data(mk_rx_data),
        .mk_tx_valid(mk_tx_valid), .mk_tx_ready(mk_tx_ready), .mk_tx_data(mk_tx_data),
        .pl_rx_valid(pl_rx_valid), .pl_rx_ready(pl_rx_ready), .pl_rx_data(pl_rx_data),
        .pl_tx_valid(pl_tx_valid), .pl_tx_ready(pl_tx_ready), .pl_tx_data(pl_tx_data),
        .mk_reset(mk_reset), .pl_reset(pl_reset)
    );

    function [7:0] frame_byte;
        input is_pl;
        input integer index;
        input integer payload;
        input integer seed;
        begin
            frame_byte = (index * 29 + seed) & 255;
            if (index == 0) frame_byte = is_pl ? 8'h50 : 8'h4d;
            if (index == 1) frame_byte = is_pl ? 8'h4c : 8'h4b;
            if (is_pl && index == 12) frame_byte = payload & 255;
            if (is_pl && index == 13) frame_byte = (payload >> 8) & 255;
            // Payload contains both magics; neither may open another frame.
            if (is_pl && index == 16) frame_byte = 8'h4d;
            if (is_pl && index == 17) frame_byte = 8'h4b;
            if (is_pl && index == 18) frame_byte = 8'h50;
            if (is_pl && index == 19) frame_byte = 8'h4c;
        end
    endfunction

    task tick;
        input integer cycles;
        begin
            repeat (cycles) @(posedge clk);
            #1;
        end
    endtask

    task check;
        input condition;
        input [767:0] message;
        begin
            checks = checks + 1;
            if (condition !== 1'b1) begin
                $display("FAIL: %0s (time %0t)", message, $time);
                $fatal(1);
            end
        end
    endtask

    task send_byte;
        input [7:0] value;
        begin
            @(negedge clk);
            rx_valid = 1;
            rx_data = value;
            @(posedge clk);
            while (!rx_ready) @(posedge clk);
            #1;
        end
    endtask

    task end_input;
        begin
            @(negedge clk);
            rx_valid = 0;
        end
    endtask

    task send_request;
        input is_pl;
        input integer payload;
        input integer seed;
        input integer gaps;
        integer index;
        integer size;
        begin
            size = 16 + (is_pl ? payload : 0);
            for (index = 0; index < size; index = index + 1) begin
                send_byte(frame_byte(is_pl, index, payload, seed));
                if (gaps != 0 && index != size - 1) begin
                    end_input;
                    tick(gaps);
                end
            end
            end_input;
        end
    endtask

    task send_response;
        input is_pl;
        input integer payload;
        input integer seed;
        input integer gaps;
        integer index;
        integer size;
        begin
            size = 16 + (is_pl ? payload : 0);
            for (index = 0; index < size; index = index + 1) begin
                @(negedge clk);
                if (is_pl) begin
                    pl_tx_valid = 1;
                    pl_tx_data = frame_byte(is_pl, index, payload, seed);
                end else begin
                    mk_tx_valid = 1;
                    mk_tx_data = frame_byte(is_pl, index, payload, seed);
                end
                @(posedge clk);
                while (!(is_pl ? pl_tx_ready : mk_tx_ready)) @(posedge clk);
                #1;
                if (gaps != 0 && index != size - 1) begin
                    @(negedge clk);
                    if (is_pl) pl_tx_valid = 0;
                    else mk_tx_valid = 0;
                    tick(gaps);
                end
            end
            @(negedge clk);
            if (is_pl) pl_tx_valid = 0;
            else mk_tx_valid = 0;
        end
    endtask

    task expect_request;
        input is_pl;
        input integer base;
        input integer payload;
        input integer seed;
        integer index;
        integer size;
        begin
            size = 16 + (is_pl ? payload : 0);
            check((is_pl ? pl_count : mk_count) == base + size,
                "endpoint receives exactly the declared frame bytes");
            for (index = 0; index < size; index = index + 1)
                check((is_pl ? pl_bytes[base + index] : mk_bytes[base + index]) ===
                    frame_byte(is_pl, index, payload, seed),
                    "request byte order and content survive routing");
        end
    endtask

    task expect_response;
        input is_pl;
        input integer base;
        input integer payload;
        input integer seed;
        integer index;
        integer size;
        begin
            size = 16 + (is_pl ? payload : 0);
            check(tx_count == base + size, "host receives exactly the declared reply bytes");
            for (index = 0; index < size; index = index + 1)
                check(tx_bytes[base + index] === frame_byte(is_pl, index, payload, seed),
                    "reply byte order and content survive routing");
        end
    endtask

    always @(posedge clk) begin
        if (!reset) begin
            if (mk_rx_valid && pl_rx_valid) $fatal(1, "request broadcast to both endpoints");
            if (mk_tx_ready && pl_tx_ready) $fatal(1, "reply ownership is ambiguous");
            if (mk_reset && previous_mk_reset) $fatal(1, "MK reset lasts more than one clock");
            if (pl_reset && previous_pl_reset) $fatal(1, "PL reset lasts more than one clock");
            if (mk_rx_valid && mk_rx_ready) begin
                mk_bytes[mk_count] = mk_rx_data;
                mk_count = mk_count + 1;
            end
            if (pl_rx_valid && pl_rx_ready) begin
                pl_bytes[pl_count] = pl_rx_data;
                pl_count = pl_count + 1;
            end
            if (tx_valid && tx_ready) begin
                tx_bytes[tx_count] = tx_data;
                tx_count = tx_count + 1;
            end
            if (mk_reset) mk_resets = mk_resets + 1;
            if (pl_reset) pl_resets = pl_resets + 1;
        end
        previous_mk_reset = !reset && mk_reset;
        previous_pl_reset = !reset && pl_reset;
    end

    initial begin
        rx_valid = 1;
        rx_data = 8'h4d;
        tick(3);
        check(!rx_ready && !tx_valid && !mk_rx_valid && !pl_rx_valid,
            "global reset gates all stream handshakes");
        @(negedge clk); rx_valid = 0; reset = 0;
        tick(1);
        check(rx_ready, "global reset returns to magic scanner");

        // A partial candidate with no endpoint owner expires without reset.
        send_byte(8'h4d);
        end_input;
        tick(21);
        check(rx_ready && mk_resets == 0 && pl_resets == 0,
            "incomplete magic expires without disturbing either endpoint");

        mk_base = mk_count;
        tx_base = tx_count;
        send_request(0, 0, 7, 1);
        expect_request(0, mk_base, 0, 7);
        check(!rx_ready, "next request waits for the current reply");
        // An offered PL frame remains blocked while the MK reply is pending.
        pl_base = pl_count;
        fork
            begin send_request(1, 8, 91, 0); end
            begin
                tick(4);
                check(!rx_ready && pl_count == pl_base,
                    "coalesced PL request cannot enter before MK response");
                send_response(0, 0, 19, 1);
            end
        join
        expect_response(0, tx_base, 0, 19);
        expect_request(1, pl_base, 8, 91);
        check(mk_count == mk_base + 16, "MK magic within PL pixels is never rescanned");

        // Host backpressure can exceed the interbyte timeout by any duration.
        tx_base = tx_count;
        mk_reset_base = mk_resets;
        pl_reset_base = pl_resets;
        @(negedge clk); tx_ready = 0;
        fork
            begin send_response(1, 8, 53, 0); end
            begin
                tick(65);
                check(tx_valid && tx_data == 8'h50 && !rx_ready,
                    "reply remains stable while host stalls past timeout");
                check(mk_resets == mk_reset_base && pl_resets == pl_reset_base,
                    "host backpressure never resets an endpoint");
                @(negedge clk); tx_ready = 1;
            end
        join
        expect_response(1, tx_base, 8, 53);
        check(rx_ready, "variable-length PL reply releases ownership at its end");

        // Noise and overlapping magic are tolerated before a zero-payload PL.
        pl_base = pl_count;
        send_byte(8'h00);
        send_byte(8'h4d);
        send_byte(8'h50);
        send_byte(8'h4c);
        for (i = 2; i < 16; i = i + 1) send_byte(frame_byte(1, i, 0, 12));
        end_input;
        expect_request(1, pl_base, 0, 12);
        tx_base = tx_count;
        send_response(1, 0, 13, 0);
        expect_response(1, tx_base, 0, 13);

        // Incomplete routed MK frame resets only MK, then a PL frame recovers.
        mk_reset_base = mk_resets;
        pl_reset_base = pl_resets;
        for (i = 0; i < 5; i = i + 1) send_byte(frame_byte(0, i, 0, 1));
        end_input;
        tick(21);
        check(mk_resets == mk_reset_base + 1 && pl_resets == pl_reset_base && rx_ready,
            "incomplete MK request times out and resets only its parser");
        pl_base = pl_count;
        send_request(1, 4, 66, 0);
        expect_request(1, pl_base, 4, 66);
        send_response(1, 0, 88, 0);

        // Incomplete PL payload also needs parser reset before magic recovery.
        mk_reset_base = mk_resets;
        pl_reset_base = pl_resets;
        for (i = 0; i < 18; i = i + 1) send_byte(frame_byte(1, i, 8, 4));
        end_input;
        tick(21);
        check(mk_resets == mk_reset_base && pl_resets == pl_reset_base + 1 && rx_ready,
            "incomplete PL payload times out and resets only its parser");

        // Declared 513-byte payload is rejected as soon as byte 13 arrives.
        pl_reset_base = pl_resets;
        for (i = 0; i < 14; i = i + 1) send_byte(frame_byte(1, i, 513, 0));
        end_input;
        tick(2);
        check(pl_resets == pl_reset_base + 1 && rx_ready,
            "oversized PL request resets its parser and releases ownership");
        mk_base = mk_count;
        send_request(0, 0, 31, 0);
        expect_request(0, mk_base, 0, 31);
        send_response(0, 0, 32, 0);

        // A length of 512 exercises the high payload-length byte and counter.
        pl_base = pl_count;
        send_request(1, 512, 51, 0);
        expect_request(1, pl_base, 512, 51);
        tx_base = tx_count;
        send_response(1, 512, 52, 0);
        expect_response(1, tx_base, 512, 52);

        // A missing endpoint reply must not hold this stream forever.
        mk_reset_base = mk_resets;
        send_request(0, 0, 2, 0);
        tick(21);
        check(mk_resets == mk_reset_base + 1 && rx_ready,
            "missing response times out and resets the owning endpoint");

        // Replay honors endpoint readiness, retaining both magic bytes.
        mk_base = mk_count;
        @(negedge clk); mk_rx_ready = 0;
        send_byte(8'h4d);
        send_byte(8'h4b);
        end_input;
        tick(5);
        check(mk_rx_valid && mk_rx_data == 8'h4d && mk_count == mk_base,
            "first magic byte stays buffered under endpoint backpressure");
        @(negedge clk); mk_rx_ready = 1;
        for (i = 2; i < 16; i = i + 1) send_byte(frame_byte(0, i, 0, 16));
        end_input;
        expect_request(0, mk_base, 0, 16);
        send_response(0, 0, 17, 0);

        // Global reset interrupts an owned partial frame without leakage.
        for (i = 0; i < 7; i = i + 1) send_byte(frame_byte(1, i, 0, 0));
        end_input;
        @(negedge clk); reset = 1;
        tick(2);
        check(!rx_ready && !tx_valid && !mk_rx_valid && !pl_rx_valid,
            "reset discards a partially routed frame immediately");
        @(negedge clk); reset = 0;
        tick(1);
        mk_base = mk_count;
        send_request(0, 0, 71, 0);
        expect_request(0, mk_base, 0, 71);
        send_response(0, 0, 72, 0);
        check(rx_ready, "new MK request completes normally after global reset");

        $display("PASS: tb_screen_stream_router (%0d checks, MK/PL framing/magic/payload/backpressure/timeout/reset)", checks);
        $finish;
    end

    initial begin
        #1000000;
        $fatal(1, "testbench timeout");
    end
endmodule
