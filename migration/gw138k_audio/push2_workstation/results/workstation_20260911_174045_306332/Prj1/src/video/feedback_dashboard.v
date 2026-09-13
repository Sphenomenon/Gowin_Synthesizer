`default_nettype none

// Four-stage, clock-enabled 1920x1080 dashboard. wave_sample is the captured sample at
// max(0, (pixel_x-64)/2), read synchronously alongside the pixel coordinates.
// No trace, meter, status lamp or counter is generated from animation time.
module feedback_dashboard #(parameter integer ENABLE_ANALYSIS=0) (
    input wire clk,
    input wire reset_n,
    input wire enable,
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
    localparam [255:0] EFFECT_TITLE = "EFFECT CHAIN / USER ORDER / ARROWS     ";
    localparam [255:0] FOOTER = "LIVE AUDIO / UART CONTROL       ";
    reg [255:0] text_line;
    reg [5:0] anim_order;
    reg [4:0] anim_timer;
    reg [10:0] text_x, text_y;
    reg text_enable, large_text;
    reg [31:0] hex_word;
    reg hex_enable, voice_enable;
    reg [7:0] voice_character;
    reg [10:0] hex_x;
    wire [10:0] relative_text_x = pixel_x - text_x;
    wire [10:0] relative_text_y = pixel_y - text_y;
    wire [4:0] text_index = large_text ? relative_text_x[9:5] : relative_text_x[8:4];
    wire [2:0] font_column = large_text ? relative_text_x[4:2] : relative_text_x[3:1];
    wire [2:0] font_row = large_text ? relative_text_y[4:2] : relative_text_y[3:1];
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
    wire [1:0] chain0=effect_order[1:0], chain1=effect_order[3:2], chain2=effect_order[5:4];
    wire chain_active0=effect_mask[chain0], chain_active1=effect_mask[chain1], chain_active2=effect_mask[chain2];
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
    reg a_voice_active;
    reg [7:0] a_spectrum_left,a_spectrum_right;
    reg a_image_hit;
    reg [9:0] a_left_width,a_right_width;
    wire [10:0] a_image_x=a_x-11'd1248, a_image_y=a_y-11'd224;
    wire [10:0] full_distance_x=a_image_x>=11'd256 ? a_image_x-11'd256 : 11'd256-a_image_x;
    wire [10:0] full_distance_y=a_image_y>=11'd256 ? a_image_y-11'd256 : 11'd256-a_image_y;
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
        if (pixel_y >= 48 && pixel_y < 80 && pixel_x >= 64 && pixel_x < 1088) begin
            text_line = TITLE; text_y = 48; text_enable = 1; large_text = 1;
        end else if (pixel_y >= 64 && pixel_y < 80 && pixel_x >= 1216 && pixel_x < 1728) begin
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
            if(pixel_y>=48 && pixel_y<80 && pixel_x>=64 && pixel_x<1088) begin
                text_line=TITLE;text_y=48;text_enable=1;large_text=1;
            end else if(pixel_y>=64 && pixel_y<80 && pixel_x>=1216 && pixel_x<1728) begin
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
                if(pixel_x>=64 && pixel_x<576) begin text_line="512 SAMPLES / 10.67 MS          ";text_enable=1;end
                if(pixel_x>=640) begin text_line=waveform_held ? "HOLD / WAITING FOR MATCH        " : "TRIGGERED                       ";text_x=640;text_enable=1;end
            end else if(pixel_y>=528 && pixel_y<544) begin
                text_y=528;
                if(pixel_x>=64 && pixel_x<576) begin text_line="FFT / 2048 HANN / DBFS          ";text_enable=1;end
                if(pixel_x>=640 && pixel_x<1152) begin text_line="L GREEN / R AMBER               ";text_x=640;text_enable=1;end
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
                if(pixel_x>=64 && pixel_x<96) begin text_line="48                              ";text_x=64;text_enable=1;end
                if(pixel_x>=282 && pixel_x<330) begin text_line="200                             ";text_x=282;text_enable=1;end
                if(pixel_x>=562 && pixel_x<594) begin text_line="1K                              ";text_x=562;text_enable=1;end
                if(pixel_x>=834 && pixel_x<866) begin text_line="5K                              ";text_x=834;text_enable=1;end
                if(pixel_x>=1040 && pixel_x<1104) begin text_line="20K                             ";text_x=1040;text_enable=1;end
            end else if(pixel_x>=1216 && pixel_x<1248 && pixel_y>=784 && pixel_y<832) begin
                text_x=1216;
                if(pixel_y<800) begin text_line="L                               ";text_y=784;text_enable=1;end
                if(pixel_y>=816) begin text_line="R                               ";text_y=816;text_enable=1;end
            end else if(pixel_y>=840 && pixel_y<856 && pixel_x>=64 && pixel_x<1104) begin
                text_line=EFFECT_TITLE;text_x=64;text_y=840;text_enable=1;
            end
            // Bottom keyboard cards are intentionally replaced by the live serial effect chain.
            if(pixel_y>=880 && pixel_y<896) begin
                if(pixel_x>=64 && pixel_x<384) begin text_line=chain_active0 ? effect_name(chain0) : "EMPTY                           ";text_x=64;text_y=880;text_enable=1;end
                if(pixel_x>=400 && pixel_x<720) begin text_line=chain_active1 ? effect_name(chain1) : "EMPTY                           ";text_x=400;text_y=880;text_enable=1;end
                if(pixel_x>=736 && pixel_x<1056) begin text_line=chain_active2 ? effect_name(chain2) : "EMPTY                           ";text_x=736;text_y=880;text_enable=1;end
            end
            if(pixel_y>=912 && pixel_y<928) begin
                if(pixel_x>=64 && pixel_x<384) begin text_line=chain_active0 ? "ON                              " : "OFF                             ";text_x=64;text_y=912;text_enable=1;end
                if(pixel_x>=400 && pixel_x<720) begin text_line=chain_active1 ? "ON                              " : "OFF                             ";text_x=400;text_y=912;text_enable=1;end
                if(pixel_x>=736 && pixel_x<1056) begin text_line=chain_active2 ? "ON                              " : "OFF                             ";text_x=736;text_y=912;text_enable=1;end
            end
        end
        // Piano-key voice cards removed; this area is reserved for effect-chain status.
    end

    always @* begin
        next_character = a_text_line[255-a_text_index*8 -: 8];
        next_hex_digit = a_hex_word[31-a_hex_index*4 -: 4];
        if (a_hex_enable)
            next_character = next_hex_digit < 10 ? 8'h30 + {4'b0000,next_hex_digit} :
                                                  8'h37 + {4'b0000,next_hex_digit};
        if (a_voice_enable) next_character = a_voice_character;

        next_background = 32'h00101b2a;
        if (a_y < 128) next_background = 32'h001a3048;
        if (a_y == 127 || a_y == 991) next_background = 32'h0031506c;
        if (a_x >= 64 && a_x < 1088 && a_y >= 224 && a_y < 736) begin
            next_background = 32'h000b1420;
            if (a_x[6:0] == 64 || a_y[6:0] == 96) next_background = 32'h001c3145;
            if (a_y == 480) next_background = 32'h0031506c;
            if (trace_ink) next_background = 32'h003cdbab;
        end
        if (a_x >= 1216 && a_x < 1856 && a_y >= 224 && a_y < 256) begin
            next_background = 32'h00273b50;
            if (a_level_x < a_level_width) begin
                if (a_x >= 1816) next_background = 32'h00ef6572;
                else if (a_x >= 1716) next_background = 32'h00f1c05a;
                else next_background = 32'h003cdbab;
            end
        end
        if (a_x >= 1776 && a_x < 1856 && a_y >= 432 && a_y < 448)
            next_background = a_memory_status[2] ? 32'h00ef6572 :
                         a_memory_status[1:0] == 2'b11 ? 32'h003cdbab : 32'h00f1c05a;
        if(ENABLE_ANALYSIS) begin
            next_background=a_y<128 ? 32'h001a3048 : 32'h00101b2a;
            if(a_y==127 || a_y==991) next_background=32'h0031506c;
            if(a_x>=64 && a_x<1088 && a_y>=208 && a_y<464) begin
                next_background=32'h000b1420;
                if(a_x[6:0]==64 || a_y[5:0]==16) next_background=32'h001c3145;
                if(a_y==336) next_background=32'h0031506c;
                if(trace_ink) next_background=32'h003cdbab;
            end
            if(a_x>=64 && a_x<1088 && a_y>=568 && a_y<792) begin
                next_background=32'h000b1420;
                if(a_y[5:0]==56 || a_x==64 || a_x==306 || a_x==578 || a_x==850 || a_x==1086)
                    next_background=32'h0031506c;
                if(spectrum_l_ink && !a_x[0]) next_background=32'h003cdbab;
                if(spectrum_r_ink && !a_x[0]) next_background=spectrum_l_ink ? 32'h00a8d5bd : 32'h00f1c05a;
            end
            if(a_x>=1248 && a_x<1760 && a_y>=224 && a_y<736) begin
                next_background=32'h000b1420;
                if(a_image_x[6:0]==0 || a_image_y[6:0]==0) next_background=32'h001c3145;
                if(a_image_x==256 || a_image_y==256 || diamond_distance==256) next_background=32'h0031506c;
                if(a_image_hit) next_background=32'h003cdbab;
            end
            if(a_x>=1248 && a_x<1760 && a_y>=784 && a_y<800) begin
                next_background=32'h00263a4f;
                if(a_x-11'd1248<a_left_width) next_background=32'h003cdbab;
            end
            if(a_x>=1248 && a_x<1760 && a_y>=816 && a_y<832) begin
                next_background=32'h00263a4f;
                if(a_x-11'd1248<a_right_width) next_background=32'h00f1c05a;
            end
        end
        if (a_x >= 64 && a_x < 1088 && a_y >= 872 && a_y < 960) begin
            // Narrow inter-card gaps carry an explicit right-pointing arrow.
            // The arrow is rasterized here so every consumer of the DDR page
            // sees the same chain direction without extra overlay logic.
            if ((a_x >= 384 && a_x < 400) || (a_x >= 720 && a_x < 736)) begin
                next_background = 32'h00101b2a;
                if (a_y >= 917 && a_y <= 923 && a_x >= (a_x < 400 ? 386 : 722) && a_x <= (a_x < 400 ? 397 : 733))
                    next_background = 32'h00e5f0fa;
                if (a_y >= 913 && a_y <= 927 && a_x >= (a_x < 400 ? 394 : 730) && a_x <= (a_x < 400 ? 397 : 733) &&
                    ((a_y <= 920 && a_x >= (a_x < 400 ? 394 + (920-a_y) : 730 + (920-a_y))) ||
                     (a_y >= 920 && a_x >= (a_x < 400 ? 394 + (a_y-920) : 730 + (a_y-920)))))
                    next_background = 32'h00e5f0fa;
            end else if (a_x < 384) begin
                next_background = effect_mask[0] ? 32'h00157d70 : 32'h00263a4f;
                if(a_y==872 || a_y==959 || a_x==64 || a_x==383) next_background = anim_timer!=0 ? 32'h00f1c05a : (chain_active0 ? 32'h003cdbab : 32'h0049627a);
            end else if (a_x >= 400 && a_x < 720) begin
                next_background = effect_mask[1] ? 32'h00157d70 : 32'h00263a4f;
                if(a_y==872 || a_y==959 || a_x==400 || a_x==719) next_background = anim_timer!=0 ? 32'h00f1c05a : (chain_active1 ? 32'h003cdbab : 32'h0049627a);
            end else if (a_x >= 736 && a_x < 1056) begin
                next_background = effect_mask[2] ? 32'h00157d70 : 32'h00263a4f;
                if(a_y==872 || a_y==959 || a_x==736 || a_x==1055) next_background = anim_timer!=0 ? 32'h00f1c05a : (chain_active2 ? 32'h003cdbab : 32'h0049627a);
            end else next_background = 32'h00101b2a;
        end
    end

    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            anim_order <= 6'b10_01_00; anim_timer <= 0;
            a_text_line <= 0; a_text_index <= 0; a_font_column <= 0; a_font_row <= 0;
            a_text_enable <= 0; a_hex_enable <= 0; a_voice_enable <= 0;
            a_hex_word <= 0; a_hex_index <= 0; a_voice_character <= 0;
            a_x <= 0; a_y <= 0; a_level_width <= 0; a_voice_active <= 0; a_memory_status <= 0;
            a_spectrum_left<=0;a_spectrum_right<=0;a_image_hit<=0;a_left_width<=0;a_right_width<=0;
            a_sample_top <= 0; a_sample_bottom <= 0; a_previous_top <= 0; a_previous_bottom <= 0;
            b_character <= 0; b_font_column <= 0; b_font_row <= 0; b_text_enable <= 0; b_background <= 0;
            c_glyph <= 0; c_font_column <= 0; c_font_row <= 0; c_text_enable <= 0; c_background <= 0;
            pixel_data <= 0;
        end else if (enable) begin
            if(effect_order!=anim_order) begin anim_order<=effect_order; anim_timer<=5'd31; end
            else if(anim_timer!=0) anim_timer<=anim_timer-1'b1;
            a_text_line <= text_line; a_text_index <= text_index;
            a_font_column <= font_column; a_font_row <= font_row; a_text_enable <= text_enable;
            a_hex_enable <= hex_enable; a_hex_word <= hex_word; a_hex_index <= hex_x[6:4];
            a_voice_enable <= voice_enable; a_voice_character <= voice_character;
            a_x <= pixel_x; a_y <= pixel_y;
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
            pixel_data <= c_text_enable && font_ink ? 32'h00e5f0fa : c_background;
        end
    end
endmodule

`default_nettype wire
