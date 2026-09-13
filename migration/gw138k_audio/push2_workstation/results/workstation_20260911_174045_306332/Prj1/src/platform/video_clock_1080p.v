`default_nettype none

// CTA 1920x1080p60 clock source: exact nominal 148.5 MHz pixel / 742.5 MHz FCLK.
// SIMULATION selects a test-only model; the default elaborates real Gowin PLLs.
module video_clock_1080p #(
    parameter SIMULATION = 0
) (
    input wire clk_50m,
    input wire reset_n,
    output wire pixel_clk,
    output wire serial_clk,
    output wire serializer_reset_n,
    output wire serializer_reset,
    output wire pixel_reset_n,
    output wire video_source_reset_n,
    output wire pll_locked
);
    generate
        if (SIMULATION) begin : g_simulation
            video_clock_1080p_model u_model (
                .clk_50m(clk_50m), .reset_n(reset_n),
                .pixel_clk(pixel_clk), .serial_clk(serial_clk),
                .serializer_reset_n(serializer_reset_n), .serializer_reset(serializer_reset), .locked(pll_locked)
            );
        end else begin : g_hardware
            video_pll_1080p_gw5a u_pll (
                .clk_50m(clk_50m), .reset_n(reset_n),
                .pixel_clk(pixel_clk), .serial_clk(serial_clk),
                .serializer_reset_n(serializer_reset_n), .serializer_reset(serializer_reset), .locked(pll_locked)
            );
        end
    endgenerate
    wire clocks_ready = reset_n & pll_locked;
    reg [3:0] pixel_reset_pipe;
    reg [3:0] source_reset_pipe;
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
