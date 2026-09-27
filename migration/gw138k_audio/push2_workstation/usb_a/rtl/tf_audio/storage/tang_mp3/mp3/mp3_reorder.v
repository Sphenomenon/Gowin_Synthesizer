// Short-block reorder: window-major -> frequency-major, in place on mp3_spectra.
//
// A short granule codes each scalefactor band as three consecutive runs, one
// per window. The IMDCT wants them interleaved:
//
//   in :  w0[0..len-1]  w1[0..len-1]  w2[0..len-1]
//   out:  w0[0] w1[0] w2[0]  w0[1] w1[1] w2[1]  ...
//
// Long blocks are untouched -- the reference only calls this when
// n_short_sfb != 0.
//
// MIXED BLOCKS start at coefficient 36: the first two bands stay long. For
// MPEG-1 that offset is always 2*18, never 4*18 -- the reference's
// `<< (HDR_GET_MY_SAMPLE_RATE == 2)` can only fire on MPEG-2/2.5, because for
// MPEG-1 that macro yields 6..8. Getting this wrong would misplace every short
// coefficient on 32 kHz mixed streams, so it is spelled out rather than copied.
//
// The permutation cannot be done in place, so it lands in a scratch buffer and
// is copied back -- the same shape as the reference's scratch + memcpy.
module mp3_reorder (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,

    input  wire        ch,
    input  wire [1:0]  samplerate_idx,
    input  wire        window_switching,
    input  wire [1:0]  block_type,
    input  wire        mixed_block,

    // shared mp3_sfbtab port
    output reg  [8:0]  sfb_addr,
    input  wire [7:0]  sfb_long_q,
    input  wire [7:0]  sfb_short_q,
    input  wire [7:0]  sfb_mixed_q,

    output reg         done,
    // mp3_spectra ports
    output reg  [10:0] rd_addr,
    input  wire signed [31:0] rd_data,
    output reg         wr_en,
    output reg  [10:0] wr_addr,
    output reg  signed [31:0] wr_data
);
    wire is_short = window_switching && (block_type == 2'd2);

    // Scratch: one channel's worth. Synchronous read, like every other buffer
    // in this design.
    // Byte-split. As one 32-bit array this maps to DPX9B at BIT_WIDTH=18 --
    // CHECKED, and that is the configuration that reads back zeros on this
    // device. Four byte-wide arrays give BIT_WIDTH=9. Costs 4 BSRAM instead of
    // 2, which is why huff_tabs was trimmed to pay for it.
    reg [7:0] scr0 [0:575];
    reg [7:0] scr1 [0:575];
    reg [7:0] scr2 [0:575];
    reg [7:0] scr3 [0:575];
    reg  [9:0] scr_waddr, scr_raddr;
    reg signed [31:0] scr_wdata, scr_rdata;
    reg        scr_we;
    always @(posedge clk) begin
        if (scr_we) begin
            scr0[scr_waddr] <= scr_wdata[7:0];
            scr1[scr_waddr] <= scr_wdata[15:8];
            scr2[scr_waddr] <= scr_wdata[23:16];
            scr3[scr_waddr] <= scr_wdata[31:24];
        end
        scr_rdata <= {scr3[scr_raddr], scr2[scr_raddr],
                      scr1[scr_raddr], scr0[scr_raddr]};
    end

    // Short scalefactor-band widths. Band index counts from the first SHORT
    // band, which is table entry 8 for mixed blocks and 0 for pure short.

    wire [7:0] len_w    = mixed_block ? sfb_mixed_q : sfb_short_q;
    wire [8:0] tab_base = ({7'd0, samplerate_idx} + 9'd5) * 9'd40
                          + (mixed_block ? 9'd8 : 9'd0);
    wire [9:0] coef_base = mixed_block ? 10'd36 : 10'd0;

    localparam [3:0] S_IDLE=0, S_BAND=1, S_BANDW=2, S_CHK=3,
                     S_RD=4, S_RDW=5, S_CAP=6, S_NEXT=7,
                     S_CP_RD=8, S_CP_RDW=9, S_CP_WR=10, S_DONE=11;

    reg [3:0] st;
    reg [7:0] len;
    reg [9:0] src;        // start of the current band's window 0
    reg [9:0] dst;        // scratch write cursor
    reg [7:0] i;          // position within a window
    reg [1:0] w;          // which window (0..2)
    reg [9:0] cp;         // copy-back cursor
    reg [9:0] cp_end;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; done <= 0; wr_en <= 0; rd_addr <= 0;
            wr_addr <= 0; wr_data <= 0; scr_we <= 0; scr_waddr <= 0;
            scr_wdata <= 0; scr_raddr <= 0; sfb_addr <= 0;
            len <= 0; src <= 0; dst <= 0; i <= 0; w <= 0; cp <= 0;
            cp_end <= 0;
        end else begin
            done   <= 1'b0;
            wr_en  <= 1'b0;
            scr_we <= 1'b0;

            case (st)
            S_IDLE: if (start) begin
                if (!is_short) begin
                    st <= S_DONE;              // long blocks need no reorder
                end else begin
                    src      <= coef_base;
                    dst      <= coef_base;
                    sfb_addr <= tab_base;
                    st       <= S_BAND;
                end
            end

            // sync_rom latency: the address was registered last edge, the ROM
            // samples it this edge, data is readable the edge after.
            S_BAND:  st <= S_BANDW;
            S_BANDW: st <= S_CHK;

            S_CHK: begin
                if (len_w == 8'd0) begin
                    cp     <= coef_base;
                    cp_end <= dst;
                    st     <= (dst == coef_base) ? S_DONE : S_CP_RD;
                end else begin
                    len <= len_w;
                    i   <= 8'd0;
                    w   <= 2'd0;
                    st  <= S_RD;
                end
            end

            // scratch[dst++] = spectra[ch][src + i + w*len], w = 0,1,2
            S_RD: begin
                rd_addr <= {ch, src + {2'd0, i} + ({8'd0, w} * {2'd0, len})};
                st      <= S_RDW;
            end
            S_RDW: st <= S_CAP;
            S_CAP: begin
                scr_we    <= 1'b1;
                scr_waddr <= dst;
                scr_wdata <= rd_data;
                dst       <= dst + 1'b1;
                if (w == 2'd2) begin
                    w <= 2'd0;
                    if (i + 8'd1 == len) st <= S_NEXT;
                    else begin i <= i + 8'd1; st <= S_RD; end
                end else begin
                    w  <= w + 2'd1;
                    st <= S_RD;
                end
            end

            S_NEXT: begin
                src      <= src + ({2'd0, len} * 10'd3);
                sfb_addr <= sfb_addr + 9'd3;      // widths repeat per window
                st       <= S_BAND;
            end

            // copy scratch back over the short region
            S_CP_RD: begin
                scr_raddr <= cp;
                st        <= S_CP_RDW;
            end
            S_CP_RDW: st <= S_CP_WR;
            S_CP_WR: begin
                wr_en   <= 1'b1;
                wr_addr <= {ch, cp};
                wr_data <= scr_rdata;
                if (cp + 10'd1 == cp_end) st <= S_DONE;
                else begin cp <= cp + 10'd1; st <= S_CP_RD; end
            end

            S_DONE: begin done <= 1'b1; st <= S_IDLE; end
            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
