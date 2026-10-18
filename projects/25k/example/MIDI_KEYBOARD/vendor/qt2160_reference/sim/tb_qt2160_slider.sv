`timescale 1ns / 1ps
module tb_qt2160_slider;
    reg clk = 0;
    always #10 clk = ~clk;
    tri1 scl, sda;
    wire scl_low, sda_low, report, touched, valid_sample, sample_done, id_done;
    wire [7:0] value;
    wire [63:0] result, id_result;
    reg slave_sda_low = 0, slave_scl_low = 0;
    assign scl = scl_low || slave_scl_low ? 1'b0 : 1'bz;
    assign sda = sda_low || slave_sda_low ? 1'b0 : 1'bz;
    qt2160_slider_reader #(.STARTUP_CYCLES(1000), .REPORT_CYCLES(1000000),
        .CALIBRATION_CYCLES(50000), .TIMEOUT_CYCLES(50000)) dut (
        .clk(clk), .scl_in(scl), .sda_in(sda), .change_n(1'b1),
        .scl_low(scl_low), .sda_low(sda_low), .report(report), .slider_value(value),
        .touched(touched), .sample_valid(valid_sample), .sample_done(sample_done),
        .slider_result(result), .id_done(id_done), .id_result(id_result));
    reg serial_rx = 1;
    wire serial_tx, led1, led2, uart_byte_sent;
    wire [63:0] uart_byte_result;
    uart_led_controller #(.ENABLE_SLIDER_REPORT(1)) uart (
        .clk(clk), .uart_rx_pin(serial_rx), .uart_tx_pin(serial_tx), .led1(led1), .led2(led2),
        .slider_report(report), .slider_value(value), .slider_touch(touched), .slider_valid(valid_sample),
        .uart_byte_sent(uart_byte_sent), .uart_byte_result(uart_byte_result));

    time last_stop = 0, last_report = 0;
    integer gaps = 0, reports = 0, lines = 0, errors = 0, replies = 0;
    bit saw_zero = 0, saw_mid = 0, saw_end = 0, saw_release = 0;
    always @(posedge report) begin
        if (last_report && $time - last_report != 20000000)
            $fatal(1, "Reports must be exactly 20 ms apart in accelerated test");
        last_report = $time; reports++;
    end
    task automatic start_condition;
        do @(negedge sda); while (scl !== 1);
        if (last_stop) begin
            if ($time - last_stop < 100000) $fatal(1, "QT2160 bus free gap too short");
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
        if (got !== expected) $fatal(1, "I2C got %02h expected %02h", got, expected);
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
        if (sda !== !master_ack) $fatal(1, "Wrong host ACK at end of read byte");
        @(negedge scl);
    endtask
    task automatic write_registers(input [7:0] pointer, input integer count, input [127:0] data);
        start_condition(); receive_byte(8'h1a); acknowledge(1);
        receive_byte(pointer); acknowledge(1);
        for (integer i = 0; i < count; i++) begin receive_byte(data[i*8 +: 8]); acknowledge(1); end
        stop_condition();
    endtask
    task automatic read_registers(input [7:0] pointer, input integer count, input [127:0] data);
        $display("I2C read pointer=%0d bytes=%0d at %0t",pointer,count,$time);
        start_condition(); receive_byte(8'h1a); acknowledge(1,1);
        receive_byte(pointer); acknowledge(1); stop_condition();
        start_condition(); receive_byte(8'h1b); acknowledge(1);
        for (integer i = 0; i < count; i++) send_byte(data[i*8 +: 8],i < count-1);
        stop_condition();
    endtask
    task automatic configure_slider(input bit corrupt_readback);
        // Expected values from datasheet: 8 electrodes, 8-bit output, AKS group 1.
        write_registers(12,1,128'h01);
        write_registers(20,10,128'h01010101010101010028);
        write_registers(38,8,128'h0a0a0a0a0a0a0a0a);
        write_registers(54,16,128'h00000000000000000808080808080808);
        read_registers(12,1,128'h01);
        read_registers(20,10,corrupt_readback ? 128'h01010101010101010008 : 128'h01010101010101010028);
        if (!corrupt_readback) begin
            read_registers(38,8,128'h0a0a0a0a0a0a0a0a);
            read_registers(54,16,128'h00000000000000000808080808080808);
            write_registers(10,1,128'h01);
        end
    endtask
    task automatic sample(input [7:0] position, input bit touch, input bit reset_flag = 0);
        read_registers(2,5,{88'b0,8'h00,position,8'h00,8'h01,{reset_flag,6'b0,touch}});
        @(posedge sample_done); #1;
        $display("Slider sample at %0t result=%016h",$time,result);
        if (!reset_flag && (!valid_sample || value !== position || touched !== touch))
            $fatal(1, "Wrong slider snapshot: %016h", result);
    endtask

    // Independent decoding of the real 115200/8N1 TX pin, not byte launch signals.
    string line_buffer = "";
    reg [7:0] tx_byte;
    initial forever begin
        @(negedge serial_tx); #4340;
        if (serial_tx !== 0) $fatal(1, "Bad UART start bit");
        for (integer b = 0; b < 8; b++) begin #8680; tx_byte[b] = serial_tx; end
        #8680;
        if (serial_tx !== 1) $fatal(1, "Bad UART stop bit");
        line_buffer = {line_buffer,tx_byte};
        if (tx_byte == 10) begin
            $display("UART line at %0t: %s",$time,line_buffer);
            if (line_buffer == "unknown command\015\n") replies++;
            else begin
                lines++;
                case (line_buffer)
                    "SLIDER=ERR,TOUCH=0\015\n": errors++;
                    "SLIDER=000,TOUCH=1\015\n": saw_zero = 1;
                    "SLIDER=128,TOUCH=1\015\n": saw_mid = 1;
                    "SLIDER=255,TOUCH=1\015\n": saw_end = 1;
                    "SLIDER=255,TOUCH=0\015\n": saw_release = 1;
                    default: $fatal(1, "Unexpected or interleaved UART line: %s",line_buffer);
                endcase
            end
            line_buffer = "";
        end
    end
    task automatic uart_send(input string text);
        for (integer i = 0; i < text.len(); i++) begin
            serial_rx = 0; #8680;
            for (integer b = 0; b < 8; b++) begin serial_rx = text[i][b]; #8680; end
            serial_rx = 1; #8680;
        end
    endtask
    initial begin
        // A mismatch must reject configuration and retry identification/configuration.
        read_registers(0,2,128'h4011); configure_slider(1);
        @(posedge dut.transaction_done); repeat (2) @(negedge clk);
        if (valid_sample || result[47:40] != 6) $fatal(1, "Readback mismatch accepted");
        read_registers(0,2,128'h4011); configure_slider(0);
        sample(0,1,1); // First status read consumes the power-up RESET flag.
        sample(0,1);
        wait(saw_zero);
        sample(128,1); wait(saw_mid);
        sample(255,1); wait(saw_end);
        fork
            begin uart_send("xyz\nLED1+BREATH\n"); end
            begin sample(255,0); end
        join
        wait(saw_release); wait(replies == 1);
        if (!uart.led1_enable) $fatal(1, "LED command lost while streaming slider");

        // NACK must invalidate the reading, report ERR and configure again.
        start_condition(); receive_byte(8'h1a); acknowledge(0); stop_condition();
        @(posedge sample_done); #1;
        if (valid_sample || result[47:40] != 1) $fatal(1, "Stale slider value after NACK");
        read_registers(0,2,128'h4011); configure_slider(0); sample(0,1,1);
        // A later device RESET requests reconfiguration, not publication of stale status.
        sample(0,1,1);
        if (valid_sample || result[47:40] != 7) $fatal(1, "Device reset not handled");
        if (!saw_zero || !saw_mid || !saw_end || !saw_release || errors == 0 || gaps < 20 || reports < 5)
            $fatal(1, "Missing slider/stream coverage");
        $display("PASS: 8-electrode configuration/readback/calibration; 100 us bus free; 16-byte transfers; stretch; position 0/128/255 and release; fixed report cadence; actual UART lines; command arbitration; NACK/reset recovery");
        $finish;
    end
    initial begin #300000000; $fatal(1, "Slider simulation timeout state=%0d index=%0d error=%0d samples=%0d",dut.state,dut.config_index,dut.last_error,dut.samples); end
endmodule
