`timescale 1ns/1ps
module tb_workstation_audio_rate_overlay;
    reg clk=0,control=0,rst_n=0,start=0;
    always #3.367 clk=~clk;
    always #10 control=~control;
    reg [3:0] status=4'b0010;
    reg [10:0] x=0,y=0;
    wire hit;wire [23:0] rgb;
    workstation_audio_rate_overlay dut(.reset_ni(rst_n),.pixel_reset_ni(rst_n),.control_clk_i(control),.pixel_clk_i(clk),
        .actual_status_i(status),.frame_start_i(start),.x_i(x),.y_i(y),.hit_o(hit),.rgb_o(rgb));
    reg [3:0] expected_status=0;
    reg [255:0] line;
    reg [7:0] character;
    wire ink;
    wire [10:0] dx=x-1248;
    video_font_5x7 oracle(.character(character),.column(dx[3:1]),.row(y[3:1]),.ink(ink),.glyph());
    always @*begin
        if(y<1024)line=expected_status[0] ? "OUTPUT   44100 HZ / STEREO      " : "OUTPUT   48000 HZ / STEREO      ";
        else if(expected_status[3])line="CLOCK    FAULT / SWITCH REJECTED";
        else if(expected_status[2])line="CLOCK    SWITCHING / MUTED      ";
        else if(!expected_status[1])line="CLOCK    NOT VALID              ";
        else line="CLOCK    READY / SESSION TOGGLE ";
        character=line[255-dx[8:4]*8 -:8];
    end
    reg hit_q=0,verify_q=0;
    reg [23:0] rgb_q;
    integer checked=0,text_pixels=0,background_pixels=0;
    always @(posedge clk)begin
        #0.001;
        // The first stage has just sampled this coordinate. The output must
        // still correspond to the preceding coordinate, exactly two stages.
        if(verify_q)begin
            if(hit!==hit_q || (hit_q && rgb!==rgb_q))
                $fatal(1,"rate overlay geometry/text/pipeline mismatch x=%0d y=%0d got=%h expected=%h hit=%b/%b state=%b",x,y,rgb,rgb_q,hit,hit_q,expected_status);
            checked++;
        end
        hit_q=x>=1248 && x<1760 && y>=992 && y<1040;
        rgb_q=(y[4:0]<16 && ink) ? 24'h343b42 : 24'hf3f4f5;
        if(hit_q)begin if(ink)text_pixels++;else background_pixels++;end
        verify_q=rst_n;
    end
    task clocks(input integer n);repeat(n)@(negedge clk);endtask
    task publish(input [3:0] actual);begin
        status=actual;clocks(100);verify_q=0;start=1;clocks(1);start=0;
        expected_status=actual;clocks(3);
    end endtask
    task draw_table;begin
        for(integer yy=990;yy<1042;yy++)for(integer xx=1246;xx<1762;xx++)begin
            @(negedge clk);x=11'(xx);y=11'(yy);
        end
        clocks(3);
    end endtask
    initial begin
        clocks(4);rst_n=1;clocks(100);
        publish(4'b0010);draw_table();
        // Busy changes must not become a mid-frame request/rate echo.
        status=4'b0110;clocks(100);draw_table();
        publish(4'b0110);draw_table();
        publish(4'b0011);draw_table();
        status=4'b1111;clocks(100);draw_table();
        publish(4'b1111);draw_table();
        publish(4'b0001);draw_table();
        publish(4'b0010);draw_table();
        if(checked<200000 || text_pixels==0 || background_pixels==0)$fatal(1,"overlay coverage short");
        $display("PASS audio_rate_overlay checked=%0d text=%0d background=%0d frame_frozen_actual=1 busy_fault_without_pcm=1",checked,text_pixels,background_pixels);
        $finish;
    end
    initial begin #20000000;$fatal(1,"overlay watchdog");end
endmodule
