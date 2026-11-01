`timescale 1ns/1ps
// Official contest identification. Artwork/source notices live beside the ROMs.
// Every enabled input is returned one enabled rising edge later. Disabled cycles
// hold all pipeline state with the parent raster. No audio scheduling dependency.
module workstation_contest_brand (
    input wire clk,
    input wire enable,
    input wire [10:0] pixel_x,
    input wire [10:0] pixel_y,
    output reg hit,
    output reg [23:0] pixel_rgb
);
    `include "rtl/display_data/assets/contest_brand_layout.svh"

    (* rom_style="block", syn_romstyle="block_rom" *) reg [3:0] logo_rom [0:11359];
    (* rom_style="block", syn_romstyle="block_rom" *) reg [23:0] glyph_rom [0:1127];
    initial begin
        $readmemh("rtl/display_data/assets/contest_brand_logo_pairs.memh", logo_rom);
        $readmemh("rtl/display_data/assets/contest_brand_glyphs.memh", glyph_rom);
    end

    wire logo_hit = pixel_x >= 11'd64 && pixel_x < 11'd347 &&
                    pixel_y >= 11'd24 && pixel_y < 11'd104;
    wire title_hit = pixel_x >= 11'd400 && pixel_x < 11'd1384 &&
                     pixel_y >= 11'd24 && pixel_y < 11'd48;
    wire principle_hit = pixel_x >= 11'd400 && pixel_x < 11'd856 &&
                         pixel_y >= 11'd64 && pixel_y < 11'd88;
    wire text_hit = title_hit || principle_hit;
    wire [10:0] logo_x = pixel_x - 11'd64;
    wire [10:0] logo_y = pixel_y - 11'd24;
    // 142 pairs/row = 128 + 8 + 4 + 2. Widths explicitly contain the sum.
    wire [13:0] logo_y_ext = {7'd0, logo_y[6:0]};
    wire [13:0] logo_address = (logo_y_ext << 7) + (logo_y_ext << 3) +
                               (logo_y_ext << 2) + (logo_y_ext << 1) +
                               {6'd0, logo_x[8:1]};
    // Compose the existing layout functions at elaboration, before the live
    // address path. Text starts at x=400=50*8; the seven chunk bits wrap at
    // 1024 exactly like the old (pixel_x-400)[9:3]. Both visible text rows
    // have a fixed pixel_y[6], so line selection needs no rectangle decode.
    function automatic [9:0] glyph_decode_entry(input [7:0] absolute_chunk);
        reg [7:0] column;
        reg [5:0] glyph;
        reg [7:0] groups;
        begin
            column = brand_column(absolute_chunk[6:0] - 7'd50);
            glyph = brand_glyph(absolute_chunk[7], column[7:2]);
            groups = {2'd0,glyph} + ({2'd0,glyph} << 1);
            glyph_decode_entry = {groups,column[1:0]};
        end
    endfunction
    wire [9:0] glyph_decode_rows [0:255];
    generate for (genvar chunk=0; chunk<256; chunk=chunk+1) begin : g_glyph_decode
        assign glyph_decode_rows[chunk] = glyph_decode_entry(8'(chunk));
    end endgenerate
    wire [9:0] glyph_decode = glyph_decode_rows[{pixel_y[6],pixel_x[9:3]}];
    wire [4:0] glyph_column = {glyph_decode[1:0],pixel_x[2:0]};
    // glyph*24+row = {glyph*3+row[4:3],row[2:0]}. The row origins
    // (24 and 64) are multiples of eight; only a two-bit row group changes.
    // This leaves one eight-bit add instead of serial eleven-bit adds.
    wire [1:0] glyph_row_eighth = pixel_y[6] ? pixel_y[4:3] : pixel_y[4:3]+2'd1;
    wire [7:0] glyph_row_group = glyph_decode[9:2] + {6'd0,glyph_row_eighth};
    wire [10:0] glyph_address = {glyph_row_group,pixel_y[2:0]};

    reg logo_valid_q, text_valid_q, logo_odd_q;
    reg [3:0] logo_pair_q;
    reg [23:0] glyph_row_q;
    reg [4:0] glyph_column_q;
    always @(posedge clk) begin
        if (enable) begin
            logo_valid_q <= logo_hit;
            text_valid_q <= text_hit;
            if (logo_hit) begin
                logo_pair_q <= logo_rom[logo_address];
                logo_odd_q <= logo_x[0];
            end
            if (text_hit) begin
                glyph_row_q <= glyph_rom[glyph_address];
                glyph_column_q <= glyph_column;
            end
        end
    end

    // The only unregistered operations after the synchronous ROMs are a
    // four-entry palette and selection of one bit from a 24-bit glyph row.
    always @* begin
        hit = logo_valid_q || text_valid_q;
        pixel_rgb = 24'hFFFFFF;
        if (logo_valid_q)
            pixel_rgb = brand_palette(logo_odd_q ? logo_pair_q[3:2] : logo_pair_q[1:0]);
        else if (text_valid_q && glyph_row_q[5'd23 - glyph_column_q])
            pixel_rgb = 24'h2C343F;
    end
endmodule
