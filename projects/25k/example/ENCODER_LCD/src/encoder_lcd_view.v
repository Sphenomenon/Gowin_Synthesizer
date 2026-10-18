`timescale 1ns/1ps
// Six parallel 16-cycle conversions finish within the display's 32-clock
// snapshot settling time. No decimal divider or framebuffer is required.
module encoder_lcd_bcd16 (
    input wire clk, reset, start,
    input wire [15:0] value,
    output reg [19:0] bcd = 0
);
    reg [35:0] work = 0;
    reg [4:0] count = 0;
    reg busy = 0;
    wire [35:0] adjusted = {
        (work[35:32] >= 5 ? work[35:32] + 4'd3 : work[35:32]),
        (work[31:28] >= 5 ? work[31:28] + 4'd3 : work[31:28]),
        (work[27:24] >= 5 ? work[27:24] + 4'd3 : work[27:24]),
        (work[23:20] >= 5 ? work[23:20] + 4'd3 : work[23:20]),
        (work[19:16] >= 5 ? work[19:16] + 4'd3 : work[19:16]),
        work[15:0]
    };
    wire [35:0] shifted = {adjusted[34:0],1'b0};
    always @(posedge clk) begin
        if (reset) begin
            work <= 0; count <= 0; busy <= 0; bcd <= 0;
        end else if (start) begin
            work <= {20'b0,value}; count <= 0; busy <= 1;
        end else if (busy) begin
            work <= shifted;
            if (count == 15) begin bcd <= shifted[35:16]; busy <= 0; end
            else count <= count + 1'b1;
        end
    end
endmodule

module encoder_lcd_view (
    input wire clk, reset, snapshot,
    input wire signed [15:0] position1, position2,
    input wire [15:0] press_count1, press_count2,
    input wire [15:0] invalid_count1, invalid_count2,
    input wire [1:0] ab1, ab2,
    input wire key1, key2,
    input wire signed [1:0] direction1, direction2,
    input wire [15:0] pixel_x, pixel_y,
    output reg [15:0] pixel_color
);
    reg sign1 = 0, sign2 = 0;
    reg [1:0] held_ab1 = 0, held_ab2 = 0;
    reg held_key1 = 0, held_key2 = 0;
    reg signed [1:0] held_direction1 = 0, held_direction2 = 0;
    wire [15:0] magnitude1 = position1[15] ? (~position1 + 16'd1) : position1;
    wire [15:0] magnitude2 = position2[15] ? (~position2 + 16'd1) : position2;
    wire [19:0] bcd_position1, bcd_position2;
    wire [19:0] bcd_press1, bcd_press2, bcd_invalid1, bcd_invalid2;
    encoder_lcd_bcd16 pos1 (.clk(clk),.reset(reset),.start(snapshot),.value(magnitude1),.bcd(bcd_position1));
    encoder_lcd_bcd16 pos2 (.clk(clk),.reset(reset),.start(snapshot),.value(magnitude2),.bcd(bcd_position2));
    encoder_lcd_bcd16 key_count1 (.clk(clk),.reset(reset),.start(snapshot),.value(press_count1),.bcd(bcd_press1));
    encoder_lcd_bcd16 key_count2 (.clk(clk),.reset(reset),.start(snapshot),.value(press_count2),.bcd(bcd_press2));
    encoder_lcd_bcd16 err_count1 (.clk(clk),.reset(reset),.start(snapshot),.value(invalid_count1),.bcd(bcd_invalid1));
    encoder_lcd_bcd16 err_count2 (.clk(clk),.reset(reset),.start(snapshot),.value(invalid_count2),.bcd(bcd_invalid2));
    always @(posedge clk) begin
        if (reset) begin
            sign1 <= 0; sign2 <= 0;
            held_ab1 <= 0; held_ab2 <= 0;
            held_key1 <= 0; held_key2 <= 0;
            held_direction1 <= 0; held_direction2 <= 0;
        end else if (snapshot) begin
            sign1 <= position1[15]; sign2 <= position2[15];
            held_ab1 <= ab1; held_ab2 <= ab2;
            held_key1 <= key1; held_key2 <= key2;
            held_direction1 <= direction1; held_direction2 <= direction2;
        end
    end

    function [7:0] decimal_char;
        input [19:0] bcd;
        input [3:0] index;
        begin
            case (index)
                0: decimal_char = 8'h30 + bcd[19:16];
                1: decimal_char = 8'h30 + bcd[15:12];
                2: decimal_char = 8'h30 + bcd[11:8];
                3: decimal_char = 8'h30 + bcd[7:4];
                4: decimal_char = 8'h30 + bcd[3:0];
                default: decimal_char = " ";
            endcase
        end
    endfunction

    // Each glyph uses seven fixed row slices, avoiding glyph_y*5 addressing.
    function font_on;
        input [7:0] character;
        input [2:0] x, y;
        reg [34:0] glyph;
        reg [4:0] row;
        begin
            case (character)
                "0": glyph={5'b01110,5'b10001,5'b10011,5'b10101,5'b11001,5'b10001,5'b01110};
                "1": glyph={5'b00100,5'b01100,5'b00100,5'b00100,5'b00100,5'b00100,5'b01110};
                "2": glyph={5'b01110,5'b10001,5'b00001,5'b00010,5'b00100,5'b01000,5'b11111};
                "3": glyph={5'b11110,5'b00001,5'b00001,5'b01110,5'b00001,5'b00001,5'b11110};
                "4": glyph={5'b00010,5'b00110,5'b01010,5'b10010,5'b11111,5'b00010,5'b00010};
                "5": glyph={5'b11111,5'b10000,5'b10000,5'b11110,5'b00001,5'b00001,5'b11110};
                "6": glyph={5'b01110,5'b10000,5'b10000,5'b11110,5'b10001,5'b10001,5'b01110};
                "7": glyph={5'b11111,5'b00001,5'b00010,5'b00100,5'b01000,5'b01000,5'b01000};
                "8": glyph={5'b01110,5'b10001,5'b10001,5'b01110,5'b10001,5'b10001,5'b01110};
                "9": glyph={5'b01110,5'b10001,5'b10001,5'b01111,5'b00001,5'b00001,5'b01110};
                "A": glyph={5'b01110,5'b10001,5'b10001,5'b11111,5'b10001,5'b10001,5'b10001};
                "B": glyph={5'b11110,5'b10001,5'b10001,5'b11110,5'b10001,5'b10001,5'b11110};
                "C": glyph={5'b01110,5'b10001,5'b10000,5'b10000,5'b10000,5'b10001,5'b01110};
                "D": glyph={5'b11110,5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b11110};
                "E": glyph={5'b11111,5'b10000,5'b10000,5'b11110,5'b10000,5'b10000,5'b11111};
                "F": glyph={5'b11111,5'b10000,5'b10000,5'b11110,5'b10000,5'b10000,5'b10000};
                "G": glyph={5'b01110,5'b10001,5'b10000,5'b10111,5'b10001,5'b10001,5'b01110};
                "H": glyph={5'b10001,5'b10001,5'b10001,5'b11111,5'b10001,5'b10001,5'b10001};
                "I": glyph={5'b01110,5'b00100,5'b00100,5'b00100,5'b00100,5'b00100,5'b01110};
                "K": glyph={5'b10001,5'b10010,5'b10100,5'b11000,5'b10100,5'b10010,5'b10001};
                "L": glyph={5'b10000,5'b10000,5'b10000,5'b10000,5'b10000,5'b10000,5'b11111};
                "N": glyph={5'b10001,5'b11001,5'b10101,5'b10011,5'b10001,5'b10001,5'b10001};
                "O": glyph={5'b01110,5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b01110};
                "P": glyph={5'b11110,5'b10001,5'b10001,5'b11110,5'b10000,5'b10000,5'b10000};
                "R": glyph={5'b11110,5'b10001,5'b10001,5'b11110,5'b10100,5'b10010,5'b10001};
                "S": glyph={5'b01111,5'b10000,5'b10000,5'b01110,5'b00001,5'b00001,5'b11110};
                "T": glyph={5'b11111,5'b00100,5'b00100,5'b00100,5'b00100,5'b00100,5'b00100};
                "U": glyph={5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b01110};
                "Y": glyph={5'b10001,5'b10001,5'b10001,5'b01010,5'b00100,5'b00100,5'b00100};
                "+": glyph={5'b00000,5'b00100,5'b00100,5'b11111,5'b00100,5'b00100,5'b00000};
                "-": glyph={5'b00000,5'b00000,5'b00000,5'b11111,5'b00000,5'b00000,5'b00000};
                ":": glyph={5'b00000,5'b00100,5'b00100,5'b00000,5'b00100,5'b00100,5'b00000};
                "/": glyph={5'b00001,5'b00001,5'b00010,5'b00100,5'b01000,5'b10000,5'b10000};
                default: glyph=0;
            endcase
            case (y)
                0: row=glyph[34:30]; 1: row=glyph[29:25];
                2: row=glyph[24:20]; 3: row=glyph[19:15];
                4: row=glyph[14:10]; 5: row=glyph[9:5];
                6: row=glyph[4:0]; default: row=0;
            endcase
            case (x)
                0: font_on=row[4]; 1: font_on=row[3]; 2: font_on=row[2];
                3: font_on=row[1]; 4: font_on=row[0]; default: font_on=0;
            endcase
        end
    endfunction

    reg [4:0] line;
    reg [1:0] scale;
    reg [8:0] y_origin;
    reg [15:0] ink_color;
    reg [15:0] relative_x, relative_y, char_x;
    reg [3:0] char_index;
    reg [2:0] glyph_x, glyph_y;
    reg [7:0] character;
    reg [119:0] text;
    reg [19:0] selected_bcd;
    reg selected_sign, selected_key;
    reg [1:0] selected_ab;
    reg signed [1:0] selected_direction;
    always @* begin
        line=31; scale=1; y_origin=0; ink_color=16'h7bef;
        if (pixel_y>=12 && pixel_y<26) begin line=0; scale=2; y_origin=12; ink_color=16'hffff; end
        else if (pixel_y>=48 && pixel_y<62) begin line=1; scale=2; y_origin=48; ink_color=16'h07ff; end
        else if (pixel_y>=76 && pixel_y<97) begin line=2; scale=3; y_origin=76; ink_color=16'h07ff; end
        else if (pixel_y>=104 && pixel_y<118) begin line=3; scale=2; y_origin=104; ink_color=16'h07ff; end
        else if (pixel_y>=124 && pixel_y<138) begin line=4; scale=2; y_origin=124; ink_color=16'h07ff; end
        else if (pixel_y>=144 && pixel_y<158) begin line=5; scale=2; y_origin=144; ink_color=16'h07ff; end
        else if (pixel_y>=162 && pixel_y<169) begin line=6; y_origin=162; ink_color=16'h07ff; end
        else if (pixel_y>=180 && pixel_y<187) begin line=7; y_origin=180; end
        else if (pixel_y>=194 && pixel_y<201) begin line=8; y_origin=194; end
        else if (pixel_y>=232 && pixel_y<246) begin line=9; scale=2; y_origin=232; ink_color=16'hffe0; end
        else if (pixel_y>=260 && pixel_y<281) begin line=10; scale=3; y_origin=260; ink_color=16'hffe0; end
        else if (pixel_y>=288 && pixel_y<302) begin line=11; scale=2; y_origin=288; ink_color=16'hffe0; end
        else if (pixel_y>=308 && pixel_y<322) begin line=12; scale=2; y_origin=308; ink_color=16'hffe0; end
        else if (pixel_y>=328 && pixel_y<342) begin line=13; scale=2; y_origin=328; ink_color=16'hffe0; end
        else if (pixel_y>=346 && pixel_y<353) begin line=14; y_origin=346; ink_color=16'hffe0; end
        else if (pixel_y>=372 && pixel_y<379) begin line=15; y_origin=372; end
        else if (pixel_y>=388 && pixel_y<395) begin line=16; y_origin=388; end
        else if (pixel_y>=406 && pixel_y<413) begin line=17; y_origin=406; end

        relative_x=pixel_x-16; relative_y=pixel_y-y_origin;
        char_index=15; char_x=0; glyph_x=7; glyph_y=7;
        // Fixed comparisons and subtracts map scaled glyph cells. Scale 3
        // uses thresholds rather than a synthesized integer divider.
        if (scale==3) begin
            if (relative_x<18) begin char_index=0; char_x=relative_x; end
            else if (relative_x<36) begin char_index=1; char_x=relative_x-18; end
            else if (relative_x<54) begin char_index=2; char_x=relative_x-36; end
            else if (relative_x<72) begin char_index=3; char_x=relative_x-54; end
            else if (relative_x<90) begin char_index=4; char_x=relative_x-72; end
            else if (relative_x<108) begin char_index=5; char_x=relative_x-90; end
            if (char_x<3) glyph_x=0; else if(char_x<6) glyph_x=1;
            else if(char_x<9) glyph_x=2; else if(char_x<12) glyph_x=3;
            else if(char_x<15) glyph_x=4; else glyph_x=5;
            if(relative_y<3) glyph_y=0; else if(relative_y<6) glyph_y=1;
            else if(relative_y<9) glyph_y=2; else if(relative_y<12) glyph_y=3;
            else if(relative_y<15) glyph_y=4; else if(relative_y<18) glyph_y=5;
            else glyph_y=6;
        end else begin
            if (scale==2) begin relative_x=relative_x>>1; relative_y=relative_y>>1; end
            if(relative_x<6) begin char_index=0; char_x=relative_x; end
            else if(relative_x<12) begin char_index=1; char_x=relative_x-6; end
            else if(relative_x<18) begin char_index=2; char_x=relative_x-12; end
            else if(relative_x<24) begin char_index=3; char_x=relative_x-18; end
            else if(relative_x<30) begin char_index=4; char_x=relative_x-24; end
            else if(relative_x<36) begin char_index=5; char_x=relative_x-30; end
            else if(relative_x<42) begin char_index=6; char_x=relative_x-36; end
            else if(relative_x<48) begin char_index=7; char_x=relative_x-42; end
            else if(relative_x<54) begin char_index=8; char_x=relative_x-48; end
            else if(relative_x<60) begin char_index=9; char_x=relative_x-54; end
            else if(relative_x<66) begin char_index=10; char_x=relative_x-60; end
            else if(relative_x<72) begin char_index=11; char_x=relative_x-66; end
            else if(relative_x<78) begin char_index=12; char_x=relative_x-72; end
            else if(relative_x<84) begin char_index=13; char_x=relative_x-78; end
            else if(relative_x<90) begin char_index=14; char_x=relative_x-84; end
            glyph_x=char_x[2:0]; glyph_y=relative_y[2:0];
        end
        text="               "; character=" ";
        selected_bcd=0; selected_sign=0; selected_key=0;
        selected_ab=0; selected_direction=0;
        if (line>=9) begin
            selected_sign=sign2; selected_ab=held_ab2;
            selected_key=held_key2; selected_direction=held_direction2;
        end else begin
            selected_sign=sign1; selected_ab=held_ab1;
            selected_key=held_key1; selected_direction=held_direction1;
        end
        case (line)
            0: text="ENCODERS       ";
            1: text="ENCODER 1      ";
            9: text="ENCODER 2      ";
            7: text="TURN: DETENTS  ";
            8: text="PRESS: COUNT   ";
            15: text="DIR + / - / 0  ";
            16: text="ERR: BAD EDGES ";
            17: text="COUNTS RETAINED";
            2,10: begin
                selected_bcd=line==2 ? bcd_position1 : bcd_position2;
                if (char_index==0) character=selected_sign ? "-" : "+";
                else character=decimal_char(selected_bcd,char_index-1'b1);
            end
            3,11: begin
                text="DIR            ";
                if(char_index==4) character=selected_direction>0 ? "+" : selected_direction<0 ? "-" : "0";
            end
            4,12: begin
                text="A  B  K        ";
                if(char_index==1) character=selected_ab[1] ? "1" : "0";
                else if(char_index==4) character=selected_ab[0] ? "1" : "0";
                else if(char_index==7) character=selected_key ? "1" : "0";
            end
            5,13: begin
                text="KEY            ";
                selected_bcd=line==5 ? bcd_press1 : bcd_press2;
                if(char_index>=4) character=decimal_char(selected_bcd,char_index-4);
            end
            6,14: begin
                text="ERR            ";
                selected_bcd=line==6 ? bcd_invalid1 : bcd_invalid2;
                if(char_index>=4) character=decimal_char(selected_bcd,char_index-4);
            end
        endcase
        // Fixed slices also keep static string addressing free of multipliers.
        if(character==" ") begin
            case(char_index)
                0: character=text[119:112]; 1: character=text[111:104];
                2: character=text[103:96]; 3: character=text[95:88];
                4: character=text[87:80]; 5: character=text[79:72];
                6: character=text[71:64]; 7: character=text[63:56];
                8: character=text[55:48]; 9: character=text[47:40];
                10: character=text[39:32]; 11: character=text[31:24];
                12: character=text[23:16]; 13: character=text[15:8];
                14: character=text[7:0]; default: character=" ";
            endcase
        end
        pixel_color=16'h0000;
        if(pixel_x==0 || pixel_x==141 || pixel_y==0 || pixel_y==427 || pixel_y==218)
            pixel_color=16'h2104;
        if(pixel_x>=16 && pixel_x<126 && line!=31 && font_on(character,glyph_x,glyph_y))
            pixel_color=ink_color;
    end
endmodule
