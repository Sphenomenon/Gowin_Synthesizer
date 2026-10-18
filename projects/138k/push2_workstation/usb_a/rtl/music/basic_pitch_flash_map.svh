`ifndef BASIC_PITCH_FLASH_MAP_SVH
`define BASIC_PITCH_FLASH_MAP_SVH
// Sector-aligned model partition; leave 0..0x005fffff for FPGA configuration.
// Image builder rejects overlap, overflow and incompatible model word counts.
`define BP_FLASH_MODEL_BYTE_BASE 24'h60_0000
`define BP_FLASH_MODEL_WORDS 52239
`define BP_FLASH_MODEL_HEADER_BYTES 32
`define BP_FLASH_CAPACITY_BYTES 32'h0100_0000
`endif
