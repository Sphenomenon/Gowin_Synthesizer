`include "src/memory/ddr_address_map.vh"
`default_nettype none
// Pack two RGB888 pixels per clock into a native BL8 beat of 16 RGB565 pixels.
module ddr_frame_writer #(
    parameter integer FRAME_STRIDE_WORDS=`PRJ1_DDR_VIDEO_FRAME_APP_WORDS
) (
    input wire clk,rst_n,enabled,front_bank,frame_swap,
    input wire renderer_ready,renderer_done,
    output reg renderer_start,
    input wire pixel_valid,
    output wire pixel_ready,
    input wire [63:0] pixel_data,
    input wire [255:0] display_meta,
    output wire req_valid,
    input wire req_ready,
    output reg [28:0] req_addr,
    output wire [255:0] req_wdata,
    output reg frame_pending,
    output reg [31:0] rendered_frames
);
    reg [255:0] packed_pixels;
    reg [2:0] pack_index;
    reg full,rendering,finished,meta_pending;
    wire [15:0] p0={pixel_data[23:19],pixel_data[15:10],pixel_data[7:3]};
    wire [15:0] p1={pixel_data[55:51],pixel_data[47:42],pixel_data[39:35]};
    assign pixel_ready=enabled && rendering && !full;
    assign req_valid=(full || meta_pending) && enabled;
    assign req_wdata=full ? packed_pixels : display_meta;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            packed_pixels<=0;pack_index<=0;full<=0;rendering<=0;finished<=0;
            req_addr<=0;frame_pending<=0;renderer_start<=0;rendered_frames<=0;meta_pending<=0;
        end else begin
            renderer_start<=0;
            if(frame_swap) frame_pending<=0;
            if(enabled && !rendering && !frame_pending && renderer_ready && !renderer_start) begin
                renderer_start<=1;rendering<=1;finished<=0;
                req_addr<=front_bank ? 0 : FRAME_STRIDE_WORDS;
                pack_index<=0;
            end
            if(pixel_valid && pixel_ready) begin
                packed_pixels[pack_index*32 +: 32]<={p1,p0};
                pack_index<=pack_index+1'b1;
                if(pack_index==7) full<=1;
            end
            if(req_valid && req_ready) begin
                if(full) begin full<=0; req_addr<=req_addr+29'd8; end
                else begin meta_pending<=0; frame_pending<=1; rendered_frames<=rendered_frames+1'b1; end
            end
            if(renderer_done) finished<=1;
            // Publishing requires both the renderer and final DDR write handshake.
            if(rendering && finished && !full && pack_index==0 && !meta_pending) begin
                rendering<=0; meta_pending<=1; req_addr<=`PRJ1_DDR_DISPLAY_DATA_APP_BASE;
            end
        end
    end
endmodule
`default_nettype wire
