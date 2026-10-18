`default_nettype none

// VGA-compatible raster, negative sync polarity. At 25 MHz: 59.524 Hz.
module video_timing_640x480 (
    input  wire pixel_clk,
    input  wire reset_n,
    output wire [9:0] pixel_x,
    output wire [9:0] pixel_y,
    output wire data_enable,
    output wire hsync,
    output wire vsync,
    output wire frame_start
);
    reg [9:0] horizontal;
    reg [9:0] vertical;
    always @(posedge pixel_clk or negedge reset_n) begin
        if (!reset_n) begin
            horizontal <= 10'd0;
            vertical <= 10'd0;
        end else if (horizontal == 10'd799) begin
            horizontal <= 10'd0;
            if (vertical == 10'd524) vertical <= 10'd0;
            else vertical <= vertical + 1'b1;
        end else horizontal <= horizontal + 1'b1;
    end
    assign pixel_x = horizontal;
    assign pixel_y = vertical;
    assign data_enable = (horizontal < 640) && (vertical < 480);
    // Horizontal: active 640, front 16, sync 96, back 48.
    // Vertical: active 480, front 10, sync 2, back 33.
    assign hsync = !((horizontal >= 656) && (horizontal < 752));
    assign vsync = !((vertical >= 490) && (vertical < 492));
    assign frame_start = (horizontal == 0) && (vertical == 0);
endmodule

`default_nettype wire
