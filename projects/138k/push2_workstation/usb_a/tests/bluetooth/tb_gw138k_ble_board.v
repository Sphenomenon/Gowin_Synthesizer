`timescale 1ns/1ps
module tb_gw138k_ble_board;
    localparam CLK_HZ=1152000;
    localparam DIV=10;
    reg clk=0,resetn=0,rx=1;
    wire tx,bt_dis,wl_dis,status_tx;
    always #5 clk=~clk;
    gw138k_ble_board_top #(.CLK_HZ(CLK_HZ),.DISABLE_MS(1),.STARTUP_MS(2),
        .SESSION_MS(8),.REPORT_MS(1),.PATCH_FILE("rtl8723ds_patch.mem")) dut (
        .clk_50m(clk),.button1_n(resetn),.ble_module_uart_tx(rx),
        .ble_module_uart_rx(tx),.ble_module_bt_dis(bt_dis),.ble_module_wl_dis(wl_dis),
        .debug_uart_tx(status_tx));
    reg [7:0] line[0:197];
    reg [7:0] byte_value;
    integer i,j,k;
    reg [767:0] expected_snapshot;
    reg [31:0] actual_word;
    function [3:0] hex_value;
        input [7:0] value;
        begin hex_value=value<=57 ? value-48 : value-65+10; end
    endfunction
    always @(posedge clk)
        if(resetn && !dut.u_status.sending && dut.u_status.divider==CLK_HZ/1000-1)
            expected_snapshot=dut.u_ble.debug;
    reg status_done=0;
    initial begin
        #1;
        if(tx!==1'bz || bt_dis!==1'bz || wl_dis!==1'bz) $fatal(1,"Reset pins not released");
        repeat(4) @(negedge clk);resetn=1;
        repeat(8) @(negedge clk);
        if(tx!==1 || bt_dis!==0 || wl_dis!==0) $fatal(1,"Initial module reset phase mismatch");
        wait(bt_dis===1'b1);
        if(dut.u_ble.debug[3*32+:32]!==1) $fatal(1,"BT disable duration mismatch");
        wait(dut.u_ble.debug[3*32+:32]>=8);
        #1;
        if(tx!==1'bz || bt_dis!==1'bz || wl_dis!==1'bz) $fatal(1,"Session expiry pins not released");
        wait(status_done);
        // A fresh reset must asynchronously release every module drive, then restart.
        @(negedge clk);resetn=0;#1;
        if(tx!==1'bz || bt_dis!==1'bz || wl_dis!==1'bz) $fatal(1,"Asynchronous reset not releasing pins");
        repeat(4) @(negedge clk);resetn=1;
        repeat(8) @(negedge clk);
        if(bt_dis!==0 || wl_dis!==0) $fatal(1,"Restart did not reset module");
        $display("GW138K_BLE_BOARD_PASS module reset/start, expiry/restart, async OE release and coherent 8N1 diagnostic frame");
        $finish;
    end
    initial begin
        wait(resetn);
        for(i=0;i<198;i=i+1) begin
            @(negedge status_tx);
            repeat(DIV+DIV/2) @(negedge clk);
            for(j=0;j<8;j=j+1) begin
                byte_value[j]=status_tx;repeat(DIV) @(negedge clk);
            end
            if(status_tx!==1) $fatal(1,"Status UART stop bit missing");
            line[i]=byte_value;
        end
        if(line[0]!="B" || line[1]!="L" || line[2]!="E" || line[3]!="1" || line[4]!=" " || line[197]!=10)
            $fatal(1,"Status frame format mismatch");
        for(i=5;i<197;i=i+1)
            if(!((line[i]>=48&&line[i]<=57)||(line[i]>=65&&line[i]<=70))) $fatal(1,"Non-hex status word");
        // Debug word0 is 42545647, captured coherently at report launch.
        if({line[5],line[6],line[7],line[8],line[9],line[10],line[11],line[12]}!=="42545647")
            $fatal(1,"Status magic word mismatch");
        for(k=0;k<24;k=k+1) begin
            actual_word=0;
            for(j=0;j<8;j=j+1) actual_word=(actual_word<<4)|hex_value(line[5+k*8+j]);
            if(actual_word!==expected_snapshot[k*32+:32]) $fatal(1,"Status snapshot word%0d inconsistent",k);
        end
        status_done=1;
    end
    initial begin #1000000;$fatal(1,"Board watchdog");end
endmodule
