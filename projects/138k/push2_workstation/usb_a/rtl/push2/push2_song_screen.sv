`timescale 1ns/1ps
// Push 2's 960x160 guide page. Names are the FAT scanner's 8.3 entries.
module push2_song_screen(
    input wire clk,rst,
    input wire name_write_valid,
    input wire [7:0] name_write_addr,name_write_data,
    input wire chosen,
    input wire [3:0] browse_index,track_index,
    input wire [4:0] track_count,
    input wire [15:0] score_count,cursor,
    input wire analysis_done,
    input wire [2:0] effect_mask,
    input wire [9:0] x,
    input wire [7:0] y,
    output reg [15:0] pixel
);
    reg [7:0] names[0:191];
    always @(posedge clk) if(name_write_valid && name_write_addr<8'd192)
        names[name_write_addr]<=name_write_data;
    wire [3:0] list_row=(y-8'd28)/8'd16;
    wire [4:0] list_track={1'b0,list_row}+(x>=10'd480 ? 5'd8 : 5'd0);
    wire [9:0] list_local_x=x>=10'd480 ? x-10'd480 : x;
    wire [6:0] list_char=(list_local_x-10'd32)/10'd12;
    wire [6:0] song_char=(x-10'd96)/10'd12;
    wire [7:0] list_addr=({3'd0,list_track}<<3)+({3'd0,list_track}<<2)+list_char;
    wire [7:0] song_addr=({4'd0,track_index}<<3)+({4'd0,track_index}<<2)+song_char;
    reg [7:0] character;
    reg [2:0] row,col;
    reg draw;
    wire ink;
    video_font_5x7 font(.character(character),.column(col),.row(row),.ink(ink),.glyph());
    function [7:0] digit(input [7:0] n);
        digit=8'd48+n;
    endfunction
    reg [127:0] header;
    reg [127:0] hint;
    reg [127:0] progress;
    reg [127:0] state_text,effect_text;
    reg [5:0] charpos;
    // The denominator grows while scanning. Numeric counts stay exact;
    // the bar becomes full only after the complete score is played.
    wire [9:0] progress_pixels=score_count==0 ? 10'd0 :
        (analysis_done && cursor>=score_count) ? 10'd800 :
        (cursor>=16'd800 ? 10'd799 : cursor[9:0]);
    always @* begin
        character=8'd32;row=0;col=0;draw=0;
        header=chosen ? "PRACTICE        " : "SELECT SONG     ";
        hint=chosen ? "SELECT: LIST    " : "L/R SEL PLAY    ";
        state_text=analysis_done ? "SONG READY      " : "SCANNING SONG   ";
        effect_text="DELAY CHORUS RVB";
        progress={digit((cursor/16'd10000)%10),digit((cursor/16'd1000)%10),
                  digit((cursor/16'd100)%10),digit((cursor/16'd10)%10),digit(cursor%10),8'h2f,
                  digit((score_count/16'd10000)%10),digit((score_count/16'd1000)%10),
                  digit((score_count/16'd100)%10),digit((score_count/16'd10)%10),
                  digit(score_count%10),40'h2020202020};
        pixel=16'h0841;
        if(y<2 || y==158) pixel=16'h4a69;
        if(y>=5 && y<19 && x>=10'd24 && x<10'd216) begin
            charpos=(x-10'd24)/10'd12;
            character=header[127-charpos*8 -:8];
            row=(y-5)/2;col=((x-24)%12)/2;draw=1;
        end else if(y>=5 && y<19 && x>=10'd700 && x<10'd892) begin
            charpos=(x-10'd700)/10'd12;
            character=hint[127-charpos*8 -:8];
            row=(y-5)/2;col=((x-700)%12)/2;draw=1;
        end
        if(!chosen) begin
            if(y>=28 && y<156 && list_track<track_count &&
               list_local_x>=32 && list_local_x<176 && list_char<12) begin
                character=names[list_addr];
                row=((y-28)%16)/2;col=((list_local_x-32)%12)/2;draw=1;
            end
            if(y>=28 && y<156 && list_track=={1'b0,browse_index} &&
               list_local_x>=16 && list_local_x<224)
                pixel=16'h18e4;
        end else begin
            if(y>=32 && y<46 && x>=96 && x<240 && song_char<12) begin
                character=names[song_addr];
                row=(y-32)/2;col=((x-96)%12)/2;draw=1;
            end else if(y>=58 && y<72 && x>=96 && x<288) begin
                charpos=(x-96)/12;
                character=state_text[127-charpos*8 -:8];
                row=(y-58)/2;col=((x-96)%12)/2;draw=1;
            end else if(y>=82 && y<96 && x>=96 && x<288) begin
                charpos=(x-96)/12;
                character=progress[127-charpos*8 -:8];
                row=(y-82)/2;col=((x-96)%12)/2;draw=1;
            end else if(y>=120 && y<134 && x>=24 && x<456) begin
                charpos=(x-24)/12;
                if(charpos<16) begin
                    character=effect_text[127-charpos*8 -:8];
                    row=(y-120)/2;col=((x-24)%12)/2;draw=1;
                end
            end
            if(y>=104 && y<114 && x>=80 && x<880) begin
                if(x-10'd80<progress_pixels)
                    pixel=16'h67ee;
                else pixel=16'h2945;
            end
            if(y>=119 && y<136 && x>=20 && x<212 && effect_mask[0]) pixel=16'h18e4;
            if(y>=119 && y<136 && x>=212 && x<404 && effect_mask[1]) pixel=16'h18e4;
            if(y>=119 && y<136 && x>=404 && x<596 && effect_mask[2]) pixel=16'h18e4;
        end
        if(draw && ink) pixel=16'hffff;
    end
endmodule
