`include "src/memory/ddr_address_map.vh"

// Focused verification for the streaming two-bank audio DDR ring.
// The bank is scaled to 64 bytes so files larger than the 128-byte window can
// exercise real bank reclamation without a multi-million-cycle test.
module tb_tf_audio_ddr_dma;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg rst_n = 1'b0;
    reg capture_done_toggle = 1'b0;
    reg restart_toggle = 1'b0;
    reg [31:0] file_size_bytes = 32'd0;
    reg fifo_in_rd_valid = 1'b0;
    reg [7:0] fifo_in_rd_data = 8'd0;
    wire fifo_in_rd_en;
    reg stall_output = 1'b0;
    wire fifo_out_full = stall_output;
    wire fifo_out_wr_en;
    wire [7:0] fifo_out_wr_data;
    wire [2:0] app_cmd;
    wire app_en;
    wire [28:0] app_addr;
    wire [255:0] app_wdata;
    wire app_wren, app_wend;
    wire playback_start_toggle, playback_done_toggle;
    wire capacity_error, bank0_valid, bank1_valid, file_size_valid;
    wire [31:0] staged_file_size;
    reg app_rvalid = 1'b0;
    reg [255:0] app_rdata = 256'd0;

    localparam integer MAX_SOURCE = 4096;
    reg [7:0] source [0:MAX_SOURCE-1];
    integer source_len, source_index;
    wire fifo_in_empty = (source_index >= source_len);

    tf_audio_ddr_dma #(
        .AUDIO_BANK_BYTES(32'd64),
        .AUDIO_STREAM_START_BYTES(32'd32)
    ) dut (
        .clk(clk), .rst_n(rst_n), .mem_ready(1'b1),
        .capture_done_toggle(capture_done_toggle), .restart_toggle(restart_toggle),
        .file_size_bytes(file_size_bytes), .fifo_in_empty(fifo_in_empty),
        .fifo_in_rd_valid(fifo_in_rd_valid), .fifo_in_rd_data(fifo_in_rd_data),
        .fifo_in_rd_en(fifo_in_rd_en), .playback_start_toggle(playback_start_toggle),
        .playback_done_toggle(playback_done_toggle), .fifo_out_full(fifo_out_full),
        .fifo_out_wr_en(fifo_out_wr_en), .fifo_out_wr_data(fifo_out_wr_data),
        .app_cmd(app_cmd), .app_en(app_en), .app_addr(app_addr),
        .app_wdata(app_wdata), .app_rdy(1'b1), .app_wren(app_wren),
        .app_wend(app_wend), .app_wrdy(1'b1), .app_rvalid(app_rvalid),
        .app_rdata(app_rdata), .capacity_error(capacity_error),
        .bank0_valid(bank0_valid), .bank1_valid(bank1_valid),
        .file_size_valid(file_size_valid), .staged_file_size(staged_file_size)
    );

    // Metadata-only default instance verifies the real corrected map and
    // keeps the scaled traffic test independent of physical bank capacity.
    wire hw_app_rvalid = 1'b0;
    wire [255:0] hw_app_rdata = 256'd0;
    tf_audio_ddr_dma dut_hw (
        .clk(clk), .rst_n(rst_n), .mem_ready(1'b1),
        .capture_done_toggle(1'b0), .restart_toggle(1'b0),
        .file_size_bytes(32'd0), .fifo_in_empty(1'b1),
        .fifo_in_rd_valid(1'b0), .fifo_in_rd_data(8'd0), .fifo_in_rd_en(),
        .playback_start_toggle(), .playback_done_toggle(), .fifo_out_full(1'b0),
        .fifo_out_wr_en(), .fifo_out_wr_data(), .app_cmd(), .app_en(),
        .app_addr(), .app_wdata(), .app_rdy(1'b1), .app_wren(), .app_wend(),
        .app_wrdy(1'b1), .app_rvalid(hw_app_rvalid), .app_rdata(hw_app_rdata),
        .capacity_error(), .bank0_valid(), .bank1_valid(),
        .file_size_valid(), .staged_file_size()
    );

    reg read_pending = 1'b0;
    reg [28:0] read_addr_q;
    reg [255:0] read_data_q;
    reg [28:0] write_addr_log [0:4095];
    reg [255:0] write_data_log [0:4095];
    reg [28:0] read_addr_log [0:4095];
    integer write_count, read_count;
    integer output_count;
    reg [7:0] output_bytes [0:8191];
    integer j;

    // Latest-write lookup models the finite scaled DDR contents.  If the DUT
    // overwrites a beat before reading it, the output comparison catches it.
    task automatic lookup_latest;
        input [28:0] addr;
        output [255:0] data;
        integer k;
        begin
            data = 256'd0;
            for (k = 0; k < write_count; k = k + 1)
                if (write_addr_log[k] == addr)
                    data = write_data_log[k];
        end
    endtask

    always @(posedge clk) begin
        fifo_in_rd_valid <= 1'b0;
        if (fifo_in_rd_en) begin
            if (source_index >= source_len)
                $fatal(1, "DMA read past source length");
            fifo_in_rd_valid <= 1'b1;
            fifo_in_rd_data <= source[source_index];
            source_index <= source_index + 1;
        end

        app_rvalid <= 1'b0;
        if (app_en && app_wren) begin
            if (app_addr[2:0] !== 3'b000)
                $fatal(1, "write app_addr low bits are not zero: %h", app_addr);
            if (write_count >= 4096)
                $fatal(1, "write log overflow");
            write_addr_log[write_count] <= app_addr;
            write_data_log[write_count] <= app_wdata;
            write_count <= write_count + 1;
        end
        if (app_en && !app_wren) begin
            if (app_addr[2:0] !== 3'b000)
                $fatal(1, "read app_addr low bits are not zero: %h", app_addr);
            if (read_count >= 4096)
                $fatal(1, "read log overflow");
            read_addr_log[read_count] <= app_addr;
            read_count <= read_count + 1;
            read_addr_q <= app_addr;
            lookup_latest(app_addr, read_data_q);
            read_pending <= 1'b1;
        end else begin
            read_pending <= 1'b0;
        end
        if (read_pending) begin
            app_rvalid <= 1'b1;
            app_rdata <= read_data_q;
        end

        if (fifo_out_wr_en) begin
            if (output_count >= 8192)
                $fatal(1, "output log overflow");
            output_bytes[output_count] <= fifo_out_wr_data;
            output_count <= output_count + 1;
        end
    end

    task clear_logs;
        begin
            write_count = 0;
            read_count = 0;
            output_count = 0;
        end
    endtask

    task start_capture;
        input integer len;
        input integer seed;
        integer k;
        begin
            source_len = len;
            source_index = 0;
            file_size_bytes = len;
            for (k = 0; k < len; k = k + 1)
                source[k] = (seed + k) & 8'hff;
            while (source_index < len)
                @(posedge clk);
            repeat (3) @(posedge clk);
            capture_done_toggle = ~capture_done_toggle;
        end
    endtask

    task restart_epoch;
        begin
            restart_toggle = ~restart_toggle;
            repeat (6) @(posedge clk);
            clear_logs;
        end
    endtask

    task wait_done_and_check;
        input integer expected_len;
        input integer seed;
        integer timeout;
        integer k;
        begin
            timeout = 0;
            while (dut.state != 2'd2 && timeout < 200000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (timeout >= 200000)
                $fatal(1, "DMA did not finish len=%0d state=%0d", expected_len, dut.state);
            repeat (3) @(posedge clk);
            if (capacity_error !== 1'b0)
                $fatal(1, "streaming file incorrectly reported capacity_error");
            if (!file_size_valid || staged_file_size != expected_len)
                $fatal(1, "file size valid=%b size=%0d expected=%0d",
                       file_size_valid, staged_file_size, expected_len);
            if (output_count != expected_len)
                $fatal(1, "output length=%0d expected=%0d", output_count, expected_len);
            for (k = 0; k < expected_len; k = k + 1)
                if (output_bytes[k] !== ((seed + k) & 8'hff))
                    $fatal(1, "output byte %0d=%h expected=%h", k, output_bytes[k],
                           ((seed + k) & 8'hff));
        end
    endtask

    task check_ring_addresses;
        input integer expected_beats;
        integer k;
        reg [28:0] expected_addr;
        begin
            if (write_count != expected_beats || read_count != expected_beats)
                $fatal(1, "write/read count=%0d/%0d expected=%0d",
                       write_count, read_count, expected_beats);
            for (k = 0; k < expected_beats; k = k + 1) begin
                if (k % 4 == 0)
                    expected_addr = `PRJ1_DDR_AUDIO_BANK0_APP_BASE;
                else if (k % 4 == 1)
                    expected_addr = `PRJ1_DDR_AUDIO_BANK0_APP_BASE + 29'd8;
                else if (k % 4 == 2)
                    expected_addr = `PRJ1_DDR_AUDIO_BANK0_APP_BASE + 29'd16;
                else
                    expected_addr = `PRJ1_DDR_AUDIO_BANK0_APP_BASE + 29'd24;
                if (write_addr_log[k] !== expected_addr)
                    $fatal(1, "write address %0d=%h expected %h", k,
                           write_addr_log[k], expected_addr);
                if (read_addr_log[k] !== expected_addr)
                    $fatal(1, "read address %0d=%h expected %h", k,
                           read_addr_log[k], expected_addr);
            end
        end
    endtask

    initial begin
        if (dut_hw.AUDIO_BANK_BYTES !== `PRJ1_DDR_AUDIO_BANK_BYTES ||
            dut_hw.AUDIO_TOTAL_BYTES !== 32'h0800_0000 ||
            dut_hw.AUDIO_BANK0_BYTE_BASE !== `PRJ1_DDR_AUDIO_BANK0_BYTE_BASE ||
            dut_hw.AUDIO_BANK1_BYTE_BASE !== `PRJ1_DDR_AUDIO_BANK1_BYTE_BASE ||
            dut_hw.AUDIO_BANK0_NATIVE_BASE !==
                {3'd0, `PRJ1_DDR_AUDIO_BANK0_APP_BASE} ||
            dut_hw.AUDIO_BANK1_NATIVE_BASE !==
                {3'd0, `PRJ1_DDR_AUDIO_BANK1_APP_BASE})
            $fatal(1, "corrected default audio DDR map constants changed");

        source_len = 0;
        source_index = 0;
        clear_logs;
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        repeat (4) @(posedge clk);

        // Empty file remains a valid zero-length stream.
        start_capture(0, 8'h10);
        wait_done_and_check(0, 8'h10);

        // A short file occupies one padded DDR beat but emits only its seven
        // valid bytes to the decoder.
        restart_epoch;
        start_capture(7, 8'h18);
        wait_done_and_check(7, 8'h18);
        check_ring_addresses(1);

        // Exact beat and bank crossing.
        restart_epoch;
        start_capture(32, 8'h20);
        wait_done_and_check(32, 8'h20);
        check_ring_addresses(1);

        restart_epoch;
        start_capture(96, 8'h40);
        wait_done_and_check(96, 8'h40);
        check_ring_addresses(3);

        // Exactly one complete two-bank window is still legal.
        restart_epoch;
        start_capture(128, 8'h60);
        wait_done_and_check(128, 8'h60);
        check_ring_addresses(4);

        // 160 bytes is larger than the scaled 128-byte ring: bank 0 is
        // reclaimed after the first four beats and receives beat five.  The
        // temporary output stall forces the input side to exercise ring-full
        // backpressure before the reader releases the first bank.
        restart_epoch;
        stall_output = 1'b1;
        fork
            begin
                start_capture(160, 8'h80);
            end
            begin
                repeat (500) @(posedge clk);
                stall_output = 1'b0;
            end
        join
        wait_done_and_check(160, 8'h80);
        check_ring_addresses(5);

        // Two complete ring traversals verify that recycling continues.
        restart_epoch;
        start_capture(256, 8'hc0);
        wait_done_and_check(256, 8'hc0);
        check_ring_addresses(8);

        // Restart prevents the previous ring contents from appearing in a
        // new short stream.
        restart_epoch;
        start_capture(32, 8'he0);
        wait_done_and_check(32, 8'he0);
        check_ring_addresses(1);

        $display("PASS tb_tf_audio_ddr_dma: streaming ring, >128MiB scaled recycle, bank crossing, restart, address alignment");
        $finish;
    end
endmodule
