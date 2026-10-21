`timescale 1ns/1ps
// Dual-clock Gray-pointer FIFO. Memory entries are immutable from write commit
// until the synchronized read pointer releases them, so the show-ahead read is
// stable before read_valid_o can assert in the destination domain.
module music_async_fifo #(
    parameter integer WIDTH=309,
    parameter integer ADDRESS_BITS=4
)(
    input  logic write_clk_i,write_rst_ni,
    input  logic write_valid_i,
    output logic write_ready_o,
    input  logic [WIDTH-1:0] write_data_i,
    input  logic read_clk_i,read_rst_ni,
    output logic read_valid_o,
    input  logic read_ready_i,
    output logic [WIDTH-1:0] read_data_o
);
    localparam integer POINTER_BITS=ADDRESS_BITS+1;
    logic [WIDTH-1:0] memory[0:(1<<ADDRESS_BITS)-1];
    logic [POINTER_BITS-1:0] write_binary,write_gray,read_binary,read_gray;
    (* ASYNC_REG="TRUE" *) logic [POINTER_BITS-1:0] read_gray_meta,read_gray_sync;
    (* ASYNC_REG="TRUE" *) logic [POINTER_BITS-1:0] write_gray_meta,write_gray_sync;

    wire write_fire=write_valid_i && write_ready_o;
    wire read_fire=read_valid_o && read_ready_i;
    wire [POINTER_BITS-1:0] write_binary_next=write_binary+write_fire;
    wire [POINTER_BITS-1:0] read_binary_next=read_binary+read_fire;
    wire [POINTER_BITS-1:0] write_gray_next=(write_binary_next>>1)^write_binary_next;
    wire [POINTER_BITS-1:0] read_gray_next=(read_binary_next>>1)^read_binary_next;
    wire full=write_gray=={~read_gray_sync[POINTER_BITS-1:POINTER_BITS-2],
                           read_gray_sync[POINTER_BITS-3:0]};
    assign write_ready_o=!full;
    assign read_valid_o=read_gray!=write_gray_sync;
    assign read_data_o=memory[read_binary[ADDRESS_BITS-1:0]];

    always_ff @(posedge write_clk_i or negedge write_rst_ni)begin
        if(!write_rst_ni)begin
            write_binary<=0;write_gray<=0;read_gray_meta<=0;read_gray_sync<=0;
        end else begin
            read_gray_meta<=read_gray;read_gray_sync<=read_gray_meta;
            if(write_fire)begin
                memory[write_binary[ADDRESS_BITS-1:0]]<=write_data_i;
                write_binary<=write_binary_next;write_gray<=write_gray_next;
            end
        end
    end
    always_ff @(posedge read_clk_i or negedge read_rst_ni)begin
        if(!read_rst_ni)begin
            read_binary<=0;read_gray<=0;write_gray_meta<=0;write_gray_sync<=0;
        end else begin
            write_gray_meta<=write_gray;write_gray_sync<=write_gray_meta;
            if(read_fire)begin read_binary<=read_binary_next;read_gray<=read_gray_next;end
        end
    end
endmodule
