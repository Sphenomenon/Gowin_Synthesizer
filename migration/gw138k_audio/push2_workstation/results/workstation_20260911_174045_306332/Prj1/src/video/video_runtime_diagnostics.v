`default_nettype none

// Observation-only telemetry. Byte 0 is the least significant byte; the
// command layer can freeze this entire 50 MHz record before reading pages.
// WINDOW_CYCLES=500000 gives a 10 ms window at the fixed 50 MHz reference.
// Reset contract: pixel_reset_n and ui_reset_n include global reset_n, assert
// asynchronously, and release synchronously in pixel_clk and ui_clk. Do not
// recombine raw reset_n into their counter resets: that reintroduces a 50 MHz
// recovery/removal path at destination registers after the domain synchronizer.
module video_runtime_diagnostics #(
    parameter integer WINDOW_CYCLES = 500000
) (
    input wire clk_50m, reset_n,
    input wire pixel_clk, pixel_reset_n, vblank_start,
    input wire ui_clk, ui_reset_n,
    input wire [31:0] rendered_frames, underruns,
    input wire hdmi_hpd, video_locked, scanout_reset_n, serializer_reset,
    output reg [127:0] diagnostics
);
    localparam integer WINDOW_WIDTH = (WINDOW_CYCLES < 2) ? 1 : $clog2(WINDOW_CYCLES);
    localparam [WINDOW_WIDTH-1:0] WINDOW_LAST = WINDOW_CYCLES - 1;

    // Count the physical pixel clock independently of the video logic reset.
    // A stopped clock therefore produces a valid zero-frequency window while
    // reset/lock flags distinguish an intentional video restart from a stall.
    (* ASYNC_REG = "TRUE" *) reg [1:0] pixel_global_reset_pipe;
    always @(posedge pixel_clk or negedge reset_n) begin
        if (!reset_n) pixel_global_reset_pipe <= 0;
        else pixel_global_reset_pipe <= {pixel_global_reset_pipe[0], 1'b1};
    end
    wire pixel_counter_reset_n = pixel_global_reset_pipe[1];
    reg [9:0] pixel_cycle_low;
    reg [15:0] pixel_block_count;
    (* syn_preserve=1, syn_keep=1 *) reg [15:0] pixel_block_gray;
    always @(posedge pixel_clk or negedge pixel_counter_reset_n) begin
        if (!pixel_counter_reset_n) begin
            pixel_cycle_low <= 0;
            pixel_block_count <= 0;
            pixel_block_gray <= 0;
        end else begin
            pixel_cycle_low <= pixel_cycle_low + 1'b1;
            if (&pixel_cycle_low) pixel_block_count <= pixel_block_count + 1'b1;
            // Keep increment and Gray conversion in separate pixel cycles.
            pixel_block_gray <= pixel_block_count ^ (pixel_block_count >> 1);
        end
    end

    wire pixel_frame_reset_n = pixel_reset_n;
    reg [31:0] pixel_frame_count;
    (* syn_preserve=1, syn_keep=1 *) reg [31:0] pixel_frame_gray;
    always @(posedge pixel_clk or negedge pixel_frame_reset_n) begin
        if (!pixel_frame_reset_n) begin
            pixel_frame_count <= 0;
            pixel_frame_gray <= 0;
        end else begin
            // Two 16-bit increments avoid a 32-bit carry path at 148.5 MHz.
            if (vblank_start) begin
                pixel_frame_count[15:0] <= pixel_frame_count[15:0] + 1'b1;
                if (&pixel_frame_count[15:0])
                    pixel_frame_count[31:16] <= pixel_frame_count[31:16] + 1'b1;
            end
            pixel_frame_gray <= pixel_frame_count ^ (pixel_frame_count >> 1);
        end
    end

    // Inputs are counters in the memory UI domain. Each counter advances by
    // at most one per UI cycle and resets with ui_reset_n; arbitrary word
    // updates must instead use a handshake mailbox, not this Gray crossing.
    wire memory_counter_reset_n = ui_reset_n;
    reg [31:0] memory_rendered_sample, memory_underrun_sample;
    (* syn_preserve=1, syn_keep=1 *) reg [31:0] memory_rendered_gray;
    (* syn_preserve=1, syn_keep=1 *) reg [31:0] memory_underrun_gray;
    always @(posedge ui_clk or negedge memory_counter_reset_n) begin
        if (!memory_counter_reset_n) begin
            memory_rendered_sample <= 0;
            memory_underrun_sample <= 0;
            memory_rendered_gray <= 0;
            memory_underrun_gray <= 0;
        end else begin
            memory_rendered_sample <= rendered_frames;
            memory_underrun_sample <= underruns;
            memory_rendered_gray <= memory_rendered_sample ^ (memory_rendered_sample >> 1);
            memory_underrun_gray <= memory_underrun_sample ^ (memory_underrun_sample >> 1);
        end
    end

    (* ASYNC_REG = "TRUE", syn_preserve=1 *) reg [15:0] pixel_block_meta, pixel_block_sync;
    (* ASYNC_REG = "TRUE", syn_preserve=1 *) reg [31:0] pixel_frame_meta, pixel_frame_sync;
    (* ASYNC_REG = "TRUE", syn_preserve=1 *) reg [31:0] memory_rendered_meta, memory_rendered_sync;
    (* ASYNC_REG = "TRUE", syn_preserve=1 *) reg [31:0] memory_underrun_meta, memory_underrun_sync;
    (* ASYNC_REG = "TRUE", syn_preserve=1 *) reg [4:0] flags_meta, flags_sync;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            pixel_block_meta <= 0; pixel_block_sync <= 0;
            pixel_frame_meta <= 0; pixel_frame_sync <= 0;
            memory_rendered_meta <= 0; memory_rendered_sync <= 0;
            memory_underrun_meta <= 0; memory_underrun_sync <= 0;
            flags_meta <= 0; flags_sync <= 0;
        end else begin
            pixel_block_meta <= pixel_block_gray; pixel_block_sync <= pixel_block_meta;
            pixel_frame_meta <= pixel_frame_gray; pixel_frame_sync <= pixel_frame_meta;
            memory_rendered_meta <= memory_rendered_gray; memory_rendered_sync <= memory_rendered_meta;
            memory_underrun_meta <= memory_underrun_gray; memory_underrun_sync <= memory_underrun_meta;
            flags_meta <= {serializer_reset, scanout_reset_n, pixel_reset_n, video_locked, hdmi_hpd};
            flags_sync <= flags_meta;
        end
    end

    // Mask reset-induced multi-bit Gray changes, even if the affected source
    // clock has stopped. Deassertion waits four reference cycles for the CDC
    // pipeline to settle. A short reset/lock pulse also invalidates the window.
    wire pixel_ready_async_n = reset_n & pixel_reset_n & video_locked;
    (* ASYNC_REG = "TRUE" *) reg [3:0] pixel_ready_pipe;
    (* ASYNC_REG = "TRUE" *) reg [3:0] memory_ready_pipe;
    always @(posedge clk_50m or negedge pixel_ready_async_n) begin
        if (!pixel_ready_async_n) pixel_ready_pipe <= 0;
        else pixel_ready_pipe <= {pixel_ready_pipe[2:0], 1'b1};
    end
    always @(posedge clk_50m or negedge memory_counter_reset_n) begin
        if (!memory_counter_reset_n) memory_ready_pipe <= 0;
        else memory_ready_pipe <= {memory_ready_pipe[2:0], 1'b1};
    end

    function [31:0] gray_to_binary;
        input [31:0] gray;
        integer bit_index;
        begin
            gray_to_binary[31] = gray[31];
            for (bit_index=30; bit_index>=0; bit_index=bit_index-1)
                gray_to_binary[bit_index] = gray_to_binary[bit_index+1] ^ gray[bit_index];
        end
    endfunction
    wire [31:0] blocks_decoded = gray_to_binary({16'd0, pixel_block_sync});
    reg [WINDOW_WIDTH-1:0] window_count;
    reg [15:0] block_baseline, measured_blocks;
    reg measurement_valid;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            window_count <= 0;
            block_baseline <= 0;
            measured_blocks <= 0;
            measurement_valid <= 0;
        end else if (!pixel_ready_pipe[3]) begin
            // Continuously rebase while unavailable. Do not expose a partial
            // first/recovery window or subtract across a reset discontinuity.
            window_count <= 0;
            block_baseline <= blocks_decoded[15:0];
            measured_blocks <= 0;
            measurement_valid <= 0;
        end else if (window_count == WINDOW_LAST) begin
            window_count <= 0;
            measured_blocks <= blocks_decoded[15:0] - block_baseline;
            block_baseline <= blocks_decoded[15:0];
            measurement_valid <= 1;
        end else window_count <= window_count + 1'b1;
    end

    // Byte 1: HPD, PLL lock, pixel reset released, scan reset released,
    // serializer reset asserted, complete measurement available, two zeros.
    // Bytes 2..3: 1024-clock blocks/window; 4..7: vblank count; 8..11:
    // completed render count; 12..15: underrun count. All words little-endian.
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) diagnostics <= 128'd1;
        else begin
            diagnostics[7:0] <= 8'd1;
            diagnostics[15:8] <= {2'd0, measurement_valid & pixel_ready_pipe[3], flags_sync};
            diagnostics[31:16] <= pixel_ready_pipe[3] ? measured_blocks : 16'd0;
            diagnostics[63:32] <= pixel_ready_pipe[3] ? gray_to_binary(pixel_frame_sync) : 32'd0;
            diagnostics[95:64] <= memory_ready_pipe[3] ? gray_to_binary(memory_rendered_sync) : 32'd0;
            diagnostics[127:96] <= memory_ready_pipe[3] ? gray_to_binary(memory_underrun_sync) : 32'd0;
        end
    end
endmodule

`default_nettype wire
