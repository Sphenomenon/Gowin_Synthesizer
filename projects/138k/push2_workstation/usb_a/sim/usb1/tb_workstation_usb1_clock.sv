`timescale 1ns/1ps
module gw138k_cpu_pll_cell #(
    parameter OUTPUT_DIV0=25, parameter OUTPUT1_ENABLE="FALSE"
)(input wire clkin,init_clk,reset,enable0,output wire lock,clkout0,clkout1);
    reg raw_clk=0,lock_enabled=0,clock_enabled=1;
    always #10.417 raw_clk=!raw_clk;
    assign lock=!reset&&lock_enabled;
    assign clkout0=clock_enabled&&raw_clk;
    assign clkout1=0;
endmodule

module tb_workstation_usb1_clock;
    reg clk_50m=0;
    always #10 clk_50m=!clk_50m;
    wire clk_48m,locked,reset_n;
    workstation_usb1_clock dut(.clk_50m(clk_50m),.clk_48m(clk_48m),.locked_o(locked),.reset_n_o(reset_n));
    task check_release;
        begin
            repeat(2)begin @(posedge clk_48m);#0.001;if(reset_n)$fatal(1,"reset released before three clocks");end
            @(posedge clk_48m);#0.001;if(!reset_n)$fatal(1,"reset did not release on the third clock");
        end
    endtask
    initial begin
        #1;if(reset_n)$fatal(1,"power-on reset missing");
        wait(dut.power_ready);#7.773;
        if(reset_n)$fatal(1,"power ready is not PLL lock");
        dut.pll.lock_enabled=1;check_release();
        @(negedge clk_48m);#2.139;
        dut.pll.clock_enabled=0;dut.pll.lock_enabled=0;
        #0.001;if(reset_n)$fatal(1,"clock loss must assert reset without a destination edge");
        #100;if(reset_n)$fatal(1,"stopped clock must not release reset");
        dut.pll.clock_enabled=1;#3.417;dut.pll.lock_enabled=1;
        check_release();
        #2.017;dut.pll.lock_enabled=0;#0.001;
        if(reset_n)$fatal(1,"asynchronous lock glitch did not cancel release");
        #1.771;dut.pll.lock_enabled=1;check_release();
        $display("PASS USB1 reset CDC: power/PLL qualification, three-clock release, stopped clock and asynchronous reassertion");
        $finish;
    end
    initial begin #100000;$fatal(1,"USB1 clock reset timeout");end
endmodule
