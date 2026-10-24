`timescale 1ns/1ps
// Integration-only PLL stub: exercises lock/reset wiring and output edge choice.
// It does not simulate Gowin PLL analog behavior or prove physical frequency.
module lcd_pll(input wire clkin, output reg clkout0=0, output reg lock=0);
    always #55.555555 clkout0=~clkout0;
    initial #600 lock=1;
endmodule

module tb_lcd_top;
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
            wait(hs===1'b1 && vs===1'b1);
            previous_edge=0;
            for(y=0;y<286;y=y+1) begin
                for(x=0;x<525;x=x+1) begin
                    @(posedge pclk);
                    if(previous_edge!=0 && ($realtime-previous_edge<111.0 ||
                       $realtime-previous_edge>111.2)) $fatal(1,"PCLK period");
                    previous_edge=$realtime;
                    if($realtime-changed_at<50) $fatal(1,"data changed near sampling edge");
                    if(de!==(x>=43 && x<523 && y>=12 && y<284)) $fatal(1,"top DE");
                    if(hs!==(x<41) || vs!==(y<10)) $fatal(1,"top sync");
                    expected_rgb=0;
                    if(de) begin
                        bar=(x-43)/60;
                        case(bar)
                            0: expected_rgb=16'hffff;
                            1: expected_rgb=16'hffe0;
                            2: expected_rgb=16'h07ff;
                            3: expected_rgb=16'h07e0;
                            4: expected_rgb=16'hf81f;
                            5: expected_rgb=16'hf800;
                            6: expected_rgb=16'h001f;
                            7: expected_rgb=0;
                        endcase
                    end
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
        if(de!==0 || bl!==0 || {r,g,b}!==0) $fatal(1,"external reset wiring");
        #130; restart_n=1;
        capture_first_frame();
        // PLL loss must use the same safe reset path and recover after relock.
        #7; dut.clockgen.lock=0; #1;
        if(de!==0 || bl!==0 || {r,g,b}!==0) $fatal(1,"PLL loss reset wiring");
        #130; dut.clockgen.lock=1;
        capture_first_frame();
        $display("PASS top: RGB pin ordering, PCLK sample edge, restart and PLL lock loss/recovery");
        $finish;
    end
    initial begin #60000000; $fatal(1,"top timeout"); end
endmodule
