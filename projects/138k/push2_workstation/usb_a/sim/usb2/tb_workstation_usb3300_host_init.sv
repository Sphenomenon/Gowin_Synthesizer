`timescale 1ns/1ps
module tb_workstation_usb3300_host_init;
    reg clk_ulpi = 1'b0;
    always #8.333 clk_ulpi = ~clk_ulpi;
    reg reset_n = 1'b0;
    reg [3:0] fault = 0;
    reg block_requests = 1'b0;
    reg block_responses = 1'b0;
    reg force_fatal = 1'b0;
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
    wire csr_valid;
    wire csr_ready;
    wire csr_write;
    wire [5:0] csr_address;
    wire [7:0] csr_data;
    wire response_valid;
    wire response_ready;
    wire [7:0] response_data;
    wire [2:0] response_error;
    wire link_fatal;
    wire ready;
    wire failed;
    wire [3:0] failure_code;
    wire [4:0] stage;
    wire [7:0] retry_count;
    wire [7:0] last_data;
    wire [2:0] last_error;
    wire [15:0] vendor_id;
    wire [15:0] product_id;
    wire [7:0] function_control;
    wire [7:0] interface_control;
    wire [7:0] otg_control;
    wire [15:0] completed;
    wire [7:0] scratch;
    wire rx_valid;
    integer checks = 0;
    integer scenarios = 0;
    reg [14:0] request_snapshot;
    reg request_stalled = 1'b0;

    workstation_ulpi_link #(.TRANSACTION_TIMEOUT_CYCLES(64)) link (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .ulpi_data_i(physical_data),
        .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt), .ulpi_data_o(link_data),
        .ulpi_data_oe_o(link_oe), .ulpi_stp_o(link_stp),
        .csr_valid_i(csr_valid && !block_requests), .csr_ready_o(csr_ready),
        .csr_write_i(csr_write), .csr_address_i(csr_address), .csr_data_i(csr_data),
        .csr_response_valid_o(response_valid), .csr_response_ready_i(response_ready && !block_responses),
        .csr_response_data_o(response_data), .csr_response_error_o(response_error),
        .utmi_data_i(8'h00), .utmi_txvalid_i(1'b0), .utmi_tx_nopid_i(1'b0),
        .utmi_txready_o(), .utmi_data_o(), .utmi_rxvalid_o(rx_valid),
        .utmi_rxactive_o(), .utmi_rxerror_o(), .utmi_linestate_o(), .vbus_state_o(),
        .id_state_o(), .host_disconnect_o(), .tx_abort_o(), .fatal_error_o(link_fatal),
        .received_bytes_o(), .transmitted_bytes_o(), .rxcmd_count_o()
    );
    workstation_usb3300_host_init #(
        .STARTUP_CYCLES(4), .STAGE_TIMEOUT_CYCLES(128), .MAX_PREEMPT_RETRIES(2)
    ) init (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .link_fatal_i(link_fatal || force_fatal),
        .csr_valid_o(csr_valid), .csr_ready_i(csr_ready && !block_requests),
        .csr_write_o(csr_write), .csr_address_o(csr_address), .csr_data_o(csr_data),
        .csr_response_valid_i(response_valid && !block_responses), .csr_response_ready_o(response_ready),
        .csr_response_data_i(response_data), .csr_response_error_i(response_error),
        .ready_o(ready), .failed_o(failed), .failure_code_o(failure_code), .stage_o(stage),
        .retry_count_o(retry_count), .last_data_o(last_data), .last_error_o(last_error),
        .vendor_id_o(vendor_id), .product_id_o(product_id), .function_control_o(function_control),
        .interface_control_o(interface_control), .otg_control_o(otg_control)
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
                $fatal(1, "%s (fault=%0d stage=%0d failure=%0d)", message, fault, stage, failure_code);
        end
    endtask

    task automatic begin_scenario(input reg [3:0] requested_fault);
        begin
            @(negedge clk_ulpi);
            reset_n = 1'b0;
            fault = requested_fault;
            block_requests = 1'b0;
            block_responses = 1'b0;
            force_fatal = 1'b0;
            repeat (3) @(negedge clk_ulpi);
            check(!ready && !failed && !link_oe && link_stp, "reset safety");
            reset_n = 1'b1;
            scenarios = scenarios + 1;
        end
    endtask

    task automatic await_terminal;
        integer waited;
        begin
            waited = 0;
            while (!ready && !failed && waited < 2000) begin
                @(negedge clk_ulpi);
                waited = waited + 1;
            end
            check(ready || failed, "initialization is bounded");
            check(!(ready && failed), "ready/failure exclusive");
        end
    endtask

    task automatic expect_failure(input reg [3:0] expected_code, input reg [4:0] expected_stage);
        begin
            await_terminal();
            check(failed && !ready, "failure latched");
            check(failure_code == expected_code && stage == expected_stage, "failure location");
            repeat (5) begin
                @(negedge clk_ulpi);
                check(failed && !ready && !csr_valid && !response_ready, "failure requires reset");
            end
        end
    endtask

    task automatic expect_success(input reg [7:0] expected_retries);
        begin
            await_terminal();
            check(ready && !failed && failure_code == 0 && stage == 17, "all stages completed");
            check(completed == 18 && scratch == 0, "physical script and scratch restore");
            check(vendor_id == 16'h0424 && product_id == 16'h0004, "physical identity readback");
            check(function_control == 8'h41 && interface_control == 8'h10 && otg_control == 8'h06,
                  "host control readback");
            check(last_data == 8'h41 && last_error == 0 && retry_count == expected_retries, "diagnostic snapshot");
            repeat (5) begin
                @(negedge clk_ulpi);
                check(ready && !csr_valid && !response_ready && !link_fatal, "handoff is quiescent");
            end
        end
    endtask

    always @(posedge clk_ulpi) begin
        if (reset_n) begin
            check(ready === (!link_fatal && !force_fatal && init.state_q == 3), "registered ready matches the completed state");
            check(!(link_oe && phy_oe), "no physical contention");
            check(!rx_valid, "register response is not a USB packet");
            if (request_stalled && csr_valid)
                check({csr_write, csr_address, csr_data} == request_snapshot, "stalled request stable");
            request_stalled <= csr_valid && !(csr_ready && !block_requests);
            request_snapshot <= {csr_write, csr_address, csr_data};
        end else
            request_stalled <= 1'b0;
    end

    initial begin
        begin_scenario(0);
        expect_success(0);
        @(negedge clk_ulpi);
        force_fatal = 1'b1;
        #1;
        check(!ready, "link failure immediately revokes readiness");
        expect_failure(1, 17);
        begin_scenario(1);
        expect_failure(4, 0);
        check(vendor_id[7:0] == 0 && completed == 1, "bad identity prevents writes");
        begin_scenario(2);
        expect_failure(5, 11);
        begin_scenario(3);
        expect_failure(5, 7);
        begin_scenario(4);
        expect_failure(5, 9);
        begin_scenario(5);
        expect_failure(5, 5);
        begin_scenario(6);
        expect_failure(1, 0);
        check(last_error == 1, "link timeout retained");
        begin_scenario(7);
        expect_success(1);
        begin_scenario(8);
        expect_failure(6, 0);
        check(retry_count == 2 && completed == 0 && last_error == 2, "retry limit and no side effects");
        begin_scenario(9);
        expect_failure(1, 0);
        begin_scenario(10);
        expect_failure(1, 4);
        check(completed == 4 && last_error == 2 && retry_count == 0, "partial write never retried");
        begin_scenario(11);
        expect_failure(5, 13);
        begin_scenario(12);
        expect_failure(5, 17);
        begin_scenario(13);
        expect_failure(4, 3);
        check(completed == 4 && product_id == 16'h0104, "full product identity checked before writes");
        begin_scenario(14);
        expect_failure(5, 15);
        begin_scenario(0);
        block_requests = 1'b1;
        expect_failure(2, 0);
        check(completed == 0 && !link_fatal, "request starvation bounded independently");
        begin_scenario(0);
        block_responses = 1'b1;
        expect_failure(2, 0);
        check(response_valid && completed == 1 && !link_fatal, "response starvation bounded independently");
        begin_scenario(0);
        wait (csr_valid && csr_write);
        @(negedge clk_ulpi);
        reset_n = 1'b0;
        #1;
        check(!ready && !failed && !link_oe && link_stp, "mid-script reset is safe");
        begin_scenario(0);
        expect_success(0);
        $display("PASS workstation_usb3300_host_init: %0d checks, %0d scenarios, physical ID/scratch/host readback, bounded retries/failures", checks, scenarios);
        $finish;
    end

    initial begin
        #1000000;
        $fatal(1, "global simulation timeout");
    end
endmodule
