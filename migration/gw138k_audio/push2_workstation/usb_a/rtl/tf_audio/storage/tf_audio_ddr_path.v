// Streaming audio path: TF stream -> DDR ring -> selected decoder -> PCM16.
// This path is intentionally single-track for bring-up; the top-level default
// selects track 0, while restart/track_index are available for clean recapture.
module tf_audio_ddr_path #(
    parameter [23:0] FILE_EXT = "WAV",
    parameter integer AUDIO_KIND = 2       // 1=MP3, 2=WAV, 3=FLAC
) (
    input  wire        clk_50m,
    input  wire        reset_n,
    input  wire        restart,
    input  wire [3:0]  track_index,
    input  wire        memory_clk,
    input  wire        memory_reset_n,
    input  wire        memory_ready,
    input  wire        sample_tick,
    input  wire        sd_miso,
    output wire        sd_cs_n,
    output wire        sd_sck,
    output wire        sd_mosi,
    output wire [1:0]  card_type,
    output wire [3:0]  card_stat,
    output wire [1:0]  filesystem_type,
    output wire [2:0]  filesystem_stat,
    output wire        scan_done,
    output wire        card_ready,
    output wire        playing,
    output wire        eof,
    output wire [4:0]  track_count,
    output wire        format_ready,
    output wire        unsupported,
    output wire        audio_ddr_error,
    output wire        audio_bank0_valid,
    output wire        audio_bank1_valid,
    output wire [31:0] audio_file_size,
    output wire [19:0] sample_rate_hz,
    output wire        stereo,
    output wire [5:0]  bits_per_sample,
    output wire        pcm_valid,
    input  wire        pcm_ready,
    output wire signed [15:0] pcm_left,
    output wire signed [15:0] pcm_right,
    output wire [15:0] frame_count,
    output wire [15:0] resync_count,
    output wire [15:0] skipped_frames,
    output wire [15:0] stuck_frames,
    output wire [15:0] pcm_fifo_parity_errors,
    output wire [7:0]  debug_cmdrsp,
    output wire [7:0]  debug_rwrsp,
    output wire [3:0]  debug_cardstate,
    output wire        debug_spidone,
    output wire        debug_rvalid_session,
    output wire [2:0]  app_cmd,
    output wire        app_en,
    output wire [28:0] app_addr,
    output wire [255:0] app_wdata,
    input  wire        app_rdy,
    output wire        app_wren,
    output wire        app_wend,
    input  wire        app_wrdy,
    input  wire        app_rvalid,
    input  wire [255:0] app_rdata
);
    wire file_valid;
    wire [7:0] file_byte;
    wire raw_eof;
    wire raw_sector_allow;
    wire raw_track_start;
    wire [7:0] reader_debug_cmdrsp, reader_debug_rwrsp;
    wire [3:0] reader_debug_cardstate;
    reg raw_started;
    reg raw_track_start_r;
    reg [31:0] captured_bytes;
    reg [31:0] file_size_latched;
    reg capture_done_toggle;
    reg restart_toggle;
    reg [3:0] track_index_q;
    reg restart_q;
    reg capture_switch_hold;
    reg capture_switch_seen_low;
    wire track_change = (track_index != track_index_q);
    wire soft_restart = (restart && !restart_q) | track_change;

    assign raw_track_start = raw_track_start_r;
    assign card_ready = (card_stat == 4'd8) || (card_stat == 4'd9);

    tf_sd_file_reader #(
        .EXT              (FILE_EXT),
        .SPI_CLK_DIV      (100),
        .SPI_CLK_DIV_FAST (12)
    ) u_file_reader (
        .rstn            (reset_n),
        .clk             (clk_50m),
        .spi_ssn         (sd_cs_n),
        .spi_sck         (sd_sck),
        .spi_mosi        (sd_mosi),
        .spi_miso        (sd_miso),
        .card_type       (card_type),
        .card_stat       (card_stat),
        .filesystem_type (filesystem_type),
        .filesystem_stat (filesystem_stat),
        .scan_done       (scan_done),
        .track_count     (track_count),
        .track_index     (track_index),
        .track_start     (raw_track_start),
        .playing         (playing),
        .eof             (raw_eof),
        .sector_allow    (raw_sector_allow),
        .outen           (file_valid),
        .outbyte         (file_byte),
        .name_raddr      (8'd0),
        .name_rdata      (),
        .debug_cmdrsp    (reader_debug_cmdrsp),
        .debug_rwrsp     (reader_debug_rwrsp),
        .debug_cardstate (reader_debug_cardstate),
        .debug_spidone   (),
        .debug_rvalid_session()
    );

    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            raw_started <= 1'b0;
            raw_track_start_r <= 1'b0;
            captured_bytes <= 32'd0;
            file_size_latched <= 32'd0;
            capture_done_toggle <= 1'b0;
            restart_toggle <= 1'b0;
            track_index_q <= track_index;
            restart_q <= 1'b0;
            capture_switch_hold <= 1'b0;
            capture_switch_seen_low <= 1'b0;
        end else begin
            raw_track_start_r <= 1'b0;
            track_index_q <= track_index;
            restart_q <= restart;
            if (soft_restart) begin
                raw_started <= 1'b0;
                captured_bytes <= 32'd0;
                file_size_latched <= 32'd0;
                restart_toggle <= ~restart_toggle;
                capture_switch_hold <= 1'b1;
                capture_switch_seen_low <= 1'b0;
            end else begin
                if (!raw_started && scan_done && track_count != 0) begin
                    raw_started <= 1'b1;
                    raw_track_start_r <= 1'b1;
                end
                if (file_valid && !capture_switch_hold)
                    captured_bytes <= captured_bytes + 1'b1;
                if (raw_eof && !capture_switch_hold) begin
                    file_size_latched <= captured_bytes + (file_valid ? 32'd1 : 32'd0);
                    capture_done_toggle <= ~capture_done_toggle;
                end
                if (capture_switch_hold) begin
                    if (!playing)
                        capture_switch_seen_low <= 1'b1;
                    else if (capture_switch_seen_low && raw_started)
                        capture_switch_hold <= 1'b0;
                end
            end
        end
    end

    wire in_full, in_empty, in_rd_en, in_rd_valid;
    wire [12:0] in_wr_count, in_rd_count;
    wire in_space_ok;
    wire [7:0] in_rd_data;
    wire dma_capacity_error, dma_bank0_valid, dma_bank1_valid;
    wire dma_file_size_valid;
    wire [31:0] dma_file_size;
    tf_async_byte_fifo #(.ADDR_WIDTH(12)) u_capture_fifo (
        .wr_clk       (clk_50m),
        .wr_rst_n     (reset_n),
        .clear_toggle (restart_toggle),
        .wr_en        (file_valid && !capture_switch_hold),
        .wr_data      (file_byte),
        .wr_full      (in_full),
        .wr_count     (in_wr_count),
        .wr_space_ok  (in_space_ok),
        .rd_clk       (memory_clk),
        .rd_rst_n     (memory_reset_n),
        .rd_en        (in_rd_en),
        .rd_data      (in_rd_data),
        .rd_valid     (in_rd_valid),
        .rd_empty     (in_empty),
        .rd_count     (in_rd_count)
    );
    assign raw_sector_allow = in_space_ok;

    wire out_full, out_empty, out_rd_en, out_rd_valid;
    wire [12:0] out_wr_count, out_rd_count;
    wire [7:0] out_rd_data;
    wire playback_start_toggle, playback_done_toggle;
    wire out_wr_en;
    wire [7:0] out_wr_data;
    tf_async_byte_fifo #(.ADDR_WIDTH(12)) u_playback_fifo (
        .wr_clk       (memory_clk),
        .wr_rst_n     (memory_reset_n),
        .clear_toggle (restart_toggle),
        .wr_en        (out_wr_en),
        .wr_data      (out_wr_data),
        .wr_full      (out_full),
        .wr_count     (out_wr_count),
        .wr_space_ok  (),
        .rd_clk       (clk_50m),
        .rd_rst_n     (reset_n),
        .rd_en        (out_rd_en),
        .rd_data      (out_rd_data),
        .rd_valid     (out_rd_valid),
        .rd_empty     (out_empty),
        .rd_count     (out_rd_count)
    );

    tf_audio_ddr_dma u_dma (
        .clk                  (memory_clk),
        .rst_n                (memory_reset_n),
        .mem_ready            (memory_ready),
        .capture_done_toggle  (capture_done_toggle),
        .restart_toggle       (restart_toggle),
        .file_size_bytes      (file_size_latched),
        .fifo_in_empty        (in_empty),
        .fifo_in_rd_valid     (in_rd_valid),
        .fifo_in_rd_data      (in_rd_data),
        .fifo_in_rd_en        (in_rd_en),
        .playback_start_toggle(playback_start_toggle),
        .playback_done_toggle (playback_done_toggle),
        .fifo_out_full        (out_full),
        .fifo_out_wr_en       (out_wr_en),
        .fifo_out_wr_data     (out_wr_data),
        .app_cmd              (app_cmd),
        .app_en               (app_en),
        .app_addr             (app_addr),
        .app_wdata            (app_wdata),
        .app_rdy              (app_rdy),
        .app_wren             (app_wren),
        .app_wend             (app_wend),
        .app_wrdy             (app_wrdy),
        .app_rvalid           (app_rvalid),
        .app_rdata            (app_rdata),
        .capacity_error       (dma_capacity_error),
        .bank0_valid           (dma_bank0_valid),
        .bank1_valid           (dma_bank1_valid),
        .file_size_valid       (dma_file_size_valid),
        .staged_file_size      (dma_file_size)
    );

    // Status is produced in the DDR clock domain and held until the next
    // restart, so a two-flop synchronizer is sufficient for the 50 MHz UI.
    reg ddr_error_meta, ddr_error_sync;
    reg bank0_meta, bank0_sync, bank1_meta, bank1_sync;
    reg file_size_valid_meta, file_size_valid_sync;
    reg [31:0] file_size_meta, file_size_sync_ui;
    assign audio_ddr_error = ddr_error_sync;
    assign audio_bank0_valid = bank0_sync;
    assign audio_bank1_valid = bank1_sync;
    assign audio_file_size = file_size_sync_ui;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            ddr_error_meta <= 1'b0;
            ddr_error_sync <= 1'b0;
            bank0_meta <= 1'b0;
            bank0_sync <= 1'b0;
            bank1_meta <= 1'b0;
            bank1_sync <= 1'b0;
            file_size_valid_meta <= 1'b0;
            file_size_valid_sync <= 1'b0;
            file_size_meta <= 32'd0;
            file_size_sync_ui <= 32'd0;
        end else begin
            ddr_error_meta <= dma_capacity_error;
            ddr_error_sync <= ddr_error_meta;
            bank0_meta <= dma_bank0_valid;
            bank0_sync <= bank0_meta;
            bank1_meta <= dma_bank1_valid;
            bank1_sync <= bank1_meta;
            file_size_valid_meta <= dma_file_size_valid;
            file_size_valid_sync <= file_size_valid_meta;
            file_size_meta <= dma_file_size;
            file_size_sync_ui <= file_size_meta;
        end
    end

    reg pb_meta, pb_sync, pb_seen, playback_active, playback_pending;
    reg playback_end_pending;
    reg pb_done_meta, pb_done_sync, pb_done_seen;
    reg [31:0] decoder_byte_count;
    reg [12:0] capture_count_debug;
    reg [15:0] decoder_first_word;
    wire decoder_ready;
    wire decoder_valid = playback_active && out_rd_valid;
    wire [7:0] decoder_byte = out_rd_data;
    wire [12:0] playback_fill_target =
        (file_size_valid_sync && file_size_sync_ui < 32'd1024) ?
        file_size_sync_ui[12:0] : 13'd1024;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            pb_meta <= 1'b0;
            pb_sync <= 1'b0;
            pb_seen <= 1'b0;
            pb_done_meta <= 1'b0;
            pb_done_sync <= 1'b0;
            pb_done_seen <= 1'b0;
            playback_active <= 1'b0;
            playback_pending <= 1'b0;
            playback_end_pending <= 1'b0;
            decoder_byte_count <= 32'd0;
            capture_count_debug <= 13'd0;
            decoder_first_word <= 16'd0;
        end else begin
            pb_meta <= playback_start_toggle;
            pb_sync <= pb_meta;
            pb_done_meta <= playback_done_toggle;
            pb_done_sync <= pb_done_meta;
            if (soft_restart) begin
                playback_active <= 1'b0;
                playback_pending <= 1'b0;
                playback_end_pending <= 1'b0;
                decoder_byte_count <= 32'd0;
                decoder_first_word <= 16'd0;
            end else begin
                if (pb_sync != pb_seen) begin
                    pb_seen <= pb_sync;
                    playback_pending <= 1'b1;
                    decoder_byte_count <= 32'd0;
                    decoder_first_word <= 16'd0;
                end
                if (pb_done_sync != pb_done_seen) begin
                    pb_done_seen <= pb_done_sync;
                    // DMA completion means that the last DDR byte has been
                    // copied into this FIFO, not that the decoder consumed it.
                    // Keep the 50 MHz reader alive until the FIFO is empty.
                    playback_end_pending <= 1'b1;
                end
                // Small/empty files must not wait forever for the normal
                // 1 KiB prebuffer.  The full-file mode is already complete,
                // so the staged length is a safe lower threshold.
                if (playback_pending && out_rd_count >= playback_fill_target &&
                    playback_fill_target != 0) begin
                    playback_pending <= 1'b0;
                    playback_active <= 1'b1;
                end
                if (playback_end_pending && playback_active && out_empty &&
                    !out_rd_valid) begin
                    playback_end_pending <= 1'b0;
                    playback_active <= 1'b0;
                end
                if (decoder_valid)
                    decoder_byte_count <= decoder_byte_count + 1'b1;
                if (decoder_valid && decoder_byte_count == 0)
                    decoder_first_word[7:0] <= decoder_byte;
                else if (decoder_valid && decoder_byte_count == 1)
                    decoder_first_word[15:8] <= decoder_byte;
                capture_count_debug <= in_wr_count;
            end
        end
    end

    // Reuse the existing command-response byte to expose the 50 MHz-side
    // playback FIFO depth. The other reader debug fields are not meaningful
    // after the file has been staged.
    assign debug_cmdrsp = playback_active ? decoder_first_word[7:0] : capture_count_debug[7:0];
    assign debug_rwrsp = playback_active ? decoder_first_word[15:8] : {3'd0, capture_count_debug[12:8]};
    assign debug_cardstate = reader_debug_cardstate;
    assign debug_spidone = playback_active;
    assign debug_rvalid_session = playback_active;

    assign out_rd_en = playback_active && !out_empty && !out_rd_valid && decoder_ready;
    wire decoder_format_ready;
    wire [1:0] decoder_channels;
    wire decoder_unsupported, decoder_error;
    tf_audio_decoder_ip #(.FORMAT(AUDIO_KIND)) u_decoder (
        .clk_i                    (clk_50m),
        .rst_ni                   (reset_n),
        .restart_i                (soft_restart),
        .byte_valid_i             (decoder_valid),
        .byte_ready_o             (decoder_ready),
        .byte_data_i              (decoder_byte),
        .byte_last_i              (1'b0),
        .pcm_valid_o              (pcm_valid),
        .pcm_ready_i              (pcm_ready),
        .pcm_left_o               (pcm_left),
        .pcm_right_o              (pcm_right),
        .format_o                 (),
        .format_ready_o           (decoder_format_ready),
        .sample_rate_hz_o         (sample_rate_hz),
        .channels_o               (decoder_channels),
        .bits_per_sample_o        (bits_per_sample),
        .eof_seen_o               (),
        .unsupported_o            (decoder_unsupported),
        .error_o                  (decoder_error),
        .bytes_seen_o             (),
        .frame_count_o            (frame_count),
        .resync_count_o           (resync_count),
        .stuck_frames_o           (stuck_frames),
        .pcm_fifo_parity_errors_o (pcm_fifo_parity_errors)
    );

    assign format_ready = decoder_format_ready;
    assign unsupported = decoder_unsupported | decoder_error;
    assign stereo = (decoder_channels == 2'd2);
    assign eof = raw_eof;
    // The unified decoder wrapper currently exposes no MP3 skipped-frame
    // counter, so retain the existing path port as zero.  Stuck/parity status
    // remains available through their dedicated outputs.
    assign skipped_frames = 16'd0;
endmodule
