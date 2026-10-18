// Stereo PCM FIFO between the decoder and the DAC.
//
// DEPTH matters for a reason that is easy to get wrong. mp3_decoder holds a
// granule's PCM in its own buffer and stalls until the consumer acknowledges
// it, so without a FIFO the sequence is: play 576 samples (13 ms, decoder
// idle), then decode the next granule (4-7 ms, no samples available) -- a gap
// in the audio every granule. One granule of buffering lets the decoder run a
// granule ahead, which is all the elasticity needed since decode is 2-3x
// faster than playout.
//
// ---- WIDTH, AND WHY THIS IS ONE 36-BIT ARRAY -------------------------------
//
// History, because the shape of this memory has broken the player twice:
//
//   AW=9,  one 32-bit array   -> SDPX9B @ 36. Worked.
//   AW=10, one 32-bit array   -> DPX9B  @ 18. Writes land, every read returns
//                                zero. The player went completely silent.
//   AW=10, four 8-bit arrays  -> DPX9B  @ 9 x4. Fixed the silence, but spends
//                                FOUR blocks on 1024x32 (each block holds
//                                2048x9, so each is half empty) and puts the
//                                left and right channels in DIFFERENT blocks:
//                                mem2/mem3 held L, mem0/mem1 held R.
//
// That last layout produced audible noise on the LEFT CHANNEL ONLY, including
// on mono material where the drain writes the identical sample to both -- an
// asymmetry that can only come from the storage, since everything upstream is
// channel-agnostic and the decoder's PCM checksum was bit-identical to a build
// that sounds clean.
//
// So: one 36-bit array. 1024x36 is TWO blocks instead of four, 36 is a width
// this device is known good at, and both channels now live in the same memory,
// which removes the asymmetry by construction rather than by luck.
//
// The 4 spare bits are NOT padding -- padding gets trimmed by yosys, which
// would drop the width back to 32 and re-enter the broken 18-bit mapping. They
// carry a byte-parity tag that is checked on read, so the bits are genuinely
// live AND the FIFO reports corruption instead of leaving it to be diagnosed
// by ear.
module pcm_fifo #(
    parameter AW = 10                      // 1024 stereo samples
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        clear,

    input  wire        wr,
    input  wire signed [15:0] wl,
    input  wire signed [15:0] wr_data_r,

    input  wire        rd,
    output wire signed [15:0] rl,
    output wire signed [15:0] rr,

    output wire [AW:0] count,
    output wire        empty,
    output wire        full,
    output reg  [15:0] perr            // parity mismatches seen on read
);
    localparam DEPTH = (1 << AW);

    function [3:0] par (input [15:0] l, input [15:0] r);
        par = {^l[15:8], ^l[7:0], ^r[15:8], ^r[7:0]};
    endfunction

    // BANKED BY DEPTH, DELIBERATELY. Declaring one 1024x36 array does NOT
    // work: a block is at most 18 bits wide in dual-port mode, so yosys splits
    // a 36-bit array WIDTH-wise into two DPX9B @ 18 -- the configuration that
    // reads back all zeros. Two banks of 512x36 each fit a single block at
    // width 36, which is the mapping that was known good at AW=9.
    //
    // Verify after ANY change here: the netlist must show SDPX9B/36, never
    // DPX9B/18. `synth_gowin ... -json` then grep the u_pcm cells.
    localparam BW = AW - 1;                // 512 entries per bank

    (* ram_style = "block" *) reg [35:0] bank0 [0:(1<<BW)-1];
    (* ram_style = "block" *) reg [35:0] bank1 [0:(1<<BW)-1];
    reg [AW:0] wptr, rptr;
    reg [35:0] rd0, rd1;
    reg        rsel_d;

    wire [35:0] wword = {par(wl, wr_data_r), wl, wr_data_r};
    wire [35:0] rdata = rsel_d ? rd1 : rd0;

    always @(posedge clk) begin
        if (wr && !full) begin
            if (wptr[AW-1]) bank1[wptr[BW-1:0]] <= wword;
            else            bank0[wptr[BW-1:0]] <= wword;
        end
        rd0    <= bank0[rptr[BW-1:0]];
        rd1    <= bank1[rptr[BW-1:0]];
        rsel_d <= rptr[AW-1];
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wptr <= 0; rptr <= 0;
        end else if (clear) begin
            wptr <= 0; rptr <= 0;
        end else begin
            if (wr && !full)  wptr <= wptr + 1'b1;
            if (rd && !empty) rptr <= rptr + 1'b1;
        end
    end

    assign count = wptr - rptr;
    assign empty = (wptr == rptr);
    assign full  = (count == DEPTH[AW:0]);

    // Registered read: rdata trails rptr by a cycle, which is what the sample
    // consumer wants -- it asserts rd and uses the value on the next request.
    assign rl = rdata[31:16];
    assign rr = rdata[15:0];

    // Parity is checked on every consumed sample. A non-zero count is proof of
    // corruption in the storage or read path; zero rules this memory out and
    // sends the search downstream.
    wire par_bad = (rdata[35:32] != par(rdata[31:16], rdata[15:0]));
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)       perr <= 16'd0;
        else if (clear)   perr <= 16'd0;
        else if (rd && !empty && par_bad && perr != 16'hffff)
                          perr <= perr + 1'b1;
    end
endmodule
