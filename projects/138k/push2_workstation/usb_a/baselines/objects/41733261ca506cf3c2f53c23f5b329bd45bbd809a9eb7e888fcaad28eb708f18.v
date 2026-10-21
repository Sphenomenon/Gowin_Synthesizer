// SD-card FAT32/FAT16 audio player front-end.
//
// This is the board-facing path for the Tang MP3/WAV cores:
//   Micro-SD SPI -> FAT root playlist -> 4 KiB byte FIFO -> decoder -> PCM16
//
// AUDIO_KIND=1 selects MPEG-1 Layer III; AUDIO_KIND=2 selects canonical
// PCM WAV; AUDIO_KIND=3 selects the FLAC decoder (use FAT short extension
// "FLA"). FILE_EXT must match the selected decoder.
// The PCM output is intentionally a normal ready/valid stream so the caller
// may connect a PT8211 sample pacer, a BRAM/DDR recorder, or a CPU mailbox.
//
// The FAT reader and MP3/audio blocks are GPL-3.0 third-party RTL.  The
// adapter/skid logic in this file is project glue and is documented in
// storage/THIRD_PARTY.md.
module tf_sd_audio_pcm_player #(
    parameter [23:0] FILE_EXT = "MP3",
    parameter integer AUDIO_KIND = 1,       // 1=MP3, 2=WAV, 3=FLAC
    // 50 MHz system clock: 100 -> ~245 kHz init (<=400 kHz SD SPI limit),
    // 6 -> ~3.57 MHz data phase.  Tang's 27 MHz defaults are 50/3.
    parameter integer SPI_CLK_DIV = 100,
    parameter integer SPI_CLK_DIV_FAST = 6
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               restart,
    // 0-based index of the root-directory file to play.  The top level drives
    // this explicitly and must tie it to 4'd0 when track switching is unused;
    // it is deliberately not defaulted, so a missing connection cannot
    // silently select track 0.  Changing it at runtime tears down and restarts
    // the byte path (see track_change below).
    input  wire [3:0]         track_index,
    input  wire               sd_miso,
    output wire               sd_cs_n,
    output wire               sd_sck,
    output wire               sd_mosi,

    output wire [1:0]         card_type,
    output wire [3:0]         card_stat,
    output wire [1:0]         filesystem_type,
    output wire [2:0]         filesystem_stat,
    output wire               scan_done,
    output wire               card_ready,
    output wire               playing,
    output wire               eof,
    output wire [4:0]         track_count,

    output wire               format_ready,
    output wire               unsupported,
    output wire [19:0]        sample_rate_hz,
    output wire               stereo,
    output wire [5:0]         bits_per_sample,
    output wire               pcm_valid,
    input  wire               pcm_ready,
    output wire signed [15:0] pcm_left,
    output wire signed [15:0] pcm_right,

    output wire [15:0]        frame_count,
    output wire [15:0]        resync_count,
    output wire [15:0]        skipped_frames,
    output wire [15:0]        stuck_frames,
    output wire [15:0]        pcm_fifo_parity_errors,
    output wire [7:0]         debug_cmdrsp,
    output wire [7:0]         debug_rwrsp,
    output wire [3:0]         debug_cardstate,
    output wire               debug_spidone,
    output wire               debug_rvalid_session
);
    reg track_start;
    reg started;

    // A runtime change of track_index tears down the whole byte path: the FAT
    // reader is re-armed on the new index (track_start below), and the byte
    // FIFO, the one-deep skid buffer and the decoder are all cleared.  For MP3
    // the decoder restart also clears its internal PCM FIFO (pcm_drain and
    // pcm_fifo .clear); for WAV it resets the chunk parser.
    reg [3:0] track_index_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) track_index_q <= 4'd0;
        else        track_index_q <= track_index;
    end

    wire track_change = (track_index != track_index_q);
    wire soft_restart = restart | track_change;   // 1-cycle pulse on a change

    // The FAT reader only stops the old track at a sector boundary, so it can
    // still present a few hundred stale bytes after the change.  switch_hold
    // drops those writes and is released once the reader has stopped and then
    // started the new track (playing low -> high), so the decoder never sees
    // bytes from the previous file.
    reg switch_hold;
    reg switch_seen_low;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            switch_hold     <= 1'b0;
            switch_seen_low <= 1'b0;
        end else if (soft_restart) begin
            switch_hold     <= 1'b1;
            switch_seen_low <= 1'b0;
        end else if (switch_hold) begin
            if (!playing)         switch_seen_low <= 1'b1;
            else if (switch_seen_low) switch_hold <= 1'b0;
        end
    end

    // Start the selected root-directory file once the playlist scan is
    // complete, and re-arm after a restart or a track change.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            track_start <= 1'b0;
            started     <= 1'b0;
        end else if (soft_restart) begin
            track_start <= 1'b0;
            started     <= 1'b0;
        end else begin
            track_start <= 1'b0;
            if (!started && scan_done && (track_count != 0)) begin
                track_start <= 1'b1;
                started     <= 1'b1;
            end
        end
    end

    wire file_out_valid;
    wire [7:0] file_out_byte;
    wire sector_allow;

    // Let the SD reader build a few sectors before the decoder starts.  This
    // absorbs the first command gap and prevents the DAC from starting with
    // an empty byte FIFO.  EOF also releases the gate so files shorter than
    // the threshold are decoded after their complete contents are buffered.
    localparam [11:0] PREBUFFER_BYTES = 12'd2048;
    reg prebuffered;

    tf_sd_file_reader #(
        .EXT              (FILE_EXT),
        .SPI_CLK_DIV      (SPI_CLK_DIV),
        .SPI_CLK_DIV_FAST (SPI_CLK_DIV_FAST)
    ) u_sd (
        .rstn            (rst_n),
        .clk             (clk),
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
        .track_start     (track_start),
        .playing         (playing),
        .eof             (eof),
        .sector_allow    (sector_allow),
        .outen           (file_out_valid),
        .outbyte         (file_out_byte),
        .name_raddr      (8'd0),
        .name_rdata      (),
        .debug_cmdrsp    (debug_cmdrsp),
        .debug_rwrsp     (debug_rwrsp),
        .debug_cardstate (debug_cardstate),
        .debug_spidone   (debug_spidone),
        .debug_rvalid_session(debug_rvalid_session)
    );

    assign card_ready = (card_stat == 4'd8) || (card_stat == 4'd9);

    // The SD reader delivers registered bytes.  audio_fifo's sector_allow is
    // asserted only when a full sector plus margin fits, preventing an SD
    // burst from overrunning the decoder while a frame is being transformed.
    wire [7:0] byte_rdata;
    wire [11:0] byte_count;
    wire byte_empty;
    wire byte_rd;
    audio_fifo #(.DEPTH(4096)) u_byte_fifo (
        .clk(clk), .rst_n(rst_n), .clear(soft_restart),
        .wr(file_out_valid && ~switch_hold), .wdata(file_out_byte),
        .rd(byte_rd), .rdata(byte_rdata),
        .count(byte_count), .empty(byte_empty), .sector_allow(sector_allow)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) prebuffered <= 1'b0;
        else if (soft_restart) prebuffered <= 1'b0;
        else if (!prebuffered && (byte_count >= PREBUFFER_BYTES || eof))
            prebuffered <= 1'b1;
    end

    wire decoder_ready;
    wire decoder_valid;
    wire [7:0] decoder_byte;
    reg skid_pend, skid_valid;
    reg [7:0] skid_byte;

    // One-deep skid buffer closes the synchronous-read gap between audio_fifo
    // and a decoder that can drop in_ready at a frame/granule boundary.
    assign byte_rd = ~byte_empty & ~skid_pend & ~skid_valid &&
                     (prebuffered || byte_count >= PREBUFFER_BYTES);
    assign decoder_valid = skid_valid;
    assign decoder_byte = skid_byte;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            skid_pend  <= 1'b0;
            skid_valid <= 1'b0;
            skid_byte  <= 8'd0;
        end else if (soft_restart) begin
            skid_pend  <= 1'b0;
            skid_valid <= 1'b0;
        end else begin
            skid_pend <= byte_rd;
            if (skid_pend) begin
                skid_byte  <= byte_rdata;
                skid_valid <= 1'b1;
            end else if (skid_valid && decoder_ready) begin
                skid_valid <= 1'b0;
            end
        end
    end

    wire mp3_pcm_valid, wav_pcm_valid;
    wire signed [15:0] mp3_pcm_left, mp3_pcm_right;
    wire signed [15:0] wav_pcm_left, wav_pcm_right;
    wire [19:0] mp3_rate, wav_rate;
    wire mp3_stereo, wav_stereo;
    wire wav_header_valid;
    wire dec_unsupported;
    wire [5:0] wav_bits;
    wire [15:0] mp3_frame_count, mp3_resync_count, mp3_skipped, mp3_stuck, mp3_perr;
    wire flac_pcm_valid;
    wire signed [15:0] flac_pcm_left, flac_pcm_right;
    wire [19:0] flac_rate;
    wire flac_stereo;
    wire [5:0] flac_bits;
    wire flac_header_valid, flac_unsupported, flac_error;
    wire [15:0] flac_frame_count;

    generate
        if (AUDIO_KIND == 1) begin : g_mp3
            tf_mp3_pcm_decoder u_decoder (
                .clk(clk), .rst_n(rst_n), .restart(soft_restart),
                .in_valid(decoder_valid), .in_byte(decoder_byte),
                .in_ready(decoder_ready), .sample_rate_hz(mp3_rate),
                .stereo(mp3_stereo), .pcm_valid(mp3_pcm_valid),
                .pcm_ready(pcm_ready), .pcm_left(mp3_pcm_left),
                .pcm_right(mp3_pcm_right), .frame_count(mp3_frame_count),
                .resync_count(mp3_resync_count), .skipped_frames(mp3_skipped),
                .stuck_frames(mp3_stuck),
                .pcm_fifo_parity_errors(mp3_perr)
            );
            assign dec_unsupported = 1'b0;
        end else begin : g_no_mp3
            assign mp3_frame_count = 16'd0;
            assign mp3_resync_count = 16'd0;
            assign mp3_skipped      = 16'd0;
            assign mp3_stuck        = 16'd0;
            assign mp3_perr         = 16'd0;
        end

        if (AUDIO_KIND == 2) begin : g_wav
            tf_wav_pcm_decoder u_decoder (
                .clk(clk), .rst_n(rst_n), .restart(soft_restart),
                .in_valid(decoder_valid), .in_byte(decoder_byte),
                .in_ready(decoder_ready), .header_valid(wav_header_valid),
                .sample_rate_hz(wav_rate), .stereo(wav_stereo),
                .bits_per_sample(wav_bits), .pcm_valid(wav_pcm_valid),
                .pcm_ready(pcm_ready), .pcm_left(wav_pcm_left),
                .pcm_right(wav_pcm_right), .unsupported(dec_unsupported)
            );
        end else begin : g_no_wav
            assign wav_header_valid = 1'b0;
            assign wav_rate = 20'd0;
            assign wav_stereo = 1'b0;
            assign wav_bits = 6'd0;
            assign wav_pcm_valid = 1'b0;
            assign wav_pcm_left = 16'sd0;
            assign wav_pcm_right = 16'sd0;
        end

        if (AUDIO_KIND == 3) begin : g_flac
            tf_flac_pcm_decoder u_decoder (
                .clk(clk), .rst_n(rst_n), .restart(soft_restart),
                .in_valid(decoder_valid), .in_byte(decoder_byte),
                .in_ready(decoder_ready), .format_ready(flac_header_valid),
                .sample_rate_hz(flac_rate), .stereo(flac_stereo),
                .bits_per_sample(flac_bits), .pcm_valid(flac_pcm_valid),
                .pcm_ready(pcm_ready), .pcm_left(flac_pcm_left),
                .pcm_right(flac_pcm_right), .unsupported(flac_unsupported),
                .error(flac_error), .frame_count(flac_frame_count)
            );
            assign dec_unsupported = 1'b0;
        end else begin : g_no_flac
            assign flac_header_valid = 1'b0;
            assign flac_rate = 20'd0;
            assign flac_stereo = 1'b0;
            assign flac_bits = 6'd0;
            assign flac_pcm_valid = 1'b0;
            assign flac_pcm_left = 16'sd0;
            assign flac_pcm_right = 16'sd0;
            assign flac_unsupported = 1'b0;
            assign flac_error = 1'b0;
            assign flac_frame_count = 16'd0;
        end

        if (AUDIO_KIND != 1 && AUDIO_KIND != 2 && AUDIO_KIND != 3) begin : g_bad_kind
            assign decoder_ready = 1'b0;
            assign dec_unsupported = 1'b1;
        end
    endgenerate

    assign format_ready             = (AUDIO_KIND == 1) ? (mp3_frame_count != 0) :
                                      (AUDIO_KIND == 2) ? wav_header_valid :
                                      (AUDIO_KIND == 3) ? flac_header_valid : 1'b0;
    assign unsupported              = (AUDIO_KIND != 1 && AUDIO_KIND != 2 && AUDIO_KIND != 3) ? 1'b1 :
                                      dec_unsupported || flac_unsupported || flac_error;
    assign sample_rate_hz           = (AUDIO_KIND == 1) ? mp3_rate :
                                      (AUDIO_KIND == 2) ? wav_rate :
                                      (AUDIO_KIND == 3) ? flac_rate : 20'd0;
    assign stereo                   = (AUDIO_KIND == 1) ? mp3_stereo :
                                      (AUDIO_KIND == 2) ? wav_stereo :
                                      (AUDIO_KIND == 3) ? flac_stereo : 1'b0;
    assign bits_per_sample          = (AUDIO_KIND == 1) ? 6'd16 :
                                      (AUDIO_KIND == 2) ? wav_bits :
                                      (AUDIO_KIND == 3) ? flac_bits : 6'd0;
    assign pcm_valid                = (AUDIO_KIND == 1) ? mp3_pcm_valid :
                                      (AUDIO_KIND == 2) ? wav_pcm_valid :
                                      (AUDIO_KIND == 3) ? flac_pcm_valid : 1'b0;
    assign pcm_left                 = (AUDIO_KIND == 1) ? mp3_pcm_left :
                                      (AUDIO_KIND == 2) ? wav_pcm_left :
                                      (AUDIO_KIND == 3) ? flac_pcm_left : 16'sd0;
    assign pcm_right                = (AUDIO_KIND == 1) ? mp3_pcm_right :
                                      (AUDIO_KIND == 2) ? wav_pcm_right :
                                      (AUDIO_KIND == 3) ? flac_pcm_right : 16'sd0;
    assign frame_count              = (AUDIO_KIND == 3) ? flac_frame_count : mp3_frame_count;
    assign resync_count             = mp3_resync_count;
    assign skipped_frames           = mp3_skipped;
    assign stuck_frames             = mp3_stuck;
    assign pcm_fifo_parity_errors   = mp3_perr;
endmodule
