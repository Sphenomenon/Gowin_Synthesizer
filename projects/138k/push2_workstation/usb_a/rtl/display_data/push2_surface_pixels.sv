// 960x160 performance panel; snapshot at each frame boundary, no DDR wait.
module push2_surface_pixels #(parameter PIPELINED=0,SHOW_LAST_NOTE=1, parameter bit MEDIA_CONTROLS_ENABLE=1'b1,
    parameter bit CNN_DEMO_STATUS_ENABLE=1'b0)(input wire clk,rst,frame_ready,output wire frame_start,
    input wire [9:0] x,input wire [7:0] y,output wire pixel_valid,
    output wire [15:0] pixel,input wire [31:0] control,options,
    input wire [63:0] held,input wire [6:0] note,velocity,
    input wire [63:0] display_meta,input wire display_meta_valid,
    input wire [31:0] score_mask,input wire score_running,record_enabled,
    input wire guide_mode,guide_chosen,
    input wire [3:0] guide_browse,guide_track,
    input wire [4:0] guide_track_count,
    input wire [15:0] guide_score_count,guide_cursor,
    input wire guide_analysis_done,
    input wire name_write_valid,
    input wire [7:0] name_write_addr,name_write_data);
    reg [22:0] timer;
    reg [31:0] cs,op;reg [63:0] pads;reg [31:0] score_pads;
    reg score_on,record_on;reg [6:0] n,v;
    reg [2:0] display_effect_mask;reg display_meta_seen;
    // The host frame request is the commit point.  The local timer is kept as
    // a pacing counter for compatibility, but must not suppress a new
    // snapshot or the Push UI will stay on its first frame.
    assign frame_start=!rst && frame_ready;
    assign pixel_valid=!rst;
    always @(posedge clk or posedge rst)begin
        if(rst)begin timer<=0;cs<=0;op<=0;pads<=0;score_pads<=0;score_on<=0;record_on<=0;
            n<=60;v<=0;display_effect_mask<=0;display_meta_seen<=0;end
        else if(frame_start)begin
            timer<=23'd4999999;cs<=control;op<=options;pads<=held;score_pads<=score_mask;
            score_on<=score_running;record_on<=record_enabled;n<=note;v<=velocity;
            if(display_meta_valid)begin display_effect_mask<=display_meta[25:23];display_meta_seen<=1;end
        end
        else if(display_meta_valid)begin display_effect_mask<=display_meta[25:23];display_meta_seen<=1;end
        else if(timer!=0)timer<=timer-1'b1;
    end
    reg [3:0] tile;
    reg [6:0] local_x;
    // Exact bounded division by 120, including the unused x=960..1023 tail.
    // Independent constant subtractors avoid a divider feeding another divide.
    always @* begin
        tile=0;local_x=0;
        for(integer t=0;t<9;t=t+1)begin
            tile=tile | (x>=t*120 && x<(t+1)*120 ? 4'(t) : 4'd0);
            local_x=local_x | (x>=t*120 && x<(t+1)*120 ? 7'(x-t*120) : 7'd0);
        end
    end
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
    reg [15:0] background,background_q;
    reg [7:0] character_q;
    reg [2:0] row_q,col_q;
    reg draw_q,active_q,guide_mode_q;
    always @(posedge clk or posedge rst) begin
        if(rst) begin
            background_q<=16'h1041;character_q<=32;row_q<=0;col_q<=0;
            draw_q<=0;active_q<=0;guide_mode_q<=0;
        end else begin
            background_q<=background;character_q<=character;row_q<=row;col_q<=col;
            draw_q<=draw;active_q<=active;guide_mode_q<=guide_mode;
        end
    end
    wire ink;
    wire [15:0] song_pixel;
    wire show_text=(PIPELINED ? draw_q : draw) && ink;
    wire [15:0] base_pixel=show_text ? ((PIPELINED ? active_q : active) ? 16'h67ee : 16'had13) :
        (PIPELINED ? background_q : background);
    assign pixel=(PIPELINED ? guide_mode_q : guide_mode) ? song_pixel : base_pixel;
    video_font_5x7 font(.character(PIPELINED ? character_q : character),
        .column(PIPELINED ? col_q : col),.row(PIPELINED ? row_q : row),.ink(ink),.glyph());
    push2_song_screen #(.PIPELINED(PIPELINED),.CNN_DEMO_STATUS_ENABLE(CNN_DEMO_STATUS_ENABLE)) song_screen(.clk(clk),.rst(rst),
        .name_write_valid(name_write_valid),.name_write_addr(name_write_addr),
        .name_write_data(name_write_data),.chosen(guide_chosen),
        .browse_index(guide_browse),.track_index(guide_track),
        .track_count(guide_track_count),.score_count(guide_score_count),
        .cursor(guide_cursor),.analysis_done(guide_analysis_done),
        .cnn_status_i(display_meta[31:0]),
        .effect_mask(display_effect_mask),
        .x(x),.y(y),.pixel(song_pixel));
    // Use the existing USB-clock snapshot. The exact seven-bit lookup keeps
    // arithmetic away from the asynchronous held-data mailbox receiver.
    function automatic [6:0] knob_width(input [6:0] value);
        case(value)
            7'd0:knob_width=7'd0;
            7'd1:knob_width=7'd0;
            7'd2:knob_width=7'd1;
            7'd3:knob_width=7'd2;
            7'd4:knob_width=7'd3;
            7'd5:knob_width=7'd3;
            7'd6:knob_width=7'd4;
            7'd7:knob_width=7'd5;
            7'd8:knob_width=7'd6;
            7'd9:knob_width=7'd6;
            7'd10:knob_width=7'd7;
            7'd11:knob_width=7'd8;
            7'd12:knob_width=7'd9;
            7'd13:knob_width=7'd9;
            7'd14:knob_width=7'd10;
            7'd15:knob_width=7'd11;
            7'd16:knob_width=7'd12;
            7'd17:knob_width=7'd12;
            7'd18:knob_width=7'd13;
            7'd19:knob_width=7'd14;
            7'd20:knob_width=7'd15;
            7'd21:knob_width=7'd15;
            7'd22:knob_width=7'd16;
            7'd23:knob_width=7'd17;
            7'd24:knob_width=7'd18;
            7'd25:knob_width=7'd18;
            7'd26:knob_width=7'd19;
            7'd27:knob_width=7'd20;
            7'd28:knob_width=7'd21;
            7'd29:knob_width=7'd21;
            7'd30:knob_width=7'd22;
            7'd31:knob_width=7'd23;
            7'd32:knob_width=7'd24;
            7'd33:knob_width=7'd24;
            7'd34:knob_width=7'd25;
            7'd35:knob_width=7'd26;
            7'd36:knob_width=7'd27;
            7'd37:knob_width=7'd27;
            7'd38:knob_width=7'd28;
            7'd39:knob_width=7'd29;
            7'd40:knob_width=7'd30;
            7'd41:knob_width=7'd30;
            7'd42:knob_width=7'd31;
            7'd43:knob_width=7'd32;
            7'd44:knob_width=7'd33;
            7'd45:knob_width=7'd34;
            7'd46:knob_width=7'd34;
            7'd47:knob_width=7'd35;
            7'd48:knob_width=7'd36;
            7'd49:knob_width=7'd37;
            7'd50:knob_width=7'd37;
            7'd51:knob_width=7'd38;
            7'd52:knob_width=7'd39;
            7'd53:knob_width=7'd40;
            7'd54:knob_width=7'd40;
            7'd55:knob_width=7'd41;
            7'd56:knob_width=7'd42;
            7'd57:knob_width=7'd43;
            7'd58:knob_width=7'd43;
            7'd59:knob_width=7'd44;
            7'd60:knob_width=7'd45;
            7'd61:knob_width=7'd46;
            7'd62:knob_width=7'd46;
            7'd63:knob_width=7'd47;
            7'd64:knob_width=7'd48;
            7'd65:knob_width=7'd49;
            7'd66:knob_width=7'd49;
            7'd67:knob_width=7'd50;
            7'd68:knob_width=7'd51;
            7'd69:knob_width=7'd52;
            7'd70:knob_width=7'd52;
            7'd71:knob_width=7'd53;
            7'd72:knob_width=7'd54;
            7'd73:knob_width=7'd55;
            7'd74:knob_width=7'd55;
            7'd75:knob_width=7'd56;
            7'd76:knob_width=7'd57;
            7'd77:knob_width=7'd58;
            7'd78:knob_width=7'd58;
            7'd79:knob_width=7'd59;
            7'd80:knob_width=7'd60;
            7'd81:knob_width=7'd61;
            7'd82:knob_width=7'd61;
            7'd83:knob_width=7'd62;
            7'd84:knob_width=7'd63;
            7'd85:knob_width=7'd64;
            7'd86:knob_width=7'd65;
            7'd87:knob_width=7'd65;
            7'd88:knob_width=7'd66;
            7'd89:knob_width=7'd67;
            7'd90:knob_width=7'd68;
            7'd91:knob_width=7'd68;
            7'd92:knob_width=7'd69;
            7'd93:knob_width=7'd70;
            7'd94:knob_width=7'd71;
            7'd95:knob_width=7'd71;
            7'd96:knob_width=7'd72;
            7'd97:knob_width=7'd73;
            7'd98:knob_width=7'd74;
            7'd99:knob_width=7'd74;
            7'd100:knob_width=7'd75;
            7'd101:knob_width=7'd76;
            7'd102:knob_width=7'd77;
            7'd103:knob_width=7'd77;
            7'd104:knob_width=7'd78;
            7'd105:knob_width=7'd79;
            7'd106:knob_width=7'd80;
            7'd107:knob_width=7'd80;
            7'd108:knob_width=7'd81;
            7'd109:knob_width=7'd82;
            7'd110:knob_width=7'd83;
            7'd111:knob_width=7'd83;
            7'd112:knob_width=7'd84;
            7'd113:knob_width=7'd85;
            7'd114:knob_width=7'd86;
            7'd115:knob_width=7'd86;
            7'd116:knob_width=7'd87;
            7'd117:knob_width=7'd88;
            7'd118:knob_width=7'd89;
            7'd119:knob_width=7'd89;
            7'd120:knob_width=7'd90;
            7'd121:knob_width=7'd91;
            7'd122:knob_width=7'd92;
            7'd123:knob_width=7'd92;
            7'd124:knob_width=7'd93;
            7'd125:knob_width=7'd94;
            7'd126:knob_width=7'd95;
            7'd127:knob_width=7'd96;
            default:knob_width=0;
        endcase
    endfunction
    wire [6:0] bar_width[0:2];
    assign bar_width[0]=knob_width(cs[30:24]);
    assign bar_width[1]=knob_width(op[10:4]);
    assign bar_width[2]=knob_width(op[17:11]);
    wire bar_fill=(tile==0 && local_x<12+bar_width[0]) ||
                  (tile==1 && local_x<12+bar_width[1]) ||
                  (tile==2 && local_x<12+bar_width[2]);
    reg [3:0] gx,gy;
    reg grid_x_ink,grid_y_ink;
    wire grid=x>=736 && x<944 && y>=40 && y<120;
    wire grid_ink=grid_x_ink && grid_y_ink;
    // Eight fixed cells: compare bounded coordinates, avoiding 32-bit div/mod.
    always @* begin
        gx=0;gy=0;grid_x_ink=0;grid_y_ink=0;
        for(integer cell_index=0;cell_index<8;cell_index=cell_index+1) begin
            if(x>=736+cell_index*26 && x<736+(cell_index+1)*26) begin
                gx=4'(cell_index);grid_x_ink=x<736+cell_index*26+22;
            end
            if(y>=40+cell_index*10 && y<40+(cell_index+1)*10) begin
                gy=4'(cell_index);grid_y_ink=y<40+cell_index*10+7;
            end
        end
    end
    always @* begin
        character=32;row=0;number=0;text="          ";active=0;draw=0;
        case(tile)0:number=cs[30:24];1:number={1'b0,op[10:4]};2:number={1'b0,op[17:11]};
            3:number={1'b0,n};4:number={1'b0,v};default:number=op[25:18];endcase
        if(y>=8 && y<22)begin
            text=top_label(tile);row=(y-8)/2;draw=1;
            active=tile<3?cs[4:3]==tile:cs[9:7]==tile-3;
        end else if(y>=26 && y<40 && tile<5)begin
            case(tile)0:text=" SCORE    ";1:text=" RECORD   ";2:text=" FX MASTER";
                3:text=" MODE <   ";default:text=" MODE >   ";endcase
            row=(y-26)/2;draw=1;
            active=tile==0?score_on:tile==1?record_on:tile==2?(|cs[2:0]):1'b1;
            if(!MEDIA_CONTROLS_ENABLE && tile<2)begin text="          ";draw=0;active=0;end
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
        background=16'h1041;
        if(y<2 || y==126)background=16'h5628;
        if(local_x==0)background=16'h28c4;
        if(y>=104 && y<111 && tile<3 && local_x>=12 && local_x<108)begin
            background=bar_fill?16'h67ee:16'h28c4;draw=0;end
        if(grid && grid_ink)begin
            draw=0;
            if(pads[(7-gy)*8+gx])background=16'hffff;
            else if(score_on && gy>=4 && score_pads[(7-gy)*8+gx])background=16'h67ee;
            else background=16'h5628;
        end
        if(!SHOW_LAST_NOTE && tile>=3 && tile<=4 && y>=42 && y<88)draw=0;
    end
endmodule
