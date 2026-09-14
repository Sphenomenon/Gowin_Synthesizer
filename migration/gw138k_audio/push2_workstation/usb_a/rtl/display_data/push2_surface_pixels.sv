// 960x160 performance panel; snapshot at each frame boundary, no DDR wait.
module push2_surface_pixels(input wire clk,rst,frame_ready,output wire frame_start,
    input wire [9:0] x,input wire [7:0] y,output wire pixel_valid,
    output reg [15:0] pixel,input wire [31:0] control,options,
    input wire [63:0] held,input wire [6:0] note,velocity,
    input wire [63:0] display_meta,input wire display_meta_valid);
    reg [22:0] timer;
    reg [31:0] cs,op;reg [63:0] pads;reg [6:0] n,v;
    reg [2:0] display_effect_mask;reg display_meta_seen;
    assign frame_start=!rst && timer==0 && frame_ready;
    assign pixel_valid=!rst;
    always @(posedge clk or posedge rst)begin
        if(rst)begin timer<=0;cs<=0;op<=0;pads<=0;n<=60;v<=0;display_effect_mask<=0;display_meta_seen<=0;end
        else if(display_meta_valid)begin display_effect_mask<=display_meta[25:23];display_meta_seen<=1;end
        else if(frame_start)begin timer<=23'd4999999;cs<=control;op<=options;pads<=held;n<=note;v<=velocity;end
        else if(timer!=0)timer<=timer-1'b1;
    end
    wire [3:0] tile=x/10'd120;
    wire [6:0] local_x=x%10'd120;
    wire [3:0] charpos=local_x/7'd12;
    wire [2:0] col=(local_x%7'd12)/2;
    reg [2:0] row;
    reg [7:0] character;
    reg [79:0] text;
    reg [7:0] number;
    reg active,draw;
    function [79:0] top_label(input [3:0] i);
        case(i)0:top_label=" A        ";1:top_label=" B        ";2:top_label=" C        ";
            3:top_label=" FLUTE    ";4:top_label=" STRINGS  ";5:top_label=" BRASS    ";
            6:top_label=" MARIMBA  ";default:top_label=" PIANO    ";endcase
    endfunction
    function [79:0] bottom_label(input [3:0] i);
        case(i)0:bottom_label=" DELAY    ";1:bottom_label=" CHORUS   ";2:bottom_label=" REVERB   ";
            3:bottom_label=" STEREO   ";4:bottom_label=" LEFT     ";5:bottom_label=" RIGHT    ";
            6:bottom_label=" MUTE     ";default:bottom_label=" PANIC    ";endcase
    endfunction
    wire ink;
    video_font_5x7 font(.character(character),.column(col),.row(row),.ink(ink),.glyph());
    wire [3:0] gx=(x-10'd736)/10'd26;
    wire [3:0] gy=(y-8'd40)/8'd10;
    wire grid=x>=736 && x<944 && y>=40 && y<120;
    wire grid_ink=((x-736)%26)<22 && ((y-40)%10)<7;
    always @* begin
        character=32;row=0;number=0;text="          ";active=0;draw=0;
        case(tile)0:number=cs[30:24];1:number={1'b0,op[10:4]};2:number={1'b0,op[17:11]};
            3:number={1'b0,n};4:number={1'b0,v};default:number=op[25:18];endcase
        if(y>=8 && y<22)begin
            text=top_label(tile);row=(y-8)/2;draw=1;
            active=tile<3?cs[4:3]==tile:cs[9:7]==tile-3;
        end else if(y>=134 && y<148)begin
            text=bottom_label(tile);row=(y-134)/2;draw=1;
            active=tile<3?(display_meta_seen?display_effect_mask[tile]:cs[tile]):tile<7?cs[6:5]==tile-3:1;
        end else if(y>=42 && y<56 && tile<6)begin
            case(tile)0:text=" VOLUME   ";1:text=" VIBRATO  ";2:text=" GLIDE    ";
                3:text=" NOTE     ";4:text=" VELOCITY ";default:text=" BEND     ";endcase
            row=(y-42)/2;draw=1;
        end else if(y>=74 && y<88 && tile<6)begin
            text={8'd32,8'(48+number/100),8'(48+(number/10)%10),8'(48+number%10),48'h202020202020};
            row=(y-74)/2;draw=1;active=1;
        end
        if(charpos<10)character=text[79-charpos*8 -:8];
        pixel=16'h1041;
        if(y<2 || y==126)pixel=16'h5628;
        if(local_x==0)pixel=16'h28c4;
        if(draw && ink)pixel=active?16'h67ee:16'had13;
        if(y>=104 && y<111 && tile<3 && local_x>=12 && local_x<108)
            pixel=(local_x-12)<(number*96/127)?16'h67ee:16'h28c4;
        if(grid && grid_ink)pixel=pads[(7-gy)*8+gx]?16'hffff:16'h5628;
    end
endmodule
