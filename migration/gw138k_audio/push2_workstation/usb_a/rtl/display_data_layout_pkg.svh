`ifndef DISPLAY_DATA_LAYOUT_PKG_SVH
`define DISPLAY_DATA_LAYOUT_PKG_SVH
package display_data_layout_pkg;
    // Native address is a 32-bit DQ word; byte_address = word_address * 4.
    localparam logic [31:0] DISPLAY_MAGIC=32'h44535032, BLOCK_MAGIC=32'h44535042;
    localparam logic [7:0] VERSION_MAJOR=1, VERSION_MINOR=0;
    localparam logic [28:0] LEGACY_META_WORD=29'h0200000;
    localparam logic [28:0] DISPLAY_CONTROL_WORD=29'h0200008;
    localparam logic [28:0] BANK0_HEADER_WORD=29'h0200010, BANK1_HEADER_WORD=29'h0200018;
    localparam logic [28:0] DESC_BANK0_WORD=29'h0200020, DESC_BANK1_WORD=29'h0200060;
    localparam logic [28:0] PAYLOAD_BANK0_WORD=29'h0210000, PAYLOAD_BANK1_WORD=29'h0220000;
    localparam logic [28:0] PAYLOAD_BANK_STRIDE_WORDS=29'h0010000;
    localparam integer WORD_BYTES=4, BL8_WORDS=8, DESCRIPTOR_WORDS=16;
    localparam logic [31:0] SAMPLE_RATE_HZ=48000;
    localparam logic [28:0] WAVEFORM_OFFSET_WORD=0, LISSAJOUS_OFFSET_WORD=29'h200,
        SPECTRUM_OFFSET_WORD=29'ha00, EFFECT_META_OFFSET_WORD=29'hb00;
    localparam logic [7:0] BLOCK_WAVEFORM=1, BLOCK_LISSAJOUS=2, BLOCK_SPECTRUM=3, BLOCK_EFFECT_META=4;
    // Declaration is MSB-first; memory word 0 is ALWAYS bits[31:0].
    typedef struct packed {
        logic [31:0] analysis_skipped, waveform_skipped, flags, descriptor_base_word;
        logic [31:0] commit_sequence, frame_sequence, version_bank_count, magic;
    } control_record_t;
    typedef struct packed {
        logic [31:0] bank_header_word, reserved, aux1, aux0, display_gain, skipped_samples, payload_words, payload_base_word;
        logic [31:0] flags, valid_length, window_trigger, sample_rate_hz, source_sequence, frame_sequence, version_type_format, magic;
    } block_descriptor_t;
endpackage
`endif
