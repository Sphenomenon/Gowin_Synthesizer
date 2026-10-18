`default_nettype none
// Two ping-pong scan lines. DDR is read in BL8 beats; RGB565 expands at scanout.
// A line is overwritten only after its final active pixel. Tagged completion
// prevents stale/late data becoming a different line or a different frame.
module video_ddr_scanout #(
    parameter integer WIDTH = 1920, HEIGHT = 1080,
    parameter integer EXPLICIT_BASE = 0,
    parameter integer GRAPH_FIRST_LINE=160,GRAPH_END_LINE=832,
    parameter integer FRAME_STRIDE_WORDS = 1048576,
    parameter integer TIMEOUT_CYCLES = 100000
) (
    input wire clk, rst_n,
    input wire enabled,
    input wire new_frame_pending,
    input wire [28:0] new_frame_base,
    input wire new_composite,
    input wire [28:0] new_analysis_base,
    output reg frame_swap,
    output reg front_bank,
    output reg front_valid,
    output wire req_valid,
    input wire req_ready,
    output wire [28:0] req_addr,
    input wire rsp_valid,
    input wire [255:0] rsp_data,
    output reg fetch_fault,
    output wire [31:0] underruns,
    input wire pixel_clk, pixel_rst_n,
    input wire [11:0] pixel_x,
    input wire [10:0] pixel_y,
    input wire data_enable, hsync, vsync, vblank_start,
    output reg [23:0] rgb,
    output reg out_de, out_hsync, out_vsync
);
    localparam integer LINE_BEATS = WIDTH/16;
    localparam integer LINE_WORDS = WIDTH/2;
    localparam [28:0] LINE_WORDS_ADDR = WIDTH/2;
    localparam [28:0] FRAME_STRIDE_ADDR = FRAME_STRIDE_WORDS;
    // 128 beats/line accommodates 1920 pixels, plus a separate second bank.
    reg [255:0] line_memory [0:255];
    reg request_toggle, ack_toggle;
    reg [19:0] held_request; // {restart, epoch[7:0], line[10:0]}
    reg ack_meta, ack_sync;
    reg [7:0] pixel_epoch;
    reg [31:0] under_count, under_gray;
    reg line_good;
    reg done0_toggle, done1_toggle;
    reg [18:0] done0_tag, done1_tag;
    reg done0_meta, done0_sync, done0_settled, done0_seen;
    reg done1_meta, done1_sync, done1_settled, done1_seen;
    reg [18:0] tag0, tag1;
    reg valid0, valid1, display_started;
    wire current_good = pixel_y[0] ? (valid1 && tag1 == {pixel_epoch,pixel_y}) :
                                              (valid0 && tag0 == {pixel_epoch,pixel_y});
    reg [255:0] scan_word;
    reg [3:0] scan_lane;
    reg scan_de, scan_hs, scan_vs, scan_good;
    wire [15:0] scan_rgb565 = scan_word[scan_lane*16 +: 16];
    // The source holds each request until the complete DDR fetch is ACKed.
    always @(posedge pixel_clk or negedge pixel_rst_n) begin
        if (!pixel_rst_n) begin
            request_toggle<=0; held_request<=0; ack_meta<=0; ack_sync<=0;
            pixel_epoch<=0; under_count<=0; under_gray<=0; line_good<=0;
            done0_meta<=0; done0_sync<=0; done0_settled<=0; done0_seen<=0;
            done1_meta<=0; done1_sync<=0; done1_settled<=0; done1_seen<=0;
            tag0<=0;tag1<=0;valid0<=0;valid1<=0;display_started<=0;
            scan_lane<=0;scan_de<=0;scan_hs<=0;scan_vs<=0;scan_good<=0;
            rgb<=0;out_de<=0;out_hsync<=0;out_vsync<=0;
        end else begin
            ack_meta<=ack_toggle; ack_sync<=ack_meta;
            // Encode the registered count one cycle later. Keep the increment
            // carry chain separate from Gray conversion at 148.5 MHz.
            under_gray<=(under_count>>1)^under_count;
            done0_meta<=done0_toggle;done0_sync<=done0_meta;done0_settled<=done0_sync;
            done1_meta<=done1_toggle;done1_sync<=done1_meta;done1_settled<=done1_sync;
            if(done0_settled!=done0_seen) begin
                tag0<=done0_tag; valid0<=1; done0_seen<=done0_settled;
                display_started<=1;
            end
            if(done1_settled!=done1_seen) begin
                tag1<=done1_tag; valid1<=1; done1_seen<=done1_settled;
                display_started<=1;
            end
            if(vblank_start) begin
                // Every frame must earn fresh line-valid tags. Otherwise a
                // stopped fetcher could replay old rows when the epoch wraps.
                valid0<=0;valid1<=0;
                pixel_epoch<=pixel_epoch+1'b1;
                if(ack_sync==request_toggle) begin
                    held_request<={1'b1,(pixel_epoch+8'd1),11'd0};
                    request_toggle<=!request_toggle;
                end
            end else if(pixel_x==WIDTH-1 && pixel_y<HEIGHT-2 && ack_sync==request_toggle) begin
                held_request<={1'b0,pixel_epoch,(pixel_y+11'd2)};
                request_toggle<=!request_toggle;
            end
            if(pixel_x==0 && pixel_y<HEIGHT) begin
                line_good<=current_good;
                // Do not count the black startup before a first tagged frame.
                if(!current_good && display_started) begin
                    under_count<=under_count+1'b1;
                end
            end
            scan_lane<=pixel_x[3:0];scan_de<=data_enable;
            scan_hs<=hsync;scan_vs<=vsync;
            scan_good<=pixel_x==0 ? current_good : line_good;
            rgb<=scan_de && scan_good ?
                {scan_rgb565[15:11],scan_rgb565[15:13],scan_rgb565[10:5],scan_rgb565[10:9],scan_rgb565[4:0],scan_rgb565[4:2]} : 24'd0;
            out_de<=scan_de;out_hsync<=scan_hs;out_vsync<=scan_vs;
        end
    end
    // Separate clocked ports infer a true dual-clock block RAM (no reset on RAM).
    always @(posedge pixel_clk)
        scan_word<=line_memory[{pixel_y[0],pixel_x[10:4]}];

    reg request_meta,request_sync,request_settled;
    // Capture the complete held mailbox before decoding or address arithmetic.
    // This keeps the CDC endpoint explicit even when synthesis infers a DSP.
    reg [19:0] request_word /* synthesis syn_preserve=1 syn_keep=1 */;
    reg request_pending;
    reg [31:0] under_meta,under_sync;
    function [31:0] gray_binary;
        input [31:0] g;
        integer j;
        begin gray_binary[31]=g[31];for(j=30;j>=0;j=j-1)gray_binary[j]=gray_binary[j+1]^g[j];end
    endfunction
    assign underruns=gray_binary(under_sync);
    reg active, second_line;
    reg [10:0] fetch_line;
    reg [7:0] fetch_epoch;
    reg [8:0] issued,received;
    reg [28:0] line_base,front_base,analysis_base;
    reg composite_active;
    // In composite mode the UI owns the frame, while the RTL analysis page owns
    // the waveform/spectrum/image band and the bottom effect-chain band.
    wire graph_line=composite_active && ((request_word[10:0]>=GRAPH_FIRST_LINE && request_word[10:0]<GRAPH_END_LINE) ||
                                         (request_word[10:0]>=11'd832 && request_word[10:0]<11'd968));
    wire [28:0] row_base=graph_line?analysis_base:front_base;
    reg [31:0] timer;
    assign req_valid=active && !fetch_fault && issued<LINE_BEATS;
    assign req_addr=line_base+{17'd0,issued,3'b000};
    always @(posedge clk) begin
        if(active && rsp_valid && received<LINE_BEATS)
            line_memory[{fetch_line[0],received[6:0]}]<=rsp_data;
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            request_meta<=0;request_sync<=0;request_settled<=0;ack_toggle<=0;
            request_word<=0;request_pending<=0;
            under_meta<=0;under_sync<=0;active<=0;second_line<=0;
            fetch_line<=0;fetch_epoch<=0;issued<=0;received<=0;line_base<=0;front_base<=0;analysis_base<=0;composite_active<=0;timer<=0;
            done0_toggle<=0;done1_toggle<=0;done0_tag<=0;done1_tag<=0;
            frame_swap<=0;front_bank<=0;front_valid<=0;fetch_fault<=0;
        end else begin
            request_meta<=request_toggle;request_sync<=request_meta;request_settled<=request_sync;
            under_meta<=under_gray;under_sync<=under_meta;
            frame_swap<=0;
            if(!active && !request_pending && request_settled!=ack_toggle) begin
                request_word<=held_request;
                request_pending<=1;
            end
            if(request_pending) begin
                request_pending<=0;
                if(!enabled || fetch_fault || (!front_valid && !new_frame_pending))
                    ack_toggle<=request_settled;
                else begin
                    fetch_line<=request_word[10:0]; fetch_epoch<=request_word[18:11];
                    second_line<=request_word[19];issued<=0;received<=0;timer<=0;
                    if(request_word[19] && new_frame_pending) begin
                        front_bank<=!front_bank;front_valid<=1;frame_swap<=1;
                        line_base<=EXPLICIT_BASE ? new_frame_base : (front_bank ? 0 : FRAME_STRIDE_WORDS);
                        if(EXPLICIT_BASE)begin
                            front_base<=new_frame_base;analysis_base<=new_analysis_base;composite_active<=new_composite;
                        end
                        active<=1;
                    end else if(front_valid) begin
                        line_base<=(EXPLICIT_BASE ? row_base : (front_bank ? FRAME_STRIDE_ADDR : 29'd0))+request_word[10:0]*LINE_WORDS_ADDR;
                        active<=1;
                    end else ack_toggle<=request_settled;
                end
            end
            if(active) begin
                if(req_valid && req_ready) issued<=issued+1'b1;
                timer<=timer+1'b1;
                if(timer==TIMEOUT_CYCLES-1 && !rsp_valid) begin
                    fetch_fault<=1;active<=0;ack_toggle<=request_settled;
                end
                if(rsp_valid) begin
                    received<=received+1'b1;timer<=0;
                    if(received==LINE_BEATS-1) begin
                        if(fetch_line[0]) begin done1_tag<={fetch_epoch,fetch_line};done1_toggle<=!done1_toggle;end
                        else begin done0_tag<={fetch_epoch,fetch_line};done0_toggle<=!done0_toggle;end
                        if(second_line) begin
                            second_line<=0;fetch_line<=1;line_base<=line_base+LINE_WORDS_ADDR;
                            issued<=0;received<=0;
                        end else begin active<=0;ack_toggle<=request_settled;end
                    end
                end
            end
        end
    end
endmodule
`default_nettype wire
