`include "mp3_mul.vh"
// Polyphase synthesis filterbank: 32 subbands x 18 time slots -> 576 PCM.
//
// Per time slot, per channel:
//
//   V[i]   = sum(k=0..31) N[i][k] * S[k]     N[i][k] = cos((16+i)(2k+1)pi/64)
//   PCM[j] = sum(a=0..7)  V[128a+j]    * D[64a+j]
//                       + V[128a+96+j] * D[64a+32+j]
//
// The second line is the ISO U-mapping and windowing folded together -- that is
// where the 16 taps per output come from, and folding them avoids materializing
// U[512] at all.
//
// THE V SHIFT IS A POINTER, NOT A MEMMOVE. The standard describes V as a
// 1024-word buffer shifted down by 64 each slot; doing that literally would
// cost 1024 word-moves per slot, more than the transform itself. `vp` walks
// backwards by 64 instead and every access is modulo 1024.
//
// 2560 multiply-accumulates per slot, ~184k per frame across both channels and
// granules, against 1.4M cycles at 54 MHz. One multiplier, reused.
//
// FORMATS: subband in is Q28; N is Q20; V is Q26 (measured peak 3.887, so 8x
// headroom); D is stored as the exact integer D*32768, i.e. Q15, because the
// ISO window lands exactly on that grid. V x D is Q41 and the output is Q15 --
// which is int16 sample units directly, so it compares against the reference's
// pcm.txt with no rescaling.
module mp3_synth (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    input  wire        flush,          // drop filter state (new track / seek)

    input  wire        ch,

    // subband samples read from mp3_spectra, band-major: {ch, band*18 + slot}
    output reg  [10:0] sb_addr,
    input  wire signed [31:0] sb_data,

    // Shared multiplier (owned by mp3_decoder). The stages run strictly one at
    // a time, so five private multipliers were five times the area for no
    // parallelism -- together they were over half the decoder.
    output wire signed [31:0] mul_a,

    output wire signed [21:0] mul_b,
    input  wire signed [53:0] mul_p,
    output reg         mul_go,      // 1-cycle request; latency = `MUL_WAIT (mp3_mul.vh)


    output reg         done,

    // PCM out, {ch, sample}; Q15, i.e. int16 units
    input  wire [10:0] pcm_addr,
    output reg  signed [15:0] pcm_data
);
    // ---- tables -------------------------------------------------------------
    reg  [10:0] cos_addr;
    wire [21:0] cos_q;
    sync_rom #(.AW(11), .DW(22), .INIT("src/storage/tang_mp3/mp3/tables/synth_cos.memh")) u_cos (
        .clk(clk), .addr(cos_addr), .data(cos_q));

    reg  [8:0]  win_addr;
    wire [17:0] win_q;
    sync_rom #(.AW(9), .DW(18), .INIT("src/storage/tang_mp3/mp3/tables/synth_win.memh")) u_win (
        .clk(clk), .addr(win_addr), .data(win_q));

    // ---- V history ----------------------------------------------------------
    // 1024 words per channel, addressed {ch, index}; packed so channel 1 does
    // not land past the end of the array (see mp3_spectra).
    // GOWIN BSRAM CONFIG TRAP -- see mp3_huffman.v. As one 32-bit array this is
    // auto-split by yosys across 4 cells; the spectra and subband checkpoints
    // now match hardware exactly while PCM does not, so the divergence is in
    // this stage. Four explicit byte-wide arrays give four independent
    // single-cell memories at BIT_WIDTH=9, the shape proven good elsewhere.
    reg [7:0] vmem0 [0:2047];
    reg [7:0] vmem1 [0:2047];
    reg [7:0] vmem2 [0:2047];
    reg [7:0] vmem3 [0:2047];
    reg  [10:0] v_waddr, v_raddr;
    reg  signed [31:0] v_wdata, v_rdata;
    reg         v_we;
    always @(posedge clk) begin
        if (v_we) begin
            vmem0[v_waddr] <= v_wdata[7:0];
            vmem1[v_waddr] <= v_wdata[15:8];
            vmem2[v_waddr] <= v_wdata[23:16];
            vmem3[v_waddr] <= v_wdata[31:24];
        end
        v_rdata <= {vmem3[v_raddr], vmem2[v_raddr],
                    vmem1[v_raddr], vmem0[v_raddr]};
    end

    // ---- PCM output ---------------------------------------------------------
    // WIDTH MATTERS ON GOWIN BSRAM. A 16-bit-wide array maps to DPX9B, whose
    // native granularity is 9 bits, and on hardware it reads back as all zeros
    // -- writes land (write enable high, data non-zero, address advancing) and
    // every read returns 0. Proven on the board with an isolated self-test:
    // 1152x32 passes, 576x16 fails, driven by nothing but a counter.
    // 8-bit (reservoir, byte FIFO) and 32-bit (spectra, PCM FIFO) are fine.
    // Store 32 bits wide and narrow on the way out.
    reg signed [31:0] pcm [0:1151];
    reg  [10:0] pcm_waddr;
    reg  signed [15:0] pcm_wdata;
    reg         pcm_we;
    wire [10:0] pcm_wa = pcm_waddr[10] ? (11'd576 + {1'b0, pcm_waddr[9:0]})
                                       : {1'b0, pcm_waddr[9:0]};
    wire [10:0] pcm_ra = pcm_addr[10]  ? (11'd576 + {1'b0, pcm_addr[9:0]})
                                       : {1'b0, pcm_addr[9:0]};
    always @(posedge clk) begin
        if (pcm_we) pcm[pcm_wa] <= {{16{pcm_wdata[15]}}, pcm_wdata};
        pcm_data <= pcm[pcm_ra][15:0];
    end

    // ---- this slot's 32 subband samples, as a rotating ring -----------------
    // Same idiom as mp3_imdct: the MAC loop always consumes the head and
    // rotates by one, so 32 steps return the ring to its original order and the
    // next V output starts from S[0] again with no reload.
    reg signed [31:0] sreg [0:31];
    integer si;

    // ---- one shared multiplier ----------------------------------------------
    reg  signed [31:0] m_a;
    reg  signed [21:0] m_b;
    wire signed [53:0] m_p = mul_p[53:0];
    assign mul_a = m_a;
    assign mul_b = m_b;

    // 32 products of (<=2^31)x(<=2^21) reach 2^57; and the window sum can reach
    // 16 * 3.887 * 2.29 before cancellation, ~2^48 in Q41. 60 bits covers both.
    // SPLIT ACCUMULATOR, pipelined carry. -noalu maps a 60-bit add to a
    // 60-deep LUT ripple (~30 ns, so ~33 MHz), and the board proves it: at
    // 36 MHz the spectra and subband checkpoints still match simulation but PCM
    // does not, while nextpnr claims 70 MHz for that build. Its model does not
    // reflect this path, so the checksums are the authority.
    //
    // Accumulate the halves independently and carry the low half's overflow
    // into the high half on the NEXT tap. Each add is 30 deep. One residual
    // carry is left at the end, folded in when the total is read.
    reg  [30:0] acc_lo;          // [29:0] value, [30] carry out
    reg  signed [30:0] acc_hi;
    wire signed [30:0] acc_hi_f = acc_hi + {30'd0, acc_lo[30]};
    wire signed [59:0] acc = {acc_hi_f[29:0], acc_lo[29:0]};

    // ROUNDING WITHOUT A WIDE ADD. `(acc + half) >>> n` is a full-width carry
    // chain -- 60 bits here -- purely to round. Adding the shifted-out bit to
    // the NARROW result is identical for round-half-up and leaves a chain the
    // width of the output. nextpnr could not legalize the long version at high
    // utilization; Gowin needs ALU chains in contiguous slices.
    wire signed [37:0] v_q26  = acc[59:22] + {37'd0, acc[21]};  // Q48 -> Q26

    // ROUND AWAY FROM ZERO, not half-up. minimp3's int16 conversion does
    // `(int)(x + .5f)` then `s -= (s < 0)` -- its comment says "to be
    // compliant" -- so a negative half rounds to the larger magnitude. Half-up
    // disagrees by 1 LSB on exactly those samples, and the ISO limit is 1 LSB
    // total, so the mismatch spends the whole budget on nothing.
    wire signed [59:0] acc_mag  = acc[59] ? -acc : acc;
    wire signed [33:0] mag_q15  = acc_mag[59:26] + {33'd0, acc_mag[25]};
    wire signed [33:0] pcm_q15  = acc[59] ? -mag_q15 : mag_q15;

    function signed [31:0] sat32 (input signed [37:0] v);
        sat32 = (v >  38'sd2147483647) ? 32'sh7FFFFFFF
              : (v < -38'sd2147483648) ? 32'sh80000000
              :                          v[31:0];
    endfunction
    // Clip to int16 rather than wrap: a wrapped sample is a full-scale click.
    function signed [15:0] sat16 (input signed [33:0] v);
        sat16 = (v >  34'sd32767)  ? 16'sh7FFF
              : (v < -34'sd32768)  ? 16'sh8000
              :                      v[15:0];
    endfunction

    localparam [3:0]
        S_IDLE=0,  S_FLUSH=1,
        S_LD_A=2,  S_LD_B=3,  S_LD_C=4,       // pull this slot's 32 subbands
        S_V_RUN=5, S_V_WR=6,
        S_W_RUN=7, S_W_WR=8,
        S_SLOT=9,  S_DONE=10;

    reg [3:0]  st;
    reg [4:0]  t;              // time slot 0..17
    reg [5:0]  vi;             // which V output, 0..63
    reg [5:0]  k;              // subband load index
    reg [5:0]  j;              // which PCM sample, 0..31
    // PER CHANNEL. The filterbank runs all 18 slots of one channel before
    // starting the other, so a single pointer would leave channel 1 reading
    // channel 0's history offset by 18*64. Mono streams cannot show this --
    // they only ever use index 0 -- which is exactly how it presented: every
    // mono vector passed and every stereo one produced near-negated output.
    reg [10:0] vpv [0:1];      // base of the newest 64 V words, mod 1024
    reg [11:0] flush_i;
    // The V history must be cleared before the FIRST granule, not only on a
    // track change. Gowin BSRAM powers up zeroed so hardware would have looked
    // fine while simulation returned X -- the same trap already fixed in
    // mp3_imdct's overlap buffer.
    reg        need_flush;

    // MAC pipeline. Addresses are issued one per cycle and the ROM answers two
    // cycles later, so operand capture trails issue by two and the accumulate
    // trails capture by one. `dv` carries the valid bit down that pipe. Without
    // it each product costs four cycles and the filterbank alone would take 57%
    // of the frame budget; pipelined it is ~15%.
    // Address cursors, stepped rather than recomputed. The window tap address
    // is vp + (iss>>1)*128 + (iss&1)*96 + j, which as a combinational
    // expression is three chained 11-bit adds; yosys merged them with the
    // surrounding counters into a single long ALU carry chain that nextpnr
    // could not legalize. Walking them incrementally is one short add each.
    //
    // Successive taps step by 96, 32, 96, 32, ... in V and a flat 32 in the
    // window table.
    reg [10:0] vcur;           // V read cursor, already modulo 1024
    reg [8:0]  wcur;           // window ROM cursor

    reg [5:0] iss;             // taps issued
    reg [5:0] nacc;            // taps accumulated
    // The shared multiplier is two-pass: a request every other cycle, and the
    // product `MUL_WAIT cycles later. The multiplier interleaves two engines, so
    // it accepts a request EVERY cycle -- a tap per cycle, not per latency. `dv`
    // tracks the answers in flight; tap_acc is still `MUL_DV_ACC because the
    // latency per request is unchanged, only the initiation interval.
    // down the pipe. Throughput halves to one tap per two cycles, which the
    // frame budget absorbs.
    // The multiplier takes four cycles per product and cannot accept a new
    // request until it finishes, so issues are spaced four cycles and the answer
    // is collected five cycles after the request.
    reg       ph;              // 1 bit: a tap every 2 cycles
    reg [6:0] dv;
    wire      tap_ld  = dv[1];
    wire      tap_acc = dv[`MUL_DV_ACC];

    wire [10:0] vp = vpv[ch];

    // V index m maps to memory as (vp + m) mod 1024, within this channel.
    // Returns 10 bits so the caller can concatenate the channel directly --
    // Verilog has no bit-select on a function result.
    function [9:0] vaddr (input [10:0] base, input [10:0] m);
        vaddr = (base + m) & 11'h3FF;
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; done <= 0; sb_addr <= 0; cos_addr <= 0; win_addr <= 0;
            v_we <= 0; v_waddr <= 0; v_wdata <= 0; v_raddr <= 0;
            pcm_we <= 0; pcm_waddr <= 0; pcm_wdata <= 0;
            m_a <= 0; m_b <= 0; acc_lo <= 0; acc_hi <= 0;
            t <= 0; vi <= 0; k <= 0; j <= 0;
            vpv[0] <= 0; vpv[1] <= 0; vcur <= 0; wcur <= 0;
            flush_i <= 0; iss <= 0; nacc <= 0; dv <= 0; need_flush <= 1'b1;
            for (si = 0; si < 32; si = si + 1) sreg[si] <= 0;
        end else begin
            done   <= 1'b0;
            mul_go <= 1'b0;
            v_we   <= 1'b0;
            pcm_we <= 1'b0;

            case (st)
            S_IDLE: begin
                if (flush || need_flush) begin
                    flush_i    <= 12'd0;
                    need_flush <= 1'b0;
                    st         <= S_FLUSH;
                end else if (start) begin
                    t       <= 5'd0;
                    k       <= 6'd0;
                    sb_addr <= {ch, 10'd0};      // band 0, slot 0
                    st      <= S_LD_A;
                end
            end

            // Clear the filter history. Without it a track change drags the
            // previous track's tail through 512 taps of window.
            S_FLUSH: begin
                v_we    <= 1'b1;
                v_waddr <= flush_i[10:0];
                v_wdata <= 32'sd0;
                if (flush_i == 12'd2047) begin
                    vpv[0] <= 11'd0;
                    vpv[1] <= 11'd0;
                    st     <= S_IDLE;
                end else flush_i <= flush_i + 12'd1;
            end

            // ---- load S[0..31] for this slot -------------------------------
            S_LD_A: st <= S_LD_B;                // mp3_imdct sb read latency
            S_LD_B: st <= S_LD_C;
            S_LD_C: begin
                sreg[31] <= sb_data;             // fill from the tail so that
                for (si = 0; si < 31; si = si + 1)   // after 32 loads sreg[0]
                    sreg[si] <= sreg[si + 1];        // holds subband 0
                if (k == 6'd31) begin
                    vpv[ch]  <= (vp - 11'd64) & 11'h3FF;
                    vi       <= 6'd0;
                    k        <= 6'd0;
                    iss      <= 6'd0; nacc <= 6'd0; dv <= 7'd0; ph <= 1'b0;
                    acc_lo <= 31'd0; acc_hi <= 31'sd0;
                    st       <= S_V_RUN;
                end else begin
                    k       <= k + 6'd1;
                    sb_addr <= {ch, (({4'd0, k} + 10'd1) * 10'd18) + {5'd0, t}};
                    st      <= S_LD_A;
                end
            end

            // ---- V[vi] = sum_k N[vi][k] * S[k] ------------------------------
            S_V_RUN: begin
                if (iss != 6'd32) begin
                    cos_addr <= {5'd0, vi} * 11'd32 + {5'd0, iss};
                    iss      <= iss + 6'd1;
                end
                dv <= {dv[5:0], (iss != 6'd32)};

                if (tap_ld) begin
                    m_a    <= sreg[0];
                    m_b    <= $signed(cos_q);
                    mul_go <= 1'b1;
                    // rotate by one; 32 steps restore the original order, so
                    // the next V output starts from S[0] with no reload
                    for (si = 0; si < 31; si = si + 1) sreg[si] <= sreg[si + 1];
                    sreg[31] <= sreg[0];
                end
                if (tap_acc) begin
                    acc_lo <= {1'b0, acc_lo[29:0]} + {1'b0, m_p[29:0]};
                    // high half of the sign-extended 60-bit product is 30 bits:
                    // six copies of the sign plus m_p[53:30]
                    acc_hi <= acc_hi + {{7{m_p[53]}}, m_p[53:30]}
                                     + {30'd0, acc_lo[30]};
                    if (nacc == 6'd31) st <= S_V_WR;
                    else nacc <= nacc + 6'd1;
                end
            end
            S_V_WR: begin
                v_we    <= 1'b1;
                v_waddr <= {ch, vaddr(vp, {5'd0, vi})};
                v_wdata <= sat32(v_q26);
                if (vi == 6'd63) begin
                    j    <= 6'd0;
                    iss  <= 6'd0; nacc <= 6'd0; dv <= 7'd0; ph <= 1'b0;
                    acc_lo <= 31'd0; acc_hi <= 31'sd0;
                    vcur <= vaddr(vp, 11'd0);      // j = 0
                    wcur <= 9'd0;
                    st   <= S_W_RUN;
                end else begin
                    vi   <= vi + 6'd1;
                    iss  <= 6'd0; nacc <= 6'd0; dv <= 7'd0; ph <= 1'b0;
                    acc_lo <= 31'd0; acc_hi <= 31'sd0;
                    st   <= S_V_RUN;
                end
            end

            // ---- PCM[j] = sum over 16 taps ----------------------------------
            // tap i: even i=2a -> V[128a + j]      * D[64a + j]
            //        odd  i=2a+1 -> V[128a + 96 + j] * D[64a + 32 + j]
            S_W_RUN: begin
                if (iss != 6'd16) begin
                    v_raddr  <= {ch, vcur[9:0]};
                    win_addr <= wcur;
                    vcur     <= (vcur + (iss[0] ? 11'd32 : 11'd96)) & 11'h3FF;
                    wcur     <= wcur + 9'd32;
                    iss      <= iss + 6'd1;
                end
                dv <= {dv[5:0], (iss != 6'd16)};

                if (tap_ld) begin
                    m_a    <= v_rdata;
                    m_b    <= {{4{win_q[17]}}, win_q};  // Q15 in a 22-bit operand
                    mul_go <= 1'b1;
                end
                if (tap_acc) begin
                    acc_lo <= {1'b0, acc_lo[29:0]} + {1'b0, m_p[29:0]};
                    // high half of the sign-extended 60-bit product is 30 bits:
                    // six copies of the sign plus m_p[53:30]
                    acc_hi <= acc_hi + {{7{m_p[53]}}, m_p[53:30]}
                                     + {30'd0, acc_lo[30]};
                    if (nacc == 6'd15) st <= S_W_WR;
                    else nacc <= nacc + 6'd1;
                end
            end
            S_W_WR: begin
                pcm_we    <= 1'b1;
                pcm_waddr <= {ch, ({5'd0, t} * 10'd32) + {4'd0, j}};
                pcm_wdata <= sat16(pcm_q15);
                if (j == 6'd31) begin
                    st <= S_SLOT;
                end else begin
                    j    <= j + 6'd1;
                    iss  <= 6'd0; nacc <= 6'd0; dv <= 7'd0; ph <= 1'b0;
                    acc_lo <= 31'd0; acc_hi <= 31'sd0;
                    vcur <= vaddr(vp, {5'd0, j} + 11'd1);
                    wcur <= {3'd0, j} + 9'd1;
                    st   <= S_W_RUN;
                end
            end

            S_SLOT: begin
                if (t == 5'd17) st <= S_DONE;
                else begin
                    t       <= t + 5'd1;
                    k       <= 6'd0;
                    sb_addr <= {ch, {5'd0, t} + 10'd1};   // band 0, next slot
                    st      <= S_LD_A;
                end
            end

            S_DONE: begin done <= 1'b1; st <= S_IDLE; end
            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
