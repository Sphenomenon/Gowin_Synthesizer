`ifndef DISPLAY_DATA_LAYOUT_PKG_SVH
`define DISPLAY_DATA_LAYOUT_PKG_SVH

// v1 layout only; not instantiated by the current P10 build.
package display_data_layout_pkg;
    localparam logic [31:0] DISPLAY_MAGIC = 32'h44535032; // "DSP2"
    localparam int VERSION_MAJOR = 1;
    localparam int VERSION_MINOR = 0;
    localparam int WORD_BYTES = 4;
    localparam int BL8_WORDS = 8;

    localparam logic [28:0] DISPLAY_CONTROL_WORD = 29'h00200000;
    localparam logic [28:0] DESC_BANK0_WORD = 29'h00200008;
    localparam logic [28:0] DESC_BANK1_WORD = 29'h00200048;
    localparam logic [28:0] PAYLOAD_BANK0_WORD = 29'h00210000;
    localparam logic [28:0] PAYLOAD_BANK1_WORD = 29'h00220000;
    localparam logic [28:0] PAYLOAD_BANK_STRIDE_WORDS = 29'h00010000;

    localparam logic [7:0] BLOCK_WAVEFORM = 8'd1;
    localparam logic [7:0] BLOCK_LISSAJOUS = 8'd2;
    localparam logic [7:0] BLOCK_SPECTRUM = 8'd3;
    localparam logic [7:0] BLOCK_EFFECT_META = 8'd4;

    localparam logic [28:0] WAVEFORM_OFFSET_WORD = 29'h00000000;
    localparam logic [28:0] LISSAJOUS_OFFSET_WORD = 29'h00000200;
    localparam logic [28:0] SPECTRUM_OFFSET_WORD = 29'h00000A00;
    localparam logic [28:0] EFFECT_META_OFFSET_WORD = 29'h00000B00;

    typedef struct packed {
        logic [31:0] magic;
        logic [7:0] version_minor;
        logic [7:0] version_major;
        logic [7:0] descriptor_words;
        logic [7:0] committed_bank;
        logic [31:0] frame_sequence;
        logic [31:0] commit_sequence;
        logic [31:0] descriptor_base_word;
        logic [31:0] flags;
        logic [63:0] reserved;
    } control_record_t;

    typedef struct packed {
        logic [31:0] type_format_flags;
        logic [31:0] frame_sequence;
        logic [31:0] source_sequence;
        logic [31:0] valid_length;
        logic [31:0] payload_base_word;
        logic [31:0] payload_words;
        logic [31:0] sample_rate_hz;
        logic [31:0] window_trigger;
    } block_descriptor_t;
endpackage
`endif
