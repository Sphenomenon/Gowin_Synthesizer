// MP3 bit reservoir: circular main-data buffer plus the bit reader that feeds
// scalefactor and Huffman decoding.
//
// THE THING THAT MAKES MP3 FRAMES NON-INDEPENDENT. A frame's header and side
// info sit at the frame boundary, but its MAIN DATA may start up to 511 bytes
// EARLIER, in bytes carried by previous frames. `main_data_begin` says how far
// back. So the decoder cannot simply consume a frame at a time: it appends each
// frame's main data to a rolling buffer and then rewinds.
//
//   ... frame N-1 main data ... | frame N header+sideinfo | frame N main data
//                    ^                                      ^
//                    |<------- main_data_begin -------------| frame N base
//                    decoding for frame N starts here
//
// Consequences handled here:
//   * after a seek, track change or resync the buffer holds no history, so the
//     first frames are UNDECODABLE. `valid` goes low and the decoder must skip
//     them rather than emit garbage. This is normal, not an error.
//   * a Xing/Info/VBRI first frame must not enter the reservoir at all;
//     `discard` with `frame_end` rolls the write pointer back to the frame base.
//
// BUFFER: 2 KB. The spec caps main_data_begin at 511, and one frame's main data
// is at most ~1440 bytes at 320 kbps, so 2 KB always covers "previous history +
// current frame" with margin. Power of two so wrapping is free.
//
// BIT READER: the window is RIGHT-aligned and refilled with a fixed
// shift-left-by-8. That keeps refill free; only `peek` needs a barrel shifter,
// and only one. A left-aligned window would need a variable shift on every
// refill instead, which is the more expensive half.
module mp3_reservoir #(
    parameter AW = 11                 // 2^11 = 2048 bytes
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        restart,       // new track/seek: drop all history

    // ---- write side (main data from mp3_bitstream) ----
    input  wire        frame_mark,    // pulse at side_done: latch this frame's base
    input  wire        wr,
    input  wire [7:0]  wdata,
    input  wire        frame_end,     // pulse at main_done
    input  wire        discard,       // with frame_end: undo this frame

    // ---- frame positioning ----
    input  wire [8:0]  main_data_begin,
    input  wire        start,         // pulse: position for the marked frame
    output reg         valid,         // enough history existed; else skip frame

    // ---- bit read port ----
    output wire        ready,         // >= 24 bits buffered, safe to peek
    output wire [23:0] peek,          // next 24 bits, MSB first
    input  wire        skip,          // pulse: consume skip_n bits
    input  wire [4:0]  skip_n,        // 1..24

    // Absolute reposition within the frame's decode window. The reference ends
    // each granule with `bs->pos = layer3gr_limit`, which can move BACKWARD:
    // its Huffman loops read a codeword and only then test the limit, so they
    // routinely overshoot by a few bits and rewind. Skipping forward cannot
    // express that, and forcing the loops to stop short instead drops the last
    // count1 values of any granule whose data ends on the boundary.
    // Lands on the containing BYTE; the caller skips the remaining 0..7 bits.
    input  wire        seek,
    input  wire [17:0] seek_bits,
    output reg  [17:0] bits_read      // since `start`, for part2_3_length checks
);
    localparam DEPTH = (1 << AW);

    reg [7:0]  mem [0:DEPTH-1];

    // The 24-bit peek window runs ahead of the granule limit, so the last few
    // bytes it touches can be past the frame's main data -- legitimately, since
    // those bits are discarded at layer3gr_limit. On hardware BSRAM reads back
    // zero there and the reference's bit reader returns 0 past its own limit,
    // so zero is the CORRECT value, not merely a convenient one. Without this,
    // simulation returned X, which propagated into the bit count and deadlocked
    // the Huffman decoder on l3-si.
    integer mi;
    // Gowin's elaborator limits one generate/initial loop to 2000 iterations.
    // Keep the deterministic simulation initialization while splitting the
    // 2 KiB reservoir into two legal 1024-entry loops.  The inferred BSRAM is
    // still one logical circular buffer; this is only a parser workaround.
    initial begin
        for (mi = 0; mi < 1024; mi = mi + 1) mem[mi] = 8'd0;
        for (mi = 1024; mi < DEPTH; mi = mi + 1) mem[mi] = 8'd0;
    end
    reg [AW-1:0] wptr;
    reg [AW-1:0] frame_base;          // wptr at the start of this frame's main data
    reg [AW:0]   filled;              // bytes ever written, saturating at DEPTH
    reg [AW:0]   filled_at_mark;      // ...as of this frame's boundary

    // ---- write path --------------------------------------------------------
    always @(posedge clk) begin
        if (wr) mem[wptr] <= wdata;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wptr <= 0; frame_base <= 0; filled <= 0; filled_at_mark <= 0;
        end else if (restart) begin
            wptr <= 0; frame_base <= 0; filled <= 0; filled_at_mark <= 0;
        end else begin
            // Latch the history depth AS OF the frame boundary. `filled` keeps
            // counting through this frame's own main data, and testing against
            // that let a frame be decoded on the strength of bytes it supplied
            // itself: with main_data_begin=461 and 382-byte frames, frame 1 was
            // accepted on 764 "available" bytes when only 382 preceded it. The
            // reference rejects frames 0 and 1 and starts at 2; so does this now.
            if (frame_mark) begin
                frame_base     <= wptr;
                filled_at_mark <= filled;
            end

            if (wr) begin
                wptr <= wptr + 1'b1;
                if (filled < DEPTH) filled <= filled + 1'b1;
            end

            // A tag frame never becomes part of the reservoir.
            if (frame_end && discard) begin
                wptr   <= frame_base;
                // `filled` is history depth, not occupancy; rolling it back by
                // the discarded frame's length would need the length, and
                // over-counting only makes `valid` optimistic for one frame
                // which is then skipped anyway. Leave it.
            end
        end
    end

    // ---- read pointer / positioning ---------------------------------------
    // The memory read is REGISTERED. Reading mem[] combinationally inside a
    // clocked block is the async-read trap that cost ~9.7k LUT4 in the vendor
    // SD core; a registered read is what lets yosys infer BSRAM here too.
    reg [AW-1:0] rptr;
    reg [7:0]    mem_q;
    always @(posedge clk) mem_q <= mem[rptr];

    reg [31:0] acc;
    reg [5:0]  cnt;          // valid bits live in the LOW `cnt` bits of acc
    reg        armed;        // mem_q now corresponds to the current rptr

    wire [AW-1:0] start_addr = frame_base - {2'b0, main_data_begin};
    reg  [AW-1:0] base_addr;          // start_addr, held for `seek`
    wire          have_hist  = (filled_at_mark >= {2'b0, main_data_begin});

    // Refill while a whole byte still fits. cnt caps at 32, so only refilling
    // at or below 24 keeps the shift-left-by-8 lossless.
    wire do_refill = armed && (cnt <= 6'd24);

    // Single place where cnt moves, so refill and skip cannot fight.
    reg [5:0] cnt_next;
    always @(*) begin
        cnt_next = cnt;
        if (do_refill) cnt_next = cnt_next + 6'd8;
        if (skip)      cnt_next = cnt_next - {1'b0, skip_n};
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rptr <= 0; acc <= 0; cnt <= 0; armed <= 1'b0;
            valid <= 1'b0; bits_read <= 0; base_addr <= 0;
        end else if (seek) begin
            // The circular RAM address is AW bits; higher seek bits are the
            // absolute stream position and intentionally wrap here.
            rptr      <= base_addr + seek_bits[AW+2:3];
            acc       <= 0;
            cnt       <= 0;
            armed     <= 1'b0;
            bits_read <= {seek_bits[17:3], 3'b000};
        end else if (restart || start) begin
            // `start` repositions to (frame base - main_data_begin) and throws
            // the window away; `armed` clears so the first byte is fetched from
            // the NEW rptr rather than a stale mem_q.
            rptr      <= restart ? {AW{1'b0}} : start_addr;
            base_addr <= restart ? {AW{1'b0}} : start_addr;
            acc       <= 0;
            cnt       <= 0;
            armed     <= 1'b0;
            bits_read <= 0;
            valid     <= restart ? 1'b0 : have_hist;
        end else begin
            if (!armed) begin
                armed <= 1'b1;            // mem_q catches up with rptr
            end else if (do_refill) begin
                acc   <= (acc << 8) | {24'b0, mem_q};
                rptr  <= rptr + 1'b1;
                armed <= 1'b0;            // new rptr needs a cycle again
            end

            cnt <= cnt_next;
            if (skip) bits_read <= bits_read + {13'b0, skip_n};
        end
    end

    assign ready = (cnt >= 6'd24);
    // Right-aligned window: the next 24 bits sit at the top of the valid region.
    assign peek  = ready ? acc[cnt - 6'd1 -: 24] : 24'd0;
endmodule
