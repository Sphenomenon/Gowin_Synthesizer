// PCM WAV byte stream to stereo PCM16 adapter.
//
// The header is parsed by tf_wav_chunk_parser, which walks the real RIFF chunk
// list, so LIST/fact/unknown chunks, 18/40-byte fmt chunks and odd-size
// alignment no longer shift the PCM start.  Only WAVE_FORMAT_PCM (and the PCM
// sub-format of WAVE_FORMAT_EXTENSIBLE) is accepted.
//
// Supported sample formats: 8/16/24/32-bit, mono or stereo.  8-bit WAV is
// unsigned (offset binary) and is converted to signed; 24/32-bit are truncated
// to the top 16 bits.  Mono is duplicated to both outputs.  Anything else
// (non-PCM codec, >2 channels, odd bit depth) is reported on unsupported_o and
// produces no PCM.
//
// Input contract: present in_byte only on a cycle with in_valid && in_ready.
// Output contract: pcm_left/right are a stereo pair and remain stable while
// pcm_valid is high and pcm_ready is low.  in_ready drops while a completed
// pair is waiting, so no WAV byte is lost to a stalled consumer.
module tf_wav_pcm_decoder (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               restart,
    input  wire               in_valid,
    input  wire [7:0]         in_byte,
    output wire               in_ready,

    output wire               header_valid,
    output wire [19:0]        sample_rate_hz,
    output wire               stereo,
    output wire [5:0]         bits_per_sample,
    output wire               pcm_valid,
    input  wire               pcm_ready,
    output wire signed [15:0] pcm_left,
    output wire signed [15:0] pcm_right,
    output wire               unsupported
);
    wire        parser_pcm_en;
    wire [7:0]  parser_pcm_byte;
    wire [19:0] parser_rate;
    wire [3:0]  parser_channels;
    wire [5:0]  parser_bits;
    wire [15:0] parser_format;
    wire        parser_header_valid;
    wire        parser_unsupported;

    tf_wav_chunk_parser u_parser (
        .clk          (clk),
        .rst_n        (rst_n),
        .restart      (restart),
        .inen         (in_valid && in_ready),
        .inbyte       (in_byte),
        .pcm_en       (parser_pcm_en),
        .pcm_byte     (parser_pcm_byte),
        .sample_rate  (parser_rate),
        .channels     (parser_channels),
        .bits         (parser_bits),
        .audio_format (parser_format),
        .header_valid (parser_header_valid),
        .unsupported  (parser_unsupported)
    );

    wire [3:0] bytes_per_sample = {1'b0, parser_bits[5:3]};  // 1, 2, 3 or 4
    wire       bits_ok = (parser_bits == 6'd8)  || (parser_bits == 6'd16) ||
                         (parser_bits == 6'd24) || (parser_bits == 6'd32);
    wire       chan_ok = (parser_channels == 4'd1) || (parser_channels == 4'd2);
    wire       is_stereo = (parser_channels == 4'd2);
    wire       supported = parser_header_valid && !parser_unsupported &&
                           (parser_format == 16'd1) && bits_ok && chan_ok;

    wire [3:0] frame_bytes = is_stereo ? {bytes_per_sample[2:0], 1'b0}
                                       : bytes_per_sample;

    // Keep each channel in its own 32-bit business word.  Even a 32-bit
    // stereo WAV is assembled as two words, never as a 64/128-bit audio bus.
    reg [31:0] left_acc,right_acc;
    reg [3:0]  bcnt;
    reg        pcm_valid_r;
    reg signed [15:0] pcm_left_r, pcm_right_r;

    function [31:0] put_byte;
        input [31:0] word;
        input [2:0] index;
        input [7:0] value;
        begin
            put_byte=word;
            case(index)
                0:put_byte[7:0]=value;
                1:put_byte[15:8]=value;
                2:put_byte[23:16]=value;
                3:put_byte[31:24]=value;
                default:begin end
            endcase
        end
    endfunction
    wire current_is_left = bcnt < bytes_per_sample;
    wire [3:0] channel_byte_full = current_is_left ? bcnt :
                                   bcnt-bytes_per_sample;
    wire [2:0] channel_byte = channel_byte_full[2:0];
    wire [31:0] left_next = current_is_left ?
                            put_byte(left_acc,channel_byte,parser_pcm_byte) : left_acc;
    wire [31:0] right_next = current_is_left ? right_acc :
                             put_byte(right_acc,channel_byte,parser_pcm_byte);

    function signed [15:0] wav_to_s16 (input [31:0] w, input [3:0] b);
        begin
            case (b)
                4'd1: wav_to_s16 = (w[7:0] << 8) - 16'sd32768;  // 8-bit is unsigned
                4'd2: wav_to_s16 = $signed(w[15:0]);
                4'd3: wav_to_s16 = $signed(w[23:8]);            // top 16 of 24 bits
                4'd4: wav_to_s16 = $signed(w[31:16]);           // top 16 of 32 bits
                default: wav_to_s16 = 16'sd0;
            endcase
        end
    endfunction

    assign in_ready = ~pcm_valid_r | pcm_ready;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            left_acc    <= 32'd0;
            right_acc   <= 32'd0;
            bcnt        <= 4'd0;
            pcm_valid_r <= 1'b0;
            pcm_left_r  <= 16'sd0;
            pcm_right_r <= 16'sd0;
        end else if (restart) begin
            left_acc    <= 32'd0;
            right_acc   <= 32'd0;
            bcnt        <= 4'd0;
            pcm_valid_r <= 1'b0;
        end else begin
            if (pcm_valid_r && pcm_ready)
                pcm_valid_r <= 1'b0;

            if (parser_pcm_en && supported) begin
                if (bcnt + 4'd1 == frame_bytes) begin
                    bcnt        <= 4'd0;
                    left_acc    <= 32'd0;
                    right_acc   <= 32'd0;
                    pcm_left_r  <= wav_to_s16(left_next, bytes_per_sample);
                    pcm_right_r <= wav_to_s16(is_stereo ? right_next : left_next,
                                              bytes_per_sample);
                    pcm_valid_r <= 1'b1;
                end else begin
                    left_acc <= left_next;
                    right_acc <= right_next;
                    bcnt <= bcnt + 4'd1;
                end
            end
        end
    end

    assign header_valid     = supported;
    assign unsupported      = parser_header_valid && !supported;
    assign sample_rate_hz   = parser_rate;
    assign stereo           = supported && is_stereo;
    assign bits_per_sample  = parser_bits;
    assign pcm_valid        = pcm_valid_r;
    assign pcm_left         = pcm_left_r;
    assign pcm_right        = pcm_right_r;
endmodule
