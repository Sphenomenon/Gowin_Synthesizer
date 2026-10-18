`timescale 1ns/1ps
`include "src/memory/ddr_address_map.vh"

module tb_ddr_address_map;
    ddr_address_map_guard guard();

    task check_region;
        input [31:0] byte_base;
        input [31:0] byte_last;
        input [28:0] app_base;
        begin
            if (byte_base[4:0] != 0)
                $fatal(1, "region byte base is not BL8 aligned: %h", byte_base);
            if ({3'd0, app_base} != (byte_base >> 2))
                $fatal(1, "byte/native conversion mismatch: %h -> %h",
                       byte_base, app_base);
            if (byte_last < byte_base)
                $fatal(1, "empty or wrapped region: %h..%h", byte_base, byte_last);
        end
    endtask

    initial begin
        if (`PRJ1_DDR_TOTAL_BYTES !== 32'h4000_0000 ||
            `PRJ1_DDR_LAST_NATIVE_ADDR !== 29'h0fff_ffff ||
            (`PRJ1_DDR_LAST_NATIVE_ADDR & 29'h1000_0000) != 0)
            $fatal(1, "physical 1-GiB DDR capacity changed");

        check_region(`PRJ1_DDR_VIDEO_FRAME0_BYTE_BASE,
                     `PRJ1_DDR_VIDEO_FRAME0_BYTE_LAST,
                     `PRJ1_DDR_VIDEO_FRAME0_APP_BASE);
        check_region(`PRJ1_DDR_VIDEO_FRAME1_BYTE_BASE,
                     `PRJ1_DDR_VIDEO_FRAME1_BYTE_LAST,
                     `PRJ1_DDR_VIDEO_FRAME1_APP_BASE);
        check_region(`PRJ1_DDR_DISPLAY_DATA_BYTE_BASE,
                     `PRJ1_DDR_DISPLAY_DATA_BYTE_LAST,
                     `PRJ1_DDR_DISPLAY_DATA_APP_BASE);
        check_region(`PRJ1_DDR_WORK_PAGE0_BYTE_BASE,
                     `PRJ1_DDR_WORK_PAGE0_BYTE_LAST,
                     `PRJ1_DDR_WORK_PAGE0_APP_BASE);
        check_region(`PRJ1_DDR_WORK_PAGE1_BYTE_BASE,
                     `PRJ1_DDR_WORK_PAGE1_BYTE_LAST,
                     `PRJ1_DDR_WORK_PAGE1_APP_BASE);
        check_region(`PRJ1_DDR_AUDIO_BANK0_BYTE_BASE,
                     `PRJ1_DDR_AUDIO_BANK0_BYTE_LAST,
                     `PRJ1_DDR_AUDIO_BANK0_APP_BASE);
        check_region(`PRJ1_DDR_AUDIO_BANK1_BYTE_BASE,
                     `PRJ1_DDR_AUDIO_BANK1_BYTE_LAST,
                     `PRJ1_DDR_AUDIO_BANK1_APP_BASE);
        check_region(`PRJ1_DDR_GROWTH_POOL_BYTE_BASE,
                     `PRJ1_DDR_GROWTH_POOL_BYTE_LAST,
                     `PRJ1_DDR_GROWTH_POOL_APP_BASE);
        check_region(`PRJ1_DDR_NN_POOL_BYTE_BASE,
                     `PRJ1_DDR_NN_POOL_BYTE_LAST,
                     `PRJ1_DDR_NN_POOL_APP_BASE);
        check_region(`PRJ1_DDR_BULK_POOL_BYTE_BASE,
                     `PRJ1_DDR_BULK_POOL_BYTE_LAST,
                     `PRJ1_DDR_BULK_POOL_APP_BASE);

        if (`PRJ1_DDR_BIST_BYTES !==
                (`PRJ1_DDR_VIDEO_FRAME_BYTES + `PRJ1_DDR_VIDEO_FRAME_BYTES) ||
            `PRJ1_DDR_AUDIO_BANK0_BYTE_LAST + 32'd1 !==
                `PRJ1_DDR_AUDIO_BANK1_BYTE_BASE ||
            `PRJ1_DDR_AUDIO_BANK1_BYTE_LAST + 32'd1 !==
                `PRJ1_DDR_GROWTH_POOL_BYTE_BASE ||
            `PRJ1_DDR_GROWTH_POOL_BYTE_LAST + 32'd1 !==
                `PRJ1_DDR_NN_POOL_BYTE_BASE ||
            `PRJ1_DDR_NN_POOL_BYTE_LAST + 32'd1 !==
                `PRJ1_DDR_BULK_POOL_BYTE_BASE ||
            `PRJ1_DDR_BULK_POOL_BYTE_LAST !== `PRJ1_DDR_LAST_BYTE)
            $fatal(1, "DDR region ordering or coverage changed");

        if (`PRJ1_DDR_NN_POOL_BYTES !== 32'h2000_0000 ||
            `PRJ1_DDR_BULK_POOL_BYTES !== 32'h1000_0000 ||
            `PRJ1_DDR_GROWTH_POOL_BYTES !== 32'h0680_0000)
            $fatal(1, "future pool capacities changed");

        if (`PRJ1_DDR_DISPLAY_CONTROL_APP !== 29'h0200008 ||
            `PRJ1_DDR_DISPLAY_PAYLOAD0_APP !== 29'h0210000 ||
            `PRJ1_DDR_DISPLAY_PAYLOAD1_APP !== 29'h0220000)
            $fatal(1, "workstation DSP2 display ABI moved outside the map");

        $display("PASS tb_ddr_address_map: 1-GiB byte/native map, fixed clients, future NN/bulk pools");
        $finish;
    end
endmodule
