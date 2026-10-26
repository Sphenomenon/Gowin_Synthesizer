`default_nettype none
module workstation_video_timing_720p60 (
    input wire pixel_clk, reset_n,
    output wire [11:0] pixel_x,
    output wire [10:0] pixel_y,
    output wire data_enable, hsync, vsync,
    output wire frame_start, line_start, vblank_start
);
    reg [11:0] horizontal;
    reg [10:0] vertical;
    reg vblank_q;
    always @(posedge pixel_clk or negedge reset_n) begin
        if (!reset_n) begin
            horizontal <= 0;
            vertical <= 0;
            vblank_q <= 0;
        end else begin
            vblank_q <= horizontal == 12'd1649 && vertical == 11'd719;
            if (horizontal == 12'd1649) begin
                horizontal <= 0;
                vertical <= vertical == 11'd749 ? 11'd0 : vertical + 1'b1;
            end else horizontal <= horizontal + 1'b1;
        end
    end
    assign pixel_x = horizontal;
    assign pixel_y = vertical;
    assign data_enable = horizontal < 12'd1280 && vertical < 11'd720;
    assign hsync = horizontal >= 12'd1390 && horizontal < 12'd1430;
    assign vsync = vertical >= 11'd725 && vertical < 11'd730;
    assign frame_start = horizontal == 0 && vertical == 0;
    assign line_start = horizontal == 0;
    assign vblank_start = vblank_q;
endmodule
`default_nettype wire
