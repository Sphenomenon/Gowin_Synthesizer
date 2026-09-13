`default_nettype none

// GW5AST-138: 50 MHz reference -> 25 MHz pixel / 125 MHz serializer.
// Reset asserts immediately; each destination releases on its own clock.
module video_clock (
    input  wire clk_50m,
    input  wire reset_n,
    output wire pixel_clk,
    output wire serial_clk,
    output wire pixel_reset_n,
    output wire video_source_reset_n
);
    wire pll_locked;
    wire clocks_ready = reset_n & pll_locked;
    reg [3:0] pixel_reset_pipe;
    reg [3:0] source_reset_pipe;

    video_pll_gw5a u_pll (
        .lock(pll_locked), .clkout0(pixel_clk),
        .clkout1(serial_clk), .clkin(clk_50m)
    );
    always @(posedge pixel_clk or negedge clocks_ready) begin
        if (!clocks_ready) pixel_reset_pipe <= 4'b0000;
        else pixel_reset_pipe <= {pixel_reset_pipe[2:0], 1'b1};
    end
    always @(posedge clk_50m or negedge clocks_ready) begin
        if (!clocks_ready) source_reset_pipe <= 4'b0000;
        else source_reset_pipe <= {source_reset_pipe[2:0], 1'b1};
    end
    assign pixel_reset_n = pixel_reset_pipe[3];
    assign video_source_reset_n = source_reset_pipe[3];
endmodule

`default_nettype wire
