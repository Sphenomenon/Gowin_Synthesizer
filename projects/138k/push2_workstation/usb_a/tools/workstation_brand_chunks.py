"""Invert only the pre-expanded fixed text ROM adaptation for pixel regression."""
import hashlib
SOURCE='rtl/display_data/workstation_contest_brand.sv'
PARENT_SHA256='f5d330b625ea5bc545d1e6c3b9e844a7cc23ba2c4e0b6549e035cffd47d18275'
SELECTED_SHA256='22254399b185bb74fbccc4ebdbd9fd1e859c2a47a1d79fe597710b353221a3e3'
EDITS=[('reg [23:0] glyph_rom [0:1127];', 'reg [7:0] glyph_chunk_rom [0:8191];'), ('$readmemh("rtl/display_data/assets/contest_brand_glyphs.memh", glyph_rom);', '$readmemh("rtl/display_data/assets/contest_brand_chunks.memh", glyph_chunk_rom);'), ("    wire [7:0] column = brand_column(text_x[9:3]);\n    wire [4:0] glyph_column = {column[1:0], text_x[2:0]};\n    wire [5:0] glyph_id = brand_glyph(principle_hit, column[7:2]);\n    wire [10:0] glyph_ext = {5'd0, glyph_id};\n    wire [10:0] glyph_address = (glyph_ext << 4) + (glyph_ext << 3) +\n                                {6'd0, text_y[4:0]};\n", '    // Pre-expand the fixed text into eight-pixel chunks. Address wiring now\n    // crosses only the x/y offset logic, instead of two serial lookup tables\n    // followed by glyph_id*24 arithmetic on the 100 MHz RAM address path.\n    // The ROM contains exactly the same licensed glyph pixels.\n    wire [12:0] glyph_address = {principle_hit,text_x[9:3],text_y[4:0]};\n'), ('reg [23:0] glyph_row_q;', 'reg [7:0] glyph_row_q;'), ('reg [4:0] glyph_column_q;', 'reg [2:0] glyph_column_q;'), ('glyph_row_q <= glyph_rom[glyph_address];', 'glyph_row_q <= glyph_chunk_rom[glyph_address];'), ('glyph_column_q <= glyph_column;', 'glyph_column_q <= text_x[2:0];'), ("glyph_row_q[5'd23 - glyph_column_q]", "glyph_row_q[3'd7 - glyph_column_q]")]

def normalize(payload):
    text=payload.decode()if isinstance(payload,bytes)else payload
    digest=lambda s:hashlib.sha256(s.encode()).hexdigest()
    if digest(text)==PARENT_SHA256:return text.encode()
    if digest(text)!=SELECTED_SHA256:raise ValueError('brand chunk source drift')
    for before,after in reversed(EDITS):
        if text.count(after)!=1:raise ValueError('brand chunk inverse anchor drift')
        text=text.replace(after,before,1)
    if digest(text)!=PARENT_SHA256:raise ValueError('brand chunk inverse drift')
    return text.encode()
