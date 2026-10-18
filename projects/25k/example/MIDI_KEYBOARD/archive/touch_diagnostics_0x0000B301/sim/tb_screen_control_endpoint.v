`timescale 1ns/1ps
module tb_screen_control_endpoint;
    reg clk = 0;
    always #5 clk = !clk;
    reg reset = 1;
    reg rx_valid = 0;
    wire rx_ready;
    reg [7:0] rx_data = 0;
    wire tx_valid;
    reg tx_ready = 0;
    wire [7:0] tx_data;
    reg [31:0] status_flags = 32'h89abcdef;
    reg [255:0] touch_diagnostics =
        256'hffffffff_80000000_12345678_abcdef01_00000008_00000007_00000001_00000000;
    wire slider_scan_pause;
    wire config_write;
    wire [7:0] config_opcode;
    wire [31:0] config_value;
    wire [3:0] midi_channel, screen_page;
    wire signed [7:0] transpose;
    wire [15:0] theme_rgb565, clear_rgb565, protocol_errors;
    wire screen_update;
    integer updates = 0;
    integer assertions = 0;
    integer transactions = 0;
    integer index;
    integer updates_before;
    integer writes = 0;
    integer writes_before;
    reg [127:0] request_bytes;
    reg [127:0] response_bytes;
    reg [127:0] expected_bytes;
    screen_control_endpoint dut (
        .clk(clk), .reset(reset), .rx_valid(rx_valid), .rx_ready(rx_ready),
        .rx_data(rx_data), .tx_valid(tx_valid), .tx_ready(tx_ready), .tx_data(tx_data),
        .status_flags(status_flags), .midi_channel(midi_channel), .transpose(transpose),
        .touch_diagnostics(touch_diagnostics), .slider_scan_pause(slider_scan_pause),
        .screen_page(screen_page), .theme_rgb565(theme_rgb565), .clear_rgb565(clear_rgb565),
        .screen_update(screen_update), .protocol_errors(protocol_errors),
        .config_write(config_write), .config_opcode(config_opcode), .config_value(config_value)
    );

    always @(posedge clk) begin
        #1;
        if (!reset && screen_update) updates = updates + 1;
        if (!reset && config_write) writes = writes + 1;
    end

    task check;
        input condition;
        input [8*100-1:0] message;
        begin
            assertions = assertions + 1;
            if (condition !== 1'b1) begin
                $display("FAIL: %0s at %0t", message, $time);
                $fatal(1);
            end
        end
    endtask

    // Reference CRC works one input bit at a time, independently of the DUT's
    // byte update function. Byte zero is at the low end of the packed vector.
    function [15:0] reference_crc;
        input [111:0] payload;
        reg [15:0] crc;
        reg feedback;
        integer byte_number, bit_number;
        begin
            crc = 16'hffff;
            for (byte_number = 0; byte_number < 14; byte_number = byte_number + 1)
                for (bit_number = 7; bit_number >= 0; bit_number = bit_number - 1) begin
                    feedback = crc[15] ^ payload[byte_number*8 + bit_number];
                    crc = {crc[14:0], 1'b0};
                    if (feedback) crc = crc ^ 16'h1021;
                end
            reference_crc = crc;
        end
    endfunction

    function [127:0] frame;
        input [7:0] opcode;
        input [15:0] sequence_number;
        input [31:0] arg0, arg1;
        input [7:0] version;
        reg [111:0] payload;
        begin
            payload = {arg1, arg0, sequence_number, opcode, version, 8'h4b, 8'h4d};
            frame = {reference_crc(payload), payload};
        end
    endfunction

    task send_byte;
        input [7:0] value;
        integer timeout;
        begin
            @(negedge clk);
            rx_valid = 1;
            rx_data = value;
            timeout = 0;
            @(posedge clk);
            while (!rx_ready) begin
                timeout = timeout + 1;
                check(timeout < 100, "RX ready timeout");
                @(posedge clk);
            end
            @(negedge clk);
            rx_valid = 0;
        end
    endtask

    task send_frame;
        input [127:0] bytes;
        integer n;
        begin
            for (n = 0; n < 16; n = n + 1) begin
                send_byte(bytes[n*8 +: 8]);
                // Force arbitrary frame chunking at byte stream boundaries.
                if (n == 4 || n == 9) repeat (7) @(negedge clk);
            end
        end
    endtask

    task receive_frame;
        integer n, stall, timeout;
        reg [7:0] held;
        begin
            response_bytes = 0;
            for (n = 0; n < 16; n = n + 1) begin
                timeout = 0;
                while (!tx_valid) begin
                    @(negedge clk);
                    timeout = timeout + 1;
                    check(timeout < 100, "TX valid timeout");
                end
                held = tx_data;
                // While a response is blocked no host input may be accepted.
                rx_valid = 1;
                rx_data = 8'h4d;
                for (stall = 0; stall < n%3+1; stall = stall + 1) begin
                    @(posedge clk);
                    #2;
                    check(tx_valid && tx_data === held, "TX byte changed under backpressure");
                    check(!rx_ready, "RX accepted a second outstanding request");
                end
                @(negedge clk);
                rx_valid = 0;
                tx_ready = 1;
                @(posedge clk);
                response_bytes[n*8 +: 8] = tx_data;
                @(negedge clk);
                tx_ready = 0;
            end
            check(!tx_valid && rx_ready, "endpoint did not return to receive mode");
            check(response_bytes[127:112] === reference_crc(response_bytes[111:0]), "response CRC invalid");
            transactions = transactions + 1;
        end
    endtask

    task transact;
        input [7:0] opcode;
        input [15:0] sequence_number;
        input [31:0] arg0, arg1, expected_status, expected_result;
        begin
            request_bytes = frame(opcode, sequence_number, arg0, arg1, 8'h01);
            send_frame(request_bytes);
            receive_frame;
            expected_bytes = frame(opcode | 8'h80, sequence_number, expected_status, expected_result, 8'h01);
            check(response_bytes === expected_bytes, "reply fields/order differ from expected response");
        end
    endtask

    task expect_defaults;
        begin
            check(midi_channel === 0 && transpose === 0 && screen_page === 0,
                  "reset MIDI/page defaults incorrect");
            check(theme_rgb565 === 16'h07ff && clear_rgb565 === 0,
                  "reset screen colors incorrect");
            check(protocol_errors === 0 && !screen_update, "reset error/update defaults incorrect");
            check(slider_scan_pause === 0 && !config_write, "reset diagnostic test defaults incorrect");
        end
    endtask

    initial begin
        if ($test$plusargs("dump")) begin
            $dumpfile("tb_screen_control_endpoint.vcd");
            $dumpvars(0, tb_screen_control_endpoint);
        end
        repeat (3) @(negedge clk);
        reset = 0;
        expect_defaults;
        // Garbage and a repeated M must resynchronize without creating errors.
        send_byte(8'h00);
        send_byte(8'h4b);
        send_byte(8'h4d);
        send_byte(8'h00);
        send_byte(8'h4d);
        send_byte(8'h4d);
        transact(8'h01, 16'h1234, 0, 0, 0, status_flags);
        check(protocol_errors == 0 && updates == 0, "garbage changed error count or screen");

        transact(8'h10, 16'h0201, 15, 0, 0, 15);
        check(midi_channel == 15 && updates == 0, "channel command failed");
        transact(8'h11, 16'h0302, -32'd48, 0, 0, -32'd48);
        check(transpose == -8'sd48 && updates == 0, "negative transpose command failed");
        transact(8'h11, 16'h0403, 48, 0, 0, 48);
        check(transpose == 8'sd48, "positive transpose command failed");
        transact(8'h20, 16'h0504, 15, 0, 0, 15);
        check(screen_page == 15 && updates == 1 && !screen_update, "page update pulse failed");
        transact(8'h21, 16'h0605, 32'hf81f, 0, 0, 32'hf81f);
        check(theme_rgb565 == 16'hf81f && updates == 2, "theme command failed");
        transact(8'h22, 16'h0706, 32'hffff, 0, 0, 32'hffff);
        check(clear_rgb565 == 16'hffff && updates == 3, "clear command failed");

        // Range errors, reserved field, high opcode bit, and unknown opcode.
        transact(8'h10, 16'h1000, 16, 0, 2, 0);
        transact(8'h11, 16'h1001, 49, 0, 2, 0);
        transact(8'h11, 16'h1002, -32'd49, 0, 2, 0);
        transact(8'h20, 16'h1003, 16, 0, 2, 0);
        transact(8'h21, 16'h1004, 32'h10000, 0, 2, 0);
        transact(8'h22, 16'h1005, 32'h10000, 0, 2, 0);
        transact(8'h01, 16'h1006, 1, 0, 2, 0);
        for (index = 0; index < 6; index = index + 1) begin
            case (index)
                0: transact(8'h01, 16'h1100, 0, 1, 2, 0);
                1: transact(8'h10, 16'h1101, 0, 1, 2, 0);
                2: transact(8'h11, 16'h1102, 0, 1, 2, 0);
                3: transact(8'h20, 16'h1103, 0, 1, 2, 0);
                4: transact(8'h21, 16'h1104, 0, 1, 2, 0);
                5: transact(8'h22, 16'h1105, 0, 1, 2, 0);
            endcase
        end
        transact(8'h7f, 16'h1200, 0, 0, 1, 0);
        transact(8'h90, 16'h1201, 0, 0, 1, 0);
        check(protocol_errors == 15, "invalid request error count incorrect");
        check(midi_channel == 15 && transpose == 48 && screen_page == 15 &&
              theme_rgb565 == 16'hf81f && clear_rgb565 == 16'hffff && updates == 3,
              "invalid request mutated settings");

        request_bytes = frame(8'h20, 16'h2001, 1, 0, 8'h01);
        request_bytes[127:112] = request_bytes[127:112] ^ 16'h0100;
        send_frame(request_bytes);
        receive_frame;
        check(response_bytes === frame(8'ha0, 16'h2001, 3, 0, 8'h01), "bad CRC rejection failed");
        request_bytes = frame(8'h20, 16'h2002, 1, 0, 8'h02);
        send_frame(request_bytes);
        receive_frame;
        check(response_bytes === frame(8'ha0, 16'h2002, 4, 0, 8'h01), "bad version rejection failed");
        check(protocol_errors == 17 && screen_page == 15 && updates == 3,
              "CRC/version error mutated settings or count");
        // CRC outranks version and opcode; a corrupt frame is counted once.
        request_bytes = frame(8'h7f, 16'h2003, 1, 1, 8'h02);
        request_bytes[112] = !request_bytes[112];
        send_frame(request_bytes);
        receive_frame;
        check(response_bytes === frame(8'hff, 16'h2003, 3, 0, 8'h01), "error priority incorrect");
        check(protocol_errors == 18, "multiple error fields counted more than once");

        // Exercise saturation without spending tens of thousands of frames.
        @(negedge clk);
        dut.protocol_errors = 16'hfffe;
        transact(8'h7f, 16'h2004, 0, 0, 1, 0);
        check(protocol_errors == 16'hffff, "error count did not reach saturation");
        transact(8'h7f, 16'h2005, 0, 0, 1, 0);
        check(protocol_errors == 16'hffff, "error count wrapped at saturation");

        // A partial frame remains pending, then reset discards it completely.
        send_byte(8'h4d);
        send_byte(8'h4b);
        send_byte(8'h01);
        repeat (100) @(negedge clk);
        check(rx_ready && !tx_valid && protocol_errors == 16'hffff,
              "partial frame should wait without timeout");
        reset = 1;
        @(negedge clk);
        reset = 0;
        #1;
        expect_defaults;
        // All diagnostic words, including high-bit/raw values, are read-only.
        writes_before = writes;
        updates_before = updates;
        for (index = 0; index < 8; index = index + 1)
            transact(8'h02, 16'h3100 + index, index, 0, 0,
                     touch_diagnostics[index*32 +: 32]);
        // A response retains the word selected at command acceptance even if
        // live diagnostics change while the byte stream is stalled.
        send_frame(frame(8'h02, 16'h3110, 7, 0, 8'h01));
        while (!tx_valid) @(negedge clk);
        touch_diagnostics[255:224] = 32'h2468ace0;
        receive_frame;
        check(response_bytes === frame(8'h82, 16'h3110, 0, 32'hffffffff, 8'h01),
              "live diagnostics changed an already accepted reply");
        transact(8'h02, 16'h3111, 7, 0, 0, 32'h2468ace0);
        transact(8'h12, 16'h3120, 1, 0, 0, 1);
        check(slider_scan_pause, "pause request was not set");
        transact(8'h12, 16'h3121, 1, 0, 0, 1);
        // Malformed diagnostics/test commands must not clear a requested pause.
        transact(8'h02, 16'h3130, 8, 0, 2, 0);
        transact(8'h02, 16'h3131, 32'hffffffff, 0, 2, 0);
        transact(8'h02, 16'h3132, 0, 1, 2, 0);
        transact(8'h12, 16'h3133, 2, 0, 2, 0);
        transact(8'h12, 16'h3134, 32'hffffffff, 0, 2, 0);
        transact(8'h12, 16'h3135, 0, 1, 2, 0);
        transact(8'h82, 16'h3136, 0, 0, 1, 0);
        request_bytes = frame(8'h12, 16'h3137, 0, 0, 8'h01);
        request_bytes[112] = !request_bytes[112];
        send_frame(request_bytes);
        receive_frame;
        check(response_bytes === frame(8'h92, 16'h3137, 3, 0, 8'h01),
              "bad CRC test command was accepted");
        send_frame(frame(8'h12, 16'h3138, 0, 0, 8'h02));
        receive_frame;
        check(response_bytes === frame(8'h92, 16'h3138, 4, 0, 8'h01),
              "bad version test command was accepted");
        check(slider_scan_pause && protocol_errors == 9,
              "invalid diagnostic/test command mutated pause or error count");
        transact(8'h12, 16'h3140, 0, 0, 0, 0);
        check(!slider_scan_pause && writes == writes_before && updates == updates_before &&
              midi_channel == 0 && transpose == 0 && screen_page == 0 &&
              theme_rgb565 == 16'h07ff && clear_rgb565 == 0 && config_opcode == 0 && config_value == 0,
              "diagnostic/test command affected musical or screen configuration");
        updates_before = updates;
        transact(8'h20, 16'h3000, 0, 0, 0, 0);
        check(updates == updates_before + 1, "same-value screen command should pulse update");
        status_flags = 32'h76543210;
        transact(8'h01, 16'h3001, 0, 0, 0, status_flags);

        // Reset aborts an already queued response as well as a partial request.
        send_frame(frame(8'h10, 16'h3002, 7, 0, 8'h01));
        repeat (20) @(negedge clk);
        check(tx_valid && !rx_ready, "expected blocked response before reset");
        reset = 1;
        @(negedge clk);
        reset = 0;
        #1;
        expect_defaults;
        check(rx_ready && !tx_valid, "reset did not abort pending response");
        transact(8'h01, 16'hffff, 0, 0, 0, status_flags);
        $display("PASS tb_screen_control_endpoint transactions=%0d assertions=%0d", transactions, assertions);
        $finish;
    end

    initial begin
        #1000000;
        $display("FAIL: global simulation timeout");
        $fatal(1);
    end
endmodule
