`timescale 1ns/1ps
// A bounded score queue. The producer pauses when 172 unplayed targets are
// buffered, then resumes as the player advances through the song.
module push2_score_guide (
    input  wire clk, rst,
    input  wire score_valid,
    output wire score_ready,
    input  wire [6:0] score_note,
    input  wire toggle,
    input  wire selected_i,
    input  wire clear_i,
    input  wire played_valid,
    input  wire [6:0] played_note,
    output reg  mode,
    output wire target_valid,
    output wire [6:0] target_note,
    output reg  [15:0] score_count,
    output reg  [15:0] cursor,
    output reg  [15:0] wrong_count,
    output reg  [63:0] guide_mask
);
    reg [6:0] notes [0:171];
    reg [7:0] read_index,write_index;
    assign score_ready = score_count != 16'hffff &&
                         (score_count - cursor) < 16'd172;
    assign target_valid = mode && selected_i && cursor != score_count;
    assign target_note = notes[read_index];
    always @* begin
        guide_mask = 64'd0;
        if (target_valid && target_note >= 7'd36 && target_note <= 7'd99)
            guide_mask[target_note - 7'd36] = 1'b1;
    end
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            mode <= 1'b0;
            score_count <= 16'd0;
            cursor <= 16'd0;
            read_index <= 8'd0;
            write_index <= 8'd0;
            wrong_count <= 16'd0;
        end else begin
            if (clear_i) begin
                score_count <= 16'd0;
                cursor <= 16'd0;
                read_index <= 8'd0;
                write_index <= 8'd0;
                wrong_count <= 16'd0;
            end else if (score_valid && score_ready) begin
                notes[write_index] <= score_note;
                write_index <= write_index == 8'd171 ? 8'd0 : write_index + 8'd1;
                score_count <= score_count + 16'd1;
            end
            if (toggle) begin
                mode <= !mode;
                wrong_count <= 16'd0;
            end else if (!clear_i && played_valid && target_valid) begin
                if (played_note == target_note) begin
                    cursor <= cursor + 16'd1;
                    read_index <= read_index == 8'd171 ? 8'd0 : read_index + 8'd1;
                end
                else if (wrong_count != 16'hffff)
                    wrong_count <= wrong_count + 16'd1;
            end
        end
    end
endmodule
