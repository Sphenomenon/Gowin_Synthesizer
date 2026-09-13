`timescale 1ns/1fs
`default_nettype none

// Test-only ideal clocks. Does not model analog PLL lock/jitter, placement, or
// missing reference clocks, and cannot establish board-level HDMI operation.
module video_clock_1080p_model (
    input wire clk_50m,
    input wire reset_n,
    output wire pixel_clk,
    output wire serial_clk,
    output wire serializer_reset_n,
    output wire serializer_reset,
    output wire locked
);
    reg pixel_osc = 0;
    reg serial_osc = 0;
    integer half_pixel_edges = 0;
    integer stable_count = 0;
    reg qualified_lock = 0;
    reg output_gate = 0;
    video_serializer_startup u_startup (
        .clk(clk_50m), .reset_n(reset_n), .qualified_lock(qualified_lock),
        .serializer_reset_n(serializer_reset_n), .serializer_reset(serializer_reset), .clock_enable(locked)
    );
    always #(1000.0 / 742.5 / 2.0) serial_osc = ~serial_osc;
    always @(negedge serial_osc or negedge locked)
        if (!locked) output_gate <= 0; else output_gate <= 1;
    // One common oscillator guarantees an exact 5:1 relation without drift.
    always @(serial_clk or negedge serializer_reset_n) begin
        if (!serializer_reset_n) begin pixel_osc = 0; half_pixel_edges = 0; end
        else if (half_pixel_edges == 4) begin
            half_pixel_edges = 0;
            pixel_osc = ~pixel_osc;
        end else half_pixel_edges = half_pixel_edges + 1;
    end
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin stable_count <= 0; qualified_lock <= 0; end
        else if (!qualified_lock) begin
            // Two 2 ms qualification intervals; startup transients are omitted.
            if (stable_count == 199999) qualified_lock <= 1;
            else stable_count <= stable_count + 1;
        end
    end
    assign pixel_clk = serializer_reset_n ? pixel_osc : 1'b0;
    assign serial_clk = output_gate ? serial_osc : 1'b0;
endmodule

`default_nettype wire
