`include "mp3_mul.vh"
// MPEG-1 Layer III joint-stereo decoding, in place on mp3_spectra.
//
// Dispatch follows the reference exactly:
//   mode_ext bit 0 set  -> intensity stereo (per band; MS on the bands it skips)
//   else joint && bit 1 -> mid/side across all 576 coefficients
//   else                -> nothing
//
// MID/SIDE:  left' = left + right,  right' = left - right.
// The 1/sqrt(2) that belongs with this transform is NOT applied here: the
// reference folds it into requantization as `gain_exp -= 2`, and mp3_requant
// already does the same. Applying it twice would be a quiet 3 dB error on every
// joint-stereo stream, so it is called out rather than left implicit.
//
// INTENSITY: above a per-window cutoff the right channel carries no spectrum of
// its own, only a position that pans the left channel between the two outputs.
// Three passes, because each needs the result of the last:
//
//   1. SCAN  - find, per window, the highest band where the RIGHT channel is
//              still non-zero. Above that, intensity applies.
//   2. PATCH - the topmost band of each window has no successor to compare
//              against, so its position is either the default (3) or inherited
//              from one window-step below.
//   3. APPLY - per band: intensity pan, or MS, or nothing.
//
// `i % 3` is carried as an explicit mod-3 counter so no divider is inferred.
//
// ist_pos comes from mp3_scalefac as the channel-1 RAW scalefactors, before
// subblock_gain and preamp -- those belong to requantization and would corrupt
// the pan lookup.
module mp3_stereo (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,

    input  wire        is_mono,
    input  wire [1:0]  mode,           // 0=stereo 1=joint 2=dual 3=mono
    input  wire [1:0]  mode_ext,
    input  wire [1:0]  samplerate_idx,
    input  wire        window_switching,
    input  wire [1:0]  block_type,
    input  wire        mixed_block,

    // mp3_scalefac ist_pos read port (channel 1)
    output reg  [5:0]  ist_band,
    input  wire [7:0]  ist_data,

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
    // COVERAGE, not status. This used to report "intensity stereo refused";
    // when the path was implemented it became a constant 0 and the sweep went
    // on reporting 0 granules, which read as "not needed" when it actually
    // meant "no longer measured". It now reports the path being TAKEN.
    output reg         ist_active,

    // mp3_spectra ports
    output reg  [10:0] rd_addr,
    input  wire signed [31:0] rd_data,
    output reg         wr_en,
    output reg  [10:0] wr_addr,
    output reg  signed [31:0] wr_data
);
    wire i_stereo = !is_mono && mode_ext[0];
    wire ms_plain = !is_mono && (mode == 2'd1) && mode_ext[1] && !mode_ext[0];
    // Inside the intensity walk the reference tests mode_ext bit 1 directly,
    // without the joint-mode check it uses for the whole-granule MS path.
    wire ms_band  = mode_ext[1];

    // ---- block geometry ----------------------------------------------------
    wire       is_short    = window_switching && (block_type == 2'd2);
    wire [5:0] n_long_sfb  = is_short ? (mixed_block ? 6'd8  : 6'd0)  : 6'd22;
    wire [5:0] n_short_sfb = is_short ? (mixed_block ? 6'd30 : 6'd39) : 6'd0;
    wire [5:0] n_sfb       = n_long_sfb + n_short_sfb;
    wire [2:0] max_blocks  = (n_short_sfb != 6'd0) ? 3'd3 : 3'd1;

    wire [7:0] sfb_w    = is_short ? (mixed_block ? sfb_mixed_q : sfb_short_q)
                                   : sfb_long_q;
    wire [8:0] sfb_base = is_short
        ? (({7'd0, samplerate_idx} + 9'd5) * 9'd40)
        : (({7'd0, samplerate_idx} + 9'd5) * 9'd23);

    // ---- intensity pan, Q16 in 18 bits, MS sqrt(2) folded in ----------------
    // Q16 rather than Q30 because this toolchain infers no DSP: a 32x32 multiply
    // costs 3881 LUT4 against 1469 for 32x18, and two of them here cost 12886 --
    // 62% of the device for one stage. Two positions are exactly 0 and 1, and
    // the rest are pans below 1.52, so 18 bits is ample.
    function signed [17:0] pan_kl (input ms, input [2:0] ip);
        case ({ms, ip})
            4'b0_000: pan_kl = 18'sd0;     4'b0_001: pan_kl = 18'sd13849;
            4'b0_010: pan_kl = 18'sd23988; 4'b0_011: pan_kl = 18'sd32768;
            4'b0_100: pan_kl = 18'sd41548; 4'b0_101: pan_kl = 18'sd51687;
            4'b0_110: pan_kl = 18'sd65536;
            4'b1_000: pan_kl = 18'sd0;     4'b1_001: pan_kl = 18'sd19586;
            4'b1_010: pan_kl = 18'sd33924; 4'b1_011: pan_kl = 18'sd46341;
            4'b1_100: pan_kl = 18'sd58758; 4'b1_101: pan_kl = 18'sd73096;
            4'b1_110: pan_kl = 18'sd92682;
            default:  pan_kl = 18'sd0;
        endcase
    endfunction
    function signed [17:0] pan_kr (input ms, input [2:0] ip);
        case ({ms, ip})
            4'b0_000: pan_kr = 18'sd65536; 4'b0_001: pan_kr = 18'sd51687;
            4'b0_010: pan_kr = 18'sd41548; 4'b0_011: pan_kr = 18'sd32768;
            4'b0_100: pan_kr = 18'sd23988; 4'b0_101: pan_kr = 18'sd13849;
            4'b0_110: pan_kr = 18'sd0;
            4'b1_000: pan_kr = 18'sd92682; 4'b1_001: pan_kr = 18'sd73096;
            4'b1_010: pan_kr = 18'sd58758; 4'b1_011: pan_kr = 18'sd46341;
            4'b1_100: pan_kr = 18'sd33924; 4'b1_101: pan_kr = 18'sd19586;
            4'b1_110: pan_kr = 18'sd0;
            default:  pan_kr = 18'sd0;
        endcase
    endfunction

    // ---- working state ------------------------------------------------------
    // Single-ported, like mp3_scalefac's iscf. Two combinational reads plus a
    // write kept this as 40 x 8 flops behind two 40:1 muxes; the array is the
    // bulk of this stage.
    // ram_style=block: tiny arrays default to distributed RAM16SDP4, whose
    // siting rules the placer cannot satisfy once the m7 LCD adds 21 I/O and
    // the UI logic. Block RAM sits in its own columns and does not compete.
    (* ram_style = "block" *)
    reg  [7:0] ipos [0:39];                  // writable copy of ist_pos
    reg  [5:0] ipos_ra;
    reg  [7:0] ipos_q;
    reg        ipos_we;
    reg  [5:0] ipos_wa;
    reg  [7:0] ipos_wd;
    always @(posedge clk) begin
        if (ipos_we) ipos[ipos_wa] <= ipos_wd;
        ipos_q <= ipos[ipos_ra];
    end
    reg signed [6:0] maxb0, maxb1, maxb2;    // -1 .. 38

    reg signed [31:0] l, r;
    reg  [9:0] coef;                         // first coefficient of this band
    reg  [7:0] curw;                         // this band's width
    reg  [7:0] k;                            // position within the band
    reg  [5:0] bnd;
    reg  [1:0] m3;
    reg  [7:0] cur_ipos;
    reg        band_ist;
    reg  [1:0] pi;
    reg  [2:0] mwait;   // see mp3_mul.vh

    wire signed [6:0] maxb_m3 = (m3 == 2'd0) ? maxb0 : (m3 == 2'd1) ? maxb1 : maxb2;
    wire [7:0] ipos_bnd = ipos_q;
    wire       cur_is_ist = ($signed({1'b0, bnd}) > maxb_m3) && (ipos_bnd < 8'd7);

    // Long blocks are a single window, so the three counters collapse to their
    // maximum before the patch step.
    wire signed [6:0] mx01 = (maxb0 > maxb1) ? maxb0 : maxb1;
    wire signed [6:0] mx3  = (mx01  > maxb2) ? mx01  : maxb2;

    // itop has no successor to compare against; prev is one window-step below.
    wire [5:0] itop  = n_sfb - {3'd0, max_blocks} + {4'd0, pi};
    wire [5:0] iprev = n_sfb - {2'd0, max_blocks, 1'b0} + {4'd0, pi};
    wire signed [6:0] maxb_pi = (pi == 2'd0) ? maxb0 : (pi == 2'd1) ? maxb1 : maxb2;

    // ONE multiplier, the two pans taken in sequence. Q29 x Q16 -> Q45, back to
    // Q29 with >>> 16, rounded.
    reg  signed [31:0] m_a;
    reg  signed [17:0] m_b;
    wire signed [49:0] m_p = mul_p[49:0];
    assign mul_a = m_a;
    assign mul_b = {{4{m_b[17]}}, m_b};

    reg  signed [49:0] p_l, p_r;
    wire signed [33:0] ist_l = p_l[49:16] + {33'd0, p_l[15]};
    wire signed [33:0] ist_r = p_r[49:16] + {33'd0, p_r[15]};

    wire signed [33:0] ms_sum = {{2{l[31]}}, l} + {{2{r[31]}}, r};
    wire signed [33:0] ms_dif = {{2{l[31]}}, l} - {{2{r[31]}}, r};

    function signed [31:0] sat34 (input signed [33:0] v);
        sat34 = (v >  34'sd2147483647) ? 32'sh7FFFFFFF
              : (v < -34'sd2147483648) ? 32'sh80000000
              :                          v[31:0];
    endfunction

    localparam [4:0]
        S_IDLE=0,
        S_LD_A=1,  S_LD_B=2,  S_LD_C=3,               // copy ist_pos in
        S_SC_A=4,  S_SC_B=5,  S_SC_C=6,  S_SC_D=7,    // scan for max_band
        S_SC_NEXT=8, S_SC_MERGE=9,
        S_PATCH=10, S_PATCHW=29, S_PATCHD=30,
        S_BD_A=11, S_BD_B=12,                          // per-band setup
        S_RD0W=13, S_CAP0=14, S_RD1W=15, S_CAP1=16,
        S_WR0=17,  S_WR1=18,  S_STEP=19,  S_MUL=27, S_MUL2=28,
        S_MS_RD0=20, S_MS_C0=21, S_MS_RD1=22, S_MS_C1=23,
        S_MS_W0=24,  S_MS_W1=25,
        S_DONE=26;

    reg [4:0] st;
    integer   ii;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; done <= 0; ist_active <= 0;
            rd_addr <= 0; wr_en <= 0; wr_addr <= 0; wr_data <= 0;
            ist_band <= 0; sfb_addr <= 0;
            l <= 0; r <= 0; coef <= 0; curw <= 0; k <= 0; bnd <= 0; m3 <= 0;
            m_a <= 0; m_b <= 0; p_l <= 0; p_r <= 0; mwait <= 0; mul_go <= 0;
            ipos_ra <= 0; ipos_we <= 0; ipos_wa <= 0; ipos_wd <= 0;
            cur_ipos <= 0; band_ist <= 0; pi <= 0;
            maxb0 <= 0; maxb1 <= 0; maxb2 <= 0;
            end else begin
            done    <= 1'b0;
            wr_en   <= 1'b0;
            mul_go  <= 1'b0;
            ipos_we <= 1'b0;

            case (st)
            S_IDLE: if (start) begin
                ist_active <= 1'b0;
                if (i_stereo) begin
                    bnd      <= 6'd0;
                    ist_band <= 6'd0;
                    st       <= S_LD_A;
                end else if (ms_plain) begin
                    coef    <= 10'd0;
                    rd_addr <= 11'd0;
                    st      <= S_MS_RD0;
                end else begin
                    st <= S_DONE;
                end
            end

            // ---- copy ist_pos into writable storage ------------------------
            S_LD_A: st <= S_LD_B;                 // registered read latency
            S_LD_B: st <= S_LD_C;
            S_LD_C: begin
                ipos_we <= 1'b1; ipos_wa <= bnd; ipos_wd <= ist_data;
                if (bnd + 6'd1 >= n_sfb) begin
                    maxb0    <= -7'sd1; maxb1 <= -7'sd1; maxb2 <= -7'sd1;
                    bnd      <= 6'd0;
                    m3       <= 2'd0;
                    coef     <= 10'd0;
                    k        <= 8'd0;
                    sfb_addr <= sfb_base;
                    st       <= S_SC_A;
                end else begin
                    bnd      <= bnd + 6'd1;
                    ist_band <= bnd + 6'd1;
                    st       <= S_LD_A;
                end
            end

            // ---- scan the RIGHT channel for the top non-zero band -----------
            S_SC_A: st <= S_SC_B;                 // sfb ROM latency
            S_SC_B: begin
                curw <= sfb_w;
                k    <= 8'd0;
                if (sfb_w == 8'd0 || bnd >= n_sfb) st <= S_SC_MERGE;
                else begin
                    rd_addr <= {1'b1, coef};      // right channel
                    st      <= S_SC_C;
                end
            end
            S_SC_C: st <= S_SC_D;                 // mp3_spectra read latency
            S_SC_D: begin
                // The reference stops at the first non-zero PAIR; stopping at
                // the first non-zero value is equivalent, since either member
                // of a pair marks the band.
                if (rd_data != 32'sd0) begin
                    case (m3)
                        2'd0:    maxb0 <= $signed({1'b0, bnd});
                        2'd1:    maxb1 <= $signed({1'b0, bnd});
                        default: maxb2 <= $signed({1'b0, bnd});
                    endcase
                    st <= S_SC_NEXT;
                end else if (k + 8'd1 >= curw) begin
                    st <= S_SC_NEXT;
                end else begin
                    k       <= k + 8'd1;
                    rd_addr <= {1'b1, coef + {2'd0, k} + 10'd1};
                    st      <= S_SC_C;
                end
            end
            S_SC_NEXT: begin
                coef     <= coef + {2'd0, curw};
                bnd      <= bnd + 6'd1;
                m3       <= (m3 == 2'd2) ? 2'd0 : m3 + 2'd1;
                sfb_addr <= sfb_addr + 9'd1;
                st       <= S_SC_A;
            end

            S_SC_MERGE: begin
                if (n_long_sfb != 6'd0) begin
                    maxb0 <= mx3; maxb1 <= mx3; maxb2 <= mx3;
                end
                pi <= 2'd0;
                st <= S_PATCH;
            end

            // ---- the topmost band of each window has no successor -----------
            // ipos is a RAM now, so the inherited value must be FETCHED first.
            S_PATCH: begin
                ipos_ra <= iprev;
                st      <= S_PATCHW;
            end
            S_PATCHW: st <= S_PATCHD;
            S_PATCHD: begin
                ipos_we <= 1'b1;
                ipos_wa <= itop;
                ipos_wd <= (maxb_pi >= $signed({1'b0, iprev})) ? 8'd3 : ipos_q;
                if ({1'b0, pi} + 3'd1 >= max_blocks) begin
                    bnd      <= 6'd0;
                    m3       <= 2'd0;
                    coef     <= 10'd0;
                    sfb_addr <= sfb_base;
                    st       <= S_BD_A;
                end else pi <= pi + 2'd1;
            end

            // ---- per band: intensity pan, or MS, or nothing -----------------
            S_BD_A: begin
                ipos_ra <= bnd;               // fetch alongside the sfb ROM
                st      <= S_BD_B;
            end
            S_BD_B: begin
                curw     <= sfb_w;
                k        <= 8'd0;
                cur_ipos <= ipos_bnd;
                band_ist <= cur_is_ist;
                if (cur_is_ist) ist_active <= 1'b1;
                if (sfb_w == 8'd0 || bnd >= n_sfb) begin
                    st <= S_DONE;
                end else if (!cur_is_ist && !ms_band) begin
                    coef     <= coef + {2'd0, sfb_w};   // leave the band alone
                    bnd      <= bnd + 6'd1;
                    m3       <= (m3 == 2'd2) ? 2'd0 : m3 + 2'd1;
                    sfb_addr <= sfb_addr + 9'd1;
                    st       <= S_BD_A;
                end else begin
                    rd_addr <= {1'b0, coef};      // left channel
                    st      <= S_RD0W;
                end
            end

            S_RD0W: st <= S_CAP0;                 // mp3_spectra read latency
            S_CAP0: begin
                l <= rd_data;
                if (band_ist) begin
                    m_a    <= rd_data;            // intensity needs only left
                    m_b    <= pan_kl(ms_band, cur_ipos[2:0]);
                    mul_go <= 1'b1;
                    mwait  <= 3'd0;
                    st     <= S_MUL;
                end else begin
                    rd_addr <= {1'b1, coef + {2'd0, k}};
                    st      <= S_RD1W;
                end
            end
            S_RD1W: st <= S_CAP1;
            S_CAP1: begin r <= rd_data; st <= S_WR0; end

            // left*kl then left*kr through the shared unit. Each product must
            // be captured in the cycle its operands are still applied -- m_b
            // changes on the same edge as the state, so capturing one state
            // later would read the NEXT product.
            S_MUL: begin
                if (mwait != `MUL_WAIT) mwait <= mwait + 3'd1;
                else begin
                    p_l    <= m_p;                // l * kl
                    m_b    <= pan_kr(ms_band, cur_ipos[2:0]);
                    mul_go <= 1'b1;
                    mwait  <= 3'd0;
                    st     <= S_MUL2;
                end
            end
            S_MUL2: begin
                if (mwait != `MUL_WAIT) mwait <= mwait + 3'd1;
                else begin
                    p_r <= m_p;                   // l * kr
                    st  <= S_WR0;
                end
            end

            S_WR0: begin
                wr_en   <= 1'b1;
                wr_addr <= {1'b0, coef + {2'd0, k}};
                wr_data <= band_ist ? sat34(ist_l) : sat34(ms_sum);
                st      <= S_WR1;
            end
            S_WR1: begin
                wr_en   <= 1'b1;
                wr_addr <= {1'b1, coef + {2'd0, k}};
                wr_data <= band_ist ? sat34(ist_r) : sat34(ms_dif);
                st      <= S_STEP;
            end

            S_STEP: begin
                if (k + 8'd1 >= curw) begin
                    coef     <= coef + {2'd0, curw};
                    bnd      <= bnd + 6'd1;
                    m3       <= (m3 == 2'd2) ? 2'd0 : m3 + 2'd1;
                    sfb_addr <= sfb_addr + 9'd1;
                    st       <= S_BD_A;
                end else begin
                    k       <= k + 8'd1;
                    rd_addr <= {1'b0, coef + {2'd0, k} + 10'd1};
                    st      <= S_RD0W;
                end
            end

            // ---- plain mid/side over the whole granule ----------------------
            S_MS_RD0: st <= S_MS_C0;              // mp3_spectra read latency
            S_MS_C0: begin
                l       <= rd_data;
                rd_addr <= {1'b1, coef};
                st      <= S_MS_RD1;
            end
            S_MS_RD1: st <= S_MS_C1;
            S_MS_C1: begin r <= rd_data; st <= S_MS_W0; end
            S_MS_W0: begin
                wr_en   <= 1'b1;
                wr_addr <= {1'b0, coef};
                wr_data <= sat34(ms_sum);
                st      <= S_MS_W1;
            end
            S_MS_W1: begin
                wr_en   <= 1'b1;
                wr_addr <= {1'b1, coef};
                wr_data <= sat34(ms_dif);
                if (coef == 10'd575) st <= S_DONE;
                else begin
                    coef    <= coef + 10'd1;
                    rd_addr <= {1'b0, coef + 10'd1};
                    st      <= S_MS_RD0;
                end
            end

            S_DONE: begin done <= 1'b1; st <= S_IDLE; end
            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
