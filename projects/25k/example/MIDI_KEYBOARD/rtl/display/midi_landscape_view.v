`timescale 1ns/1ps
// Native GRAM stays at the proven MADCTL=00 and column offset 12. The display
// renderer maps native coordinates to a 428x142 landscape canvas in RTL.
// Pixel latency: four rising edges (geometry -> character -> font -> color).
module midi_landscape_view (
 input wire clk, reset, snapshot,
 input wire [15:0] key_bitmap,
 input wire [3:0] midi_channel,
 input wire signed [7:0] transpose,
 input wire [6:0] velocity, program_number,
 input wire [1:0] slider_mode,
 input wire [7:0] brightness, strip_value,
 input wire [2:0] focus,
 input wire usb_online, ble_online, touch_ready, panic_busy,
 input wire slider_ready, slider_touched, slider_overrun,
 input wire [7:0] slider_raw_position, slider_filtered_position,
 input wire [7:0] slider_error, slider_general_status, slider_sample_count,
 input wire [15:0] theme_rgb565, clear_rgb565,
 input wire [8:0] pixel_x,
 input wire [7:0] pixel_y,
 output reg [15:0] pixel_color
);
 reg [15:0] keys;
 reg [3:0] channel;
 reg signed [7:0] shift;
 reg [6:0] vel, prog;
 reg [1:0] mode;
 reg [7:0] lamp, strip;
 reg [2:0] selected;
 reg usb, ble, touch, panic;
 reg s2_ready,s2_touched,s2_overrun;
 reg [7:0] s2_error,s2_general_status,s2_sample_count;
 reg [15:0] theme, background;
 // Decimal conversion happens once per snapshot, rather than per pixel.
 reg [11:0] bcd_shift,bcd_channel,bcd_velocity,bcd_program,bcd_lamp,bcd_strip;
 reg [11:0] bcd_s2_raw,bcd_s2_position;
 function [11:0] bin_bcd;
  input [7:0] value;
  reg [11:0] bcd;
  integer n;
  begin
   bcd=0;
   for(n=7;n>=0;n=n-1)begin
    if(bcd[3:0]>=5)bcd[3:0]=bcd[3:0]+4'd3;
    if(bcd[7:4]>=5)bcd[7:4]=bcd[7:4]+4'd3;
    if(bcd[11:8]>=5)bcd[11:8]=bcd[11:8]+4'd3;
    bcd={bcd[10:0],value[n]};
   end
   bin_bcd=bcd;
  end
 endfunction
 always @(posedge clk) begin
  if(reset) begin
   keys<=0;channel<=0;shift<=0;vel<=100;prog<=0;mode<=0;lamp<=96;strip<=0;
   selected<=0;usb<=0;ble<=0;touch<=0;panic<=0;theme<=16'h07ff;background<=16'h0841;
   bcd_shift<=12'h000;bcd_channel<=12'h001;bcd_velocity<=12'h100;
   bcd_program<=12'h001;bcd_lamp<=12'h096;bcd_strip<=0;
   s2_ready<=0;s2_touched<=0;s2_overrun<=0;
   s2_error<=0;s2_general_status<=0;s2_sample_count<=0;bcd_s2_raw<=0;bcd_s2_position<=0;
  end else if(snapshot) begin
   keys<=key_bitmap;channel<=midi_channel;shift<=transpose;vel<=velocity;
   prog<=program_number;mode<=slider_mode;lamp<=brightness;strip<=strip_value;
   selected<=focus;usb<=usb_online;ble<=ble_online;touch<=touch_ready;panic<=panic_busy;
   theme<=theme_rgb565;background<=clear_rgb565;
   bcd_shift<=bin_bcd(transpose[7] ? -transpose : transpose);
   bcd_channel<=bin_bcd({4'd0,midi_channel}+8'd1);
   bcd_velocity<=bin_bcd({1'b0,velocity});bcd_program<=bin_bcd({1'b0,program_number}+8'd1);
   bcd_lamp<=bin_bcd(brightness);bcd_strip<=bin_bcd(strip_value);
   s2_ready<=slider_ready;s2_touched<=slider_touched;s2_overrun<=slider_overrun;
   s2_error<=slider_error;s2_general_status<=slider_general_status;s2_sample_count<=slider_sample_count;
   bcd_s2_raw<=bin_bcd(slider_raw_position);bcd_s2_position<=bin_bcd(slider_filtered_position);
  end
 end
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
                "J": glyph={5'b00111,5'b00010,5'b00010,5'b00010,5'b10010,5'b10010,5'b01100};
                "M": glyph={5'b10001,5'b11011,5'b10101,5'b10101,5'b10001,5'b10001,5'b10001};
                "Q": glyph={5'b01110,5'b10001,5'b10001,5'b10001,5'b10101,5'b10010,5'b01101};
                "V": glyph={5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b01010,5'b00100};
                "W": glyph={5'b10001,5'b10001,5'b10001,5'b10101,5'b10101,5'b11011,5'b10001};
                "X": glyph={5'b10001,5'b10001,5'b01010,5'b00100,5'b01010,5'b10001,5'b10001};
                "Z": glyph={5'b11111,5'b00001,5'b00010,5'b00100,5'b01000,5'b10000,5'b11111};
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


 // One glyph decoder is shared by all regions. Only small, fixed-width
 // coordinates reach /6 and %6; no 32-bit per-label divider or 384-bit mux.
 localparam [3:0] T_NONE=0,T_TITLE=1,T_USB=2,T_BLE=3,T_TOUCH=4,T_PANIC=5,
  T_LABEL=6,T_VALUE=7,T_STRIP=8,T_POSITION=9,T_KEY=10,T_FOOTER=11,
  T_SLIDER_DIAGNOSTIC=12,T_SLIDER_STATUS=13;
 reg [15:0] base_color;
 reg [3:0] text_id;
 reg [2:0] card_index;
 reg [8:0] card_base,card_dx,key_relative;
 reg [4:0] key_index,key_dx;
 reg [7:0] glyph_dx;
 reg [3:0] glyph_dy;
 reg scale2,text_enable;
 reg [15:0] text_ink;
 reg [7:0] character;
 reg [4:0] character_index;
 reg [7:0] font_dx;
 reg [2:0] font_x,font_y;
 reg [11:0] value_bcd;
 reg [31:0] value_word;
 reg [39:0] label_word;
 reg [2:0] value_count,label_count;
 reg [5:0] short_shift;
 reg [7:0] key_number;
 reg [16:0] strip_threshold;
 reg [7:0] strip_distance;
 function [7:0] digit_ascii;
  input [3:0] digit;
  begin digit_ascii={4'h3,digit};end
 endfunction
 function [7:0] hex_ascii;
  input [3:0] digit;
  begin hex_ascii=digit<10 ? (8'h30+digit) : (8'h41+digit-4'd10);end
 endfunction
 function [7:0] footer_character;
  input [4:0] at;
  begin
   case(at)
    0:footer_character="E";1:footer_character="1";2:footer_character=" ";
    3:footer_character="S";4:footer_character="E";5:footer_character="L";
    6:footer_character="E";7:footer_character="C";8:footer_character="T";
    9:footer_character="/";10:footer_character="S";11:footer_character="T";
    12:footer_character="R";13:footer_character="I";14:footer_character="P";
    15,16,17:footer_character=" ";18:footer_character="E";19:footer_character="2";
    20:footer_character=" ";21:footer_character="V";22:footer_character="A";
    23:footer_character="L";24:footer_character="U";25:footer_character="E";
    26:footer_character="/";27:footer_character="P";28:footer_character="A";
    29:footer_character="N";30:footer_character="I";31:footer_character="C";
    default:footer_character=0;
   endcase
  end
 endfunction
 always @* begin
  base_color=background;
  text_id=T_NONE;glyph_dx=0;glyph_dy=0;scale2=0;text_ink=16'hffff;
  value_bcd=0;value_word=0;label_word=0;value_count=0;label_count=0;
  // Six 58-pixel cards stop at x=375, leaving the right-side strip clear.
  // Select a card from X once. Four-pixel gaps are rejected by card_dx.
  if(pixel_x>=318)begin card_index=5;card_base=318;end
  else if(pixel_x>=256)begin card_index=4;card_base=256;end
  else if(pixel_x>=194)begin card_index=3;card_base=194;end
  else if(pixel_x>=132)begin card_index=2;card_base=132;end
  else if(pixel_x>=70)begin card_index=1;card_base=70;end
  else begin card_index=0;card_base=8;end
  card_dx=pixel_x-card_base;
  key_relative=pixel_x-9'd8;
  key_index=key_relative/9'd23;key_dx=key_relative%9'd23;
  key_number={3'd0,key_index}+8'd1;
  // A value of zero is empty, 255 fills the 70-pixel track bottom to top.
  strip_threshold=strip*7'd70;strip_distance=8'd112-pixel_y;
  if(pixel_y<24)begin
   base_color=16'h1084;
   if(pixel_x>=8 && pixel_x<116 && pixel_y>=5 && pixel_y<19)begin
    text_id=T_TITLE;glyph_dx=pixel_x-9'd8;glyph_dy=pixel_y-8'd5;scale2=1;
   end else if(pixel_y>=7 && pixel_y<14)begin
    glyph_dy=pixel_y-8'd7;
    if(pixel_x>=235 && pixel_x<253)begin text_id=T_USB;glyph_dx=pixel_x-9'd235;text_ink=usb?16'h07e0:16'h7bef;end
    else if(pixel_x>=287 && pixel_x<305)begin text_id=T_BLE;glyph_dx=pixel_x-9'd287;text_ink=ble?16'h07e0:16'h7bef;end
    else if(pixel_x>=340 && pixel_x<370)begin text_id=T_TOUCH;glyph_dx=pixel_x-9'd340;text_ink=touch?16'h07e0:16'hfd20;end
    else if(panic && pixel_x>=168 && pixel_x<198)begin text_id=T_PANIC;glyph_dx=pixel_x-9'd168;text_ink=16'hf800;end
   end
  end else if(pixel_y>=29 && pixel_y<72 && card_dx<58)begin
   base_color=selected==card_index?16'h19a6:16'h10a3;
   if(pixel_y==29 || pixel_y==71 || card_dx==0 || card_dx==57)
    base_color=selected==card_index?theme:16'h2945;
   case(card_index)
    0:begin label_word="SHIFT";label_count=5;value_bcd=bcd_shift;
     value_word={8'd0,shift[7]?8'h2d:8'h2b,digit_ascii(bcd_shift[7:4]),digit_ascii(bcd_shift[3:0])};value_count=3;end
    1:begin label_word="CH";label_count=2;value_bcd=bcd_channel;value_count=2;end
    2:begin label_word="VEL";label_count=3;value_bcd=bcd_velocity;value_count=3;end
    3:begin label_word="STRIP";label_count=5;
     if(mode==0)begin value_word="MOD";value_count=3;end
     else if(mode==1)begin value_word="EXPR";value_count=4;end
     else begin value_word="BEND";value_count=mode==2?4:3;end
    end
    4:begin label_word="PROG";label_count=4;value_bcd=bcd_program;value_count=3;end
    default:begin label_word="LAMP";label_count=4;value_bcd=bcd_lamp;value_count=3;end
   endcase
   if(card_index!=0 && card_index!=3)
    value_word={8'd0,digit_ascii(value_bcd[11:8]),digit_ascii(value_bcd[7:4]),digit_ascii(value_bcd[3:0])};
   if(card_dx>=5 && pixel_y>=34 && pixel_y<41)begin
    text_id=T_LABEL;glyph_dx=card_dx-9'd5;glyph_dy=pixel_y-8'd34;text_ink=16'h9cf3;
   end else if(card_dx>=5 && pixel_y>=49 && pixel_y<63)begin
    text_id=T_VALUE;glyph_dx=card_dx-9'd5;glyph_dy=pixel_y-8'd49;scale2=1;
    text_ink=selected==card_index?theme:16'hffff;
   end
  end else if(pixel_y>=74 && pixel_y<81 && pixel_x>=8 && pixel_x<140)begin
   // S2 is the separately configured QT2160 on the slider I2C bus.
   text_id=T_SLIDER_DIAGNOSTIC;glyph_dx=pixel_x-9'd8;glyph_dy=pixel_y-8'd74;
   text_ink=(!s2_ready || s2_error!=0)?16'hf800:(s2_touched?16'h07ff:16'h07e0);
  end else if(pixel_x>=384 && pixel_x<420 && pixel_y>=29 && pixel_y<127)begin
   // This sidebar has its own bounds, separate from all six cards and 16 keys.
   base_color=16'h10a3;
   if(pixel_x==384 || pixel_x==419 || pixel_y==29 || pixel_y==126)
    base_color=selected==3?theme:16'h2945;
   if(pixel_x>=392 && pixel_x<412 && pixel_y>=43 && pixel_y<113)begin
    base_color=16'h2104;
    if({1'b0,strip_distance,8'd0}<strip_threshold)base_color=theme;
    if(mode==2 && pixel_y==77)base_color=16'hffff;
   end else if(pixel_x>=387 && pixel_x<417 && pixel_y>=32 && pixel_y<39)begin
    text_id=T_STRIP;glyph_dx=pixel_x-9'd387;glyph_dy=pixel_y-8'd32;text_ink=16'h9cf3;
   end else if(pixel_x>=393 && pixel_x<411 && pixel_y>=118 && pixel_y<125)begin
    text_id=T_POSITION;glyph_dx=pixel_x-9'd393;glyph_dy=pixel_y-8'd118;text_ink=theme;
   end
  end else if(pixel_y>=82 && pixel_y<127 && pixel_x>=8 && key_index<16 && key_dx<20)begin
   base_color=keys[key_index[3:0]]?theme:16'h2945;
   if(pixel_y==82 || pixel_y==126)base_color=keys[key_index[3:0]]?16'hffff:16'h4208;
   if(key_dx>=4 && key_dx<16 && pixel_y>=101 && pixel_y<108)begin
    text_id=T_KEY;glyph_dx={3'd0,key_dx}-8'd4;glyph_dy=pixel_y-8'd101;
    text_ink=keys[key_index[3:0]]?16'h0000:16'hce59;
   end
  end else if(pixel_y>=133 && pixel_y<140 && pixel_x>=8 && pixel_x<200)begin
   text_id=T_FOOTER;glyph_dx=pixel_x-9'd8;glyph_dy=pixel_y-8'd133;text_ink=16'h8410;
  end else if(pixel_y>=133 && pixel_y<140 && pixel_x>=208 && pixel_x<298)begin
   text_id=T_SLIDER_STATUS;glyph_dx=pixel_x-9'd208;glyph_dy=pixel_y-8'd133;
   text_ink=(s2_error!=0 || s2_overrun)?16'hf800:(s2_ready?16'h07e0:16'hfd20);
  end
 end
 // Stage 1: region geometry, cell offsets and coherent color metadata.
 reg [15:0] g_base_color,g_text_ink;
 reg [3:0] g_text_id,g_glyph_dy;
 reg [7:0] g_glyph_dx,g_key_number;
 reg g_scale2;
 reg [31:0] g_value_word;
 reg [39:0] g_label_word;
 reg [2:0] g_value_count,g_label_count;
 reg [11:0] g_bcd_strip;
 reg [11:0] g_bcd_s2_raw,g_bcd_s2_position;
 reg g_s2_ready,g_s2_touched,g_s2_overrun;
 reg [7:0] g_s2_error,g_s2_general_status,g_s2_sample_count;
 // Stage 2: a single ASCII character and local 5x7 font coordinates.
 reg [15:0] c_base_color,c_text_ink;
 reg [7:0] c_character;
 reg [2:0] c_font_x,c_font_y;
 reg c_text_enable;
 // Stage 3: font lookup has its own timing budget, color mux follows in stage4.
 reg [15:0] f_base_color,f_text_ink;
 reg f_on;
 always @(posedge clk)begin
  if(reset)begin
   g_base_color<=16'h0841;g_text_ink<=0;g_text_id<=T_NONE;
   g_glyph_dx<=0;g_glyph_dy<=0;g_scale2<=0;g_value_word<=0;g_label_word<=0;
   g_value_count<=0;g_label_count<=0;g_bcd_strip<=0;g_key_number<=0;
   g_bcd_s2_raw<=0;g_bcd_s2_position<=0;g_s2_ready<=0;g_s2_touched<=0;g_s2_overrun<=0;
   g_s2_error<=0;g_s2_general_status<=0;g_s2_sample_count<=0;
   c_base_color<=16'h0841;c_text_ink<=0;c_character<=0;c_font_x<=0;c_font_y<=0;c_text_enable<=0;
   f_base_color<=16'h0841;f_text_ink<=0;f_on<=0;pixel_color<=16'h0841;
  end else begin
   g_base_color<=base_color;g_text_ink<=text_ink;g_text_id<=text_id;
   g_glyph_dx<=glyph_dx;g_glyph_dy<=glyph_dy;g_scale2<=scale2;
   g_value_word<=value_word;g_label_word<=label_word;g_value_count<=value_count;g_label_count<=label_count;
   g_bcd_strip<=bcd_strip;g_key_number<=key_number;
   g_bcd_s2_raw<=bcd_s2_raw;g_bcd_s2_position<=bcd_s2_position;
   g_s2_ready<=s2_ready;g_s2_touched<=s2_touched;g_s2_overrun<=s2_overrun;
   g_s2_error<=s2_error;g_s2_general_status<=s2_general_status;g_s2_sample_count<=s2_sample_count;
   c_base_color<=g_base_color;c_text_ink<=g_text_ink;
   c_character<=character;c_font_x<=font_x;c_font_y<=font_y;c_text_enable<=text_enable;
   f_base_color<=c_base_color;f_text_ink<=c_text_ink;
   f_on<=c_text_enable && font_on(c_character,c_font_x,c_font_y);
   pixel_color<=f_on?f_text_ink:f_base_color;
  end
 end
 always @* begin
  character=0;character_index=0;font_dx=0;font_x=0;font_y=0;short_shift=0;text_enable=0;
  // The only character-cell divider and glyph-coordinate modulo in the view.
  font_dx=g_scale2?{1'b0,g_glyph_dx[7:1]}:g_glyph_dx;
  character_index=font_dx/8'd6;font_x=font_dx%8'd6;
  font_y=g_scale2?g_glyph_dy[3:1]:g_glyph_dy[2:0];
  text_enable=g_text_id!=T_NONE;
  case(g_text_id)
   T_TITLE:case(character_index)
    0:character="M";1:character="I";2:character="D";3:character="I";
    4:character=" ";5:character="K";6:character="E";7:character="Y";8:character="S";
    default:character=0;endcase
   T_USB:case(character_index)0:character="U";1:character="S";2:character="B";default:character=0;endcase
   T_BLE:case(character_index)0:character="B";1:character="L";2:character="E";default:character=0;endcase
   T_TOUCH:case(character_index)0:character="T";1:character="O";2:character="U";3:character="C";4:character="H";default:character=0;endcase
   T_PANIC:case(character_index)0:character="P";1:character="A";2:character="N";3:character="I";4:character="C";default:character=0;endcase
   T_LABEL:begin
    if(character_index>=g_label_count)text_enable=0;
    short_shift=(g_label_count-1'b1-character_index)<<3;
    character=g_label_word>>short_shift;
   end
   T_VALUE:begin
    if(character_index>=g_value_count)text_enable=0;
    short_shift=(g_value_count-1'b1-character_index)<<3;
    character=g_value_word>>short_shift;
   end
   T_STRIP:case(character_index)0:character="S";1:character="T";2:character="R";3:character="I";4:character="P";default:character=0;endcase
   T_POSITION:case(character_index)0:character=digit_ascii(g_bcd_strip[11:8]);1:character=digit_ascii(g_bcd_strip[7:4]);2:character=digit_ascii(g_bcd_strip[3:0]);default:character=0;endcase
   T_KEY:if(character_index==0)character=g_key_number>=10?"1":"0";
    else character=digit_ascii(g_key_number>=10?g_key_number-8'd10:g_key_number);
   T_FOOTER:character=footer_character(character_index);
   T_SLIDER_DIAGNOSTIC:case(character_index)
    0:character="S";1:character="2";2:character=" ";
    3:character="R";4:character=g_s2_ready?"1":"0";5:character=" ";
    6:character="T";7:character=g_s2_touched?"1":"0";8:character=" ";
    9:character="R";10:character="A";11:character="W";
    12:character=digit_ascii(g_bcd_s2_raw[11:8]);
    13:character=digit_ascii(g_bcd_s2_raw[7:4]);
    14:character=digit_ascii(g_bcd_s2_raw[3:0]);15:character=" ";
    16:character="P";17:character="O";18:character="S";
    19:character=digit_ascii(g_bcd_s2_position[11:8]);
    20:character=digit_ascii(g_bcd_s2_position[7:4]);
    21:character=digit_ascii(g_bcd_s2_position[3:0]);default:character=0;
   endcase
   T_SLIDER_STATUS:case(character_index)
    0:character="G";1:character=hex_ascii(g_s2_general_status[7:4]);2:character=hex_ascii(g_s2_general_status[3:0]);3:character=" ";
    4:character="E";5:character=hex_ascii(g_s2_error[7:4]);6:character=hex_ascii(g_s2_error[3:0]);7:character=" ";
    8:character="O";9:character="V";10:character=g_s2_overrun?"1":"0";11:character=" ";
    12:character="N";13:character=hex_ascii(g_s2_sample_count[7:4]);14:character=hex_ascii(g_s2_sample_count[3:0]);default:character=0;
   endcase
   default:character=0;
  endcase
 end
endmodule
