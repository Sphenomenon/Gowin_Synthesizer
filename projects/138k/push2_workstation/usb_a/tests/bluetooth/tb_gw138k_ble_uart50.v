`timescale 1ns/1ps
module tb_gw138k_ble_uart50;
    localparam DIV=434;
    reg clk=0,resetn=0,enable=0,rx=1,tx_valid=0;
    reg [7:0] tx_data=0;
    wire tx,tx_ready,tx_done,rx_valid,rx_error;
    wire [7:0] rx_data;
    integer received=0,errors=0;
    always #10 clk=~clk;
    bt_uart #(.CLK_HZ(50000000),.BAUD(115200)) dut (
        .clk(clk),.resetn(resetn),.enable(enable),.rx(rx),.tx(tx),
        .tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),.tx_done(tx_done),
        .rx_data(rx_data),.rx_valid(rx_valid),.rx_error(rx_error));
    reg [7:0] expected;
    always @(posedge clk) begin
        if(rx_valid) begin
            if(rx_data!==expected) $fatal(1,"RX data mismatch at real 50 MHz");
            received=received+1;
        end
        if(rx_error) errors=errors+1;
    end
    task bit_send;
        input value;
        begin rx=value; repeat(DIV) @(negedge clk); end
    endtask
    task byte_send;
        input [7:0] value;
        input bad_parity;
        integer i;
        begin
            expected=value;
            bit_send(0);
            for(i=0;i<8;i=i+1) bit_send(value[i]);
            bit_send((^value)^bad_parity);
            bit_send(1);
            repeat(10) @(negedge clk);
        end
    endtask
    reg [10:0] observed;
    integer j;
    initial begin
        repeat(4) @(negedge clk);resetn=1;enable=1;
        fork
            begin byte_send(8'hc0,0);byte_send(8'hdb,0);byte_send(8'h55,1);byte_send(8'haa,0);end
            begin
                repeat(15) @(negedge clk);
                tx_data=8'hdb;tx_valid=1;
                @(negedge clk);tx_valid=0;
                if(tx!==0) $fatal(1,"UART start bit missing");
                repeat(DIV/2) @(negedge clk);
                for(j=0;j<11;j=j+1) begin
                    observed[j]=tx;repeat(DIV) @(negedge clk);
                end
                if(observed!=={1'b1,(^8'hdb),8'hdb,1'b0}) $fatal(1,"50 MHz TX 8E1 mismatch");
            end
        join
        if(received!=3 || errors!=1) $fatal(1,"Parity drop/recovery mismatch");
        enable=0;repeat(3) @(negedge clk);
        if(tx!==1 || tx_ready!==0) $fatal(1,"Stopped UART not idle");
        $display("GW138K_BLE_UART50_PASS 50MHz 115200 8E1 simultaneous TX/RX and parity recovery");
        $finish;
    end
    initial begin #10000000;$fatal(1,"50MHz UART watchdog");end
endmodule
