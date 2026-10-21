`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// Copies the immutable CNN model image from distributed ROM into external DDR
// once after configuration.  distributed_rom is intentional: this boot image
// must not consume the BSRAM that the migration is meant to release.
module basic_pitch_model_loader #(
    parameter integer WORDS = 20721
) (
    input  logic        clk_i,
    input  logic        rst_ni,
    output logic        done_o,
    output logic        mem_req_o,
    output logic        mem_write_o,
    output logic [31:0] mem_byte_addr_o,
    output logic [15:0] mem_wdata_o,
    input  logic        mem_ready_i
);
    localparam logic [1:0] S_READ = 2'd0, S_LATCH = 2'd1,
                           S_WRITE = 2'd2, S_DONE = 2'd3;
    logic [1:0] state;
    logic [14:0] index;
    logic [15:0] rom_data;
    (* syn_romstyle = "distributed_rom", rom_style = "distributed" *)
    logic [15:0] model_rom [0:WORDS-1];
    initial $readmemh("rtl/music/weights/cnn_ddr_blob.mem", model_rom);

    assign done_o = state == S_DONE;
    assign mem_req_o = state == S_WRITE;
    assign mem_write_o = 1'b1;
    assign mem_byte_addr_o = `BP_DDR_NN_MODEL_BYTE_BASE + ({17'd0, index} << 1);
    assign mem_wdata_o = rom_data;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_READ;
            index <= '0;
            rom_data <= '0;
        end else begin
            if (state == S_READ) begin
                rom_data <= model_rom[index];
                state <= S_LATCH;
            end else if (state == S_LATCH) begin
                state <= S_WRITE;
            end else if (state == S_WRITE && mem_ready_i) begin
                if (index == WORDS - 1) state <= S_DONE;
                else begin
                    index <= index + 1'b1;
                    state <= S_READ;
                end
            end
        end
    end
endmodule
