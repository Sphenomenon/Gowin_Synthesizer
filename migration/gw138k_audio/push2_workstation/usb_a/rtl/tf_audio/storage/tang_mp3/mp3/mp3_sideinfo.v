// MPEG-1 Layer III side-info parser.
//
// Layout (bits), stereo = 32 bytes = 256, mono = 17 bytes = 136:
//   main_data_begin      9
//   private_bits         3 (stereo) / 5 (mono)
//   scfsi[ch][0..3]      4 per channel
//   then for gr in 0..1, for ch in 0..nch-1  -- 59 bits each:
//     part2_3_length    12
//     big_values         9
//     global_gain        8
//     scalefac_compress  4
//     window_switching   1
//       if 1: block_type 2, mixed 1, table_select[2] 5+5, subblock_gain[3] 3+3+3
//       if 0: table_select[3] 5+5+5, region0_count 4, region1_count 3
//     preflag            1
//     scalefac_scale     1
//     count1table_select 1
// Check: 9+3+8 + 2*2*59 = 256 stereo, 9+5+4 + 2*1*59 = 136 mono.
//
// The block is BUFFERED first, then parsed bit-serially.
//
// A first attempt parsed on the fly from a 32-bit window, which cannot work:
// the block is up to 256 bits and the byte strobes arrive from the SD FIFO with
// no guaranteed gaps, so there is nowhere to drain the window to. Buffering the
// whole block costs 256 flops (nothing here) and removes the coupling entirely.
//
// Extraction shifts ONE bit per cycle rather than by `need`. A 256-bit barrel
// shifter would be thousands of LUTs; a 1-bit shift is free, and the whole
// block costs ~256 cycles against the ~1.41 M available per frame.
//
// Fields land in flat arrays indexed by {gr, ch}; sel_gr/sel_ch pick which set
// appears on the read port, so a consumer can revisit any granule.
module mp3_sideinfo (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        is_mono,
    input  wire        side_en,        // byte strobe from mp3_bitstream
    input  wire [7:0]  side_byte,
    input  wire        side_done,      // last byte consumed -> start parsing
    output reg         si_valid,       // pulse: all fields parsed

    output reg  [8:0]  main_data_begin,

    // read port
    input  wire        sel_gr,
    input  wire        sel_ch,
    output wire [11:0] part2_3_length,
    output wire [8:0]  big_values,
    output wire [7:0]  global_gain,
    output wire [3:0]  scalefac_compress,
    output wire        window_switching,
    output wire [1:0]  block_type,
    output wire        mixed_block,
    output wire [14:0] table_select,   // {t2,t1,t0}, 5 bits each
    output wire [8:0]  subblock_gain,  // {g2,g1,g0}, 3 bits each
    output wire [7:0]  region0_count,
    output wire [7:0]  region1_count,
    output wire        preflag,
    output wire        scalefac_scale,
    output wire        count1_table,
    output wire [3:0]  scfsi_ch
);
    reg [255:0] sbuf;

    // ---- storage -----------------------------------------------------------
    reg [11:0] r_part23  [0:3];
    reg [8:0]  r_bigval  [0:3];
    reg [7:0]  r_ggain   [0:3];
    reg [3:0]  r_sfcomp  [0:3];
    reg        r_winsw   [0:3];
    reg [1:0]  r_btype   [0:3];
    reg        r_mixed   [0:3];
    reg [14:0] r_tsel    [0:3];
    reg [8:0]  r_sbgain  [0:3];
    reg [7:0]  r_reg0    [0:3];
    reg [7:0]  r_reg1    [0:3];
    reg        r_pre     [0:3];
    reg        r_sfscale [0:3];
    reg        r_cnt1    [0:3];
    reg [3:0]  r_scfsi   [0:1];

    wire [1:0] sel = {sel_gr, sel_ch};
    assign part2_3_length    = r_part23 [sel];
    assign big_values        = r_bigval [sel];
    assign global_gain       = r_ggain  [sel];
    assign scalefac_compress = r_sfcomp [sel];
    assign window_switching  = r_winsw  [sel];
    assign block_type        = r_btype  [sel];
    assign mixed_block       = r_mixed  [sel];
    assign table_select      = r_tsel   [sel];
    assign subblock_gain     = r_sbgain [sel];
    assign region0_count     = r_reg0   [sel];
    assign region1_count     = r_reg1   [sel];
    assign preflag           = r_pre    [sel];
    assign scalefac_scale    = r_sfscale[sel];
    assign count1_table      = r_cnt1   [sel];
    assign scfsi_ch          = r_scfsi  [sel_ch];

    // ---- parser ------------------------------------------------------------
    // LOAD (latch this field's width) -> SHIFT (one bit per cycle) ->
    // COMMIT (store it, choose the next field). The extra LOAD cycle exists so
    // that `need` is always read for the step that is CURRENT, which keeps cnt
    // single-driver; ~30 spare cycles per frame is not worth avoiding it.
    localparam [1:0] P_IDLE = 2'd0, P_HDR = 2'd1, P_GR = 2'd2;
    localparam [1:0] S_IDLE = 2'd0, S_LOAD = 2'd1, S_SHIFT = 2'd2, S_COMMIT = 2'd3;

    reg [1:0]  phase, state;
    reg [4:0]  step;
    reg        gr, ch;
    reg [1:0]  gc;
    reg [2:0]  scfsi_i;
    reg [3:0]  cnt;
    reg [11:0] acc;

    reg [3:0] need;
    always @(*) begin
        case (phase)
        P_HDR: case (step)
            5'd0:    need = 4'd9;                    // main_data_begin
            5'd1:    need = is_mono ? 4'd5 : 4'd3;   // private_bits
            default: need = 4'd4;                    // scfsi, per channel
        endcase
        P_GR: case (step)
            5'd0:  need = 4'd12;  5'd1:  need = 4'd9;   5'd2:  need = 4'd8;
            5'd3:  need = 4'd4;   5'd4:  need = 4'd1;   5'd5:  need = 4'd2;
            5'd6:  need = 4'd1;   5'd7:  need = 4'd5;   5'd8:  need = 4'd5;
            5'd9:  need = 4'd3;   5'd10: need = 4'd3;   5'd11: need = 4'd3;
            5'd12: need = 4'd5;   5'd13: need = 4'd5;   5'd14: need = 4'd5;
            5'd15: need = 4'd4;   5'd16: need = 4'd3;
            default: need = 4'd1;                    // preflag/sfscale/count1
        endcase
        default: need = 4'd1;
        endcase
    end

    // Mono blocks are 17 bytes so they occupy the LOW 136 bits of sbuf; stereo
    // fills all 256. Extraction always takes the top bit of the used region.
    wire top_bit = is_mono ? sbuf[135] : sbuf[255];
    wire [1:0] nch_m1 = is_mono ? 2'd0 : 2'd1;
    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sbuf <= 0; phase <= P_IDLE; state <= S_IDLE; step <= 0;
            cnt <= 0; acc <= 0; gr <= 0; ch <= 0; gc <= 0; scfsi_i <= 0;
            main_data_begin <= 0; si_valid <= 1'b0;
            for (i = 0; i < 4; i = i + 1) begin
                r_part23[i]<=0; r_bigval[i]<=0; r_ggain[i]<=0; r_sfcomp[i]<=0;
                r_winsw[i]<=0;  r_btype[i]<=0;  r_mixed[i]<=0; r_tsel[i]<=0;
                r_sbgain[i]<=0; r_reg0[i]<=0;   r_reg1[i]<=0;  r_pre[i]<=0;
                r_sfscale[i]<=0; r_cnt1[i]<=0;
            end
            r_scfsi[0] <= 0; r_scfsi[1] <= 0;
        end else begin
            si_valid <= 1'b0;

            if (side_en)
                sbuf <= {sbuf[247:0], side_byte};

            if (side_done) begin
                phase   <= P_HDR;  step <= 5'd0;  scfsi_i <= 3'd0;
                gr <= 1'b0; ch <= 1'b0; gc <= 2'd0;
                state   <= S_LOAD;
            end else case (state)

            S_LOAD: begin
                cnt   <= need;
                acc   <= 12'd0;
                state <= S_SHIFT;
            end

            S_SHIFT: begin
                acc  <= {acc[10:0], top_bit};
                sbuf <= sbuf << 1;
                cnt  <= cnt - 4'd1;
                if (cnt == 4'd1) state <= S_COMMIT;
            end

            S_COMMIT: begin
                state <= S_LOAD;
                case (phase)
                P_HDR: case (step)
                    5'd0: begin main_data_begin <= acc[8:0]; step <= 5'd1; end
                    5'd1: begin step <= 5'd2; scfsi_i <= 3'd0; end
                    default: begin
                        r_scfsi[scfsi_i[0]] <= acc[3:0];
                        if (scfsi_i[1:0] >= nch_m1) begin
                            phase <= P_GR; step <= 5'd0;
                        end else begin
                            scfsi_i <= scfsi_i + 3'd1;
                        end
                    end
                endcase

                P_GR: case (step)
                    5'd0: begin r_part23[gc] <= acc[11:0]; step <= 5'd1; end
                    5'd1: begin r_bigval[gc] <= acc[8:0];  step <= 5'd2; end
                    5'd2: begin r_ggain[gc]  <= acc[7:0];  step <= 5'd3; end
                    5'd3: begin r_sfcomp[gc] <= acc[3:0];  step <= 5'd4; end
                    5'd4: begin
                              r_winsw[gc] <= acc[0];
                              step <= acc[0] ? 5'd5 : 5'd12;
                              if (acc[0]) begin
                                  // short/start/stop: no third Huffman table,
                                  // and the region counts are DERIVED (set at
                                  // step 6 once mixed_block_flag is known)
                                  r_tsel[gc][14:10] <= 5'd0;
                              end else begin
                                  r_btype[gc] <= 2'd0; r_mixed[gc] <= 1'b0;
                                  r_sbgain[gc] <= 9'd0;
                              end
                          end
                    5'd5:  begin r_btype[gc]       <= acc[1:0]; step <= 5'd6;  end
                    5'd6:  begin
                               r_mixed[gc] <= acc[0];
                               step <= 5'd7;
                               // Match the reference exactly: region_count[0]
                               // is 8 for a pure short block and 7 otherwise;
                               // region_count[1] is the 255 "no region 2"
                               // sentinel. These are NOT bitstream fields when
                               // window switching is on -- reading them as if
                               // they were would desync the whole block.
                               r_reg0[gc] <= (r_btype[gc] == 2'd2 && !acc[0]) ? 8'd8 : 8'd7;
                               r_reg1[gc] <= 8'd255;
                           end
                    5'd7:  begin r_tsel[gc][4:0]   <= acc[4:0]; step <= 5'd8;  end
                    5'd8:  begin r_tsel[gc][9:5]   <= acc[4:0]; step <= 5'd9;  end
                    5'd9:  begin r_sbgain[gc][2:0] <= acc[2:0]; step <= 5'd10; end
                    5'd10: begin r_sbgain[gc][5:3] <= acc[2:0]; step <= 5'd11; end
                    5'd11: begin r_sbgain[gc][8:6] <= acc[2:0]; step <= 5'd17; end
                    5'd12: begin r_tsel[gc][4:0]   <= acc[4:0]; step <= 5'd13; end
                    5'd13: begin r_tsel[gc][9:5]   <= acc[4:0]; step <= 5'd14; end
                    5'd14: begin r_tsel[gc][14:10] <= acc[4:0]; step <= 5'd15; end
                    5'd15: begin r_reg0[gc]        <= {4'b0, acc[3:0]}; step <= 5'd16; end
                    5'd16: begin r_reg1[gc]        <= {5'b0, acc[2:0]}; step <= 5'd17; end
                    5'd17: begin r_pre[gc]     <= acc[0]; step <= 5'd18; end
                    5'd18: begin r_sfscale[gc] <= acc[0]; step <= 5'd19; end
                    5'd19: begin
                              r_cnt1[gc] <= acc[0];
                              step <= 5'd0;
                              if (is_mono ? gr : (gr & ch)) begin
                                  phase    <= P_IDLE;
                                  state    <= S_IDLE;
                                  si_valid <= 1'b1;
                              end else if (is_mono) begin
                                  gr <= 1'b1; gc <= 2'd2;
                              end else begin
                                  {gr, ch} <= gc + 2'd1;
                                  gc       <= gc + 2'd1;
                              end
                          end
                    default: step <= 5'd0;
                endcase
                default: state <= S_IDLE;
                endcase
            end

            default: ;   // S_IDLE
            endcase
        end
    end
endmodule
