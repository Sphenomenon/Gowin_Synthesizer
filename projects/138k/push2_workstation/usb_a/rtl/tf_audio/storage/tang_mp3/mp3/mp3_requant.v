`include "mp3_mul.vh"
// MPEG-1 Layer III requantization: raw Huffman integers -> scaled spectra.
//
//   xr[i] = sign(v) * |v|^(4/3) * 2^(E/4)
//   E     = global_gain - 258 - (MS ? 2 : 0) - (iscf[band] << scf_shift)
//
// The -258 is the reference's constants folded together:
//   gain_exp = global_gain + BITS_DEQUANTIZER_OUT*4 - 210 - (MS?2:0), with
//   BITS_DEQUANTIZER_OUT = -1, then a further -MAX_SCFI (=44) from
//   L3_ldexp_q2(1 << (MAX_SCFI/4), MAX_SCFI - gain_exp).
//
// OUTPUT FORMAT: Q29 signed 32-bit, i.e. out = xr * 2^29 where xr is the
// reference's float value. Chosen from measurement, not taste: across the
// in-scope compliance vectors |xr| peaks at 2.441 with ~143 dB of useful range,
// so Q29 puts the maximum at 1.3e9 (inside int32) and still leaves ~90 quanta
// at the 1st percentile of nonzero coefficients.
//
// E is split as 4q + r so 2^(E/4) = 2^q * 2^(r/4): a barrel shift plus one of
// four constants. That is the whole reason MP3 gains are expressed in quarter
// powers -- only the fractional part needs a multiplier.
//
// |v|^(4/3) comes from pow43_full (Q20, x = 0..1026):
//   x <  1024 : direct lookup
//   x >= 1024 : x = 8q8 + rem, lerp(t[q8], t[q8+1], rem/8) * 16, exact because
//               (8y)^(4/3) = 16*y^(4/3). Worst relative error 3.4e-6.
module mp3_requant (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,

    input  wire [7:0]  global_gain,
    input  wire        scalefac_scale,
    input  wire        ms_stereo,
    input  wire        window_switching,
    input  wire [1:0]  block_type,
    input  wire        mixed_block,
    input  wire [1:0]  samplerate_idx,
    input  wire        ch,             // which channel's half of mp3_spectra

    // integer scalefactors (mp3_scalefac read port)
    output reg  [5:0]  sf_addr,
    input  wire [7:0]  sf_data,

    // raw Huffman integers (mp3_huffman read port)
    output reg  [9:0]  raw_addr,
    input  wire signed [15:0] raw_data,

    // shared mp3_sfbtab port
    output reg  [8:0]  sfb_addr,
    input  wire [7:0]  sfb_long_q,
    input  wire [7:0]  sfb_short_q,
    input  wire [7:0]  sfb_mixed_q,

    // Shared multiplier (owned by mp3_decoder). The stages run strictly one at
    // a time, so five private multipliers were five times the area for no
    // parallelism -- together they were over half the decoder.
    output wire signed [31:0] mul_a,

    output wire signed [21:0] mul_b,
    input  wire signed [53:0] mul_p,
    output reg         mul_go,      // 1-cycle request; latency = `MUL_WAIT (mp3_mul.vh)


    output reg         done,
    // requantized output -> mp3_spectra (write port)
    output reg         wr_en,
    output reg  [10:0] wr_addr,
    output reg signed [31:0] wr_data
);
    // ---- tables ------------------------------------------------------------
    // TABLE IS 1024 ENTRIES + ONE CONSTANT, not 2048.
    //
    // rd_mag is 13 bits, so the big path's address is rd_mag[12:3] <= 1023 and
    // the lerp's second point reaches 1024 -- one entry past a power of two.
    // AW(11) to hold that single value cost 4 BSRAM instead of 2, and BSRAM is
    // the binding resource on this design (45/46 before this change). Keep the
    // ROM at 1024 and special-case the top entry.
    localparam [35:0] P43_TOP = 36'h285145f32;   // pow43_full.memh[1024]

    reg  [10:0] p43_addr;                        // bit 10 = "the top entry"
    wire [35:0] p43_rom;
    sync_rom #(.AW(10), .DW(36), .INIT("src/storage/tang_mp3/mp3/tables/pow43_1024.memh")) u_p43 (
        .clk(clk), .addr(p43_addr[9:0]), .data(p43_rom));

    // sync_rom registers its read, so the select has to be delayed to match.
    reg p43_top_d;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) p43_top_d <= 1'b0; else p43_top_d <= p43_addr[10];
    wire [35:0] p43_q = p43_top_d ? P43_TOP : p43_rom;

    wire       is_short = window_switching && (block_type == 2'd2);
    wire [7:0] sfb_w    = is_short ? (mixed_block ? sfb_mixed_q : sfb_short_q)
                                   : sfb_long_q;
    wire [8:0] sfb_base = is_short
        ? (({7'd0, samplerate_idx} + 9'd5) * 9'd40)
        : (({7'd0, samplerate_idx} + 9'd5) * 9'd23);

    // 2^(r/4) in Q24, 26 bits. Q30 in 32 bits made this a 40x32 multiply on a
    // device where nothing infers DSP, for four constants between 1.0 and 1.69.
    // Q24 is 3.6e-8 relative, far under the 1 LSB PCM budget.
    //
    // COMPUTED, not typed. A hand-written set was wrong in the fifth digit
    // (9.1e-5 relative) -- invisible on inspection, and it surfaced only as PCM
    // RMS jumping 0.038 -> 0.367 LSB.
    function [21:0] frac2 (input [1:0] r);
        case (r)
            2'd0: frac2 = 22'd1048576;   // 2^(0/4) * 2^20
            2'd1: frac2 = 22'd1246974;   // 2^(1/4)
            2'd2: frac2 = 22'd1482910;   // 2^(2/4)
            default: frac2 = 22'd1763488; // 2^(3/4)
        endcase
    endfunction

    // ---- state -------------------------------------------------------------
    localparam [3:0] S_IDLE=0, S_BAND0=1, S_BAND1=2, S_SF=3, S_EXP=4,
                     S_FETCH=5, S_P0=6, S_P1=7, S_P2=8, S_MUL=9, S_WR=10,
                     S_DONE=11, S_MULH=12, S_MULL=13;

    reg [3:0]  st;
    reg [9:0]  i;              // coefficient index
    reg [5:0]  band;
    reg [8:0]  left;           // coefficients remaining in this band
    reg [1:0]  wait_c;
    reg [2:0]  mwait;   // see mp3_mul.vh

    reg signed [12:0] E;
    reg signed [10:0] q;       // E >> 2, arithmetic
    reg [1:0]  r;

    reg [12:0] mag;
    reg        neg;
    reg        big;            // mag >= 1024
    reg [2:0]  rem;
    reg [35:0] p_lo, p_hi;
    // pval must hold the BIG path's lerp(...)*16. Max |v| is 8191+15 = 8206, so
    // 8206^(4/3) * 2^20 * 16 ~ 1.74e11 needs 38 bits. At 36 bits it wrapped and
    // only coefficients >= 1024 were wrong -- one per granule in this stream,
    // which is exactly how it presented.
    reg [39:0] pval;

    // The magnitude was written out four times, and each copy synthesised its
    // own conditional-negate tree feeding a shared comparator -- yosys packed
    // the result into MUX2_LUT7 cells that nextpnr could not site. Naming it
    // once leaves a single negate.
    wire [12:0] rd_mag = raw_data[15] ? (~raw_data[12:0] + 13'd1) : raw_data[12:0];
    wire        rd_big = rd_mag >= 13'd1024;

    wire signed [12:0] E_calc =
        $signed({5'b0, global_gain}) - 13'sd258
        - (ms_stereo ? 13'sd2 : 13'sd0)
        - $signed({5'b0, sf_data} << (scalefac_scale ? 2 : 1));

    // p * 2^(r/4), keeping Q20
    // pval is 40 bits, which alone would force the SHARED multiplier to 41x27
    // (5801 LUT slots) when every other stage needs only 32x22 (4697). Split it
    // into two 20-bit halves and take two passes instead: requant does 576
    // multiplies per granule-channel, so the extra cycles are ~5k per frame
    // against a 1.4M budget, and the narrower unit is shared by everyone.
    //
    //   pval * f = (pval[39:20] * f) << 20 + (pval[19:0] * f)
    reg  [31:0] mreg_a;
    reg  [21:0] mreg_b;
    assign mul_a = mreg_a;
    assign mul_b = {1'b0, mreg_b[20:0]};

    reg  [41:0] prod_hi, prod_lo;
    // Only prod[60:20] is ever used, and prod[19:0] comes straight from
    // prod_lo with nothing carrying into the upper half. Adding the full
    // 62-bit value built a 31-deep ALU carry chain that nextpnr could not
    // legalize at high utilization -- this is a 42-bit add instead.
    wire [42:0] t_sum  = {1'b0, prod_hi} + {23'd0, prod_lo[41:20]};
    wire [40:0] t_q20  = t_sum[40:0];        // Q40 -> Q20

    // out = t << (20 + q); q is negative in practice so this is usually a right
    // shift, but a left shift is possible at extreme gains -- saturate there
    // rather than wrap, because a wrapped coefficient is far worse than a
    // clipped one downstream.
    // The shift was a 96-bit bidirectional barrel for a result that is only
    // ever 32 bits. t_q20 is 41 bits, so a right shift past 41 is zero and a
    // left shift past 31 saturates; clamping first keeps one narrow shifter
    // each way instead.
    wire signed [11:0] shl = 12'sd20 + $signed({q[10], q});
    wire        shl_pos    = (shl >= 0);
    wire [6:0]  rsh        = ((-shl) > 12'sd63) ? 7'd63 : (-shl[6:0]);
    // A left shift past 12 always saturates: t_q20 is Q20 of |v|^(4/3) and the
    // zero-magnitude case is short-circuited at the write, so t_q20 >= 2^20
    // whenever this path runs, and 2^20 << 12 already exceeds Q29's 32 bits.
    // Clamping at 12 turns a 75-bit barrel into a 53-bit one.
    wire [3:0]  lsh        = (shl > 12'sd12) ? 4'd12 : shl[3:0];
    wire        lsh_over   = shl_pos && (shl > 12'sd12);

    wire [42:0] r_shifted  = {2'd0, t_q20} >> rsh;
    wire [52:0] l_shifted  = {12'd0, t_q20} << lsh;
    wire        l_over     = shl_pos && (lsh_over || (|l_shifted[52:31]));

    // TWO 2:1 muxes, not one 4:1. A four-way select across 32 bits packs into
    // MUX2_LUT7 cells, which need a contiguous LUT group and would not place
    // once the device was dense. Deciding direction and overflow separately
    // keeps each mux one level deep.
    wire [31:0] shifted_val = shl_pos ? l_shifted[31:0] : r_shifted[31:0];
    wire        over        = shl_pos ? l_over : (|r_shifted[42:31]);
    wire [31:0] sat         = over ? 32'h7FFFFFFF : shifted_val;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; done <= 0; wr_en <= 0; wr_addr <= 0; wr_data <= 0;
            i <= 0; band <= 0; left <= 0; wait_c <= 0;
            E <= 0; q <= 0; r <= 0; mag <= 0; neg <= 0; big <= 0; rem <= 0;
            p_lo <= 0; p_hi <= 0; pval <= 0;
            mreg_a <= 0; mreg_b <= 0; prod_hi <= 0; prod_lo <= 0;
            mwait <= 0; mul_go <= 0;
            sf_addr <= 0; raw_addr <= 0; p43_addr <= 0; sfb_addr <= 0;
        end else begin
            done   <= 1'b0;
            wr_en  <= 1'b0;
            mul_go <= 1'b0;

            case (st)
            S_IDLE: if (start) begin
                i <= 0; band <= 0;
                sfb_addr <= sfb_base;
                sf_addr  <= 6'd0;
                wait_c   <= 0;
                st       <= S_BAND0;
            end

            S_BAND0: begin                     // sfb + scalefactor ROM latency
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) st <= S_BAND1;
            end

            S_BAND1: begin
                if (sfb_w == 8'd0 || i >= 10'd576) st <= S_DONE;
                else begin
                    left <= {1'b0, sfb_w};
                    st   <= S_EXP;
                end
            end

            S_EXP: begin
                E <= E_calc;
                q <= E_calc[12:2];             // arithmetic >> 2
                r <= E_calc[1:0];
                raw_addr <= i;
                wait_c   <= 0;
                st       <= S_FETCH;
            end

            S_FETCH: begin
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) begin
                    neg      <= raw_data[15];
                    mag      <= rd_mag;
                    big      <= rd_big;
                    rem      <= rd_mag[2:0];
                    // x < 1024 -> direct; x >= 1024 -> lerp on x/8
                    p43_addr <= rd_big ? {3'd0, rd_mag[12:3]} : {1'b0, rd_mag[9:0]};
                    wait_c   <= 0;
                    st       <= S_P0;
                end
            end

            S_P0: begin
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) begin
                    p_lo     <= p43_q;
                    p43_addr <= p43_addr + 1'b1;   // second point for the lerp
                    wait_c   <= 0;
                    st       <= big ? S_P1 : S_P2;
                end
            end

            S_P1: begin
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) begin p_hi <= p43_q; st <= S_P2; end
            end

            S_P2: begin
                // lerp then *16 for the big path; direct otherwise
                pval <= big ? ({4'd0, p_lo + (((p_hi - p_lo) * {33'd0, rem}) >> 3)} << 4)
                            : {4'd0, p_lo};
                st   <= S_MUL;
            end

            // Two passes through the shared multiplier, high half then low.
            S_MUL: begin
                mreg_a <= {12'd0, pval[39:20]};
                mreg_b <= frac2(r);
                mul_go <= 1'b1;
                mwait  <= 3'd0;
                st     <= S_MULH;
            end
            S_MULH: begin
                if (mwait != `MUL_WAIT) mwait <= mwait + 3'd1;
                else begin
                    prod_hi <= mul_p[41:0];
                    mreg_a  <= {12'd0, pval[19:0]};
                    mul_go  <= 1'b1;
                    mwait   <= 3'd0;
                    st      <= S_MULL;
                end
            end
            S_MULL: begin
                if (mwait != `MUL_WAIT) mwait <= mwait + 3'd1;
                else begin
                    prod_lo <= mul_p[41:0];
                    st      <= S_WR;
                end
            end

            S_WR: begin
                wr_en   <= 1'b1;
                wr_addr <= {ch, i};
                wr_data <= (mag == 13'd0) ? 32'sd0
                         : (neg ? -$signed({1'b0, sat[30:0]})
                                :  $signed({1'b0, sat[30:0]}));
                i <= i + 1'b1;
                if (left == 9'd1) begin
                    band     <= band + 1'b1;
                    sfb_addr <= sfb_addr + 1'b1;
                    sf_addr  <= sf_addr + 1'b1;
                    wait_c   <= 0;
                    st       <= S_BAND0;
                end else begin
                    left     <= left - 1'b1;
                    raw_addr <= i + 1'b1;
                    wait_c   <= 0;
                    st       <= S_FETCH;
                end
            end

            S_DONE: begin
                // any coefficients past the last band stay zero
                if (i < 10'd576) begin
                    wr_en   <= 1'b1;
                    wr_addr <= {ch, i};
                    wr_data <= 32'sd0;
                    i       <= i + 1'b1;
                end else begin
                    done <= 1'b1;
                    st   <= S_IDLE;
                end
            end

            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
