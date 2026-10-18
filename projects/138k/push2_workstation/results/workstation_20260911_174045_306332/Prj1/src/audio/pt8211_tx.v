// PT8211: two 16-bit right-justified slots. NOT Philips one-bit-delayed I2S.
// DIN/WS change on BCK falling edges and are stable at BCK rising edges.
// PT8211 low-WS is RIGHT, high-WS is LEFT; optional mono compatibility.
// 50 MHz / (2 * 16 * 32) = 48,828.125 samples/s, BCK = 1.5625 MHz.
module pt8211_tx #(
    parameter integer BCK_HALF_CYCLES = 16,
    parameter integer STEREO_ENABLE = 0
) (
    input wire clk,
    input wire reset_n,
    input wire signed [31:0] sample_data,
    input wire signed [31:0] sample_right,
    input wire sample_valid,
    output reg sample_tick,
    output reg hp_bck,
    output reg hp_ws,
    output reg hp_din,
    output wire pa_en,
    output reg [31:0] underrun_count,
    output reg [31:0] frame_count,
    input wire [23:0] sample_revision,
    input wire [31:0] sample_nonzero_voices,
    output wire trace_dac_done,
    output wire [23:0] trace_dac_revision,
    output wire [31:0] trace_dac_nonzero_voices,
    input wire [31:0] sample_trigger_reference,
    output reg [31:0] frame_trigger_reference
);
    reg [31:0] divider;
    reg [4:0] bit_index;
    reg signed [15:0] pending_sample, frame_sample;
    reg signed [15:0] pending_right, frame_right;
    reg pending_valid;
    reg [23:0] pending_revision, frame_revision;
    reg [31:0] pending_nonzero_voices, frame_nonzero_voices;
    reg frame_tag_valid;
    reg [31:0] pending_trigger_reference;
    reg [9:0] warmup;

    // Round Q1.31 to signed PCM16, nearest, ties away from zero; saturate.
    function [15:0] quantize16;
        input signed [31:0] value;
        reg signed [32:0] rounded;
        reg signed [32:0] scaled;
        begin
            rounded = {value[31],value} + (value[31] ? 33'sd32767 : 33'sd32768);
            scaled = rounded >>> 16;
            if (scaled > 32767) quantize16 = 16'h7fff;
            else if (scaled < -32768) quantize16 = 16'h8000;
            else quantize16 = scaled[15:0];
        end
    endfunction
    wire [15:0] input_pcm = quantize16(sample_data);
    wire [15:0] right_pcm = STEREO_ENABLE ? quantize16(sample_right) : input_pcm;
    // Last left-slot bit is captured at this rising BCK edge. Digital
    // serialization completion is independent of PCM being zero or nonzero.
    assign trace_dac_done = reset_n && frame_tag_valid &&
        divider == BCK_HALF_CYCLES-1 && !hp_bck && bit_index == 31;
    assign trace_dac_revision = frame_revision;
    assign trace_dac_nonzero_voices = frame_nonzero_voices;
    // NS4263 shutdown is active HIGH. Allow 512 zero/audio frames to settle.
    assign pa_en = !reset_n || !warmup[9];

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            divider <= 0;
            bit_index <= 31;
            hp_bck <= 1;
            hp_ws <= 1;
            hp_din <= 0;
            sample_tick <= 0;
            pending_sample <= 0;
            frame_sample <= 0;
            pending_right <= 0; frame_right <= 0;
            pending_valid <= 0;
            pending_revision <= 0; frame_revision <= 0;
            pending_trigger_reference <= 0; frame_trigger_reference <= 0;
            pending_nonzero_voices <= 0; frame_nonzero_voices <= 0; frame_tag_valid <= 0;
            warmup <= 0;
            underrun_count <= 0;
            frame_count <= 0;
        end else begin
            sample_tick <= 0;
            if (sample_valid) begin
                pending_sample <= input_pcm;
                pending_right <= right_pcm;
                pending_valid <= 1;
                pending_revision <= sample_revision;
                pending_trigger_reference <= sample_trigger_reference;
                pending_nonzero_voices <= sample_nonzero_voices;
            end
            if (divider == BCK_HALF_CYCLES-1) begin
                divider <= 0;
                hp_bck <= ~hp_bck;
                if (hp_bck) begin // falling edge: launch next serial bit
                    bit_index <= bit_index + 1'b1;
                    if (bit_index == 31) begin
                        hp_ws <= 0;
                        sample_tick <= 1;
                        frame_count <= frame_count + 1'b1;
                        if (!warmup[9]) warmup <= warmup + 1'b1;
                        // Same-edge arrivals are accepted directly, never discarded.
                        if (sample_valid) begin
                            frame_sample <= input_pcm;
                            frame_right <= right_pcm;
                            hp_din <= right_pcm[15];
                            frame_revision <= sample_revision;
                            frame_trigger_reference <= sample_trigger_reference;
                            frame_nonzero_voices <= sample_nonzero_voices; frame_tag_valid <= 1;
                        end else if (pending_valid) begin
                            frame_sample <= pending_sample;
                            frame_right <= pending_right;
                            hp_din <= pending_right[15];
                            frame_revision <= pending_revision;
                            frame_trigger_reference <= pending_trigger_reference;
                            frame_nonzero_voices <= pending_nonzero_voices; frame_tag_valid <= 1;
                        end else begin
                            frame_sample <= 0;
                            frame_right <= 0;
                            hp_din <= 0;
                            frame_revision <= 0; frame_nonzero_voices <= 0; frame_tag_valid <= 0;
                            frame_trigger_reference <= 0;
                            if (frame_count != 0)
                                underrun_count <= underrun_count + 1'b1;
                        end
                        pending_valid <= 0;
                    end else begin
                        hp_ws <= (bit_index >= 15);
                        hp_din <= bit_index >= 15 ? frame_sample[15 - ((bit_index + 1'b1) & 15)] :
                                                  frame_right[15 - ((bit_index + 1'b1) & 15)];
                    end
                end
            end else divider <= divider + 1'b1;
        end
    end
endmodule
