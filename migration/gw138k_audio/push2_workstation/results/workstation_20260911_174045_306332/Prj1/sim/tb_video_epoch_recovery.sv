`timescale 1ns/1ps
// Exercise a real stopped fetcher across all 256 epoch values with a reduced
// 32x4 raster. A timeout leaves nonzero pixels physically in both line RAMs;
// stale tags must never make those pixels visible after the epoch wraps.
module tb_video_epoch_recovery;
    localparam integer WIDTH=32, HEIGHT=4;
    reg clk=0,pixel_clk=0,rst_n=0;
    always #5 clk=~clk;
    always #3.4 pixel_clk=~pixel_clk;
    reg frame_pending=1,return_data=1;
    wire frame_swap,front_bank,front_valid,req_valid,fetch_fault;
    wire [28:0] req_addr;
    reg rsp_valid=0;
    wire [31:0] underruns;
    reg [11:0] x=0;
    reg [10:0] y=HEIGHT;
    reg de=0,vblank=0;
    wire [23:0] rgb;
    wire out_de,out_hs,out_vs;
    video_ddr_scanout #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.FRAME_STRIDE_WORDS(512),.TIMEOUT_CYCLES(30)) dut(
        .clk(clk),.rst_n(rst_n),.enabled(1'b1),.new_frame_pending(frame_pending),
        .frame_swap(frame_swap),.front_bank(front_bank),.front_valid(front_valid),
        .req_valid(req_valid),.req_ready(1'b1),.req_addr(req_addr),
        .rsp_valid(rsp_valid),.rsp_data({16{16'h07e0}}),.fetch_fault(fetch_fault),.underruns(underruns),
        .pixel_clk(pixel_clk),.pixel_rst_n(rst_n),.pixel_x(x),.pixel_y(y),
        .data_enable(de),.hsync(1'b0),.vsync(1'b0),.vblank_start(vblank),
        .rgb(rgb),.out_de(out_de),.out_hsync(out_hs),.out_vsync(out_vs));
    integer requests=0,requests_at_fault=0;
    reg fault_phase=0;
    // Ordered one-cycle return on the user boundary, disabled to cause timeout.
    always @(posedge clk) begin
        if(!rst_n) begin rsp_valid<=0;requests<=0;end
        else begin
            rsp_valid<=req_valid && return_data;
            if(req_valid) requests<=requests+1;
            if(fault_phase && req_valid) $fatal(1,"fetcher issued another read after fault");
        end
    end

    reg check_pixels=0;
    reg [23:0] desired_color=0,expected_color=0;
    reg expected_de=0;
    integer checked_pixels=0,wraps=0;
    always @(posedge pixel_clk) begin
        #0.1;
        if(rst_n && check_pixels && expected_de) begin
            if(!out_de || rgb!==expected_color)
                $fatal(1,"old row leaked or recovery failed: epoch=%d rgb=%h expected=%h",dut.pixel_epoch,rgb,expected_color);
            checked_pixels=checked_pixels+1;
        end
        expected_de=rst_n && de;
        expected_color=desired_color;
    end
    task drive(input integer px,input integer py,input bit active,input bit vb);
        begin @(negedge pixel_clk);x=px;y=py;de=active;vblank=vb;end
    endtask
    task begin_frame;
        begin
            drive(0,HEIGHT,0,1);
            repeat(40) drive(1,HEIGHT,0,0);
        end
    endtask
    task line(input integer py);
        integer px;
        begin
            for(px=0;px<WIDTH+16;px=px+1) drive(px,py,px<WIDTH,0);
        end
    endtask
    integer n,py,old_checked;
    reg [31:0] old_underruns;
    initial begin
        #43;rst_n=1;
        begin_frame();
        wait(dut.valid0 && dut.valid1);
        if(!front_valid) $fatal(1,"initial frame never became valid");
        frame_pending=0;return_data=0; // The next line request will time out.
        desired_color=24'h00ff00;check_pixels=1;
        line(0); // Prove actual nonzero DDR pixels exist before stopping reads.
        drive(1,HEIGHT,0,0);
        wait(fetch_fault);
        repeat(4) @(negedge clk);
        fault_phase=1;requests_at_fault=requests;
        desired_color=0;
        old_checked=checked_pixels;old_underruns=underruns;
        for(n=0;n<256;n=n+1) begin
            begin_frame();
            if(dut.pixel_epoch==0) wraps=wraps+1;
            for(py=0;py<HEIGHT;py=py+1) line(py);
            drive(1,HEIGHT,0,0);
        end
        repeat(8) @(negedge clk);
        if(wraps!=1 || checked_pixels-old_checked!=256*WIDTH*HEIGHT || requests!=requests_at_fault)
            $fatal(1,"incomplete epoch/no-read coverage");
        if(underruns-old_underruns < 256*HEIGHT)
            $fatal(1,"missing lines stopped counting after valid tags were cleared");
        // Joint reset cancels the fault and ownership; a new DDR fetch must work.
        check_pixels=0;fault_phase=0;
        @(negedge clk);rst_n=0;
        repeat(5) @(negedge clk);
        return_data=1;frame_pending=1;rst_n=1;
        begin_frame();
        wait(dut.valid0 && dut.valid1);
        if(fetch_fault || underruns!=0 || !front_valid) $fatal(1,"reset did not restore fetch state");
        desired_color=24'h00ff00;check_pixels=1;
        line(0);drive(1,HEIGHT,0,0);
        repeat(4) @(negedge pixel_clk);
        $display("PASS video epoch recovery: real timeout, 256-frame wrap, no stale rows/no new reads, continuing underrun counts and reset recovery");
        $finish;
    end
    initial begin #2000000;$fatal(1,"epoch recovery test timeout");end
endmodule
