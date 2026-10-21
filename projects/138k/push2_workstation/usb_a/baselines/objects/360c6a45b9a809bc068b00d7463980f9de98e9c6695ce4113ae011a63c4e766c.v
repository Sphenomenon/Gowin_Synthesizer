// WAV header parser: locks onto the "RIFF....WAVE" magic, extracts the fields
// the audio path needs, then passes PCM bytes through.
//
// SELF-SYNCHRONISING BY DESIGN, and that is the point. The original (inherited
// from tang_fm_transmitter) just counted the first 44 bytes after a `restart`
// pulse as the header. That is wrong across a track change: `player_ctrl`
// pulses flush/track_start together, but `sd_file_reader` only switches files
// at a SECTOR boundary, so the tail of the previous track's in-flight sector
// still arrives afterwards. Those stale bytes got counted as the new header,
// and the sample rate came out of whatever PCM happened to sit at offsets
// 24..26 -- observed on hardware as 0x40423 (263203 Hz) and 0x8f1c4 on tracks
// after the first, with the DAC then running ~8x too fast.
//
// Hunting for the magic instead makes the parser immune to however many stale
// bytes precede the real file, without needing to reason about SD latency.
//
// False-lock guard: PCM data can contain the bytes "RIFF" by chance (1 in 2^32
// per position, which over a 20 MB file is not negligible), so hunting is only
// armed while `hdr_done` is low. Once locked, the magic is ignored until the
// next `restart`. The "WAVE" tag at offset 8 is also checked, and a mismatch
// drops back to hunting.
//
// Canonical header offsets (little-endian):
//   0..3 "RIFF"   4..7 size      8..11 "WAVE"    12..15 "fmt "
//   22..23 channels   24..27 sample rate   34..35 bits    36..39 "data"
module wav_parser (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        restart,      // pulse on track change
    input  wire        inen,
    input  wire [7:0]  inbyte,
    output reg         pcm_en,
    output reg  [7:0]  pcm_byte,
    output reg  [19:0] sample_rate,  // Hz; 44100 default until parsed
    output reg         stereo,       // 1 = 2 or more channels
    output reg  [5:0]  bits,         // bits per sample (expect 16)
    output reg         hdr_done
);
    localparam [31:0] MAGIC_RIFF = "RIFF";
    localparam [31:0] MAGIC_WAVE = "WAVE";

    reg [31:0] sr;        // rolling last 4 bytes
    reg [5:0]  cnt;       // header byte index once locked
    reg        hunting;

    wire [31:0] sr_next = {sr[23:0], inbyte};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sr          <= 32'h0;
            cnt         <= 6'd0;
            hunting     <= 1'b1;
            sample_rate <= 20'd44_100;
            stereo      <= 1'b1;
            bits        <= 6'd16;
            hdr_done    <= 1'b0;
            pcm_en      <= 1'b0;
            pcm_byte    <= 8'h0;
        end else begin
            pcm_en <= 1'b0;

            if (restart) begin
                sr          <= 32'h0;
                cnt         <= 6'd0;
                hunting     <= 1'b1;
                hdr_done    <= 1'b0;
                sample_rate <= 20'd44_100;
                stereo      <= 1'b1;
                bits        <= 6'd16;
            end else if (inen) begin
                sr <= sr_next;

                if (hunting) begin
                    // Discard everything until the RIFF magic. sr_next holds
                    // bytes 0..3 at the moment it matches, so the next byte in
                    // is header index 4.
                    if (sr_next == MAGIC_RIFF) begin
                        hunting <= 1'b0;
                        cnt     <= 6'd4;
                    end
                end else if (cnt < 6'd44) begin
                    cnt <= cnt + 1'b1;
                    case (cnt)
                        6'd11: if (sr_next != MAGIC_WAVE) begin
                                   // "RIFF" was a coincidence, not a header
                                   hunting <= 1'b1;
                                   cnt     <= 6'd0;
                               end
                        6'd22: stereo             <= (inbyte >= 8'd2);
                        6'd24: sample_rate[ 7:0]  <= inbyte;
                        6'd25: sample_rate[15:8]  <= inbyte;
                        6'd26: sample_rate[19:16] <= inbyte[3:0];
                        6'd34: bits               <= inbyte[5:0];
                        default: ;
                    endcase
                    if (cnt == 6'd43)
                        hdr_done <= 1'b1;
                end else begin
                    pcm_en   <= 1'b1;
                    pcm_byte <= inbyte;
                end
            end
        end
    end
endmodule
