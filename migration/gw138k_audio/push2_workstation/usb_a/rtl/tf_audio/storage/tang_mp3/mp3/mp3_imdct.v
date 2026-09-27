`include "mp3_mul.vh"
// IMDCT + windowing + overlap-add: 576 spectral coefficients -> 576 subband
// samples, per channel per granule.
//
// Evaluated DIRECTLY rather than via the reference's factored DCT:
//
//   raw[n]   = sum(k=0..17) x[k] * cos(pi/72 * (2n+19) * (2k+1))     n = 0..35
//   w[n]     = raw[n] * window[block_type][n]
//   out[n]   = overlap[n] + w[n]                                     n = 0..17
//   overlap' = w[18..35]
//
// 18 MACs per output, 648 per band, ~41k per granule-channel. The frame budget
// at 54 MHz is 1.4M cycles, so the naive form fits several times over and there
// is no reason to carry a butterfly network's index bookkeeping.
//
// WHY THIS DIFFERS FROM THE REFERENCE'S OVERLAP. minimp3 stores nine
// UNWINDOWED values per band and applies the *current* granule's window to the
// previous granule's tail, which is valid only because MP3's window-switching
// rules guarantee w_prev[18+n] == w_cur[17-n]. That is why it needs just two
// window tables and treats START and NORMAL as the same. Here the real
// 36-point window is applied and the WINDOWED tail is stored, so all three
// window shapes are distinct and the equality above is never relied on. The
// outputs agree; the internal state does not, so overlap must not be diffed
// against the reference -- only subband.txt is meaningful.
//
// SHORT BLOCKS are three 12-point transforms per band, deposited at offsets
// 6, 12 and 18 of the 36-sample frame, leaving [0..5] and [30..35] zero.
//
// Q28 THROUGHOUT (ceiling 8.0). Measured across the in-scope compliance
// vectors: raw peaks at 4.760 and the post-overlap output at 3.887, so Q29
// would have left 3% of headroom on the output and none on raw.
module mp3_imdct (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    input  wire        flush,          // drop overlap state (new track / seek)

    input  wire        ch,
    input  wire        window_switching,
    input  wire [1:0]  block_type,
    input  wire        mixed_block,

    // Shared multiplier (owned by mp3_decoder). The stages run strictly one at
    // a time, so five private multipliers were five times the area for no
    // parallelism -- together they were over half the decoder.
    output wire signed [31:0] mul_a,

    output wire signed [21:0] mul_b,
    input  wire signed [53:0] mul_p,
    output reg         mul_go,      // 1-cycle request; latency = `MUL_WAIT (mp3_mul.vh)


    output reg         done,

    // mp3_spectra read port
    output reg  [10:0] rd_addr,
    input  wire signed [31:0] rd_data,

    // subband output -> mp3_spectra (write port). IN PLACE: a whole band is
    // loaded into the xin ring before any output is written, and the sequencer
    // finishes one channel completely before touching the other, so the band's
    // spectra are dead by the time the samples land on them. That retires a
    // second 1152 x 32 buffer and its address muxing.
    output reg         wr_en,
    output reg  [10:0] wr_addr,
    output reg  signed [31:0] wr_data
);
    localparam [10:0] COS_BASE   = 11'd0;
    localparam [10:0] WIN_BASE   = 11'd648;
    localparam [10:0] COS12_BASE = 11'd756;
    localparam [10:0] WIN12_BASE = 11'd828;

    reg  [5:0]  b;              // band 0..31
    reg  [9:0]  rom_addr;
    wire [21:0] rom_data;
    sync_rom #(.AW(10), .DW(22), .INIT("src/storage/tang_mp3/mp3/tables/imdct.memh")) u_rom (
        .clk(clk), .addr(rom_addr), .data(rom_data));

    wire [1:0] bt = window_switching ? block_type : 2'd0;
    wire       is_short = (bt == 2'd2);
    // mixed_block_flag ALONE, not gated on block_type: the reference computes
    // n_long_bands from the flag and applies it to start and stop blocks too,
    // where n_short_sfb is zero and nothing is reordered but the first two
    // bands still take the NORMAL window. Gating on block_type gave a mixed
    // start/stop block the start/stop window on bands 0-1, whose tail then
    // failed to line up with the next granule's head -- errors around 1e-4,
    // three orders above the quantization floor.
    //
    // MPEG-1 only: the reference's `<< (HDR_GET_MY_SAMPLE_RATE == 2)` cannot
    // fire here, because that macro yields 6..8 for MPEG-1.
    wire [5:0] n_long_bands = mixed_block ? 6'd2 : 6'd0;
    // 0 = normal, 1 = start, 2 = stop
    wire [1:0] win_type = (bt == 2'd1) ? 2'd1 : (bt == 2'd3) ? 2'd2 : 2'd0;
    // The long bands of a mixed block always use the normal window.
    wire [1:0] cur_win  = (b < n_long_bands) ? 2'd0 : win_type;

    // ---- overlap state (persists across granules) --------------------------
    // Packed as ch*576 + index, NOT {ch, index}: the latter puts channel 1 at
    // 1024 and walks off a 1152-word array above index 127. See mp3_spectra.
    // ONE 32-bit array (SPX9 @ BIT_WIDTH=36). This was briefly split into four
    // byte-wide arrays while chasing what turned out to be a TIMING bug in the
    // synthesis accumulator, not a memory-configuration one -- the subband
    // checksum was varying build to build, which a memory fault never does.
    // The split was never independently justified, and it cost placement:
    // o36 in particular became 24 RAM16SDP4 cells, which the placer could not
    // site once the m7 UI was added. Verified bit-exact on hardware unsplit.
    reg signed [31:0] ovl [0:1151];
    reg  [10:0] ovl_addr;
    reg  signed [31:0] ovl_wdata, ovl_rdata;
    reg         ovl_we;
    wire [10:0] ovl_a = ovl_addr[10] ? (11'd576 + {1'b0, ovl_addr[9:0]})
                                     : {1'b0, ovl_addr[9:0]};
    always @(posedge clk) begin
        if (ovl_we) ovl[ovl_a] <= ovl_wdata;
        ovl_rdata <= ovl[ovl_a];
    end

    // ---- subband output ----------------------------------------------------
    // ---- the band's 18 inputs, as a rotating ring --------------------------
    // A ring, not an addressed register file: the MAC loop always consumes the
    // head. The long path rotates by 1 (k = 0,1,2,...) and the short path by 3
    // (k = j, j+3, j+6, ...); both return to the identity after 18 steps, so
    // successive outputs see the same starting order without any reload.
    reg signed [31:0] xin [0:17];
    integer xi;

    // ---- the 36-sample windowed frame --------------------------------------
    reg signed [31:0] o36 [0:35];
    reg  [5:0]  o36_addr;
    reg  signed [31:0] o36_wdata, o36_rdata;
    reg         o36_we;
    always @(posedge clk) begin
        if (o36_we) o36[o36_addr] <= o36_wdata;
        o36_rdata <= o36[o36_addr];
    end

    // ---- one shared multiplier ---------------------------------------------
    // Reused by the MAC and the window multiply. 32x18, NOT 32x32: this
    // toolchain infers no DSP, so a 32x32 costs 3881 LUT4 against 1469 for
    // 32x18. The ROM keeps its Q30 words -- narrowing happens here, at the
    // point of use, so the table stays the precise source of truth and the
    // trade-off is visible in one place.
    //
    // Q20, not Q16: Q16 was tried and left only 1.45x margin on the ISO
    // max-absolute-error limit at the subband stage, with the filterbank still
    // to come. The two loudest compliance vectors failed. Q20 costs 3162 LUT4
    // against 1469 and puts the coefficient error at 2.0e-6.
    reg  signed [31:0] m_a;
    reg  signed [21:0] m_b;
    wire signed [53:0] m_p = mul_p[53:0];
    assign mul_a = m_a;
    assign mul_b = m_b;

    // 18 products of (<=2^31) x (<=2^21) reach 18*2^52 ~ 2^56.2, so 60 bits
    // signed leaves slack. A wrapped accumulator is a silent, data-dependent
    // fault, so it is sized generously.
    // NOT SPLIT -- deliberately. The same two-half pipelined-carry trick that
    // fixed mp3_synth makes THIS stage worse: it moves the long chain out of the
    // accumulate path and into the READ path (acc_hi + carry, reconstructed on
    // every use), and here the reconstructed value feeds raw_q28 and the whole
    // windowing tail rather than one write per output. Measured on the board:
    // with the split, the subband checksum is wrong at 36 MHz; without it, the
    // decoder is bit-exact at 36. Leave it whole.
    reg  signed [59:0] acc;

    // acc is Q49 (Q29 data x Q20 coefficient). Q28 output -> >>> 21, rounded.
    // ROUNDING WITHOUT A WIDE ADD. `(acc + half) >>> n` is a full-width carry
    // chain -- 60 bits here -- purely to round. Adding the shifted-out bit to
    // the NARROW result is identical for round-half-up and leaves a chain the
    // width of the output. nextpnr could not legalize the long version at high
    // utilization; Gowin needs ALU chains in contiguous slices.
    wire signed [38:0] raw_q28 = acc[59:21] + {38'd0, acc[20]};

    // Q28 x Q20 -> Q48, back to Q28 with >>> 20, rounded.
    wire signed [33:0] win_q28 = m_p[53:20] + {33'd0, m_p[19]};

    wire signed [21:0] coef_q20 = $signed(rom_data);

    // One saturation helper, widest case. Everything narrower is sign-extended
    // to 40 bits at the call site so the comparison is unambiguous -- mixing
    // widths in a signed compare is how the requant overflow hid for a while.
    function signed [31:0] sat40 (input signed [39:0] v);
        sat40 = (v >  40'sd2147483647) ? 32'sh7FFFFFFF
              : (v < -40'sd2147483648) ? 32'sh80000000
              :                          v[31:0];
    endfunction
    function signed [39:0] sx32 (input signed [31:0] v);
        sx32 = {{8{v[31]}}, v};
    endfunction
    function signed [39:0] sx34 (input signed [33:0] v);
        sx34 = {{6{v[33]}}, v};
    endfunction
    function signed [39:0] sx39 (input signed [38:0] v);
        sx39 = {v[38], v};
    endfunction

    localparam [4:0]
        S_IDLE   = 5'd0,  S_FLUSH  = 5'd1,
        S_LD_A   = 5'd2,  S_LD_B   = 5'd3,  S_LD_C = 5'd4,
        S_ZERO   = 5'd5,
        S_MAC_A  = 5'd6,  S_MAC_B  = 5'd7,  S_MAC_C = 5'd8, S_MAC_D = 5'd9,
        S_WIN_A  = 5'd10, S_WIN_B  = 5'd11, S_WIN_C = 5'd12,
        S_DEP_RD = 5'd13, S_DEP_W  = 5'd14, S_DEP_WR = 5'd15,
        S_OUT_A  = 5'd16, S_OUT_B  = 5'd17, S_OUT_C = 5'd18,
        S_NEXTB  = 5'd19, S_DONE   = 5'd20,
        S_MAC_W  = 5'd21, S_WIN_W  = 5'd22;

    reg [4:0] st;
    reg [5:0] n;            // output index within the transform
    reg [4:0] k;            // taps ISSUED so far
    reg [4:0] nacc_i;       // taps ACCUMULATED so far
    reg [1:0] j;            // short-block window 0..2
    reg [5:0] emit_n;       // 0..35 during the emit walk
    reg [10:0] flush_i;
    // The overlap RAM must be cleared before the FIRST granule, not only on a
    // track change. Gowin BSRAM happens to power up zeroed, so on hardware this
    // would have looked fine while simulation returned X -- and it would still
    // have been wrong after the first seek.
    reg       need_flush;
    reg       band_short;   // this band uses the 12-point path
    reg [5:0] taps;         // 18 (long) or 6 (short)
    reg [2:0] mwait;

    // Band base addresses, stepped rather than recomputed. `b * 18 + n` appeared
    // in five places; each is a constant multiply plus an add, and on this device
    // ALU cells may occupy only three of every four LUT positions, so at high
    // density ALU count is what runs out first. Cursors replace all of them.
    reg [9:0] bbase;                       // b * 18, into the spectra RAM
    reg [9:0] cbase;                       // n * 18, into the cosine table   // see mp3_mul.vh
    reg [5:0] depos;        // where this output lands in the 36-frame
    reg       accum;        // deposit adds to what is already there

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; done <= 0; rd_addr <= 0; rom_addr <= 0;
            ovl_addr <= 0; ovl_wdata <= 0; ovl_we <= 0;
            wr_addr <= 0; wr_data <= 0; wr_en <= 0;
            o36_addr <= 0; o36_wdata <= 0; o36_we <= 0;
            m_a <= 0; m_b <= 0; acc <= 0; mwait <= 0; mul_go <= 0;
            b <= 0; n <= 0; k <= 0; j <= 0; emit_n <= 0; flush_i <= 0;
            bbase <= 0; cbase <= 0;
            need_flush <= 1'b1;
            band_short <= 0; taps <= 0; depos <= 0; accum <= 0; nacc_i <= 0;
            for (xi = 0; xi < 18; xi = xi + 1) xin[xi] <= 0;
        end else begin
            done   <= 1'b0;
            mul_go <= 1'b0;
            ovl_we <= 1'b0;
            wr_en  <= 1'b0;
            o36_we <= 1'b0;

            case (st)
            S_IDLE: begin
                if (flush || need_flush) begin
                    flush_i    <= 11'd0;
                    need_flush <= 1'b0;
                    st         <= S_FLUSH;
                end else if (start) begin
                    b          <= 6'd0;
                    bbase      <= 10'd0;
                    band_short <= is_short && (n_long_bands == 6'd0);
                    rd_addr    <= {ch, 10'd0};
                    k          <= 5'd0;
                    st         <= S_LD_A;
                end
            end

            // Zero the overlap history. Without this a track change carries the
            // previous track's tail into the first granule of the new one.
            S_FLUSH: begin
                ovl_we    <= 1'b1;
                ovl_addr  <= flush_i;
                ovl_wdata <= 32'sd0;
                if (flush_i == 11'd1151) st <= S_IDLE;
                else flush_i <= flush_i + 1'b1;
            end

            // ---- load this band's 18 coefficients into the ring ------------
            S_LD_A: st <= S_LD_B;                  // mp3_spectra read latency
            S_LD_B: st <= S_LD_C;
            S_LD_C: begin
                xin[17] <= rd_data;                // fill from the tail so that
                for (xi = 0; xi < 17; xi = xi + 1) // after 18 loads xin[0] is
                    xin[xi] <= xin[xi + 1];        // coefficient 0
                if (k == 5'd17) begin
                    n      <= 6'd0;
                    cbase  <= 10'd0;
                    j      <= 2'd0;
                    emit_n <= 6'd0;
                    taps   <= band_short ? 6'd6 : 6'd18;
                    st     <= band_short ? S_ZERO : S_MAC_A;
                    k      <= 5'd0;
                end else begin
                    k       <= k + 5'd1;
                    rd_addr <= {ch, bbase + {5'd0, k} + 10'd1};
                    st      <= S_LD_A;
                end
            end

            // Short blocks accumulate into the 36-frame, so it starts at zero.
            // Long blocks write every position exactly once and skip this.
            S_ZERO: begin
                o36_we    <= 1'b1;
                o36_addr  <= emit_n;
                o36_wdata <= 32'sd0;
                if (emit_n == 6'd35) begin
                    emit_n <= 6'd0;
                    st     <= S_MAC_A;
                end else emit_n <= emit_n + 6'd1;
            end

            // ---- one output: sum of `taps` products ------------------------
            S_MAC_A: begin
                rom_addr <= band_short
                    ? (COS12_BASE[9:0] + {4'd0, n} * 10'd6)
                    : (COS_BASE[9:0]   + cbase);
                acc    <= 60'sd0;
                k      <= 5'd0;
                nacc_i <= 5'd0;
                st     <= S_MAC_B;
            end
            S_MAC_B: st <= S_MAC_C;                // sync_rom latency
            // SOFTWARE-PIPELINED: issue the NEXT tap's ROM address here, so its
            // latency hides inside this tap's multiply wait. S_MAC_A/B are then
            // only needed to prime the first tap, and the steady-state loop is
            // C -> W -> W -> D = 4 cycles instead of 7.
            // Issue the FIRST tap only. Every later tap is issued from S_MAC_D
            // in the same cycle it accumulates the previous one, which is what
            // makes the steady-state loop 3 cycles instead of 4.
            S_MAC_C: begin
                m_a    <= xin[0];
                m_b    <= coef_q20;
                mul_go <= 1'b1;
                mwait  <= 3'd0;
                k      <= 5'd1;
                rom_addr <= band_short
                    ? (COS12_BASE[9:0] + {4'd0, n} * 10'd6 + 10'd1)
                    : (COS_BASE[9:0]   + cbase + 10'd1);
                st     <= S_MAC_W;
            end
            // The shared multiplier is two-pass now: three cycles per product.
            S_MAC_W: begin
                // Two of the idle wait cycles carry the short path's extra
                // rotations. xin[0] was already captured into the multiplier at
                // S_MAC_C, so moving the ring here is safe.
                if (band_short && (mwait == 3'd0 || mwait == 3'd1)) begin
                    for (xi = 0; xi < 17; xi = xi + 1) xin[xi] <= xin[xi + 1];
                    xin[17] <= xin[0];
                end
                // mul_go is REGISTERED, so it is high during the first wait
                // cycle and the product is readable one cycle before
                // `MUL_WAIT counts out. Leaving at 1 costs the loop nothing and
                // saves a cycle per tap.
                if (mwait == 3'd1) st <= S_MAC_D;
                else mwait <= mwait + 3'd1;
            end
            // ACCUMULATE the product that is ready AND ISSUE the next tap in
            // the same cycle. m_a takes xin[1], which is what xin[0] becomes
            // after the rotation below -- both are non-blocking, so reading
            // index 1 gives the post-rotation head without waiting a cycle.
            S_MAC_D: begin
                acc <= acc + {{6{m_p[53]}}, m_p};
                for (xi = 0; xi < 17; xi = xi + 1) xin[xi] <= xin[xi + 1];
                xin[17] <= xin[0];

                if (nacc_i + 5'd1 == {1'b0, taps[4:0]}) begin
                    st <= S_WIN_A;      // that was the last product
                end else begin
                    nacc_i <= nacc_i + 5'd1;
                    m_a    <= xin[1];
                    m_b    <= coef_q20;
                    mul_go <= 1'b1;
                    mwait  <= 3'd0;
                    k      <= k + 5'd1;
                    rom_addr <= band_short
                        ? (COS12_BASE[9:0] + {4'd0, n} * 10'd6 + {5'd0, k + 5'd1})
                        : (COS_BASE[9:0]   + cbase + {5'd0, k + 5'd1});
                    st     <= S_MAC_W;
                end
            end

            // ---- window this output ----------------------------------------
            S_WIN_A: begin
                rom_addr <= band_short
                    ? (WIN12_BASE[9:0] + {4'd0, n})
                    : (WIN_BASE[9:0] + {8'd0, cur_win} * 10'd36 + {4'd0, n});
                st <= S_WIN_B;
            end
            S_WIN_B: st <= S_WIN_C;
            S_WIN_C: begin
                m_a    <= sat40(sx39(raw_q28));
                m_b    <= coef_q20;
                mul_go <= 1'b1;
                mwait  <= 3'd0;
                // where this windowed value lands in the 36-sample frame
                if (band_short) begin
                    depos <= 6'd6 + {2'd0, j} * 6'd6 + n;
                    // positions 12..17 and 18..23 receive two windows' output
                    accum <= (j != 2'd0) && (n < 6'd6);
                end else begin
                    depos <= n;
                    accum <= 1'b0;
                end
                st <= S_WIN_W;
            end
            S_WIN_W: begin
                if (mwait == `MUL_WAIT) st <= S_DEP_RD;
                else mwait <= mwait + 3'd1;
            end

            // ---- deposit into the 36-sample frame ---------------------------
            S_DEP_RD: begin
                o36_addr <= depos;
                st       <= accum ? S_DEP_W : S_DEP_WR;
            end
            S_DEP_W: st <= S_DEP_WR;               // o36 read latency
            S_DEP_WR: begin
                o36_we    <= 1'b1;
                o36_addr  <= depos;
                o36_wdata <= accum ? sat40(sx32(o36_rdata) + sx34(win_q28))
                                   : sat40(sx34(win_q28));
                // next output, then next window, then emit
                if (band_short) begin
                    if (n == 6'd11) begin
                        n     <= 6'd0;
                        cbase <= 10'd0;
                        if (j == 2'd2) begin emit_n <= 6'd0; st <= S_OUT_A; end
                        else begin
                            j <= j + 2'd1;
                            // step the ring by one so the head becomes x[j+1]
                            for (xi = 0; xi < 17; xi = xi + 1) xin[xi] <= xin[xi + 1];
                            xin[17] <= xin[0];
                            st <= S_MAC_A;
                        end
                    end else begin
                        n     <= n + 6'd1;
                        cbase <= cbase + 10'd18;
                        st    <= S_MAC_A;
                    end
                end else begin
                    if (n == 6'd35) begin emit_n <= 6'd0; st <= S_OUT_A; end
                    else begin n <= n + 6'd1; cbase <= cbase + 10'd18; st <= S_MAC_A; end
                end
            end

            // ---- emit: out[0..17] = overlap + frame, overlap' = frame[18..35]
            S_OUT_A: begin
                o36_addr <= emit_n;
                ovl_addr <= {ch, bbase + {4'd0, emit_n}};
                st       <= S_OUT_B;
            end
            S_OUT_B: st <= S_OUT_C;
            S_OUT_C: begin
                if (emit_n < 6'd18) begin
                    wr_en   <= 1'b1;
                    wr_addr <= {ch, bbase + {4'd0, emit_n}};
                    // change_sign: odd samples of odd-numbered bands are
                    // negated, which the polyphase stage expects.
                    wr_data <= (b[0] & emit_n[0])
                        ? -sat40(sx32(o36_rdata) + sx32(ovl_rdata))
                        :  sat40(sx32(o36_rdata) + sx32(ovl_rdata));
                end else begin
                    ovl_we    <= 1'b1;
                    ovl_addr  <= {ch, bbase + {4'd0, emit_n} - 10'd18};
                    ovl_wdata <= o36_rdata;
                end
                if (emit_n == 6'd35) st <= S_NEXTB;
                else begin emit_n <= emit_n + 6'd1; st <= S_OUT_A; end
            end

            S_NEXTB: begin
                if (b == 6'd31) st <= S_DONE;
                else begin
                    b          <= b + 6'd1;
                    bbase      <= bbase + 10'd18;
                    band_short <= is_short && ((b + 6'd1) >= n_long_bands);
                    rd_addr    <= {ch, bbase + 10'd18};
                    k          <= 5'd0;
                    st         <= S_LD_A;
                end
            end

            S_DONE: begin done <= 1'b1; st <= S_IDLE; end
            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
