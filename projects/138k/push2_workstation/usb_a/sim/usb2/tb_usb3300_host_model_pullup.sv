`timescale 1ns/1ps
module tb_usb3300_host_model_pullup;
    reg clk = 0, reset_n = 0, attached = 1, device_term = 1, device_chirp = 0;
    reg [1:0] device_xcvr = 0;
    reg [7:0] link_data = 0;
    reg link_oe = 0, link_stp = 0;
    wire [7:0] function_control;
    wire [1:0] device_line;
    wire phy_dir, phy_nxt;
    integer checks = 0;
    always #8.333 clk = !clk;
    usb3300_host_model #(.HIGH_SPEED(0)) phy (
        .clk_ulpi(clk), .reset_n(reset_n), .runtime_i(1'b0), .attached_i(attached), .stall_i(1'b0),
        .link_data_i(link_data), .link_oe_i(link_oe), .link_stp_i(link_stp),
        .phy_data_o(), .phy_oe_o(), .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt),
        .device_txdata_i(8'd0), .device_txvalid_i(1'b0), .device_chirp_i(device_chirp),
        .device_xcvr_i(device_xcvr), .device_term_i(device_term), .device_txready_o(),
        .device_rxdata_o(), .device_rxvalid_o(), .device_rxactive_o(), .device_line_o(device_line),
        .function_o(function_control), .normal_packets_o()
    );

    task automatic expect_line(input [1:0] expected);
        begin
            #1;
            if (device_line !== expected)
                $fatal(1, "pullup function=%x term=%b xcvr=%0d chirp=%b line=%b expected=%b",
                       function_control, device_term, device_xcvr, device_chirp, device_line, expected);
            checks = checks + 1;
        end
    endtask

    task automatic set_function(input [7:0] value);
        begin
            @(negedge clk);
            while (phy_dir) @(negedge clk);
            link_data = 8'h84; link_oe = 1;
            @(negedge clk);
            while (!phy_nxt) @(negedge clk);
            @(negedge clk); link_data = value;
            @(negedge clk); link_data = 0; link_stp = 1;
            @(negedge clk); link_oe = 0; link_stp = 0;
            repeat (5) @(negedge clk);
            if (function_control !== value) $fatal(1, "function control write failed");
        end
    endtask

    initial begin
        repeat (3) @(negedge clk); reset_n = 1;
        expect_line(2'b01);
        device_xcvr = 1; expect_line(2'b01);
        device_term = 0; expect_line(2'b00);
        device_term = 1; device_xcvr = 2; expect_line(2'b00);
        device_xcvr = 0; device_chirp = 1; expect_line(2'b10);
        device_chirp = 0; expect_line(2'b01);
        set_function(8'h50); expect_line(2'b00);
        set_function(8'h45); expect_line(2'b01);
        attached = 0; expect_line(2'b00);
        attached = 1; expect_line(2'b01);
        $display("PASS usb3300_host_model_pullup: %0d FS/HS terminations, reset release while peripheral awaits chirps", checks);
        $finish;
    end
    initial begin #100000; $fatal(1, "pullup model timeout"); end
endmodule
