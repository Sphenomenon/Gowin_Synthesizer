`timescale 1ns/1ps
module tb_lcd_scan;
    parameter FIXED=-1, HS=0, VS=0, BL=1, W=800, H=480, FRAMES=13;
    parameter HSW=48, HBP=88, HFP=40, VSW=3, VBP=32, VFP=13;
    localparam HX=HSW+HBP, VY=VSW+VBP;
    localparam HT=HX+W+HFP, VT=VY+H+VFP;
    reg clk=0, reset_n=1;
    wire [15:0] rgb;
    wire hs,vs,de,bl;
    wire [3:0] pattern;
    integer fd,f,x,y,active_count;
    reg want_de;
    reg [1023:0] output_path;
    always #15.873016 clk=~clk;
    lcd_scan #(.H_ACTIVE(W),.V_ACTIVE(H),
        .H_SYNC(HSW),.H_BACK(HBP),.H_FRONT(HFP),
        .V_SYNC(VSW),.V_BACK(VBP),.V_FRONT(VFP),.FRAMES_PER_PATTERN(1),
        .FIXED_PATTERN(FIXED),.HS_ACTIVE(HS),.VS_ACTIVE(VS),.BL_ACTIVE(BL)) dut(
        .pixel_clk(clk),.reset_n(reset_n),.rgb(rgb),.hsync(hs),.vsync(vs),
        .de(de),.bl(bl),.pattern(pattern));

    task check_frame;
        input integer frame_number;
        input integer capture;
        begin
            active_count=0;
            for(y=0;y<VT;y=y+1) begin
                for(x=0;x<HT;x=x+1) begin
                    @(negedge clk); #1;
                    want_de=x>=HX && x<HX+W && y>=VY && y<VY+H;
                    if(de!==want_de || hs!==(x<HSW ? HS[0] : !HS[0]) ||
                       vs!==(y<VSW ? VS[0] : !VS[0]))
                        $fatal(1,"scan mismatch frame=%0d x=%0d y=%0d",frame_number,x,y);
                    if(!de && rgb!==16'h0000) $fatal(1,"nonzero blanking");
                    if(^rgb===1'bx) $fatal(1,"unknown pixel value");
                    // Last pixel commits the completed-frame backlight counter.
                    if(!(x==HT-1 && y==VT-1) &&
                       bl!==(frame_number>=3 ? BL[0] : !BL[0]))
                        $fatal(1,"backlight startup mismatch");
                    if(de) begin
                        active_count=active_count+1;
                        if(capture) $fwrite(fd,"%c%c",rgb[15:8],rgb[7:0]);
                    end
                end
            end
            if(active_count!=W*H) $fatal(1,"active area size");
            if(pattern!==(FIXED<0 ? (frame_number+1)%12 : FIXED))
                $fatal(1,"pattern sequence/fixed mode mismatch");
        end
    endtask

    initial begin
        if(!$value$plusargs("output=%s",output_path)) $fatal(1,"output path required");
        fd=$fopen(output_path,"wb");
        if(fd==0) $fatal(1,"cannot open capture");
        #1; reset_n=0; #20;
        if(de!==0 || rgb!==0 || bl!==!BL[0]) $fatal(1,"reset outputs");
        @(negedge clk); #2; reset_n=1;
        for(f=0;f<FRAMES;f=f+1) check_frame(f,1);
        // Reset in the middle of an active line, then decode a fresh full frame.
        repeat(HT*(VY+1)+HX+W/2) @(negedge clk);
        #3; reset_n=0; #1;
        if(de!==0 || rgb!==0 || bl!==!BL[0]) $fatal(1,"mid-frame reset");
        @(negedge clk); #2; reset_n=1;
        check_frame(0,0);
        $fclose(fd);
        $display("PASS scan, blanking, startup, sequence, reset (%0dx%0d)",W,H);
        $finish;
    end
    initial begin #500000000; $fatal(1,"timeout"); end
endmodule
