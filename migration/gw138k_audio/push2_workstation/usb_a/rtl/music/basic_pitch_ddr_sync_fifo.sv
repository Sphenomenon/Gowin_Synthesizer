`timescale 1ns/1ps
// DDR-bound delay maintenance FIFO with synchronous dual-port BSRAM read.
// Preload one entry into an output hold; only the consumer releases that hold.
// Both reset inputs must assert together, as in the original P10 integration.
module basic_pitch_ddr_sync_fifo #(
    parameter integer WIDTH=65, ADDRESS_BITS=9
)(
    input wire write_clk_i,write_rst_ni,write_valid_i,
    output wire write_ready_o,
    input wire [WIDTH-1:0] write_data_i,
    input wire read_clk_i,read_rst_ni,
    output wire read_valid_o,
    input wire read_ready_i,
    output wire [WIDTH-1:0] read_data_o
);
    localparam integer POINTER_BITS=ADDRESS_BITS+1;
    (* syn_ramstyle="block_ram" *) reg [WIDTH-1:0] memory[0:(1<<ADDRESS_BITS)-1];
    reg [POINTER_BITS-1:0] write_binary,write_gray,read_binary,read_gray;
    (* ASYNC_REG="TRUE" *) reg [POINTER_BITS-1:0] read_gray_meta,read_gray_sync;
    (* ASYNC_REG="TRUE" *) reg [POINTER_BITS-1:0] write_gray_meta,write_gray_sync;
    reg [WIDTH-1:0] ram_q,output_data;
    reg fetch_pending,output_valid;
    wire full=write_gray=={~read_gray_sync[POINTER_BITS-1:POINTER_BITS-2],read_gray_sync[POINTER_BITS-3:0]};
    wire write_fire=write_valid_i && !full;
    wire [POINTER_BITS-1:0] write_next=write_binary+1'b1;
    wire [POINTER_BITS-1:0] read_next=read_binary+1'b1;
    wire output_pop=output_valid && read_ready_i;
    wire fetch=!fetch_pending && (!output_valid || output_pop) && read_gray!=write_gray_sync;
    assign write_ready_o=!full;
    assign read_valid_o=output_valid;
    assign read_data_o=output_data;
    initial if(WIDTH<1 || ADDRESS_BITS<2 || ADDRESS_BITS>12)$fatal(1,"invalid synchronous DDR FIFO parameters");
    // Keep reset off the RAM read register so the vendor infers a real
    // synchronous dual-port memory. Invalid data remains masked by valid.
    always @(posedge write_clk_i)if(write_rst_ni && write_fire)
        memory[write_binary[ADDRESS_BITS-1:0]]<=write_data_i;
    always @(posedge read_clk_i)ram_q<=memory[read_binary[ADDRESS_BITS-1:0]];
    always @(posedge write_clk_i or negedge write_rst_ni)begin
        if(!write_rst_ni)begin write_binary<=0;write_gray<=0;read_gray_meta<=0;read_gray_sync<=0;end
        else begin
            read_gray_meta<=read_gray;read_gray_sync<=read_gray_meta;
            if(write_fire)begin write_binary<=write_next;write_gray<=write_next^(write_next>>1);end
        end
    end
    always @(posedge read_clk_i or negedge read_rst_ni)begin
        if(!read_rst_ni)begin
            read_binary<=0;read_gray<=0;write_gray_meta<=0;write_gray_sync<=0;
            fetch_pending<=0;output_valid<=0;output_data<=0;
        end else begin
            write_gray_meta<=write_gray;write_gray_sync<=write_gray_meta;
            if(output_pop)output_valid<=0;
            if(fetch)begin read_binary<=read_next;read_gray<=read_next^(read_next>>1);fetch_pending<=1;end
            if(fetch_pending)begin output_data<=ram_q;output_valid<=1;fetch_pending<=0;end
        end
    end
endmodule
