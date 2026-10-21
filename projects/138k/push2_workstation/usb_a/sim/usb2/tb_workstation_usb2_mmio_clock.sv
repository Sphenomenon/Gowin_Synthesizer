`timescale 1ns/1ps
module tb_workstation_usb2_mmio_clock;
    reg clk_cpu = 0, clk_ref = 0, clk_ulpi = 0, clock_running = 0, reset_n = 1;
    always #10.417 clk_cpu = !clk_cpu;
    always #10 clk_ref = !clk_ref;
    always #8.333 if (clock_running) clk_ulpi = !clk_ulpi;
    reg cpu_cs = 0, cpu_write = 0;
    reg [7:0] cpu_address = 0;
    reg [31:0] cpu_write_data = 0;
    wire [31:0] cpu_read_data;
    wire cpu_ack, cpu_error;
    wire [7:0] host_data, phy_data;
    wire host_oe, host_stp, phy_oe, phy_dir, phy_nxt, phy_ready, failed;
    tri [7:0] physical_data;
    assign physical_data = host_oe ? host_data : 8'hzz;
    assign physical_data = phy_oe ? phy_data : 8'hzz;
    workstation_usb2_host_mmio host (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n),
        .reg_cs_i(cpu_cs), .reg_wr_i(cpu_write), .reg_addr_i(cpu_address), .reg_wdata_i(cpu_write_data), .reg_be_i(4'hf),
        .reg_ack_o(cpu_ack), .reg_error_o(cpu_error), .reg_rdata_o(cpu_read_data), .irq_o(),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
        .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
        .transaction_reset_n_o(), .phy_ready_o(phy_ready), .failed_o(failed),
        .high_speed_o(), .traffic_enable_o(), .sof_count_o()
    );
    usb3300_register_model #(.HOST_PORT_MODEL(1)) phy (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .fault_i(4'd0), .link_data_i(physical_data),
        .link_data_oe_i(host_oe), .link_stp_i(host_stp), .phy_data_o(phy_data), .phy_data_oe_o(phy_oe),
        .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt), .completed_o(), .scratch_o(),
        .device_line_i(2'b00), .function_o(), .host_chirp_valid_o(), .host_chirp_data_o()
    );
    integer checks = 0;
    task automatic check(input reg condition, input string message);
        begin checks = checks + 1; if (!condition) $fatal(1, "%s", message); end
    endtask
    task automatic access_register(input reg write_enable, input [7:0] address, input [31:0] data, output reg [31:0] value);
        begin
            @(negedge clk_cpu); cpu_cs = 1; cpu_write = write_enable; cpu_address = address; cpu_write_data = data;
            @(negedge clk_cpu); check(cpu_ack && !cpu_error, "CPU bus must answer independently of PHY clock");
            value = cpu_read_data; cpu_cs = 0; @(negedge clk_cpu);
        end
    endtask
    task automatic await_reference_fault(input [31:0] expected);
        integer attempts;
        reg [31:0] value;
        begin
            attempts = 0; value = ~expected;
            while (value != expected && attempts < 5000) begin
                access_register(0, 8'h38, 0, value); attempts = attempts + 1;
            end
            check(value == expected, $sformatf("reference fault expected %0d got %0d raw=%0d enable=%b failed=%b", expected, value,
                  host.clock_failure, host.enable_ref_q, failed));
        end
    endtask
    reg [31:0] scratch;
    initial begin
        #1; reset_n = 0;
        repeat (10) @(negedge clk_cpu); reset_n = 1; repeat (10) @(negedge clk_cpu);
        access_register(1, 4, 3, scratch); await_reference_fault(1);
        check(failed && !host_oe && host_stp, "missing PHY clock isolates physical bus");
        access_register(1, 4, 2, scratch); await_reference_fault(0);
        clock_running = 1; repeat (200) @(negedge clk_cpu); access_register(1, 4, 3, scratch);
        wait (phy_ready); check(!failed, "clock startup and real PHY identity self-test");
        @(negedge clk_ulpi); clock_running = 0; await_reference_fault(2);
        check(failed && !host_oe && host_stp && !phy_ready, "running clock loss isolates physical bus");
        clock_running = 1; repeat (12000) @(negedge clk_cpu);
        access_register(0, 8'h38, 0, scratch); check(scratch == 2 && failed, "clock return does not automatically clear fault");
        access_register(1, 4, 2, scratch); await_reference_fault(0);
        repeat (200) @(negedge clk_cpu); access_register(1, 4, 3, scratch);
        wait (phy_ready); check(!failed, "explicit CPU restart repeats actual PHY self-test");
        $display("PASS workstation_usb2_mmio_clock: %0d checks, actual missing/stopped PHY clock, live CPU diagnostics and restart", checks);
        $finish;
    end
    initial begin #2000000; $fatal(1, "native MMIO clock test timeout"); end
endmodule
