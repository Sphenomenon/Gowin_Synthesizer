`timescale 1ns/1ps
module tb_video_timing;
    reg clk = 0;
    always #20 clk = ~clk;
    reg reset_n = 0;
    wire [9:0] x, y;
    wire de, hs, vs, frame_start;
    video_timing_640x480 dut(clk, reset_n, x, y, de, hs, vs, frame_start);
    integer row, col, active_count, hsync_count, vsync_count, frames;
    initial begin
        active_count=0; hsync_count=0; vsync_count=0; frames=0;
        repeat (3) @(negedge clk);
        reset_n=1;
        for (row=0; row<525; row=row+1) begin
            for (col=0; col<800; col=col+1) begin
                if (x !== col || y !== row) $fatal(1,"raster discontinuity %d,%d",x,y);
                if (de !== (col<640 && row<480)) $fatal(1,"active window incorrect");
                if (hs !== !(col>=656 && col<752)) $fatal(1,"horizontal porch/sync incorrect");
                if (vs !== !(row>=490 && row<492)) $fatal(1,"vertical porch/sync incorrect");
                if (de) active_count=active_count+1;
                if (!hs) hsync_count=hsync_count+1;
                if (!vs) vsync_count=vsync_count+1;
                if (frame_start) frames=frames+1;
                @(negedge clk);
            end
        end
        if (active_count!=307200 || hsync_count!=50400 || vsync_count!=1600 || frames!=1)
            $fatal(1,"frame totals incorrect");
        if (x!==0 || y!==0 || !frame_start) $fatal(1,"frame wrap incorrect");
        $display("PASS tb_video_timing: complete 800x525 raster / 640x480 active");
        $finish;
    end
endmodule
