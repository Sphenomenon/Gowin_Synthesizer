`timescale 1ns/1ps

module workstation_frame_delivery #(
    parameter bit REQUEST_EPOCH_SNAPSHOT=0
) (
    input wire clk_i, rst_ni, sample_ce_i, muted_i,
    input wire [9:0] cancel_epoch_i,
    input wire render_valid_i,
    input wire signed [31:0] left_i, right_i,
    input wire [31:0] reference_i, voices_i,
    output wire valid_o,
    output wire signed [31:0] left_o, right_o,
    output wire [31:0] reference_o, voices_o,
    output logic [31:0] duplicate_frames_o
);
    logic [9:0] observed_epoch;
    logic frame_offered;
    logic frame_cancelled;
    // A request-driven caller snapshots the current epoch when accepting a
    // new slot. A previous slot's pending epoch observation cannot cancel it.
    // A new PANIC on that edge changes the input epoch on the next cycle and
    // still cancels the newly accepted request.
    wire cancelled = cancel_epoch_i != observed_epoch &&
        !(REQUEST_EPOCH_SNAPSHOT && sample_ce_i);
    wire available = !frame_offered || sample_ce_i;
    wire render_allowed = !frame_cancelled || sample_ce_i;
    wire muted_frame = muted_i && sample_ce_i;

    assign valid_o = available && ((render_valid_i && render_allowed) || cancelled || muted_frame);
    assign left_o = cancelled || muted_i ? 32'sd0 : left_i;
    assign right_o = cancelled || muted_i ? 32'sd0 : right_i;
    assign reference_o = cancelled || muted_i ? 32'd0 : reference_i;
    assign voices_o = cancelled || muted_i ? 32'd0 : voices_i;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            observed_epoch <= 0;
            frame_offered <= 0;
            frame_cancelled <= 0;
            duplicate_frames_o <= 0;
        end else begin
            observed_epoch <= cancel_epoch_i;
            if (sample_ce_i) begin
                frame_offered <= 0;
                frame_cancelled <= 0;
            end
            if (valid_o) frame_offered <= 1;
            if (cancelled || muted_frame) frame_cancelled <= 1;
            if (render_valid_i && !available && !frame_cancelled && !cancelled && !muted_i)
                duplicate_frames_o <= duplicate_frames_o + 1'b1;
        end
    end
endmodule
