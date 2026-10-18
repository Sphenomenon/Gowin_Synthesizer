`timescale 1ns/1ps
module tb_analysis_renderer;
    reg clk=0,source_clk=0,reset_n=0,start=0,valid=0;
    always #5 clk=~clk;always #10 source_clk=~source_clk;
    reg [31:0] pair=0,mono=0;
    wire ready,busy,done,pixel_valid;
    wire [63:0] pixels;
    reg [15:0] random_state=16'h5ab3;
    wire pixel_ready=random_state[3:0]!=0;
    feedback_renderer #(.ENABLE_ANALYSIS(1)) dut(.clk(clk),.rst_n(reset_n),.start(start),
        .frame_ready(ready),.busy(busy),.frame_done(done),.pixel_valid(pixel_valid),.pixel_ready(pixel_ready),.pixel_data(pixels),
        .source_clk(source_clk),.source_reset_n(reset_n),.sample_data(mono),.sample_valid(valid),.output_pcm(pair),
        .trigger_reference(32'd3),.active_voices(32'h80010001),.status_data(32'd0),
        .memory_status(32'hcb),.underruns(32'd0),.frame_count(32'd123));
    integer bin_map[0:511];
    integer n,l,r,beats=0,x,y,lane,column,bin,hl,hr,dx,dy,first_bin,scan_bin;
    integer expected_left[0:511],expected_right[0:511];
    integer spectrum_pixels=0,image_pixels=0,stalls=0;
    reg [31:0] expected_color,actual_color;
    reg [63:0] held_pixels;
    reg held=0;
    localparam real PI=3.14159265358979323846;
    always @(posedge clk) if(reset_n) begin
        random_state<={random_state[14:0],random_state[15]^random_state[13]^random_state[12]^random_state[10]};
        if(held && (!pixel_valid || pixels!==held_pixels)) $fatal(1,"analysis raster changed under backpressure");
        held=pixel_valid && !pixel_ready;held_pixels=pixels;
        if(held) stalls=stalls+1;
        if(pixel_valid && pixel_ready) begin
            y=beats/960;
            for(lane=0;lane<2;lane=lane+1) begin
                x=(beats%960)*2+lane;actual_color=lane ? pixels[63:32] : pixels[31:0];
                if(x>=64 && x<1088 && y>=568 && y<792) begin
                    column=(x-64)/2;bin=bin_map[column];
                    hl=expected_left[column];hr=expected_right[column];
                    expected_color=32'h000b1420;
                    if(y%64==56 || x==64 || x==306 || x==578 || x==850 || x==1086) expected_color=32'h0031506c;
                    if(hl!=0 && y>=792-hl) expected_color=32'h003cdbab;
                    if(hr!=0 && y>=792-hr) expected_color=hl!=0 && y>=792-hl ? 32'h00a8d5bd : 32'h00f1c05a;
                    if(actual_color!==expected_color) $fatal(1,"spectrum raster alignment at %0d,%0d bin=%0d got=%h expected=%h",x,y,bin,actual_color,expected_color);
                    spectrum_pixels=spectrum_pixels+1;
                end
                if(x>=1248 && x<1760 && y>=224 && y<736) begin
                    dx=x-1504;if(dx<0)dx=-dx;dy=y-480;if(dy<0)dy=-dy;
                    expected_color=32'h000b1420;
                    if((x-1248)%128==0 || (y-224)%128==0) expected_color=32'h001c3145;
                    if(x==1504 || y==480 || dx+dy==256) expected_color=32'h0031506c;
                    if(dut.g_analysis.u_analysis.image_pixels[((y-224)/2)*256+(x-1248)/2]) expected_color=32'h003cdbab;
                    if(actual_color!==expected_color) $fatal(1,"stereo image raster alignment at %0d,%0d",x,y);
                    image_pixels=image_pixels+1;
                end
            end
            beats=beats+1;
        end
    end
    initial begin
        for(n=0;n<512;n=n+1) bin_map[n]=$rtoi($exp($ln(419.0)*n/511)+0.5);
        repeat(4) @(negedge source_clk);reset_n=1;
        for(n=0;n<1024;n=n+1) begin
            l=$rtoi(16384.0*$sin(2*PI*16*n/1024));r=$rtoi(8192.0*$sin(2*PI*37*n/1024));
            @(negedge source_clk);pair={l[15:0],r[15:0]};mono=(l+r)*32768;valid=1;
        end
        @(negedge source_clk);valid=0;
        wait(ready);
        // Independently cover every bin in each log interval, not just its
        // endpoint. Include repeated low-frequency columns without gaps.
        for(n=0;n<512;n=n+1) begin
            first_bin=n==0 ? 1 : bin_map[n-1]+1;
            if(first_bin>bin_map[n]) first_bin=bin_map[n];
            expected_left[n]=0;expected_right[n]=0;
            for(scan_bin=first_bin;scan_bin<=bin_map[n];scan_bin=scan_bin+1) begin
                if(dut.g_analysis.u_analysis.levels_left[scan_bin]>expected_left[n]) expected_left[n]=dut.g_analysis.u_analysis.levels_left[scan_bin];
                if(dut.g_analysis.u_analysis.levels_right[scan_bin]>expected_right[n]) expected_right[n]=dut.g_analysis.u_analysis.levels_right[scan_bin];
            end
        end
        @(negedge clk);start=1;@(negedge clk);start=0;
        // Fill the other audio banks while this raster stalls. Published
        // spectra, peaks and the image must remain tied to the first block.
        for(n=0;n<2300;n=n+1) begin @(negedge source_clk);pair=32'h01000200;mono=32'h01800000;valid=1;end
        @(negedge source_clk);valid=0;
        wait(done);@(negedge clk);
        if(beats!=1036800 || spectrum_pixels!=229376 || image_pixels!=262144 || stalls<1000)
            $fatal(1,"incomplete full raster coverage");
        $display("PASS analysis renderer: all 1920x1080 pixels, %0d spectrum pixels and %0d stereo pixels aligned, %0d backpressure cycles, simultaneous next-block capture and final handshake",spectrum_pixels,image_pixels,stalls);$finish;
    end
    initial begin #25000000;$fatal(1,"analysis renderer timeout");end
endmodule
