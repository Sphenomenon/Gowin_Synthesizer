`timescale 1ns/1ps
// Hold one detector result until a matching new physical note-on is accepted.
// Releases, pressure, wrong notes, and repeated held-state snapshots cannot
// advance the PCM detector cursor.
module blocking_note_trainer (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        start_i,
    input  logic        stop_i,
    input  logic        target_valid_i,
    output logic        target_ready_o,
    input  logic [6:0]  target_note_i,
    input  logic [31:0] target_frame_i,
    input  logic [15:0] target_confidence_i,
    input  logic        played_note_valid_i,
    input  logic [6:0]  played_note_i,
    output logic        running_o,
    output logic        waiting_o,
    output logic        correct_pulse_o,
    output logic        wrong_pulse_o,
    output logic        request_next_o,
    output logic [6:0]  current_note_o,
    output logic [31:0] current_frame_o,
    output logic [15:0] current_confidence_o,
    output logic [63:0] guide_mask_o,
    output logic [31:0] accepted_count_o,
    output logic [31:0] wrong_count_o
);
    logic target_consumed;

    always_comb begin
        guide_mask_o = 64'd0;
        if (waiting_o && current_note_o >= 7'd36 && current_note_o <= 7'd99)
            guide_mask_o[current_note_o[5:0]-6'd36] = 1'b1;
    end

    assign target_ready_o = running_o && !waiting_o && !target_consumed;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            running_o <= 1'b0;
            waiting_o <= 1'b0;
            target_consumed <= 1'b0;
            correct_pulse_o <= 1'b0;
            wrong_pulse_o <= 1'b0;
            request_next_o <= 1'b0;
            current_note_o <= 7'd0;
            current_frame_o <= 32'd0;
            current_confidence_o <= 16'd0;
            accepted_count_o <= 32'd0;
            wrong_count_o <= 32'd0;
        end else begin
            correct_pulse_o <= 1'b0;
            wrong_pulse_o <= 1'b0;
            request_next_o <= 1'b0;
            if (stop_i) begin
                running_o <= 1'b0;
                waiting_o <= 1'b0;
                target_consumed <= 1'b0;
            end else if (start_i && !running_o) begin
                running_o <= 1'b1;
                waiting_o <= 1'b0;
                target_consumed <= 1'b0;
                accepted_count_o <= 32'd0;
                wrong_count_o <= 32'd0;
                request_next_o <= 1'b1;
            end else if (running_o) begin
                // A Viterbi result is a level held stable until the next
                // window starts. Consume it once; otherwise a correct key
                // would immediately re-arm the same target.
                if (!target_valid_i)
                    target_consumed <= 1'b0;
                if (!waiting_o && target_valid_i && !target_consumed) begin
                    waiting_o <= 1'b1;
                    target_consumed <= 1'b1;
                    current_note_o <= target_note_i;
                    current_frame_o <= target_frame_i;
                    current_confidence_o <= target_confidence_i;
                end else if (waiting_o && played_note_valid_i) begin
                    if (played_note_i == current_note_o) begin
                        waiting_o <= 1'b0;
                        correct_pulse_o <= 1'b1;
                        request_next_o <= 1'b1;
                        accepted_count_o <= accepted_count_o + 1'b1;
                    end else begin
                        wrong_pulse_o <= 1'b1;
                        wrong_count_o <= wrong_count_o + 1'b1;
                    end
                end
            end
        end
    end
endmodule
