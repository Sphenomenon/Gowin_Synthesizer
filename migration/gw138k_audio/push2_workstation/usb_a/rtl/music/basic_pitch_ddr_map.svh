`ifndef BASIC_PITCH_DDR_MAP_SVH
`define BASIC_PITCH_DDR_MAP_SVH

// Basic Pitch allocations.  CNN activations belong to the shared NN pool;
// non-latency-critical DP/history state belongs to the bulk pool.
// The parent's first BULK granule (0x3000_0000) is reserved for the delay ring.
// Keep DP backpointers in a separate granule: sharing 0x3000_0000 silently
// corrupts traceback while owner 6 streams delay samples.
// The parent map allocates in 1-MiB granules.  Native DDR app_addr values are
// 32-bit-word addresses; the adapter converts these byte addresses and aligns
// every command to one 32-byte BL8 beat.
`define BP_DDR_BPTR_BYTE_BASE       32'h3040_0000
`define BP_DDR_NOTE_BYTE_BASE       32'h3010_0000
`define BP_DDR_ONSET_BYTE_BASE      32'h3020_0000
`define BP_DDR_NN_ACT_BYTE_BASE     32'h1000_0000
`define BP_DDR_NN_MODEL_BYTE_BASE   32'h1010_0000
`define BP_DDR_NN_NOTES_BYTE_BASE   32'h1020_0000
`define BP_DDR_NN_ONSET_BYTE_BASE   32'h1030_0000
`define BP_DDR_NN_CONTOUR_BYTE_BASE 32'h1040_0000
`define BP_DDR_NN_REDUCE_BYTE_BASE  32'h1050_0000
`define BP_DDR_NN_NOTE_POST_BYTE_BASE 32'h1060_0000
`define BP_DDR_NN_ONSET_POST_BYTE_BASE 32'h1070_0000
`define BP_DDR_CQT_SIGNAL_BYTE_BASE 32'h1080_0000
`define BP_DDR_ANALYSIS_BYTE_BASE   32'h3030_0000
`define BP_DDR_REGION_BYTES         32'h0010_0000
`define BP_DDR_LAST_BYTE            32'h304f_ffff

`endif
