// Unified audio decoder IP wrapper.
//
// This is the reusable boundary for the project decoder kernels.  It is
// deliberately independent of the TF/SPI reader: a DMA, CPU, BRAM reader or
// tf_sd_audio_pcm_player can drive the byte stream using ready/valid.
//
// FORMAT = 1: MPEG-1 Layer III (MP3)
// FORMAT = 2: canonical PCM16 RIFF/WAVE
// FORMAT = 3: FLAC (common fixed/verbatim/Rice subset) -> PCM16
// FORMAT = 4+: reserved, reports unsupported and consumes no bytes
//
// The output is one signed PCM16 stereo pair per transfer.  Mono sources are
// duplicated to both channels.  Metadata becomes valid after the selected
// decoder recognizes its stream header/frame.
module tf_audio_decoder_ip #(
    parameter integer FORMAT = 1
) (
    input  wire               clk_i,
    input  wire               rst_ni,
    input  wire               restart_i,

    // File byte stream.  A producer must hold byte_data_i while
    // byte_valid_i && !byte_ready_o.
    input  wire               byte_valid_i,
    output wire               byte_ready_o,
    input  wire [7:0]         byte_data_i,
    input  wire               byte_last_i,

    // Stereo PCM16 stream.
    output wire               pcm_valid_o,
    input  wire               pcm_ready_i,
    output wire signed [15:0] pcm_left_o,
    output wire signed [15:0] pcm_right_o,

    // Stream metadata/status.
    output wire [1:0]         format_o,
    output wire               format_ready_o,
    output wire [19:0]        sample_rate_hz_o,
    output wire [1:0]         channels_o,       // 1=mono, 2=stereo
    output wire [5:0]         bits_per_sample_o,
    output wire               eof_seen_o,
    output wire               unsupported_o,
    output wire               error_o,
    output wire [31:0]        bytes_seen_o,
    output wire [15:0]        frame_count_o,
    output wire [15:0]        resync_count_o,
    output wire [15:0]        stuck_frames_o,
    output wire [15:0]        pcm_fifo_parity_errors_o
);
    localparam [1:0] FORMAT_MP3  = 2'd1;
    localparam [1:0] FORMAT_WAV  = 2'd2;
    localparam [1:0] FORMAT_FLAC = 2'd3;

    wire mp3_ready, wav_ready;
    wire mp3_pcm_valid, wav_pcm_valid;
    wire signed [15:0] mp3_left, mp3_right, wav_left, wav_right;
    wire [19:0] mp3_rate, wav_rate;
    wire mp3_stereo, wav_stereo;
    wire wav_header_valid;
    wire wav_unsupported;
    wire [5:0] wav_bits;
    wire [15:0] mp3_frames, mp3_resync, mp3_stuck, mp3_parity;
    wire flac_ready, flac_format_ready, flac_pcm_valid;
    wire signed [15:0] flac_left, flac_right;
    wire [19:0] flac_rate;
    wire flac_stereo;
    wire [5:0] flac_bits;
    wire flac_unsupported, flac_error;
    wire [15:0] flac_frames;

    generate
        if (FORMAT == 1) begin : g_mp3
            tf_mp3_pcm_decoder u_mp3 (
                .clk(clk_i), .rst_n(rst_ni), .restart(restart_i),
                .in_valid(byte_valid_i), .in_byte(byte_data_i),
                .in_ready(mp3_ready), .sample_rate_hz(mp3_rate),
                .stereo(mp3_stereo), .pcm_valid(mp3_pcm_valid),
                .pcm_ready(pcm_ready_i), .pcm_left(mp3_left),
                .pcm_right(mp3_right), .frame_count(mp3_frames),
                .resync_count(mp3_resync), .skipped_frames(),
                .stuck_frames(mp3_stuck),
                .pcm_fifo_parity_errors(mp3_parity)
            );
        end else begin : g_no_mp3
            assign mp3_ready  = 1'b0;
            assign mp3_frames = 16'd0;
            assign mp3_resync = 16'd0;
            assign mp3_stuck = 16'd0;
            assign mp3_parity = 16'd0;
        end

        if (FORMAT == 2) begin : g_wav
            tf_wav_pcm_decoder u_wav (
                .clk(clk_i), .rst_n(rst_ni), .restart(restart_i),
                .in_valid(byte_valid_i), .in_byte(byte_data_i),
                .in_ready(wav_ready), .header_valid(wav_header_valid),
                .sample_rate_hz(wav_rate), .stereo(wav_stereo),
                .bits_per_sample(wav_bits), .pcm_valid(wav_pcm_valid),
                .pcm_ready(pcm_ready_i), .pcm_left(wav_left),
                .pcm_right(wav_right), .unsupported(wav_unsupported)
            );
        end else begin : g_no_wav
            assign wav_ready = 1'b0;
            assign wav_header_valid = 1'b0;
            assign wav_unsupported = 1'b0;
            assign wav_rate = 20'd0;
            assign wav_stereo = 1'b0;
            assign wav_bits = 6'd0;
            assign wav_pcm_valid = 1'b0;
            assign wav_left = 16'sd0;
            assign wav_right = 16'sd0;
        end

        if (FORMAT == 3) begin : g_flac
            tf_flac_pcm_decoder u_flac (
                .clk(clk_i), .rst_n(rst_ni), .restart(restart_i),
                .in_valid(byte_valid_i), .in_byte(byte_data_i),
                .in_ready(flac_ready), .format_ready(flac_format_ready),
                .sample_rate_hz(flac_rate), .stereo(flac_stereo),
                .bits_per_sample(flac_bits), .pcm_valid(flac_pcm_valid),
                .pcm_ready(pcm_ready_i), .pcm_left(flac_left),
                .pcm_right(flac_right), .unsupported(flac_unsupported),
                .error(flac_error), .frame_count(flac_frames)
            );
        end else begin : g_no_flac
            assign flac_ready = 1'b0;
            assign flac_format_ready = 1'b0;
            assign flac_pcm_valid = 1'b0;
            assign flac_left = 16'sd0;
            assign flac_right = 16'sd0;
            assign flac_rate = 20'd0;
            assign flac_stereo = 1'b0;
            assign flac_bits = 6'd0;
            assign flac_unsupported = 1'b0;
            assign flac_error = 1'b0;
            assign flac_frames = 16'd0;
        end
    endgenerate

    wire supported = (FORMAT == 1) || (FORMAT == 2) || (FORMAT == 3);
    wire unsupported = !supported;
    wire decoder_ready = (FORMAT == 1) ? mp3_ready :
                         (FORMAT == 2) ? wav_ready :
                         (FORMAT == 3) ? flac_ready : 1'b0;
    wire decoder_format_ready = (FORMAT == 1) ? (mp3_frames != 0) :
                                (FORMAT == 2) ? wav_header_valid :
                                (FORMAT == 3) ? flac_format_ready : 1'b0;
    wire decoder_pcm_valid = (FORMAT == 1) ? mp3_pcm_valid :
                             (FORMAT == 2) ? wav_pcm_valid :
                             (FORMAT == 3) ? flac_pcm_valid : 1'b0;
    wire signed [15:0] decoder_left = (FORMAT == 1) ? mp3_left :
                                      (FORMAT == 2) ? wav_left :
                                      (FORMAT == 3) ? flac_left : 16'sd0;
    wire signed [15:0] decoder_right = (FORMAT == 1) ? mp3_right :
                                       (FORMAT == 2) ? wav_right :
                                       (FORMAT == 3) ? flac_right : 16'sd0;
    wire [19:0] decoder_rate = (FORMAT == 1) ? mp3_rate :
                                (FORMAT == 2) ? wav_rate :
                                (FORMAT == 3) ? flac_rate : 20'd0;
    wire decoder_stereo = (FORMAT == 1) ? mp3_stereo :
                          (FORMAT == 2) ? wav_stereo :
                          (FORMAT == 3) ? flac_stereo : 1'b0;
    wire [5:0] decoder_bits = (FORMAT == 1) ? 6'd16 :
                              (FORMAT == 2) ? wav_bits :
                              (FORMAT == 3) ? flac_bits : 6'd0;

    reg [31:0] bytes_seen;
    reg eof_seen;
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni || restart_i) begin
            bytes_seen <= 32'd0;
            eof_seen   <= 1'b0;
        end else if (byte_valid_i && decoder_ready) begin
            bytes_seen <= bytes_seen + 1'b1;
            if (byte_last_i)
                eof_seen <= 1'b1;
        end
    end

    assign byte_ready_o = decoder_ready;
    assign pcm_valid_o  = decoder_pcm_valid;
    assign pcm_left_o   = decoder_left;
    assign pcm_right_o  = decoder_right;
    assign format_o     = (FORMAT == 1) ? FORMAT_MP3 :
                          (FORMAT == 2) ? FORMAT_WAV : FORMAT_FLAC;
    assign format_ready_o = decoder_format_ready;
    assign sample_rate_hz_o = decoder_rate;
    assign channels_o = decoder_stereo ? 2'd2 :
                        (decoder_format_ready ? 2'd1 : 2'd0);
    assign bits_per_sample_o = decoder_bits;
    assign eof_seen_o = eof_seen;
    assign unsupported_o = unsupported || (FORMAT == 2 && wav_unsupported) ||
                           (FORMAT == 3 && flac_unsupported);
    assign error_o = unsupported || (FORMAT == 2 && wav_unsupported) ||
                     (FORMAT == 3 && flac_error) ||
                     (mp3_stuck != 0) || (mp3_parity != 0);
    assign bytes_seen_o = bytes_seen;
    assign frame_count_o = (FORMAT == 3) ? flac_frames : mp3_frames;
    assign resync_count_o = mp3_resync;
    assign stuck_frames_o = mp3_stuck;
    assign pcm_fifo_parity_errors_o = mp3_parity;
endmodule
