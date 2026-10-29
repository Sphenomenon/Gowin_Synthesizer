`timescale 1ns/1ps
module tb_workstation_usb2_service_adapter;
    reg clk = 0, reset_n = 0, session_valid = 1, connected = 0;
    reg valid = 0, write_request = 0, owner_ready = 1;
    reg [7:0] address = 0;
    reg [31:0] data = 0;
    reg [3:0] mask = 15;
    wire ready, error, owner_select, owner_write;
    wire [7:0] owner_address;
    wire [31:0] owner_data, read_data;
    wire [31:0] canceled_requests;
    integer commits = 0, acknowledgments = 0, checks = 0;
    reg [7:0] last_address;
    reg [31:0] last_data;
    always #10 clk = !clk;
    workstation_usb2_service_adapter dut (
        .clk_cpu(clk), .reset_n(reset_n), .session_valid_i(session_valid), .owner_connected_i(connected),
        .service_valid_i(valid), .service_write_i(write_request), .service_address_i(address),
        .service_write_data_i(data), .service_mask_i(mask), .service_ready_o(ready), .service_error_o(error),
        .service_read_data_o(read_data), .owner_select_o(owner_select), .owner_write_o(owner_write),
        .owner_address_o(owner_address), .owner_write_data_o(owner_data), .owner_ready_i(owner_ready),
        .owner_read_data_i({24'habcdef, owner_address}), .canceled_requests_o(canceled_requests)
    );
    always @(posedge clk) begin
        if (!reset_n) connected <= 0;
        else begin
            if (owner_select && owner_ready) begin
                commits <= commits + 1; last_address <= owner_address; last_data <= owner_data;
                if (owner_write && owner_address == 0) connected <= owner_data[0];
            end
            if (valid && ready) acknowledgments <= acknowledgments + 1;
        end
    end
    task automatic check(input condition, input [767:0] label);
        begin checks = checks + 1; if (!condition) $fatal(1, "adapter %0s", label); end
    endtask
    task automatic start_request(input write_value, input [7:0] address_value,
                                 input [31:0] data_value, input [3:0] mask_value);
        begin
            @(negedge clk); valid = 1; write_request = write_value;
            address = address_value; data = data_value; mask = mask_value;
        end
    endtask
    task automatic complete_request(input expected_error, input expected_commit);
        integer previous_commits, previous_acks, waited;
        begin
            previous_commits = commits; previous_acks = acknowledgments; waited = 0;
            #1;
            while (!ready && waited < 20) begin @(negedge clk); waited = waited + 1; end
            check(ready && error == expected_error, "result/error");
            if (!expected_error && !write_request)
                check(read_data == {24'habcdef, address}, "read data from owner");
            repeat (5) @(negedge clk);
            check(commits == previous_commits + (expected_commit ? 1 : 0), "exactly one owner commit");
            check(acknowledgments == previous_acks + 1, "held valid gets one ACK");
            valid = 0; repeat (3) @(negedge clk);
        end
    endtask
    task automatic interrupted_request(input [7:0] request_address, input [31:0] request_data,
                                        input owner_was_connected);
        integer previous_canceled, previous_commits, previous_acknowledgments;
        begin
            previous_canceled = canceled_requests;
            previous_commits = commits;
            previous_acknowledgments = acknowledgments;
            owner_ready = 0;
            if (!owner_was_connected) session_valid = 0;
            start_request(1, request_address, request_data, 15);
            if (owner_was_connected) begin
                repeat (4) @(negedge clk);
                session_valid = 0;
                repeat (2) @(negedge clk);
            end else @(negedge clk);
            session_valid = 1;
            repeat (2) @(negedge clk);
            if (owner_was_connected) begin
                check(owner_select && owner_write && owner_address == 0 && owner_data == 0,
                      "lost-session detach remains pending after transport recovers");
                owner_ready = 1;
                @(negedge clk);
                check(!connected && last_address == 0 && last_data == 0,
                      "old owner detaches before stale request completes");
            end else begin
                check(!owner_select, "stale attach cannot revive after transport recovers");
                owner_ready = 1;
            end
            repeat (5) @(negedge clk);
            check(commits == previous_commits + (owner_was_connected ? 1 : 0),
                  "only pending detach commits after interrupted request");
            check(acknowledgments == previous_acknowledgments + 1,
                  "interrupted request acknowledges exactly once");
            check(canceled_requests == previous_canceled + 1, "interrupted request counted exactly once");
            check(!connected, "interrupted request does not attach a new owner");
            valid = 0;
            repeat (3) @(negedge clk);
        end
    endtask
    initial begin
        repeat (3) @(negedge clk); reset_n = 1;
        start_request(0, 8'h20, 0, 15); complete_request(0, 1);
        start_request(1, 8'h00, 7, 15); complete_request(0, 1);
        check(connected, "connect reaches owner");
        for (integer mask_value = 0; mask_value < 15; mask_value = mask_value + 1) begin
            start_request(1, 8'h54, 32'h00004e64, 4'(mask_value)); complete_request(1, 0);
        end
        for (integer offset = 1; offset < 4; offset = offset + 1) begin
            start_request(0, 8'h20 + 8'(offset), 0, 15); complete_request(1, 0);
        end
        start_request(1, 8'h50, 1, 15); complete_request(1, 0);
        start_request(1, 8'hf0, 1, 15); complete_request(1, 0);
        owner_ready = 0;
        start_request(1, 8'h54, 32'h00004e64, 15);
        repeat (8) @(negedge clk);
        check(!ready && owner_select && owner_address == 8'h54 && owner_data == 32'h00004e64,
              "stalled request preserved");
        owner_ready = 1; complete_request(0, 1);
        owner_ready = 0;
        start_request(1, 8'h54, 32'h00004e64, 15);
        repeat (4) @(negedge clk);
        begin
            integer previous_commits;
            previous_commits = commits; valid = 0;
            #1; check(!owner_select, "withdrawal cancels immediately");
            owner_ready = 1; repeat (4) @(negedge clk);
            check(commits == previous_commits, "no late commit after timeout");
        end
        owner_ready = 0;
        start_request(1, 8'h54, 32'h00004e64, 15);
        repeat (4) @(negedge clk);
        session_valid = 0; #1;
        check(owner_select && owner_write && owner_address == 0 && owner_data == 0,
              "disconnect preempts pending event");
        owner_ready = 1;
        @(negedge clk);
        check(!connected && last_address == 0 && last_data == 0, "hardware detach commits");
        complete_request(0, 0);
        start_request(1, 8'h00, 7, 15); complete_request(0, 0);
        session_valid = 1;
        start_request(1, 8'h54, 32'h00004e64, 15); complete_request(0, 0);
        start_request(1, 8'h00, 7, 15); complete_request(0, 1);
        start_request(1, 8'h54, 32'h00004e64, 15); complete_request(0, 1);
        start_request(1, 8'h00, 0, 15); complete_request(0, 1);
        start_request(0, 8'h6c, 0, 15); complete_request(0, 1);
        check(canceled_requests == 4, "withdrawal and three stale writes counted");
        interrupted_request(8'h00, 7, 0);
        start_request(1, 8'h00, 7, 15); complete_request(0, 1);
        interrupted_request(8'h54, 32'h00004e64, 1);
        start_request(1, 8'h00, 1, 15); complete_request(0, 1);
        interrupted_request(8'h04, 32'h00004f64, 1);
        start_request(1, 8'h00, 1, 15); complete_request(0, 1);
        start_request(1, 8'h54, 32'h00005064, 15); complete_request(0, 1);
        check(connected && canceled_requests == 7, "fresh Push request succeeds after interrupted sessions");
        $display("PASS workstation_usb2_service_adapter: %0d checks, exact-once, bounds, withdrawal, hardware detach, transient session loss and reattach", checks);
        $finish;
    end
    initial begin #100000; $fatal(1, "adapter timeout"); end
endmodule
