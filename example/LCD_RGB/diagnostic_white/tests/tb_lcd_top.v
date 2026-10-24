`timescale 1ns/1ps
// Integration-only PLL stub: exercises lock/reset wiring and output edge choice.
// It does not simulate Gowin PLL analog behavior or prove physical frequency.
module lcd_pll(input wire clkin, output reg clkout0=0, output reg lock=0);
    always #15.873016 clkout0=~clkout0;
    initial #600 lock=1;
endmodule

module tb_lcd_top;
    localparam W=800,H=480,HSW=48,HBP=88,HFP=40,VSW=3,VBP=32,VFP=13;
    localparam HX=HSW+HBP,VY=VSW+VBP,HT=HX+W+HFP,VT=VY+H+VFP;
    reg clock50=0, restart_n=1;
    wire [4:0] r,b;
    wire [5:0] g;
    wire pclk,hs,vs,de,bl;
    realtime changed_at=-1000, previous_edge;
    integer x,y,pass,bar;
    reg [15:0] expected_rgb;
    always #10 clock50=~clock50;
    lcd_rgb_top dut(.clk_50mhz(clock50),.restart_n(restart_n),
        .lcd_r(r),.lcd_g(g),.lcd_b(b),.lcd_pclk(pclk),
        .lcd_hsync(hs),.lcd_vsync(vs),.lcd_de(de),.lcd_bl(bl));
    always @(r or g or b or hs or vs or de) changed_at=$realtime;
    task capture_first_frame;
        begin
            wait(dut.reset_release[1]===1'b1);
            @(posedge dut.pixel_clk); #1;
            previous_edge=0;
            for(y=0;y<VT;y=y+1) begin
                for(x=0;x<HT;x=x+1) begin
                    @(posedge pclk);
                    if(previous_edge!=0 && ($realtime-previous_edge<31.74 ||
                       $realtime-previous_edge>31.76)) $fatal(1,"PCLK period");
                    previous_edge=$realtime;
                    if($realtime-changed_at<15) $fatal(1,"data changed near sampling edge");
                    if(de!==(x>=HX && x<HX+W && y>=VY && y<VY+H)) $fatal(1,"top DE");
                    if(hs!==!(x<HSW) || vs!==!(y<VSW)) $fatal(1,"top sync");
                    expected_rgb=16'hffff;
                    if({r,g,b}!==expected_rgb) $fatal(1,"top RGB ordering");
                    if(bl!==0) $fatal(1,"backlight enabled before three frames");
                end
            end
        end
    endtask
    initial begin
        #1; restart_n=0; #100; restart_n=1;
        capture_first_frame();
        // Assert external reset between edges, then verify a complete restart.
        #7; restart_n=0; #1;
        if(de!==0 || bl!==0 || {r,g,b}!==16'hffff) $fatal(1,"external reset wiring");
        #130; restart_n=1;
        capture_first_frame();
        // PLL loss must use the same safe reset path and recover after relock.
        #7; dut.clockgen.lock=0; #1;
        if(de!==0 || bl!==0 || {r,g,b}!==16'hffff) $fatal(1,"PLL loss reset wiring");
        #130; dut.clockgen.lock=1;
        capture_first_frame();
        $display("PASS fixed-white diagnostic top: RGB pins, PCLK sample edge, restart and PLL lock loss/recovery");
        $finish;
    end
    initial begin #60000000; $fatal(1,"top timeout"); end
endmodule
