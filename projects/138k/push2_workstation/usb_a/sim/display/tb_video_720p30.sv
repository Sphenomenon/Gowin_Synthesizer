`timescale 1ns/1ps
module tb_video_720p30 #(parameter integer REFRESH_HZ=30);
    localparam integer H_TOTAL=REFRESH_HZ==60 ? 1650 : 3300;
    localparam integer H_SYNC_START=REFRESH_HZ==60 ? 1390 : 3040;
    localparam integer H_SYNC_END=H_SYNC_START+40;
    reg pixel_clk=0, reset_n=0;
    always #6.734007 pixel_clk=~pixel_clk;
    wire [11:0] pixel_x;
    wire [10:0] pixel_y;
    wire data_enable,hsync,vsync,frame_start,line_start,vblank_start;
    generate
        if(REFRESH_HZ==60) begin : g_60
            workstation_video_timing_720p60 dut (.*);
        end else begin : g_30
            workstation_video_timing_720p30 dut (.*);
        end
    endgenerate
    integer active_pixels=0, blank_events=0;
    initial begin
        repeat(4) @(negedge pixel_clk);
        reset_n=1;
        for(integer frame_index=0;frame_index<2;frame_index=frame_index+1) begin
            for(integer row=0;row<750;row=row+1) begin
                for(integer column=0;column<H_TOTAL;column=column+1) begin
                    #0.001;
                    if(pixel_x!==column || pixel_y!==row) $fatal(1,"raster coordinate mismatch");
                    if(data_enable!==(column<1280 && row<720)) $fatal(1,"active raster mismatch");
                    if(hsync!==(column>=H_SYNC_START && column<H_SYNC_END)) $fatal(1,"horizontal sync mismatch");
                    if(vsync!==(row>=725 && row<730)) $fatal(1,"vertical sync mismatch");
                    if(frame_start!==(column==0 && row==0)) $fatal(1,"frame marker mismatch");
                    if(line_start!==(column==0)) $fatal(1,"line marker mismatch");
                    if(vblank_start!==(column==0 && row==720)) $fatal(1,"vblank marker mismatch");
                    if(data_enable) active_pixels=active_pixels+1;
                    if(vblank_start) blank_events=blank_events+1;
                    @(negedge pixel_clk);
                end
            end
        end
        if(active_pixels!=1843200 || blank_events!=2) $fatal(1,"frame coverage mismatch");
        #1 reset_n=0;
        #1;
        if(pixel_x!=0 || pixel_y!=0 || vblank_start!=0) $fatal(1,"asynchronous reset mismatch");
        $display("PASS 720p%0d: %0dx750 totals, 1280x720 active, two frames, sync and reset",REFRESH_HZ,H_TOTAL);
        $finish;
    end
    initial begin #70000000; $fatal(1,"raster timeout"); end
endmodule

module tb_video_720p_renderer;
    reg clk=0,rst_n=0,start=0,pixel_ready=0;
    always #5 clk=~clk;
    wire frame_ready,busy,frame_done,pixel_valid;
    wire [63:0] pixel_data;
    feedback_renderer #(.WIDTH(1280),.HEIGHT(720),.SCALE_THREE_HALVES(1)) dut (
        .clk(clk),.rst_n(rst_n),.start(start),.frame_ready(frame_ready),.busy(busy),
        .frame_done(frame_done),.pixel_valid(pixel_valid),.pixel_ready(pixel_ready),.pixel_data(pixel_data),
        .source_clk(clk),.source_reset_n(rst_n),.sample_data(32'd0),.sample_valid(1'b0),
        .output_pcm(32'd0),.trigger_reference(32'd0),.active_voices(32'd0),.status_data(32'd0),
        .effect_mask(3'd0),.effect_order(6'b10_01_00),.memory_status(32'd0),
        .underruns(32'd0),.frame_count(32'd0),.shared_done(1'b0),.shared_read_enable(1'b0),
        .shared_read_kind(2'd0),.shared_read_addr(16'd0),.shared_render_wave_data(32'd0),
        .shared_render_image_hit(1'b0),.shared_render_spectrum_left(8'd0),.shared_render_spectrum_right(8'd0),
        .shared_render_meta(256'd0),.shared_render_analysis_sequence(32'd0),.shared_render_analysis_skipped(32'd0),
        .shared_render_stereo_peaks(32'd0),.shared_render_image_gain(3'd0),.shared_render_analysis_valid(1'b0));
    integer cycles=0,accepted=0,stalled=0;
    integer frame_file=0;
    string frame_dump_path;
    integer expected_column,expected_row;
    reg held_valid=0;
    reg [63:0] held_pixels;
    reg [10:0] held_x,held_y;
    always @(negedge clk) begin
        cycles=cycles+1;
        pixel_ready=cycles%19<12;
    end
    always @(posedge clk) begin
        if(rst_n) begin
            if(held_valid && (!pixel_valid || pixel_data!==held_pixels || dut.output_x!==held_x || dut.output_y!==held_y))
                $fatal(1,"renderer changed a stalled output");
            held_valid=pixel_valid && !pixel_ready;
            if(held_valid) begin
                held_pixels=pixel_data;held_x=dut.output_x;held_y=dut.output_y;stalled=stalled+1;
            end
            if(pixel_valid && pixel_ready) begin
                if(^pixel_data===1'bx) $fatal(1,"renderer emitted unknown pixel data");
                expected_column=(accepted%640)*2;
                expected_row=accepted/640;
                if(dut.output_x!==expected_column*3/2 || dut.output_y!==expected_row*3/2)
                    $fatal(1,"canvas map mismatch pair=%0d x=%0d y=%0d",accepted,dut.output_x,dut.output_y);
                if(dut.u_odd.pixel_x!==dut.u_even.pixel_x+11'd1)
                    $fatal(1,"canvas odd pixel mismatch");
                if(frame_file!=0)
                    $fwrite(frame_file,"%c%c%c%c%c%c",pixel_data[23:16],pixel_data[15:8],pixel_data[7:0],
                            pixel_data[55:48],pixel_data[47:40],pixel_data[39:32]);
                accepted=accepted+1;
            end
            if(frame_done) begin
                if(accepted!=460800 || stalled==0 || busy) $fatal(1,"renderer coverage mismatch");
                if(frame_file!=0) $fclose(frame_file);
                $display("PASS 720p renderer: %0d pairs, full canvas, %0d stalled cycles",accepted,stalled);
                $finish;
            end
        end
    end
    initial begin
        if($value$plusargs("FRAME_DUMP=%s",frame_dump_path)) begin
            frame_file=$fopen(frame_dump_path,"wb");
            if(frame_file==0) $fatal(1,"cannot open frame dump");
            $fwrite(frame_file,"P6\n1280 720\n255\n");
        end
        force dut.snapshot_ready=1;
        force dut.aligned_ready=1;
        force dut.snapshot_peak=0;
        force dut.snapshot_voices=0;
        force dut.snapshot_status=0;
        force dut.snapshot_sequence=0;
        force dut.snapshot_skipped=0;
        force dut.render_wave_data=0;
        force dut.waveform_held=0;
        repeat(5) @(negedge clk);
        rst_n=1;
        @(negedge clk);start=1;
        @(negedge clk);start=0;
    end
    initial begin #20000000;$fatal(1,"renderer timeout");end
endmodule
