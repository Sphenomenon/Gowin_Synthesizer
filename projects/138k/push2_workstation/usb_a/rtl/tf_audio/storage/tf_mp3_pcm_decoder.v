// MP3 byte-stream to stereo PCM16 adapter.
//
// The decoder itself is the GPL-3.0 Tang MP3 core in tang_mp3/.  This file is
// project glue: it gives that granule-oriented decoder a normal ready/valid
// byte input and a normal ready/valid PCM pair output.  A byte FIFO/SD reader
// can sit in front of it, or a memory/CPU can feed it directly.
//
// Input contract: present in_byte only on a cycle with in_valid && in_ready.
// Output contract: pcm_left/right are a stereo pair and remain stable while
// pcm_valid is high and pcm_ready is low.
module tf_mp3_pcm_decoder #(
    parameter integer PCM_FIFO_AW = 10
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              restart,

    input  wire              in_valid,
    input  wire [7:0]        in_byte,
    output wire              in_ready,

    output wire [19:0]       sample_rate_hz,
    output wire              stereo,
    output wire               pcm_valid,
    input  wire              pcm_ready,
    output wire signed [15:0] pcm_left,
    output wire signed [15:0] pcm_right,

    output wire [15:0]       frame_count,
    output wire [15:0]       resync_count,
    output wire [15:0]       skipped_frames,
    output wire [15:0]       stuck_frames,
    output wire [15:0]       pcm_fifo_parity_errors
);
    wire mp3_pcm_valid;
    wire mp3_pcm_ack;
    wire [10:0] mp3_pcm_addr;
    wire signed [15:0] mp3_pcm_data;
    wire is_mono;

    // Checkpoints are deliberately acknowledged immediately.  They are kept
    // in the underlying core for bit-exact verification, not in the runtime
    // audio path.
    wire spec_valid, spec_gr, spec_ch, sb_valid, sb_gr;
    wire signed [31:0] spec_data, sb_data;

    mp3_decoder u_decoder (
        .clk(clk), .rst_n(rst_n), .restart(restart),
        .inen(in_valid), .inbyte(in_byte), .in_ready(in_ready),
        .samplerate_hz(sample_rate_hz), .is_mono(is_mono),
        .spec_valid(spec_valid), .spec_gr(spec_gr), .spec_ch(spec_ch),
        .spec_ack(1'b1), .spec_addr(11'd0), .spec_data(spec_data),
        .sb_valid(sb_valid), .sb_gr(sb_gr), .sb_ack(1'b1),
        .sb_addr(11'd0), .sb_data(sb_data),
        .pcm_valid(mp3_pcm_valid), .pcm_ack(mp3_pcm_ack),
        .pcm_addr(mp3_pcm_addr), .pcm_data(mp3_pcm_data),
        .frame_count(frame_count), .resync_count(resync_count),
        .skipped_frames(skipped_frames), .istereo_frames(),
        .stuck_frames(stuck_frames)
    );

    wire fifo_wr;
    wire signed [15:0] fifo_wl, fifo_wr_data;
    wire fifo_full, fifo_empty;
    wire signed [15:0] fifo_rl, fifo_rr;
    wire [PCM_FIFO_AW:0] fifo_count;

    pcm_drain u_drain (
        .clk(clk), .rst_n(rst_n), .clear(restart), .is_mono(is_mono),
        .pcm_valid(mp3_pcm_valid), .pcm_ack(mp3_pcm_ack),
        .pcm_addr(mp3_pcm_addr), .pcm_data(mp3_pcm_data),
        .fifo_wr(fifo_wr), .fifo_l(fifo_wl), .fifo_r(fifo_wr_data),
        .fifo_full(fifo_full)
    );

    reg fifo_rd;
    reg fifo_rd_pending;
    reg pcm_valid_r;
    reg signed [15:0] pcm_left_r, pcm_right_r;

    // pcm_fifo is a synchronous-read memory: rd is issued first, and the
    // returned pair is captured on the following clock.  The extra register is
    // what makes the outer interface a conventional hold-until-accepted bus.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fifo_rd         <= 1'b0;
            fifo_rd_pending <= 1'b0;
            pcm_valid_r     <= 1'b0;
            pcm_left_r      <= 16'sd0;
            pcm_right_r     <= 16'sd0;
        end else if (restart) begin
            fifo_rd         <= 1'b0;
            fifo_rd_pending <= 1'b0;
            pcm_valid_r     <= 1'b0;
        end else begin
            fifo_rd <= 1'b0;

            if (pcm_valid_r && pcm_ready)
                pcm_valid_r <= 1'b0;

            if (fifo_rd_pending) begin
                pcm_left_r      <= fifo_rl;
                pcm_right_r     <= fifo_rr;
                pcm_valid_r     <= 1'b1;
                fifo_rd_pending <= 1'b0;
            end else if (!pcm_valid_r && !fifo_empty) begin
                fifo_rd         <= 1'b1;
                fifo_rd_pending <= 1'b1;
            end
        end
    end

    pcm_fifo #(.AW(PCM_FIFO_AW)) u_pcm_fifo (
        .clk(clk), .rst_n(rst_n), .clear(restart),
        .wr(fifo_wr), .wl(fifo_wl), .wr_data_r(fifo_wr_data),
        .rd(fifo_rd), .rl(fifo_rl), .rr(fifo_rr),
        .count(fifo_count), .empty(fifo_empty), .full(fifo_full),
        .perr(pcm_fifo_parity_errors)
    );

    assign stereo   = ~is_mono;
    assign pcm_valid = pcm_valid_r;
    assign pcm_left = pcm_left_r;
    assign pcm_right = pcm_right_r;
endmodule
