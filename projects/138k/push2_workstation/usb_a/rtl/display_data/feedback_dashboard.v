`default_nettype none

// Four-stage, clock-enabled 1920x1080 dashboard. wave_sample is the captured sample at
// max(0, (pixel_x-64)/2), read synchronously alongside the pixel coordinates.
// No trace, meter, status lamp or counter is generated from animation time.
module feedback_dashboard #(parameter integer ENABLE_ANALYSIS=0, parameter integer HMI_D_ONLY=0) (
    input wire clk,
    input wire reset_n,
    input wire enable,
    input wire frame_start,
    input wire [10:0] pixel_x,
    input wire [10:0] pixel_y,
    input wire [31:0] wave_sample,
    input wire [31:0] wave_previous,
    input wire waveform_held,
    input wire [7:0] spectrum_left,spectrum_right,
    input wire image_hit,
    input wire [15:0] peak_left,peak_right,
    input wire [2:0] image_gain,
    input wire [31:0] analysis_sequence,analysis_skipped,
    input wire [31:0] peak_data,
    input wire [31:0] active_voices,
    input wire [31:0] status_data,
    input wire [128:0] applied_parameters,
    input wire [2:0] effect_mask,
    input wire [5:0] effect_order,
    input wire [31:0] sequence_data,
    input wire [31:0] skipped_data,
    input wire [31:0] memory_status,
    input wire [31:0] underruns,
    input wire [31:0] framecount,
    output reg [31:0] pixel_data
);
    localparam [255:0] TITLE = "FPGA SYNTH                      ";
    localparam [255:0] RATE = "1920 X 1080 / 60 HZ             ";
    localparam [255:0] WAVE = "OUTPUT WAVEFORM                 ";
    localparam [255:0] WINDOW = "512 SAMPLES / 10 MS / Q1 31     ";
    localparam [255:0] LEVEL = "OUTPUT PEAK                     ";
    localparam [255:0] SOURCE = "48000 HZ / HEADPHONE            ";
    localparam [255:0] DDR = "DDR FRAMEBUFFER                 ";
    localparam [255:0] VOICES = "32 VOICES / ACTIVE AND RELEASE  ";
    localparam [255:0] EFFECT_TITLE = "APPLIED EFFECT CHAIN            ";
    localparam [255:0] FOOTER = "LIVE AUDIO / PUSH OR 25K        ";
    // These are frame-frozen read-only projections of the audio owner.
    // No command/request state is inferred from the health/status counters.
    wire [31:0] applied_state=applied_parameters[95:64];
    wire [31:0] applied_options=applied_parameters[31:0];
    wire [6:0] applied_volume=applied_state[31:16]>=16'd32768 ? 7'd127 : applied_state[30:24];
    function automatic [23:0] decimal3(input [6:0] value);
        reg [6:0] remainder;
        reg [3:0] tens;
        begin
            // Exact 7-bit binary-to-text lookup keeps the HMI critical path
            // out of a priority comparator, DSP multiply and final subtraction.
            // The complete binary case has no storage or pipeline latency.
            case (value)
                7'd0: decimal3="000";
                7'd1: decimal3="001";
                7'd2: decimal3="002";
                7'd3: decimal3="003";
                7'd4: decimal3="004";
                7'd5: decimal3="005";
                7'd6: decimal3="006";
                7'd7: decimal3="007";
                7'd8: decimal3="008";
                7'd9: decimal3="009";
                7'd10: decimal3="010";
                7'd11: decimal3="011";
                7'd12: decimal3="012";
                7'd13: decimal3="013";
                7'd14: decimal3="014";
                7'd15: decimal3="015";
                7'd16: decimal3="016";
                7'd17: decimal3="017";
                7'd18: decimal3="018";
                7'd19: decimal3="019";
                7'd20: decimal3="020";
                7'd21: decimal3="021";
                7'd22: decimal3="022";
                7'd23: decimal3="023";
                7'd24: decimal3="024";
                7'd25: decimal3="025";
                7'd26: decimal3="026";
                7'd27: decimal3="027";
                7'd28: decimal3="028";
                7'd29: decimal3="029";
                7'd30: decimal3="030";
                7'd31: decimal3="031";
                7'd32: decimal3="032";
                7'd33: decimal3="033";
                7'd34: decimal3="034";
                7'd35: decimal3="035";
                7'd36: decimal3="036";
                7'd37: decimal3="037";
                7'd38: decimal3="038";
                7'd39: decimal3="039";
                7'd40: decimal3="040";
                7'd41: decimal3="041";
                7'd42: decimal3="042";
                7'd43: decimal3="043";
                7'd44: decimal3="044";
                7'd45: decimal3="045";
                7'd46: decimal3="046";
                7'd47: decimal3="047";
                7'd48: decimal3="048";
                7'd49: decimal3="049";
                7'd50: decimal3="050";
                7'd51: decimal3="051";
                7'd52: decimal3="052";
                7'd53: decimal3="053";
                7'd54: decimal3="054";
                7'd55: decimal3="055";
                7'd56: decimal3="056";
                7'd57: decimal3="057";
                7'd58: decimal3="058";
                7'd59: decimal3="059";
                7'd60: decimal3="060";
                7'd61: decimal3="061";
                7'd62: decimal3="062";
                7'd63: decimal3="063";
                7'd64: decimal3="064";
                7'd65: decimal3="065";
                7'd66: decimal3="066";
                7'd67: decimal3="067";
                7'd68: decimal3="068";
                7'd69: decimal3="069";
                7'd70: decimal3="070";
                7'd71: decimal3="071";
                7'd72: decimal3="072";
                7'd73: decimal3="073";
                7'd74: decimal3="074";
                7'd75: decimal3="075";
                7'd76: decimal3="076";
                7'd77: decimal3="077";
                7'd78: decimal3="078";
                7'd79: decimal3="079";
                7'd80: decimal3="080";
                7'd81: decimal3="081";
                7'd82: decimal3="082";
                7'd83: decimal3="083";
                7'd84: decimal3="084";
                7'd85: decimal3="085";
                7'd86: decimal3="086";
                7'd87: decimal3="087";
                7'd88: decimal3="088";
                7'd89: decimal3="089";
                7'd90: decimal3="090";
                7'd91: decimal3="091";
                7'd92: decimal3="092";
                7'd93: decimal3="093";
                7'd94: decimal3="094";
                7'd95: decimal3="095";
                7'd96: decimal3="096";
                7'd97: decimal3="097";
                7'd98: decimal3="098";
                7'd99: decimal3="099";
                7'd100: decimal3="100";
                7'd101: decimal3="101";
                7'd102: decimal3="102";
                7'd103: decimal3="103";
                7'd104: decimal3="104";
                7'd105: decimal3="105";
                7'd106: decimal3="106";
                7'd107: decimal3="107";
                7'd108: decimal3="108";
                7'd109: decimal3="109";
                7'd110: decimal3="110";
                7'd111: decimal3="111";
                7'd112: decimal3="112";
                7'd113: decimal3="113";
                7'd114: decimal3="114";
                7'd115: decimal3="115";
                7'd116: decimal3="116";
                7'd117: decimal3="117";
                7'd118: decimal3="118";
                7'd119: decimal3="119";
                7'd120: decimal3="120";
                7'd121: decimal3="121";
                7'd122: decimal3="122";
                7'd123: decimal3="123";
                7'd124: decimal3="124";
                7'd125: decimal3="125";
                7'd126: decimal3="126";
                7'd127: decimal3="127";
                default: begin
                    // Preserve the prior four-state result for X/Z inputs.
                    remainder=value>=100 ? value-7'd100 : value;
                    tens=remainder>=90 ? 9 : remainder>=80 ? 8 : remainder>=70 ? 7 :
                        remainder>=60 ? 6 : remainder>=50 ? 5 : remainder>=40 ? 4 :
                        remainder>=30 ? 3 : remainder>=20 ? 2 : remainder>=10 ? 1 : 0;
                    remainder=remainder-{3'd0,tens}*7'd10;
                    decimal3={value>=100 ? 8'h31 : 8'h30,8'h30+{4'd0,tens},8'h30+{1'd0,remainder}};
                end
            endcase
        end
    endfunction
    wire [255:0] applied_source=(HMI_D_ONLY!=0) ? "SOURCE   D / BLUETOOTH STREAM   " :
        applied_parameters[104] ? "SOURCE   VECTOR / LIVE MIDI     " :
        applied_state[4:3]==0 ? "SOURCE   A / LIVE MIDI          " :
        applied_state[4:3]==1 ? "SOURCE   B / LIVE MIDI          " : "SOURCE   C / LIVE MIDI          ";
    wire [23:0] brand_rgb;
    wire brand_hit;
    // One enabled ROM cycle coincides with stage A below.
    workstation_contest_brand brand(.clk(clk),.enable(enable),.pixel_x(pixel_x),.pixel_y(pixel_y),
        .hit(brand_hit),.pixel_rgb(brand_rgb));
    reg [255:0] text_line;
    // Coordinates belong to effect identities, not to numbered slots. Move
    // once per rendered frame; DDR stalls cannot accelerate the animation.
    reg [10:0] effect_x0, effect_x1, effect_x2;
    reg [2:0] visible_mask;
    reg [1:0] front_effect;
    function [10:0] destination(input [1:0] id);
        begin
            if (!effect_mask[id]) destination=11'd1120;
            else if (effect_order[1:0]==id) destination=11'd64;
            else if (effect_order[3:2]==id) destination=11'd400;
            else if (effect_order[5:4]==id) destination=11'd736;
            else destination=11'd1120;
        end
    endfunction
    function [10:0] slide(input [10:0] position, target);
        reg [10:0] distance, step;
        begin
            distance=position<target ? target-position : position-target;
            step=(distance+11'd3)>>2;
            if(step>32) step=11'd32;
            slide=position<target ? position+step : position-step;
        end
    endfunction
    wire dash_select_0_0=(effect_mask[0]) && (effect_order[1:0]==2'd0);
    wire dash_select_0_1=(effect_mask[0] && !(effect_order[1:0]==2'd0)) && (effect_order[3:2]==2'd0);
    wire dash_select_0_2=(effect_mask[0] && !(effect_order[1:0]==2'd0) && !(effect_order[3:2]==2'd0)) && (effect_order[5:4]==2'd0);
    wire dash_select_0_3=!effect_mask[0] || (effect_mask[0] && !(effect_order[1:0]==2'd0) && !(effect_order[3:2]==2'd0) && !(effect_order[5:4]==2'd0));
    wire [10:0] dash_next_0=({11{dash_select_0_0}} & slide(effect_x0,11'd64)) | ({11{dash_select_0_1}} & slide(effect_x0,11'd400)) | ({11{dash_select_0_2}} & slide(effect_x0,11'd736)) | ({11{dash_select_0_3}} & slide(effect_x0,11'd1120));
    wire dash_select_1_0=(effect_mask[1]) && (effect_order[1:0]==2'd1);
    wire dash_select_1_1=(effect_mask[1] && !(effect_order[1:0]==2'd1)) && (effect_order[3:2]==2'd1);
    wire dash_select_1_2=(effect_mask[1] && !(effect_order[1:0]==2'd1) && !(effect_order[3:2]==2'd1)) && (effect_order[5:4]==2'd1);
    wire dash_select_1_3=!effect_mask[1] || (effect_mask[1] && !(effect_order[1:0]==2'd1) && !(effect_order[3:2]==2'd1) && !(effect_order[5:4]==2'd1));
    wire [10:0] dash_next_1=({11{dash_select_1_0}} & slide(effect_x1,11'd64)) | ({11{dash_select_1_1}} & slide(effect_x1,11'd400)) | ({11{dash_select_1_2}} & slide(effect_x1,11'd736)) | ({11{dash_select_1_3}} & slide(effect_x1,11'd1120));
    wire dash_select_2_0=(effect_mask[2]) && (effect_order[1:0]==2'd2);
    wire dash_select_2_1=(effect_mask[2] && !(effect_order[1:0]==2'd2)) && (effect_order[3:2]==2'd2);
    wire dash_select_2_2=(effect_mask[2] && !(effect_order[1:0]==2'd2) && !(effect_order[3:2]==2'd2)) && (effect_order[5:4]==2'd2);
    wire dash_select_2_3=!effect_mask[2] || (effect_mask[2] && !(effect_order[1:0]==2'd2) && !(effect_order[3:2]==2'd2) && !(effect_order[5:4]==2'd2));
    wire [10:0] dash_next_2=({11{dash_select_2_0}} & slide(effect_x2,11'd64)) | ({11{dash_select_2_1}} & slide(effect_x2,11'd400)) | ({11{dash_select_2_2}} & slide(effect_x2,11'd736)) | ({11{dash_select_2_3}} & slide(effect_x2,11'd1120));
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            effect_x0<=11'd1120; effect_x1<=11'd1120; effect_x2<=11'd1120;
            visible_mask<=0; front_effect<=0;
        end else if (frame_start) begin
            effect_x0<=dash_next_0;
            effect_x1<=dash_next_1;
            effect_x2<=dash_next_2;
            visible_mask<=effect_mask;
            if(effect_mask[0] && !visible_mask[0]) front_effect<=0;
            else if(effect_mask[1] && !visible_mask[1]) front_effect<=1;
            else if(effect_mask[2] && !visible_mask[2]) front_effect<=2;
        end
    end
    wire [10:0] effect_rel0=pixel_x-effect_x0;
    wire [10:0] effect_rel1=pixel_x-effect_x1;
    wire [10:0] effect_rel2=pixel_x-effect_x2;
    wire effect_band=pixel_x>=64 && pixel_x<1088 && pixel_y>=872 && pixel_y<960;
    wire hit0=effect_band && effect_rel0<288;
    wire hit1=effect_band && effect_rel1<288;
    wire hit2=effect_band && effect_rel2<288;
    reg effect_hit;
    reg [1:0] effect_id;
    reg [10:0] effect_relative;
    always @* begin
        effect_hit=hit0 || hit1 || hit2;
        effect_id=0; effect_relative=effect_rel0;
        if(hit1) begin effect_id=1; effect_relative=effect_rel1; end
        if(hit2) begin effect_id=2; effect_relative=effect_rel2; end
        // A newly selected card crosses in front; text and fill use the same
        // hit so another card's label cannot shine through its background.
        if(front_effect==0 && hit0) begin effect_id=0; effect_relative=effect_rel0; end
        if(front_effect==1 && hit1) begin effect_id=1; effect_relative=effect_rel1; end
        if(front_effect==2 && hit2) begin effect_id=2; effect_relative=effect_rel2; end
    end
    reg a_effect_hit,a_effect_edge,a_effect_on;
    reg a_effect_label,a_effect_status;
    reg [1:0] a_effect_id;
    reg [10:0] text_x, text_y;
    reg text_enable, large_text;
    reg [31:0] hex_word;
    reg hex_enable, voice_enable;
    reg [7:0] voice_character;
    reg [10:0] hex_x;
    wire [10:0] relative_text_x = effect_hit ? effect_relative-11'd16 : pixel_x-text_x;
    wire [10:0] relative_text_y = pixel_y - text_y;
    wire title_large=pixel_y>=48 && pixel_y<80 && pixel_x>=64 && pixel_x<1088;
    wire [4:0] text_index = title_large ? relative_text_x[9:5] : relative_text_x[8:4];
    wire [2:0] font_column = title_large ? relative_text_x[4:2] : relative_text_x[3:1];
    // Every enabled label has a fixed vertical origin. Compute the row
    // from raster bands directly, independent of horizontal/card hit priority.
    wire font_origin8=(pixel_y>=168 && pixel_y<184) ||
        (pixel_y>=840 && pixel_y<856) || (pixel_y>=888 && pixel_y<904) ||
        (pixel_y>=920 && pixel_y<936) || (pixel_y>=968 && pixel_y<984) ||
        (ENABLE_ANALYSIS && ((pixel_y>=200 && pixel_y<216) ||
          (pixel_x>=8 && pixel_x<56 && ((pixel_y>=568 && pixel_y<584) ||
           (pixel_y>=632 && pixel_y<648) || (pixel_y>=696 && pixel_y<712) ||
           (pixel_y>=760 && pixel_y<776)))));
    wire [3:0] font_origin=font_origin8 ? 4'd8 :
        (ENABLE_ANALYSIS && pixel_x<1104 && pixel_y>=804 && pixel_y<820 ? 4'd4 : 4'd0);
    wire [3:0] font_small_relative=pixel_y[3:0]-font_origin;
    wire parameter_table=pixel_x>=1248 && pixel_x<1760 && pixel_y>=864 && pixel_y<1040;
    wire [2:0] font_row=parameter_table ? pixel_y[3:1] : title_large ? pixel_y[4:2]^3'd4 : font_small_relative[3:1];
    // Freeze display-only power-of-two gain at raster start; keep the same
    // gain while the matcher holds the preceding waveform. Never changes PCM.
    reg [2:0] wave_gain,computed_wave_gain;
    integer gain_bit;
    always @* begin
        computed_wave_gain=0;
        for(gain_bit=0;gain_bit<6;gain_bit=gain_bit+1)
            if(peak_data!=0 && peak_data<(32'h40000000>>gain_bit))computed_wave_gain=gain_bit+1;
    end
    always @(posedge clk or negedge reset_n)
        if(!reset_n)wave_gain<=0;
        else if(enable && pixel_x<2 && pixel_y==0 && !waveform_held)
            wave_gain<=ENABLE_ANALYSIS ? computed_wave_gain : 0;
    wire [4:0] wave_shift=ENABLE_ANALYSIS ? 5'd24-{2'd0,wave_gain} : 5'd23;
    wire signed [31:0] scaled_sample=$signed(wave_sample)>>>wave_shift;
    wire signed [31:0] scaled_previous=$signed(wave_previous)>>>wave_shift;
    wire signed [9:0] sample_height=ENABLE_ANALYSIS ?
        (scaled_sample>127 ? 10'sd127 : scaled_sample < -127 ? -10'sd127 : scaled_sample[9:0]) : scaled_sample[9:0];
    wire signed [9:0] previous_height=ENABLE_ANALYSIS ?
        (scaled_previous>127 ? 10'sd127 : scaled_previous < -127 ? -10'sd127 : scaled_previous[9:0]) : scaled_previous[9:0];
    wire signed [11:0] sample_extended = {{2{sample_height[9]}}, sample_height};
    wire signed [11:0] previous_extended = {{2{previous_height[9]}}, previous_height};
    function automatic [255:0] effect_name(input [1:0] id);
        begin case(id)
            2'd0: effect_name="DELAY                           ";
            2'd1: effect_name="CHORUS                          ";
            default: effect_name="REVERB                          ";
        endcase end
    endfunction
    wire [10:0] card_relative = pixel_x - 11'd64;
    // Two rows of sixteen 64-pixel slots share the waveform's 1024-pixel
    // width. Fixed bit slices avoid division/multiplication in tile lookup.
    wire voice_row = pixel_y >= 11'd928;
    wire [4:0] voice_index = {voice_row,card_relative[9:6]};
    wire [5:0] voice_number = {1'b0,voice_index} + 6'd1;
    wire [3:0] voice_tens = voice_number >= 30 ? 4'd3 :
                           voice_number >= 20 ? 4'd2 :
                           voice_number >= 10 ? 4'd1 : 4'd0;
    wire [5:0] voice_ones = voice_number >= 30 ? voice_number - 6'd30 :
                          voice_number >= 20 ? voice_number - 6'd20 :
                          voice_number >= 10 ? voice_number - 6'd10 : voice_number;
    wire [10:0] card_y = pixel_y - (voice_row ? 11'd928 : 11'd880);

    // Stage A breaks the measured 29-primitive output_y -> text origin ->
    // character -> glyph -> pixel path at the font address. All stages share
    // enable, so the complete raster pipeline stops without data movement.
    reg [255:0] a_text_line;
    reg [4:0] a_text_index;
    reg [2:0] a_font_column, a_font_row;
    reg a_text_enable, a_hex_enable, a_voice_enable;
    reg [31:0] a_hex_word;
    reg [2:0] a_hex_index;
    reg [7:0] a_voice_character;
    reg [10:0] a_x, a_y, a_level_width;
    // Coordinate-only decisions share the existing A capture edge. The B
    // color priority now consumes one-bit predicates instead of repeated
    // subtract/compare chains; pipeline length and enable stalls stay fixed.
    reg a_header,a_separator,a_wave_box,a_wave_grid,a_wave_center,a_level_box,a_level_red,a_level_orange,a_memory_box,a_analysis_wave_box,a_analysis_wave_grid,a_analysis_wave_center,a_spectrum_box,a_spectrum_grid,a_spectrum_even,a_xy_box,a_xy_grid,a_xy_axis,a_left_box,a_right_box,a_card_band,a_card_box,a_card_edge,a_arrow_shaft,a_arrow_head,a_status_box,a_status_grid;
    reg a_voice_active;
    reg [7:0] a_spectrum_left,a_spectrum_right;
    reg a_image_hit;
    reg [9:0] a_left_width,a_right_width;
    wire [10:0] input_image_x=pixel_x-11'd1248, input_image_y=pixel_y-11'd224;
    wire [10:0] full_distance_x=input_image_x>=11'd256 ? input_image_x-11'd256 : 11'd256-input_image_x;
    wire [10:0] full_distance_y=input_image_y>=11'd256 ? input_image_y-11'd256 : 11'd256-input_image_y;
    // Only used inside the 512x512 plot, where each distance is 0..256.
    wire [8:0] distance_x=full_distance_x[8:0], distance_y=full_distance_y[8:0];
    wire [9:0] diamond_distance={1'b0,distance_x}+{1'b0,distance_y};
    wire spectrum_l_ink=a_spectrum_left!=0 && a_y>=11'd792-{3'd0,a_spectrum_left};
    wire spectrum_r_ink=a_spectrum_right!=0 && a_y>=11'd792-{3'd0,a_spectrum_right};
    reg [2:0] a_memory_status;
    reg signed [11:0] a_sample_top, a_sample_bottom;
    reg signed [11:0] a_previous_top, a_previous_bottom;
    wire [10:0] a_card_relative = a_x - 11'd64;
    wire [10:0] a_level_x = a_x - 11'd1216;
    wire signed [11:0] a_signed_y = $signed({1'b0,a_y});
    wire trace_ink = ((a_signed_y >= a_sample_top && a_signed_y <= a_previous_bottom) ||
                      (a_signed_y >= a_previous_top && a_signed_y <= a_sample_bottom));

    // Stage B isolates the dynamic 32-character/hex selection from the glyph
    // lookup. Trace comparisons are only 12 bits; no unsized 32-bit arithmetic.
    reg [7:0] next_character;
    reg [3:0] next_hex_digit;
    reg [31:0] next_background;
    reg [7:0] b_character;
    reg [2:0] b_font_column, b_font_row;
    reg b_text_enable;
    reg [31:0] b_background;
    // Stage C registers the complete shared bitmap. Fixed row slices and a
    // five-way column case in stage D avoid the old (6-row)*5 DSP/ALU path.
    wire [34:0] decoded_glyph;
    reg [34:0] c_glyph;
    reg [2:0] c_font_column, c_font_row;
    reg c_text_enable;
    reg [31:0] c_background;
    reg [4:0] selected_row;
    reg font_ink;
    video_font_5x7 u_font(.character(b_character), .column(3'd0), .row(3'd0), .ink(), .glyph(decoded_glyph));
    always @* begin
        case(c_font_row)
            3'd0: selected_row=c_glyph[34:30];
            3'd1: selected_row=c_glyph[29:25];
            3'd2: selected_row=c_glyph[24:20];
            3'd3: selected_row=c_glyph[19:15];
            3'd4: selected_row=c_glyph[14:10];
            3'd5: selected_row=c_glyph[9:5];
            3'd6: selected_row=c_glyph[4:0];
            default: selected_row=5'd0;
        endcase
        case(c_font_column)
            3'd0: font_ink=selected_row[4];
            3'd1: font_ink=selected_row[3];
            3'd2: font_ink=selected_row[2];
            3'd3: font_ink=selected_row[1];
            3'd4: font_ink=selected_row[0];
            default: font_ink=1'b0;
        endcase
    end

    always @* begin
        text_line = 0; text_x = 64; text_y = 0;
        text_enable = 0; large_text = 0;
        hex_word = 0; hex_enable = 0; hex_x = 0; voice_enable = 0; voice_character = 0;
        if (1'b0 && pixel_y >= 48 && pixel_y < 80 && pixel_x >= 64 && pixel_x < 1088) begin
            text_line = TITLE; text_y = 48; text_enable = 1; large_text = 1;
        end else if (1'b0 && pixel_y >= 64 && pixel_y < 80 && pixel_x >= 1216 && pixel_x < 1728) begin
            text_line = RATE; text_x = 1216; text_y = 64; text_enable = 1;
        end else if (pixel_y >= 168 && pixel_y < 184 && pixel_x >= 64 && pixel_x < 576) begin
            text_line = WAVE; text_y = 168; text_enable = 1;
        end else if (pixel_y >= 768 && pixel_y < 784 && pixel_x >= 64 && pixel_x < 576) begin
            text_line = WINDOW; text_y = 768; text_enable = 1;
        end else if (pixel_y >= 768 && pixel_y < 784 && pixel_x >= 640 && pixel_x < 1152) begin
            text_line = waveform_held ? "HOLD / WAITING FOR MATCH        " : "TRIGGERED                       ";
            text_x = 640; text_y = 768; text_enable = 1;
        end else if (pixel_y >= 168 && pixel_y < 184 && pixel_x >= 1216 && pixel_x < 1728) begin
            text_line = LEVEL; text_x = 1216; text_y = 168; text_enable = 1;
        end else if (pixel_y >= 352 && pixel_y < 368 && pixel_x >= 1216 && pixel_x < 1728) begin
            text_line = SOURCE; text_x = 1216; text_y = 352; text_enable = 1;
        end else if (pixel_y >= 432 && pixel_y < 448 && pixel_x >= 1216 && pixel_x < 1728) begin
            text_line = DDR; text_x = 1216; text_y = 432; text_enable = 1;
        end else if (pixel_y >= 840 && pixel_y < 856 && pixel_x >= 64 && pixel_x < 576) begin
            text_line = VOICES; text_y = 840; text_enable = 1;
        end else if (pixel_y >= 1024 && pixel_y < 1040 && pixel_x >= 64 && pixel_x < 576) begin
            text_line = FOOTER; text_y = 1024; text_enable = 1;
        end
        if(ENABLE_ANALYSIS) begin
            text_line=0; text_x=64; text_y=0; text_enable=0; large_text=0; hex_enable=0;
            if(1'b0 && pixel_y>=48 && pixel_y<80 && pixel_x>=64 && pixel_x<1088) begin
                text_line=TITLE;text_y=48;text_enable=1;large_text=1;
            end else if(1'b0 && pixel_y>=64 && pixel_y<80 && pixel_x>=1216 && pixel_x<1728) begin
                text_line=RATE;text_x=1216;text_y=64;text_enable=1;
            end else if(pixel_y>=168 && pixel_y<184) begin
                if(pixel_x>=64 && pixel_x<576) begin
                    case(wave_gain)
                        0:text_line="MID WAVEFORM / AUTO X1          ";
                        1:text_line="MID WAVEFORM / AUTO X2          ";
                        2:text_line="MID WAVEFORM / AUTO X4          ";
                        3:text_line="MID WAVEFORM / AUTO X8          ";
                        4:text_line="MID WAVEFORM / AUTO X16         ";
                        5:text_line="MID WAVEFORM / AUTO X32         ";
                        default:text_line="MID WAVEFORM / AUTO X64         ";
                    endcase
                    text_y=168;text_enable=1;
                end
                if(pixel_x>=1248 && pixel_x<1760) begin text_line="STEREO IMAGE / FINAL DAC PCM    ";text_x=1248;text_y=168;text_enable=1;end
            end else if(pixel_y>=200 && pixel_y<216) begin
                text_y=200;
                if(pixel_x>=1280 && pixel_x<1312) begin text_line="L                               ";text_x=1280;text_enable=1;end
                if(pixel_x>=1472 && pixel_x<1536) begin text_line="MONO                            ";text_x=1472;text_enable=1;end
                if(pixel_x>=1712 && pixel_x<1744) begin text_line="R                               ";text_x=1712;text_enable=1;end
            end else if(pixel_y>=480 && pixel_y<496 && pixel_x<1152) begin
                text_y=480;
                if(pixel_x>=64 && pixel_x<576) begin text_line=applied_parameters[128] ? "512 SAMPLES / 11.61 MS          " : "512 SAMPLES / 10.67 MS          ";text_enable=1;end
                if(pixel_x>=640) begin text_line=waveform_held ? "HOLD / WAITING FOR MATCH        " : "TRIGGERED                       ";text_x=640;text_enable=1;end
            end else if(pixel_y>=528 && pixel_y<544) begin
                text_y=528;
                if(pixel_x>=64 && pixel_x<576) begin text_line="FFT / 2048 HANN / DBFS          ";text_enable=1;end
                if(pixel_x>=640 && pixel_x<1152) begin text_line="L BLUE / R ORANGE               ";text_x=640;text_enable=1;end
            end else if(pixel_y>=568 && pixel_y<776 && pixel_x>=8 && pixel_x<56) begin
                text_x=8;
                if(pixel_y>=568 && pixel_y<584) begin text_line="0                               ";text_y=568;text_enable=1;end
                if(pixel_y>=632 && pixel_y<648) begin text_line="-24                             ";text_y=632;text_enable=1;end
                if(pixel_y>=696 && pixel_y<712) begin text_line="-48                             ";text_y=696;text_enable=1;end
                if(pixel_y>=760 && pixel_y<776) begin text_line="-72                             ";text_y=760;text_enable=1;end
            end else if(pixel_y>=752 && pixel_y<768 && pixel_x>=1248 && pixel_x<1760) begin
                text_x=1248;text_y=752;text_enable=1;
                case(image_gain)
                    0:text_line="AUTO X1 / MID-SIDE              ";
                    1:text_line="AUTO X2 / MID-SIDE              ";
                    2:text_line="AUTO X4 / MID-SIDE              ";
                    3:text_line="AUTO X8 / MID-SIDE              ";
                    4:text_line="AUTO X16 / MID-SIDE             ";
                    5:text_line="AUTO X32 / MID-SIDE             ";
                    6:text_line="AUTO X64 / MID-SIDE             ";
                    7:text_line="AUTO X128 / MID-SIDE            ";
                endcase
            end else if(pixel_y>=804 && pixel_y<820 && pixel_x<1104) begin
                text_y=804;
                if(pixel_x>=64 && pixel_x<96) begin text_line=applied_parameters[128] ? "44                              " : "48                              ";text_x=64;text_enable=1;end
                if(pixel_x>=282 && pixel_x<330) begin text_line=applied_parameters[128] ? "184                             " : "200                             ";text_x=282;text_enable=1;end
                if(pixel_x>=562 && pixel_x<626) begin text_line=applied_parameters[128] ? "0.9K                            " : "1K                              ";text_x=562;text_enable=1;end
                if(pixel_x>=834 && pixel_x<898) begin text_line=applied_parameters[128] ? "4.6K                            " : "5K                              ";text_x=834;text_enable=1;end
                if(pixel_x>=1040 && pixel_x<1104) begin text_line=applied_parameters[128] ? "18K                             " : "20K                             ";text_x=1040;text_enable=1;end
            end else if(pixel_x>=1216 && pixel_x<1248 && pixel_y>=784 && pixel_y<832) begin
                text_x=1216;
                if(pixel_y<800) begin text_line="L                               ";text_y=784;text_enable=1;end
                if(pixel_y>=816) begin text_line="R                               ";text_y=816;text_enable=1;end
            end else if(pixel_y>=840 && pixel_y<856 && pixel_x>=64 && pixel_x<576) begin
                text_line=EFFECT_TITLE;text_x=64;text_y=840;text_enable=1;
            end
        end
        // Static numbered positions remain left-to-right 1, 2, 3. Effects
        // entering/leaving the queue slide between these positions and the
        // clipped right-hand parking position, carrying their labels.
        if(pixel_y>=888 && pixel_y<904) begin
            if(pixel_x>=80 && pixel_x<352) begin text_line="EMPTY                           ";text_x=80;text_y=888;text_enable=1;end
            if(pixel_x>=416 && pixel_x<688) begin text_line="EMPTY                           ";text_x=416;text_y=888;text_enable=1;end
            if(pixel_x>=752 && pixel_x<1024) begin text_line="EMPTY                           ";text_x=752;text_y=888;text_enable=1;end
        end
        if(pixel_y>=968 && pixel_y<984) begin
            text_y=968;
            if(pixel_x>=200 && pixel_x<216) begin text_line="1                               ";text_x=200;text_enable=1;end
            if(pixel_x>=536 && pixel_x<552) begin text_line="2                               ";text_x=536;text_enable=1;end
            if(pixel_x>=872 && pixel_x<888) begin text_line="3                               ";text_x=872;text_enable=1;end
        end
        if(effect_hit) begin
            text_enable=0; hex_enable=0; voice_enable=0; large_text=0;
            if(effect_relative>=16 && effect_relative<272) begin
                if(pixel_y>=888 && pixel_y<904) begin
                    text_y=888;text_enable=1;
                end
                if(pixel_y>=920 && pixel_y<936) begin

                    text_y=920;text_enable=1;
                end
            end
        end
        // Compact HMI parameter table, from the applied frame snapshot.
        if(pixel_x>=1248 && pixel_x<1760 && pixel_y>=864 && pixel_y<1040) begin
            text_x=1248;text_y={pixel_y[10:5],5'd0};text_enable=pixel_y[4:0]<16;
            hex_enable=0;voice_enable=0;large_text=0;
            case(pixel_y[7:5])
                3: text_line=applied_source; // 864
                4: text_line={"MASTER ",decimal3(applied_volume)," / VOICES ",decimal3({1'b0,applied_state[15:10]}),"         "};
                5: begin // 928: the committed Q20 pitch ratio, in exact hex units
                    text_line="PITCH Q20                       ";
                    if(pixel_x>=1440 && pixel_x<1568) begin
                        hex_enable=1;hex_word={10'd0,applied_parameters[53:32]};hex_x=pixel_x-11'd1440;
                    end
                end
                6: text_line=(HMI_D_ONLY!=0) ? {"CRUSH ",decimal3(applied_options[6:0])," DRIVE ",decimal3(applied_options[13:7])," SEND ",decimal3(applied_options[20:14]),"    "} :
                    {"GLIDE ",decimal3(applied_options[17:11])," VIB ",decimal3(applied_options[10:4])," SUSTAIN ",applied_options[3] ? "ON " : "OFF","   "};
                7: text_line=applied_parameters[128] ? "OUTPUT   44100 HZ / STEREO      " : "OUTPUT   48000 HZ / STEREO      ";
                default: text_line={"PROFILE ",8'h30+{5'd0,applied_state[9:7]}," / ROUTE ",8'h30+{6'd0,applied_state[6:5]},"             "};
            endcase
        end
        // Piano-key voice cards removed; this area is reserved for effect-chain status.
    end

    wire [255:0] effect_label_word=effect_name(a_effect_id);
    wire [255:0] effect_status_word=a_effect_on ? "ON                              " : "OFF                             ";
    always @* begin
        next_character = a_text_line[255-a_text_index*8 -: 8];
        if(a_effect_label)next_character=effect_label_word[255-a_text_index*8 -:8];
        if(a_effect_status)next_character=effect_status_word[255-a_text_index*8 -:8];
        next_hex_digit = a_hex_word[31-a_hex_index*4 -: 4];
        if (a_hex_enable)
            next_character = next_hex_digit < 10 ? 8'h30 + {4'b0000,next_hex_digit} :
                                                  8'h37 + {4'b0000,next_hex_digit};
        if (a_voice_enable) next_character = a_voice_character;

        next_background = 32'h00f2f3f5;
        if (a_header) next_background = 32'h00ffffff;
        if (a_separator) next_background = 32'h00b6c0cb;
        if (a_wave_box) begin
            next_background = 32'h00ffffff;
            if (a_wave_grid) next_background = 32'h00e1e5e9;
            if (a_wave_center) next_background = 32'h00b6c0cb;
            if (trace_ink) next_background = 32'h00285c81;
        end
        if (a_level_box) begin
            next_background = 32'h00dce1e6;
            if (a_level_x < a_level_width) begin
                if (a_level_red) next_background = 32'h00b94343;
                else if (a_level_orange) next_background = 32'h00b17522;
                else next_background = 32'h00285c81;
            end
        end
        if (a_memory_box)
            next_background = a_memory_status[2] ? 32'h00b94343 :
                         a_memory_status[1:0] == 2'b11 ? 32'h00285c81 : 32'h00b17522;
        if(ENABLE_ANALYSIS) begin
            next_background=a_header ? 32'h00ffffff : 32'h00f2f3f5;
            if(a_separator) next_background=32'h00b6c0cb;
            if(a_analysis_wave_box) begin
                next_background=32'h00ffffff;
                if(a_analysis_wave_grid) next_background=32'h00e1e5e9;
                if(a_analysis_wave_center) next_background=32'h00b6c0cb;
                if(trace_ink) next_background=32'h00285c81;
            end
            if(a_spectrum_box) begin
                next_background=32'h00ffffff;
                if(a_spectrum_grid)
                    next_background=32'h00b6c0cb;
                if(spectrum_l_ink && a_spectrum_even) next_background=32'h00285c81;
                if(spectrum_r_ink && a_spectrum_even) next_background=spectrum_l_ink ? 32'h0068798b : 32'h00b17522;
            end
            if(a_xy_box) begin
                next_background=32'h00ffffff;
                if(a_xy_grid) next_background=32'h00e1e5e9;
                if(a_xy_axis) next_background=32'h00b6c0cb;
                if(a_image_hit) next_background=32'h00285c81;
            end
            if(a_left_box) begin
                next_background=32'h00e0e4e8;
                if(a_x-11'd1248<a_left_width) next_background=32'h00285c81;
            end
            if(a_right_box) begin
                next_background=32'h00e0e4e8;
                if(a_x-11'd1248<a_right_width) next_background=32'h00b17522;
            end
        end
        if (a_card_band) begin
            if(a_card_box) begin
                next_background=32'h00e9edf1;
                if(a_card_edge)
                    next_background=32'h00aab7c3;
            end
            // 48-pixel gaps leave enough room for a readable arrowhead.
            if(a_arrow_shaft)
                next_background=32'h00343b42;
            if(a_arrow_head)
                next_background=32'h00343b42;
        end
        if(a_status_box) begin
            next_background=32'h00ffffff;
            if(a_status_grid)
                next_background=32'h00c2cbd3;
        end
        if(brand_hit) next_background={8'd0,brand_rgb};
        if(a_effect_hit) begin
            next_background=a_effect_edge ? 32'h00556f87 : 32'h00cddbe6;
            if(!a_effect_on) next_background=a_effect_edge ? 32'h00919da8 : 32'h00e0e4e8;
        end
    end

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            a_effect_hit<=0; a_effect_edge<=0; a_effect_on<=0; a_effect_id<=0;a_effect_label<=0;a_effect_status<=0;
            a_text_line <= 0; a_text_index <= 0; a_font_column <= 0; a_font_row <= 0;
            a_text_enable <= 0; a_hex_enable <= 0; a_voice_enable <= 0;
            a_hex_word <= 0; a_hex_index <= 0; a_voice_character <= 0;
            a_x <= 0; a_y <= 0; a_level_width <= 0; a_voice_active <= 0; a_memory_status <= 0;
            a_header<=1'b1; a_separator<=1'b0; a_wave_box<=1'b0; a_wave_grid<=1'b0; a_wave_center<=1'b0; a_level_box<=1'b0; a_level_red<=1'b0; a_level_orange<=1'b0; a_memory_box<=1'b0; a_analysis_wave_box<=1'b0; a_analysis_wave_grid<=1'b0; a_analysis_wave_center<=1'b0; a_spectrum_box<=1'b0; a_spectrum_grid<=1'b0; a_spectrum_even<=1'b0; a_xy_box<=1'b0; a_xy_grid<=1'b0; a_xy_axis<=1'b0; a_left_box<=1'b0; a_right_box<=1'b0; a_card_band<=1'b0; a_card_box<=1'b0; a_card_edge<=1'b0; a_arrow_shaft<=1'b0; a_arrow_head<=1'b0; a_status_box<=1'b0; a_status_grid<=1'b0;
            a_spectrum_left<=0;a_spectrum_right<=0;a_image_hit<=0;a_left_width<=0;a_right_width<=0;
            a_sample_top <= 0; a_sample_bottom <= 0; a_previous_top <= 0; a_previous_bottom <= 0;
            b_character <= 0; b_font_column <= 0; b_font_row <= 0; b_text_enable <= 0; b_background <= 0;
            c_glyph <= 0; c_font_column <= 0; c_font_row <= 0; c_text_enable <= 0; c_background <= 0;
            pixel_data <= 0;
        end else if (enable) begin
            a_effect_hit<=effect_hit; a_effect_id<=effect_id;
            a_effect_label<=effect_hit && effect_relative>=16 && effect_relative<272 && pixel_y>=888 && pixel_y<904;
            a_effect_status<=effect_hit && effect_relative>=16 && effect_relative<272 && pixel_y>=920 && pixel_y<936;
            a_effect_on<=visible_mask[effect_id];
            a_effect_edge<=effect_relative<2 || effect_relative>=286 || pixel_y<874 || pixel_y>=958;
            a_text_line <= text_line; a_text_index <= text_index;
            a_font_column <= font_column; a_font_row <= font_row; a_text_enable <= text_enable;
            a_hex_enable <= hex_enable; a_hex_word <= hex_word; a_hex_index <= hex_x[6:4];
            a_voice_enable <= voice_enable; a_voice_character <= voice_character;
            a_x <= pixel_x; a_y <= pixel_y;
            a_header<=(pixel_y < 128);
            a_separator<=(pixel_y == 127 || pixel_y == 991);
            a_wave_box<=(pixel_x >= 64 && pixel_x < 1088 && pixel_y >= 224 && pixel_y < 736);
            a_wave_grid<=(pixel_x[6:0] == 64 || pixel_y[6:0] == 96);
            a_wave_center<=(pixel_y == 480);
            a_level_box<=(pixel_x >= 1216 && pixel_x < 1856 && pixel_y >= 224 && pixel_y < 256);
            a_level_red<=(pixel_x >= 1816);
            a_level_orange<=(pixel_x >= 1716);
            a_memory_box<=(pixel_x >= 1776 && pixel_x < 1856 && pixel_y >= 432 && pixel_y < 448);
            a_analysis_wave_box<=(pixel_x>=64 && pixel_x<1088 && pixel_y>=208 && pixel_y<464);
            a_analysis_wave_grid<=(pixel_x[6:0]==64 || pixel_y[5:0]==16);
            a_analysis_wave_center<=(pixel_y==336);
            a_spectrum_box<=(pixel_x>=64 && pixel_x<1088 && pixel_y>=568 && pixel_y<792);
            a_spectrum_grid<=(pixel_y[5:0]==56 || pixel_x==64 || pixel_x==306 || pixel_x==578 || pixel_x==850 || pixel_x==1086);
            a_spectrum_even<=(!pixel_x[0]);
            a_xy_box<=(pixel_x>=1248 && pixel_x<1760 && pixel_y>=224 && pixel_y<736);
            a_xy_grid<=(input_image_x[6:0]==0 || input_image_y[6:0]==0);
            a_xy_axis<=(input_image_x==256 || input_image_y==256 || diamond_distance==256);
            a_left_box<=(pixel_x>=1248 && pixel_x<1760 && pixel_y>=784 && pixel_y<800);
            a_right_box<=(pixel_x>=1248 && pixel_x<1760 && pixel_y>=816 && pixel_y<832);
            a_card_band<=(pixel_y>=872 && pixel_y<960);
            a_card_box<=((pixel_x>=64 && pixel_x<352) || (pixel_x>=400 && pixel_x<688) || (pixel_x>=736 && pixel_x<1024));
            a_card_edge<=(pixel_y==872 || pixel_y==959 || pixel_x==64 || pixel_x==351 || pixel_x==400 || pixel_x==687 || pixel_x==736 || pixel_x==1023);
            a_arrow_shaft<=(pixel_y>=917 && pixel_y<=921 && ((pixel_x>=360 && pixel_x<=380) || (pixel_x>=696 && pixel_x<=716)));
            a_arrow_head<=(pixel_y>=907 && pixel_y<=931 &&
                (((pixel_x>=378 && pixel_x<=390) && (pixel_y>=919 ? pixel_y-11'd919 : 11'd919-pixel_y)<=11'd390-pixel_x) ||
                 ((pixel_x>=714 && pixel_x<=726) && (pixel_y>=919 ? pixel_y-11'd919 : 11'd919-pixel_y)<=11'd726-pixel_x)));
            a_status_box<=(pixel_x>=1232 && pixel_x<1776 && pixel_y>=856 && pixel_y<1048);
            a_status_grid<=(pixel_y==856 || pixel_y==1047 || pixel_x==1232 || pixel_x==1775 || pixel_y[4:0]==23);
            a_spectrum_left<=spectrum_left;a_spectrum_right<=spectrum_right;a_image_hit<=image_hit;
            a_left_width<=peak_left[15:6];a_right_width<=peak_right[15:6];
            a_level_width <= peak_data[31] ? 11'd640 : {2'b00,peak_data[30:22]} + {4'b0000,peak_data[30:24]};
            a_voice_active <= active_voices[voice_index]; a_memory_status <= memory_status[2:0];
            // Full negative scale is clamped at row735 inside the plot.
            a_sample_top <= ENABLE_ANALYSIS ? (sample_height == -10'sd128 ? 12'sd462 : 12'sd335-sample_extended) :
                (sample_height == -10'sd256 ? 12'sd734 : 12'sd479-sample_extended);
            a_sample_bottom <= ENABLE_ANALYSIS ? (sample_height == -10'sd128 ? 12'sd464 : 12'sd337-sample_extended) :
                (sample_height == -10'sd256 ? 12'sd736 : 12'sd481-sample_extended);
            a_previous_top <= ENABLE_ANALYSIS ? (previous_height == -10'sd128 ? 12'sd462 : 12'sd335-previous_extended) :
                (previous_height == -10'sd256 ? 12'sd734 : 12'sd479-previous_extended);
            a_previous_bottom <= ENABLE_ANALYSIS ? (previous_height == -10'sd128 ? 12'sd464 : 12'sd337-previous_extended) :
                (previous_height == -10'sd256 ? 12'sd736 : 12'sd481-previous_extended);
            b_character <= next_character; b_font_column <= a_font_column; b_font_row <= a_font_row;
            b_text_enable <= a_text_enable; b_background <= next_background;
            c_glyph <= decoded_glyph; c_font_column <= b_font_column; c_font_row <= b_font_row;
            c_text_enable <= b_text_enable; c_background <= b_background;
            pixel_data <= c_text_enable && font_ink ? 32'h00343b42 : c_background;
        end
    end
endmodule

`default_nettype wire
