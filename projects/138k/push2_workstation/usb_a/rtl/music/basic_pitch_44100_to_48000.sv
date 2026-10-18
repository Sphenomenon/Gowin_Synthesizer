`timescale 1ns/1ps
// Nearest-sample 160/147 rate conversion for the score analyzer. Every 147
// decoded 44.1-kHz samples produce exactly 160 48-kHz samples. Backpressure
// preserves both the input samples and output repeats.
module basic_pitch_44100_to_48000 (
    input wire clk_i,rst_ni,
    input wire valid_i,
    output wire ready_o,
    input wire signed [15:0] left_i,right_i,
    output wire valid_o,
    input wire ready_i,
    output reg signed [15:0] left_o,right_o
);
    reg pending;
    reg [1:0] remaining;
    reg [7:0] phase;
    wire double_sample = phase >= 8'd134;
    assign ready_o = !pending;
    assign valid_o = pending;
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            pending<=0;remaining<=0;phase<=0;left_o<=0;right_o<=0;
        end else begin
            if(valid_i && ready_o) begin
                left_o<=left_i;right_o<=right_i;
                pending<=1;
                remaining<=double_sample ? 2'd2 : 2'd1;
                phase<=double_sample ? phase-8'd134 : phase+8'd13;
            end else if(valid_o && ready_i) begin
                if(remaining==2'd1) begin pending<=0;remaining<=0;end
                else remaining<=remaining-1'b1;
            end
        end
    end
endmodule
