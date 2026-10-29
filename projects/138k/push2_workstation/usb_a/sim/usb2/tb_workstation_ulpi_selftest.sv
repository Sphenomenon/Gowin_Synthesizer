`timescale 1ns/1ps
module tb_workstation_ulpi_selftest;
    reg clk_ref = 0;
    always #10 clk_ref = !clk_ref;
    reg clk_ulpi = 0;
    reg clock_enabled = 1;
    real ulpi_half_period = 8.333;
    always begin
        #(ulpi_half_period);
        if (clock_enabled) clk_ulpi = !clk_ulpi;
    end
    integer scenario = 0;
    reg [3:0] fault = 0;
    wire [7:0] phy_data;
    wire phy_oe, phy_dir, phy_nxt, stp;
    tri [7:0] physical_data;
    assign physical_data = phy_oe ? phy_data : 8'hzz;
    wire [7:0] scratch;
    workstation_ulpi_selftest_top #(
        .POWER_ON_BITS(4), .WINDOW_REF_CYCLES(250), .CLOCK_TIMEOUT_REF_CYCLES(500),
        .EXIT_HOLD_REF_CYCLES(8), .QUALIFY_EDGES(3), .HEARTBEAT_WIDTH(2), .STARTUP_CYCLES(4),
        .TRANSACTION_TIMEOUT_CYCLES(128), .STAGE_TIMEOUT_CYCLES(256)
    ) dut (
        .clk_50m(clk_ref), .usb2_ulpi_clk(clk_ulpi), .usb2_ulpi_dir(phy_dir),
        .usb2_ulpi_nxt(phy_nxt), .usb2_ulpi_stp(stp), .usb2_ulpi_data(physical_data)
    );
    usb3300_register_model phy (
        .clk_ulpi(clk_ulpi), .reset_n(dut.reset_n), .fault_i(fault),
        .link_data_i(physical_data), .link_data_oe_i(dut.link_oe), .link_stp_i(stp),
        .phy_data_o(phy_data), .phy_data_oe_o(phy_oe), .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt),
        .completed_o(), .scratch_o(scratch), .device_line_i(2'b00), .function_o(),
        .host_chirp_valid_o(), .host_chirp_data_o()
    );
    always @(posedge clk_ref)
        if (dut.reset_n && (!dut.clock_running || dut.clock_failed) && (stp !== 1'b1 || dut.link_oe !== 1'b0))
            $fatal(1, "unavailable clock must keep DATA high-impedance and STP high");
    integer waited;
    reg [31:0] snapshots_before;
    initial begin
        if (!$value$plusargs("SCENARIO=%d", scenario)) scenario = 0;
        force dut.reset_n = 1'b1;
        #1;
        release dut.reset_n;
        if (scenario == 1 || scenario == 2) clock_enabled = 0;
        if (scenario == 4) fault = 1;
        if (scenario == 5) fault = 11;
        if (scenario == 6) ulpi_half_period = 16.667;
        if (scenario == 2) begin
            #5000;
            clock_enabled = 1;
        end
        wait (dut.reset_n);
        waited = 0;
        while (waited < 15000 && !dut.status_q[0] && !dut.status_q[1] && !dut.clock_failed) begin
            @(negedge clk_ref);
            waited = waited + 1;
        end
        if (scenario == 1) begin
            repeat (600) @(negedge clk_ref);
            if (!dut.clock_failed || dut.clock_failure != 1 || dut.window_edges_q != 0 ||
                dut.clock_seen_q || dut.snapshot_valid_q || dut.snapshot_updates_q != 0)
                $fatal(1, "missing clock: failed=%b code=%d edges=%d seen=%b valid=%b updates=%d release=%b heartbeat=%b quiet=%d state=%d", dut.clock_failed, dut.clock_failure, dut.window_edges_q, dut.clock_seen_q, dut.snapshot_valid_q, dut.snapshot_updates_q, dut.ulpi_release_q, dut.u_phy.supervisor.heartbeat_sync_q, dut.u_phy.supervisor.quiet_q, dut.u_phy.supervisor.state_q);
        end else if (scenario == 4 || scenario == 5) begin
            if (!dut.snapshot_valid_q || !dut.status_q[1] || dut.status_q[0])
                $fatal(1, "register fault was not reported through a valid snapshot");
            if (scenario == 4 && dut.status_q[12:9] != 4)
                $fatal(1, "bad vendor ID not distinguished");
            if (scenario == 5 && (dut.status_q[12:9] != 5 || dut.status_q[8:4] != 13))
                $fatal(1, "bad AA scratch readback not distinguished");
        end else begin
            if (!dut.snapshot_valid_q || !dut.status_q[0] || dut.status_q[2:1] != 0 ||
                dut.status_q[8:4] != 17 || dut.status_q[47:32] != 16'h0424 ||
                dut.status_q[63:48] != 16'h0004 || dut.status_q[87:64] != 24'h061041 || scratch != 0)
                $fatal(1, "initialization: valid=%b status=%h scratch=%h failed=%b code=%d ulpi_release=%b", dut.snapshot_valid_q, dut.status_q, scratch, dut.clock_failed, dut.clock_failure, dut.ulpi_release_q);
            repeat (1000) @(negedge clk_ref);
            if (scenario == 6) begin
                if (dut.window_edges_q < 148 || dut.window_edges_q > 152 || !dut.clock_seen_q)
                    $fatal(1, "independent clock measurement not approximately 30 MHz");
                if (dut.window_input_toggles_q < 198 || dut.window_input_toggles_q > 202)
                    $fatal(1, "50 MHz input sampler must see approximately 200 transitions for 30 MHz input");
            end else if (dut.window_edges_q < 298 || dut.window_edges_q > 302 || !dut.clock_seen_q)
                $fatal(1, "independent clock measurement not approximately 60 MHz");
            else if (dut.window_input_toggles_q < 98 || dut.window_input_toggles_q > 102)
                $fatal(1, "50 MHz input sampler must see approximately 100 transitions for 60 MHz input");
            if (!((dut.window_input_high_q >= 98 && dut.window_input_high_q <= 102) ||
                  (dut.window_input_high_q >= 148 && dut.window_input_high_q <= 152)))
                $fatal(1, "rational 50 MHz sampling must produce approximately 100 or 150 high samples");
            if (scenario == 3) begin
                clock_enabled = 0;
                repeat (20) @(negedge clk_ref);
                snapshots_before = dut.snapshot_updates_q;
                repeat (1100) @(negedge clk_ref);
                if (!dut.clock_failed || dut.clock_failure != 2 || dut.window_edges_q != 0 ||
                    !dut.clock_seen_q || dut.snapshot_updates_q != snapshots_before)
                    $fatal(1, "stopped clock must not be mistaken for a live successful snapshot");
            end
        end
        $display("PASS ULPI selftest scenario=%0d edges=%0d stage=%0d failure=%0d snapshot=%0d", scenario,
                 dut.window_edges_q, dut.status_q[8:4], dut.status_q[12:9], dut.snapshot_updates_q);
        $finish;
    end
    initial begin
        #10000000;
        $fatal(1, "selftest simulation timeout");
    end
endmodule
