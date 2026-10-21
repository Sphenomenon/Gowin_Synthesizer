`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"
`include "basic_pitch_ddr_map.svh"
// Basic Pitch CQT2010v2 filterbank engine.
//
// Reproduces the ONNX frontend: 9 decimating octaves, 36 complex kernels of
// 256 taps each, reflect padding of 128, a 256-tap lowpass decimator between
// octaves, magnitude sqrt(re^2+im^2), the per-bin sqrt(lengths) weighting and
// the final [-309:] frequency slice.
//
// Arithmetic notes
//   * Global scaling is not tracked. NormalizedLog subtracts the minimum and
//     divides by (max-min), so any constant factor on the whole magnitude
//     plane cancels. Only the per-bin sqrt(lengths) weighting is kept.
//   * The same argument holds inside the logarithm, so the engine stores
//     log2(magnitude) + log2(sqrt(lengths)) as Q8.8. That keeps the full
//     dynamic range in int16 and turns NormalizedLog into a subtract/divide.
//
// Decimated signals share one RAM and decimation is in place: the write index
// i is always below every read index 2i+k.
//
// Status: RTL candidate, unit-simulated; not synthesised or routed here.
module basic_pitch_cqt_engine #(
    parameter int WIN_LEN  = 43844,
    parameter int PER_OCT  = 36,
    parameter int CQT_BINS = 309,
    parameter int KTAPS    = 256,
    parameter int HOP_NUMERATOR=256,
    parameter int HOP_DENOMINATOR=1,
    parameter bit USE_DDR_SIGNAL = 1'b0,
    parameter bit USE_DDR_COEFF = 1'b0
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               start_i,
    input  logic [4:0]         octave_limit_i,   // octaves to run, 1..9 (test hook)
    input  logic [8:0]         frame_limit_i,    // frames to compute (test hook)
    input  logic               win_we_i,
    input  logic [15:0]        win_addr_i,
    input  logic signed [15:0] win_data_i,
    output logic               win_ready_o,
    output logic [13:0]        kre_addr_o,
    input  logic signed [15:0] kre_data_i,
    output logic [13:0]        kim_addr_o,
    input  logic signed [15:0] kim_data_i,
    output logic               coeff_req_o,
    input  logic               coeff_valid_i,
    output logic [7:0]         klp_addr_o,
    input  logic signed [15:0] klp_data_i,
    output logic [8:0]         norm_addr_o,
    input  logic signed [15:0] norm_log_data_i,
    output logic [8:0]         loglut_addr_o,
    input  logic signed [15:0] loglut_data_i,
    output logic               mag_we_o,
    output logic [15:0]        mag_addr_o,
    output logic signed [15:0] mag_data_o,
    output logic               busy_o,
    output logic               done_o,
    output logic               sig_mem_req_o,
    output logic               sig_mem_write_o,
    output logic [31:0]        sig_mem_addr_o,
    output logic [15:0]        sig_mem_wdata_o,
    input  logic               sig_mem_ready_i,
    input  logic               sig_mem_rsp_valid_i,
    input  logic [15:0]        sig_mem_rdata_i,
    output logic               sig_overflow_o
);
    localparam int MAXLEN = WIN_LEN;
    localparam logic [4:0] S_IDLE = 5'd0, S_T = 5'd1, S_MAC_REQ = 5'd2,
                           S_MAC = 5'd3, S_SQRT = 5'd4, S_LOG = 5'd5,
                           S_STORE = 5'd6, S_DEC_REQ = 5'd7, S_DEC = 5'd8,
                           S_NEXT = 5'd9, S_DONE = 5'd10, S_FLUSH = 5'd11,
                           S_MAC_WAIT = 5'd12, S_DEC_WAIT = 5'd13,
                           S_COEFF_REQ = 5'd14, S_DEC_ACC = 5'd15,
                           S_DEC_STORE = 5'd16, S_DEC_ISSUE = 5'd17,
                           S_SQUARE = 5'd18, S_SQUARE_SUM = 5'd19,
                           S_MAC_ISSUE = 5'd20;

    logic [4:0]         state;
    // The decimator runs in place. Output i can overwrite source i once
    // i >= 128; smaller source indices are still in the 256-tap dependency
    // window, so the first 128 outputs are deferred in a small head buffer and
    // copied back only after the complete octave has been consumed.
    logic [17:0]        signal_rd_addr;
    logic signed [15:0] sig_rdata;
    logic signed [15:0] sig_local_rdata, sig_ddr_rdata;
    logic sig_write_pending;
    logic [17:0] sig_pending_addr;
    logic [15:0] sig_pending_data;
    logic               sig_we;
    logic [17:0]        sig_waddr;
    logic signed [15:0] sig_wdata;
    (* ram_style = "distributed" *) logic signed [15:0] dec_head [0:127];
    logic [7:0]         flush_i;

    logic [4:0]         oct;
    logic [16:0]        sig_len;
    logic [15:0]        hop;
    logic [8:0]         t_cnt, b_cnt, k_cnt;
    logic signed [47:0] acc_re, acc_im;
    logic signed [15:0] mac_kre, mac_kim;
    logic signed [63:0] sval;
    logic signed [63:0] square_re_q, square_im_q;
    logic signed [31:0] root;
    logic signed [15:0] mag_q;
    logic [35:0]        srem;
    logic [5:0]         sbit;
    logic [16:0]        dec_i;
    logic [7:0]         dec_k;
    logic signed [47:0] dec_acc;
    logic dec_in_q;
    logic [17:0] dec_request_addr_q;
    logic [17:0] mac_request_addr_q;
    logic signed [31:0] dec_product_q;


    assign win_ready_o = (state == S_IDLE);
    assign busy_o      = (state != S_IDLE);
    wire   last_oct    = (oct == octave_limit_i - 1);
    wire [16:0] next_len = sig_len >> 1;

    wire signed [9:0] j_idx   = (10'sd8 - {5'd0, oct}) * 10'sd36 + {1'b0, b_cnt} - 10'sd15;
    wire              j_valid = (j_idx >= 0) && (j_idx < CQT_BINS);

    // Divide after multiplying the frame number, before the octave shift.
    // A rational 22050/4 hop keeps every octave aligned at 0,250,500,... ms.
    // Repeatedly shifting a rounded 5512-sample hop would drift in low octaves.
    wire [31:0] frame_sample = (t_cnt * HOP_NUMERATOR) / HOP_DENOMINATOR;
    wire [19:0] octave_sample = frame_sample >> oct;
    wire signed [19:0] raw_idx = $signed(octave_sample)
                                 + $signed({9'd0, k_cnt}) - 20'sd128;
    function automatic [17:0] reflect(input signed [19:0] idx, input [16:0] len);
        if (idx < 0)                 reflect = -idx[17:0];
        else if (idx >= {1'b0, len}) reflect = (len << 1) - 2 - idx[17:0];
        else                         reflect = idx[17:0];
    endfunction
    wire [17:0] rd_idx = reflect(raw_idx, sig_len);

    wire signed [19:0] dec_raw = $signed({3'b0, dec_i} << 1) + $signed({12'd0, dec_k}) - 20'sd127;
    wire               dec_in  = (dec_raw >= 0) && (dec_raw < $signed({1'b0, sig_len}));
    wire signed [15:0] dec_sample = dec_in_q ? sig_rdata : 16'sd0;

    // decimation tap sum including the current tap; >>24 is an arbitrary global
    // scale (it cancels in NormalizedLog), kept small enough to saturate rarely
    // Signed 16x16 fits exactly in 32 bits; explicitly extend before the
    // existing 48-bit accumulator. Split validity/multiply/add/saturation
    // without adding or copying any signal/head RAM.
    wire signed [47:0] dec_sum = dec_acc +
        $signed({{16{dec_product_q[31]}}, dec_product_q});

    function automatic signed [15:0] sat15(input signed [47:0] v);
        logic signed [32:0] sh;
        begin
            sh = v >>> 15;
            if (sh > 33'sd32767)       sat15 = 16'sd32767;
            else if (sh < -33'sd32768) sat15 = -16'sd32768;
            else                       sat15 = sh[15:0];
        end
    endfunction

    // Both RAMs continuously register the address.  The MAC/decimation
    // request states provide the one-cycle latency required by the RAM.
    assign signal_rd_addr = (state == S_MAC_REQ) ? rd_idx :
                            ((state == S_DEC_REQ && dec_in) ? dec_raw[17:0] : 18'd0);
    assign sig_we    = win_we_i ||
                       ((state == S_DEC_STORE) && (dec_i >= 17'd128)) ||
                       (state == S_FLUSH);
    assign sig_waddr = win_we_i ? {2'd0, win_addr_i} :
                       (state == S_FLUSH) ? {10'd0, flush_i} : {1'b0, dec_i};
    assign sig_wdata = win_we_i ? win_data_i :
                       (state == S_FLUSH) ? dec_head[flush_i] : sat15(dec_acc);

    generate if (USE_DDR_SIGNAL) begin : g_ddr_signal
        assign sig_rdata = sig_ddr_rdata;
        assign sig_mem_req_o = sig_write_pending || (state == S_FLUSH) ||
                               (state == S_MAC_ISSUE) ||
                               (state == S_DEC_ISSUE);
        assign sig_mem_write_o = sig_write_pending || (state == S_FLUSH);
        assign sig_mem_addr_o = `BP_DDR_CQT_SIGNAL_BYTE_BASE +
            ({14'd0, sig_write_pending ? sig_pending_addr :
              (state == S_FLUSH ? {10'd0,flush_i} :
               (state == S_MAC_ISSUE ? mac_request_addr_q : dec_request_addr_q))} << 1);
        assign sig_mem_wdata_o = sig_write_pending ? sig_pending_data : dec_head[flush_i];
    end else begin : g_local_signal
        basic_pitch_signal_ram #(.DEPTH(MAXLEN)) u_sig_ram (
            .clk_i(clk_i), .we_i(sig_we), .waddr_i(sig_waddr), .wdata_i(sig_wdata),
            .raddr_i(signal_rd_addr), .rdata_o(sig_local_rdata));
        assign sig_rdata = sig_local_rdata;
        assign sig_mem_req_o = 1'b0;
        assign sig_mem_write_o = 1'b0;
        assign sig_mem_addr_o = 32'd0;
        assign sig_mem_wdata_o = 16'd0;
        assign sig_overflow_o = 1'b0;
    end endgenerate

    generate if (USE_DDR_SIGNAL) begin : g_ddr_signal_state
        always_ff @(posedge clk_i or negedge rst_ni) begin
            if (!rst_ni) begin
                sig_ddr_rdata <= 0;
                sig_write_pending <= 0;
                sig_pending_addr <= 0;
                sig_pending_data <= 0;
                sig_overflow_o <= 0;
            end else begin
                if (sig_write_pending && sig_mem_ready_i) sig_write_pending <= 0;
                if (win_we_i || ((state == S_DEC_STORE) && dec_i >= 17'd128)) begin
                    if (sig_write_pending && !sig_mem_ready_i) sig_overflow_o <= 1;
                    sig_write_pending <= 1;
                    sig_pending_addr <= win_we_i ? {2'd0,win_addr_i} : {1'd0,dec_i};
                    sig_pending_data <= win_we_i ? win_data_i : sat15(dec_acc);
                end
                if (sig_mem_rsp_valid_i && (state == S_MAC_WAIT || state == S_DEC_WAIT))
                    sig_ddr_rdata <= sig_mem_rdata_i;
            end
        end
    end endgenerate

    // 256 = 2^8, so the linear kernel address is a plain concatenation
    assign kre_addr_o  = {b_cnt[5:0], k_cnt[7:0]};
    assign kim_addr_o  = kre_addr_o;
    assign coeff_req_o = USE_DDR_COEFF && state == S_COEFF_REQ;
    assign klp_addr_o  = {8'd0, dec_k};

    logic [5:0] msb;
    wire [7:0]  frac;
    wire [5:0]  shr_amt = (msb >= 6'd8) ? (msb - 6'd8) : 6'd0;
    wire [5:0]  shl_amt = (msb >= 6'd8) ? 6'd0 : (6'd8 - msb);
    wire signed [31:0] frac_win = (msb >= 6'd8) ? (root >> shr_amt) : (root << shl_amt);
    always_comb begin
        msb = 6'd0;
        for (int i = 0; i < 32; i = i + 1)
            if (root[i]) msb = i[5:0];
    end
    assign frac = frac_win[7:0];
    assign norm_addr_o   = j_valid ? j_idx[8:0] : 9'd0;
    assign loglut_addr_o = frac;

    // log2(magnitude) in Q8.8 plus the per-bin log2(sqrt(lengths))
    wire signed [31:0] log_sum = ($signed({26'd0, msb}) <<< 8)
                                 + $signed(loglut_data_i) + $signed(norm_log_data_i);
    wire signed [15:0] log_sat = (log_sum > 32'sd32767)      ? 16'sd32767 :
                                 (log_sum < -32'sd32768)     ? -16'sd32768 : log_sum[15:0];

    // running sums that include the tap being presented this cycle
    wire signed [15:0] src_at = sig_rdata;
    wire signed [47:0] kx = $signed({{32{src_at[15]}}, src_at});
    wire signed [47:0] acc_re_f = acc_re + $signed(USE_DDR_COEFF ? mac_kre : kre_data_i) * kx;
    wire signed [47:0] acc_im_f = acc_im + $signed(USE_DDR_COEFF ? mac_kim : kim_data_i) * kx;

    // restoring square-root step
    // Consume the same two bits per iteration from a shift register. This
    // removes a 32-way dynamic selector ahead of compare/subtract.
    wire [35:0] trial_rem = {srem[33:0], sval[63:62]};
    wire [35:0] trial_sub = {{4{1'b0}}, root[31:0], 2'b01};

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_IDLE; oct <= '0; t_cnt <= '0; b_cnt <= '0; k_cnt <= '0;
            sig_len <= WIN_LEN[16:0]; hop <= 16'd256;
            acc_re <= '0; acc_im <= '0; root <= '0; mag_q <= '0;
            mac_kre <= 16'sd0; mac_kim <= 16'sd0;
            srem <= '0; sbit <= 6'd31; sval <= '0;
            square_re_q <= '0; square_im_q <= '0;
            dec_i <= '0; dec_k <= '0; dec_acc <= '0; flush_i <= '0;
            dec_in_q <= 1'b0; dec_product_q <= 32'sd0;
            dec_request_addr_q <= 18'd0; mac_request_addr_q <= 18'd0;
            done_o <= 1'b0; mag_we_o <= 1'b0;
        end else begin
            mag_we_o <= 1'b0;
            done_o   <= 1'b0;

            case (state)
                S_IDLE: if (start_i) begin
                    oct     <= 5'd0;
                    sig_len <= WIN_LEN[16:0];
                    hop     <= 16'd256;
                    t_cnt   <= '0;
                    b_cnt   <= '0;
                    state   <= S_T;
                end

                S_T: begin
                    k_cnt  <= '0;
                    acc_re <= '0;
                    acc_im <= '0;
                    state  <= USE_DDR_COEFF ? S_COEFF_REQ : S_MAC_REQ;
                end

                S_COEFF_REQ: if (coeff_valid_i) state <= S_MAC_REQ;

                // Registered RAM read.  Keeping the address/read in a
                // clocked state lets Gowin infer the large signal buffers as
                // dual-port BSRAM instead of expanding them into DFFs.
                S_MAC_REQ: begin
                    if (USE_DDR_COEFF) begin
                        mac_kre <= kre_data_i;
                        mac_kim <= kim_data_i;
                    end
                    // Reflection/index arithmetic ends at this register;
                    // only registered addresses enter the shared DDR mux.
                    mac_request_addr_q <= rd_idx;
                    state <= USE_DDR_SIGNAL ? S_MAC_ISSUE : S_MAC;
                end
                S_MAC_ISSUE: if (!sig_write_pending && sig_mem_ready_i)
                    state <= S_MAC_WAIT;
                S_MAC_WAIT: if (sig_mem_rsp_valid_i) state <= S_MAC;

                S_MAC: begin
                    acc_re <= acc_re_f;
                    acc_im <= acc_im_f;
                    if (k_cnt == KTAPS - 1) begin
                        // The final tap is already included in acc_* above.
                        // Register it before magnitude multiplication.
                        state <= S_SQUARE;
                    end else begin
                        k_cnt <= k_cnt + 1'b1;
                        state <= USE_DDR_COEFF ? S_COEFF_REQ : S_MAC_REQ;
                    end
                end

                S_SQUARE: begin
                    // Keep the accepted arithmetic: signed >>10, then the
                    // low 64 bits of each square, then a wrapping 64-bit sum.
                    // Scalar registers separate MAC, squares, sum and sqrt.
                    square_re_q <= (acc_re >>> 10) * (acc_re >>> 10);
                    square_im_q <= (acc_im >>> 10) * (acc_im >>> 10);
                    state <= S_SQUARE_SUM;
                end

                S_SQUARE_SUM: begin
                    sval <= square_re_q + square_im_q;
                    sbit <= 6'd31;
                    srem <= '0;
                    root <= '0;
                    state <= S_SQRT;
                end

                S_SQRT: begin
                    sval <= {sval[61:0], 2'b00};
                    if (trial_rem >= trial_sub) begin
                        root <= {root[30:0], 1'b1};
                        srem <= trial_rem - trial_sub;
                    end else begin
                        root <= {root[30:0], 1'b0};
                        srem <= trial_rem;
                    end
                    if (sbit == 6'd0) state <= S_LOG;
                    else              sbit <= sbit - 6'd1;
                end

                S_LOG: begin
                    mag_q <= (root <= 0) ? 16'sd0 : log_sat;
                    state <= S_STORE;
                end

                S_STORE: begin
                    if (j_valid) begin
                        mag_we_o   <= 1'b1;
                        mag_addr_o <= {7'd0, t_cnt} * 9'd309 + j_idx[8:0];
                        mag_data_o <= mag_q;
                    end
                    if (b_cnt == PER_OCT - 1) begin
                        b_cnt <= '0;
                        if (t_cnt == frame_limit_i - 1) begin
                            dec_i <= '0; dec_k <= '0; dec_acc <= '0;
                            state <= last_oct ? S_DONE : S_DEC_REQ;
                        end else begin
                            t_cnt <= t_cnt + 1'b1;
                            state <= S_T;
                        end
                    end else begin
                        b_cnt <= b_cnt + 1'b1;
                        state <= S_T;
                    end
                end

                S_DEC_REQ: begin
                    // Keep raw-index addition/range comparison out of the
                    // shared request/ready path. DDR sees only a registered
                    // issue state and address; local RAM retains its old beat.
                    dec_in_q <= dec_in;
                    dec_request_addr_q <= dec_raw[17:0];
                    state <= (!USE_DDR_SIGNAL || !dec_in) ? S_DEC : S_DEC_ISSUE;
                end
                S_DEC_ISSUE: if (!sig_write_pending && sig_mem_ready_i)
                    state <= S_DEC_WAIT;
                S_DEC_WAIT: if (sig_mem_rsp_valid_i) state <= S_DEC;

                S_DEC: begin
                    dec_product_q <= $signed(klp_data_i) * $signed(dec_sample);
                    state <= S_DEC_ACC;
                end

                S_DEC_ACC: begin
                    dec_acc <= dec_sum;
                    if (dec_k == 8'd255) begin
                        state <= S_DEC_STORE;
                    end else begin
                        dec_k <= dec_k + 1'b1;
                        state <= S_DEC_REQ;
                    end
                end

                S_DEC_STORE: begin
                    // The final tap is already included in dec_acc. Keep the
                    // first 128 outputs deferred until the source is consumed.
                    if (dec_i < 17'd128)
                        dec_head[dec_i[6:0]] <= sat15(dec_acc);
                    dec_acc <= '0;
                    dec_k <= '0;
                    if (dec_i == next_len - 1) begin
                        flush_i <= 8'd0;
                        state <= S_FLUSH;
                    end else begin
                        dec_i <= dec_i + 1'b1;
                        state <= S_DEC_REQ;
                    end
                end

                S_FLUSH: begin
                    if (!USE_DDR_SIGNAL || (!sig_write_pending && sig_mem_ready_i)) begin
                        if ((flush_i == 8'd127) || (flush_i == next_len - 1))
                            state <= S_NEXT;
                        else
                            flush_i <= flush_i + 1'b1;
                    end
                end

                S_NEXT: begin
                    oct     <= oct + 1'b1;
                    hop     <= hop >> 1;
                    sig_len <= next_len;
                    t_cnt   <= '0;
                    state   <= S_T;
                end

                S_DONE: begin
                    done_o <= 1'b1;
                    state  <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule

// A small, explicit synchronous RAM wrapper.  Keeping the memory in its own
// module prevents the CQT control muxes from defeating Gowin's RAM inference.
module basic_pitch_signal_ram #(
    parameter integer DEPTH = 43844
) (
    input  logic clk_i,
    input  logic we_i,
    input  logic [17:0] waddr_i,
    input  logic signed [15:0] wdata_i,
    input  logic [17:0] raddr_i,
    output logic signed [15:0] rdata_o
);
    (* ram_style = "block" *) logic signed [15:0] mem [0:DEPTH-1];
    always_ff @(posedge clk_i) begin
        if (we_i && (waddr_i < DEPTH)) mem[waddr_i] <= wdata_i;
        if (raddr_i < DEPTH) rdata_o <= mem[raddr_i];
        else                 rdata_o <= 16'sd0;
    end
endmodule
