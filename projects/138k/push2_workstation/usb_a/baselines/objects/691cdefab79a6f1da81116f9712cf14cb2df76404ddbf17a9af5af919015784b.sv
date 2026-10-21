`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// DDR backing store for the two largest CNN intermediate tensors.  Notes and
// onset are written through as they are produced.  Before their consumer runs,
// only its temporal dependency window is loaded into one shared BSRAM cache.
module basic_pitch_feature_ddr #(
    parameter integer FRAMES = 172,
    parameter integer BINS = 88,
    parameter integer CHANNELS = 32,
    parameter integer MAX_ROWS = 7
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               contour_we_i,
    input  logic [8:0]         contour_row_i,
    input  logic [8:0]         contour_col_i,
    input  logic [2:0]         contour_ch_i,
    input  logic signed [15:0] contour_data_i,
    input  logic               notes_we_i,
    input  logic [8:0]         notes_row_i,
    input  logic [6:0]         notes_col_i,
    input  logic [4:0]         notes_ch_i,
    input  logic signed [15:0] notes_data_i,
    input  logic               onset_we_i,
    input  logic [8:0]         onset_row_i,
    input  logic [6:0]         onset_col_i,
    input  logic [4:0]         onset_ch_i,
    input  logic signed [15:0] onset_data_i,

    input  logic               load_start_i,
    input  logic [1:0]         load_kind_i, // 0=contour, 1=notes, 2=onset
    input  logic signed [10:0] load_start_row_i,
    input  logic [3:0]         load_rows_i,
    output logic               load_done_o,
    output logic               overflow_o,

    input  logic               read_valid_i,
    input  logic [14:0]        read_addr_i,
    output logic signed [15:0] read_data_o,

    output logic               mem_req_o,
    output logic               mem_write_o,
    output logic [31:0]        mem_byte_addr_o,
    output logic [15:0]        mem_wdata_o,
    input  logic               mem_ready_i,
    input  logic               mem_rsp_valid_i,
    input  logic [15:0]        mem_rdata_i
);
    localparam integer MAX_WORDS = MAX_ROWS * BINS * CHANNELS;
    localparam logic [2:0] S_IDLE=3'd0, S_SLOT=3'd1, S_READ=3'd2,
                           S_WAIT=3'd3, S_DONE=3'd4;

    (* ram_style = "block", syn_ramstyle = "block_ram" *)
    logic signed [15:0] cache [0:MAX_WORDS-1];
    logic [2:0] state;
    logic [1:0] load_kind;
    logic [8:0] load_bins;
    logic [5:0] load_channels;
    logic [31:0] load_base;
    logic signed [10:0] start_row;
    logic [3:0] row_count, slot;
    logic [8:0] col;
    logic [5:0] ch;
    logic write_pending;
    logic [31:0] write_addr;
    logic [15:0] write_data;

    wire signed [11:0] global_row = start_row + $signed({8'd0, slot});
    wire global_valid = (global_row >= 0) && (global_row < FRAMES);
    wire [14:0] cache_index = ((slot * load_bins + col) * load_channels) + ch;
    wire [31:0] load_linear = (($unsigned(global_row) * load_bins + col) * load_channels) + ch;

    assign load_done_o = state == S_DONE;
    assign mem_req_o = write_pending || (state == S_READ);
    assign mem_write_o = write_pending;
    assign mem_byte_addr_o = write_pending ? write_addr
                                            : load_base + (load_linear << 1);
    assign mem_wdata_o = write_data;

    always_ff @(posedge clk_i) begin
        if (read_valid_i && (read_addr_i < MAX_WORDS))
            read_data_o <= cache[read_addr_i];
        else
            read_data_o <= 16'sd0;
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_IDLE;
            load_kind <= 2'd0;
            load_bins <= 9'd88;
            load_channels <= 6'd32;
            load_base <= `BP_DDR_NN_NOTES_BYTE_BASE;
            start_row <= '0;
            row_count <= '0;
            slot <= '0;
            col <= '0;
            ch <= '0;
            write_pending <= 1'b0;
            write_addr <= '0;
            write_data <= '0;
            overflow_o <= 1'b0;
        end else begin
            if (write_pending && mem_ready_i)
                write_pending <= 1'b0;

            if (contour_we_i || notes_we_i || onset_we_i) begin
                if (write_pending && !mem_ready_i)
                    overflow_o <= 1'b1;
                write_pending <= 1'b1;
                if (contour_we_i) begin
                    write_addr <= `BP_DDR_NN_CONTOUR_BYTE_BASE +
                        (((contour_row_i * 264 + contour_col_i) * 8 + contour_ch_i) << 1);
                    write_data <= contour_data_i;
                end else if (notes_we_i) begin
                    write_addr <= `BP_DDR_NN_NOTES_BYTE_BASE +
                        (((notes_row_i * BINS + notes_col_i) * CHANNELS + notes_ch_i) << 1);
                    write_data <= notes_data_i;
                end else begin
                    write_addr <= `BP_DDR_NN_ONSET_BYTE_BASE +
                        (((onset_row_i * BINS + onset_col_i) * CHANNELS + onset_ch_i) << 1);
                    write_data <= onset_data_i;
                end
            end

            case (state)
                S_IDLE: if (load_start_i) begin
                    load_kind <= load_kind_i;
                    if (load_kind_i == 0) begin
                        load_bins <= 9'd264;
                        load_channels <= 6'd8;
                        load_base <= `BP_DDR_NN_CONTOUR_BYTE_BASE;
                    end else if (load_kind_i == 1) begin
                        load_bins <= 9'd88;
                        load_channels <= 6'd32;
                        load_base <= `BP_DDR_NN_NOTES_BYTE_BASE;
                    end else begin
                        load_bins <= 9'd88;
                        load_channels <= 6'd32;
                        load_base <= `BP_DDR_NN_ONSET_BYTE_BASE;
                    end
                    start_row <= load_start_row_i;
                    row_count <= load_rows_i;
                    slot <= 0; col <= 0; ch <= 0;
                    state <= S_SLOT;
                end
                S_SLOT: if (!write_pending) begin
                    if (global_valid) begin
                        state <= S_READ;
                    end else begin
                        cache[cache_index] <= 16'sd0;
                        if (ch == load_channels-1) begin
                            ch <= 0;
                            if (col == load_bins-1) begin
                                col <= 0;
                                if (slot == row_count-1) state <= S_DONE;
                                else slot <= slot + 1'b1;
                            end else col <= col + 1'b1;
                        end else ch <= ch + 1'b1;
                    end
                end
                S_READ: if (mem_ready_i) state <= S_WAIT;
                S_WAIT: if (mem_rsp_valid_i) begin
                    cache[cache_index] <= mem_rdata_i;
                    if (ch == load_channels-1) begin
                        ch <= 0;
                        if (col == load_bins-1) begin
                            col <= 0;
                            if (slot == row_count-1) state <= S_DONE;
                            else begin slot <= slot + 1'b1; state <= S_SLOT; end
                        end else begin col <= col + 1'b1; state <= S_SLOT; end
                    end else begin ch <= ch + 1'b1; state <= S_SLOT; end
                end
                S_DONE: state <= S_IDLE;
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
