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
    wire [10:0] text_x = pixel_x - 11'd400;
    wire [10:0] text_y = pixel_y - (principle_hit ? 11'd64 : 11'd24);
    wire [7:0] column = brand_column(text_x[9:3]);
    wire [4:0] glyph_column = {column[1:0], text_x[2:0]};
    wire [5:0] glyph_id = brand_glyph(principle_hit, column[7:2]);
    wire [10:0] glyph_ext = {5'd0, glyph_id};
    wire [10:0] glyph_address = (glyph_ext << 4) + (glyph_ext << 3) +
                                {6'd0, text_y[4:0]};

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
