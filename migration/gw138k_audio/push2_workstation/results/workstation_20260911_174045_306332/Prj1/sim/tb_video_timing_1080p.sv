`timescale 1ns/1ps
module tb_video_timing_1080p;
    reg clk = 0;
    always #1 clk = ~clk;
    reg reset_n = 0;
    wire [11:0] x;
    wire [10:0] y;
    wire de, hs, vs, frame_start, line_start, vblank_start;
    video_timing_1080p dut (
        .pixel_clk(clk), .reset_n(reset_n), .pixel_x(x), .pixel_y(y),
        .data_enable(de), .hsync(hs), .vsync(vs), .frame_start(frame_start),
        .line_start(line_start), .vblank_start(vblank_start)
    );
    integer row, col, active_count, hsync_count, vsync_count, frames, lines, blanks;
    initial begin
        active_count=0; hsync_count=0; vsync_count=0;
        frames=0; lines=0; blanks=0;
        repeat (3) @(negedge clk);
        reset_n=1;
        for (row=0; row<1125; row=row+1) begin
            for (col=0; col<2200; col=col+1) begin
                if (x !== col || y !== row) $fatal(1,"1080p raster discontinuity %d,%d",x,y);
                if (de !== (col<1920 && row<1080)) $fatal(1,"1080p active window incorrect");
                if (hs !== (col>=2008 && col<2052)) $fatal(1,"1080p positive horizontal sync incorrect");
                if (vs !== (row>=1084 && row<1089)) $fatal(1,"1080p positive vertical sync incorrect");
                if (frame_start !== (col==0 && row==0)) $fatal(1,"frame marker incorrect");
                if (line_start !== (col==0)) $fatal(1,"line marker incorrect");
                if (vblank_start !== (col==0 && row==1080)) $fatal(1,"DDR prefetch marker incorrect");
                if (de) active_count=active_count+1;
                if (hs) hsync_count=hsync_count+1;
                if (vs) vsync_count=vsync_count+1;
                if (frame_start) frames=frames+1;
                if (line_start) lines=lines+1;
                if (vblank_start) blanks=blanks+1;
                @(negedge clk);
            end
        end
        if (active_count!=2073600 || hsync_count!=49500 || vsync_count!=11000 ||
            frames!=1 || lines!=1125 || blanks!=1) $fatal(1,"1080p frame totals incorrect");
        if (x!==0 || y!==0 || !frame_start) $fatal(1,"1080p frame wrap incorrect");
        repeat (128) @(negedge clk);
        reset_n=0;
        #0.1;
        if (x!==0 || y!==0 || hs!==0 || vs!==0) $fatal(1,"reset did not restart raster");
        $display("PASS tb_video_timing_1080p: 2200x1125 raster, 1920x1080 active, positive sync, DDR markers");
        $finish;
    end
endmodule
