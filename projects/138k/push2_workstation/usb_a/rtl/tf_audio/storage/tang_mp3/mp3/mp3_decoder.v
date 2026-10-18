// MP3 spectral + subband decoder: byte stream in, subband samples out.
//
// Wires the stages together and owns the sequencing that each stage's
// testbench used to fake:
//
//   mp3_bitstream -> mp3_sideinfo
//                 -> mp3_reservoir -> mp3_scalefac -> mp3_huffman -> mp3_requant
//                                                                       |
//                              mp3_spectra (both channels of one granule)
//                                                                       |
//                    mp3_stereo -> mp3_reorder -> mp3_antialias -> mp3_imdct
//
// Per frame, per granule: decode every channel's spectra, THEN stereo (which
// needs both channels resident), THEN the per-channel tail. That ordering is
// the reference's and is why mp3_spectra is shared rather than per stage.
//
// BACKPRESSURE. mp3_sideinfo holds one frame's fields, so the framer must not
// parse frame N+1 until frame N is fully decoded. It parks itself on main_done
// and waits for `frame_ack`. It has no elastic buffer, so `in_ready` also goes
// low while parked and the byte source must hold off -- ignoring that cost two
// frames in three on the first integration run, because the framer resumed
// mid-frame and had to hunt for the next sync every time. In hardware the SD
// byte FIFO absorbs it: a frame decodes in ~200k cycles against ~3400 cycles
// per byte at 128 kbps, so a few dozen bytes queue up.
//
// The reservoir is positioned ONCE per frame (after main_done, since the decode
// window is history + this frame). Each granule then reads on from where the
// previous one stopped, and the sequencer skips any bits a granule leaves
// unread so the next one starts at part2_3_length exactly -- the same absolute
// `layer3gr_limit` bookkeeping the reference does.
module mp3_decoder (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        restart,        // new track/seek

    // byte stream (from the SD FIFO)
    input  wire        inen,
    input  wire [7:0]  inbyte,
    output wire        in_ready,       // low while a frame is being decoded

    output wire [19:0] samplerate_hz,
    output wire        is_mono,

    // ---- checkpoint: requantized spectra, one granule/channel at a time ----
    // Exists for the M4 regression (diffed against spectra.txt). In hardware
    // tie spec_ack high; the cost is one cycle per channel.
    output reg         spec_valid,
    output reg         spec_gr,
    output reg         spec_ch,
    input  wire        spec_ack,
    input  wire [10:0] spec_addr,      // {ch, index}
    output wire signed [31:0] spec_data,

    // ---- output: subband samples for a whole granule, both channels --------
    output reg         sb_valid,
    output reg         sb_gr,
    input  wire        sb_ack,
    input  wire [10:0] sb_addr,        // {ch, index}
    output wire signed [31:0] sb_data,

    // ---- output: PCM for the granule, both channels ------------------------
    output reg         pcm_valid,
    input  wire        pcm_ack,
    input  wire [10:0] pcm_addr,        // {ch, sample}, 576 per channel
    output wire signed [15:0] pcm_data,

    // status
    output wire [15:0] frame_count,
    output wire [15:0] resync_count,
    output reg  [15:0] skipped_frames, // reservoir not primed yet
    output reg  [15:0] istereo_frames, // granules that used intensity stereo
    output reg  [15:0] stuck_frames    // frames abandoned by the watchdog
);
    // ---- sequencer state ----------------------------------------------------
    // Listed in execution order, numbered contiguously. The previous layout
    // grew by appending, which is how Q_SYNTH silently collided with Q_SEEKW.
    localparam [4:0]
        Q_IDLE=0,    Q_POS=1,     Q_CHK=2,      Q_SCF=3,    Q_HUF=4,
        Q_RQ=5,      Q_SPEC=6,    Q_SEEKW=7,    Q_TRIM=8,   Q_TRIMW=9,
        Q_TRIMW2=10, Q_NEXTCH=11, Q_STEREO=12,  Q_REORD=13, Q_AA=14,
        Q_IMDCT=15,  Q_SYNTH=16,  Q_NEXTPCH=17, Q_GRDONE=18, Q_SBACK=19,
        Q_PCM=20,    Q_NEXTGR=21, Q_DROP=22;

    reg [4:0] qst;
    reg       nch_m1;                  // 0 = mono, 1 = stereo

    // WATCHDOG. Every stage waits on `res_ready` somewhere, and a malformed or
    // truncated stream can leave one waiting forever -- that is exactly how
    // l3-si hung the sweep before the reservoir was zero-initialized. In a
    // player that is not a failed test, it is music that stops and never comes
    // back. A frame that overruns is abandoned and the decoder resynchronizes.
    //
    // Counting pauses in the consumer-paced states, so a slow consumer on the
    // debug checkpoints cannot trip it; in hardware those acks are tied high.
    localparam [21:0] WD_LIMIT = 22'd2000000;   // ~37 ms at 54 MHz
    reg  [21:0] wd;
    wire        wd_paused = (qst == Q_IDLE)  || (qst == Q_SPEC)
                         || (qst == Q_SBACK) || (qst == Q_PCM);
    wire        wd_fire   = (wd == WD_LIMIT);

    // Recovery is a full internal restart: stage FSMs have no abort input, and
    // after a stream error the filter histories are meaningless anyway.
    wire        abort = wd_fire;

    // ---- framer ------------------------------------------------------------
    wire        hdr_valid, side_en, side_done, main_en, main_done, main_discard;
    wire [7:0]  side_byte, main_byte;
    wire [1:0]  mode, mode_ext, samplerate_idx;
    reg         frame_ack;

    mp3_bitstream u_bs (
        .clk(clk), .rst_n(rst_n), .restart(restart | abort), .frame_ack(frame_ack),
        .in_ready(in_ready),
        .inen(inen), .inbyte(inbyte),
        .hdr_valid(hdr_valid), .bitrate_idx(), .samplerate_idx(samplerate_idx),
        .samplerate_hz(samplerate_hz), .mode(mode), .mode_ext(mode_ext),
        .crc_present(), .is_mono(is_mono), .frame_bytes(),
        .side_en(side_en), .side_byte(side_byte), .side_done(side_done),
        .main_en(main_en), .main_byte(main_byte), .main_done(main_done),
        .main_discard(main_discard),
        .frame_count(frame_count), .resync_count(resync_count)
    );

    // MS stereo = joint stereo with mode_ext bit 1 (bit 0 is intensity stereo)
    wire ms_stereo = (mode == 2'd1) && mode_ext[1];

    // ---- side info ---------------------------------------------------------
    reg         sel_gr, sel_ch;
    wire        si_valid;
    wire [8:0]  main_data_begin;
    wire [11:0] part2_3_length;
    wire [8:0]  big_values, subblock_gain;
    wire [7:0]  global_gain, region0_count, region1_count;
    wire [3:0]  scalefac_compress, scfsi_ch;
    wire [14:0] table_select;
    wire [1:0]  block_type;
    wire        window_switching, mixed_block, preflag, scalefac_scale, count1_table;

    mp3_sideinfo u_si (
        .clk(clk), .rst_n(rst_n), .is_mono(is_mono),
        .side_en(side_en), .side_byte(side_byte), .side_done(side_done),
        .si_valid(si_valid), .main_data_begin(main_data_begin),
        .sel_gr(sel_gr), .sel_ch(sel_ch),
        .part2_3_length(part2_3_length), .big_values(big_values),
        .global_gain(global_gain), .scalefac_compress(scalefac_compress),
        .window_switching(window_switching), .block_type(block_type),
        .mixed_block(mixed_block), .table_select(table_select),
        .subblock_gain(subblock_gain), .region0_count(region0_count),
        .region1_count(region1_count), .preflag(preflag),
        .scalefac_scale(scalefac_scale), .count1_table(count1_table),
        .scfsi_ch(scfsi_ch)
    );

    // ---- reservoir ---------------------------------------------------------
    reg         res_start;
    wire        res_valid, res_ready;
    wire [23:0] res_peek;
    wire [17:0] res_bits;
    wire        scf_skip, huf_skip;
    wire [4:0]  scf_skip_n, huf_skip_n;
    reg         seq_skip;
    reg  [4:0]  seq_skip_n;
    reg         seq_seek;
    reg  [17:0] bit_limit;   // absolute end of this granule, in window bits

    mp3_reservoir u_res (
        .clk(clk), .rst_n(rst_n), .restart(restart | abort),
        .frame_mark(side_done), .wr(main_en), .wdata(main_byte),
        .frame_end(main_done), .discard(main_discard),
        .main_data_begin(main_data_begin),
        .start(res_start), .valid(res_valid),
        .ready(res_ready), .peek(res_peek),
        .skip(scf_skip | huf_skip | seq_skip),
        .skip_n(scf_skip ? scf_skip_n : huf_skip ? huf_skip_n : seq_skip_n),
        .seek(seq_seek), .seek_bits(bit_limit),
        .bits_read(res_bits)
    );

    // ---- shared spectra RAM and its port muxes -----------------------------
    // Exactly one stage is active at a time, so these are plain selects rather
    // than an arbiter.
    wire        rq_wr_en;
    wire [10:0] rq_wr_addr;
    wire signed [31:0] rq_wr_data;

    wire        ster_rd_sel, ro_rd_sel, aa_rd_sel, im_rd_sel;
    wire [10:0] ster_rd_addr, ro_rd_addr, aa_rd_addr, im_rd_addr;
    wire        ster_wr_en, ro_wr_en, aa_wr_en, im_wr_en;
    wire [10:0] ster_wr_addr, ro_wr_addr, aa_wr_addr, im_wr_addr;
    wire signed [31:0] ster_wr_data, ro_wr_data, aa_wr_data, im_wr_data;
    wire [10:0] syn_rd_addr;

    wire [10:0] spec_rd_addr = ster_rd_sel      ? ster_rd_addr
                             : ro_rd_sel        ? ro_rd_addr
                             : aa_rd_sel        ? aa_rd_addr
                             : im_rd_sel        ? im_rd_addr
                             : (qst == Q_SYNTH) ? syn_rd_addr
                             : (qst == Q_SBACK) ? sb_addr
                             :                    spec_addr;

    // The subband checkpoint now reads the same RAM the spectra checkpoint
    // does -- the IMDCT overwrites each band in place -- so the two share a
    // data path and are distinguished by which sequencer state is active.
    assign sb_data = spec_data;

    mp3_spectra u_spec (
        .clk(clk),
        .wr_en  (rq_wr_en   | ster_wr_en | ro_wr_en | aa_wr_en | im_wr_en),
        .wr_addr(rq_wr_en   ? rq_wr_addr
               : ster_wr_en ? ster_wr_addr
               : ro_wr_en   ? ro_wr_addr
               : aa_wr_en   ? aa_wr_addr : im_wr_addr),
        .wr_data(rq_wr_en   ? rq_wr_data
               : ster_wr_en ? ster_wr_data
               : ro_wr_en   ? ro_wr_data
               : aa_wr_en   ? aa_wr_data : im_wr_data),
        .rd_addr(spec_rd_addr), .rd_data(spec_data)
    );

    // ---- spectral stages ---------------------------------------------------

    // ---- shared multiplier ---------------------------------------------------
    // ONE multiplier for the whole decoder. Requantization, stereo, antialias,
    // the IMDCT and the filterbank each used to carry their own -- about 13500
    // LUT slots, over half the decoder, on a device where nothing infers DSP.
    // They never run together: the sequencer drives exactly one at a time, the
    // same property the shared mp3_spectra port mux and mp3_sfbtab already rely
    // on. Sized 41x27 so requant's 40x26 fits alongside the others' 32x22.
    wire signed [31:0] rq_mul_a, ster_mul_a, aa_mul_a, im_mul_a, syn_mul_a;
    wire signed [21:0] rq_mul_b, ster_mul_b, aa_mul_b, im_mul_b, syn_mul_b;

    // AND-OR, not a priority mux. Exactly one stage is active, so masking and
    // OR-ing gives the same result as a five-way select -- but yosys maps a
    // chain of conditionals onto MUX2_LUT7/8 cells, which need a contiguous LUT
    // group and were the last thing nextpnr could not place. An OR reduction
    // becomes an ordinary LUT tree that fits anywhere.
    wire sel_rq   = (qst == Q_RQ);
    wire sel_ster = (qst == Q_STEREO);
    wire sel_aa   = (qst == Q_AA);
    wire sel_syn  = (qst == Q_SYNTH);
    wire sel_im   = ~(sel_rq | sel_ster | sel_aa | sel_syn);

    wire signed [31:0] mul_a = ({32{sel_rq}}   & rq_mul_a)
                             | ({32{sel_ster}} & ster_mul_a)
                             | ({32{sel_aa}}   & aa_mul_a)
                             | ({32{sel_syn}}  & syn_mul_a)
                             | ({32{sel_im}}   & im_mul_a);
    wire signed [21:0] mul_b = ({22{sel_rq}}   & rq_mul_b)
                             | ({22{sel_ster}} & ster_mul_b)
                             | ({22{sel_aa}}   & aa_mul_b)
                             | ({22{sel_syn}}  & syn_mul_b)
                             | ({22{sel_im}}   & im_mul_b);
    wire rq_mul_go, ster_mul_go, aa_mul_go, im_mul_go, syn_mul_go;

    // FOUR-PASS. Operand width dominates a LUT-built multiplier on a device
    // where nothing infers DSP: 32x22 is 4752 slots, 17x22 is 2500, 9x22 is
    // 1055. The decoder was placeable on its own but not alongside the SD stack,
    // so the narrowest practical unit wins.
    //
    //     a * b = ((((a3*b) << 8 + a2*b) << 8 + a1*b) << 8) + a0*b
    //
    // a3 is the signed top byte; a2..a0 ride as positive 9-bit values. Four
    // cycles per product instead of two, which the frame budget still covers.
    //
    // The result is REGISTERED and HOLDS until the next request, so callers need
    // only enough latency rather than an exact sampling cycle.
    wire        mul_go = (qst == Q_RQ)     ? rq_mul_go
                       : (qst == Q_STEREO) ? ster_mul_go
                       : (qst == Q_AA)     ? aa_mul_go
                       : (qst == Q_SYNTH)  ? syn_mul_go
                       :                     im_mul_go;

    // TWO passes of 16 bits, not four of 8. Profiling the decoder by state
    // showed Q_IMDCT at 48% and Q_SYNTH at 46% of all cycles, and both loops
    // issue exactly one tap per multiplier latency -- so the number of passes
    // sets the throughput of 94% of the decoder. Four passes could not sustain
    // real time in stereo (841k cycles/granule against a 705k budget); two
    // pass costs ~1.4k LUT and halves it.
    //   a = a_hi*2^16 + a_lo,   a_hi signed 16b, a_lo unsigned 16b
    //   a*b = ((a_hi*b) << 16) + a_lo*b
    // TWO ALTERNATING ENGINES, so the unit is fully pipelined: it accepts a
    // mul_go every cycle and the product is always valid `MUL_WAIT (=2) cycles
    // later, whichever engine served it.
    //
    // Each engine still does the same two 16-bit passes and takes two cycles;
    // with two of them, odd and even requests interleave. That matters because
    // the MAC loops in synthesis and IMDCT were issuing one tap per multiplier
    // LATENCY, not per throughput -- 94% of all decode cycles spent waiting on
    // a busy multiplier. Interleaving halves the decoder's runtime for the cost
    // of a second 17x22 array, which buys back the timing that -noalu costs.
    reg               mul_phase;         // which engine takes the next request
    reg  signed [31:0] mul_a_sr [0:1];
    reg  signed [21:0] mul_b_r  [0:1];
    reg  signed [53:0] mul_acc  [0:1];
    reg  signed [53:0] mul_p_r  [0:1];
    reg               mul_busy  [0:1];

    // Engine e sees the raw stage operands on its first pass and its own held
    // copies on the second, so the wide five-way stage mux is only ever in the
    // first pass's cone (leaving it combinational for both passes packed into
    // MUX2_LUT7 cells that would not place).
    wire start0 = mul_go & ~mul_phase;
    wire start1 = mul_go &  mul_phase;

    wire signed [16:0] chunk0 = start0 ? {mul_a[31], mul_a[31:16]}
                                       : {1'b0, mul_a_sr[0][31:16]};
    wire signed [16:0] chunk1 = start1 ? {mul_a[31], mul_a[31:16]}
                                       : {1'b0, mul_a_sr[1][31:16]};
    wire signed [21:0] b0     = start0 ? mul_b : mul_b_r[0];
    wire signed [21:0] b1     = start1 ? mul_b : mul_b_r[1];

    wire signed [38:0] part0  = chunk0 * b0;
    wire signed [38:0] part1  = chunk1 * b1;
    // |a_hi*b| <= 2^36, so acc[37] carries its sign and nothing above it is
    // significant; shifting acc[37:0] up by 16 lands that sign in bit 53.
    wire signed [53:0] shift0 = {mul_acc[0][37:0], 16'd0};
    wire signed [53:0] shift1 = {mul_acc[1][37:0], 16'd0};

    integer mi_;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mul_phase <= 1'b0;
            for (mi_ = 0; mi_ < 2; mi_ = mi_ + 1) begin
                mul_acc[mi_]  <= 54'sd0; mul_p_r[mi_] <= 54'sd0;
                mul_a_sr[mi_] <= 32'sd0; mul_b_r[mi_] <= 22'sd0;
                mul_busy[mi_] <= 1'b0;
            end
        end else begin
            if (mul_go) mul_phase <= ~mul_phase;

            if (start0) begin
                mul_acc[0]  <= {{15{part0[38]}}, part0};   // a_hi * b
                mul_a_sr[0] <= {mul_a[15:0], 16'd0};       // a_lo next
                mul_b_r[0]  <= mul_b;
                mul_busy[0] <= 1'b1;
            end else if (mul_busy[0]) begin
                mul_p_r[0]  <= shift0 + {{15{part0[38]}}, part0};
                mul_busy[0] <= 1'b0;
            end

            if (start1) begin
                mul_acc[1]  <= {{15{part1[38]}}, part1};
                mul_a_sr[1] <= {mul_a[15:0], 16'd0};
                mul_b_r[1]  <= mul_b;
                mul_busy[1] <= 1'b1;
            end else if (mul_busy[1]) begin
                mul_p_r[1]  <= shift1 + {{15{part1[38]}}, part1};
                mul_busy[1] <= 1'b0;
            end
        end
    end

    // A request accepted on cycle T is written into mul_p_r[e] at the end of
    // T+1 and read during T+2, so the result select must follow the engine that
    // served the request TWO cycles back -- not the current phase, which has
    // already moved on when requests arrive every cycle. Between results it
    // holds, so the sparse users (requant, stereo, antialias) still see a stable
    // product for as long as they take to read it.
    reg e1, e2, v1, v2, sel_hold;
    wire sel_due = v2 ? e2 : sel_hold;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            e1 <= 1'b0; e2 <= 1'b0; v1 <= 1'b0; v2 <= 1'b0; sel_hold <= 1'b0;
        end else begin
            e1 <= mul_phase;  v1 <= mul_go;
            e2 <= e1;         v2 <= v1;
            sel_hold <= sel_due;
        end
    end

    wire signed [53:0] mul_p = sel_due ? mul_p_r[1] : mul_p_r[0];

    // ---- shared scalefactor-band tables ------------------------------------
    // One instance for four stages. They run strictly one at a time, so the
    // address is a plain select, and the eight BSRAM blocks the duplicated
    // copies used to cost are the difference between fitting M6 and not.
    wire [8:0] huf_sfb_addr, rq_sfb_addr, ro_sfb_addr, ster_sfb_addr;
    wire [7:0] sfb_long_q, sfb_short_q, sfb_mixed_q;

    mp3_sfbtab u_sfb (
        .clk(clk),
        .addr(  (qst == Q_HUF)                      ? huf_sfb_addr
              : (qst == Q_RQ)                       ? rq_sfb_addr
              : (qst == Q_REORD)                    ? ro_sfb_addr
              :                                       ster_sfb_addr),
        .long_q(sfb_long_q), .short_q(sfb_short_q), .mixed_q(sfb_mixed_q)
    );

    // Intensity stereo reads channel 1's raw scalefactors straight out of
    // mp3_scalefac. No arbitration needed: scalefactors are decoded per channel
    // long before stereo runs, and stereo never runs while they are.
    wire [5:0] ster_ist_band;
    wire [7:0] scf_ist_data;

    reg        scf_start, huf_start, rq_start;
    wire       scf_done, huf_done, rq_done;
    wire [5:0] rq_sf_addr;
    wire [7:0] scf_data;
    wire [9:0] rq_raw_addr;
    wire signed [15:0] huf_data;

    mp3_scalefac u_scf (
        .clk(clk), .rst_n(rst_n), .start(scf_start),
        .ch(sel_ch), .gr1(sel_gr),
        .scalefac_compress(scalefac_compress),
        .window_switching(window_switching), .block_type(block_type),
        .mixed_block(mixed_block), .scfsi(scfsi_ch), .preflag(preflag),
        .subblock_gain(subblock_gain), .scalefac_scale(scalefac_scale),
        .res_ready(res_ready), .res_peek(res_peek),
        .res_skip(scf_skip), .res_skip_n(scf_skip_n),
        .done(scf_done), .n_bands(),
        .sf_addr(rq_sf_addr), .sf_data(scf_data),
        .ist_band(ster_ist_band), .ist_data(scf_ist_data)
    );

    mp3_huffman u_huf (
        .clk(clk), .rst_n(rst_n), .start(huf_start),
        .big_values(big_values), .table_select(table_select),
        .region0_count(region0_count), .region1_count(region1_count),
        .count1_table(count1_table),
        .window_switching(window_switching), .block_type(block_type),
        .mixed_block(mixed_block), .samplerate_idx(samplerate_idx),
        .bit_limit(bit_limit),
        .res_ready(res_ready), .res_peek(res_peek), .res_bits(res_bits),
        .res_skip(huf_skip), .res_skip_n(huf_skip_n),
        .sfb_addr(huf_sfb_addr), .sfb_long_q(sfb_long_q),
        .sfb_short_q(sfb_short_q), .sfb_mixed_q(sfb_mixed_q),
        .done(huf_done), .spec_addr(rq_raw_addr), .spec_data(huf_data)
    );

    mp3_requant u_rq (
        .clk(clk), .rst_n(rst_n), .start(rq_start),
        .global_gain(global_gain), .scalefac_scale(scalefac_scale),
        .ms_stereo(ms_stereo),
        .window_switching(window_switching), .block_type(block_type),
        .mixed_block(mixed_block), .samplerate_idx(samplerate_idx),
        .ch(sel_ch),
        .sf_addr(rq_sf_addr), .sf_data(scf_data),
        .raw_addr(rq_raw_addr), .raw_data(huf_data),
        .sfb_addr(rq_sfb_addr), .sfb_long_q(sfb_long_q),
        .sfb_short_q(sfb_short_q), .sfb_mixed_q(sfb_mixed_q),
        .mul_a(rq_mul_a), .mul_b(rq_mul_b), .mul_p(mul_p),
        .mul_go(rq_mul_go),
        .done(rq_done),
        .wr_en(rq_wr_en), .wr_addr(rq_wr_addr), .wr_data(rq_wr_data)
    );

    // ---- subband stages ----------------------------------------------------
    reg  ster_start, ro_start, aa_start, im_start;
    wire ster_done, ro_done, aa_done, im_done, ster_ist_active;

    mp3_stereo u_ster (
        .clk(clk), .rst_n(rst_n), .start(ster_start),
        .is_mono(is_mono), .mode(mode), .mode_ext(mode_ext),
        .samplerate_idx(samplerate_idx),
        .window_switching(window_switching), .block_type(block_type),
        .mixed_block(mixed_block),
        .ist_band(ster_ist_band), .ist_data(scf_ist_data),
        .sfb_addr(ster_sfb_addr), .sfb_long_q(sfb_long_q),
        .sfb_short_q(sfb_short_q), .sfb_mixed_q(sfb_mixed_q),
        .mul_a(ster_mul_a), .mul_b(ster_mul_b), .mul_p(mul_p),
        .mul_go(ster_mul_go),
        .done(ster_done), .ist_active(ster_ist_active),
        .rd_addr(ster_rd_addr), .rd_data(spec_data),
        .wr_en(ster_wr_en), .wr_addr(ster_wr_addr), .wr_data(ster_wr_data)
    );

    mp3_reorder u_ro (
        .clk(clk), .rst_n(rst_n), .start(ro_start),
        .ch(sel_ch), .samplerate_idx(samplerate_idx),
        .window_switching(window_switching), .block_type(block_type),
        .mixed_block(mixed_block),
        .sfb_addr(ro_sfb_addr), .sfb_long_q(sfb_long_q),
        .sfb_short_q(sfb_short_q), .sfb_mixed_q(sfb_mixed_q),
        .done(ro_done),
        .rd_addr(ro_rd_addr), .rd_data(spec_data),
        .wr_en(ro_wr_en), .wr_addr(ro_wr_addr), .wr_data(ro_wr_data)
    );

    mp3_antialias u_aa (
        .clk(clk), .rst_n(rst_n), .start(aa_start),
        .ch(sel_ch),
        .window_switching(window_switching), .block_type(block_type),
        .mixed_block(mixed_block),
        .mul_a(aa_mul_a), .mul_b(aa_mul_b), .mul_p(mul_p),
        .mul_go(aa_mul_go),
        .done(aa_done),
        .rd_addr(aa_rd_addr), .rd_data(spec_data),
        .wr_en(aa_wr_en), .wr_addr(aa_wr_addr), .wr_data(aa_wr_data)
    );

    // The subband buffer is read either by the consumer (M5 checkpoint) or by
    // the filterbank; they never overlap, since Q_SYNTH runs before the granule
    // is announced.

    mp3_imdct u_im (
        .clk(clk), .rst_n(rst_n), .start(im_start), .flush(restart | abort),
        .ch(sel_ch),
        .window_switching(window_switching), .block_type(block_type),
        .mixed_block(mixed_block),
        .mul_a(im_mul_a), .mul_b(im_mul_b), .mul_p(mul_p),
        .mul_go(im_mul_go),
        .done(im_done),
        .rd_addr(im_rd_addr), .rd_data(spec_data),
        .wr_en(im_wr_en), .wr_addr(im_wr_addr), .wr_data(im_wr_data)
    );

    reg  syn_start;
    wire syn_done;

    mp3_synth u_syn (
        .clk(clk), .rst_n(rst_n), .start(syn_start), .flush(restart | abort),
        .ch(sel_ch),
        .sb_addr(syn_rd_addr), .sb_data(spec_data),
        .mul_a(syn_mul_a), .mul_b(syn_mul_b), .mul_p(mul_p),
        .mul_go(syn_mul_go),
        .done(syn_done),
        .pcm_addr(pcm_addr), .pcm_data(pcm_data)
    );

    // ---- sequencer ---------------------------------------------------------

    assign ster_rd_sel = (qst == Q_STEREO);
    assign ro_rd_sel   = (qst == Q_REORD);
    assign aa_rd_sel   = (qst == Q_AA);
    assign im_rd_sel   = (qst == Q_IMDCT);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            qst <= Q_IDLE; frame_ack <= 1'b0; res_start <= 1'b0;
            scf_start <= 0; huf_start <= 0; rq_start <= 0;
            ster_start <= 0; ro_start <= 0; aa_start <= 0; im_start <= 0;
            syn_start <= 0; pcm_valid <= 0;
            sel_gr <= 0; sel_ch <= 0; bit_limit <= 0;
            spec_valid <= 0; spec_gr <= 0; spec_ch <= 0;
            sb_valid <= 0; sb_gr <= 0;
            seq_skip <= 0; seq_skip_n <= 0; seq_seek <= 0;
            skipped_frames <= 0; istereo_frames <= 0; nch_m1 <= 0;
            stuck_frames <= 0; wd <= 0;
        end else begin
            res_start  <= 1'b0;
            frame_ack  <= 1'b0;
            scf_start  <= 1'b0;
            huf_start  <= 1'b0;
            rq_start   <= 1'b0;
            ster_start <= 1'b0;
            ro_start   <= 1'b0;
            aa_start   <= 1'b0;
            im_start   <= 1'b0;
            syn_start  <= 1'b0;
            pcm_valid  <= 1'b0;
            spec_valid <= 1'b0;
            sb_valid   <= 1'b0;
            seq_skip   <= 1'b0;
            seq_seek   <= 1'b0;

            // watchdog bookkeeping
            if (qst == Q_IDLE)      wd <= 22'd0;
            else if (!wd_paused)    wd <= wd + 22'd1;

            if (restart) begin
                qst <= Q_IDLE;
                wd  <= 22'd0;
            end else if (wd_fire) begin
                stuck_frames <= stuck_frames + 1'b1;
                wd           <= 22'd0;
                qst          <= Q_IDLE;
            end else case (qst)

            // main_done means the frame's main data is fully in the reservoir,
            // which is when it can be positioned. The framer is already parked
            // in S_HOLD, so nothing needs asserting here to hold it.
            Q_IDLE: if (main_done) begin
                res_start <= 1'b1;
                sel_gr    <= 1'b0;
                sel_ch    <= 1'b0;
                bit_limit <= 18'd0;
                nch_m1    <= ~is_mono;
                qst       <= Q_POS;
            end

            Q_POS: qst <= Q_CHK;           // let res_valid settle

            // A frame whose main_data_begin exceeds the history available --
            // right after a seek, track change or resync -- cannot be decoded.
            // Skipping it is correct behaviour, not an error.
            Q_CHK: if (!res_valid) begin
                skipped_frames <= skipped_frames + 1'b1;
                qst <= Q_DROP;
            end else begin
                bit_limit <= bit_limit + {6'd0, part2_3_length};
                scf_start <= 1'b1;
                qst       <= Q_SCF;
            end

            Q_SCF: if (scf_done) begin huf_start <= 1'b1; qst <= Q_HUF; end
            Q_HUF: if (huf_done) begin rq_start  <= 1'b1; qst <= Q_RQ;  end
            Q_RQ:  if (rq_done) begin
                spec_valid <= 1'b1;
                spec_gr    <= sel_gr;
                spec_ch    <= sel_ch;
                qst        <= Q_SPEC;
            end

            // Seek to this granule's end, then let Q_TRIM walk off the last
            // 0..7 bits. A seek rather than a forward skip because Huffman can
            // finish either side of the limit.
            Q_SPEC: if (spec_ack) begin
                seq_seek <= 1'b1;
                qst      <= Q_SEEKW;
            end

            Q_SEEKW: qst <= Q_TRIM;      // let the reservoir re-arm

            // SETTLE AFTER THE SKIP. `seq_skip` is registered, so the
            // reservoir consumes a cycle later and res_bits is stale for two
            // more. Re-testing it immediately issued the skip a second time and
            // overshot -- granule 1 then started 4 bits late and decoded to
            // garbage. This is the same registered-skip trap as in mp3_scalefac
            // and mp3_huffman; it stayed hidden here only because Huffman used
            // to stop short of the limit, so the skip path almost never ran.
            Q_TRIM: if (res_bits >= bit_limit) begin
                qst <= Q_NEXTCH;
            end else if (res_ready) begin
                seq_skip   <= 1'b1;
                seq_skip_n <= ((bit_limit - res_bits) > 18'd24) ? 5'd24
                              : (bit_limit - res_bits);
                qst        <= Q_TRIMW;
            end

            Q_TRIMW:  qst <= Q_TRIMW2;
            Q_TRIMW2: qst <= Q_TRIM;

            // Every channel's spectra must be decoded before stereo, which
            // needs L and R together.
            Q_NEXTCH: if (sel_ch != nch_m1) begin
                sel_ch <= 1'b1;
                qst    <= Q_CHK;
            end else begin
                sel_ch     <= 1'b0;
                ster_start <= 1'b1;
                qst        <= Q_STEREO;
            end

            Q_STEREO: if (ster_done) begin
                if (ster_ist_active) istereo_frames <= istereo_frames + 1'b1;
                ro_start <= 1'b1;
                qst      <= Q_REORD;
            end

            Q_REORD: if (ro_done) begin aa_start <= 1'b1; qst <= Q_AA;    end
            Q_AA:    if (aa_done) begin im_start <= 1'b1; qst <= Q_IMDCT; end
            Q_IMDCT: if (im_done) begin syn_start <= 1'b1; qst <= Q_SYNTH; end

            // Filterbank for this channel, straight off the subband buffer.
            Q_SYNTH: if (syn_done) qst <= Q_NEXTPCH;

            Q_NEXTPCH: if (sel_ch != nch_m1) begin
                sel_ch   <= 1'b1;
                ro_start <= 1'b1;
                qst      <= Q_REORD;
            end else begin
                qst <= Q_GRDONE;
            end

            Q_GRDONE: begin
                sb_valid <= 1'b1;
                sb_gr    <= sel_gr;
                qst      <= Q_SBACK;
            end

            Q_SBACK: if (sb_ack) begin
                pcm_valid <= 1'b1;
                qst       <= Q_PCM;
            end

            Q_PCM: if (pcm_ack) qst <= Q_NEXTGR;

            Q_NEXTGR: begin
                if (!sel_gr) begin
                    sel_gr <= 1'b1;
                    sel_ch <= 1'b0;
                    qst    <= Q_CHK;
                end else begin
                    frame_ack <= 1'b1;     // release the framer
                    qst       <= Q_IDLE;
                end
            end

            Q_DROP: begin frame_ack <= 1'b1; qst <= Q_IDLE; end

            default: qst <= Q_IDLE;
            endcase
        end
    end

endmodule
