`timescale 1ns/1ps
// The TF reader's transport watchdog resets and rescans on a stalled sector.
// The playlist bridge marks every rescan by sending the invalid word 16'hff00
// before the restored count. Hold the previous count through that window so a
// stall that recovers never reaches the song menu as a "no card" state; only
// a list that stays invalid for the whole hold is a real removal and clears
// the count, letting the menu drop the practice screen.
module push2_playlist_hold #(
    parameter [28:0] HOLD_CYCLES = 29'd480_000_000   // 10 s at 48 MHz
)(
    input wire clk,reset_n,
    input wire word_valid,
    input wire [15:0] word,
    output reg [4:0] track_count
);
    reg [28:0] hold;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            track_count<=0;hold<=0;
        end else begin
            if(word_valid && word[15:8]==8'hff) begin
                if(word[4:0]!=0) begin
                    track_count<=word[4:0];
                    hold<=0;
                end else if(track_count!=0 && hold==0)
                    hold<=1'b1;
            end else if(hold!=0) begin
                if(hold==HOLD_CYCLES) begin
                    track_count<=0;
                    hold<=0;
                end else hold<=hold+1'b1;
            end
        end
    end
endmodule
