`timescale 1ns/1ps
// Dual-clock Gray-pointer FIFO. Memory entries are immutable from write commit
// until the synchronized read pointer releases them, so the show-ahead read is
// stable before read_valid_o can assert in the destination domain.
module music_async_fifo #(
    parameter integer WIDTH=309,
    parameter integer ADDRESS_BITS=4,
    parameter RAM_STYLE="distributed_ram"
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
    logic [POINTER_BITS-1:0] write_binary,write_gray,read_binary,read_gray;
    (* ASYNC_REG="TRUE" *) logic [POINTER_BITS-1:0] read_gray_meta,read_gray_sync;
    (* ASYNC_REG="TRUE" *) logic [POINTER_BITS-1:0] write_gray_meta,write_gray_sync;

    wire write_fire=write_valid_i && write_ready_o;
    wire read_fire=read_valid_o && read_ready_i;
    wire [POINTER_BITS-1:0] write_binary_next=write_binary+1'b1;
    wire [POINTER_BITS-1:0] read_binary_next=read_binary+1'b1;
    wire [POINTER_BITS-1:0] write_gray_next=(write_binary_next>>1)^write_binary_next;
    wire [POINTER_BITS-1:0] read_gray_next=(read_binary_next>>1)^read_binary_next;
    wire full=write_gray=={~read_gray_sync[POINTER_BITS-1:POINTER_BITS-2],
                           read_gray_sync[POINTER_BITS-3:0]};
    assign read_valid_o=read_gray!=write_gray_sync;
    generate if(WIDTH==65 && ADDRESS_BITS>=8) begin:g_large_head
        // Adjacent heads live in opposite banks. Read both synchronously and
        // select the post-pop head, preserving a full-depth show-ahead FIFO.
        // A registered full flag releases conservatively one write clock late.
        logic full_q;
        logic [WIDTH-1:0] even_q,odd_q;
        logic head_odd;
        (* syn_ramstyle=RAM_STYLE *) logic [WIDTH-1:0] even_memory[0:(1<<(ADDRESS_BITS-1))-1];
        (* syn_ramstyle=RAM_STYLE *) logic [WIDTH-1:0] odd_memory[0:(1<<(ADDRESS_BITS-1))-1];
        wire [ADDRESS_BITS-2:0] even_address=read_binary[ADDRESS_BITS-1:1]+read_binary[0];
        assign write_ready_o=!full_q;
        assign read_data_o=head_odd ? odd_q : even_q;
        always_ff @(posedge write_clk_i or negedge write_rst_ni)begin
            if(!write_rst_ni)full_q<=0;
            else full_q<=(write_fire ? write_gray_next : write_gray)==
                {~read_gray_sync[POINTER_BITS-1:POINTER_BITS-2],read_gray_sync[POINTER_BITS-3:0]};
        end
        always @(posedge write_clk_i)begin
            if(write_rst_ni && write_fire)begin
                if(write_binary[0])odd_memory[write_binary[ADDRESS_BITS-1:1]]<=write_data_i;
                else even_memory[write_binary[ADDRESS_BITS-1:1]]<=write_data_i;
            end
        end
        always_ff @(posedge read_clk_i or negedge read_rst_ni)begin
            if(!read_rst_ni)begin even_q<=0;odd_q<=0;head_odd<=0;end
            else begin
                even_q<=even_memory[even_address];
                odd_q<=odd_memory[read_binary[ADDRESS_BITS-1:1]];
                head_odd<=read_binary[0]^read_fire;
            end
        end
    end else begin:g_small_head
        logic [WIDTH-1:0] memory[0:(1<<ADDRESS_BITS)-1];
        assign write_ready_o=!full;
        assign read_data_o=memory[read_binary[ADDRESS_BITS-1:0]];
        always @(posedge write_clk_i)begin
            if(write_rst_ni && write_fire)memory[write_binary[ADDRESS_BITS-1:0]]<=write_data_i;
        end
    end endgenerate

    always_ff @(posedge write_clk_i or negedge write_rst_ni)begin
        if(!write_rst_ni)begin
            write_binary<=0;write_gray<=0;read_gray_meta<=0;read_gray_sync<=0;
        end else begin
            read_gray_meta<=read_gray;read_gray_sync<=read_gray_meta;
            if(write_fire)begin
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
