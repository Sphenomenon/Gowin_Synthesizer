`timescale 1ns/1ps
module tb_workstation_usb3300_host_link;
    reg clk_ref = 1'b0;
    always #10 clk_ref = ~clk_ref;
    reg clk_ulpi = 1'b0;
    reg clock_enabled = 1'b1;
    always begin
        #8.333;
        if (clock_enabled)
            clk_ulpi = !clk_ulpi;
    end
    reg reset_n = 1'b0;
    reg enable = 1'b0;
    reg [3:0] fault = 0;
    reg csr_valid = 1'b0;
    reg csr_write = 1'b1;
    reg [5:0] csr_address = 6'h16;
    reg [7:0] csr_data = 8'h3c;
    reg response_ready = 1'b0;
    wire [7:0] link_data;
    wire link_oe;
    wire link_stp;
    wire [7:0] phy_data;
    wire phy_oe;
    wire phy_dir;
    wire phy_nxt;
    tri [7:0] physical_data;
    assign physical_data = link_oe ? link_data : 8'hzz;
    assign physical_data = phy_oe ? phy_data : 8'hzz;
    wire ready;
    wire clock_running;
    wire clock_present;
    wire clock_failed;
    wire [1:0] clock_failure_code;
    wire init_failed;
    wire [3:0] init_failure_code;
    wire [4:0] init_stage;
    wire [7:0] init_retry_count;
    wire [7:0] init_last_data;
    wire [2:0] init_last_error;
    wire [15:0] vendor_id;
    wire [15:0] product_id;
    wire [7:0] function_control;
    wire [7:0] interface_control;
    wire [7:0] otg_control;
    wire csr_ready;
    wire response_valid;
    wire [7:0] response_data;
    wire [2:0] response_error;
    wire link_reset_n;
    wire tx_ready;
    wire rx_valid;
    wire rx_active;
    wire rx_error;
    wire link_fatal;
    wire [31:0] received_bytes;
    wire [31:0] transmitted_bytes;
    wire [15:0] completed;
    wire [7:0] scratch;
    integer checks = 0;
    integer scenarios = 0;

    workstation_usb3300_host_link #(
        .HEARTBEAT_WIDTH(2), .EXIT_HOLD_REF_CYCLES(8), .QUALIFY_EDGES(3),
        .CLOCK_TIMEOUT_REF_CYCLES(40), .STARTUP_CYCLES(4),
        .TRANSACTION_TIMEOUT_CYCLES(64), .STAGE_TIMEOUT_CYCLES(128)
    ) dut (
        .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .enable_i(enable),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
        .ulpi_data_o(link_data), .ulpi_data_oe_o(link_oe), .ulpi_stp_o(link_stp),
        .link_reset_n_o(link_reset_n), .ready_o(ready), .clock_running_o(clock_running),
        .clock_present_o(clock_present), .clock_failed_o(clock_failed), .clock_failure_code_o(clock_failure_code),
        .init_failed_o(init_failed), .init_failure_code_o(init_failure_code), .init_stage_o(init_stage),
        .init_retry_count_o(init_retry_count), .init_last_data_o(init_last_data), .init_last_error_o(init_last_error),
        .vendor_id_o(vendor_id), .product_id_o(product_id), .function_control_o(function_control),
        .interface_control_o(interface_control), .otg_control_o(otg_control),
        .csr_valid_i(csr_valid), .csr_ready_o(csr_ready), .csr_write_i(csr_write),
        .csr_address_i(csr_address), .csr_data_i(csr_data), .csr_response_valid_o(response_valid),
        .csr_response_ready_i(response_ready), .csr_response_data_o(response_data), .csr_response_error_o(response_error),
        .utmi_data_i(8'h69), .utmi_txvalid_i(!ready), .utmi_tx_nopid_i(1'b0), .utmi_txready_o(tx_ready),
        .utmi_data_o(), .utmi_rxvalid_o(rx_valid), .utmi_rxactive_o(rx_active), .utmi_rxerror_o(rx_error),
        .utmi_linestate_o(), .vbus_state_o(), .id_state_o(), .host_disconnect_o(),
        .tx_abort_o(), .link_fatal_o(link_fatal), .received_bytes_o(received_bytes),
        .transmitted_bytes_o(transmitted_bytes), .rxcmd_count_o()
    );
    usb3300_register_model phy (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .fault_i(fault),
        .link_data_i(physical_data), .link_data_oe_i(link_oe), .link_stp_i(link_stp),
        .phy_data_o(phy_data), .phy_data_oe_o(phy_oe), .phy_dir_o(phy_dir),
        .phy_nxt_o(phy_nxt), .completed_o(completed), .scratch_o(scratch)
    );

    task automatic check(input reg condition, input string message);
        begin
            checks = checks + 1;
            if (condition !== 1'b1)
                $fatal(1, "%s (stage=%0d initfail=%0d clockfail=%0d)", message, init_stage, init_failure_code, clock_failure_code);
        end
    endtask

    task automatic begin_scenario(input reg start_clock, input reg [3:0] requested_fault);
        begin
            @(negedge clk_ref);
            reset_n = 1'b0;
            enable = 1'b0;
            clock_enabled = start_clock;
            csr_valid = 1'b1;
            csr_write = 1'b1;
            csr_address = 6'h16;
            csr_data = 8'h3c;
            response_ready = 1'b0;
            fault = requested_fault;
            repeat (4) @(negedge clk_ref);
            check(!ready && !link_oe && link_stp && !csr_ready && !response_valid, "reset closes all client gates");
            reset_n = 1'b1;
            enable = 1'b1;
            scenarios = scenarios + 1;
        end
    endtask

    task automatic await_ready(input reg [7:0] expected_retries);
        integer waited;
        begin
            waited = 0;
            while (!ready && !init_failed && !clock_failed && waited < 2000) begin
                @(negedge clk_ulpi);
                check(!response_valid && !tx_ready, "initialization is not a runtime response or packet acceptance");
                waited = waited + 1;
            end
            check(ready && clock_present && clock_running && !init_failed && !link_fatal, "supervised initialization ready");
            check(vendor_id == 16'h0424 && product_id == 16'h0004, "identity delivered");
            check(function_control == 8'h41 && interface_control == 8'h10 && otg_control == 8'h06, "host configuration delivered");
            check(init_stage == 17 && init_retry_count == expected_retries && init_last_data == 8'h41 && init_last_error == 0,
                  "initialization evidence delivered");
        end
    endtask

    task automatic await_response(input reg [7:0] expected_data);
        integer waited;
        begin
            waited = 0;
            while (!response_valid && waited < 200) begin
                @(negedge clk_ulpi);
                waited = waited + 1;
            end
            check(response_valid && response_error == 0 && response_data == expected_data, "runtime response correct");
            repeat (4) begin
                @(negedge clk_ulpi);
                check(response_valid && response_error == 0 && response_data == expected_data && ready, "runtime response held under backpressure");
            end
            response_ready = 1'b1;
            @(negedge clk_ulpi);
            response_ready = 1'b0;
            check(!response_valid, "runtime response consumed exactly once");
        end
    endtask

    task automatic submit_runtime_read;
        begin
            @(negedge clk_ulpi);
            csr_write = 1'b0;
            csr_valid = 1'b1;
            while (!csr_ready) @(negedge clk_ulpi);
            @(negedge clk_ulpi);
            csr_valid = 1'b0;
        end
    endtask

    always @(posedge clk_ulpi) begin
        if (reset_n) begin
            check(!(link_oe && phy_oe), "no board bus contention");
            check(!rx_valid && !rx_active && !rx_error && received_bytes == 0 && transmitted_bytes == 0,
                  "register bringup does not become USB traffic");
            if (!ready)
                check(!csr_ready && !response_valid && !tx_ready, "unready client fencing");
            if (init_failed || link_fatal || clock_failed)
                check(!link_oe && link_stp, "failure forces STP and tri-state data");
        end
    end

    initial begin
        begin_scenario(1'b1, 0);
        await_ready(0);
        check(completed == 18 && scratch == 0, "early client cannot corrupt initialization script");
        @(negedge clk_ulpi);
        csr_valid = 1'b0;
        await_response(0);
        check(completed == 19 && scratch == 8'h3c, "runtime CSR takes ownership after initialization");
        submit_runtime_read();
        await_response(8'h3c);
        @(negedge clk_ulpi);
        clock_enabled = 1'b0;
        repeat (50) @(negedge clk_ref);
        check(clock_failed && clock_failure_code == 2 && !ready && !link_reset_n && !link_oe && link_stp,
              "stopped clock asynchronously cancels complete composition");
        clock_enabled = 1'b1;
        repeat (60) @(negedge clk_ref);
        check(clock_failed && !ready, "failed link does not restart from clock return alone");
        enable = 1'b0;
        repeat (5) @(negedge clk_ref);
        enable = 1'b1;
        await_ready(0);
        check(completed == 38 && scratch == 0, "explicit restart rechecks warm PHY without physical PHY reset");
        begin_scenario(1'b1, 1);
        wait (init_failed);
        @(negedge clk_ulpi);
        check(init_failure_code == 4 && init_stage == 0 && !ready && !link_oe && link_stp,
              "bad identity safely blocks bus and client handoff");
        begin_scenario(1'b0, 0);
        repeat (60) @(negedge clk_ref);
        check(clock_failed && clock_failure_code == 1 && !ready && !link_oe && link_stp,
              "no PHY clock cannot hang CPU-visible readiness");
        begin_scenario(1'b1, 0);
        await_ready(0);
        @(negedge clk_ulpi);
        csr_valid = 1'b0;
        await_response(0);
        fault = 6;
        submit_runtime_read();
        wait (link_fatal);
        @(negedge clk_ulpi);
        check(!ready && !link_oe && link_stp && !response_valid,
              "runtime fatal is explicit cancellation, not a successful stale CSR response");
        @(negedge clk_ulpi);
        check(init_failed && init_failure_code == 1, "runtime fatal diagnostic follows on the next ULPI edge");
        begin_scenario(1'b1, 7);
        await_ready(1);
        $display("PASS workstation_usb3300_host_link: %0d checks, %0d scenarios, real composition/CSR handoff, warm recovery, missing clock and runtime cancellation", checks, scenarios);
        $finish;
    end

    initial begin
        #1000000;
        $fatal(1, "global simulation timeout");
    end
endmodule
