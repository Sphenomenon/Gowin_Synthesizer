`default_nettype none
// Observe the final PT8211 pins in their 50 MHz launch clock domain. This
// reconstructs both physical PCM16 slots, including serializer underruns.
// No synthesizer samples, predicted PCM, or audio backpressure are involved.
module pt8211_observer (
    input wire clk, reset_n,
    input wire bck, ws, din,
    input wire [31:0] frame_reference,
    output reg [31:0] pcm_pair, // LEFT in bits31:16, RIGHT in bits15:0
    output reg sample_valid,
    output reg [31:0] trigger_reference
);
    reg bck_previous, slot_left, right_complete;
    reg [4:0] bits_seen;
    reg [15:0] shift_word, right_word;
    wire [15:0] received_word = {shift_word[14:0],din};
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            bck_previous<=1; slot_left<=0; right_complete<=0;
            bits_seen<=0; shift_word<=0; right_word<=0;
            pcm_pair<=0; sample_valid<=0; trigger_reference<=0;
        end else begin
            bck_previous<=bck; sample_valid<=0;
            if(bck && !bck_previous) begin
                if(ws != slot_left) begin
                    slot_left<=ws; shift_word<={15'd0,din}; bits_seen<=1;
                    if(!ws) right_complete<=0;
                end else if(bits_seen < 16) begin
                    shift_word<=received_word; bits_seen<=bits_seen+1'b1;
                    if(bits_seen == 15) begin
                        if(!ws) begin right_word<=received_word; right_complete<=1; end
                        else if(right_complete) begin
                            pcm_pair<={received_word,right_word}; sample_valid<=1;
                            trigger_reference<=frame_reference; right_complete<=0;
                        end
                    end
                end
            end
        end
    end
endmodule
`default_nettype wire
