`timescale 1ns/1ps
module tb_continuous;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0;
    wire active;
    wire [767:0] debug;
    bt_verilog_core #(.CLK_HZ(1000000),.SESSION_MS(0),.DISABLE_MS(1),.STARTUP_MS(1000),
        .PATCH_FILE("vendor/rtl8723ds_ble/rtl8723ds_patch.mem")) dut(
        .clk(clk),.resetn(resetn),.enable(1'b1),.uart_rx(1'b1),.uart_tx(),
        .bt_enable(),.outputs_active(active),.initialized(),.connected(),.subscribed(),.failed(),.debug(debug));
    initial begin
        repeat(10) @(negedge clk); resetn=1;
        repeat(10000) @(negedge clk);
        if(!active || debug[2*32+6] || debug[3*32+:32]<9) $fatal(1,"zero session must run continuously");
        $display("PASS: SESSION_MS=0 keeps BLE session active"); $finish;
    end
endmodule
