// MP3 frame framer: takes the raw byte stream off the SD reader and splits it
// into header fields, side-info bytes and main-data bytes.
//
// Scope is MPEG-1 Layer III (Phase 1). MPEG-2/2.5, Layer I/II, and free-format
// streams are rejected at validation and the framer resyncs rather than trying
// to decode them.
//
// CONTAINER JUNK is handled here because it has to be: real files start with an
// ID3v2 tag (often tens of kilobytes of album art) and frequently carry a
// Xing/Info/LAME header in an otherwise-silent first frame. The reference
// decoder in tools/mp3ref does exactly the same two skips, deliberately -- it
// was written first so that it doubles as the spec for this module.
//
// SYNC is not just "find 0xFF Ex". PCM data contains that pattern constantly,
// so a candidate header is only accepted if it also validates: MPEG-1, Layer
// III, a real bitrate index (not 0=free or 15=bad) and a real sample-rate index
// (not 3=reserved). A false lock costs one frame and resyncs.
module mp3_bitstream (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        restart,        // pulse: new file, re-arm ID3/Xing skip

    // BACKPRESSURE. mp3_sideinfo holds ONE frame's fields, so parsing frame N+1
    // while frame N is still being decoded silently overwrites them -- found
    // during M4 when stereo (four gr/ch sets) failed and mono (two) did not.
    //
    // An explicit ACK PULSE, not a level. A level fails: the consumer can only
    // raise it a cycle after main_done, but S_HOLD is entered ON main_done and
    // would sample it still low and leave immediately. Waiting for a pulse has
    // no such race.
    input  wire        frame_ack,
    // Deasserted while parked. There is no elastic buffer inside the framer,
    // so bytes offered during a hold are simply LOST -- the source (the SD byte
    // FIFO) has to wait. Ignoring this cost two frames of every three in the
    // first integration run: the framer resumed mid-frame and had to hunt for
    // the next sync each time.
    output wire        in_ready,

    // byte stream in
    input  wire        inen,
    input  wire [7:0]  inbyte,

    // header, valid one cycle with hdr_valid
    output reg         hdr_valid,
    output reg  [3:0]  bitrate_idx,
    output reg  [1:0]  samplerate_idx,
    output reg  [19:0] samplerate_hz,
    output reg  [1:0]  mode,           // 0=stereo 1=joint 2=dual 3=mono
    output reg  [1:0]  mode_ext,
    output reg         crc_present,
    output reg         is_mono,
    output reg  [10:0] frame_bytes,

    // side info bytes (32 for stereo, 17 for mono)
    output reg         side_en,
    output reg  [7:0]  side_byte,
    output reg         side_done,      // pulse after the last side-info byte

    // main data bytes -> reservoir
    output reg         main_en,
    output reg  [7:0]  main_byte,
    output reg         main_done,      // pulse after the last main-data byte
    output reg         main_discard,   // with main_done: that frame was a
                                       // Xing/Info/VBRI tag, roll the
                                       // reservoir write pointer back

    // status
    output reg  [15:0] frame_count,
    output reg  [15:0] resync_count
);
    reg [7:0] h1, h2, h3;      // header bytes 1..3 (byte 0 is the 0xFF sync)

    // ---- frame size ROM ----------------------------------------------------
    // floor(144000*kbps/fs); index = bitrate_idx*4 + samplerate_idx. A ROM
    // instead of a divider: both indices are tiny and this is once per frame.
    // Address driven COMBINATIONALLY from the already-latched h2, not assigned
    // in S_HDR: sync_rom registers its read, so an address set at the S_HDR
    // edge would not produce data until one cycle after S_SIZE looks at it.
    // (That off-by-one made 64 kbps @ 48 kHz report 216 bytes instead of 192.)
    wire [10:0] fsz_rom;
    wire [5:0]  fsz_addr = {h2[7:4], h2[3:2]};
    sync_rom #(.AW(6), .DW(11), .INIT("src/storage/tang_mp3/mp3/tables/frame_size.memh")) u_fsz (
        .clk(clk), .addr(fsz_addr), .data(fsz_rom)
    );

    localparam [3:0] S_ID3     = 4'd0,   // maybe skip an ID3v2 tag at file start
                     S_ID3SKIP = 4'd1,
                     S_SYNC    = 4'd2,   // hunt 0xFF Ex
                     S_HDR     = 4'd3,   // collect header bytes 1..3
                     S_SIZE    = 4'd4,   // ROM latency + validation
                     S_CRC     = 4'd5,
                     S_SIDE    = 4'd6,
                     S_MAIN    = 4'd7,
                     S_HOLD    = 4'd8;   // frame done, waiting on the decoder

    reg [3:0]  st;
    assign in_ready = (st != S_HOLD);

    reg [1:0]  hidx;
    reg [27:0] skip_cnt;
    reg [10:0] left;                 // bytes remaining in the current section
    reg [5:0]  side_len;
    reg [3:0]  id3_idx;
    reg        seen_first_frame;     // Xing check applies to frame 0 only
    reg [31:0] tagwin;               // rolling 4 bytes, for Xing/Info/VBRI
    reg [7:0]  xing_pos;

    // header field decode (combinational on the latched bytes)
    wire       h_mpeg1     = (h1[4:3] == 2'b11);
    wire       h_layer3    = (h1[2:1] == 2'b01);
    wire       h_crc       = ~h1[0];             // 0 = protection present
    wire [3:0] h_br        = h2[7:4];
    wire [1:0] h_sr        = h2[3:2];
    wire       h_pad       = h2[1];
    wire [1:0] h_mode      = h3[7:6];
    wire [1:0] h_modeext   = h3[5:4];
    wire       h_mono      = (h3[7:6] == 2'b11);
    wire       h_valid     = h_mpeg1 & h_layer3 &
                             (h_br != 4'd0) & (h_br != 4'd15) &
                             (h_sr != 2'd3);

    function [19:0] sr_hz(input [1:0] i);
        case (i)
            2'd0: sr_hz = 20'd44100;
            2'd1: sr_hz = 20'd48000;
            2'd2: sr_hz = 20'd32000;
            default: sr_hz = 20'd44100;
        endcase
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_ID3; hidx <= 0; id3_idx <= 0; skip_cnt <= 0;
            left <= 0; side_len <= 0; seen_first_frame <= 1'b0;
            tagwin <= 0; xing_pos <= 0;
            hdr_valid <= 0; side_en <= 0; side_done <= 0;
            main_en <= 0; main_done <= 0; main_discard <= 0;
            frame_count <= 0; resync_count <= 0;
            bitrate_idx <= 0; samplerate_idx <= 0; samplerate_hz <= 20'd44100;
            mode <= 0; mode_ext <= 0; crc_present <= 0; is_mono <= 0;
            frame_bytes <= 0; side_byte <= 0; main_byte <= 0;
            h1 <= 0; h2 <= 0; h3 <= 0;
        end else begin
            hdr_valid <= 1'b0;
            side_en   <= 1'b0;
            side_done <= 1'b0;
            main_en      <= 1'b0;
            main_done    <= 1'b0;
            main_discard <= 1'b0;

            if (restart) begin
                st <= S_ID3; hidx <= 0; id3_idx <= 0; skip_cnt <= 0;
                seen_first_frame <= 1'b0; tagwin <= 0;
            end else case (st)

            // ---- optional ID3v2 tag at the very start ----------------------
            // "ID3", ver(2), flags(1), syncsafe size(4). Bit 4 of flags adds a
            // 10-byte footer. Anything that is not a tag falls straight into
            // the sync hunt with the byte preserved.
            S_ID3: if (inen) begin
                case (id3_idx)
                    // Falling through to S_SYNC must NOT swallow this byte:
                    // a stream with no ID3 tag starts with 0xFF, and dropping
                    // it made the framer miss frame 0 entirely and false-lock
                    // on a later 0xFF. Carry the byte into the sync state by
                    // seeding hidx from it.
                    4'd0: if (inbyte == "I") id3_idx <= 4'd1;
                          else begin st <= S_SYNC;
                                     hidx <= (inbyte == 8'hFF) ? 2'd1 : 2'd0; end
                    4'd1: if (inbyte == "D") id3_idx <= 4'd2;
                          else begin st <= S_SYNC; id3_idx <= 0;
                                     hidx <= (inbyte == 8'hFF) ? 2'd1 : 2'd0; end
                    4'd2: if (inbyte == "3") id3_idx <= 4'd3;
                          else begin st <= S_SYNC; id3_idx <= 0;
                                     hidx <= (inbyte == 8'hFF) ? 2'd1 : 2'd0; end
                    4'd3, 4'd4: id3_idx <= id3_idx + 1'b1;      // version
                    4'd5: begin                                  // flags
                              skip_cnt <= inbyte[4] ? 28'd10 : 28'd0;
                              id3_idx  <= 4'd6;
                          end
                    4'd6: begin skip_cnt <= skip_cnt + {21'b0, inbyte[6:0]} * 28'd2097152;
                                id3_idx <= 4'd7; end
                    4'd7: begin skip_cnt <= skip_cnt + {21'b0, inbyte[6:0]} * 28'd16384;
                                id3_idx <= 4'd8; end
                    4'd8: begin skip_cnt <= skip_cnt + {21'b0, inbyte[6:0]} * 28'd128;
                                id3_idx <= 4'd9; end
                    4'd9: begin skip_cnt <= skip_cnt + {21'b0, inbyte[6:0]};
                                id3_idx <= 0;
                                st      <= S_ID3SKIP; end
                    default: id3_idx <= 0;
                endcase
            end

            S_ID3SKIP: if (inen) begin
                if (skip_cnt <= 28'd1) st <= S_SYNC;
                else                   skip_cnt <= skip_cnt - 28'd1;
            end

            // ---- frame sync -------------------------------------------------
            S_SYNC: if (inen) begin
                if (hidx == 2'd0) begin
                    if (inbyte == 8'hFF) hidx <= 2'd1;
                end else begin
                    // second byte must have the top 3 sync bits set
                    if (inbyte[7:5] == 3'b111) begin
                        h1   <= inbyte;
                        hidx <= 2'd0;
                        st   <= S_HDR;
                    end else begin
                        // not a header; the byte itself may start the next one
                        hidx <= (inbyte == 8'hFF) ? 2'd1 : 2'd0;
                    end
                end
            end

            S_HDR: if (inen) begin
                if (hidx == 2'd0) begin h2 <= inbyte; hidx <= 2'd1; end
                else begin
                    h3   <= inbyte;
                    hidx <= 2'd0;
                    st   <= S_SIZE;
                end
            end

            // ROM data lands the cycle after fsz_addr was set; validate here.
            S_SIZE: begin
                if (!h_valid) begin
                    resync_count <= resync_count + 1'b1;
                    st <= S_SYNC;
                end else begin
                    bitrate_idx    <= h_br;
                    samplerate_idx <= h_sr;
                    samplerate_hz  <= sr_hz(h_sr);
                    mode           <= h_mode;
                    mode_ext       <= h_modeext;
                    crc_present    <= h_crc;
                    is_mono        <= h_mono;
                    frame_bytes    <= fsz_rom + {10'b0, h_pad};
                    side_len       <= h_mono ? 6'd17 : 6'd32;
                    hdr_valid      <= 1'b1;

                    // bytes left after the 4-byte header
                    left <= fsz_rom + {10'b0, h_pad} - 11'd4;
                    st   <= h_crc ? S_CRC : S_SIDE;
                end
            end

            S_CRC: if (inen) begin
                // two CRC bytes, not checked (Phase 1): a bad CRC would only
                // tell us to mute a frame we can already detect as garbage
                if (hidx == 2'd0) begin hidx <= 2'd1; left <= left - 11'd1; end
                else begin hidx <= 2'd0; left <= left - 11'd1; st <= S_SIDE; end
            end

            S_SIDE: if (inen) begin
                side_en   <= 1'b1;
                side_byte <= inbyte;
                left      <= left - 11'd1;
                if (side_len == 6'd1) begin
                    side_done <= 1'b1;
                    xing_pos  <= 8'd0;
                    tagwin    <= 32'd0;
                    st        <= S_MAIN;
                end else begin
                    side_len <= side_len - 6'd1;
                end
            end

            // Main data always streams to the reservoir. A Xing/Info/VBRI tag
            // sits at the start of the FIRST frame's main data, so the first 4
            // bytes are sniffed on the way past; if they turn out to be a tag,
            // main_discard fires with main_done and the reservoir rolls its
            // write pointer back to the frame start.
            //
            // Sniffing without emitting would have been simpler but wrong: when
            // the bytes are NOT a tag they are real main data and would have to
            // be replayed. Emitting and rolling back needs no replay path.
            S_MAIN: if (inen) begin
                main_en   <= 1'b1;
                main_byte <= inbyte;

                if (!seen_first_frame && xing_pos < 8'd4) begin
                    tagwin   <= {tagwin[23:0], inbyte};
                    xing_pos <= xing_pos + 8'd1;
                end

                if (left <= 11'd1) begin
                    main_done        <= 1'b1;
                    main_discard     <= ~seen_first_frame &
                                        ((tagwin == "Xing") ||
                                         (tagwin == "Info") ||
                                         (tagwin == "VBRI"));
                    seen_first_frame <= 1'b1;
                    frame_count      <= frame_count + 1'b1;
                    st               <= S_HOLD;
                    hidx             <= 2'd0;
                end else begin
                    left <= left - 11'd1;
                end
            end

            S_HOLD: if (frame_ack) st <= S_SYNC;

            default: st <= S_SYNC;
            endcase
        end
    end
endmodule
