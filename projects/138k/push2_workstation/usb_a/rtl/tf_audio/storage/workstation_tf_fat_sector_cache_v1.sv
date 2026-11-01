`timescale 1ns/1ps
// One metadata sector only. The file owner may publish a fill only after its
// actual CRC-enabled sector owner reports complete success. No audio storage.
module workstation_tf_fat_sector_cache_v1 (
    input wire clk_i,rst_ni,invalidate_i,
    input wire fill_start_i,
    input wire [31:0] fill_lba_i,
    input wire fill_byte_valid_i,
    input wire [8:0] fill_byte_index_i,
    input wire [7:0] fill_byte_i,
    input wire fill_done_i,
    input wire [31:0] lookup_lba_i,
    input wire [6:0] lookup_word_i,
    input wire lookup_request_i,
    output wire lookup_hit_o,
    output wire lookup_valid_o,
    output reg [31:0] lookup_data_o
);
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [31:0] words[0:127];
    reg valid,fill_live,fill_order_error,lookup_valid;
    reg [31:0] key_lba;
    reg [9:0] fill_count;
    reg [23:0] assembled_low;
    wire accept_lookup=lookup_request_i && lookup_hit_o && !fill_start_i;
    assign lookup_hit_o=valid && key_lba==lookup_lba_i && !invalidate_i && !fill_start_i;
    assign lookup_valid_o=lookup_valid && !invalidate_i && !fill_start_i;
    // One synchronous RAM read. Result validity is revoked immediately on a
    // lifecycle fence; the caller never consumes RAM contents without it.
    always @(posedge clk_i)begin
        if(accept_lookup)lookup_data_o<=words[lookup_word_i];
        if(fill_live && !invalidate_i && !fill_start_i && fill_byte_valid_i &&
           !fill_order_error && fill_count<512 &&
           fill_byte_index_i==fill_count[8:0])begin
            if(fill_byte_index_i[1:0]==3)
                words[fill_byte_index_i[8:2]]<={fill_byte_i,assembled_low};
        end
    end
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            valid<=0;fill_live<=0;fill_order_error<=0;fill_count<=0;
            key_lba<=0;assembled_low<=0;lookup_valid<=0;
        end else if(invalidate_i)begin
            valid<=0;fill_live<=0;fill_order_error<=0;fill_count<=0;lookup_valid<=0;
        end else begin
            lookup_valid<=accept_lookup;
            if(fill_start_i)begin
                // The old line is unusable before its first word is replaced.
                valid<=0;fill_live<=1;fill_order_error<=0;fill_count<=0;
                key_lba<=fill_lba_i;lookup_valid<=0;
            end else if(fill_live)begin
                if(fill_byte_valid_i)begin
                    if(fill_count>=512 || fill_byte_index_i!=fill_count[8:0])fill_order_error<=1;
                    else begin
                        fill_count<=fill_count+1'b1;
                        case(fill_byte_index_i[1:0])
                            0:assembled_low[7:0]<=fill_byte_i;
                            1:assembled_low[15:8]<=fill_byte_i;
                            2:assembled_low[23:16]<=fill_byte_i;
                            default:begin end
                        endcase
                    end
                end
                if(fill_done_i)begin
                    fill_live<=0;
                    valid<=fill_count==512 && !fill_order_error && !fill_byte_valid_i;
                end
            end
        end
    end
endmodule
