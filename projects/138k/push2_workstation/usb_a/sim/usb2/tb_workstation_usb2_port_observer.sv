`timescale 1ns/1ps
module tb_workstation_usb2_port_observer;
    reg clock = 0;
    always #10 clock = !clock;
    reg reset_n = 0;
    reg [7:0] ulpi_data = 0;
    reg ulpi_dir = 0, ulpi_nxt = 0;
    workstation_usb2_host_mmio #(.PORT_OBSERVER(1)) dut (
        .clk_cpu(clock), .clk_ref(clock), .clk_ulpi(clock), .reset_n(reset_n),
        .reg_cs_i(1'b0), .reg_wr_i(1'b0), .reg_addr_i(8'd0), .reg_wdata_i(32'd0), .reg_be_i(4'd0),
        .ulpi_data_i(ulpi_data), .ulpi_dir_i(ulpi_dir), .ulpi_nxt_i(ulpi_nxt)
    );
    initial begin
        force dut.port_state = 0;
        force dut.port_failure = 0;
        force dut.phy_ready_o = 0;
        force dut.unused_function = 0;
        force dut.unused_received = 0;
        force dut.unused_transmitted = 0;
        force dut.sof_count_o = 0;
        repeat (4) @(negedge clock);
        reset_n = 1;
        repeat (4) @(negedge clock);
        force dut.phy_ready_o = 1;
        force dut.port_state = 13;
        force dut.unused_function = 8'h50;
        force dut.unused_transmitted = 123456;
        repeat (2) @(negedge clock);
        force dut.port_state = 18;
        force dut.port_failure = 7;
        repeat (3) @(negedge clock);
        force dut.phy_ready_o = 0;
        force dut.port_state = 0;
        force dut.port_failure = 0;
        force dut.unused_function = 0;
        force dut.unused_transmitted = 0;
        repeat (3) @(negedge clock);
        if (!dut.state_history_q[13] || !dut.state_history_q[18] ||
            !dut.failure_history_q[7] || dut.last_failure_q != 7 ||
            dut.last_failure_state_q != 13 || dut.last_failure_function_q != 8'h50 ||
            dut.transmitted_peak_q != 123456 || dut.attempts_q != 1)
            $fatal(1, "port diagnostic evidence was lost across a Host retry");
        force dut.phy_ready_o = 1;
        repeat (3) @(negedge clock);
        if (dut.attempts_q != 2)
            $fatal(1, "retry counter did not advance");
        force dut.connected = 1;
        force dut.high_speed_o = 1;
        force dut.failed_o = 0;
        force dut.mac_failed = 0;
        force dut.phy_failed = 0;
        force dut.reset_active = 0;
        force dut.sof_enable = 1;
        force dut.unused_function = 8'h40;
        force dut.port_state = 15;
        force dut.ulpi_stp_o = 0;
        ulpi_dir = 1;
        ulpi_data = 8'h30;
        repeat (4) @(negedge clock);
        ulpi_dir = 0;
        ulpi_nxt = 1;
        force dut.ulpi_data_oe_o = 1;
        force dut.ulpi_data_o = 8'h45;
        @(negedge clock);
        force dut.ulpi_data_o = 8'h00;
        @(negedge clock);
        force dut.ulpi_data_o = 8'h10;
        @(negedge clock);
        ulpi_nxt = 0;
        force dut.sof_count_o = 12;
        repeat (2) @(negedge clock);
        force dut.port_state = 1;
        repeat (2) @(negedge clock);
        force dut.phy_ready_o = 0;
        force dut.port_state = 0;
        force dut.sof_count_o = 0;
        force dut.unused_function = 0;
        repeat (3) @(negedge clock);
        if (dut.recovery_count_q != 1 || dut.recovery_aborts_q != 1 || dut.active_count_q != 0 ||
            dut.recovery_exit_ticks_q != 9 || dut.recovery_exit_sofs_q != 12 ||
            dut.recovery_exit_state_q != 1 || dut.recovery_exit_rxcmd_q != 8'h30 ||
            dut.recovery_exit_function_q != 8'h40 || dut.recovery_exit_flags_q != 8'he1 ||
            dut.last_sof_token_q != 16'h1000 || dut.command_count_q != 0)
            $fatal(1, "recovery exit evidence was lost or decoded incorrectly: ticks=%0d flags=%h rxcmd=%h token=%h",
                   dut.recovery_exit_ticks_q, dut.recovery_exit_flags_q, dut.recovery_exit_rxcmd_q, dut.last_sof_token_q);
        force dut.port_state = 15;
        repeat (2) @(negedge clock);
        force dut.port_state = 16;
        repeat (2) @(negedge clock);
        if (dut.recovery_count_q != 2 || dut.recovery_aborts_q != 1 || dut.active_count_q != 1 ||
            dut.recovery_exit_state_q != 16 || dut.recovery_exit_ticks_q != 2)
            $fatal(1, "successful recovery was counted as an abort");
        force dut.command_valid = 1;
        force dut.command_ready = 1;
        force dut.command_pid = 8'h2d;
        force dut.command_device = 1;
        force dut.command_endpoint = 0;
        force dut.command_toggle = 0;
        force dut.command_length = 8;
        force dut.result_valid = 1;
        force dut.result_ready = 1;
        force dut.result_status = 3;
        force dut.result_pid = 0;
        force dut.result_length = 0;
        @(negedge clock);
        force dut.command_valid = 0;
        force dut.result_valid = 0;
        @(negedge clock);
        if (dut.command_count_q != 1 || dut.last_command_q != {2'd0,8'h2d,7'd1,4'd0,1'b0,10'd8} ||
            dut.last_result_q != {2'd0,4'd3,8'd0,10'd0})
            $fatal(1, "EP0 command and result diagnostics did not survive the handshake");
        reset_n = 0;
        repeat (3) @(negedge clock);
        if (dut.state_history_q != 0 || dut.attempts_q != 0 ||
            dut.failure_history_q != 0 || dut.transmitted_peak_q != 0 ||
            dut.recovery_count_q != 0 || dut.command_count_q != 0 || dut.recovery_exit_rxcmd_q != 0)
            $fatal(1, "global reset did not clear port diagnostics");
        $display("PASS workstation_usb2_port_observer: sticky failure, recovery timing/RXCMD/SOF, EP0, retry and reset");
        $finish;
    end
endmodule
