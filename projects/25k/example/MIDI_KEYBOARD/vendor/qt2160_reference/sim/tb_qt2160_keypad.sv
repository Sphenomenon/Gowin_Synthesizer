`timescale 1ns / 1ps
module tb_qt2160_keypad;
    reg clk = 0;
    always #10 clk = ~clk;
    tri1 scl, sda;
    wire scl_low, sda_low, event_valid, event_ready, sample_done;
    wire [3:0] key_index;
    wire [15:0] key_signal, key_reference;
    wire [63:0] result;
    wire scan_done;
    wire [63:0] scan_result;
    reg slave_sda_low = 0, slave_scl_low = 0;
    assign scl = scl_low || slave_scl_low ? 1'b0 : 1'bz;
    assign sda = sda_low || slave_sda_low ? 1'b0 : 1'bz;
    qt2160_keypad_reader #(.STARTUP_CYCLES(1000), .POLL_CYCLES(5000000),
        .CALIBRATION_CYCLES(50000), .TIMEOUT_CYCLES(50000)) dut (
        .clk(clk), .scl_in(scl), .sda_in(sda), .scl_low(scl_low), .sda_low(sda_low),
        .event_valid(event_valid), .event_ready(event_ready), .key_index(key_index),
        .key_signal(key_signal), .key_reference(key_reference), .sample_done(sample_done), .result(result),
        .scan_done(scan_done), .scan_result(scan_result));
    wire key_tx_valid, key_tx_ready, key_tx_last;
    wire [7:0] key_tx_data;
    qt2160_keypad_uart formatter (
        .clk(clk), .event_valid(event_valid), .event_ready(event_ready),
        .key_index(key_index), .key_signal(key_signal), .key_reference(key_reference),
        .tx_valid(key_tx_valid), .tx_ready(key_tx_ready), .tx_data(key_tx_data), .tx_last(key_tx_last));
    reg serial_rx = 1;
    wire serial_tx, led1, led2, byte_sent;
    wire [63:0] byte_result;
    // Deliberately assert the old report input: the new configuration must suppress it.
    uart_led_controller #(.ENABLE_SLIDER_REPORT(0), .ENABLE_KEY_REPORT(1)) uart (
        .clk(clk), .uart_rx_pin(serial_rx), .uart_tx_pin(serial_tx), .led1(led1), .led2(led2),
        .slider_report(1'b1), .slider_value(8'hff), .slider_touch(1'b1), .slider_valid(1'b1),
        .key_tx_valid(key_tx_valid), .key_tx_ready(key_tx_ready), .key_tx_data(key_tx_data), .key_tx_last(key_tx_last),
        .uart_byte_sent(byte_sent), .uart_byte_result(byte_result));
    time last_stop = 0;
    integer gaps = 0, expected_count = 0, key_lines = 0, replies = 0, events = 0;
    string expected_lines[0:127];
    integer diagnostic_records = 0;
    reg [15:0] diagnostic_keys = 0;
    always @(posedge clk) if (scan_done) begin
        diagnostic_records++;
        diagnostic_keys[scan_result[47:44]] = 1;
    end
    reg [15:0] seen_keys = 0;
    always @(posedge clk) if (event_valid && event_ready) begin
        events = events + 1;
        seen_keys[key_index] = 1;
    end

    task automatic start_condition;
        do @(negedge sda); while (scl !== 1);
        if (last_stop) begin
            if ($time - last_stop < 100000) $fatal(1, "Bus free less than 100 us");
            gaps++;
        end
    endtask
    task automatic stop_condition;
        do @(posedge sda); while (scl !== 1);
        last_stop = $time;
    endtask
    task automatic receive_byte(input [7:0] expected);
        reg [7:0] got;
        for (integer b = 7; b >= 0; b--) begin @(posedge scl); got[b] = sda; end
        if (got !== expected) $fatal(1, "I2C got %02h expected %02h",got,expected);
    endtask
    task automatic acknowledge(input bit ack, input bit stretch = 0);
        @(negedge scl); slave_sda_low = ack;
        if (stretch) begin slave_scl_low = 1; #50000; slave_scl_low = 0; end
        @(posedge scl); @(negedge scl); slave_sda_low = 0;
    endtask
    task automatic send_byte(input [7:0] data, input bit master_ack);
        for (integer b = 7; b >= 0; b--) begin
            slave_sda_low = !data[b]; @(posedge scl); @(negedge scl);
        end
        slave_sda_low = 0; @(posedge scl);
        if (sda !== !master_ack) $fatal(1, "Wrong final host ACK/NACK");
        @(negedge scl);
    endtask
    task automatic write_registers(input [7:0] pointer, input integer count, input [127:0] data);
        start_condition(); receive_byte(8'h1a); acknowledge(1);
        receive_byte(pointer); acknowledge(1);
        for (integer i = 0; i < count; i++) begin receive_byte(data[i*8 +: 8]); acknowledge(1); end
        stop_condition();
    endtask
    task automatic read_registers(input [7:0] pointer, input integer count, input [127:0] data);
        start_condition(); receive_byte(8'h1a); acknowledge(1,1);
        receive_byte(pointer); acknowledge(1); stop_condition();
        start_condition(); receive_byte(8'h1b); acknowledge(1);
        for (integer i = 0; i < count; i++) send_byte(data[i*8 +: 8],i < count-1);
        stop_condition();
    endtask
    task automatic configure_keypad(input bit corrupt_readback);
        write_registers(12,2,128'h0101); write_registers(17,1,7); write_registers(20,1,0);
        write_registers(22,16,0); write_registers(38,16,{16{8'h0a}});
        write_registers(54,16,{16{8'h04}});
        read_registers(12,2,128'h0101); read_registers(17,1,7);
        read_registers(20,1,corrupt_readback ? 1 : 0);
        if (!corrupt_readback) begin
            read_registers(22,16,0); read_registers(38,16,{16{8'h0a}});
            read_registers(54,16,{16{8'h04}}); write_registers(10,1,1);
        end
    endtask
    task automatic expect_key(input integer key, input integer signal_value, input integer reference_value);
        integer difference;
        string sign_text;
        difference = reference_value - signal_value;
        sign_text = difference < 0 ? "-" : "+";
        expected_lines[expected_count] = $sformatf("KEY=%02d,Y=%0d,X=%0d,SIGNAL=%05d,REF=%05d,DELTA=%s%05d\015\n",
            key+1,key/8,key%8,signal_value,reference_value,sign_text,difference < 0 ? -difference : difference);
        expected_count++;
    endtask
    task automatic frame(input [15:0] before_keys, input [15:0] after_keys,
        input [255:0] signal_data, input [255:0] reference_data, input bit initial_reset = 0);
        integer signal_value, reference_value;
        time frame_start;
        for (integer key = 0; key < 16; key++) begin
            signal_value = signal_data[key*16 +: 16]; reference_value = reference_data[key*16 +: 16];
            if (before_keys[key] && after_keys[key] && reference_value-signal_value >= 8)
                expect_key(key,signal_value,reference_value);
        end
        read_registers(2,5,{104'b0,before_keys,{initial_reset,7'b0}});
        frame_start = $time;
        for (integer key = 0; key < 16; key++) begin
            read_registers(100+2*key,2,signal_data[key*16 +: 16]);
            read_registers(132+2*key,2,reference_data[key*16 +: 16]);
        end
        read_registers(2,5,{104'b0,after_keys,8'h00});
        @(posedge sample_done); #1;
        if ($time-frame_start > 25000000) $fatal(1,"UART delayed the complete I2C frame");
    endtask
    task automatic uart_send(input string text);
        for (integer i = 0; i < text.len(); i++) begin
            serial_rx = 0; #8680;
            for (integer b = 0; b < 8; b++) begin serial_rx = text[i][b]; #8680; end
            serial_rx = 1; #8680;
        end
    endtask
    // Independently decode the actual TX pin at 115200/8N1.
    string line_buffer = "";
    reg [7:0] tx_byte;
    initial forever begin
        @(negedge serial_tx); #4340;
        if (serial_tx !== 0) $fatal(1,"Invalid UART start");
        for (integer b = 0; b < 8; b++) begin #8680; tx_byte[b] = serial_tx; end
        #8680;
        if (serial_tx !== 1) $fatal(1,"Invalid UART stop");
        line_buffer = {line_buffer,tx_byte};
        if (tx_byte == 10) begin
            if (line_buffer == "unknown command\015\n") replies++;
            else begin
                if (key_lines >= expected_count || line_buffer != expected_lines[key_lines])
                    $fatal(1,"Unexpected/interleaved UART line %s expected %s",line_buffer,expected_lines[key_lines]);
                $display("UART %s",line_buffer);
                key_lines++;
            end
            line_buffer = "";
        end
    end
    reg [255:0] signal_data, reference_data;
    initial begin
        // Wrong device ID and bad readback must not enable the keypad.
        read_registers(0,2,128'h4012); @(posedge sample_done); #1;
        if (result[15] || result[47:40] != 4) $fatal(1,"Wrong ID accepted");
        read_registers(0,2,128'h4011); configure_keypad(1);
        @(posedge sample_done); #1;
        if (result[15] || result[47:40] != 6) $fatal(1,"Bad config accepted");
        read_registers(0,2,128'h4011); configure_keypad(0);
        signal_data = {16{16'd1000}}; reference_data = {16{16'd1100}};
        frame(0,0,signal_data,reference_data,1);
        frame(0,0,signal_data,reference_data);
        if (events || key_lines) $fatal(1,"Idle reports are forbidden");
        // Reproduce screenshot: low deltas and keys released during the scan.
        signal_data = {16{16'd1956}}; reference_data = {16{16'd1968}};
        signal_data[7*16 +: 16] = 65535; reference_data[7*16 +: 16] = 0;
        signal_data[8*16 +: 16] = 0; reference_data[8*16 +: 16] = 65535;
        signal_data[15*16 +: 16] = 1966; // delta 2 with stale status must be rejected.
        fork
            begin frame(16'h8181,16'h8181,signal_data,reference_data); end
            begin wait(event_valid); uart_send("bad\nLED1+BREATH\n"); end
        join
        wait(key_lines == 2 && replies == 1);
        if (!uart.led1_enable) $fatal(1,"LED command lost during key reporting");
        frame(16'hffff,0,signal_data,reference_data);
        if (key_lines != 2) $fatal(1,"Released keys emitted stale readings");
        // Hold all 16 keys: no key may be dropped while UART applies backpressure.
        for (integer key = 0; key < 16; key++) begin
            signal_data[key*16 +: 16] = 1000+key; reference_data[key*16 +: 16] = 1100+key;
        end
        frame(16'hffff,16'hffff,signal_data,reference_data);
        wait(key_lines == 18);
        // Preserve the datasheet's NTHR-2 hysteresis boundary (8 passes, 7 fails).
        signal_data = {16{16'd1000}}; reference_data = {16{16'd1007}};
        reference_data[15:0] = 1008;
        frame(3,3,signal_data,reference_data); wait(key_lines == 19);
        frame(0,0,signal_data,reference_data);
        frame(0,0,signal_data,reference_data);
        if (events != 19 || seen_keys != 16'hffff || diagnostic_keys != 16'hffff)
            $fatal(1,"Missing/extra matrix key or diagnostics");
        // NACK midway through a buffered frame must not emit any of that frame.
        read_registers(2,5,128'h0100); read_registers(100,2,128'd999);
        start_condition(); receive_byte(8'h1a); acknowledge(0); stop_condition();
        @(posedge sample_done); #1;
        if (event_valid || result[15] || result[47:40] != 1) $fatal(1,"NACK did not invalidate");
        read_registers(0,2,128'h4011); configure_keypad(0); frame(0,0,signal_data,reference_data,1);
        // Runtime RESET must restart initialization.
        read_registers(2,5,128'h0180); @(posedge sample_done); #1;
        if (event_valid || result[15] || result[47:40] != 7) $fatal(1,"RESET did not invalidate");
        read_registers(0,2,128'h4011); configure_keypad(0);
        signal_data = {16{16'd15}}; reference_data = {16{16'd45}};
        frame(1,1,signal_data,reference_data,1); wait(key_lines == 20);
        frame(0,0,signal_data,reference_data);
        if (events != 20 || gaps < 100 || diagnostic_records < 160) $fatal(1,"Coverage incomplete");
        $display("PASS: full-frame buffering and before/after status; stale/low/negative delta rejection; hysteresis 8/7; all 16 keys; BREP/NDIL/BL config readback; raw diagnostics; UART pin/command arbitration; NACK/RESET recovery");
        $finish;
    end
    initial begin #3000000000.0; $fatal(1,"Keypad timeout state=%0d config=%0d lines=%0d",dut.state,dut.config_index,key_lines); end
endmodule
