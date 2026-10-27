`timescale 1ns/1ps
`include "src/memory/ddr_address_map.vh"
module tb_video_scanout #(parameter integer USE_QUEUES=0, VIDEO_720P30=0, VIDEO_720P60=0,
                         READ_LATENCY_CYCLES=64);
    localparam integer VIDEO_720=VIDEO_720P30 || VIDEO_720P60;
    localparam integer WIDTH=VIDEO_720 ? 1280 : 1920, HEIGHT=8;
    localparam integer H_TOTAL=VIDEO_720P60 ? 1650 : VIDEO_720P30 ? 3300 : 2200;
    localparam integer V_BLANK=VIDEO_720 ? 30 : 45;
    localparam realtime PIXEL_HALF_NS=VIDEO_720 ? 6.734007 : 3.3670035;
    reg memory_clk=0, pixel_clk=0, reset_n=0;
    always #5 memory_clk=~memory_clk;
    always #(PIXEL_HALF_NS) pixel_clk=~pixel_clk;
    reg [11:0] pixel_x=0;
    reg [10:0] pixel_y=HEIGHT;
    reg vblank_start=0;
    wire data_enable=pixel_x<WIDTH && pixel_y<HEIGHT;
    wire hsync=VIDEO_720P60 ? pixel_x>=1390 && pixel_x<1430 :
        VIDEO_720P30 ? pixel_x>=3040 && pixel_x<3080 : pixel_x>=2008 && pixel_x<2052;
    wire vsync=pixel_y==HEIGHT+1;
    reg frame_pending=1;
    reg [28:0] frame_base=`PRJ1_DDR_VIDEO_FRAME0_APP_BASE;
    wire frame_swap,front_bank,front_valid,request_valid,fetch_fault;
    wire [28:0] request_address;
    wire [31:0] underruns;
    wire [23:0] rgb;
    wire out_de,out_hsync,out_vsync;
    wire request_ready,response_valid;
    wire [255:0] response_data;
    reg model_ready=0,model_response_valid=0;
    reg [255:0] model_response_data=0;
    wire model_request;
    wire [28:0] model_address;
    wire native_fault,native_write;
    integer background_writes=0;
    generate
        if(USE_QUEUES) begin : g_native
            wire app_enable,app_write_enable,app_write_end;
            wire [2:0] app_command;
            wire [255:0] app_data;
            wire [31:0] app_mask;
            basic_pitch_ddr_client_queues queues (
                .clk(memory_clk),.reset_n(reset_n),.bist_done(1'b1),
                .bist_valid(1'b0),.bist_write(1'b0),.bist_address(29'd0),.bist_data(256'd0),
                .scan_valid(request_valid),.scan_address(request_address),
                .scan_ready(request_ready),.scan_response(response_valid),
                .display_valid(1'b0),.display_address(29'd0),
                .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),
                .music_valid(1'b0),.music_write(1'b0),.music_address(29'd0),.music_data(256'd0),.music_mask(32'd0),
                .delay_valid(1'b0),.delay_write(1'b0),.delay_address(29'd0),.delay_data(256'd0),
                .writer_valid(1'b1),.writer_address(29'h08000000),.writer_data(256'h1234),
                .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),.cpu_mask(32'd0),
                .app_cmd(app_command),.app_en(app_enable),.app_wren(app_write_enable),.app_wend(app_write_end),
                .app_address(model_address),.app_data(app_data),.app_mask(app_mask),
                .app_ready(model_ready),.app_write_ready(model_ready),
                .app_response(model_response_valid),.app_response_data(model_response_data),
                .response_data(response_data),.response_fault(native_fault));
            assign model_request=app_enable && app_command==3'b001;
            assign native_write=app_write_enable;
        end else begin : g_direct
            assign request_ready=model_ready;
            assign response_valid=model_response_valid;
            assign response_data=model_response_data;
            assign model_request=request_valid;
            assign model_address=request_address;
            assign native_fault=1'b0;
            assign native_write=1'b0;
        end
    endgenerate
    video_ddr_scanout #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.EXPLICIT_BASE(1)) dut (
        .clk(memory_clk),.rst_n(reset_n),.enabled(1'b1),
        .new_frame_pending(frame_pending),.new_frame_base(frame_base),
        .new_composite(1'b0),.new_analysis_base(29'd0),
        .frame_swap(frame_swap),.front_bank(front_bank),.front_valid(front_valid),
        .req_valid(request_valid),.req_ready(request_ready),.req_addr(request_address),
        .rsp_valid(response_valid),.rsp_data(response_data),
        .fetch_fault(fetch_fault),.underruns(underruns),
        .pixel_clk(pixel_clk),.pixel_rst_n(reset_n),.pixel_x(pixel_x),.pixel_y(pixel_y),
        .data_enable(data_enable),.hsync(hsync),.vsync(vsync),.vblank_start(vblank_start),
        .rgb(rgb),.out_de(out_de),.out_hsync(out_hsync),.out_vsync(out_vsync));

    function automatic [15:0] color565(input integer position,input integer generation);
        color565={5'b10000 | generation[4:0],position[5:0],position[10:6]^generation[4:0]};
    endfunction
    function automatic [23:0] expand565(input [15:0] color);
        expand565={color[15:11],color[15:13],color[10:5],color[10:9],color[4:0],color[4:2]};
    endfunction

    integer memory_cycle=0,queue_head=0,queue_tail=0;
    reg [28:0] queued_address[0:16383];
    integer queued_due[0:16383];
    integer blocked_cycles=0,stall_mode=0,read_latency=READ_LATENCY_CYCLES;
    integer selected_generation=1;
    integer response_position,response_generation;
    reg stall_started=0;
    always @(negedge memory_clk) begin
        if(reset_n) begin
            memory_cycle=memory_cycle+1;
            model_ready=memory_cycle%11!=0;
            model_response_valid=0;
            if(blocked_cycles>0) blocked_cycles=blocked_cycles-1;
            else if(queue_head<queue_tail && memory_cycle>=queued_due[queue_head]) begin
                model_response_valid=1;
                response_generation=queued_address[queue_head]>=`PRJ1_DDR_VIDEO_FRAME1_APP_BASE ? 2 : 1;
                response_position=((queued_address[queue_head] & 29'h000fffff)>>3)*16;
                for(integer lane=0;lane<16;lane=lane+1)
                    model_response_data[lane*16+:16]=color565(response_position+lane,response_generation);
                queue_head=queue_head+1;
            end
        end
    end
    always @(posedge memory_clk) begin
        if(reset_n) begin
            if(model_request && model_ready) begin
                if(queue_tail==16384) $fatal(1,"response queue capacity");
                queued_address[queue_tail]=model_address;
                queued_due[queue_tail]=memory_cycle+read_latency;
                queue_tail=queue_tail+1;
                if(stall_mode!=0 && !stall_started && dut.fetch_line==3) begin
                    stall_started=1;
                    blocked_cycles=(stall_mode==1 ? 2100 : 15000)*(VIDEO_720P30 ? 3 : VIDEO_720P60 ? 2 : 1);
                end
            end
            if(frame_swap) frame_pending<=0;
            if(native_write) background_writes=background_writes+1;
            if(native_fault) $fatal(1,"native arbiter response fault");
            if(fetch_fault) $fatal(1,"unexpected fetch fault");
            if(dut.outstanding>8 || dut.response_count>8)
                $fatal(1,"response credit overflow");
        end
    end

    reg delayed_de=0,delayed_hsync=0,delayed_vsync=0;
    integer delayed_x=0,delayed_y=0,delayed_generation=1;
    integer colored_lines=0,black_lines=0,checked_pixels=0;
    integer allowed_black=0;
    reg line_black=0;
    reg [23:0] expected_rgb;
    always @(posedge pixel_clk) begin
        #0.001;
        if(reset_n) begin
            if({out_de,out_hsync,out_vsync}!=={delayed_de,delayed_hsync,delayed_vsync})
                $fatal(1,"timing pipeline mismatch");
            if(delayed_de) begin
                if(delayed_x==0) begin
                    line_black=rgb==0;
                    if(line_black) begin
                        black_lines=black_lines+1;
                        if(!allowed_black) $fatal(1,"unexpected black line %0d",delayed_y);
                    end else colored_lines=colored_lines+1;
                end
                expected_rgb=line_black ? 24'd0 : expand565(color565(delayed_y*WIDTH+delayed_x,delayed_generation));
                if(rgb!==expected_rgb)
                    $fatal(1,"pixel mismatch x=%0d y=%0d got=%h expected=%h",delayed_x,delayed_y,rgb,expected_rgb);
                checked_pixels=checked_pixels+1;
            end
        end
        delayed_de=reset_n && data_enable;
        delayed_hsync=reset_n && hsync;
        delayed_vsync=reset_n && vsync;
        delayed_x=pixel_x;delayed_y=pixel_y;delayed_generation=selected_generation;
    end

    task automatic drive_pixel(input integer column,input integer row,input bit blank_start);
        @(negedge pixel_clk);
        pixel_x=column;pixel_y=row;vblank_start=blank_start;
    endtask
    task automatic run_frame(input integer mode,input integer allow_missing);
        integer previous_pixels,previous_black,previous_colored;
        begin
            stall_mode=mode;stall_started=0;allowed_black=allow_missing;
            previous_pixels=checked_pixels;previous_black=black_lines;previous_colored=colored_lines;
            drive_pixel(0,HEIGHT,1);
            for(integer blank=1;blank<V_BLANK*H_TOTAL;blank=blank+1)
                drive_pixel(blank%H_TOTAL,HEIGHT,0);
            if(!front_valid) $fatal(1,"front frame not published");
            selected_generation=dut.front_base>=`PRJ1_DDR_VIDEO_FRAME1_APP_BASE ? 2 : 1;
            for(integer row=0;row<HEIGHT;row=row+1)
                for(integer column=0;column<H_TOTAL;column=column+1)
                    drive_pixel(column,row,0);
            drive_pixel(0,HEIGHT,0);
            repeat(3) drive_pixel(1,HEIGHT,0);
            if(checked_pixels-previous_pixels!=WIDTH*HEIGHT) $fatal(1,"pixel coverage mismatch");
            if(mode==1 && (black_lines==previous_black || colored_lines==previous_colored))
                $fatal(1,"late response case did not exercise missing and good lines");
        end
    endtask

    integer requested_mode=0;
    initial begin
        if(!$value$plusargs("MODE=%d",requested_mode)) requested_mode=0;
        repeat(8) @(negedge memory_clk);
        reset_n=1;
        run_frame(0,0);
        run_frame(0,0);
        if(requested_mode==1) begin
            run_frame(1,1);
            run_frame(0,0);
        end else if(requested_mode==2) begin
            run_frame(2,1);
            run_frame(0,1);
            run_frame(0,0);
        end else begin
            @(negedge memory_clk);frame_base=`PRJ1_DDR_VIDEO_FRAME1_APP_BASE;frame_pending=1;
            run_frame(0,0);
            run_frame(0,0);
            if(selected_generation!=2) $fatal(1,"new frame was not selected");
            if(underruns!=0) $fatal(1,"steady-state underrun count %0d",underruns);
        end
        if(USE_QUEUES && background_writes==0) $fatal(1,"background traffic not exercised");
        $display("PASS mode=%0d queues=%0d checked_pixels=%0d colored_lines=%0d black_lines=%0d underruns=%0d background_writes=%0d",requested_mode,USE_QUEUES,checked_pixels,colored_lines,black_lines,underruns,background_writes);
        $finish;
    end
    initial begin #20000000;$fatal(1,"test timeout");end
endmodule
