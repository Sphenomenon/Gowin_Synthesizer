// MPEG-1 Layer III scalefactor decoder.
//
// Reads the per-band scalefactors at the front of each granule's main data and
// applies the two adjustments the spec folds in here:
//
//   short blocks   -> iscf[n_long + i] += subblock_gain[i mod 3] << (3 - scf_shift)
//   long + preflag -> iscf[11 + i]     += g_preamp[i]   (i = 0..9)
//
// Output is the INTEGER scalefactor per band. Turning that into a gain is
// requantization's job: the exponent also carries global_gain, the MS-stereo
// correction and scalefac_scale, so assembling it once there beats twice.
//
// SCFSI lets granule 1 reuse granule 0's scalefactors per partition, so the RAW
// values persist per channel across granules. `sfraw` is that memory, `iscf` is
// the adjusted copy for the granule being decoded. (In the reference these are
// `ist_pos` and `iscf`; for MPEG-1 `ist_pos[k]` is just a copy of the raw value
// -- the -1 sentinel only arises for MPEG-2 intensity stereo, out of scope.)
//
// Both arrays are read SYNCHRONOUSLY. An async read here would be the same trap
// that cost ~9.7k LUT4 in the vendor SD core, and the scfsi copy path is
// exactly where it would sneak in.
module mp3_scalefac (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        start,             // pulse: decode one granule/channel
    input  wire        ch,                // selects the persistent sfraw half
    input  wire        gr1,               // granule 1 -> scfsi may apply
    input  wire [3:0]  scalefac_compress,
    input  wire        window_switching,
    input  wire [1:0]  block_type,
    input  wire        mixed_block,
    input  wire [3:0]  scfsi,
    input  wire        preflag,
    input  wire [8:0]  subblock_gain,     // {g2,g1,g0}
    input  wire        scalefac_scale,

    // reservoir bit port
    input  wire        res_ready,
    input  wire [23:0] res_peek,
    output reg         res_skip,
    output reg  [4:0]  res_skip_n,

    output reg         done,
    output reg  [5:0]  n_bands,           // valid entries in iscf

    // read port (registered)
    input  wire [5:0]  sf_addr,
    output reg  [7:0]  sf_data,

    // ist_pos read port: channel 1's RAW scalefactors, which for MPEG-1 are the
    // intensity-stereo positions. Raw, not adjusted -- subblock_gain and preamp
    // belong to requantization and must not leak into the pan lookup.
    input  wire [5:0]  ist_band,
    output reg  [7:0]  ist_data
);
    // ---- tables ------------------------------------------------------------
    reg  [6:0] part_addr;
    wire [4:0] part_rom;
    sync_rom #(.AW(7), .DW(5), .INIT("src/storage/tang_mp3/mp3/tables/scf_partitions.memh")) u_part (
        .clk(clk), .addr(part_addr), .data(part_rom));

    wire [4:0] scfc_rom;
    sync_rom #(.AW(4), .DW(5), .INIT("src/storage/tang_mp3/mp3/tables/scfc_decode.memh")) u_scfc (
        .clk(clk), .addr(scalefac_compress), .data(scfc_rom));

    reg  [3:0] pre_addr;
    wire [2:0] pre_rom;
    sync_rom #(.AW(4), .DW(3), .INIT("src/storage/tang_mp3/mp3/tables/preamp.memh")) u_pre (
        .clk(clk), .addr(pre_addr), .data(pre_rom));

    localparam [4:0] S_IDLE=4'd0, S_SETUP=4'd1, S_PART=4'd2, S_READ=4'd3,
                     S_COPY0=4'd4, S_COPY1=4'd5, S_ADJPRE=4'd6, S_ADJSB=4'd7,
                     S_ADJSBW=4'd12,
                     S_NEXTP=4'd8, S_ZPAD=4'd9, S_DONE=4'd10, S_RDWAIT=4'd11;
    reg [4:0] st;

    // ---- storage -----------------------------------------------------------
    // ram_style=block: tiny arrays default to distributed RAM16SDP4, whose
    // siting rules the placer cannot satisfy once the m7 LCD adds 21 I/O and
    // the UI logic. Block RAM sits in its own columns and does not compete.
    (* ram_style = "block" *)
    reg [7:0] sfraw [0:79];        // 2 channels x 40 bands, persists for scfsi
    // ram_style=block: tiny arrays default to distributed RAM16SDP4, whose
    // siting rules the placer cannot satisfy once the m7 LCD adds 21 I/O and
    // the UI logic. Block RAM sits in its own columns and does not compete.
    (* ram_style = "block" *)
    reg [7:0] iscf  [0:39];

    reg [6:0] raw_addr;
    // ONE read port, address muxed. Two independent read ports turned this into
    // 80 x 8 flops behind two 80:1 muxes; with iscf the same, mp3_scalefac was
    // 4948 LUT slots, twice any other stage. The consumers never overlap:
    // `ist_data` is read by mp3_stereo and `sf_data` by mp3_requant, both only
    // while this module is idle, so idleness selects between internal and
    // external addressing and the array infers as a RAM instead.
    wire       sf_idle   = (st == S_IDLE);
    wire [6:0] sfraw_ra  = sf_idle ? (7'd40 + {1'b0, ist_band}) : raw_addr;
    reg  [7:0] sfraw_q;
    always @(posedge clk) sfraw_q <= sfraw[sfraw_ra];

    reg [5:0] iscf_addr;
    wire [5:0] iscf_ra = sf_idle ? sf_addr : iscf_addr;
    reg [7:0] iscf_q;
    always @(posedge clk) iscf_q <= iscf[iscf_ra];

    // Both external read ports observe the same registered word; which one is
    // meaningful is decided by the caller's own sequencing.
    always @(*) sf_data  = iscf_q;
    always @(*) ist_data = sfraw_q;

    // ONE write port each, sources muxed. iscf was written from four places
    // (read, scfsi copy, subblock gain, preamp, zero pad), which is what
    // prevented RAM inference.
    reg        iscf_we;
    reg  [5:0] iscf_wa;
    reg  [7:0] iscf_wd;
    reg        sfraw_we;
    reg  [6:0] sfraw_wa;
    reg  [7:0] sfraw_wd;
    always @(posedge clk) begin
        if (iscf_we)  iscf[iscf_wa]   <= iscf_wd;
        if (sfraw_we) sfraw[sfraw_wa] <= sfraw_wd;
    end

    // ---- block geometry ----------------------------------------------------
    wire       is_short  = window_switching && (block_type == 2'd2);
    wire [1:0] part_row  = is_short ? (mixed_block ? 2'd1 : 2'd2) : 2'd0;
    wire [5:0] n_long    = is_short ? (mixed_block ? 6'd8  : 6'd0 ) : 6'd22;
    wire [5:0] n_short   = is_short ? (mixed_block ? 6'd30 : 6'd39) : 6'd0;
    wire [1:0] scf_shift = {1'b0, scalefac_scale} + 2'd1;
    wire [1:0] sh        = 2'd3 - scf_shift;

    // row * 28, written as shifts so no multiplier is inferred
    wire [6:0] part_base = {part_row, 4'd0} + {part_row, 3'd0} + {part_row, 2'd0};

    wire [2:0] slen1 = {1'b0, scfc_rom[4:2]};
    wire [2:0] slen2 = {1'b0, scfc_rom[1:0]};

    reg [2:0] slen;            // bits per scalefactor in the current partition
    reg [1:0] mod3;            // explicit band-mod-3, so no divider is inferred

    reg [2:0] sbg_sel;
    always @(*) begin
        case (mod3)
            2'd0:    sbg_sel = subblock_gain[2:0];
            2'd1:    sbg_sel = subblock_gain[5:3];
            default: sbg_sel = subblock_gain[8:6];
        endcase
    end

    // top `slen` bits of the peek window
    wire [7:0] sf_bits = (slen == 3'd0) ? 8'd0 :
                         (res_peek >> (5'd24 - {2'b0, slen})) & ((8'd1 << slen) - 8'd1);

    reg [1:0] pidx;
    reg [4:0] pcnt;
    reg [5:0] bidx;
    reg [3:0] scfsi_r;
    reg [1:0] wait_cnt;
    reg [6:0] base;
    reg [1:0] zpad;
    reg       last_of_part;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; done <= 0; res_skip <= 0; res_skip_n <= 0;
            pidx <= 0; pcnt <= 0; bidx <= 0; slen <= 0; scfsi_r <= 0;
            wait_cnt <= 0; part_addr <= 0; pre_addr <= 0; n_bands <= 0;
            base <= 0; mod3 <= 0; raw_addr <= 0; iscf_addr <= 0; zpad <= 0;
            iscf_we <= 0; iscf_wa <= 0; iscf_wd <= 0;
            sfraw_we <= 0; sfraw_wa <= 0; sfraw_wd <= 0;
            last_of_part <= 0;
        end else begin
            done     <= 1'b0;
            res_skip <= 1'b0;

            case (st)
            S_IDLE: if (start) begin
                bidx      <= 0;
                pidx      <= 0;
                base      <= ch ? 7'd40 : 7'd0;
                scfsi_r   <= gr1 ? scfsi : 4'd0;
                part_addr <= part_base;
                wait_cnt  <= 0;
                n_bands   <= n_long + n_short;
                st        <= S_SETUP;
            end

            // sync_rom is registered: give the partition/slen ROMs a cycle.
            S_SETUP: begin
                wait_cnt <= wait_cnt + 2'd1;
                if (wait_cnt == 2'd1) st <= S_PART;
            end

            S_PART: begin
                pcnt <= part_rom;
                slen <= (pidx < 2'd2) ? slen1 : slen2;
                if (part_rom == 5'd0) begin
                    zpad <= 2'd0;
                    st   <= S_ZPAD;
                end else if (scfsi_r[3]) begin
                    raw_addr <= base + bidx;
                    st       <= S_COPY0;
                end else begin
                    st <= S_READ;
                end
            end

            // slen == 0 means the whole partition is zero and costs no bits.
            //
            // res_skip is REGISTERED, so it does not reach the reservoir until
            // the next cycle and the peek window is stale until the cycle after
            // that. Re-entering S_READ immediately would re-read the same bits
            // whenever cnt happened to stay >= 24 (so `ready` never dropped) --
            // an intermittent, data-dependent duplicate that zeros hide
            // completely. S_RDWAIT makes the settle explicit.
            S_READ: if (res_ready || slen == 3'd0) begin
                if (slen != 3'd0) begin
                    res_skip   <= 1'b1;
                    res_skip_n <= {2'b0, slen};
                end
                sfraw_we <= 1'b1; sfraw_wa <= base + bidx; sfraw_wd <= sf_bits;
                iscf_we  <= 1'b1; iscf_wa  <= bidx;         iscf_wd  <= sf_bits;
                bidx <= bidx + 1'b1;
                if (pcnt == 5'd1) last_of_part <= 1'b1;
                else begin
                    last_of_part <= 1'b0;
                    pcnt         <= pcnt - 5'd1;
                end
                st <= S_RDWAIT;
            end

            S_RDWAIT: st <= last_of_part ? S_NEXTP : S_READ;

            // scfsi share: registered read, so two states per band.
            S_COPY0: st <= S_COPY1;
            S_COPY1: begin
                iscf_we <= 1'b1; iscf_wa <= bidx; iscf_wd <= sfraw_q;
                bidx <= bidx + 1'b1;
                if (pcnt == 5'd1) st <= S_NEXTP;
                else begin
                    pcnt     <= pcnt - 5'd1;
                    raw_addr <= base + bidx + 1'b1;
                    st       <= S_COPY0;
                end
            end

            S_NEXTP: begin
                pidx    <= pidx + 2'd1;
                scfsi_r <= {scfsi_r[2:0], 1'b0};
                if (pidx == 2'd3) begin
                    zpad <= 2'd0;
                    st   <= S_ZPAD;
                end else begin
                    part_addr <= part_addr + 1'b1;
                    wait_cnt  <= 0;
                    st        <= S_SETUP;
                end
            end

            // short blocks: += subblock_gain[band mod 3] << sh
            //
            // iscf is a single-ported RAM now, so the old value has to be
            // FETCHED before it can be accumulated -- two cycles, exactly like
            // the preamp ROM below. Reading it combinationally is what the
            // flop-based array allowed; carrying that assumption over left the
            // addend on a stale word and every short granule came out 2^6 low.
            S_ADJSB: begin
                if (bidx < n_short) begin
                    iscf_addr <= n_long + bidx;
                    wait_cnt  <= 2'd0;
                    st        <= S_ADJSBW;
                end else st <= S_DONE;
            end
            S_ADJSBW: begin
                wait_cnt <= wait_cnt + 2'd1;
                if (wait_cnt == 2'd1) begin
                    iscf_we <= 1'b1;
                    iscf_wa <= n_long + bidx;
                    iscf_wd <= iscf_q + ({5'b0, sbg_sel} << sh);
                    bidx    <= bidx + 1'b1;
                    mod3    <= (mod3 == 2'd2) ? 2'd0 : mod3 + 2'd1;
                    st      <= S_ADJSB;
                end
            end

            // long + preflag: += g_preamp[i] over iscf[11..20]
            //
            // sync_rom needs TWO cycles, not one: pre_addr is assigned
            // non-blocking, so the ROM only samples it at the following edge
            // and the data appears the edge after that. Reading one cycle early
            // applied g_preamp[i-1], which is invisible for bands 11..14
            // because g_preamp[0..3] are all 1 -- it first shows at band 15
            // (needs +2, got +1) and again at 17 and 20.
            S_ADJPRE: begin
                if (bidx < 6'd10) begin
                    case (wait_cnt)
                        2'd0: begin
                            pre_addr  <= bidx[3:0];
                            iscf_addr <= 6'd11 + bidx;   // same two-cycle fetch
                            wait_cnt  <= 2'd1;
                        end
                        2'd1: wait_cnt <= 2'd2;                 // ROM samples addr
                        default: begin                          // data valid
                            iscf_we <= 1'b1;
                            iscf_wa <= 6'd11 + bidx;
                            iscf_wd <= iscf_q + {5'b0, pre_rom};
                            bidx     <= bidx + 1'b1;
                            wait_cnt <= 2'd0;
                        end
                    endcase
                end else st <= S_DONE;
            end

            // The reference's L3_read_scalefactors ends with
            //   scf[0] = scf[1] = scf[2] = 0;
            // writing three zeros PAST the last partition band. Long blocks use
            // partitions 6+5+5+5 = 21 bands but n_bands is 22, so band 21 comes
            // from this fill and nothing else -- without it that band reads as x.
            S_ZPAD: begin
                iscf_we <= 1'b1; iscf_wa <= bidx + {4'b0, zpad}; iscf_wd <= 8'd0;
                if (zpad == 2'd2) begin
                    bidx <= 0; mod3 <= 0; pre_addr <= 0; wait_cnt <= 0;
                    st   <= (n_short != 0) ? S_ADJSB : (preflag ? S_ADJPRE : S_DONE);
                end else zpad <= zpad + 2'd1;
            end

            S_DONE: begin done <= 1'b1; st <= S_IDLE; end
            default: st <= S_IDLE;
            endcase
        end
    end

endmodule
