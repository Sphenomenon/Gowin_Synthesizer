`timescale 1ns/1ps
// One held word, toggle handshake. Source has no ready/backpressure input.
// Both domains share async reset; each releases locally. A stopped consumer
// drops new observations (counted), never stalls audio or overwrites held data.
module gw138k_stream_cdc #(parameter integer WIDTH=32, parameter bit PRESERVE_RELEASE=0) (
    input wire reset_n, source_clk, destination_clk,
    input wire source_valid,
    input wire [WIDTH-1:0] source_data,
    output logic [31:0] drop_count,
    output logic destination_valid,
    output logic [WIDTH-1:0] destination_data
);
    logic [2:0] source_release, destination_release;
    (* ASYNC_REG="TRUE" *) logic ack_meta, ack_sync, req_meta, req_sync;
    logic req_settled, request_toggle, acknowledge_toggle;
    logic [WIDTH-1:0] held_data;
    // Only the selected retained mailboxes keep independent release state.
    // Literal attributes are required by Gowin; parameter-valued attributes
    // are not honored by this synthesis version.
    generate if(PRESERVE_RELEASE)begin:g_preserved_release
        (* ASYNC_REG="TRUE", syn_preserve=1, syn_keep=1 *)
        logic [2:0] source_pipe, destination_pipe;
        always_ff @(posedge source_clk or negedge reset_n)
            if(!reset_n)source_pipe<=0;
            else source_pipe<={source_pipe[1:0],1'b1};
        always_ff @(posedge destination_clk or negedge reset_n)
            if(!reset_n)destination_pipe<=0;
            else destination_pipe<={destination_pipe[1:0],1'b1};
        assign source_release=source_pipe;
        assign destination_release=destination_pipe;
    end else begin:g_parent_release
        always_ff @(posedge source_clk or negedge reset_n)
            if(!reset_n)source_release<=0;
            else source_release<={source_release[1:0],1'b1};
        always_ff @(posedge destination_clk or negedge reset_n)
            if(!reset_n)destination_release<=0;
            else destination_release<={destination_release[1:0],1'b1};
    end endgenerate
    wire source_reset_n=source_release[2];
    wire destination_reset_n=destination_release[2];
    always_ff @(posedge source_clk or negedge source_reset_n) begin
        if(!source_reset_n) begin
            ack_meta<=0; ack_sync<=0; request_toggle<=0; held_data<=0; drop_count<=0;
        end else begin
            ack_meta<=acknowledge_toggle; ack_sync<=ack_meta;
            if(source_valid) begin
                if(ack_sync==request_toggle) begin
                    held_data<=source_data; request_toggle<=~request_toggle;
                end else drop_count<=drop_count+1'b1;
            end
        end
    end
    always_ff @(posedge destination_clk or negedge destination_reset_n) begin
        if(!destination_reset_n) begin
            req_meta<=0; req_sync<=0; req_settled<=0; acknowledge_toggle<=0;
            destination_valid<=0; destination_data<=0;
        end else begin
            req_meta<=request_toggle; req_sync<=req_meta; req_settled<=req_sync;
            destination_valid<=0;
            if(req_settled!=acknowledge_toggle) begin
                destination_data<=held_data; destination_valid<=1;
                acknowledge_toggle<=req_settled;
            end
        end
    end
endmodule
