`timescale 1ns/1ps
// Push 2's 960x160 guide page. Names are the FAT scanner's 8.3 entries.
module push2_song_screen #(parameter PIPELINED=0)(
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
    output wire [15:0] pixel
);
    // Counters change far slower than pixel reads. Convert off the pixel
    // path; each captured value completes after 16 shift/add-3 steps.
    wire [19:0] cursor_digits,score_digits;
    push2_decimal16 cursor_decimal(.clk(clk),.rst(rst),.value_i(cursor),.digits_o(cursor_digits));
    push2_decimal16 score_decimal(.clk(clk),.rst(rst),.value_i(score_count),.digits_o(score_digits));
    reg [15:0] background;
    // Two small asynchronous reads; keep the existing 192-byte table in LUT RAM.
    (* syn_ramstyle="distributed_ram", ram_style="distributed" *) reg [7:0] names[0:191];
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
    reg [7:0] character_q;
    reg [2:0] row_q,col_q;
    reg draw_q;
    reg [15:0] background_q;
    always @(posedge clk or posedge rst) begin
        if(rst) begin character_q<=32;row_q<=0;col_q<=0;draw_q<=0;background_q<=16'h0841;end
        else begin character_q<=character;row_q<=row;col_q<=col;draw_q<=draw;background_q<=background;end
    end
    wire ink;
    assign pixel=(PIPELINED ? draw_q : draw) && ink ? 16'hffff : (PIPELINED ? background_q : background);
    video_font_5x7 font(.character(PIPELINED ? character_q : character),
        .column(PIPELINED ? col_q : col),.row(PIPELINED ? row_q : row),.ink(ink),.glyph());
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
        character=8'd32;row=0;col=0;draw=0;charpos=0;
        header=chosen ? "PRACTICE        " : "SELECT SONG     ";
        hint=chosen ? "SELECT: LIST    " : "L/R SEL PLAY    ";
        state_text=analysis_done ? "SONG READY      " : "SCANNING SONG   ";
        effect_text="DELAY CHORUS RVB";
        progress={digit({4'b0,cursor_digits[19:16]}),digit({4'b0,cursor_digits[15:12]}),digit({4'b0,cursor_digits[11:8]}),digit({4'b0,cursor_digits[7:4]}),digit({4'b0,cursor_digits[3:0]}),8'h2f,
                  digit({4'b0,score_digits[19:16]}),digit({4'b0,score_digits[15:12]}),digit({4'b0,score_digits[11:8]}),digit({4'b0,score_digits[7:4]}),digit({4'b0,score_digits[3:0]}),40'h2020202020};
        background=16'h0841;
        if(y<2 || y==158) background=16'h4a69;
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
                background=16'h18e4;
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
                    background=16'h67ee;
                else background=16'h2945;
            end
            if(y>=119 && y<136 && x>=20 && x<212 && effect_mask[0]) background=16'h18e4;
            if(y>=119 && y<136 && x>=212 && x<404 && effect_mask[1]) background=16'h18e4;
            if(y>=119 && y<136 && x>=404 && x<596 && effect_mask[2]) background=16'h18e4;
        end
    end
endmodule

// Five decimal digits for every 16-bit value, without a combinational divider.
// The input is captured once per conversion. A changed value is picked up
// after completion; once the input is stable it is published within 34 clocks.
module push2_decimal16(
    input wire clk,rst,
    input wire [15:0] value_i,
    output reg [19:0] digits_o
);
    reg [15:0] captured,binary;
    reg [19:0] bcd;
    reg [4:0] step;
    reg busy;
    reg [19:0] corrected;
    integer digit_index;
    always @* begin
        corrected=bcd;
        for(digit_index=0;digit_index<5;digit_index=digit_index+1)
            if(bcd[digit_index*4+:4]>=4'd5)
                corrected[digit_index*4+:4]=bcd[digit_index*4+:4]+4'd3;
    end
    always @(posedge clk or posedge rst) begin
        if(rst) begin
            captured<=0;binary<=0;bcd<=0;step<=0;busy<=0;digits_o<=0;
        end else if(!busy) begin
            if(value_i!=captured) begin
                captured<=value_i;binary<=value_i;bcd<=0;step<=0;busy<=1;
            end
        end else begin
            bcd<={corrected[18:0],binary[15]};
            binary<={binary[14:0],1'b0};
            if(step==5'd15) begin
                digits_o<={corrected[18:0],binary[15]};busy<=0;
            end else step<=step+1'b1;
        end
    end
endmodule
