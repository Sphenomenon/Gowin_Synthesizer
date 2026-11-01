`timescale 1ns/1ps
module tb_contest_brand_unit;
    reg clk=0,enable=0;
    reg [10:0] x=0,y=0;
    wire hit,reference_hit;
    wire [23:0] rgb,reference_rgb;
    workstation_contest_brand actual(.clk,.enable,.pixel_x(x),.pixel_y(y),.hit,.pixel_rgb(rgb));
    reference_workstation_contest_brand reference(.clk,.enable,.pixel_x(x),.pixel_y(y),.hit(reference_hit),.pixel_rgb(reference_rgb));
    integer pixels=0,stalls=0,text_addresses=0,ink=0,check_address=0;
    task tick(input bit live);
        reg [24:0] previous;
        begin
            enable=live;previous={hit,rgb};#2;clk=1;#2;
            if({hit,rgb}!=={reference_hit,reference_rgb})
                $fatal(1,"brand pixel mismatch xy=%0d,%0d got=%h want=%h",x,y,{hit,rgb},{reference_hit,reference_rgb});
            if(!live)begin
                if({hit,rgb}!==previous)$fatal(1,"brand stalled state moved");
                stalls=stalls+1;
            end else begin
                if($isunknown({hit,rgb}))$fatal(1,"unknown brand pixel");
                pixels=pixels+1;
                if(hit && rgb!=24'hffffff)ink=ink+1;
                if(actual.text_hit)begin
                    if(check_address!=0 && (actual.glyph_address!==reference.glyph_address || actual.glyph_column!==reference.glyph_column))
                        $fatal(1,"brand address mismatch xy=%0d,%0d",x,y);
                    text_addresses=text_addresses+1;
                end
            end
            clk=0;
        end
    endtask
    initial begin
        if($value$plusargs("CHECK_ADDRESS=%d",check_address))begin end
        tick(1);pixels=0;
        for(integer yy=0;yy<2048;yy=yy+1)for(integer xx=0;xx<2048;xx=xx+1)begin
            x=11'(xx);y=11'(yy);
            if((xx+yy)%113==0)begin
                x=11'(xx)^11'h155;y=11'(yy)^11'h2aa;tick(0);
                x=11'(xx);y=11'(yy);
            end
            tick(1);
        end
        if(pixels!=4194304 || text_addresses!=34560 || stalls<30000 || ink==0)$fatal(1,"brand coverage");
        $display("PASS brand unit: pixels=%0d stalls=%0d text_addresses=%0d ink=%0d enabled_latency=1",pixels,stalls,text_addresses,ink);
        $finish;
    end
endmodule

module tb_contest_brand_dashboard;
    reg clk=0,rst=0,enable=1,frame_start=0;
    reg [10:0] x=0,y=0;
    reg [128:0] parameters=0;
    reg signed [31:0] wave=0;
    wire [31:0] actual[0:3],reference[0:3];
    integer ticks=0,stalls=0,pixels=0;
    `define DASHBOARD_PORTS .clk(clk),.reset_n(rst),.enable(enable),.frame_start(frame_start),.pixel_x(x),.pixel_y(y),.wave_sample(wave),.wave_previous(wave-32'sd4194304),.waveform_held(1'b0),.spectrum_left(8'(x+y)),.spectrum_right(8'(x*3+y)),.image_hit(x[4:0]==y[4:0]),.peak_left(16'(x*29+y)),.peak_right(16'(x+y*31)),.image_gain(3'd0),.analysis_sequence(32'd91),.analysis_skipped(32'd0),.peak_data(32'h40000000),.active_voices(32'hffff),.status_data(32'd0),.applied_parameters(parameters),.effect_mask(3'b111),.effect_order(6'b10_01_00),.sequence_data(32'd91),.skipped_data(32'd0),.memory_status(32'd3),.underruns(32'd0),.framecount(32'd1)
    for(genvar config_id=0;config_id<4;config_id=config_id+1)begin:configs
        feedback_dashboard #(.ENABLE_ANALYSIS(config_id&1),.HMI_D_ONLY(config_id>>1)) current(`DASHBOARD_PORTS,.pixel_data(actual[config_id]));
        reference_feedback_dashboard #(.ENABLE_ANALYSIS(config_id&1),.HMI_D_ONLY(config_id>>1)) frozen(`DASHBOARD_PORTS,.pixel_data(reference[config_id]));
    end
    `undef DASHBOARD_PORTS
    task tick(input bit live);
        reg [127:0] previous;
        begin
            enable=live;previous={actual[0],actual[1],actual[2],actual[3]};#2;clk=1;#2;
            for(integer c=0;c<4;c=c+1)if(actual[c]!==reference[c])
                $fatal(1,"dashboard pixel mismatch config=%0d xy=%0d,%0d tick=%0d",c,x,y,ticks);
            if(!live)begin
                if(previous!=={actual[0],actual[1],actual[2],actual[3]})$fatal(1,"dashboard stalled output moved");
                stalls=stalls+1;
            end
            clk=0;ticks=ticks+1;
        end
    endtask
    initial begin
        #1;rst=0;tick(0);rst=1;
        parameters={1'b0,32'h00000100,16'h6000,6'd16,3'd2,2'd0,2'd2,3'b111,32'h00100000,11'd0,7'd64,7'd96,7'd32};
        frame_start=1;repeat(100)tick(1);frame_start=0;
        for(integer yy=0;yy<1080;yy=yy+1)for(integer xx=0;xx<1920;xx=xx+1)begin
            x=11'(xx);y=11'(yy);wave=($signed({1'b0,x[8:0]})-32'sd256)<<<22;
            if((xx+yy)%97==0)tick(0);
            tick(1);pixels=pixels+1;
        end
        for(integer n=0;n<65536;n=n+1)begin
            x=11'(n*37);y=11'(n*91);parameters[95:88]=8'(n);parameters[128]=1'(n);
            frame_start=(n%71)==0;tick((n%13)!=0);
        end
        $display("PASS brand dashboard: configurations=4 pixels_per_config=%0d extra_vectors=65536 ticks=%0d stalls=%0d enabled_latency=4",pixels,ticks,stalls);
        $finish;
    end
endmodule

module tb_contest_brand_renderer;
    reg clk=0,rst=0,start=0,ready=0;
    always #5 clk=~clk;
    wire [1:0] current_valid,reference_valid,current_done,reference_done,current_busy,reference_busy;
    wire [63:0] current_pixels[0:1],reference_pixels[0:1];
    integer cycles=0;
    reg [1:0] complete=0;
    for(genvar mode=0;mode<2;mode=mode+1)begin:resolution
        localparam integer W=mode==0 ? 1920 : 1280;
        localparam integer H=mode==0 ? 1080 : 720;
        wire [31:0] wave=32'(cycles*65521);
        `define RENDERER_PORTS .clk(clk),.rst_n(rst),.start(start),.pixel_ready(ready),.source_clk(clk),.source_reset_n(rst),.sample_data(32'd0),.sample_valid(1'b0),.output_pcm(32'd0),.trigger_reference(32'd0),.active_voices(32'hffff),.status_data(32'd0),.applied_parameters(129'd0),.effect_mask(3'b111),.effect_order(6'b10_01_00),.memory_status(32'd3),.underruns(32'd0),.frame_count(32'd1),.shared_done(1'b0),.shared_read_enable(1'b0),.shared_read_kind(2'd0),.shared_read_addr(16'd0),.shared_render_wave_data(wave),.shared_render_image_hit(cycles[4:0]==5'd0),.shared_render_spectrum_left(8'(cycles)),.shared_render_spectrum_right(8'(cycles*3)),.shared_render_meta(256'd0),.shared_render_analysis_sequence(32'd91),.shared_render_analysis_skipped(32'd0),.shared_render_stereo_peaks(32'h40002000),.shared_render_image_gain(3'd0),.shared_render_analysis_valid(1'b1)
        feedback_renderer #(.WIDTH(W),.HEIGHT(H),.SCALE_THREE_HALVES(mode),.ENABLE_ANALYSIS(0),.RENDER_ANALYSIS(1),.SHARED_RENDER(1)) current(
            `RENDERER_PORTS,.pixel_valid(current_valid[mode]),.pixel_data(current_pixels[mode]),.frame_done(current_done[mode]),.busy(current_busy[mode]));
        reference_feedback_renderer #(.WIDTH(W),.HEIGHT(H),.SCALE_THREE_HALVES(mode),.ENABLE_ANALYSIS(0),.RENDER_ANALYSIS(1),.SHARED_RENDER(1)) frozen(
            `RENDERER_PORTS,.pixel_valid(reference_valid[mode]),.pixel_data(reference_pixels[mode]),.frame_done(reference_done[mode]),.busy(reference_busy[mode]));
        `undef RENDERER_PORTS
        integer accepted=0,stalls=0;
        reg was_stalled=0;
        reg [63:0] held_pixels;
        reg [10:0] held_x,held_y;
        always @(posedge clk)if(rst)begin
            if({current_valid[mode],current_done[mode],current_busy[mode]}!=={reference_valid[mode],reference_done[mode],reference_busy[mode]})
                $fatal(1,"renderer handshake mismatch mode=%0d",mode);
            if(current_valid[mode] && current_pixels[mode]!==reference_pixels[mode])
                $fatal(1,"renderer pixel mismatch mode=%0d pair=%0d",mode,accepted);
            if(was_stalled && (!current_valid[mode] || current_pixels[mode]!==held_pixels || current.output_x!==held_x || current.output_y!==held_y))
                $fatal(1,"renderer stalled output moved mode=%0d",mode);
            was_stalled=current_valid[mode] && !ready;
            if(was_stalled)begin
                held_pixels=current_pixels[mode];held_x=current.output_x;held_y=current.output_y;stalls=stalls+1;
            end
            if(current_valid[mode] && ready)begin
                if($isunknown(current_pixels[mode]))$fatal(1,"unknown renderer pixel");
                if(current.output_x!==11'(((accepted%(W/2))*2)*(mode==0 ? 2 : 3)/2) || current.output_y!==11'((accepted/(W/2))*(mode==0 ? 2 : 3)/2))
                    $fatal(1,"renderer coordinate mismatch mode=%0d",mode);
                accepted=accepted+1;
            end
            if(current_done[mode])begin
                if(accepted!=W*H/2 || stalls==0 || current_busy[mode])$fatal(1,"renderer coverage mode=%0d",mode);
                complete[mode]=1;
                $display("PASS brand renderer: width=%0d height=%0d accepted_pairs=%0d stalls=%0d",W,H,accepted,stalls);
            end
        end
        initial begin
            // Frozen and maintained raster logic both run unchanged. Override
            // only capture readiness/data stimulus, as the 720p renderer test.
            force current.snapshot_ready=1;force current.aligned_ready=1;
            force frozen.snapshot_ready=1;force frozen.aligned_ready=1;
        end
    end
    always @(negedge clk)begin cycles=cycles+1;ready=cycles%19<12;end
    initial begin
        repeat(5)@(negedge clk);rst=1;
        repeat(3)@(negedge clk);start=1;@(negedge clk);start=0;
        wait(&complete);$display("PASS brand actual renderer: both complete rasters equivalent");$finish;
    end
    initial begin #30000000;$fatal(1,"renderer timeout");end
endmodule
