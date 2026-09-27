`include "mp3_mul.vh"
// Antialias butterflies across subband boundaries, in place on mp3_spectra.
//
// For each boundary between band b and band b+1, the eight coefficients either
// side are mixed:
//
//   u = x[18(b+1) + i]      d = x[18b + 17 - i]
//   x[18(b+1) + i] = u*cs[i] - d*ca[i]
//   x[18b + 17 - i] = u*ca[i] + d*cs[i]
//
// This undoes the encoder's aliasing reduction, which exists because the
// polyphase filterbank's bands overlap.
//
// HOW MANY BOUNDARIES depends on the block type, and getting it wrong is
// silent rather than obvious:
//   long / start / stop  -> 31 (every boundary)
//   mixed short          -> 1  (only the long/short seam)
//   pure short           -> 0
// The reference expresses the last two as `n_long_bands - 1`, which underflows
// to -1 for pure short and is caught by its loop condition; here it is an
// explicit zero.
module mp3_antialias (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,

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

    // mp3_spectra ports
    output reg  [10:0] rd_addr,
    input  wire signed [31:0] rd_data,
    output reg         wr_en,
    output reg  [10:0] wr_addr,
    output reg  signed [31:0] wr_data
);
    wire is_short = window_switching && (block_type == 2'd2);
    wire [5:0] nbands = is_short ? (mixed_block ? 6'd1 : 6'd0) : 6'd31;

    // Sixteen constants. A combinational case is right here and does not
    // violate the no-async-ROM rule that governs the big tables: this is ~16
    // LUT4 of constant mux, not a 1152-word array.
    //
    // Q20 IN 22 BITS. synth_gowin in this toolchain infers no DSP at all -- a
    // 32x18 multiply costs 1469 LUT4, 32x22 costs 3162, 32x32 costs 3881 --
    // so operand width is paid for directly in logic and the narrowest adequate
    // coefficient wins.
    //
    // Q16 was tried and is NOT adequate here. Half an LSB of Q16 is 7.6e-6, and
    // this stage multiplies values up to 2.44, so the error reaches ~1.9e-5
    // against an ISO limit of 3.05e-5 on the FINAL PCM -- before the IMDCT and
    // filterbank have added theirs. It showed up as the two loudest compliance
    // vectors failing while the quiet ones passed. Q20 puts it at 1.2e-6.
    function signed [21:0] aa_cs (input [2:0] k);   // Q20
        case (k)
            3'd0: aa_cs = 22'sd899147;  3'd1: aa_cs = 22'sd924573;
            3'd2: aa_cs = 22'sd995758;  3'd3: aa_cs = 22'sd1031080;
            3'd4: aa_cs = 22'sd1043876; 3'd5: aa_cs = 22'sd1047696;
            3'd6: aa_cs = 22'sd1048470; default: aa_cs = 22'sd1048569;
        endcase
    endfunction
    function signed [21:0] aa_ca (input [2:0] k);   // Q20
        case (k)
            3'd0: aa_ca = 22'sd539488; 3'd1: aa_ca = 22'sd494647;
            3'd2: aa_ca = 22'sd328600; 3'd3: aa_ca = 22'sd190750;
            3'd4: aa_ca = 22'sd99168;  3'd5: aa_ca = 22'sd42956;
            3'd6: aa_ca = 22'sd14888;  default: aa_ca = 22'sd3880;
        endcase
    endfunction

    localparam [3:0] S_IDLE=0, S_RDU=1, S_RDUW=2, S_RDDW=3,
                     S_CAPD=4, S_MUL=5, S_WRU=6, S_WRD=7, S_STEP=8, S_DONE=9;

    reg [3:0] st;
    reg [5:0] b;
    reg [2:0] i;
    reg signed [31:0] u, d;

    // ONE multiplier, four products in sequence. Four concurrent 32x32 units
    // cost 17961 LUT4 here -- 87% of the device for one stage -- against a
    // cycle budget with room to spare: 31 bands x 8 butterflies x 4 extra
    // cycles is ~1k cycles per granule-channel out of 1.4M per frame.
    reg  signed [31:0] m_a;
    reg  signed [21:0] m_b;
    wire signed [53:0] m_p = mul_p[53:0];
    assign mul_a = m_a;
    assign mul_b = m_b;

    reg  signed [53:0] p_ucs, p_uca, p_dcs, p_dca;
    reg  [1:0] mstep;
    reg  [2:0] mwait;   // see mp3_mul.vh

    // Q29 x Q20 -> Q49, back to Q29 with >>> 20, rounded.
    wire signed [54:0] sum_u = {p_ucs[53], p_ucs} - {p_dca[53], p_dca};
    wire signed [54:0] sum_d = {p_uca[53], p_uca} + {p_dcs[53], p_dcs};
    // round using the shifted-out bit, not a 55-bit add
    wire signed [33:0] new_u = sum_u[54:20] + {33'd0, sum_u[19]};
    wire signed [33:0] new_d = sum_d[54:20] + {33'd0, sum_d[19]};

    function signed [31:0] sat34 (input signed [33:0] v);
        sat34 = (v >  34'sd2147483647) ? 32'sh7FFFFFFF
              : (v < -34'sd2147483648) ? 32'sh80000000
              :                          v[31:0];
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; done <= 0; wr_en <= 0; rd_addr <= 0;
            wr_addr <= 0; wr_data <= 0; b <= 0; i <= 0; u <= 0; d <= 0;
            m_a <= 0; m_b <= 0; mstep <= 0; mwait <= 0; mul_go <= 0;
            p_ucs <= 0; p_uca <= 0; p_dcs <= 0; p_dca <= 0;
        end else begin
            done   <= 1'b0;
            wr_en  <= 1'b0;
            mul_go <= 1'b0;

            case (st)
            S_IDLE: if (start) begin
                if (nbands == 6'd0) st <= S_DONE;
                else begin
                    b       <= 6'd0;
                    i       <= 3'd0;
                    rd_addr <= {ch, 10'd18};        // 18*(0+1) + 0
                    st      <= S_RDU;
                end
            end

            S_RDU: st <= S_RDUW;                    // mp3_spectra read latency
            S_RDUW: begin
                u       <= rd_data;
                rd_addr <= {ch, ({4'd0, b} * 10'd18) + 10'd17 - {7'd0, i}};
                st      <= S_RDDW;
            end
            S_RDDW: st <= S_CAPD;
            S_CAPD: begin
                d      <= rd_data;
                m_a    <= u;
                m_b    <= aa_cs(i);
                mul_go <= 1'b1;
                mstep  <= 2'd0;
                mwait  <= 3'd0;
                st     <= S_MUL;
            end

            // u*cs, u*ca, d*cs, d*ca through the shared two-pass unit, which
            // answers three cycles after the request.
            S_MUL: begin
                if (mwait != `MUL_WAIT) mwait <= mwait + 3'd1;
                else begin
                    mwait <= 3'd0;
                    case (mstep)
                        2'd0: begin p_ucs <= m_p; m_a <= u; m_b <= aa_ca(i); mul_go <= 1'b1; end
                        2'd1: begin p_uca <= m_p; m_a <= d; m_b <= aa_cs(i); mul_go <= 1'b1; end
                        2'd2: begin p_dcs <= m_p; m_a <= d; m_b <= aa_ca(i); mul_go <= 1'b1; end
                        default: p_dca <= m_p;
                    endcase
                    if (mstep == 2'd3) st <= S_WRU;
                    else mstep <= mstep + 2'd1;
                end
            end

            S_WRU: begin
                wr_en   <= 1'b1;
                wr_addr <= {ch, (({4'd0, b} + 10'd1) * 10'd18) + {7'd0, i}};
                wr_data <= sat34(new_u);
                st      <= S_WRD;
            end
            S_WRD: begin
                wr_en   <= 1'b1;
                wr_addr <= {ch, ({4'd0, b} * 10'd18) + 10'd17 - {7'd0, i}};
                wr_data <= sat34(new_d);
                st      <= S_STEP;
            end

            S_STEP: begin
                if (i == 3'd7) begin
                    if (b + 6'd1 == nbands) st <= S_DONE;
                    else begin
                        b       <= b + 6'd1;
                        i       <= 3'd0;
                        rd_addr <= {ch, (({4'd0, b} + 10'd2) * 10'd18)};
                        st      <= S_RDU;
                    end
                end else begin
                    i       <= i + 3'd1;
                    rd_addr <= {ch, (({4'd0, b} + 10'd1) * 10'd18)
                                    + {7'd0, i} + 10'd1};
                    st      <= S_RDU;
                end
            end

            S_DONE: begin done <= 1'b1; st <= S_IDLE; end
            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
