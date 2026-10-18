`default_nettype none

// CTA 1920x1080p60: 148.5 MHz / (2200 * 1125) = 60 Hz, positive H/V sync.
// Coordinates include blanking. All markers refer to the current raster pixel;
// downstream memory/TMDS pipelines must delay RGB and timing by the same amount.
module video_timing_1080p (
    input wire pixel_clk,
    input wire reset_n,
    output wire [11:0] pixel_x,
    output wire [10:0] pixel_y,
    output wire data_enable,
    output wire hsync,
    output wire vsync,
    output wire frame_start,
    output wire line_start,
    output wire vblank_start
);
    reg [11:0] horizontal;
    reg [10:0] vertical;
    always @(posedge pixel_clk or negedge reset_n) begin
        if (!reset_n) begin
            horizontal <= 12'd0;
            vertical <= 11'd0;
        end else if (horizontal == 12'd2199) begin
            horizontal <= 12'd0;
            if (vertical == 11'd1124) vertical <= 11'd0;
            else vertical <= vertical + 1'b1;
        end else horizontal <= horizontal + 1'b1;
    end
    assign pixel_x = horizontal;
    assign pixel_y = vertical;
    assign data_enable = (horizontal < 12'd1920) && (vertical < 11'd1080);
    // Horizontal: active 1920, front 88, sync 44, back 148.
    // Vertical: active 1080, front 4, sync 5, back 36.
    assign hsync = (horizontal >= 12'd2008) && (horizontal < 12'd2052);
    assign vsync = (vertical >= 11'd1084) && (vertical < 11'd1089);
    assign frame_start = (horizontal == 0) && (vertical == 0);
    assign line_start = (horizontal == 0);
    assign vblank_start = (horizontal == 0) && (vertical == 11'd1080);
endmodule

`default_nettype wire
