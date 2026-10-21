`timescale 1ns/1ps
module tb_workstation_usb2_cpu_bus;
    reg clk = 0, reset_n = 0;
    always #10.417 clk = !clk;
    reg instruction_valid = 0;
    reg [31:0] instruction_address = 0;
    wire instruction_ready, instruction_response, instruction_error;
    wire [31:0] instruction_data;
    reg data_valid = 0, data_write = 0;
    reg [31:0] data_address = 0, data_write_data = 0;
    reg [3:0] data_mask = 15;
    wire data_ready, data_response;
    wire [31:0] data_read_data;
    wire usb_cs, usb_write, service_valid, service_write;
    wire [7:0] usb_address, service_address;
    wire [31:0] usb_write_data, service_write_data;
    wire [3:0] usb_mask, service_mask, fault;
    wire [31:0] fault_address;
    reg usb_ack = 0, usb_error = 0, service_ready = 0, service_error = 0;
    integer checks = 0, usb_count = 0, service_count = 0;
    workstation_usb2_cpu_bus #(.BUS_TIMEOUT_CYCLES(32)) dut (
        .clk_cpu(clk), .reset_n(reset_n),
        .instruction_valid_i(instruction_valid), .instruction_ready_o(instruction_ready), .instruction_address_i(instruction_address),
        .instruction_response_o(instruction_response), .instruction_error_o(instruction_error), .instruction_data_o(instruction_data),
        .data_valid_i(data_valid), .data_ready_o(data_ready), .data_write_i(data_write), .data_address_i(data_address),
        .data_write_data_i(data_write_data), .data_mask_i(data_mask), .data_response_o(data_response), .data_read_data_o(data_read_data),
        .uart_rx_i(1'b1), .uart_tx_o(), .usb_cs_o(usb_cs), .usb_write_o(usb_write), .usb_address_o(usb_address),
        .usb_write_data_o(usb_write_data), .usb_mask_o(usb_mask), .usb_ack_i(usb_ack), .usb_error_i(usb_error), .usb_read_data_i(32'hcafebabe),
        .service_valid_o(service_valid), .service_write_o(service_write), .service_address_o(service_address),
        .service_write_data_o(service_write_data), .service_mask_o(service_mask),
        .service_ready_i(service_ready), .service_error_i(service_error), .service_read_data_i(32'h12345678),
        .fault_o(fault), .fault_address_o(fault_address)
    );
    always @(posedge clk) begin
        if (usb_cs && usb_ack) usb_count = usb_count + 1;
        if (service_valid && service_ready) service_count = service_count + 1;
    end
    task automatic check(input reg condition, input string message);
        begin checks = checks + 1; if (!condition) $fatal(1, "%s", message); end
    endtask
    task automatic command(input reg write_enable, input [31:0] address, input [31:0] value, input [3:0] mask);
        begin
            @(negedge clk); data_valid = 1; data_write = write_enable; data_address = address; data_write_data = value; data_mask = mask;
            while (!data_ready) @(negedge clk);
            @(negedge clk); data_valid = 0;
        end
    endtask
    task automatic read_word(input [31:0] address, input [31:0] expected);
        integer deadline;
        begin
            command(0, address, 0, 0); deadline = 0;
            while (!data_response && deadline < 64) begin @(negedge clk); deadline = deadline + 1; end
            check(data_response && data_read_data === expected, $sformatf("read %08x expected %08x got %08x", address, expected, data_read_data));
        end
    endtask
    initial begin
        repeat (5) @(negedge clk); reset_n = 1;
        read_word(32'h02000060, 32'h55324301);
        command(1, 32'h00000100, 32'h12345678, 15);
        command(1, 32'h00000101, 32'h0000ab00, 2);
        command(1, 32'h00000102, 32'hcdef0000, 12);
        read_word(32'h00000100, 32'hcdefab78);
        @(negedge clk); instruction_valid = 1; instruction_address = 32'h100;
        @(negedge clk); check(instruction_response && !instruction_error && instruction_data == 32'hcdefab78, "instruction synchronous RAM response");
        instruction_valid = 0;
        command(0, 32'h02000118, 0, 0);
        check(usb_cs && usb_address == 8'h18 && !usb_write, "USB request captured");
        repeat (5) begin @(negedge clk); check(!data_ready && usb_cs && usb_address == 8'h18, "USB backpressure holds request"); end
        usb_ack = 1; @(negedge clk); usb_ack = 0;
        check(data_response && data_read_data == 32'hcafebabe && !usb_cs, "USB response delivered once");
        @(negedge clk); check(!data_response && data_ready, "USB CS release cycle completed");
        command(1, 32'h02000110, 32'h5a, 1);
        check(usb_write && usb_mask == 1 && usb_write_data == 32'h5a, "USB byte write captured");
        usb_error = 1; usb_ack = 1; @(negedge clk); usb_ack = 0; usb_error = 0;
        check(!data_response && fault[1] && fault_address == 32'h02000110, "posted USB store error is observable");
        read_word(32'h02000058, 2); command(1, 32'h02000058, 15, 15); read_word(32'h02000058, 0);
        command(0, 32'h02000240, 0, 0);
        check(service_valid && !service_write && service_address == 8'h40, "workstation service request captured");
        @(negedge clk); instruction_valid = 1; instruction_address = 32'h100;
        @(negedge clk); check(instruction_response && instruction_data == 32'hcdefab78, "instruction fetch continues during MMIO wait");
        instruction_valid = 0; service_ready = 1; @(negedge clk); service_ready = 0;
        check(data_response && data_read_data == 32'h12345678, "service read response");
        command(0, 32'h02000280, 0, 0);
        repeat (34) @(negedge clk);
        check(fault[2] && fault_address == 32'h02000280 && !service_valid, "bounded service timeout");
        command(1, 32'h02000058, 15, 15); read_word(32'h02000058, 0);
        read_word(32'h00010100, 0); check(fault[0] && fault_address == 32'h00010100, "RAM address does not alias above 64 KiB");
        command(1, 32'h02000058, 15, 15);
        command(1, 32'h02000050, 1, 15); check(fault[0], "read-only timer writes are rejected");
        command(1, 32'h02000058, 15, 15);
        @(negedge clk); instruction_valid = 1; instruction_address = 32'h10000;
        @(negedge clk); check(instruction_error && fault[3], "bad instruction fetch is visible"); instruction_valid = 0;
        check(usb_count == 2 && service_count == 1, "targets see no duplicate transaction");
        $display("PASS workstation_usb2_cpu_bus: %0d checks, RAM lanes/arbitration/posted-store errors/timeout", checks);
        $finish;
    end
    initial begin #100000; $fatal(1, "CPU bus timeout"); end
endmodule
