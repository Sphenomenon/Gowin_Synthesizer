`timescale 1ns/1ps
module tb_workstation_ulpi_link;
    localparam integer WATCHDOG_CYCLES = 2048;
    reg clock = 1'b0;
    always #8.333 clock = !clock;
    reg reset_n = 1'b0;
    reg phy_direction = 1'b0;
    reg phy_next = 1'b0;
    reg phy_drive = 1'b0;
    reg [7:0] phy_data = 8'h00;
    tri [7:0] physical_data;
    wire [7:0] link_data;
    wire link_enable, stop;
    reg csr_valid = 1'b0;
    wire csr_ready;
    reg csr_write = 1'b0;
    reg [5:0] csr_address = 6'h00;
    reg [7:0] csr_data = 8'h00;
    wire response_valid;
    reg response_ready = 1'b0;
    wire [7:0] response_data;
    wire [2:0] response_error;
    reg [7:0] transmit_data = 8'h00;
    reg transmit_valid = 1'b0;
    reg transmit_nopid = 1'b0;
    wire transmit_ready;
    wire [7:0] receive_data;
    wire receive_valid, receive_active, receive_error;
    wire [1:0] line_state, vbus_state;
    wire id_state, disconnected, transmit_aborted, fatal_error;
    wire [31:0] received_bytes, transmitted_bytes;
    wire [15:0] received_commands;
    wire received_status;
    reg [7:0] phy_registers [0:63];
    integer checks = 0;
    integer scenarios = 0;
    integer byte_index;
    integer wait_cycles;
    reg [7:0] returned_data;

    assign physical_data = link_enable ? link_data : 8'hzz;
    assign physical_data = phy_drive ? phy_data : 8'hzz;
    workstation_ulpi_link #(
        .TRANSACTION_TIMEOUT_CYCLES(WATCHDOG_CYCLES), .NOPID_TIMEOUT_CYCLES(4096)
    ) dut(
        .clk_ulpi(clock), .reset_n(reset_n),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_direction), .ulpi_nxt_i(phy_next),
        .ulpi_data_o(link_data), .ulpi_data_oe_o(link_enable), .ulpi_stp_o(stop),
        .csr_valid_i(csr_valid), .csr_ready_o(csr_ready), .csr_write_i(csr_write),
        .csr_address_i(csr_address), .csr_data_i(csr_data),
        .csr_response_valid_o(response_valid), .csr_response_ready_i(response_ready),
        .csr_response_data_o(response_data), .csr_response_error_o(response_error),
        .utmi_data_i(transmit_data), .utmi_txvalid_i(transmit_valid),
        .utmi_tx_nopid_i(transmit_nopid), .utmi_txready_o(transmit_ready),
        .utmi_data_o(receive_data), .utmi_rxvalid_o(receive_valid),
        .utmi_rxactive_o(receive_active), .utmi_rxerror_o(receive_error),
        .utmi_linestate_o(line_state), .vbus_state_o(vbus_state), .id_state_o(id_state),
        .host_disconnect_o(disconnected), .tx_abort_o(transmit_aborted),
        .fatal_error_o(fatal_error), .received_bytes_o(received_bytes),
        .transmitted_bytes_o(transmitted_bytes), .rxcmd_count_o(received_commands), .rxcmd_valid_o(received_status)
    );

    task automatic check(input logic condition, input string label);
        begin
            if (condition !== 1'b1)
                $fatal(1, "%s at %0t", label, $time);
            checks = checks + 1;
        end
    endtask

    task automatic tick;
        begin @(posedge clock); #1; end
    endtask

    task automatic reset_link;
        begin
            @(negedge clock);
            reset_n = 1'b0;
            phy_direction = 1'b0;
            phy_next = 1'b0;
            phy_drive = 1'b0;
            csr_valid = 1'b0;
            response_ready = 1'b0;
            transmit_valid = 1'b0;
            transmit_nopid = 1'b0;
            #1;
            check(!link_enable && stop, "asynchronous reset releases DATA and asserts STP");
            repeat (2) tick();
            @(negedge clock);
            reset_n = 1'b1;
            tick();
            check(csr_ready && !fatal_error, "fresh link is ready");
            scenarios = scenarios + 1;
        end
    endtask

    task automatic request_register(input logic write_enable, input [5:0] address, input [7:0] value);
        begin
            @(negedge clock);
            csr_valid = 1'b1;
            csr_write = write_enable;
            csr_address = address;
            csr_data = value;
            check(csr_ready, "CSR request acceptance");
            tick();
            @(negedge clock);
            csr_valid = 1'b0;
            check(link_enable && physical_data == {write_enable ? 2'b10 : 2'b11, address}, "CSR command encoding");
        end
    endtask

    task automatic accept_response(input [2:0] error_code);
        begin
            check(response_valid && response_error == error_code, "CSR terminal response");
            returned_data = response_data;
            repeat (3) begin
                tick();
                check(response_valid && response_data == returned_data && response_error == error_code,
                      "CSR response remains stable under backpressure");
                check(!csr_ready, "single outstanding CSR response");
            end
            @(negedge clock);
            response_ready = 1'b1;
            tick();
            check(!response_valid, "CSR response consumed once");
            @(negedge clock);
            response_ready = 1'b0;
        end
    endtask

    task automatic write_register(input [5:0] address, input [7:0] value);
        begin
            request_register(1'b1, address, value);
            repeat (3) begin
                tick();
                check(physical_data == {2'b10, address} && !stop, "register command waits for NXT");
            end
            @(negedge clock);
            phy_next = 1'b1;
            tick();
            check(physical_data == value && !stop, "register write data follows command ACK");
            @(negedge clock);
            phy_next = 1'b0;
            repeat (2) begin
                tick();
                check(physical_data == value && !stop, "register data stable under NXT stall");
            end
            @(negedge clock);
            phy_next = 1'b1;
            phy_registers[address] = physical_data;
            tick();
            check(stop && physical_data == 8'h00, "register write terminates with STP and idle");
            @(negedge clock);
            phy_next = 1'b0;
            tick();
            check(!stop, "register STP lasts one cycle");
            accept_response(3'd0);
        end
    endtask

    task automatic read_register(input [5:0] address, input logic return_next);
        begin
            request_register(1'b0, address, 8'h00);
            @(negedge clock);
            phy_next = 1'b1;
            tick();
            @(negedge clock);
            phy_direction = 1'b1;
            phy_next = 1'b0;
            #1;
            check(!link_enable, "raw DIR immediately withdraws link drive");
            tick();
            check(!receive_valid && !response_valid, "read turnaround is not a byte");
            @(negedge clock);
            phy_drive = 1'b1;
            phy_data = phy_registers[address];
            phy_next = return_next;
            tick();
            check(!receive_valid && !response_valid, "register return is never UTMI RX data");
            @(negedge clock);
            phy_direction = 1'b0;
            phy_drive = 1'b0;
            phy_next = 1'b0;
            #1;
            check(!link_enable, "PHY-to-link turnaround is high impedance");
            tick();
            tick();
            accept_response(3'd0);
            check(returned_data == phy_registers[address], "register read data matches physical PHY storage");
        end
    endtask

    task automatic receive_status(input [7:0] value);
        begin
            @(negedge clock);
            phy_data = value;
            phy_next = 1'b0;
            tick();
            check(!receive_valid, "RXCMD never becomes a payload byte");
            check(received_status, "RXCMD provides a fresh status indication independent of its saturating counter");
        end
    endtask

    task automatic transmit_packet(input integer payload_bytes, input logic no_pid);
        integer payload_index;
        reg [7:0] expected_byte;
        begin
            reset_link();
            @(negedge clock);
            transmit_valid = 1'b1;
            transmit_nopid = no_pid;
            transmit_data = no_pid ? 8'h5a : 8'hc3;
            tick();
            check(physical_data == (no_pid ? 8'h40 : 8'h43), "ULPI transmit command carries PID nibble or NOPID");
            repeat (4) begin
                tick();
                check(!transmit_ready && transmitted_bytes == 0, "no byte accepted while command is stalled");
            end
            @(negedge clock);
            phy_next = 1'b1;
            #1;
            check(transmit_ready == !no_pid, "NOPID command must not consume first UTMI data byte");
            tick();
            for (payload_index = 0; payload_index < payload_bytes; payload_index = payload_index + 1) begin
                expected_byte = 8'(payload_index ^ (payload_index >> 8) ^ 8'h5a);
                @(negedge clock);
                transmit_data = expected_byte;
                phy_next = 1'b0;
                #1;
                check(physical_data == expected_byte && !stop && !transmit_ready, "payload stable during NXT backpressure");
                if (payload_index % 7 == 0)
                    repeat (2) tick();
                @(negedge clock);
                phy_next = 1'b1;
                #1;
                check(transmit_ready && physical_data == expected_byte, "every physical payload byte is accepted once");
                tick();
            end
            @(negedge clock);
            transmit_valid = 1'b0;
            phy_next = 1'b0;
            #1;
            check(stop && physical_data == 0, "packet termination is not an extra zero payload byte");
            tick();
            check(!stop && !fatal_error, "packet terminated without fatal error");
            check(transmitted_bytes == 32'(payload_bytes + (no_pid ? 0 : 1)), "accepted UTMI byte count includes PID only in normal mode");
        end
    endtask

    always @(posedge clock) begin
        if (phy_drive && link_enable)
            $fatal(1, "ULPI DATA contention");
        if (link_enable && (!reset_n || phy_direction))
            $fatal(1, "link drove DATA while reset or PHY-owned");
        if (transmit_ready && (!transmit_valid || phy_direction || !phy_next || fatal_error))
            $fatal(1, "invalid UTMI TX acceptance");
    end

    initial begin
        for (byte_index = 0; byte_index < 64; byte_index = byte_index + 1)
            phy_registers[byte_index] = 8'h00;
        phy_registers[0] = 8'h24;
        phy_registers[1] = 8'h04;
        phy_registers[2] = 8'h04;
        phy_registers[3] = 8'h00;
        reset_link();
        for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1)
            read_register(6'(byte_index), 1'b0);
        for (byte_index = 0; byte_index < 256; byte_index = byte_index + 1) begin
            write_register(6'h16, 8'(byte_index));
            read_register(6'h16, byte_index[0]);
        end
        check(received_commands == 0 && received_bytes == 0, "CSR transactions do not pollute packet or RXCMD counters");

        reset_link();
        @(negedge clock);
        phy_direction = 1'b1;
        phy_next = 1'b1;
        tick();
        check(receive_active && !receive_valid, "RX start turnaround sets active but consumes no byte");
        for (byte_index = 0; byte_index < 256; byte_index = byte_index + 1) begin
            @(negedge clock);
            phy_drive = 1'b1;
            phy_data = 8'(byte_index);
            tick();
            check(receive_active && receive_valid && receive_data == 8'(byte_index), "all RX payload byte values preserved");
        end
        receive_status(8'h7d);
        check(receive_active && receive_error && line_state == 1 && vbus_state == 3 && id_state,
              "RX error, line, VBUS and ID decoded independently");
        receive_status(8'h02);
        check(!receive_active && !receive_error && line_state == 2, "RX end clears active and error");
        receive_status(8'h20);
        check(disconnected && !receive_active && !receive_error, "host disconnect RXCMD is exposed");
        @(negedge clock);
        phy_drive = 1'b0;
        phy_direction = 1'b0;
        #1;
        check(!link_enable, "link does not skip receive-to-transmit turnaround");
        tick();
        check(received_bytes == 256 && received_commands == 3 && !disconnected, "RX counters and disconnect pulse");

        transmit_packet(0, 1'b0);
        transmit_packet(3, 1'b0);
        transmit_packet(66, 1'b0);
        transmit_packet(514, 1'b0);
        transmit_packet(64, 1'b1);

        reset_link();
        request_register(1'b1, 6'h16, 8'h55);
        @(negedge clock);
        phy_direction = 1'b1;
        tick();
        check(response_valid && response_error == 2 && !fatal_error, "unaccepted CSR command preemption is retryable");

        reset_link();
        request_register(1'b1, 6'h16, 8'haa);
        @(negedge clock);
        phy_next = 1'b1;
        tick();
        @(negedge clock);
        phy_direction = 1'b1;
        tick();
        check(response_valid && response_error == 2 && fatal_error, "partial register write is not silently replayed");

        reset_link();
        request_register(1'b0, 6'h00, 8'h00);
        @(negedge clock);
        phy_next = 1'b1;
        tick();
        @(negedge clock);
        phy_direction = 1'b1;
        phy_next = 1'b0;
        tick();
        @(negedge clock);
        phy_direction = 1'b0;
        tick();
        check(response_valid && response_error == 3 && fatal_error && !receive_valid, "truncated read fails without inventing data");

        reset_link();
        @(negedge clock);
        transmit_valid = 1'b1;
        transmit_data = 8'hc3;
        tick();
        @(negedge clock);
        phy_direction = 1'b1;
        tick();
        check(!transmit_aborted && !fatal_error && transmitted_bytes == 0, "preempted PID has not been consumed");
        @(negedge clock);
        phy_direction = 1'b0;
        wait_cycles = 0;
        while (link_data != 8'h43 && wait_cycles < 8) begin tick(); wait_cycles = wait_cycles + 1; end
        check(link_data == 8'h43 && transmitted_bytes == 0, "unconsumed PID is retried after turnaround");
        @(negedge clock);
        phy_next = 1'b1;
        tick();
        @(negedge clock);
        phy_direction = 1'b1;
        tick();
        check(transmit_aborted && fatal_error && transmitted_bytes == 1 && !transmit_ready,
              "partial packet preemption aborts explicitly instead of duplicating payload");

        reset_link();
        request_register(1'b0, 6'h00, 8'h00);
        repeat (WATCHDOG_CYCLES + 2) tick();
        check(response_valid && response_error == 1 && fatal_error, "stalled CSR command has a finite terminal response");
        check(!csr_ready && !transmit_ready, "fatal timeout requires explicit reset before further traffic");

        reset_link();
        request_register(1'b0, 6'h00, 8'h00);
        @(negedge clock);
        phy_next = 1'b1;
        tick();
        @(negedge clock);
        phy_next = 1'b0;
        repeat (WATCHDOG_CYCLES + 2) tick();
        check(response_valid && response_error == 1 && fatal_error && !receive_valid, "PHY never returning register data times out");

        reset_link();
        @(negedge clock);
        transmit_valid = 1'b1;
        transmit_data = 8'hc3;
        tick();
        wait_cycles = 0;
        while (!fatal_error && wait_cycles < WATCHDOG_CYCLES + 3) begin tick(); wait_cycles = wait_cycles + 1; end
        check(fatal_error && transmit_aborted && transmitted_bytes == 0, "stalled TX command aborts finitely");

        reset_link();
        @(negedge clock);
        transmit_valid = 1'b1;
        transmit_nopid = 1'b1;
        transmit_data = 8'h00;
        tick();
        repeat (WATCHDOG_CYCLES + 2) tick();
        check(!fatal_error, "NOPID has its own bounded budget without changing ordinary packet timeout");
        wait_cycles = 0;
        while (!fatal_error && wait_cycles < 4098) begin tick(); wait_cycles = wait_cycles + 1; end
        check(fatal_error && transmit_aborted && !received_status, "stalled NOPID also has a finite fatal boundary");

        reset_link();
        @(negedge clock);
        transmit_valid = 1'b1;
        transmit_data = 8'hc3;
        tick();
        @(negedge clock);
        transmit_valid = 1'b0;
        tick();
        check(fatal_error && transmit_aborted && transmitted_bytes == 0, "withdrawing unaccepted PID is an explicit cancellation");

        reset_link();
        request_register(1'b1, 6'h16, 8'haa);
        @(negedge clock);
        phy_next = 1'b1;
        tick();
        @(negedge clock);
        reset_n = 1'b0;
        #1;
        check(!link_enable && stop && !response_valid, "reset in flight immediately releases DATA and clears pending response");

        $display("PASS workstation_ulpi_link: %0d checks, %0d reset scenarios, 256 scratch patterns, 514-byte TX, NOPID, RXCMD, preemption, timeouts", checks, scenarios);
        $finish;
    end

    initial begin
        #1000000;
        $fatal(1, "global simulation timeout");
    end
endmodule
