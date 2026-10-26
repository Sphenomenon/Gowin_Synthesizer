`timescale 1ns/1ps
`include "src/memory/ddr_address_map.vh"
module tb_video_frame_publication;
    localparam integer WIDTH=64,HEIGHT=8,FRAME_BEATS=WIDTH*HEIGHT/16;
    reg clk=0,reset_n=0;
    always #5 clk=~clk;
    wire frame_pending,frame_available,analysis_bank,analysis_commit,renderer_start,pixel_ready;
    wire request_valid,renderer_ready;
    wire [28:0] request_address,selected_base;
    wire [255:0] request_data;
    wire [31:0] rendered_frames;
    reg frame_swap=0;
    reg pixel_valid=0,renderer_done=0;
    reg [63:0] pixel_data=0;
    integer cycle=0,generation=0,position=0,write_count=0;
    integer last_stall=0,meta_stall=0,late_commit_attempts=0,commit_count=0;
    integer completed_generation[0:1];
    reg visible_valid=0,visible_bank=0,write_bank=0;
    wire metadata_request=request_address==`PRJ1_DDR_DISPLAY_DATA_APP_BASE;
    reg request_ready=0;
    wire commit_request=(frame_pending && cycle%41==0) ||
                        (request_valid && request_ready && metadata_request);
    assign renderer_ready=!pixel_valid;
    ddr_frame_writer writer (
        .clk(clk),.rst_n(reset_n),.enabled(1'b1),.front_bank(analysis_bank),
        .frame_swap(analysis_commit),.renderer_ready(renderer_ready && !request_valid),
        .renderer_done(renderer_done),.renderer_start(renderer_start),.pixel_valid(pixel_valid),
        .pixel_ready(pixel_ready),.pixel_data(pixel_data),.display_meta(256'h1234),
        .req_valid(request_valid),.req_ready(request_ready),.req_addr(request_address),
        .req_wdata(request_data),.frame_pending(frame_pending),.rendered_frames(rendered_frames));
    gw138k_view_select view_select (
        .clk(clk),.reset_n(reset_n),.frame_swap(frame_swap),.analysis_pending(frame_pending),
        .ui_pending(1'b0),.ui_visible(1'b0),.ui_next_visible(1'b0),.ui_front_base(29'd0),.ui_next_base(29'd0),
        .analysis_bank(analysis_bank),.analysis_commit(analysis_commit),.frame_available(frame_available),
        .selected_base(selected_base));
    function automatic [15:0] color565(input integer frame,input integer offset);
        color565={5'b10000 | frame[4:0],offset[5:0],offset[10:6]^frame[4:0]};
    endfunction
    function automatic [23:0] expand565(input [15:0] color);
        expand565={color[15:11],color[15:13],color[10:5],color[10:9],color[4:0],color[4:2]};
    endfunction
    function automatic [63:0] pixel_pair(input integer frame,input integer offset);
        pixel_pair={8'd0,expand565(color565(frame,offset+1)),8'd0,expand565(color565(frame,offset))};
    endfunction
    reg previous_held=0;
    reg [284:0] previous_request=0;
    always @(negedge clk) begin
        if(reset_n) begin
            cycle=cycle+1;
            request_ready=cycle%5!=0 && (metadata_request ? meta_stall>=40 :
                                                (write_count!=FRAME_BEATS-1 || last_stall>=40));
        end
    end
    always @(posedge clk) begin
        if(reset_n) begin
            renderer_done<=0;
            if(renderer_start) begin
                generation=generation+1;position=0;write_count=0;last_stall=0;meta_stall=0;
                pixel_valid<=1;pixel_data<=pixel_pair(generation,0);
            end else if(pixel_valid && pixel_ready) begin
                if(position==WIDTH*HEIGHT-2) begin pixel_valid<=0;renderer_done<=1;end
                else begin position=position+2;pixel_data<=pixel_pair(generation,position);end
            end
            if(previous_held && (!request_valid || {request_address,request_data}!==previous_request))
                $fatal(1,"writer request changed while stalled");
            previous_held=request_valid && !request_ready;
            previous_request={request_address,request_data};
            if(request_valid && !request_ready) begin
                if(metadata_request) meta_stall=meta_stall+1;
                else if(write_count==FRAME_BEATS-1) last_stall=last_stall+1;
            end
            if(request_valid && request_ready) begin
                if(metadata_request) begin
                    if(write_count!=FRAME_BEATS) $fatal(1,"metadata preceded complete pixels");
                    if(last_stall<40 || meta_stall<40) $fatal(1,"final write stalls not covered");
                    completed_generation[write_bank]=generation;
                    if(frame_pending) $fatal(1,"frame pending before metadata acceptance");
                    if(frame_available) late_commit_attempts=late_commit_attempts+1;
                end else begin
                    write_bank=request_address>=`PRJ1_DDR_VIDEO_FRAME1_APP_BASE;
                    if(visible_valid && write_bank==visible_bank) $fatal(1,"writer modified visible bank");
                    if((request_address & 29'h000fffff)!=write_count*8) $fatal(1,"pixel write order");
                    for(integer lane=0;lane<16;lane=lane+1)
                        if(request_data[lane*16+:16]!==color565(generation,write_count*16+lane))
                            $fatal(1,"RGB565 packing mismatch");
                    write_count=write_count+1;
                end
            end
            frame_swap<=commit_request && frame_available;
            if(commit_request && frame_available) begin
                visible_bank=selected_base==`PRJ1_DDR_VIDEO_FRAME1_APP_BASE;
                if(completed_generation[visible_bank]==0) $fatal(1,"selected incomplete frame");
                visible_valid=1;
            end
            if(analysis_commit) begin
                if(!frame_pending) $fatal(1,"acknowledgement stole later pending page");
                commit_count=commit_count+1;
            end
            if(commit_count==8) begin
                if(late_commit_attempts<7 || rendered_frames<8) $fatal(1,"publication coverage");
                $display("PASS mode=0 frame_publication commits=%0d late_pending_races=%0d rendered=%0d",commit_count,late_commit_attempts,rendered_frames);
                $finish;
            end
        end
    end
    initial begin
        completed_generation[0]=0;completed_generation[1]=0;
        repeat(8) @(negedge clk);
        reset_n=1;
    end
    initial begin #1000000;$fatal(1,"publication test timeout");end
endmodule
