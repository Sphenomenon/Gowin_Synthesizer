`default_nettype none
`include "src/memory/ddr_address_map.vh"

// Elaboration-only address policy checks.  Each deliberately undefined cell
// is instantiated only when a map invariant is broken, turning overlap,
// alignment or capacity mistakes into a compile/synthesis error.
module ddr_address_map_guard;
    localparam [31:0] VIDEO_END_EXCL =
        `PRJ1_DDR_VIDEO_FRAME1_BYTE_LAST + 32'd1;
    localparam [31:0] VIDEO_GROWTH_END_EXCL =
        `PRJ1_DDR_VIDEO_GROWTH_BYTE_LAST + 32'd1;
    localparam [31:0] WORK0_END_EXCL =
        `PRJ1_DDR_WORK_PAGE0_BYTE_LAST + 32'd1;
    localparam [31:0] WORK1_END_EXCL =
        `PRJ1_DDR_WORK_PAGE1_BYTE_LAST + 32'd1;
    localparam [31:0] AUDIO0_END_EXCL =
        `PRJ1_DDR_AUDIO_BANK0_BYTE_LAST + 32'd1;
    localparam [31:0] AUDIO1_END_EXCL =
        `PRJ1_DDR_AUDIO_BANK1_BYTE_LAST + 32'd1;
    localparam [31:0] GROWTH_END_EXCL =
        `PRJ1_DDR_GROWTH_POOL_BYTE_LAST + 32'd1;
    localparam [31:0] NN_END_EXCL =
        `PRJ1_DDR_NN_POOL_BYTE_LAST + 32'd1;

    generate
        if (`PRJ1_DDR_BLE_PCM_APP_BASE != (`PRJ1_DDR_BLE_PCM_BYTE_BASE >> 2) ||
            (`PRJ1_DDR_BLE_PCM_BYTE_BASE & 32'h000f_ffff) != 0 ||
            `PRJ1_DDR_BLE_PCM_BYTE_BASE <= `PRJ1_DDR_DELAY_RING_BYTE_LAST ||
            `PRJ1_DDR_BLE_PCM_BYTE_LAST > `PRJ1_DDR_BULK_POOL_BYTE_LAST ||
            `PRJ1_DDR_BLE_PCM_BYTE_LAST - `PRJ1_DDR_BLE_PCM_BYTE_BASE != 65535) begin: g_bad_ble_pcm
            PRJ1_DDR_MAP_ERROR_BLE_PCM_RESERVATION invalid();
        end
        if (`PRJ1_DDR_NATIVE_WORD_COUNT !=
            (`PRJ1_DDR_TOTAL_BYTES >> 2)) begin : g_bad_capacity_ratio
            PRJ1_DDR_MAP_ERROR_CAPACITY_RATIO invalid();
        end
        if (`PRJ1_DDR_BIST_BYTE_BASE !=
            `PRJ1_DDR_VIDEO_FRAME0_BYTE_BASE ||
            `PRJ1_DDR_BIST_BYTES != VIDEO_END_EXCL) begin : g_bad_bist_alias
            PRJ1_DDR_MAP_ERROR_BIST_ALIAS invalid();
        end
        if (`PRJ1_DDR_BIST_BEATS * `PRJ1_DDR_BEAT_BYTES !=
                `PRJ1_DDR_BIST_BYTES ||
            `PRJ1_DDR_VIDEO_FRAME0_BYTE_LAST -
                `PRJ1_DDR_VIDEO_FRAME0_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_VIDEO_FRAME_BYTES ||
            `PRJ1_DDR_VIDEO_FRAME1_BYTE_LAST -
                `PRJ1_DDR_VIDEO_FRAME1_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_VIDEO_FRAME_BYTES ||
            `PRJ1_DDR_WORK_PAGE0_BYTE_LAST -
                `PRJ1_DDR_WORK_PAGE0_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_WORK_PAGE_BYTES ||
            `PRJ1_DDR_WORK_PAGE1_BYTE_LAST -
                `PRJ1_DDR_WORK_PAGE1_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_WORK_PAGE_BYTES ||
            `PRJ1_DDR_AUDIO_BANK0_BYTE_LAST -
                `PRJ1_DDR_AUDIO_BANK0_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_AUDIO_BANK_BYTES ||
            `PRJ1_DDR_AUDIO_BANK1_BYTE_LAST -
                `PRJ1_DDR_AUDIO_BANK1_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_AUDIO_BANK_BYTES ||
            `PRJ1_DDR_GROWTH_POOL_BYTE_LAST -
                `PRJ1_DDR_GROWTH_POOL_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_GROWTH_POOL_BYTES ||
            `PRJ1_DDR_NN_POOL_BYTE_LAST -
                `PRJ1_DDR_NN_POOL_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_NN_POOL_BYTES ||
            `PRJ1_DDR_BULK_POOL_BYTE_LAST -
                `PRJ1_DDR_BULK_POOL_BYTE_BASE + 32'd1 !=
                `PRJ1_DDR_BULK_POOL_BYTES) begin : g_bad_size
            PRJ1_DDR_MAP_ERROR_REGION_SIZE invalid();
        end
        if (`PRJ1_DDR_VIDEO_FRAME0_BYTE_LAST + 32'd1 !=
            `PRJ1_DDR_VIDEO_FRAME1_BYTE_BASE ||
            VIDEO_END_EXCL > `PRJ1_DDR_VIDEO_GROWTH_BYTE_BASE ||
            VIDEO_GROWTH_END_EXCL > `PRJ1_DDR_WORK_PAGE0_BYTE_BASE ||
            WORK0_END_EXCL > `PRJ1_DDR_WORK_PAGE1_BYTE_BASE ||
            WORK1_END_EXCL > `PRJ1_DDR_AUDIO_BANK0_BYTE_BASE ||
            AUDIO0_END_EXCL > `PRJ1_DDR_AUDIO_BANK1_BYTE_BASE ||
            AUDIO1_END_EXCL > `PRJ1_DDR_GROWTH_POOL_BYTE_BASE ||
            GROWTH_END_EXCL > `PRJ1_DDR_NN_POOL_BYTE_BASE ||
            NN_END_EXCL > `PRJ1_DDR_BULK_POOL_BYTE_BASE ||
            `PRJ1_DDR_BULK_POOL_BYTE_LAST != `PRJ1_DDR_LAST_BYTE) begin : g_bad_order
            PRJ1_DDR_MAP_ERROR_OVERLAP_OR_GAP invalid();
        end
        if ((`PRJ1_DDR_VIDEO_FRAME0_BYTE_BASE & 32'h0000_001f) != 0 ||
            (`PRJ1_DDR_VIDEO_FRAME1_BYTE_BASE & 32'h0000_001f) != 0 ||
            (`PRJ1_DDR_WORK_PAGE0_BYTE_BASE & 32'h0000_001f) != 0 ||
            (`PRJ1_DDR_WORK_PAGE1_BYTE_BASE & 32'h0000_001f) != 0 ||
            (`PRJ1_DDR_AUDIO_BANK0_BYTE_BASE & 32'h0000_001f) != 0 ||
            (`PRJ1_DDR_AUDIO_BANK1_BYTE_BASE & 32'h0000_001f) != 0 ||
            (`PRJ1_DDR_GROWTH_POOL_BYTE_BASE & 32'h0000_001f) != 0 ||
            (`PRJ1_DDR_NN_POOL_BYTE_BASE & 32'h0000_001f) != 0 ||
            (`PRJ1_DDR_BULK_POOL_BYTE_BASE & 32'h0000_001f) != 0) begin : g_bad_alignment
            PRJ1_DDR_MAP_ERROR_ALIGNMENT invalid();
        end
        if (`PRJ1_DDR_VIDEO_FRAME0_APP_BASE !=
                (`PRJ1_DDR_VIDEO_FRAME0_BYTE_BASE >> 2) ||
            `PRJ1_DDR_VIDEO_FRAME1_APP_BASE !=
                (`PRJ1_DDR_VIDEO_FRAME1_BYTE_BASE >> 2) ||
            `PRJ1_DDR_DISPLAY_DATA_APP_BASE !=
                (`PRJ1_DDR_DISPLAY_DATA_BYTE_BASE >> 2) ||
            `PRJ1_DDR_WORK_PAGE0_APP_BASE !=
                (`PRJ1_DDR_WORK_PAGE0_BYTE_BASE >> 2) ||
            `PRJ1_DDR_WORK_PAGE1_APP_BASE !=
                (`PRJ1_DDR_WORK_PAGE1_BYTE_BASE >> 2) ||
            `PRJ1_DDR_AUDIO_BANK0_APP_BASE !=
                (`PRJ1_DDR_AUDIO_BANK0_BYTE_BASE >> 2) ||
            `PRJ1_DDR_AUDIO_BANK1_APP_BASE !=
                (`PRJ1_DDR_AUDIO_BANK1_BYTE_BASE >> 2) ||
            `PRJ1_DDR_GROWTH_POOL_APP_BASE !=
                (`PRJ1_DDR_GROWTH_POOL_BYTE_BASE >> 2) ||
            `PRJ1_DDR_NN_POOL_APP_BASE !=
                (`PRJ1_DDR_NN_POOL_BYTE_BASE >> 2) ||
            `PRJ1_DDR_BULK_POOL_APP_BASE !=
                (`PRJ1_DDR_BULK_POOL_BYTE_BASE >> 2)) begin : g_bad_conversion
            PRJ1_DDR_MAP_ERROR_BYTE_NATIVE_CONVERSION invalid();
        end
        if (`PRJ1_DDR_VIDEO_FRAME0_APP_LAST !=
                (`PRJ1_DDR_VIDEO_FRAME0_BYTE_LAST >> 2) ||
            `PRJ1_DDR_VIDEO_FRAME1_APP_LAST !=
                (`PRJ1_DDR_VIDEO_FRAME1_BYTE_LAST >> 2) ||
            `PRJ1_DDR_WORK_PAGE0_APP_LAST !=
                (`PRJ1_DDR_WORK_PAGE0_BYTE_LAST >> 2) ||
            `PRJ1_DDR_WORK_PAGE1_APP_LAST !=
                (`PRJ1_DDR_WORK_PAGE1_BYTE_LAST >> 2) ||
            `PRJ1_DDR_AUDIO_BANK0_APP_LAST !=
                (`PRJ1_DDR_AUDIO_BANK0_BYTE_LAST >> 2) ||
            `PRJ1_DDR_AUDIO_BANK1_APP_LAST !=
                (`PRJ1_DDR_AUDIO_BANK1_BYTE_LAST >> 2)) begin : g_bad_last_conversion
            PRJ1_DDR_MAP_ERROR_LAST_CONVERSION invalid();
        end
        if ((`PRJ1_DDR_AUDIO_BANK0_APP_LAST & 29'd7) != 29'd7 ||
            (`PRJ1_DDR_AUDIO_BANK1_APP_LAST & 29'd7) != 29'd7 ||
            (`PRJ1_DDR_AUDIO_BANK0_LAST_BEAT & 29'd7) != 29'd0 ||
            (`PRJ1_DDR_AUDIO_BANK1_LAST_BEAT & 29'd7) != 29'd0) begin : g_bad_last_beat
            PRJ1_DDR_MAP_ERROR_LAST_BEAT invalid();
        end
        if (`PRJ1_DDR_DISPLAY_DATA_BYTE_BASE <
                `PRJ1_DDR_VIDEO_GROWTH_BYTE_BASE ||
            `PRJ1_DDR_DISPLAY_DATA_BYTE_LAST >
                `PRJ1_DDR_VIDEO_GROWTH_BYTE_LAST ||
            (`PRJ1_DDR_DISPLAY_CONTROL_APP & 29'd7) != 0 ||
            (`PRJ1_DDR_DISPLAY_PAYLOAD0_APP & 29'd7) != 0 ||
            (`PRJ1_DDR_DISPLAY_PAYLOAD1_APP & 29'd7) != 0) begin : g_bad_display_reservation
            PRJ1_DDR_MAP_ERROR_DISPLAY_RESERVATION invalid();
        end
    endgenerate
endmodule
`default_nettype wire
