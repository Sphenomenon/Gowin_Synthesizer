`timescale 1ps/1ps
module tb_workstation_usb2_cpu_bridge #(
    parameter integer CPU_HALF_PERIOD_PS = 10417
);
    reg clk_cpu = 0, clk_ulpi = 0, clock_running = 1;
    always #(CPU_HALF_PERIOD_PS) clk_cpu = !clk_cpu;
    always #8333 if (clock_running) clk_ulpi = !clk_ulpi;
    reg reset_n = 0, session_reset_n = 0;
    reg reg_cs = 0, reg_wr = 0;
    reg [7:0] reg_addr = 0;
    reg [31:0] reg_wdata = 0;
    reg [3:0] reg_be = 15;
    wire reg_ack, reg_error, irq, enable, hs_enable, reset_request;
    wire [31:0] reg_rdata;
    reg [15:0] status = 16'h000f;
    reg [2:0] reference_fault = 0;
    reg [15:0] diagnostic_counter = 0;
    reg [31:0] sof_counter = 0;
    wire command_valid, command_toggle, transmit_valid, result_ready, receive_ready;
    wire [7:0] command_pid, transmit_data;
    wire [6:0] command_device;
    wire [3:0] command_endpoint;
    wire [9:0] command_length;
    reg allow_command = 1, allow_upload = 1, allow_result = 1, allow_receive = 1, bad_last = 0;
    reg [3:0] fake_status = 0;
    reg [2:0] fake_state = 0;
    reg [9:0] fake_length = 0, fake_index = 0;
    reg [7:0] fake_pid = 0;
    integer checks = 0, cycles = 0, command_count = 0, reset_count = 0;
    wire command_ready = fake_state == 0 && allow_command;
    wire transmit_ready = fake_state == 1 && allow_upload && cycles % 7 != 0;
    wire result_valid = fake_state == 2 && allow_result;
    wire [9:0] result_length = fake_pid == 8'h69 && fake_status == 0 ? fake_length : 10'd0;
    wire receive_valid = fake_state == 3 && allow_receive && cycles % 5 != 0;
    wire receive_last = bad_last || fake_index + 10'd1 == fake_length;

    function automatic [7:0] pattern(input integer index);
        pattern = 8'((index * 73) ^ 166);
    endfunction
    workstation_usb2_cpu_bridge #(.TRANSACTION_TIMEOUT_CYCLES(2048)) dut (
        .clk_cpu(clk_cpu), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .session_reset_n_i(session_reset_n),
        .reg_cs_i(reg_cs), .reg_wr_i(reg_wr), .reg_addr_i(reg_addr), .reg_wdata_i(reg_wdata), .reg_be_i(reg_be),
        .reg_ack_o(reg_ack), .reg_error_o(reg_error), .reg_rdata_o(reg_rdata), .irq_o(irq),
        .enable_o(enable), .hs_enable_o(hs_enable), .reset_request_o(reset_request),
        .status_i(status), .diagnostic_i({diagnostic_counter, ~diagnostic_counter}), .sof_count_i(sof_counter),
        .reference_fault_i(reference_fault),
        .command_valid_o(command_valid), .command_ready_i(command_ready), .command_pid_o(command_pid),
        .command_device_o(command_device), .command_endpoint_o(command_endpoint), .command_toggle_o(command_toggle),
        .command_length_o(command_length), .transmit_data_o(transmit_data), .transmit_valid_o(transmit_valid),
        .transmit_ready_i(transmit_ready), .result_valid_i(result_valid), .result_ready_o(result_ready),
        .result_status_i(fake_status), .result_pid_i(8'h4b), .result_length_i(result_length),
        .receive_data_i(pattern(int'(fake_index))), .receive_valid_i(receive_valid),
        .receive_ready_o(receive_ready), .receive_last_i(receive_last)
    );
    always @(posedge clk_ulpi) begin
        cycles = cycles + 1; diagnostic_counter <= diagnostic_counter + 1'b1; sof_counter <= sof_counter + 1'b1;
        if (reset_request) reset_count = reset_count + 1;
    end
    always @(posedge clk_ulpi or negedge session_reset_n) begin
        if (!session_reset_n) begin fake_state <= 0; fake_length <= 0; fake_index <= 0; fake_pid <= 0; end
        else begin
            if (command_valid && command_ready) begin
                if (command_device != 5 || command_endpoint != 3 || !command_toggle)
                    $fatal(1, "torn command mailbox");
                command_count = command_count + 1;
                fake_pid <= command_pid; fake_length <= command_length; fake_index <= 0;
                fake_state <= command_pid == 8'he1 && command_length != 0 ? 1 : 2;
            end
            if (transmit_valid && transmit_ready) begin
                if (transmit_data !== pattern(int'(fake_index))) $fatal(1, "TX RAM byte %0d is %02x", fake_index, transmit_data);
                checks = checks + 1;
                if (fake_index + 10'd1 == fake_length) begin fake_state <= 2; fake_index <= 0; end
                else fake_index <= fake_index + 1'b1;
            end
            if (result_valid && result_ready) begin fake_state <= result_length == 0 ? 0 : 3; fake_index <= 0; end
            if (receive_valid && receive_ready) begin
                if (receive_last) begin fake_state <= 0; fake_index <= 0; end
                else fake_index <= fake_index + 1'b1;
            end
        end
    end
    task automatic check(input reg condition, input string message);
        begin checks = checks + 1; if (!condition) $fatal(1, "%s cycles=%0d fake=%0d", message, cycles, fake_state); end
    endtask
    task automatic cpu_wait(input integer count);
        repeat (count) @(negedge clk_cpu);
    endtask
    task automatic access_register(input reg write_enable, input [7:0] address, input [31:0] value,
                                   input [3:0] byte_enable, input reg expected_error, output reg [31:0] response);
        integer deadline;
        begin
            @(negedge clk_cpu); reg_cs = 1; reg_wr = write_enable; reg_addr = address; reg_wdata = value; reg_be = byte_enable;
            deadline = 0;
            @(negedge clk_cpu);
            while (!reg_ack && deadline < 12) begin deadline = deadline + 1; @(negedge clk_cpu); end
            check(reg_ack && reg_error == expected_error, $sformatf("MMIO address %02x expected error %0d", address, expected_error));
            response = reg_rdata;
            repeat (2) begin @(negedge clk_cpu); check(!reg_ack, "held CS acknowledged twice"); end
            reg_cs = 0; @(negedge clk_cpu);
        end
    endtask
    reg [31:0] scratch;
    task automatic write_register(input [7:0] address, input [31:0] value);
        access_register(1, address, value, 15, 0, scratch);
    endtask
    task automatic read_register(input [7:0] address, output reg [31:0] value);
        access_register(0, address, 0, 0, 0, value);
    endtask
    task automatic start(input [7:0] pid, input integer length);
        write_register(8'h0c, {2'd0, 10'(length), 1'b1, 4'd3, 7'd5, pid});
    endtask
    task automatic wait_done;
        integer deadline;
        reg [31:0] state_value;
        begin
            deadline = 0; state_value = 0;
            while (!state_value[18] && deadline < 3000) begin read_register(8'h08, state_value); deadline = deadline + 1; end
            check(state_value[18] && !state_value[17], "sealed result reached CPU");
        end
    endtask
    task automatic cancel_session;
        reg [31:0] before_generation, after_generation, state_value;
        begin
            read_register(8'h28, before_generation);
            #3; session_reset_n = 0; #7; session_reset_n = 1;
            cpu_wait(12); read_register(8'h28, after_generation); read_register(8'h08, state_value);
            check(after_generation == before_generation + 1 && state_value[19] && !state_value[18] && !state_value[17], "short session reset cancels and advances generation");
            access_register(0, 8'h14, 0, 0, 1, scratch);
            read_register(8'h20, state_value); check(state_value == 0, "old TX staging discarded");
            write_register(8'h1c, 4);
        end
    endtask
    integer before_commands, before_reset;
    reg [31:0] value, generation;
    initial begin
        cpu_wait(6); reset_n = 1; cpu_wait(8);
        read_register(0, value); check(value == 32'h55324801, "ABI identity");
        access_register(1, 8'h10, 0, 15, 1, scratch);
        write_register(4, 3); session_reset_n = 1; cpu_wait(20);
        check(enable && hs_enable, "control crosses independently of packet channel");
        for (integer iteration = 0; iteration < 20; iteration = iteration + 1) begin
            read_register(8'h2c, value); check(value[15:0] == ~value[31:16], "coherent status mailbox");
        end
        access_register(1, 4, 1, 15, 1, scratch);
        access_register(1, 8'h0d, 0, 15, 1, scratch);
        access_register(1, 8'h10, 0, 2, 1, scratch);
        access_register(1, 8'h0c, {2'd0, 10'd1, 1'b1, 4'd3, 7'd5, 8'he1}, 15, 1, scratch);
        for (integer byte_index = 0; byte_index < 512; byte_index = byte_index + 1)
            access_register(1, 8'h10, {24'd0, pattern(byte_index)}, byte_index % 2 == 0 ? 1 : 15, 0, scratch);
        read_register(8'h20, value); check(value == 512, "TX capacity exactly 512");
        access_register(1, 8'h10, 0, 15, 1, scratch);
        allow_command = 0; start(8'he1, 512); cpu_wait(10);
        access_register(1, 8'h10, 0, 15, 1, scratch);
        access_register(1, 8'h0c, 0, 15, 1, scratch);
        access_register(1, 8'h1c, 3, 15, 1, scratch);
        allow_command = 1; wait_done(); read_register(8'h18, value);
        check(value == 32'h80004b00, "OUT response metadata"); write_register(8'h1c, 1);
        start(8'h69, 512); wait_done(); cpu_wait(100);
        check(fake_state == 0 && irq, "CPU polling cannot hold the MAC result or receive stream");
        read_register(8'h18, value); check(value == 32'h82004b00, "IN response metadata");
        for (integer byte_index = 0; byte_index < 512; byte_index = byte_index + 1) begin
            read_register(8'h24, value); check(value == 32'(512 - byte_index), "remaining packet length");
            read_register(8'h14, value); check(value == {24'd0, pattern(byte_index)}, "RX RAM byte order");
        end
        access_register(0, 8'h14, 0, 0, 1, scratch); write_register(8'h1c, 1);
        fake_status = 1; start(8'h69, 64); wait_done(); read_register(8'h18, value);
        check(value == 32'h80004b01, "NAK does not publish payload"); write_register(8'h1c, 1); fake_status = 0;
        status[2] = 0; cpu_wait(24);
        access_register(1, 8'h0c, {2'd0, 10'd65, 1'b1, 4'd3, 7'd5, 8'h69}, 15, 1, scratch);
        access_register(1, 8'h0c, {2'd0, 10'd0, 1'b1, 4'd3, 7'd5, 8'hb4}, 15, 1, scratch);
        start(8'h69, 64); wait_done(); cancel_session(); status[2] = 1; cpu_wait(24);
        allow_command = 0; before_commands = command_count; start(8'h69, 8); cpu_wait(12); cancel_session();
        allow_command = 1; cpu_wait(20); check(command_count == before_commands, "cancelled request is not reissued");
        for (integer byte_index = 0; byte_index < 8; byte_index = byte_index + 1) write_register(8'h10, {24'd0, pattern(byte_index)});
        allow_upload = 0; start(8'he1, 8); wait (fake_state == 1); cancel_session(); allow_upload = 1;
        allow_result = 0; start(8'h69, 8); wait (fake_state == 2); cancel_session(); allow_result = 1;
        allow_receive = 0; start(8'h69, 512); wait (fake_state == 3); cancel_session(); allow_receive = 1;
        start(8'h69, 64); wait_done(); cancel_session();
        bad_last = 1; before_reset = reset_count; start(8'h69, 64);
        wait (reset_count > before_reset); cancel_session(); bad_last = 0;
        allow_command = 0; before_reset = reset_count; start(8'h69, 8);
        wait (reset_count > before_reset); cancel_session(); allow_command = 1;
        allow_result = 0; start(8'h69, 8); wait (fake_state == 2);
        @(negedge clk_ulpi); clock_running = 0; session_reset_n = 0; cpu_wait(12);
        reference_fault = 3'b010; cpu_wait(4); read_register(8'h38, value);
        check(value == 2, "reference fault remains observable without ULPI clock");
        read_register(8'h08, value); check(value[19] && !value[16] && !value[17], "cancel reaches CPU with stopped ULPI clock");
        write_register(4, 2); check(!enable, "disable works without PHY clock");
        reference_fault = 0;
        clock_running = 1; allow_result = 1; cpu_wait(20); write_register(4, 3); session_reset_n = 1; cpu_wait(20);
        write_register(8'h1c, 4); start(8'h69, 8); wait_done(); write_register(8'h1c, 1);
        before_reset = reset_count; write_register(4, 7); cpu_wait(30);
        check(reset_count == before_reset + 1, "software reset is a single acknowledged pulse");
        read_register(8'h04, value); check(!value[16], "software reset request acknowledged");
        for (integer iteration = 0; iteration < 16; iteration = iteration + 1) begin
            start(8'h69, 8); wait_done(); cancel_session();
        end
        $display("PASS workstation_usb2_cpu_bridge: half-period=%0d, %0d checks, sealed 512-byte CDC/reset/timeout/clock loss", CPU_HALF_PERIOD_PS, checks);
        $finish;
    end
    initial begin #2000000000; $fatal(1, "MMIO bridge timeout"); end
endmodule
