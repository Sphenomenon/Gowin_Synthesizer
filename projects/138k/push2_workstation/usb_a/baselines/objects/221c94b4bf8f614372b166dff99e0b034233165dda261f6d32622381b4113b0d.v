// MPEG-1 Layer III Huffman decoder -> 576 raw signed spectral integers.
//
// Uses minimp3's packed tree encoding (tables extracted by gen_tables.py, so
// the data is byte-identical to the golden model's):
//
//   w = 5; leaf = tabs[base + peek(5)]
//   while (leaf < 0) { skip(w); w = leaf & 7; leaf = tabs[base + peek(w) - (leaf>>3)]; }
//   skip(leaf >> 8)                       // total code length
//   x = leaf & 15, y = (leaf >> 4) & 15   // low nibble first
//
// A value of 15 means "plus linbits extra bits", and any nonzero value is
// followed by one sign bit. After big_values, count1 quads decode four +/-1
// values at a time from tab32/tab33 until part2_3_length is reached.
//
// Requantization is deliberately NOT done here: this stage emits the integers,
// which can be diffed against the reference directly (huffraw.txt). Folding the
// scalefactor gain in -- as minimp3 does -- would make a wrong exponent and a
// wrong codeword indistinguishable.
//
// TWO LESSONS FROM EARLIER STAGES ARE BUILT IN:
//   * sync_rom needs TWO cycles: the address is assigned non-blocking, so the
//     ROM samples it on the following edge and data lands the edge after. Three
//     bugs in this project came from reading in the state that set the address.
//   * res_skip is registered, so the reservoir's peek window is stale for a
//     cycle afterwards. Every read is followed by a settle state.
module mp3_huffman (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        start,
    input  wire [8:0]  big_values,
    input  wire [14:0] table_select,     // {t2,t1,t0}
    input  wire [7:0]  region0_count,
    input  wire [7:0]  region1_count,
    input  wire        count1_table,
    input  wire        window_switching,
    input  wire [1:0]  block_type,
    input  wire        mixed_block,
    input  wire [1:0]  samplerate_idx,
    // ABSOLUTE reservoir bit position at which this granule's data ends, i.e.
    // (bits_read at granule start) + part2_3_length. The reference works the
    // same way -- layer3gr_limit is an absolute bs->pos, not a length -- and
    // res_bits counts from the FRAME start, not the granule start.
    input  wire [17:0] bit_limit,

    // reservoir bit port
    input  wire        res_ready,
    input  wire [23:0] res_peek,
    input  wire [17:0] res_bits,         // bits consumed since the granule start
    output reg         res_skip,
    output reg  [4:0]  res_skip_n,

    // shared mp3_sfbtab port
    output reg  [8:0]  sfb_addr,
    input  wire [7:0]  sfb_long_q,
    input  wire [7:0]  sfb_short_q,
    input  wire [7:0]  sfb_mixed_q,

    output reg         done,

    // spectral read port (registered)
    input  wire [9:0]  spec_addr,
    output reg signed [15:0] spec_data
);
    // ---- ROMs --------------------------------------------------------------
    // 2048 entries in BSRAM + a 116-entry tail in logic. The full table is
    // 2164 entries, and AW(12) to cover that tail cost 4 BSRAM where AW(11)
    // costs 2 -- see huff_tabs_tail.v. The select is delayed one cycle to
    // match sync_rom's registered read.
    reg  [11:0] tabs_addr;
    wire [13:0] tabs_rom, tabs_tail;
    sync_rom #(.AW(11), .DW(14), .INIT("src/storage/tang_mp3/mp3/tables/huff_tabs_2048.memh")) u_tabs (
        .clk(clk), .addr(tabs_addr[10:0]), .data(tabs_rom));
    huff_tabs_tail u_tabs_tail (.idx(tabs_addr[10:0]), .t(tabs_tail));

    reg tabs_hi_d;
    reg [13:0] tabs_tail_d;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) begin tabs_hi_d <= 1'b0; tabs_tail_d <= 14'd0; end
        else begin tabs_hi_d <= tabs_addr[11]; tabs_tail_d <= tabs_tail; end
    wire [13:0] tabs_q = tabs_hi_d ? tabs_tail_d : tabs_rom;
    wire signed [13:0] leaf_s = $signed(tabs_q);

    reg  [4:0]  tsel_addr;
    wire [11:0] tindex_q;
    sync_rom #(.AW(5), .DW(12), .INIT("src/storage/tang_mp3/mp3/tables/huff_index.memh")) u_tidx (
        .clk(clk), .addr(tsel_addr), .data(tindex_q));

    wire [3:0] linb_q;
    sync_rom #(.AW(5), .DW(4), .INIT("src/storage/tang_mp3/mp3/tables/huff_linbits.memh")) u_linb (
        .clk(clk), .addr(tsel_addr), .data(linb_q));

    // count1: tab32 (28) and tab33 (16) in one 64-entry ROM, tab33 at offset 32
    reg  [5:0] c1_addr;
    wire [7:0] c1_q;
    sync_rom #(.AW(6), .DW(8), .INIT("src/storage/tang_mp3/mp3/tables/huff_count1.memh")) u_c1 (
        .clk(clk), .addr(c1_addr), .data(c1_q));

    // scalefactor band widths; MPEG-1 uses rows 5..7 (= 5 + samplerate_idx)

    wire       is_short = window_switching && (block_type == 2'd2);
    wire [7:0] sfb_w    = is_short ? (mixed_block ? sfb_mixed_q : sfb_short_q)
                                   : sfb_long_q;
    // row stride: long 23, short/mixed 40
    wire [8:0] sfb_base = is_short
        ? (({7'd0, samplerate_idx} + 9'd5) * 9'd40)
        : (({7'd0, samplerate_idx} + 9'd5) * 9'd23);

    // ---- spectral buffer ---------------------------------------------------
    // GOWIN BSRAM WIDTH TRAP. This array as a single 16-bit memory maps to
    // DPX9B at BIT_WIDTH=18, and that configuration reads back as ALL ZEROS on
    // hardware -- writes land (write enable high, non-zero data, address
    // advancing) and every read returns 0. Proven on the board with an isolated
    // self-test driven by nothing but a counter.
    //
    // Widening the declaration to 32 bits does NOT help: yosys sees that only
    // bits [15:0] are ever read and trims it straight back to 18.
    //
    // Two 8-bit halves map to DPX9B at BIT_WIDTH=9 -- the same configuration as
    // the bit reservoir, which works. 9 and 36 are known good on this device.
    reg [7:0] spec_lo [0:575];
    reg [7:0] spec_hi [0:575];

    reg  [9:0]  wr_addr;
    reg signed [15:0] wr_data;
    reg         wr_en;

    always @(posedge clk) begin
        if (wr_en) begin
            spec_lo[wr_addr] <= wr_data[7:0];
            spec_hi[wr_addr] <= wr_data[15:8];
        end
        spec_data <= {spec_hi[spec_addr], spec_lo[spec_addr]};
    end

    // ---- state -------------------------------------------------------------
    localparam [4:0]
        S_IDLE=0, S_CLR=1, S_RGN0=2, S_RGN1=3, S_BAND0=4, S_BAND1=5,
        S_T0=6, S_T1=7, S_T2=8, S_SKIPW=9, S_CODEW=11,
        S_VAL=12, S_LIN=13, S_LINW=14, S_SIGN=15, S_SIGNW=16, S_WRITE=17,
        S_C0=18, S_C1=19, S_C2=20, S_C3=21, S_CSK=22, S_CVAL=23, S_CSGN=24,
        S_BANDW=25, S_SKIPW0=26, S_DONE=27;

    reg [4:0]  st;
    reg [9:0]  idx;             // next spectral position
    reg [9:0]  clr;
    reg [9:0]  bvc;             // big_values*2 remaining
    reg [1:0]  ireg;
    reg [8:0]  sfb_i;
    reg [8:0]  rgn_left;        // bands left in this region
    reg [8:0]  np;              // values in this band
    reg [8:0]  pairs;
    reg [2:0]  w;
    reg [11:0] tbase;
    reg [3:0]  linbits;
    reg [13:0] leaf;
    reg [3:0]  vmag;            // 0..15 from the leaf nibble
    reg [15:0] vfull;           // after linbits
    reg        second;          // 0 = x (low nibble), 1 = y
    reg [7:0]  c1leaf;
    reg [1:0]  c1i;
    reg [1:0]  wait_c;

    wire [11:0] tabs_idx5 = tbase + {7'd0, res_peek[23 -: 5]};
    wire [11:0] tabs_idxw = tbase + {5'd0, (res_peek >> (5'd24 - {2'b0, w})) &
                                          ((7'd1 << w) - 7'd1)}
                                  - {{1{leaf[13]}}, leaf[13:3]};

    wire [15:0] lin_val = (res_peek >> (5'd24 - {1'b0, linbits})) &
                          ((16'd1 << linbits) - 16'd1);
    wire        sign_bit = res_peek[23];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; done <= 0; res_skip <= 0; res_skip_n <= 0;
            wr_en <= 0; wr_addr <= 0; wr_data <= 0;
            idx <= 0; clr <= 0; bvc <= 0; ireg <= 0; sfb_i <= 0;
            rgn_left <= 0; np <= 0; pairs <= 0; w <= 0; tbase <= 0;
            linbits <= 0; leaf <= 0; vmag <= 0; vfull <= 0; second <= 0;
            c1leaf <= 0; c1i <= 0; wait_c <= 0;
            tabs_addr <= 0; tsel_addr <= 0; c1_addr <= 0; sfb_addr <= 0;
        end else begin
            done     <= 1'b0;
            res_skip <= 1'b0;
            wr_en    <= 1'b0;

            case (st)
            S_IDLE: if (start) begin
                clr <= 0; st <= S_CLR;
            end

            // L3_huffman only writes up to the last decoded coefficient, so the
            // tail must be pre-zeroed -- the same requirement the reference meets
            // with memset(grbuf, 0, 576*2*sizeof(float)).
            S_CLR: begin
                wr_en   <= 1'b1;
                wr_addr <= clr;
                wr_data <= 16'sd0;
                if (clr == 10'd575) begin
                    idx <= 0; ireg <= 0; sfb_i <= 0; second <= 0;
                    bvc <= {big_values, 1'b0};
                    st  <= S_RGN0;
                end else clr <= clr + 1'b1;
            end

            // ---- start a region ------------------------------------------
            S_RGN0: begin
                if (bvc == 10'd0) begin
                    c1i <= 0; st <= S_C0;
                end else begin
                    case (ireg)
                        2'd0: tsel_addr <= {1'b0, table_select[4:0]};
                        2'd1: tsel_addr <= {1'b0, table_select[9:5]};
                        default: tsel_addr <= {1'b0, table_select[14:10]};
                    endcase
                    rgn_left <= (ireg == 2'd0) ? {1'b0, region0_count} :
                                (ireg == 2'd1) ? {1'b0, region1_count} : 9'd511;
                    sfb_addr <= sfb_base + sfb_i;
                    wait_c   <= 0;
                    st       <= S_RGN1;
                end
            end

            S_RGN1: begin                       // two cycles of ROM latency
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) begin
                    tbase   <= tindex_q;
                    linbits <= linb_q;
                    ireg    <= ireg + 2'd1;
                    st      <= S_BAND0;
                end
            end

            // ---- start a band --------------------------------------------
            S_BAND0: begin
                np    <= {1'b0, sfb_w} >> 1;    // width/2 pairs
                pairs <= ({1'b0, sfb_w} >> 1) > bvc[9:1] ? bvc[9:1]
                                                        : ({1'b0, sfb_w} >> 1);
                st    <= S_BAND1;
            end

            S_BAND1: begin
                if (pairs == 9'd0) begin
                    c1i <= 0; st <= S_C0;
                end else begin
                    w  <= 3'd5;
                    st <= S_T0;
                end
            end

            // ---- tree walk -----------------------------------------------
            S_T0: if (res_ready) begin
                tabs_addr <= tabs_idx5;
                wait_c    <= 0;
                st        <= S_T1;
            end

            S_T1: begin
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) begin leaf <= tabs_q; st <= S_T2; end
            end

            S_T2: begin
                if (leaf_s < 0) begin
                    res_skip   <= 1'b1;         // flush w bits, descend
                    res_skip_n <= {2'b0, w};
                    w          <= leaf[2:0];
                    st         <= S_SKIPW0;
                end else begin
                    res_skip   <= 1'b1;         // flush the code length
                    res_skip_n <= leaf[13:8] > 6'd24 ? 5'd24 : leaf[12:8];
                    second     <= 1'b0;
                    st         <= S_CODEW;
                end
            end

            // res_skip is registered: it is only asserted to the reservoir
            // DURING this state, so the window does not move until the end of
            // it. Computing tabs_idxw here would use the pre-skip bits. Costs
            // one cycle per tree level; there are at most a few per codeword.
            S_SKIPW0: st <= S_SKIPW;

            S_SKIPW: if (res_ready) begin       // window is fresh now
                tabs_addr <= tabs_idxw;
                wait_c    <= 0;
                st        <= S_T1;
            end

            S_CODEW: st <= S_VAL;               // settle after the skip

            // ---- one value (x then y) ------------------------------------
            S_VAL: begin
                vmag <= second ? leaf[7:4] : leaf[3:0];
                if ((second ? leaf[7:4] : leaf[3:0]) == 4'd15 && linbits != 0)
                    st <= S_LIN;
                else begin
                    vfull <= {12'd0, (second ? leaf[7:4] : leaf[3:0])};
                    st    <= S_SIGN;
                end
            end

            S_LIN: if (res_ready) begin
                vfull      <= 16'd15 + lin_val;
                res_skip   <= 1'b1;
                res_skip_n <= {1'b0, linbits};
                st         <= S_LINW;
            end

            S_LINW: st <= S_SIGN;

            S_SIGN: if (vfull == 16'd0) begin
                wr_en   <= 1'b1;                // zero: no sign bit
                wr_addr <= idx;
                wr_data <= 16'sd0;
                st      <= S_WRITE;
            end else if (res_ready) begin
                wr_en      <= 1'b1;
                wr_addr    <= idx;
                wr_data    <= sign_bit ? -$signed({1'b0, vfull[14:0]})
                                       :  $signed({1'b0, vfull[14:0]});
                res_skip   <= 1'b1;
                res_skip_n <= 5'd1;
                st         <= S_SIGNW;
            end

            S_SIGNW: st <= S_WRITE;

            S_WRITE: begin
                idx <= idx + 1'b1;
                if (!second) begin
                    second <= 1'b1;
                    st     <= S_VAL;
                end else begin
                    second <= 1'b0;
                    bvc    <= bvc - 10'd2;
                    if (pairs == 9'd1) begin
                        // band finished
                        sfb_i <= sfb_i + 1'b1;
                        if (bvc <= 10'd2) begin
                            c1i <= 0; st <= S_C0;
                        end else if (rgn_left == 9'd0) begin
                            st <= S_RGN0;
                        end else begin
                            rgn_left <= rgn_left - 1'b1;
                            sfb_addr <= sfb_base + sfb_i + 1'b1;
                            wait_c   <= 0;
                            st       <= S_BANDW;
                        end
                    end else begin
                        pairs <= pairs - 1'b1;
                        w     <= 3'd5;
                        st    <= S_T0;
                    end
                end
            end

            S_BANDW: begin
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) st <= S_BAND0;
            end

            // ---- count1 quads --------------------------------------------
            // STRICTLY greater, matching the reference's `BSPOS > layer3gr_limit`.
            // With >= the loop quit one quad early whenever a granule's count1
            // data ended exactly on the limit, dropping the last +/-1 values --
            // invisible on ordinary music and caught only by l3-he_mode, whose
            // granules are built to land right on the boundary. The real break
            // is the post-flush check in S_CVAL, which the reference also uses;
            // this one is just a guard against a starved reservoir.
            S_C0: if (res_bits > bit_limit) begin
                st <= S_DONE;
            end else if (res_ready) begin
                c1_addr <= count1_table ? (6'd32 + {2'd0, res_peek[23 -: 4]})
                                        : {2'd0, res_peek[23 -: 4]};
                wait_c  <= 0;
                st      <= S_C1;
            end

            S_C1: begin
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) begin c1leaf <= c1_q; st <= S_C2; end
            end

            S_C2: begin
                if (!c1leaf[3]) begin
                    // Reference: codebook[(leaf >> 3) + (bs_cache << 4 >> (32 - (leaf & 3)))]
                    //   - the sub-table offset is leaf >> 3, i.e. bits [7:3]
                    //     (not [7:4] -- that cost a factor of two on the offset)
                    //   - the extra index bits come AFTER the first 4 already
                    //     peeked, so they are peek[19 -: n], not the top n
                    c1_addr <= (count1_table ? 6'd32 : 6'd0) + {1'd0, c1leaf[7:3]}
                             + {4'd0, (res_peek >> (5'd20 - {3'd0, c1leaf[1:0]}))
                                      & ((6'd1 << c1leaf[1:0]) - 6'd1)};
                    wait_c  <= 0;
                    st      <= S_C3;
                end else begin
                    res_skip   <= 1'b1;
                    res_skip_n <= {2'b0, c1leaf[2:0]};
                    c1i        <= 0;
                    st         <= S_CSK;
                end
            end

            S_C3: begin
                wait_c <= wait_c + 2'd1;
                if (wait_c == 2'd1) begin c1leaf <= c1_q; st <= S_C2; end
            end

            S_CSK: st <= S_CVAL;                // settle after the code skip

            // ONCE PER QUAD, not once per value. The reference tests
            // `BSPOS > layer3gr_limit` at the top of the loop and then writes
            // all four values unconditionally, so a quad whose sign bits run
            // past the limit still lands in full. Re-testing per value dropped
            // the tail values of any granule ending on the boundary.
            S_CVAL: if (c1i == 2'd0 && res_bits > bit_limit) begin
                st <= S_DONE;
            end else if (idx >= 10'd576) begin
                st <= S_DONE;
            end else begin
                // bit (128 >> c1i) of the leaf selects whether this position
                // carries a +/-1
                if (c1leaf[7 - c1i]) begin
                    if (res_ready) begin
                        wr_en      <= 1'b1;
                        wr_addr    <= idx;
                        wr_data    <= sign_bit ? -16'sd1 : 16'sd1;
                        res_skip   <= 1'b1;
                        res_skip_n <= 5'd1;
                        st         <= S_CSGN;
                    end
                end else begin
                    idx <= idx + 1'b1;
                    if (c1i == 2'd3) begin c1i <= 0; st <= S_C0; end
                    else c1i <= c1i + 2'd1;
                end
            end

            S_CSGN: begin
                idx  <= idx + 1'b1;
                c1i  <= (c1i == 2'd3) ? 2'd0 : c1i + 2'd1;
                st   <= (c1i == 2'd3) ? S_C0 : S_CVAL;
            end

            S_DONE: begin done <= 1'b1; st <= S_IDLE; end
            default: st <= S_IDLE;
            endcase
        end
    end

endmodule
