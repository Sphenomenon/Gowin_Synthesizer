`timescale 1ns / 1ps
`default_nettype none

// QT2160 qualifies the touch itself. Keep new touches responsive, suppress
// position noise, and require a second nearby sample before accepting a jump.
module midi_slider_filter #(
    parameter integer DEADBAND = 3,
    parameter integer JUMP_THRESHOLD = 32,
    parameter integer JUMP_TOLERANCE = 3
) (
    input wire clk,
    input wire reset,
    input wire sample_valid,
    input wire raw_touch,
    input wire [7:0] raw_position,
    output reg valid,
    output reg touched,
    output reg [7:0] position
);
    reg candidate_valid;
    reg [7:0] candidate_position;
    wire [8:0] distance;
    wire [8:0] candidate_distance;

    // Extend before subtraction so transitions across 0/255 cannot wrap.
    assign distance = raw_position >= position
        ? {1'b0, raw_position} - {1'b0, position}
        : {1'b0, position} - {1'b0, raw_position};
    assign candidate_distance = raw_position >= candidate_position
        ? {1'b0, raw_position} - {1'b0, candidate_position}
        : {1'b0, candidate_position} - {1'b0, raw_position};

    always @(posedge clk) begin
        if (reset) begin
            valid <= 1'b0;
            touched <= 1'b0;
            position <= 8'd0;
            candidate_valid <= 1'b0;
            candidate_position <= 8'd0;
        end else begin
            valid <= 1'b0;
            if (sample_valid) begin
                valid <= 1'b1;
                if (!raw_touch) begin
                    touched <= 1'b0;
                    candidate_valid <= 1'b0;
                end else if (!touched) begin
                    touched <= 1'b1;
                    position <= raw_position;
                    candidate_valid <= 1'b0;
                end else if (distance < DEADBAND) begin
                    candidate_valid <= 1'b0;
                end else if (distance <= JUMP_THRESHOLD) begin
                    position <= raw_position;
                    candidate_valid <= 1'b0;
                end else if (candidate_valid &&
                             candidate_distance <= JUMP_TOLERANCE) begin
                    position <= raw_position;
                    candidate_valid <= 1'b0;
                end else begin
                    candidate_position <= raw_position;
                    candidate_valid <= 1'b1;
                end
            end
        end
    end
endmodule

`default_nettype wire
