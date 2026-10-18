// Optional stereo PCM16 sample buffer for a memory-first playback path.
//
// One entry is {left,right} = 32 bits.  The interface is ready/valid on both
// sides, so this can sit directly after tf_mp3_pcm_decoder or
// tf_wav_pcm_decoder.  The RAM read is synchronous: a queued pair is held
// stable while out_valid is high and out_ready is low.
module tf_pcm_bram_fifo #(
    parameter integer AW = 10                 // 1024 stereo sample pairs
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               clear,
    input  wire               in_valid,
    output wire               in_ready,
    input  wire signed [15:0] in_left,
    input  wire signed [15:0] in_right,
    output wire               out_valid,
    input  wire               out_ready,
    output wire signed [15:0] out_left,
    output wire signed [15:0] out_right,
    output wire [AW:0]        count,
    output reg                overflow
);
    localparam integer DEPTH = (1 << AW);

    (* ram_style = "block" *) reg [31:0] mem [0:DEPTH-1];
    reg [AW:0] wptr, rptr;
    reg [AW:0] count_r;
    reg [31:0] read_word;
    reg        read_pending;
    reg        out_valid_r;

    wire push = in_valid && in_ready;
    wire pop  = out_valid_r && out_ready;

    assign in_ready  = (count_r != DEPTH);
    assign out_valid = out_valid_r;
    assign out_left  = $signed(read_word[31:16]);
    assign out_right = $signed(read_word[15:0]);
    assign count     = count_r;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wptr        <= 0;
            rptr        <= 0;
            count_r     <= 0;
            read_word   <= 0;
            read_pending<= 1'b0;
            out_valid_r <= 1'b0;
            overflow    <= 1'b0;
        end else if (clear) begin
            wptr        <= 0;
            rptr        <= 0;
            count_r     <= 0;
            read_word   <= 0;
            read_pending<= 1'b0;
            out_valid_r <= 1'b0;
            overflow    <= 1'b0;
        end else begin
            if (in_valid && !in_ready)
                overflow <= 1'b1;

            if (push)
                mem[wptr[AW-1:0]] <= {in_left, in_right};

            if (pop)
                out_valid_r <= 1'b0;

            if (read_pending) begin
                read_word    <= mem[rptr[AW-1:0]];
                rptr         <= rptr + 1'b1;
                read_pending <= 1'b0;
                out_valid_r  <= 1'b1;
            end else if (!out_valid_r && (count_r != 0)) begin
                // Issue a synchronous RAM read; data is captured above on the
                // following cycle.  rptr advances only when that read is
                // actually issued, not when the consumer accepts the word.
                read_pending <= 1'b1;
            end

            if (push)
                wptr <= wptr + 1'b1;

            case ({push, pop})
                2'b10: count_r <= count_r + 1'b1;
                2'b01: count_r <= count_r - 1'b1;
                default: ;
            endcase
        end
    end
endmodule
