`timescale 1ns/1ps

// Selected-MCLK domain only. PCM is already selected and master-volume scaled.
// The renderer bridge must use each request exactly once and preserve its tags.
module workstation_i2s_serializer #(
    parameter integer PDN_HOLD_FRAMES = 4,
    parameter integer STARTUP_MUTE_FRAMES = 1028,
    // Explicit opt-in keeps existing unconnected/legacy sample interfaces
    // unchanged. Tagged frame compositions must enable and connect this bit.
    parameter bit SAMPLE_ERROR_ENABLE = 0
) (
    input wire clk_i, rst_ni,
    // Stable before local reset release through the first selected-clock edge.
    // Later staged changes are ignored while the old frame drains.
    input wire rate_44k1_i,
    input wire [31:0] epoch_i,
    input wire quiesce_i, resume_i,
    output reg serial_quiescent_o, output_running_o,
    output wire prefill_ready_o,
    // Request the next output slot, one full frame ahead after prefill.
    output reg request_o,
    output reg [31:0] request_sequence_o,
    output wire request_44k1_o,
    output wire [31:0] request_epoch_o,
    input wire sample_valid_i,
    output wire sample_ready_o,
    input wire sample_44k1_i,
    input wire sample_error_i,
    input wire [31:0] sample_epoch_i, sample_sequence_i, sample_pcm_i,
    output wire mclk_o,
    output reg bck_o, lrck_o, data_o,
    output wire pdn_no, smute_o,
    // Completed physical frame; underruns are explicit zero/error frames.
    output reg frame_valid_o, frame_error_o,
    output reg [31:0] frame_pcm_o, frame_sequence_o,
    output wire frame_44k1_o,
    output wire [31:0] frame_epoch_o,
    output reg [31:0] underrun_count_o, rejected_sample_count_o,
    output reg [31:0] source_error_count_o
);
    localparam integer STARTUP_BITS = $clog2(STARTUP_MUTE_FRAMES+1);
    initial begin
        if (PDN_HOLD_FRAMES < 1 || STARTUP_MUTE_FRAMES <= PDN_HOLD_FRAMES)
            $fatal(1, "invalid DAC startup frame counts");
    end

    reg configured, mode_44k1;
    reg [31:0] epoch;
    reg [1:0] half_count;
    reg [5:0] bit_position;
    reg [STARTUP_BITS-1:0] startup_frames;
    reg playing, current_error;
    reg [31:0] current_pcm, current_sequence;
    reg requested, have_next, next_error;
    reg [31:0] next_pcm, wanted_sequence;
    wire half_end = half_count == (mode_44k1 ? 2'd2 : 2'd1);
    wire frame_boundary = half_end && bck_o && bit_position == 6'd63;
    wire startup_done = startup_frames == STARTUP_BITS'(STARTUP_MUTE_FRAMES);
    wire incoming = sample_valid_i && sample_ready_o;
    wire incoming_match = incoming && requested &&
        sample_44k1_i == mode_44k1 && sample_epoch_i == epoch &&
        sample_sequence_i == wanted_sequence;
    wire next_available = have_next || incoming_match;
    wire [31:0] available_pcm = have_next ? next_pcm : sample_pcm_i;
    wire available_error = SAMPLE_ERROR_ENABLE && (have_next ? next_error : sample_error_i);

    assign mclk_o = clk_i;
    assign pdn_no = rst_ni && configured && startup_frames >= STARTUP_BITS'(PDN_HOLD_FRAMES);
    assign smute_o = !pdn_no || !startup_done || !playing;
    assign prefill_ready_o = configured && startup_done && have_next && !quiesce_i;
    assign sample_ready_o = configured && !have_next && !quiesce_i;
    assign request_44k1_o = mode_44k1;
    assign request_epoch_o = epoch;
    assign frame_44k1_o = mode_44k1;
    assign frame_epoch_o = epoch;

    function automatic [31:0] saturating_increment(input [31:0] value);
        saturating_increment = &value ? value : value + 1'b1;
    endfunction

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            configured <= 0; mode_44k1 <= 0; epoch <= 0;
            half_count <= 0; bit_position <= 0;
            bck_o <= 0; lrck_o <= 0; data_o <= 0;
            startup_frames <= 0;
            playing <= 0; current_error <= 0; current_pcm <= 0; current_sequence <= 0;
            requested <= 0; have_next <= 0; next_error <= 0; next_pcm <= 0; wanted_sequence <= 0;
            serial_quiescent_o <= 1; output_running_o <= 0;
            request_o <= 0; request_sequence_o <= 0;
            frame_valid_o <= 0; frame_error_o <= 0;
            frame_pcm_o <= 0; frame_sequence_o <= 0;
            underrun_count_o <= 0; rejected_sample_count_o <= 0;
            source_error_count_o <= 0;
        end else if (!configured) begin
            // Never change a divider in a running frame.
            configured <= 1;
            mode_44k1 <= rate_44k1_i;
            epoch <= epoch_i;
        end else begin
            request_o <= 0;
            frame_valid_o <= 0;
            if (quiesce_i) begin
                // The current serial frame continues until its final bit.
                have_next <= 0;
                requested <= 0;
                output_running_o <= 0;
            end else begin
                serial_quiescent_o <= 0;
                if (!requested) begin
                    requested <= 1;
                    request_o <= 1;
                    request_sequence_o <= wanted_sequence;
                end
                if (incoming) begin
                    if (incoming_match) begin
                        have_next <= 1; next_pcm <= sample_pcm_i;
                        next_error <= SAMPLE_ERROR_ENABLE && sample_error_i;
                    end
                    else rejected_sample_count_o <= saturating_increment(rejected_sample_count_o);
                end
            end

            if (!half_end) half_count <= half_count + 1'b1;
            else begin
                half_count <= 0;
                bck_o <= !bck_o;
                if (bck_o) begin
                    bit_position <= bit_position + 1'b1;
                    // Position 0/32 is the I2S delay bit; 1..16/33..48
                    // carry PCM16, and the rest of each 32-bit slot is zero.
                    if (bit_position == 6'd31 || bit_position == 6'd63) data_o <= 0;
                    else if (playing && bit_position < 6'd16)
                        data_o <= current_pcm[31-bit_position];
                    else if (playing && bit_position >= 6'd32 && bit_position < 6'd48)
                        data_o <= current_pcm[47-bit_position];
                    else data_o <= 0;
                    if (bit_position == 6'd31) lrck_o <= 1;
                    if (frame_boundary) begin
                        lrck_o <= 0;
                        if (!startup_done) startup_frames <= startup_frames + 1'b1;
                        if (playing) begin
                            frame_valid_o <= 1;
                            frame_error_o <= current_error;
                            frame_pcm_o <= current_pcm;
                            frame_sequence_o <= current_sequence;
                            if (!current_error && !quiesce_i) output_running_o <= 1;
                        end
                        if (quiesce_i) begin
                            playing <= 0;
                            current_pcm <= 0;
                            current_error <= 0;
                            serial_quiescent_o <= 1;
                        end else if (startup_done && resume_i && (playing || next_available)) begin
                            playing <= 1;
                            current_pcm <= next_available && !available_error ? available_pcm : 32'd0;
                            current_sequence <= wanted_sequence;
                            current_error <= !next_available || available_error;
                            if (!next_available)
                                underrun_count_o <= saturating_increment(underrun_count_o);
                            else if (available_error)
                                source_error_count_o <= saturating_increment(source_error_count_o);
                            have_next <= 0;
                            wanted_sequence <= wanted_sequence + 1'b1;
                            requested <= 1;
                            request_o <= 1;
                            request_sequence_o <= wanted_sequence + 1'b1;
                        end else begin
                            playing <= 0;
                            current_pcm <= 0;
                            current_error <= 0;
                        end
                    end
                end
            end
        end
    end
endmodule
