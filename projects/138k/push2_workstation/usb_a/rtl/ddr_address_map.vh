`ifndef PRJ1_DDR_ADDRESS_MAP_VH
`define PRJ1_DDR_ADDRESS_MAP_VH

// Tang Mega 138K workstation DDR3 address policy.
//
// All byte addresses, sizes, counters and allocator offsets are 32-bit.
// The Gowin app_addr values count native 32-bit DQ words.  One BL8 request is
// 32 bytes, so every issued app_addr is 8-word aligned and advances by 8.
`define PRJ1_DDR_NATIVE_WORD_BYTES       32'd4
`define PRJ1_DDR_BEAT_BYTES              32'd32
`define PRJ1_DDR_APP_ADDR_STEP           29'd8
`define PRJ1_DDR_ALLOC_GRANULE_BYTES     32'h0010_0000

// Two 4-Gbit x16 devices form a 32-bit, 1-GiB physical memory.  Valid native
// word addresses keep app_addr[28] clear.
`define PRJ1_DDR_TOTAL_BYTES             32'h4000_0000
`define PRJ1_DDR_LAST_BYTE               32'h3fff_ffff
`define PRJ1_DDR_NATIVE_WORD_COUNT       32'h1000_0000
`define PRJ1_DDR_LAST_NATIVE_ADDR        29'h0fff_ffff
`define PRJ1_DDR_BEAT_COUNT              32'h0200_0000

// Startup BIST intentionally aliases the two video frames.  It runs before
// either frame becomes valid and must not be treated as a concurrent client.
`define PRJ1_DDR_BIST_BYTE_BASE          32'h0000_0000
`define PRJ1_DDR_BIST_BYTES              32'h0080_0000
`define PRJ1_DDR_BIST_APP_BASE           29'h0000_0000
`define PRJ1_DDR_BIST_BEATS              32'd262_144

// Current committed clients.
`define PRJ1_DDR_VIDEO_FRAME_BYTES       32'h0040_0000
`define PRJ1_DDR_VIDEO_FRAME_APP_WORDS   29'h0010_0000
`define PRJ1_DDR_VIDEO_FRAME0_BYTE_BASE  32'h0000_0000
`define PRJ1_DDR_VIDEO_FRAME0_BYTE_LAST  32'h003f_ffff
`define PRJ1_DDR_VIDEO_FRAME0_APP_BASE   29'h0000_0000
`define PRJ1_DDR_VIDEO_FRAME0_APP_LAST   29'h000f_ffff
`define PRJ1_DDR_VIDEO_FRAME1_BYTE_BASE  32'h0040_0000
`define PRJ1_DDR_VIDEO_FRAME1_BYTE_LAST  32'h007f_ffff
`define PRJ1_DDR_VIDEO_FRAME1_APP_BASE   29'h0010_0000
`define PRJ1_DDR_VIDEO_FRAME1_APP_LAST   29'h001f_ffff

// 8..16 MiB is the display-services reservation.  The active DSP2 control,
// descriptor and payload records live at byte 0x00800000..0x008bffff; the
// remainder stays adjacent to the two scanout pages for a third frame,
// expanded descriptors or a larger startup diagnostic.
`define PRJ1_DDR_VIDEO_GROWTH_BYTE_BASE  32'h0080_0000
`define PRJ1_DDR_VIDEO_GROWTH_BYTE_LAST  32'h00ff_ffff
`define PRJ1_DDR_DISPLAY_DATA_BYTE_BASE  32'h0080_0000
`define PRJ1_DDR_DISPLAY_DATA_BYTE_LAST  32'h008b_ffff
`define PRJ1_DDR_DISPLAY_DATA_APP_BASE   29'h0020_0000
`define PRJ1_DDR_DISPLAY_CONTROL_APP     29'h0020_0008
`define PRJ1_DDR_DISPLAY_PAYLOAD0_APP    29'h0021_0000
`define PRJ1_DDR_DISPLAY_PAYLOAD1_APP    29'h0022_0000

// Two live AE350 workstation UI pages.  Software sees byte addresses
// 0x10000000/0x10400000; gw138k_ahb_ddr converts them to the native app_addr
// values below.  Each page is a fixed 4 MiB allocation.
`define PRJ1_DDR_WORK_PAGE_BYTES         32'h0040_0000
`define PRJ1_DDR_WORK_PAGE0_BYTE_BASE    32'h0100_0000
`define PRJ1_DDR_WORK_PAGE0_BYTE_LAST    32'h013f_ffff
`define PRJ1_DDR_WORK_PAGE0_APP_BASE     29'h0040_0000
`define PRJ1_DDR_WORK_PAGE0_APP_LAST     29'h004f_ffff
`define PRJ1_DDR_WORK_PAGE1_BYTE_BASE    32'h0140_0000
`define PRJ1_DDR_WORK_PAGE1_BYTE_LAST    32'h017f_ffff
`define PRJ1_DDR_WORK_PAGE1_APP_BASE     29'h0050_0000
`define PRJ1_DDR_WORK_PAGE1_APP_LAST     29'h005f_ffff

// TF audio is a streaming two-bank ring.  Each bank is a fixed, aligned
// 64 MiB physical window; files larger than 128 MiB reuse a bank only after
// its prior beats have been copied into the playback FIFO.  The logical file
// counters remain 32-bit and never derive byte addresses from app_addr units.
`define PRJ1_DDR_AUDIO_BANK_BYTES        32'h0400_0000
`define PRJ1_DDR_AUDIO_BANK_APP_WORDS    32'h0100_0000
`define PRJ1_DDR_AUDIO_BANK_BEATS        32'h0020_0000
`define PRJ1_DDR_AUDIO_BANK0_BYTE_BASE   32'h0180_0000
`define PRJ1_DDR_AUDIO_BANK0_BYTE_LAST   32'h057f_ffff
`define PRJ1_DDR_AUDIO_BANK0_APP_BASE    29'h0060_0000
`define PRJ1_DDR_AUDIO_BANK0_APP_LAST    29'h015f_ffff
`define PRJ1_DDR_AUDIO_BANK0_LAST_BEAT   29'h015f_fff8
`define PRJ1_DDR_AUDIO_BANK1_BYTE_BASE   32'h0580_0000
`define PRJ1_DDR_AUDIO_BANK1_BYTE_LAST   32'h097f_ffff
`define PRJ1_DDR_AUDIO_BANK1_APP_BASE    29'h0160_0000
`define PRJ1_DDR_AUDIO_BANK1_APP_LAST    29'h025f_ffff
`define PRJ1_DDR_AUDIO_BANK1_LAST_BEAT   29'h025f_fff8

// Future pools are reservations, not active clients.  Allocation inside each
// pool must be recorded here in 1-MiB granules before RTL starts using it.
`define PRJ1_DDR_GROWTH_POOL_BYTE_BASE   32'h0980_0000
`define PRJ1_DDR_GROWTH_POOL_BYTE_LAST   32'h0fff_ffff
`define PRJ1_DDR_GROWTH_POOL_BYTES       32'h0680_0000
`define PRJ1_DDR_GROWTH_POOL_APP_BASE    29'h0260_0000

// Shared model/weight/activation space.  Do not split it by network layer in
// RTL; a descriptor-driven allocator can repartition it as networks evolve.
`define PRJ1_DDR_NN_POOL_BYTE_BASE       32'h1000_0000
`define PRJ1_DDR_NN_POOL_BYTE_LAST       32'h2fff_ffff
`define PRJ1_DDR_NN_POOL_BYTES           32'h2000_0000
`define PRJ1_DDR_NN_POOL_APP_BASE        29'h0400_0000

// Bulk state pool for BSRAM migration, delay/reverb histories, wave tables,
// FFT/analysis history and recording buffers.  Small latency-critical caches
// remain in BSRAM; bulk backing storage belongs here.
`define PRJ1_DDR_BULK_POOL_BYTE_BASE     32'h3000_0000
`define PRJ1_DDR_BULK_POOL_BYTE_LAST     32'h3fff_ffff
`define PRJ1_DDR_BULK_POOL_BYTES         32'h1000_0000
`define PRJ1_DDR_BULK_POOL_APP_BASE      29'h0c00_0000

// First granule of the bulk pool: the P10 delay-effect ring (Plan B BSRAM
// migration).  16384 stereo samples x 8 bytes = 128 KiB of the reserved 1 MiB;
// owner 6 of the DDR arbiter streams it sequentially through delay_ddr_dma.
`define PRJ1_DDR_DELAY_RING_BYTE_BASE    32'h3000_0000
`define PRJ1_DDR_DELAY_RING_BYTE_LAST    32'h3001_ffff
`define PRJ1_DDR_DELAY_RING_BYTES        32'h0002_0000
`define PRJ1_DDR_DELAY_RING_APP_BASE     29'h0c00_0000

// Second 1 MiB bulk granule: BLE PCM capture. Only the first 64 KiB is
// currently used (16384 stereo PCM16 frames); shared music owner arbitrates.
`define PRJ1_DDR_BLE_PCM_BYTE_BASE      32'h3010_0000
`define PRJ1_DDR_BLE_PCM_BYTE_LAST      32'h3010_ffff
`define PRJ1_DDR_BLE_PCM_APP_BASE       29'h0c04_0000

`endif
