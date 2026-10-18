`timescale 1ns/1ps
// Bounded rolling row storage used by the streaming Basic Pitch head.
//
// The address is explicitly row-major and the row index wraps modulo
// ROWS.  The producer advances a row only after every column has been
// accepted, so a consumer can keep a fixed 19-row dependency window without
// retaining a complete feature map in DDR or registers.
module basic_pitch_row_buffer #(
    parameter integer ROWS = 19,
    parameter integer COLS = 264,
    parameter integer DATA_WIDTH = 16
) (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic write_i,
    input  logic [$clog2(ROWS)-1:0] write_row_i,
    input  logic [$clog2(COLS)-1:0] write_col_i,
    input  logic signed [DATA_WIDTH-1:0] write_data_i,
    input  logic read_i,
    input  logic [$clog2(ROWS)-1:0] read_row_i,
    input  logic [$clog2(COLS)-1:0] read_col_i,
    output logic signed [DATA_WIDTH-1:0] read_data_o
);
    localparam integer ROW_AW = (ROWS <= 1) ? 1 : $clog2(ROWS);
    localparam integer COL_AW = (COLS <= 1) ? 1 : $clog2(COLS);
    logic signed [DATA_WIDTH-1:0] mem [0:ROWS*COLS-1];
    integer i;

    wire [ROW_AW-1:0] wr_row = (write_row_i >= ROWS) ? '0 : write_row_i;
    wire [COL_AW-1:0] wr_col = (write_col_i >= COLS) ? '0 : write_col_i;
    wire [ROW_AW-1:0] rd_row = (read_row_i >= ROWS) ? '0 : read_row_i;
    wire [COL_AW-1:0] rd_col = (read_col_i >= COLS) ? '0 : read_col_i;
    wire [31:0] wr_addr = wr_row * COLS + wr_col;
    wire [31:0] rd_addr = rd_row * COLS + rd_col;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            read_data_o <= '0;
        end else begin
            if (write_i)
                mem[wr_addr] <= write_data_i;
            if (read_i)
                read_data_o <= mem[rd_addr];
        end
    end
endmodule
