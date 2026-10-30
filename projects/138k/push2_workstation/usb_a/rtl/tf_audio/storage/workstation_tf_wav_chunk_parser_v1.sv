// Maintained strict WAV v1 derivative; see workstation_tf_direct_ingress.provenance.json.
// Legacy kernels/default selection remain byte-identical. EOF is a separate
// drained file event; zero-size data is empty, and incomplete RIFF/chunks fail.
// RIFF/WAVE chunk walker for the TF audio decoder IP.
//
// The vendored wav_parser counts a fixed 44-byte header, which only works for
// exactly one file layout: "RIFF"<size>"WAVE" then a 16-byte `fmt ` chunk
// immediately followed by `data`.  Real files routinely break that:
//
//   * metadata chunks (LIST/INFO, fact, cue, JUNK, bext) before or after fmt;
//   * an 18-byte fmt chunk (cbSize) or a 40-byte WAVE_FORMAT_EXTENSIBLE fmt;
//   * odd-sized chunks, whose payload is followed by one alignment pad byte.
//
// In every such file the old parser read channels/rate/bits from the wrong
// offsets and started the PCM stream in the middle of a header chunk.  This
// walker parses the actual chunk list instead.
//
// Layout walked:
//   "RIFF" <u32 size> "WAVE" ( "fmt " <u32 n> <n bytes> | "data" <u32 n>
//                              <n bytes> | <other> <u32 n> <n bytes> )*
//
// Metadata reported after `fmt ` is parsed:
//   audio_format_o  1 for PCM and for WAVE_FORMAT_EXTENSIBLE with a PCM
//                   sub-format, otherwise the raw format code
//   channels_o      1..15
//   bits_o          bits per sample
//   unsupported_o   1 when the stream is parsed but is not PCM
//
// A `data` chunk is streamed only up to its declared size; size 0 is
// empty in this strict v1. Once declared bytes have been emitted the
// walker returns to chunk parsing, so a trailing LIST/JUNK is never mistaken
// for audio.
//
// The stream is rejected (unsupported_o = 1 and no PCM) when the codec is not
// PCM (including WAVE_FORMAT_EXTENSIBLE with a non-PCM sub-format), when the
// fmt chunk is shorter than the 16 bytes needed for the PCM fields, or when
// `data` appears before a usable `fmt `.
//
// pcm_en is COMBINATIONAL in inen and is asserted only for bytes inside the
// `data` payload.  The consumer's in_ready is therefore the single
// back-pressure point: no byte can be accepted twice while the decoder output
// is stalled, which is what the registered-output variant in the vendored
// parser could not guarantee for one-byte-per-sample formats.
module workstation_tf_wav_chunk_parser_v1 (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        restart,          // pulse on track change

    input  wire        inen,             // byte accepted this cycle
    input  wire [7:0]  inbyte,
    input  wire        eof_i, // separate event, only after all accepted bytes
    output reg         eos_o,
    output reg         error_o,
    output wire        payload_end_o,

    output wire        pcm_en,
    output wire [7:0]  pcm_byte,

    output reg  [19:0] sample_rate,
    output reg  [3:0]  channels,
    output reg  [5:0]  bits,
    output reg  [15:0] audio_format,
    output reg         header_valid,     // a usable fmt chunk has been parsed
    output reg         unsupported       // parsed, but not PCM
);
    localparam [2:0] S_HUNT = 3'd0,      // shift until "RIFF"
                     S_RSZ  = 3'd1,      // consume the 4-byte RIFF size
                     S_WAVE = 3'd2,      // expect "WAVE"
                     S_CID  = 3'd3,      // read a 4-byte chunk id
                     S_CSZ  = 3'd4,      // read a 4-byte chunk size
                     S_FMT  = 3'd5,      // read the fmt payload
                     S_SKIP = 3'd6,      // skip a payload (+ alignment pad)
                     S_DATA = 3'd7;      // stream the data payload

    localparam [31:0] MAGIC_RIFF = "RIFF";
    localparam [31:0] MAGIC_WAVE = "WAVE";
    localparam [31:0] ID_FMT     = "fmt ";
    localparam [31:0] ID_DATA    = "data";

    localparam [15:0] FORMAT_PCM        = 16'd1;
    localparam [15:0] FORMAT_EXTENSIBLE = 16'hFFFE;

    reg [2:0]  st;
    reg [1:0]  bc;                        // byte index inside a 4-byte field
    reg [31:0] win;                       // rolling/shift register
    reg [31:0] cid;                       // current chunk id
    reg [31:0] csize;                     // current chunk size
    reg [31:0] left;                      // payload bytes still to consume
    reg [5:0]  fcnt;                      // fmt byte index
    reg [15:0] fmt_code;                  // fmt bytes 0..1
    reg [15:0] chan_w;                    // fmt bytes 2..3
    reg [19:0] rate_w;                    // fmt bytes 4..7 (20 bits kept)
    reg [15:0] bits_w;                    // fmt bytes 14..15
    reg [15:0] sub_w;                     // extensible sub-format bytes 24..25
    reg [31:0] data_left;                 // data payload bytes still to stream
    reg        data_stream;               // data size 0: stream until restart
    reg [32:0] byte_count;
    reg [31:0] riff_size;
    reg rate_high,guid_bad;
    reg data_seen;
    reg        rejected;                  // a hard reject; a later fmt cannot clear it

    function [7:0] pcm_guid_byte(input [5:0] index);
        case(index)
            24:pcm_guid_byte=8'h01;30:pcm_guid_byte=8'h10;
            32:pcm_guid_byte=8'h80;35:pcm_guid_byte=8'haa;
            37:pcm_guid_byte=8'h38;38:pcm_guid_byte=8'h9b;39:pcm_guid_byte=8'h71;
            default:pcm_guid_byte=0;
        endcase
    endfunction
    wire guid_byte_bad=(fcnt>=24 && fcnt<40 && inbyte!=pcm_guid_byte(fcnt));
    wire [31:0] win_next = {win[23:0], inbyte};

    // The shift window keeps the first byte in the most significant position,
    // which is what makes "RIFF"/"fmt " compare against Verilog string
    // literals directly.  RIFF numeric fields are little-endian, so a chunk
    // size read out of the window has to be byte-reversed before use.
    wire [31:0] csize_le = {win_next[7:0], win_next[15:8],
                            win_next[23:16], win_next[31:24]};

    wire [33:0] chunk_end={1'b0,byte_count}+34'd1+
        {2'b0,csize_le}+{33'd0,csize_le[0]};
    // Final field values, folding in the byte that is arriving right now.  The
    // last fmt byte is only known at the same edge the metadata is committed,
    // so committing from the plain registers would read one byte stale.
    wire [15:0] fmt_final  = (fcnt == 6'd0) ? {8'd0, inbyte} :
                             (fcnt == 6'd1) ? {inbyte, fmt_code[7:0]} :
                             fmt_code;
    wire [15:0] chan_final = (fcnt == 6'd2) ? {8'd0, inbyte} :
                             (fcnt == 6'd3) ? {inbyte, chan_w[7:0]} :
                             chan_w;
    wire [19:0] rate_final = (fcnt == 6'd4) ? {12'd0, inbyte} :
                             (fcnt == 6'd5) ? {4'd0, inbyte, rate_w[7:0]} :
                             (fcnt == 6'd6) ? {inbyte[3:0], rate_w[15:8], rate_w[7:0]} :
                             rate_w;
    wire [15:0] bits_final = (fcnt == 6'd14) ? {8'd0, inbyte} :
                             (fcnt == 6'd15) ? {inbyte, bits_w[7:0]} :
                             bits_w;
    wire [15:0] sub_final  = (fcnt == 6'd24) ? {8'd0, inbyte} :
                             (fcnt == 6'd25) ? {inbyte, sub_w[7:0]} :
                             sub_w;

    wire is_pcm_final = (fmt_final == FORMAT_PCM) ||
                        (fmt_final == FORMAT_EXTENSIBLE && sub_final == FORMAT_PCM);

    assign pcm_en   = inen && (st == S_DATA) && !error_o && !eos_o;
    assign payload_end_o = pcm_en && data_left == 32'd1;
    assign pcm_byte = inbyte;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            eos_o<=0;error_o<=0;byte_count<=0;riff_size<=0;rate_high<=0;guid_bad<=0;data_seen<=0;
            st           <= S_HUNT;
            bc           <= 2'd0;
            win          <= 32'd0;
            cid          <= 32'd0;
            csize        <= 32'd0;
            left         <= 32'd0;
            fcnt         <= 6'd0;
            fmt_code     <= 16'd0;
            chan_w       <= 16'd0;
            rate_w       <= 20'd44_100;
            bits_w       <= 16'd16;
            sub_w        <= 16'd0;
            data_left    <= 32'd0;
            data_stream  <= 1'b0;
            rejected     <= 1'b0;
            sample_rate  <= 20'd44_100;
            channels     <= 4'd2;
            bits         <= 6'd16;
            audio_format <= FORMAT_PCM;
            header_valid <= 1'b0;
            unsupported  <= 1'b0;
        end else if (restart) begin
            eos_o<=0;error_o<=0;byte_count<=0;riff_size<=0;rate_high<=0;guid_bad<=0;data_seen<=0;
            st           <= S_HUNT;
            bc           <= 2'd0;
            win          <= 32'd0;
            cid          <= 32'd0;
            csize        <= 32'd0;
            left         <= 32'd0;
            fcnt         <= 6'd0;
            data_left    <= 32'd0;
            data_stream  <= 1'b0;
            rejected     <= 1'b0;
            header_valid <= 1'b0;
            unsupported  <= 1'b0;
        end else begin
            if(eof_i)begin
                if(!error_o && st==S_CID && bc==0 && header_valid &&
                   !unsupported && data_seen && riff_size>=4 &&
                   byte_count==({1'b0,riff_size}+33'd8))eos_o<=1;
                else error_o<=1;
            end
            if(inen && !error_o && !eos_o)begin
            byte_count<=byte_count+1'b1;
            if(byte_count>=33'd8 && byte_count>=({1'b0,riff_size}+33'd8))error_o<=1;

            case (st)
            S_HUNT: begin
                win <= win_next;
                if(bc==3)begin
                    bc<=0;
                    if(win_next==MAGIC_RIFF)st<=S_RSZ;
                    else error_o<=1;
                end else bc<=bc+1'b1;
            end

            S_RSZ: begin
                win<=win_next;
                if (bc == 2'd3) begin
                    riff_size<=csize_le;
                    if(csize_le<4)error_o<=1;
                    st  <= S_WAVE;
                    bc  <= 2'd0;
                    win <= 32'd0;
                end else begin
                    bc <= bc + 2'd1;
                end
            end

            S_WAVE: begin
                win <= win_next;
                if (bc == 2'd3) begin
                    if (win_next == MAGIC_WAVE) begin
                        st <= S_CID;
                        bc <= 2'd0;
                    end else begin
                        error_o<=1;
                    end
                end else begin
                    bc <= bc + 2'd1;
                end
            end

            S_CID: begin
                win <= win_next;
                if (bc == 2'd3) begin
                    cid <= win_next;
                    st  <= S_CSZ;
                    bc  <= 2'd0;
                end else begin
                    bc <= bc + 2'd1;
                end
            end

            S_CSZ: begin
                win <= win_next;
                if (bc == 2'd3) begin
                    if(chunk_end>({2'b0,riff_size}+34'd8))error_o<=1;
                    csize <= csize_le;
                    bc    <= 2'd0;
                    if (cid == ID_FMT) begin
                        if (csize_le >= 32'd16) begin
                            st   <= S_FMT;
                            fcnt <= 6'd0;rate_high<=0;guid_bad<=0;
                            left <= csize_le;
                        end else begin
                            // Too short to hold the PCM fields: not a usable
                            // header, so the stream is rejected.
                            header_valid <= 1'b1;
                            unsupported  <= 1'b1;
                            audio_format <= 16'd0;
                            if (csize_le == 32'd0) begin
                                st <= S_CID;
                            end else begin
                                st   <= S_SKIP;
                                left <= csize_le + {31'd0, csize_le[0]};
                            end
                        end
                    end else if (cid == ID_DATA) begin
                        if (header_valid && !unsupported) begin
                            // Strict zero-size data is empty. File EOF is separate;
                            // tail metadata is never PCM.
                            data_seen<=1;
                            st<=(csize_le==0) ? S_CID:S_DATA;
                            data_left<=csize_le;
                            data_stream<=0;
                        end else begin
                            // data before fmt, or a stream already known not to
                            // be PCM: never emit samples for it.  The reject is
                            // sticky so a later fmt cannot re-enable streaming.
                            unsupported <= 1'b1;
                            rejected    <= 1'b1;
                            if (csize_le == 32'd0) begin
                                st <= S_CID;
                            end else begin
                                st   <= S_SKIP;
                                left <= csize_le + {31'd0, csize_le[0]};
                            end
                        end
                    end else begin
                        // Metadata or unknown chunk.  A zero-length chunk has no
                        // payload, so it must not consume the next chunk's first
                        // ID byte.
                        if (csize_le == 32'd0) begin
                            st <= S_CID;
                            bc <= 2'd0;
                        end else begin
                            st   <= S_SKIP;
                            left <= csize_le + {31'd0, csize_le[0]};
                        end
                    end
                end else begin
                    bc <= bc + 2'd1;
                end
            end

            S_FMT: begin
                if(fcnt==6 && inbyte[7:4]!=0)rate_high<=1;
                if(fcnt==7 && inbyte!=0)rate_high<=1;
                if(fcnt>=24 && fcnt<40 && guid_byte_bad)guid_bad<=1;
                case (fcnt)
                    6'd0:  fmt_code[7:0]  <= inbyte;
                    6'd1:  fmt_code[15:8] <= inbyte;
                    6'd2:  chan_w[7:0]    <= inbyte;
                    6'd3:  chan_w[15:8]   <= inbyte;
                    6'd4:  rate_w[7:0]    <= inbyte;
                    6'd5:  rate_w[15:8]   <= inbyte;
                    6'd6:  rate_w[19:16]  <= inbyte[3:0];
                    6'd14: bits_w[7:0]    <= inbyte;
                    6'd15: bits_w[15:8]   <= inbyte;
                    6'd24: sub_w[7:0]     <= inbyte;
                    6'd25: sub_w[15:8]    <= inbyte;
                    default: ;
                endcase

                if (left <= 32'd1) begin
                    // Last fmt byte: commit the metadata folded with this byte.
                    if (is_pcm_final && !rejected && !rate_high && chan_final>=1 && chan_final<=2 &&
                        (bits_final==8 || bits_final==16 || bits_final==24 || bits_final==32) &&
                        (fmt_final!=FORMAT_EXTENSIBLE || (csize>=40 && !guid_bad && !guid_byte_bad))) begin
                        audio_format <= FORMAT_PCM;
                        unsupported  <= 1'b0;
                    end else begin
                        audio_format <= is_pcm_final ? FORMAT_PCM : fmt_final;
                        unsupported  <= 1'b1;
                    end
                    channels     <= chan_final[3:0];
                    sample_rate  <= rate_final;
                    bits         <= bits_final[5:0];
                    header_valid <= 1'b1;
                    if (csize[0]) begin
                        st   <= S_SKIP;
                        left <= 32'd1;
                    end else begin
                        st   <= S_CID;
                        left <= 32'd0;
                    end
                end else begin
                    if(fcnt!=6'd63)fcnt <= fcnt + 6'd1;
                    left <= left - 32'd1;
                end
            end

            S_SKIP: begin
                if (left <= 32'd1) begin
                    left <= 32'd0;
                    st   <= S_CID;
                    bc   <= 2'd0;
                end else begin
                    left <= left - 32'd1;
                end
            end

            S_DATA: begin
                // pcm_en is asserted combinationally for the byte being
                // consumed, so the count and the emitted byte stay in step.  A
                // bounded data chunk returns to chunk parsing afterwards.
                if (!data_stream) begin
                    if (data_left <= 32'd1) begin
                        data_left <= 32'd0;
                        st        <= csize[0] ? S_SKIP:S_CID;
                        left      <= csize[0] ? 32'd1:32'd0;
                        bc        <= 2'd0;
                    end else begin
                        data_left <= data_left - 32'd1;
                    end
                end
            end

            default: st <= S_HUNT;
            endcase
            end
        end
    end
endmodule
