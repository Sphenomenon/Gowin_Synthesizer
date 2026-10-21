// Moves a decoded granule out of mp3_decoder's PCM buffer into the PCM FIFO.
//
// mp3_decoder announces a granule and then stalls -- and with it the framer and
// the SD reader -- until the granule is acknowledged. So this drain is what
// paces the whole decode: it copies as fast as the FIFO has room, acks, and the
// decoder immediately starts the next granule.
//
// MONO IS DUPLICATED to both outputs here rather than downstream, because the
// DAC frame always carries two samples and the decoder only fills channel 0.
module pcm_drain (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        clear,

    input  wire        is_mono,

    // mp3_decoder granule interface
    input  wire        pcm_valid,
    output reg         pcm_ack,
    output reg  [10:0] pcm_addr,
    input  wire signed [15:0] pcm_data,

    // pcm_fifo write side
    output reg         fifo_wr,
    output reg  signed [15:0] fifo_l,
    output reg  signed [15:0] fifo_r,
    input  wire        fifo_full
);
    localparam [2:0] S_IDLE=0, S_L_A=1, S_L_B=2, S_R_A=3, S_R_B=4,
                     S_WR=5, S_ACK=6;

    reg [2:0] st;
    reg [9:0] k;
    reg signed [15:0] samp_l;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; pcm_ack <= 0; pcm_addr <= 0;
            fifo_wr <= 0; fifo_l <= 0; fifo_r <= 0; k <= 0; samp_l <= 0;
        end else if (clear) begin
            st <= S_IDLE; pcm_ack <= 0; fifo_wr <= 0; k <= 0;
        end else begin
            pcm_ack <= 1'b0;
            fifo_wr <= 1'b0;

            case (st)
            S_IDLE: if (pcm_valid) begin
                k        <= 10'd0;
                pcm_addr <= 11'd0;            // {ch=0, 0}
                st       <= S_L_A;
            end

            S_L_A: st <= S_L_B;               // decoder PCM buffer read latency
            S_L_B: begin
                samp_l <= pcm_data;
                if (is_mono) begin
                    st <= S_WR;               // both outputs take the same value
                end else begin
                    pcm_addr <= {1'b1, k};    // {ch=1, k}
                    st       <= S_R_A;
                end
            end
            S_R_A: st <= S_R_B;
            S_R_B: st <= S_WR;

            // Stall here rather than drop: the decoder is already waiting on
            // the ack, so back-pressure costs nothing but a full FIFO.
            S_WR: if (!fifo_full) begin
                fifo_wr <= 1'b1;
                fifo_l  <= samp_l;
                fifo_r  <= is_mono ? samp_l : pcm_data;
                if (k == 10'd575) begin
                    st <= S_ACK;
                end else begin
                    k        <= k + 10'd1;
                    pcm_addr <= {1'b0, k + 10'd1};
                    st       <= S_L_A;
                end
            end

            S_ACK: begin
                pcm_ack <= 1'b1;
                st      <= S_IDLE;
            end

            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
