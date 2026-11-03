`timescale 1ns/1ps
module tb_workstation_usb2_display_status;
    reg cpu_clk=0,ulpi_clk=0,ulpi_run=1,reset_n=0;
    always #5 cpu_clk=~cpu_clk;
    always #7 if(ulpi_run)ulpi_clk=~ulpi_clk;
    reg [2:0] device_state=0;
    reg [3:0] cpu_fault=0;
    reg failed=0,traffic_enable=0,transaction_ready=0,high_speed=0;
    wire [7:0] status;
    workstation_usb2_display_status #(.STALE_CYCLES(100)) dut(.*);
    task settle(input [7:0] expected);
        begin
            repeat(90) @(negedge cpu_clk);
            if(status!==expected)$fatal(1,"status %h expected %h",status,expected);
        end
    endtask
    initial begin
        repeat(3) @(negedge cpu_clk);reset_n=1;
        settle(0);
        traffic_enable=1;transaction_ready=1;settle(8'h30);
        device_state=1;high_speed=1;settle(8'h39);
        device_state=3;settle(8'h3b);
        device_state=7;high_speed=0;settle(8'h37);
        cpu_fault=4'b0100;settle(8'hb7);cpu_fault=0;
        failed=1;settle(8'h77);failed=0;settle(8'h37);
        // Once the actual ULPI publisher stops, connection bits expire.
        ulpi_run=0;repeat(180) @(negedge cpu_clk);
        if(status!==8'h47)$fatal(1,"stopped ULPI retained live connection %h",status);
        ulpi_run=1;settle(8'h37);
        device_state=0;traffic_enable=0;transaction_ready=0;settle(0);
        ulpi_run=0;reset_n=0;repeat(5) @(negedge cpu_clk);
        reset_n=1;repeat(160) @(negedge cpu_clk);
        if(status!==0)$fatal(1,"reset while ULPI stopped reused status");
        ulpi_run=1;device_state=1;traffic_enable=1;transaction_ready=1;high_speed=1;
        settle(8'h39);
        $display("PASS actual USB status CDC, classification, faults, stop and reset recovery");
        $finish;
    end
    initial begin #100000;$fatal(1,"timeout");end
endmodule
