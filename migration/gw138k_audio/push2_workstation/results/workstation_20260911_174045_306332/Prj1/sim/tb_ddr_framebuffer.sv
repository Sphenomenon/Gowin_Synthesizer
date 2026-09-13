`timescale 1ns/1ps
// Behavioral native DDR boundary: ordered reads, random command stalls and
// return latency. This intentionally excludes the encrypted analog DDR PHY.
module tb_ddr_framebuffer;
    localparam integer WIDTH=64, HEIGHT=8, STRIDE=512, BEATS=32;
    reg clk=0,pixel_clk=0;
    always #5 clk=~clk;
    always #3.4 pixel_clk=~pixel_clk;
    reg rst_n=0,pixel_rst_n=0,enabled=1;
    wire frame_swap,front_bank,front_valid,frame_pending;
    wire [31:0] rendered_frames,underruns;
    wire fetch_fault;
    wire s_valid;
    reg s_ready=0;
    wire [28:0] s_addr;
    reg rsp_valid=0;
    reg [255:0] rsp_data=0;
    reg [11:0] pixel_x=0;
    reg [10:0] pixel_y=HEIGHT;
    reg data_enable=0,hsync=0,vsync=0,vblank_start=0;
    wire [23:0] rgb;
    wire out_de,out_hsync,out_vsync;
    video_ddr_scanout #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),
        .FRAME_STRIDE_WORDS(STRIDE),.TIMEOUT_CYCLES(2000)) scanout (
        .clk(clk),.rst_n(rst_n),.enabled(enabled),
        .new_frame_pending(frame_pending),.frame_swap(frame_swap),
        .front_bank(front_bank),.front_valid(front_valid),
        .req_valid(s_valid),.req_ready(s_ready),.req_addr(s_addr),
        .rsp_valid(rsp_valid),.rsp_data(rsp_data),
        .fetch_fault(fetch_fault),.underruns(underruns),
        .pixel_clk(pixel_clk),.pixel_rst_n(pixel_rst_n),
        .pixel_x(pixel_x),.pixel_y(pixel_y),.data_enable(data_enable),
        .hsync(hsync),.vsync(vsync),.vblank_start(vblank_start),
        .rgb(rgb),.out_de(out_de),.out_hsync(out_hsync),.out_vsync(out_vsync)
    );
    wire renderer_start,pixel_ready,w_valid;
    reg renderer_ready=1,renderer_done=0,pixel_valid=0;
    reg [63:0] pixel_data=0;
    reg w_ready=0;
    wire [28:0] w_addr;
    wire [255:0] w_data;
    ddr_frame_writer #(.FRAME_STRIDE_WORDS(STRIDE)) writer (
        .clk(clk),.rst_n(rst_n),.enabled(enabled),.front_bank(front_bank),
        .frame_swap(frame_swap),.renderer_ready(renderer_ready),
        .renderer_done(renderer_done),.renderer_start(renderer_start),
        .pixel_valid(pixel_valid),.pixel_ready(pixel_ready),.pixel_data(pixel_data),
        .req_valid(w_valid),.req_ready(w_ready),.req_addr(w_addr),
        .req_wdata(w_data),.frame_pending(frame_pending),.rendered_frames(rendered_frames)
    );

    function [15:0] color565(input integer generation,input integer position);
        color565={5'b10000 | generation[4:0],position[5:0],position[10:6]^generation[4:0]};
    endfunction
    function [23:0] expand565(input [15:0] c);
        expand565={c[15:11],c[15:13],c[10:5],c[10:9],c[4:0],c[4:2]};
    endfunction
    function [63:0] pixel_pair(input integer generation,input integer position);
        pixel_pair={8'd0,expand565(color565(generation,position+1)),
                    8'd0,expand565(color565(generation,position))};
    endfunction

    integer generation=0,position=0,write_count=0;
    integer bank_generation[0:1];
    reg [255:0] memory[0:127];
    reg [255:0] queue_data[0:511];
    integer queue_delay[0:511];
    integer qhead=0,qtail=0;
    integer swaps=0,final_stall=0;
    reg final_stalled=0;
    integer stall_mode=0,read_stall=0;
    reg read_stall_started=0;
    reg old_w_held=0;
    reg [284:0] old_w_request;
    integer idx, lane, actual_bank, actual_index;

    // Mock renderer emits two pixels/beat and only completes after acceptance.
    always @(posedge clk) begin
        if(!rst_n) begin
            pixel_valid<=0;renderer_done<=0;renderer_ready<=1;
            generation=0;position=0;write_count=0;
            final_stalled=0;old_w_held=0;qhead=0;qtail=0;swaps=0;
        end else begin
            renderer_done<=0;
            if(renderer_start) begin
                generation=generation+1;position=0;write_count=0;
                pixel_valid<=1;renderer_ready<=0;
                pixel_data<=pixel_pair(generation,0);
                final_stalled=0;
            end else if(pixel_valid && pixel_ready) begin
                if(position==WIDTH*HEIGHT-2) begin
                    pixel_valid<=0;renderer_done<=1;renderer_ready<=1;
                end else begin
                    position=position+2;
                    pixel_data<=pixel_pair(generation,position);
                end
            end
            if(old_w_held && w_valid && {w_addr,w_data}!==old_w_request)
                $fatal(1,"writer request changed under backpressure");
            old_w_held=w_valid&&!w_ready;
            old_w_request={w_addr,w_data};
            if(w_valid&&w_ready) begin
                actual_bank=(w_addr>=STRIDE);
                actual_index=(w_addr%STRIDE)>>3;
                if(actual_index!=write_count || w_addr[2:0]!=0)
                    $fatal(1,"writer address/packing order");
                if(front_valid && actual_bank==front_bank)
                    $fatal(1,"writer modified the displayed frame");
                for(lane=0;lane<16;lane=lane+1)
                    if(w_data[lane*16+:16]!==color565(generation,write_count*16+lane))
                        $fatal(1,"writer RGB565 packing mismatch");
                memory[w_addr>>3]=w_data;
                write_count=write_count+1;
                if(write_count==BEATS) bank_generation[actual_bank]=generation;
            end
            if(frame_pending && write_count!=BEATS)
                $fatal(1,"frame published before all DDR writes were accepted");
            if(frame_swap) begin
                if(!frame_pending || data_enable)
                    $fatal(1,"swap without completed frame or outside blanking");
                swaps=swaps+1;
            end
            if(s_valid&&s_ready) begin
                if(s_addr[2:0]!=0 || (s_addr%STRIDE)>=WIDTH*HEIGHT/2)
                    $fatal(1,"scanout invalid native address");
                queue_data[qtail%512]=memory[s_addr>>3];
                queue_delay[qtail%512]=$urandom_range(1,4);
                qtail=qtail+1;
            end
        end
    end
    always @(negedge clk) begin
        s_ready=0;w_ready=0;rsp_valid=0;
        if(rst_n) begin
            if(stall_mode!=0 && !read_stall_started && s_valid &&
                (s_addr%STRIDE)/(WIDTH/2)==(stall_mode==1 ? 2 : 6)) begin
                read_stall_started=1;
                read_stall=(stall_mode==1 ? 80 : 370);
            end
            if(read_stall>0) read_stall=read_stall-1;
            else s_ready=($urandom_range(0,3)!=0);
            if(w_valid && ((w_addr%STRIDE)>>3)==BEATS-1 && !final_stalled) begin
                final_stalled=1;final_stall=17;
            end
            if(final_stall>0) final_stall=final_stall-1;
            else w_ready=!s_valid&&($urandom_range(0,3)!=0);
            if(qhead<qtail) begin
                if(queue_delay[qhead%512]==0) begin
                    rsp_valid=1;rsp_data=queue_data[qhead%512];qhead=qhead+1;
                end else queue_delay[qhead%512]=queue_delay[qhead%512]-1;
            end
        end
    end

    integer frame_generation=0,allow_black=0;
    integer output_pixels=0,black_lines=0,good_lines=0;
    reg line_black=0;
    reg expected_de=0,expected_hs=0,expected_vs=0;
    integer expected_x=0,expected_y=0,expected_generation=0;
    reg [23:0] expected_rgb;
    always @(posedge pixel_clk) begin
        #0.1;
        if(pixel_rst_n) begin
            if(out_de!==expected_de || out_hsync!==expected_hs || out_vsync!==expected_vs)
                $fatal(1,"scanout control pipeline misalignment");
            if(expected_de) begin
                if(expected_x==0) begin
                    line_black=(rgb==0);
                    if(line_black) begin
                        black_lines=black_lines+1;
                        if(!allow_black) $fatal(1,"unexpected black line %0d",expected_y);
                    end else good_lines=good_lines+1;
                end
                expected_rgb=line_black ? 24'd0 :
                    expand565(color565(expected_generation,expected_y*WIDTH+expected_x));
                if(rgb!==expected_rgb)
                    $fatal(1,"scanout pixel mismatch y=%0d x=%0d got=%h expected=%h generation=%0d",
                        expected_y,expected_x,rgb,expected_rgb,expected_generation);
                output_pixels=output_pixels+1;
            end
        end
        expected_de=data_enable&&pixel_rst_n;
        expected_hs=hsync&&pixel_rst_n;expected_vs=vsync&&pixel_rst_n;
        expected_x=pixel_x;expected_y=pixel_y;expected_generation=frame_generation;
    end

    task drive_pixel(input integer x,input integer y,input bit de,input bit vb);
        begin
            @(negedge pixel_clk);
            pixel_x=x;pixel_y=y;data_enable=de;vblank_start=vb;
            hsync=(x>=WIDTH+4 && x<WIDTH+8);vsync=(y==HEIGHT);
        end
    endtask
    task run_frame(input integer mode,input integer black_allowed);
        integer x,y,old_pixels,old_black,old_good;
        begin
            stall_mode=mode;
            if(mode!=0) read_stall_started=0;
            allow_black=black_allowed;
            old_pixels=output_pixels;old_black=black_lines;old_good=good_lines;
            drive_pixel(0,HEIGHT,0,1);
            repeat(200) drive_pixel(1,HEIGHT,0,0);
            frame_generation=bank_generation[front_bank];
            if(!front_valid || frame_generation==0) $fatal(1,"no complete display frame");
            for(y=0;y<HEIGHT;y=y+1) begin
                for(x=0;x<WIDTH+16;x=x+1)
                    drive_pixel(x,y,x<WIDTH,0);
            end
            drive_pixel(0,HEIGHT,0,0);
            repeat(3) drive_pixel(1,HEIGHT,0,0);
            if(output_pixels-old_pixels!=WIDTH*HEIGHT)
                $fatal(1,"active pixel count mismatch");
            if(mode==1 && (black_lines==old_black || good_lines==old_good))
                $fatal(1,"late-line test did not exercise both underrun and recovery");
            if(fetch_fault) $fatal(1,"fetch fault in non-timeout scenarios");
        end
    endtask
    integer seed=86731;
    initial begin
        seed=$urandom(seed);
        bank_generation[0]=0;bank_generation[1]=0;
        repeat(8) @(negedge clk);
        rst_n=1;
        repeat(4) @(negedge pixel_clk);
        pixel_rst_n=1;
        wait(frame_pending);
        run_frame(0,0);
        run_frame(1,1);
        run_frame(0,0);
        run_frame(2,1);
        // Old request deliberately spans vblank; new epoch must reject old tags.
        run_frame(0,1);
        run_frame(0,0);
        if(underruns==0 || swaps<3 || black_lines==0 || good_lines<HEIGHT*3)
            $fatal(1,"incomplete feedback/swap/underrun coverage");
        $display("PASS tb_ddr_framebuffer: RGB565 packing, DDR backpressure, completed frame swaps, all pixels, black underrun lines and epoch recovery (%0d swaps, %0d black lines)",swaps,black_lines);
        $finish;
    end
    initial begin #2000000;$fatal(1,"framebuffer test timeout");end
endmodule
