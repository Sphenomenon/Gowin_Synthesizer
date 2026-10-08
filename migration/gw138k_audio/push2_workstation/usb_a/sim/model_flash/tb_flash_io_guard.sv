`timescale 1ns/1ps
module tb_flash_io_guard;
    reg cs=1,clk=0,mosi=0,other=0,other_clk=1;
    tri pad_cs,pad_clk,pad_mosi,pad_wp,pad_hold;
    wire owned;
    basic_pitch_flash_io_guard dut(
        .spi_cs_n_i(cs),.spi_clk_i(clk),.spi_mosi_i(mosi),
        .flash_cs_n_o(pad_cs),.flash_clk_o(pad_clk),.flash_mosi_o(pad_mosi),
        .flash_wp_n_o(pad_wp),.flash_hold_n_o(pad_hold),.owned_o(owned));
    // Independent other master drives even IO2/3 low. Idle user logic must
    // not clamp any shared pad or contend with configuration-time transfers.
    assign pad_cs=other ? 1'b0 : 1'bz;
    assign pad_clk=other ? other_clk : 1'bz;
    assign pad_mosi=other ? 1'b1 : 1'bz;
    assign pad_wp=other ? 1'b0 : 1'bz;
    assign pad_hold=other ? 1'b0 : 1'bz;
    initial begin
        #2;
        if({pad_cs,pad_clk,pad_mosi,pad_wp,pad_hold}!==5'bzzzzz || owned!==0)
            $fatal(1,"idle/reset pads not fully released");
        other=1;#2;
        if({pad_cs,pad_clk,pad_mosi,pad_wp,pad_hold}!==5'b01100)
            $fatal(1,"idle user pads contend with other master");
        other_clk=0;clk=1;mosi=1;#2;
        if({pad_cs,pad_clk,pad_mosi,pad_wp,pad_hold}!==5'b00100)
            $fatal(1,"idle user clock/MOSI leaked onto shared bus");
        other=0;cs=0;clk=0;#2;
        if({pad_cs,pad_clk,pad_mosi,pad_wp,pad_hold}!==5'b00111 || owned!==1)
            $fatal(1,"user transaction grant/sideband wrong");
        clk=1;mosi=0;#2;
        if({pad_cs,pad_clk,pad_mosi,pad_wp,pad_hold}!==5'b01011)
            $fatal(1,"active SPI wave propagation wrong");
        cs=1;#2;
        if({pad_cs,pad_clk,pad_mosi,pad_wp,pad_hold}!==5'bzzzzz || owned!==0)
            $fatal(1,"completed transaction did not release pads");
        $display("PASS Flash IO guard: idle release, other-master ownership, active SPI and release");
        $finish;
    end
endmodule
