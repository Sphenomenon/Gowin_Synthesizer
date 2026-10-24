`timescale 1ns/1ps
// Board-boundary test uses the real core with a short session and no module
// responses. Covers POR/OE, reset pulse, debounce, and session expiry.
module tb_ble_bringup;
    reg clk = 0;
    always #500 clk = ~clk; // 1 MHz; speedup is test-only
    reg key_n = 1;
    tri module_rx, module_dis;
    wire ready, done;
    ble_bringup_top #(
        .CLK_HZ(1000000), .DISABLE_MS(2), .STARTUP_MS(20),
        .SESSION_MS(25), .NOTIFY_MS(5),
        .PATCH_FILE("vendor/rtl8723ds_ble/rtl8723ds_patch.mem")
    ) dut (.clk_50mhz(clk), .restart_n(key_n), .module_uart_tx(1'b1),
        .usb1_dp(1'b0), .usb1_dm(1'b0),
        .module_uart_rx(module_rx), .module_bt_dis_n(module_dis),
        .led_ready(ready), .led_done(done));
    task clocks;
        input integer n;
        integer i;
        begin for(i=0;i<n;i=i+1) @(negedge clk); end
    endtask
    task check;
        input condition;
        input [511:0] message;
        begin if(condition !== 1'b1) begin
            $display("FAIL: %0s",message); $finish(1);
        end end
    endtask
    initial begin
        clocks(2);
        check(module_rx === 1'bz && module_dis === 1'bz,"POR must disable both OEs");
        clocks(1100);
        check(module_dis === 1'b0,"session begins with BT_DIS low");
        check(dut.usb1_line_state === 2'b00 && dut.usb1_se0_long_seen === 1'b1,
              "USB1 passive monitor observes SE0 without driving pins");
        clocks(2500);
        check(module_dis === 1'b1,"BT_DIS high after disable interval");
        key_n=0;
        clocks(5000); key_n=1;
        clocks(5000);
        check(dut.driver_resetn === 1'b1,"short press bounce must not reset");
        clocks(15000);
        check(module_rx === 1'bz && module_dis === 1'bz,"session expiry releases I/O");
        check(ready === 1'b1 && done === 1'b0,"expired session LED pattern");
        key_n=0; clocks(22000);
        check(dut.driver_resetn === 1'b0,"long press asserts reset");
        check(module_rx === 1'bz && module_dis === 1'bz,"button reset keeps I/O high-Z");
        key_n=1; clocks(20500);
        check(module_dis === 1'b0,"release restarts with module reset low");
        $display("PASS: POR, low/high BT_DIS, button debounce, expiry, OE, restart");
        $finish;
    end
    initial begin #150000000; $display("FAIL: watchdog"); $finish(1); end
endmodule
