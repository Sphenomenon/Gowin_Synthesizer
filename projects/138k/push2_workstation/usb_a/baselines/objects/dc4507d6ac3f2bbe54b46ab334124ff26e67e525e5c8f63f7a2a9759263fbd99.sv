`timescale 1ns/1ps

// Register the DDR-side output of the model request CDC FIFO.  The FIFO pop
// then depends only on this local full bit, not on the shared DDR arbiter.
module basic_pitch_ddr_command_buffer (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        in_valid_i,
    input  logic [48:0] in_data_i,
    output logic        in_ready_o,
    output logic        out_valid_o,
    output logic [48:0] out_data_o,
    input  logic        out_ready_i
);
    logic full;
    logic [48:0] data_q;
    assign in_ready_o = !full;
    assign out_valid_o = full;
    assign out_data_o = data_q;
    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            full <= 1'b0;
            data_q <= 49'd0;
        end else if (full && out_ready_i) begin
            full <= 1'b0;
        end else if (!full && in_valid_i) begin
            data_q <= in_data_i;
            full <= 1'b1;
        end
    end
endmodule
