`timescale 1ns/1ps
// Full-precision 32-bit words, stored as two 16-bit halfwords in native GW5A
// SDP blocks. One word per 512 entries per block. Read returns valid after
// both halves; write-enable must have at least one idle clock between words.
// Clients use handshakes; no audio bits are discarded. RAM is never cleared.
module workstation_sdp_banked #(parameter integer WORDS=2048,
    parameter integer ADDR_WIDTH=$clog2(WORDS)) (
    input wire rst_ni,clear_i,
    input wire write_clk_i,write_enable_i,
    input wire [ADDR_WIDTH-1:0] write_addr_i,
    input wire [31:0] write_data_i,
    input wire read_clk_i,read_request_i,
    input wire [ADDR_WIDTH-1:0] read_addr_i,
    output reg read_valid_o,
    output reg [31:0] read_data_o
);
    localparam integer BANKS=(WORDS+511)/512;
    wire [15:0] data [0:BANKS-1];
    reg write_pending;
    reg [ADDR_WIDTH-1:0] write_hold,read_hold,bank_q;
    reg [15:0] write_high,read_low;
    reg [1:0] read_state;
    wire [ADDR_WIDTH-1:0] write_word=write_enable_i ? write_addr_i : write_hold;
    wire [9:0] write_half_addr={9'(write_word),!write_enable_i};
    wire [9:0] read_half_addr=read_request_i ? {9'(read_addr_i),1'b0} : {9'(read_hold),1'b1};
    genvar bank;
    generate for(bank=0;bank<BANKS;bank=bank+1) begin : g_bank
        workstation_sdp #(.DATA_WIDTH(16),.ADDR_WIDTH(10)) ram(
            .write_clk_i(write_clk_i),
            .write_enable_i(rst_ni && !clear_i && (write_enable_i || write_pending) &&
                           (write_word>>9)==bank && write_word<WORDS),
            .write_addr_i(write_half_addr),
            .write_data_i(write_enable_i ? write_data_i[15:0] : write_high),
            .read_clk_i(read_clk_i),.read_enable_i(read_request_i || read_state==1),
            .read_addr_i(read_half_addr),.read_data_o(data[bank]));
    end endgenerate
    always @(posedge write_clk_i or negedge rst_ni) begin
        if(!rst_ni)begin write_pending<=0;write_hold<=0;write_high<=0;end
        else if(clear_i)write_pending<=0;
        else begin
            write_pending<=write_enable_i;
            if(write_enable_i)begin write_hold<=write_addr_i;write_high<=write_data_i[31:16];end
        end
    end
    always @(posedge read_clk_i or negedge rst_ni) begin
        if(!rst_ni)begin
            read_hold<=0;bank_q<=0;read_state<=0;read_low<=0;read_valid_o<=0;read_data_o<=0;
        end else begin
            read_valid_o<=0;
            if(clear_i)begin read_state<=0;read_data_o<=0;end
            else case(read_state)
                0:if(read_request_i)begin read_hold<=read_addr_i;bank_q<=read_addr_i>>9;read_state<=1;end
                1:begin read_low<=bank_q<BANKS ? data[bank_q] : 16'd0;read_state<=2;end
                2:begin
                    read_data_o<=read_hold<WORDS ? {data[bank_q],read_low} : 32'd0;
                    read_valid_o<=1;read_state<=0;
                end
                default:read_state<=0;
            endcase
        end
    end
endmodule
