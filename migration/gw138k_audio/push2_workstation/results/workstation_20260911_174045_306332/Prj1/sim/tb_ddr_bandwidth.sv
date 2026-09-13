`timescale 1ns/1fs
// Throughput budget model, NOT a physical DDR3/PHY simulation.
// UI=100 MHz; exact nominal pixel=148.5 MHz, CTA 2200x1125 raster.
// Shared native command port: read priority; one BL8/accepted command.
// Command ready blocked every fourth cycle; write ready additionally blocked
// every eighth cycle. Both channels and read returns pause for 26 of every
// 780 UI cycles (260 ns per 7.8 us refresh budget). Reads become eligible to
// return after 12-15 cycles; ordered delivery/refresh can extend that delay.
// At most one return/UI cycle is emitted; queue depth is 64.
// A lightweight renderer emits 2 constant-color pixels/cycle under ready.
module tb_ddr_bandwidth;
    localparam integer WIDTH=1920, HEIGHT=1080, FRAME_BEATS=129600;
    localparam integer STRIDE=1048576;
    localparam real FRAME_NS=1000000000.0/60.0;
    reg clk=0,pixel_clk=0;
    always #5 clk=~clk;
    always #(500.0/148.5) pixel_clk=~pixel_clk;
    reg rst_n=0,pixel_rst_n=0;
    wire [11:0] pixel_x;
    wire [10:0] pixel_y;
    wire de,hs,vs,frame_start,line_start,vblank_start;
    video_timing_1080p timing (
        .pixel_clk(pixel_clk),.reset_n(pixel_rst_n),.pixel_x(pixel_x),
        .pixel_y(pixel_y),.data_enable(de),.hsync(hs),.vsync(vs),
        .frame_start(frame_start),.line_start(line_start),.vblank_start(vblank_start)
    );
    wire frame_swap,front_bank,front_valid,frame_pending,fetch_fault;
    wire [31:0] rendered_frames,underruns;
    wire s_valid,w_valid;
    reg s_ready=0,w_ready=0,rsp_valid=0;
    wire [28:0] s_addr,w_addr;
    reg [255:0] rsp_data=0;
    wire [255:0] w_data;
    wire [23:0] rgb;
    wire out_de,out_hs,out_vs;
    video_ddr_scanout scanout (
        .clk(clk),.rst_n(rst_n),.enabled(1'b1),
        .new_frame_pending(frame_pending),.frame_swap(frame_swap),
        .front_bank(front_bank),.front_valid(front_valid),
        .req_valid(s_valid),.req_ready(s_ready),.req_addr(s_addr),
        .rsp_valid(rsp_valid),.rsp_data(rsp_data),.fetch_fault(fetch_fault),
        .underruns(underruns),.pixel_clk(pixel_clk),.pixel_rst_n(pixel_rst_n),
        .pixel_x(pixel_x),.pixel_y(pixel_y),.data_enable(de),
        .hsync(hs),.vsync(vs),.vblank_start(vblank_start),
        .rgb(rgb),.out_de(out_de),.out_hsync(out_hs),.out_vsync(out_vs)
    );
    wire renderer_start,pixel_ready;
    reg renderer_ready=1,renderer_done=0,pixel_valid=0;
    reg [63:0] pixel_data=0;
    ddr_frame_writer writer (
        .clk(clk),.rst_n(rst_n),.enabled(1'b1),.front_bank(front_bank),
        .frame_swap(frame_swap),.renderer_ready(renderer_ready),
        .renderer_done(renderer_done),.renderer_start(renderer_start),
        .pixel_valid(pixel_valid),.pixel_ready(pixel_ready),.pixel_data(pixel_data),
        .req_valid(w_valid),.req_ready(w_ready),.req_addr(w_addr),.req_wdata(w_data),
        .frame_pending(frame_pending),.rendered_frames(rendered_frames)
    );
    function [15:0] generation_color(input integer n);
        generation_color={5'b10000|n[4:0],6'b101010,5'b01000|n[4:0]};
    endfunction
    function [23:0] expand565(input [15:0] c);
        expand565={c[15:11],c[15:13],c[10:5],c[10:9],c[4:0],c[4:2]};
    endfunction

    integer ui_cycle=0,refresh_phase=0;
    integer generation=0,pairs_sent=0,writes_this_frame=0;
    integer bank_generation[0:1];
    integer read_count=0,write_count=0,return_count=0,max_inflight=0;
    integer qhead=0,qtail=0;
    integer return_due[0:63];
    reg [255:0] return_data[0:63];
    reg [255:0] expected_wdata;
    reg [23:0] expected_screen_rgb;
    integer swaps=0,completed_writes=0;
    reg previous_pending=0;
    real render_begin=0,max_render_ns=0,render_duration=0,last_swap_ns=0,swap_period=0;
    reg command_allowed,write_allowed;

    always @(negedge clk) begin
        s_ready=0;w_ready=0;rsp_valid=0;
        if(rst_n) begin
            command_allowed=(ui_cycle%4!=0)&&(refresh_phase>=26);
            write_allowed=command_allowed&&(ui_cycle%8!=1);
            // Match hdmi_display.v: scanout takes priority over writer.
            s_ready=s_valid&&command_allowed;
            w_ready=!s_valid&&w_valid&&write_allowed;
            if(qhead<qtail && return_due[qhead%64]<=ui_cycle && refresh_phase>=26) begin
                rsp_valid=1;rsp_data=return_data[qhead%64];qhead=qhead+1;
            end
        end
    end
    always @(posedge clk) begin
        if(rst_n) begin
            ui_cycle=ui_cycle+1;
            refresh_phase=(refresh_phase==779)?0:refresh_phase+1;
            renderer_done<=0;
            if(renderer_start) begin
                generation=generation+1;pairs_sent=0;writes_this_frame=0;
                pixel_valid<=1;renderer_ready<=0;
                pixel_data<={8'd0,expand565(generation_color(generation)),
                             8'd0,expand565(generation_color(generation))};
                expected_wdata={16{generation_color(generation)}};
                render_begin=$realtime;
            end else if(pixel_valid&&pixel_ready) begin
                pairs_sent=pairs_sent+1;
                if(pairs_sent==WIDTH*HEIGHT/2) begin
                    pixel_valid<=0;renderer_done<=1;renderer_ready<=1;
                end
            end
            if(w_valid&&w_ready) begin
                if((w_addr%STRIDE)!==writes_this_frame*8 || w_data!==expected_wdata)
                    $fatal(1,"bandwidth writer address/data mismatch");
                if(front_valid && (w_addr>=STRIDE)==front_bank)
                    $fatal(1,"bandwidth writer overwrote front bank");
                writes_this_frame=writes_this_frame+1;write_count=write_count+1;
                if(writes_this_frame==FRAME_BEATS)
                    bank_generation[w_addr>=STRIDE]=generation;
            end
            if(frame_pending&&!previous_pending) begin
                if(writes_this_frame!=FRAME_BEATS)
                    $fatal(1,"bandwidth frame published before final write");
                render_duration=$realtime-render_begin;
                if(render_duration>max_render_ns) max_render_ns=render_duration;
                if(render_duration>=FRAME_NS)
                    $fatal(1,"renderer+writer missed 60 FPS budget: %0.6f ms",render_duration/1e6);
                completed_writes=completed_writes+1;
                $display("BANDWIDTH back frame %0d complete: %0.6f ms (budget 16.666667 ms)",generation,render_duration/1e6);
            end
            previous_pending=frame_pending;
            if(frame_swap) begin
                if(!frame_pending || de)
                    $fatal(1,"bandwidth invalid swap");
                if(swaps!=0) begin
                    swap_period=$realtime-last_swap_ns;
                    if(swap_period<FRAME_NS-20 || swap_period>FRAME_NS+20)
                        $fatal(1,"missed a 1080p60 frame boundary: %0.6f ms",swap_period/1e6);
                end
                last_swap_ns=$realtime;swaps=swaps+1;
                expected_screen_rgb=expand565(generation_color(bank_generation[front_bank]));
            end
            if(s_valid&&s_ready) begin
                if(qtail-qhead>=64) $fatal(1,"bandwidth return queue overflow");
                if(bank_generation[s_addr>=STRIDE]==0)
                    $fatal(1,"read an unwritten frame bank");
                return_data[qtail%64]={16{generation_color(bank_generation[s_addr>=STRIDE])}};
                return_due[qtail%64]=ui_cycle+12+(s_addr[4:3]);
                qtail=qtail+1;read_count=read_count+1;
                if(qtail-qhead>max_inflight) max_inflight=qtail-qhead;
            end
            if(rsp_valid) return_count=return_count+1;
            if(fetch_fault || underruns!=0)
                $fatal(1,"1080p bandwidth underflow/fetch fault after %0d swaps",swaps);
        end
    end

    // Check every active pixel of three whole steady-state frames. At a pixel
    // edge these are the old output registers, avoiding NBA races with timing.
    integer active_pixels=0,checked_frames=0;
    always @(posedge pixel_clk) begin
        if(pixel_rst_n) begin
            if(front_valid&&out_de) begin
                if(rgb!==expected_screen_rgb)
                    $fatal(1,"1080p active pixel has stale/black/incorrect data");
                active_pixels=active_pixels+1;
            end
            if(vblank_start && front_valid) begin
                if(active_pixels!=WIDTH*HEIGHT)
                    $fatal(1,"steady frame pixel count %0d",active_pixels);
                active_pixels=0;checked_frames=checked_frames+1;
                $display("BANDWIDTH steady output frame %0d: 2073600 correct pixels, zero underruns",checked_frames);
                if(checked_frames==3) begin
                    if(swaps!=3 || completed_writes<4 || max_render_ns<=0)
                        $fatal(1,"insufficient steady-state swap/write coverage");
                    $display("BANDWIDTH assumptions: 100 MHz UI, 148.5 MHz pixels, command stalls 1/4, extra write stalls 1/8, refresh 26/780 cycles, nominal read eligibility 12-15 cycles with ordered delivery, 64 pending slots");
                    $display("BANDWIDTH results: max render+DDR write %0.6f ms; margin %0.6f ms; max reads pending %0d; accepted reads=%0d writes=%0d returns=%0d",
                        max_render_ns/1e6,(FRAME_NS-max_render_ns)/1e6,max_inflight,read_count,write_count,return_count);
                    $display("PASS tb_ddr_bandwidth: three complete 1080p60 output frames, fresh back buffer per frame, zero underruns (behavioral budget model only)");
                    $finish;
                end
            end
        end
    end
    initial begin
        bank_generation[0]=0;bank_generation[1]=0;
        repeat(8) @(negedge clk);
        rst_n=1;
        repeat(4) @(negedge pixel_clk);
        pixel_rst_n=1;
    end
    initial begin #80000000;$fatal(1,"bandwidth simulation timed out");end
endmodule
