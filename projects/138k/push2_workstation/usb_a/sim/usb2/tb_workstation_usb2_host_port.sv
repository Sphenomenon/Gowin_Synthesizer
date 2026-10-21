`timescale 1ns/1ps
module tb_workstation_usb2_host_port;
    reg clk_ulpi = 1'b0;
    always #8.333 clk_ulpi = ~clk_ulpi;
    reg reset_n = 1'b0;
    reg phy_ready = 1'b0;
    reg phy_fatal = 1'b0;
    reg hs_enable = 1'b1;
    reg reset_request = 1'b0;
    reg mac_idle = 1'b1;
    reg attached = 1'b0;
    reg low_speed = 1'b0;
    reg device_k = 1'b0;
    reg disconnect = 1'b0;
    reg abort_tx = 1'b0;
    reg [3:0] fault = 0;
    reg [7:0] function_value = 8'h41;
    wire [1:0] physical_line = function_value == 8'h45 ? (attached ? (low_speed ? 2'b10 : 2'b01) : 2'b00) :
                               function_value == 8'h50 && device_k ? 2'b10 : 2'b00;
    reg [1:0] reported_line = 0;
    reg status_valid = 1'b0;
    wire csr_valid;
    wire csr_ready;
    wire csr_write;
    wire [5:0] csr_address;
    wire [7:0] csr_data;
    reg response_valid = 1'b0;
    wire response_ready;
    reg [7:0] response_data = 0;
    reg [2:0] response_error = 0;
    wire [7:0] chirp_data;
    wire chirp_valid;
    wire chirp_ready;
    wire connected;
    wire high_speed;
    wire sof_enable;
    wire traffic_enable;
    wire reset_active;
    wire owns_tx;
    wire session_reset;
    wire unsupported_low_speed;
    wire failed;
    wire [3:0] failure_code;
    wire [4:0] state;
    wire [7:0] last_function;
    wire [7:0] last_response;
    wire [7:0] csr_retries;
    wire [15:0] chirp_count;
    integer checks = 0;
    integer scenarios = 0;
    integer cycle_count = 0;
    integer response_delay = 0;
    integer request_count = 0;
    integer tx_start_delay = 0;
    integer tx_bytes = 0;
    integer segment_bytes = 0;
    integer segments = 0;
    integer reset_start_cycle = -1;
    integer chirp_end_cycle = -1;
    integer sof_start_cycle = -1;
    integer session_count = 0;
    integer drain_delay = 0;
    reg pending = 1'b0;
    reg preempted = 1'b0;
    reg transmitting_q = 1'b0;
    reg last_j = 1'b0;
    reg drain_reported = 1'b0;
    reg chirp_ended_q = 1'b0;
    assign chirp_ready = chirp_valid && fault != 6 && !(fault == 7 && tx_bytes > 3) && tx_start_delay >= 3;
    assign csr_ready = !pending && !response_valid && fault != 4;

    workstation_usb2_host_port #(
        .CYCLES_PER_US(1), .ATTACH_DEBOUNCE_US(20), .ROOT_RESET_US(8000),
        .RECOVERY_US(30), .CSR_TIMEOUT_US(32)
    ) dut (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .phy_ready_i(phy_ready), .phy_fatal_i(phy_fatal),
        .hs_enable_i(hs_enable), .reset_request_i(reset_request), .mac_idle_i(mac_idle),
        .linestate_i(reported_line), .rxcmd_valid_i(status_valid), .host_disconnect_i(disconnect), .tx_abort_i(abort_tx),
        .csr_valid_o(csr_valid), .csr_ready_i(csr_ready), .csr_write_o(csr_write),
        .csr_address_o(csr_address), .csr_data_o(csr_data), .csr_response_valid_i(response_valid),
        .csr_response_ready_o(response_ready), .csr_response_data_i(response_data), .csr_response_error_i(response_error),
        .chirp_data_o(chirp_data), .chirp_valid_o(chirp_valid), .chirp_ready_i(chirp_ready),
        .connected_o(connected), .high_speed_o(high_speed), .sof_enable_o(sof_enable), .traffic_enable_o(traffic_enable),
        .reset_active_o(reset_active), .owns_tx_o(owns_tx), .session_reset_o(session_reset),
        .unsupported_low_speed_o(unsupported_low_speed), .failed_o(failed), .failure_code_o(failure_code),
        .state_o(state), .last_function_o(last_function), .last_response_o(last_response),
        .csr_retries_o(csr_retries), .chirp_count_o(chirp_count)
    );

    task automatic check(input reg condition, input string message);
        begin
            checks = checks + 1;
            if (condition !== 1'b1)
                $fatal(1, "%s (fault=%0d state=%0d failure=%0d cycle=%0d)", message, fault, state, failure_code, cycle_count);
        end
    endtask

    always @(posedge clk_ulpi) begin
        cycle_count = cycle_count + 1;
        if (!reset_n) begin
            function_value <= 8'h41;
            response_valid <= 1'b0;
            response_data <= 0;
            response_error <= 0;
            pending <= 1'b0;
            response_delay <= 0;
            request_count <= 0;
            preempted <= 1'b0;
            reset_start_cycle <= -1;
            sof_start_cycle <= -1;
            session_count <= 0;
        end else begin
            if (response_valid && response_ready)
                response_valid <= 1'b0;
            if (pending && fault != 5) begin
                if (response_delay == 0) begin
                    response_valid <= 1'b1;
                    pending <= 1'b0;
                end else
                    response_delay <= response_delay - 1;
            end
            if (csr_valid && csr_ready) begin
                request_count <= request_count + 1;
                pending <= 1'b1;
                response_delay <= 1;
                response_error <= 0;
                response_data <= 0;
                check(csr_address == 6'h04 || (!csr_write && csr_address == 6'h15), "only owned registers accessed");
                if (fault == 2 || (fault == 1 && !preempted)) begin
                    response_error <= 2;
                    preempted <= 1'b1;
                end else if (csr_write) begin
                    check(csr_data == 8'h45 || csr_data == 8'h50 || csr_data == 8'h40, "legal Host Function Control settings");
                    function_value <= csr_data;
                    if (csr_data == 8'h50)
                        reset_start_cycle <= cycle_count;
                    if (csr_data == 8'h40)
                        check(drain_reported, "OpMode changes only after a fresh drained SE0 RXCMD");
                end else if (csr_address == 6'h04)
                    response_data <= fault == 3 ? function_value ^ 8'h01 : function_value;
                else
                    response_data <= {6'd0, physical_line};
            end
            if (session_reset)
                session_count <= session_count + 1;
            if (sof_enable && sof_start_cycle < 0) begin
                sof_start_cycle <= cycle_count;
                check(cycle_count - reset_start_cycle >= 8000, "reset is not ended early");
                if (high_speed)
                    check(cycle_count - chirp_end_cycle >= 100 && cycle_count - chirp_end_cycle <= 500,
                          "HS chirp ends 100-500 us before reset release");
            end
            if (traffic_enable)
                check(sof_enable && cycle_count - sof_start_cycle >= 30 && connected && !owns_tx,
                      "SOF precedes normal traffic throughout reset recovery");
            if (failed)
                check(!csr_valid && !chirp_valid && !traffic_enable && !sof_enable, "failure gates all traffic");
        end
    end

    always @(negedge clk_ulpi) begin
        status_valid = 1'b0;
        if (!reset_n) begin
            reported_line = 0;
            tx_start_delay = 0;
            drain_delay = 0;
            drain_reported = 1'b0;
        end else begin
            if (!chirp_valid && physical_line != reported_line) begin
                reported_line = physical_line;
                status_valid = 1'b1;
            end
            if (chirp_valid)
                tx_start_delay = tx_start_delay + 1;
            if (chirp_ended_q)
                drain_delay = 4;
            if (drain_delay > 0) begin
                drain_delay = drain_delay - 1;
                if (drain_delay == 0 && fault != 8) begin
                    reported_line = 0;
                    status_valid = 1'b1;
                    drain_reported = 1'b1;
                end
            end
        end
    end

    always @(posedge clk_ulpi) begin
        chirp_ended_q = 1'b0;
        if (!reset_n) begin
            transmitting_q = 1'b0;
            tx_bytes = 0;
            segment_bytes = 0;
            segments = 0;
            chirp_end_cycle = -1;
        end else begin
            if (chirp_valid && chirp_ready) begin
                check(chirp_data == 8'h00 || chirp_data == 8'hff, "raw chirps use only K or J bytes");
                if (segment_bytes == 0) begin
                    check(chirp_data == 0, "chirp train starts with K");
                    last_j = 1'b0;
                end else if (last_j != (chirp_data == 8'hff)) begin
                    check(segment_bytes == 50, "each complete K/J segment is exactly 50 us");
                    segments = segments + 1;
                    segment_bytes = 0;
                    last_j = !last_j;
                end
                segment_bytes = segment_bytes + 1;
                tx_bytes = tx_bytes + 1;
                transmitting_q = 1'b1;
            end else if (!chirp_valid && transmitting_q) begin
                if (!failed) begin
                    check(segment_bytes == 50 && last_j, "chirp train ends after a complete J segment");
                    check(segments >= 5, "at least KJ KJ KJ delivered");
                end
                transmitting_q = 1'b0;
                chirp_end_cycle = cycle_count;
                chirp_ended_q = 1'b1;
            end
        end
    end

    task automatic begin_scenario(input reg [3:0] selected_fault);
        begin
            @(negedge clk_ulpi);
            #1;
            reset_n = 1'b0;
            phy_ready = 1'b0;
            phy_fatal = 1'b0;
            hs_enable = 1'b1;
            reset_request = 1'b0;
            mac_idle = 1'b1;
            attached = 1'b0;
            low_speed = 1'b0;
            device_k = 1'b0;
            disconnect = 1'b0;
            abort_tx = 1'b0;
            fault = selected_fault;
            repeat (4) @(negedge clk_ulpi);
            #1;
            reset_n = 1'b1;
            repeat (3) @(negedge clk_ulpi);
            #1;
            check(!csr_valid && !traffic_enable && !chirp_valid, "no access before PHY initialization");
            phy_ready = 1'b1;
            scenarios = scenarios + 1;
        end
    endtask

    task automatic await_state(input reg [4:0] expected_state, input integer timeout_cycles);
        integer waited;
        begin
            waited = 0;
            while (state != expected_state && !failed && waited < timeout_cycles) begin
                @(negedge clk_ulpi);
                #1;
                waited = waited + 1;
            end
            check(state == expected_state, "expected bounded state transition");
        end
    endtask

    task automatic attach_device;
        begin
            await_state(7, 200);
            attached = 1'b1;
            await_state(9, 200);
            check(connected && reset_active && !traffic_enable && !sof_enable, "debounced attach starts reset, not traffic");
        end
    endtask

    task automatic device_chirp;
        begin
            repeat (5) @(negedge clk_ulpi);
            #1;
            device_k = 1'b1;
            repeat (20) @(negedge clk_ulpi);
            #1;
            device_k = 1'b0;
        end
    endtask

    task automatic expect_failure(input reg [3:0] expected_code);
        integer waited;
        begin
            waited = 0;
            while (!failed && waited < 10000) begin
                @(negedge clk_ulpi);
                #1;
                waited = waited + 1;
            end
            check(failed && failure_code == expected_code && !connected && !traffic_enable, "expected terminal failure");
            repeat (3) @(negedge clk_ulpi);
        end
    endtask

    initial begin
        begin_scenario(0);
        attach_device();
        device_k = 1'b1;
        @(negedge clk_ulpi);
        #1;
        device_k = 1'b0;
        repeat (8) @(negedge clk_ulpi);
        #1;
        check(!chirp_valid && chirp_count == 0, "short K glitch does not start HS response");
        device_chirp();
        await_state(16, 10000);
        check(high_speed && last_function == 8'h40 && chirp_count >= 6 && !reset_active, "HS port ready with verified configuration");
        attached = 1'b0;
        disconnect = 1'b1;
        @(negedge clk_ulpi);
        #1;
        disconnect = 1'b0;
        await_state(7, 100);
        check(!connected && !high_speed && session_count == 2, "HS disconnect fences prior session and returns to FS detect");
        begin_scenario(0);
        attach_device();
        await_state(16, 10000);
        check(!high_speed && last_function == 8'h45 && chirp_count == 0, "FS-only peripheral falls back after full reset");
        attached = 1'b0;
        @(negedge clk_ulpi);
        #1;
        attached = 1'b1;
        repeat (6) @(negedge clk_ulpi);
        #1;
        check(connected && traffic_enable, "short FS SE0 is not a disconnect");
        hs_enable = 1'b0;
        mac_idle = 1'b0;
        reset_request = 1'b1;
        @(negedge clk_ulpi);
        #1;
        reset_request = 1'b0;
        repeat (4) @(negedge clk_ulpi);
        #1;
        check(!traffic_enable && !sof_enable && function_value == 8'h45, "software reset first quiesces MAC without changing PHY");
        mac_idle = 1'b1;
        await_state(9, 100);
        device_chirp();
        await_state(16, 10000);
        check(!high_speed && chirp_count == 0 && session_count == 2, "HS disabled policy is latched for the entire reset");
        attached = 1'b0;
        await_state(7, 100);
        check(!connected, "stable FS SE0 disconnects");
        begin_scenario(0);
        await_state(7, 100);
        low_speed = 1'b1;
        attached = 1'b1;
        await_state(17, 30);
        check(unsupported_low_speed && !connected && !traffic_enable && !reset_active, "LS is reported, not mis-negotiated as HS");
        attached = 1'b0;
        await_state(7, 30);
        low_speed = 1'b0;
        attached = 1'b1;
        repeat (10) @(negedge clk_ulpi);
        #1;
        attached = 1'b0;
        await_state(7, 30);
        check(session_count == 0 && !reset_active, "bouncing attach restarts debounce");
        begin_scenario(1);
        await_state(7, 100);
        check(csr_retries == 1 && !failed && last_function == 8'h45, "safe CSR preemption is retried");
        begin_scenario(2);
        expect_failure(2);
        check(csr_retries == 3, "CSR retry budget bounded");
        begin_scenario(3);
        expect_failure(4);
        begin_scenario(4);
        expect_failure(3);
        begin_scenario(5);
        expect_failure(3);
        begin_scenario(6);
        attach_device();
        device_chirp();
        expect_failure(5);
        begin_scenario(7);
        attach_device();
        device_chirp();
        expect_failure(6);
        begin_scenario(8);
        attach_device();
        device_chirp();
        expect_failure(7);
        begin_scenario(0);
        attach_device();
        abort_tx = 1'b1;
        expect_failure(1);
        begin_scenario(0);
        attach_device();
        phy_ready = 1'b0;
        @(negedge clk_ulpi);
        #1;
        check(!connected && !reset_active && !chirp_valid && !csr_valid && !failed, "lost PHY cancels pending reset without replay");
        begin_scenario(0);
        attach_device();
        await_state(16, 10000);
        mac_idle = 1'b0;
        reset_request = 1'b1;
        @(negedge clk_ulpi);
        #1;
        reset_request = 1'b0;
        expect_failure(10);
        $display("PASS workstation_usb2_host_port: %0d checks, %0d scenarios, HS chirps/FS fallback, debounce/recovery/session fencing and failure injection", checks, scenarios);
        $finish;
    end

    initial begin
        #3000000;
        $fatal(1, "global simulation timeout");
    end
endmodule
