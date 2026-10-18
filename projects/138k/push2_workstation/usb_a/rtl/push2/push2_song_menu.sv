`timescale 1ns/1ps
// Play opens the song list; Left/Right browse; Select starts analysis.
// Select again returns to the list. No stale score is exposed while browsing.
module push2_song_menu(
    input wire clk,rst,
    input wire toggle,mode,
    input wire prev,next,select_key,
    input wire [4:0] track_count,
    output reg chosen,
    output reg [3:0] browse_index,track_index,
    output reg launch
);
    always @(posedge clk or posedge rst) begin
        if(rst) begin
            chosen<=0;browse_index<=0;track_index<=0;launch<=0;
        end else begin
            launch<=0;
            if(track_count==0) begin chosen<=0;browse_index<=0;track_index<=0;end
            else if(toggle) begin chosen<=0;browse_index<=track_index;end
            else if(mode) begin
                if(select_key) begin
                    if(chosen) begin chosen<=0;browse_index<=track_index;end
                    else if(track_count!=0 && {1'b0,browse_index}<track_count) begin
                        chosen<=1;track_index<=browse_index;launch<=1;
                    end
                end else if(!chosen && prev && browse_index!=0)
                    browse_index<=browse_index-1'b1;
                else if(!chosen && next && {1'b0,browse_index}+5'd1<track_count)
                    browse_index<=browse_index+1'b1;
            end
        end
    end
endmodule
