// Scalefactor-band width tables, shared by every stage that walks bands.
//
// mp3_huffman, mp3_requant, mp3_reorder and mp3_stereo all need the same three
// tables, and each used to instantiate its own copies -- eleven ROM instances of
// three 512x8 tables. On this device BSRAM is the binding resource (35 of 46
// blocks before this change), so the duplication cost roughly eight blocks for
// nothing.
//
// One instance is safe because the stages are strictly sequential: the decoder's
// sequencer runs scalefactors, then Huffman, then requantization, then stereo,
// reorder, antialias and IMDCT, one at a time. The address is muxed by whichever
// stage is active, exactly like the mp3_spectra port mux.
//
// All three outputs are presented at once and the caller selects; that costs
// nothing extra, since a single address feeds all three and the block-type
// choice is already a mux inside each stage.
module mp3_sfbtab (
    input  wire       clk,
    input  wire [8:0] addr,
    output wire [7:0] long_q,
    output wire [7:0] short_q,
    output wire [7:0] mixed_q
);
    sync_rom #(.AW(9), .DW(8), .INIT("src/storage/tang_mp3/mp3/tables/sfb_long.memh")) u_l (
        .clk(clk), .addr(addr), .data(long_q));
    sync_rom #(.AW(9), .DW(8), .INIT("src/storage/tang_mp3/mp3/tables/sfb_short.memh")) u_s (
        .clk(clk), .addr(addr), .data(short_q));
    sync_rom #(.AW(9), .DW(8), .INIT("src/storage/tang_mp3/mp3/tables/sfb_mixed.memh")) u_m (
        .clk(clk), .addr(addr), .data(mixed_q));
endmodule
