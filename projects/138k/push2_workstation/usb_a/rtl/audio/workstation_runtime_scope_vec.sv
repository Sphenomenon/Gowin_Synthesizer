`timescale 1ns/1ps
// One shared synchronous geometry ROM, time-multiplexed over eight voices.
// Geometry is a closed phase contour, never a time-indexed audio recording.
module workstation_runtime_scope_vec #(
    parameter integer VOICES=8,
    parameter integer SHAPES=8,
    parameter integer POINT_BITS=9,
    parameter integer HARMONICS=8,
    parameter integer MAX_SCAN_HZ=2000,
    parameter PATH_FILE="rtl/audio/scope_vec/data/paths.mem",
    parameter ROTATION_FILE="rtl/audio/scope_vec/data/rotation.mem",
    parameter NOTE_FILE="rtl/audio/scope_vec/data/note_steps.mem",
    parameter ADSR_FILE="sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem",
    parameter bit SEPARATE_OFF_NOTE=1'b0
)(
    input wire clk_i,rst_ni,panic_i,sample_ce_i,rate_44k1_i,
    output wire sample_ready_o,
    output reg sample_valid_o,
    output reg signed [31:0] left_o,right_o,
    input wire event_valid_i,event_note_on_i,
    output wire event_ready_o,
    input wire [6:0] event_note_i,event_velocity_i,
    input wire [2:0] event_shape_i,event_morph_shape_i,event_profile_i,
    input wire [21:0] event_pitch_q20_i,pitch_q20_i,
    input wire [15:0] morph_q15_i,scale_q15_i,
    input wire [6:0] rotation_i,
    input wire signed [15:0] cal_x_q14_i,cal_y_q14_i,
    input wire signed [31:0] offset_x_i,offset_y_i,
    output reg [VOICES-1:0] active_mask_o,
    output reg [3:0] active_count_o,
    output reg [31:0] rejected_events_o,
    output reg config_error_o,frequency_error_o,clip_o,
    output wire busy_o,
    input wire [6:0] event_off_note_i
);
    localparam integer POINTS=1<<POINT_BITS;
    localparam [31:0] MAX_STEP=32'((64'd4294967296*MAX_SCAN_HZ)/48000);
    localparam [31:0] MAX_STEP_44=32'((64'd4294967296*MAX_SCAN_HZ)/44100);
    localparam [2:0] IDLE=0,ATTACK=1,DECAY=2,SUSTAIN=3,RELEASE=4;
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [31:0] path_rom[0:SHAPES*POINTS-1];
    reg [31:0] note_rom[0:127],rotation_rom[0:511];
    reg [31:0] rotation_q;
    // Compare fixed tuning words before selecting a note. This is a continuous
    // view of the original ROM, so there is no second initialization order.
    wire [127:0] note_above_limit;
    for(genvar n=0;n<128;n=n+1)begin: g_note_limit
        assign note_above_limit[n]=note_rom[n]>MAX_STEP;
    end
    reg [23:0] adsr_rom[0:19];
    reg [31:0] phase[0:VOICES-1],base_step[0:VOICES-1];
    reg [21:0] own_pitch[0:VOICES-1];
    reg [6:0] note[0:VOICES-1];
    reg [2:0] shape[0:VOICES-1],morph_shape[0:VOICES-1],env_state[0:VOICES-1];
    reg [23:0] envelope[0:VOICES-1],attack[0:VOICES-1],decay[0:VOICES-1],sustain[0:VOICES-1],release_step[0:VOICES-1];
    reg [15:0] velocity[0:VOICES-1];
    reg [4:0] state;
    reg [$clog2(VOICES)-1:0] voice_index;
    reg [31:0] scan_phase;
    reg [53:0] own_product,pitch_product;
    // Low phase/product bits are intentionally discarded by interpolation.
    wire unused_fraction = &{1'b0,scan_phase[6:0],own_product[19:0]};
    reg [15:0] morph,scale,frame_morph,frame_scale;
    reg [8:0] rotation;
    reg signed [15:0] frame_cal_x,frame_cal_y;
    reg signed [31:0] frame_offset_x,frame_offset_y;
    reg [21:0] frame_pitch;
    reg frame_44k1;
    reg [7:0] slew_remainder,rotation_remainder;
    wire [16:0] slew_numerator=17'd40960+{9'd0,slew_remainder};
    wire [15:0] slew_step=rate_44k1_i ? 16'(slew_numerator/17'd147) : 16'd256;
    wire [8:0] rotation_numerator=9'd160+{1'b0,rotation_remainder};
    wire [8:0] rotation_step=rate_44k1_i ? 9'(rotation_numerator/9'd147) : 9'd1;
    wire signed [8:0] rotation_delta=$signed(9'({rotation_i,2'b00}-rotation));
    wire [8:0] rotation_distance=rotation_delta[8] ? -9'(rotation_delta) : 9'(rotation_delta);
    wire [8:0] rotation_increment=rotation_distance>rotation_step ? rotation_step : rotation_distance;
    reg [POINT_BITS+2:0] rom_address;
    reg [31:0] rom_q,a0,a1,b0,b1,rotation_xy;
    reg signed [17:0] ax,ay,bx,by,mx,my;
    reg signed [17:0] rotated_x,rotated_y;
    reg signed [42:0] env_x,env_y;
    reg signed [34:0] voice_x,voice_y;
    reg signed [35:0] sum_x,sum_y;
    reg signed [51:0] cal_product_x,cal_product_y;
    reg signed [55:0] scaled_x,scaled_y;
    reg own_overflow;
    reg [23:0] frame_envelope_max;
    wire signed [34:0] rotation_product_x=$signed(mx)*$signed(rotation_xy[31:16])-$signed(my)*$signed(rotation_xy[15:0]);
    wire signed [34:0] rotation_product_y=$signed(mx)*$signed(rotation_xy[15:0])+$signed(my)*$signed(rotation_xy[31:16]);
    // The maximum is final before state 15. Capture the offset products beside
    // the calibration products, so per-voice max selection cannot drive DSP CE.
    reg signed [56:0] offset_product_x,offset_product_y;
    wire signed [38:0] calibrated_x=39'(cal_product_x>>>14)+39'(offset_product_x>>>24);
    wire signed [38:0] calibrated_y=39'(cal_product_y>>>14)+39'(offset_product_y>>>24);
    // The workstation has independent on/off sources during sustain scans.
    // Only Note On addresses the tuning ROM; release compares this bypass.
    wire [6:0] off_note=SEPARATE_OFF_NOTE ? event_off_note_i : event_note_i;
    wire [VOICES-1:0] idle_mask,release_mask,free_select,release_select;
    wire free_found=|idle_mask;
    integer j;
    // Select the lowest voice directly; avoid priority encode then decode.
    for(genvar v=0;v<VOICES;v=v+1) begin: g_event_select
        assign idle_mask[v]=env_state[v]==IDLE;
        assign release_mask[v]=note[v]==off_note && env_state[v]!=IDLE && env_state[v]!=RELEASE;
        if(v==0) begin: g_first_voice
            assign free_select[v]=idle_mask[v];
            assign release_select[v]=release_mask[v];
        end else begin: g_later_voice
            assign free_select[v]=idle_mask[v] && !(|idle_mask[v-1:0]);
            assign release_select[v]=release_mask[v] && !(|release_mask[v-1:0]);
        end
    end
    wire [24:0] voice_attack_sum[0:VOICES-1],voice_decay_threshold[0:VOICES-1];
    for(genvar e=0;e<VOICES;e=e+1) begin: g_local_envelope
        assign voice_attack_sum[e]={1'b0,envelope[e]}+{1'b0,envelope_step(attack[e],frame_44k1)};
        assign voice_decay_threshold[e]={1'b0,sustain[e]}+{1'b0,envelope_step(decay[e],frame_44k1)};
    end
    reg [VOICES-1:0] frame_active;
    reg frame_frequency_error;
    wire [POINT_BITS-1:0] point_index=scan_phase[31 -: POINT_BITS];
    wire [POINT_BITS-1:0] next_point=point_index+1'b1;
    wire [15:0] fraction=scan_phase[31-POINT_BITS -: 16];
    // Keep canonical48k note/phase state. Scale the full final pitch product,
    // then test its35-bit result before truncating a safe phase increment.
    wire [61:0] rate_step_numerator={8'd0,pitch_product}*62'd160+62'd77070336;
    wire [34:0] effective_step=frame_44k1 ? 35'(rate_step_numerator/62'd154140672)
                                                      : {3'd0,pitch_product[51:20]};
    wire [34:0] step_limit=frame_44k1 ? {3'd0,MAX_STEP_44} : {3'd0,MAX_STEP};
    assign sample_ready_o=state==0;
    assign event_ready_o=state==0 && !sample_ce_i;
    assign busy_o=state!=0;
    initial begin
        if(VOICES!=8 || SHAPES<1 || SHAPES>8 || POINT_BITS<7 || POINT_BITS>9 ||
           SHAPES*POINTS*4>16384 || HARMONICS!=8 || MAX_SCAN_HZ!=2000)
            $fatal(1,"scope_vec: unsupported configuration / path ROM budget");
        $readmemh(PATH_FILE,path_rom);
        $readmemh(NOTE_FILE,note_rom);
        $readmemh(ROTATION_FILE,rotation_rom);
        $readmemh(ADSR_FILE,adsr_rom);
    end
    function automatic [15:0] slew(input [15:0] old_value,target,input [15:0] step);
        begin
            if(old_value<target) slew=target-old_value>step ? old_value+step : target;
            else slew=old_value-target>step ? old_value-step : target;
        end
    endfunction
    function automatic [23:0] envelope_step(input [23:0] value,input bit rate44);
        reg [31:0] numerator,scaled;
        begin
            numerator={8'd0,value}*32'd160+32'd73;
            scaled=numerator/32'd147;
            envelope_step=rate44 ? (scaled>32'hffffff ? 24'hffffff : scaled[23:0]) : value;
        end
    endfunction
    function automatic signed [17:0] interpolate(input [15:0] p,q,input [15:0] f);
        reg signed [16:0] delta;
        reg signed [33:0] product;
        begin
            delta=$signed(q)-$signed(p);
            product=delta*$signed({1'b0,f});
            interpolate=18'($signed(p)+(product>>>16));
        end
    endfunction
    function automatic signed [17:0] morph_point(input signed [17:0] p,q,input [15:0] f);
        reg signed [18:0] delta;
        reg signed [35:0] product;
        begin delta=q-p;product=delta*$signed({1'b0,f});morph_point=18'(p+(product>>>15));end
    endfunction
    function automatic signed [31:0] saturate(input signed [63:0] value);
        begin
            if(value>64'sd2147483647) saturate=32'sh7fffffff;
            else if(value< -64'sd2147483648) saturate=32'sh80000000;
            else saturate=value[31:0];
        end
    endfunction
    // Address multiplexing infers one physical synchronous ROM read port.
    always @* begin
        rom_address=0;
        case(state)
            4:rom_address={shape[voice_index],point_index};
            5:rom_address={shape[voice_index],next_point};
            6:rom_address={morph_shape[voice_index],point_index};
            7:rom_address={morph_shape[voice_index],next_point};

            default:rom_address=0;
        endcase
        active_mask_o=0;active_count_o=0;
        for(integer k=0;k<VOICES;k=k+1) begin
            if(env_state[k]!=IDLE) begin active_mask_o[k]=1;active_count_o=active_count_o+1'b1;end
        end
    end
    always @(posedge clk_i) begin rom_q<=path_rom[rom_address];rotation_q<=rotation_rom[rotation];end
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            state<=0;voice_index<=0;sample_valid_o<=0;left_o<=0;right_o<=0;
            rejected_events_o<=0;config_error_o<=0;frequency_error_o<=0;clip_o<=0;
            morph<=0;scale<=0;rotation<=0;frame_morph<=0;frame_scale<=0;
            frame_44k1<=0;slew_remainder<=73;rotation_remainder<=73;
            frame_pitch<=22'd1048576;frame_cal_x<=16384;frame_cal_y<=16384;
            frame_offset_x<=0;frame_offset_y<=0;sum_x<=0;sum_y<=0;own_overflow<=0;frame_envelope_max<=0;
            scan_phase<=0;own_product<=0;pitch_product<=0;frame_active<=0;frame_frequency_error<=0;
            a0<=0;a1<=0;b0<=0;b1<=0;rotation_xy<=0;ax<=0;ay<=0;bx<=0;by<=0;mx<=0;my<=0;
            rotated_x<=0;rotated_y<=0;env_x<=0;env_y<=0;voice_x<=0;voice_y<=0;
            cal_product_x<=0;cal_product_y<=0;scaled_x<=0;scaled_y<=0;offset_product_x<=0;offset_product_y<=0;
            for(j=0;j<VOICES;j=j+1) begin
                phase[j]<=0;base_step[j]<=0;own_pitch[j]<=1048576;note[j]<=0;shape[j]<=0;morph_shape[j]<=0;
                env_state[j]<=IDLE;envelope[j]<=0;attack[j]<=0;decay[j]<=0;sustain[j]<=0;release_step[j]<=0;velocity[j]<=0;
            end
        end else begin
            sample_valid_o<=0;clip_o<=0;
            if(sample_ce_i && !sample_ready_o) config_error_o<=1;
            if(panic_i) begin
                state<=0;left_o<=0;right_o<=0;sum_x<=0;sum_y<=0;
                for(j=0;j<VOICES;j=j+1) begin env_state[j]<=IDLE;envelope[j]<=0;end
            end else begin
                if(event_valid_i && event_ready_o) begin
                    if(event_note_on_i) begin
                        if(32'(event_shape_i)>=SHAPES || 32'(event_morph_shape_i)>=SHAPES || event_profile_i>=5 ||
                           event_pitch_q20_i==0 || event_velocity_i==0 || note_above_limit[event_note_i]) begin
                            rejected_events_o<=rejected_events_o+1'b1;config_error_o<=1;
                        end else if(!free_found) rejected_events_o<=rejected_events_o+1'b1;
                        else for(j=0;j<VOICES;j=j+1) if(free_select[j]) begin
                            phase[j]<=0;base_step[j]<=note_rom[event_note_i];own_pitch[j]<=event_pitch_q20_i;
                            note[j]<=event_note_i;shape[j]<=event_shape_i;morph_shape[j]<=event_morph_shape_i;
                            env_state[j]<=ATTACK;envelope[j]<=0;
                            attack[j]<=adsr_rom[{event_profile_i,2'b00}];
                            decay[j]<=adsr_rom[{event_profile_i,2'b00}+1];
                            sustain[j]<=adsr_rom[{event_profile_i,2'b00}+2];
                            release_step[j]<=adsr_rom[{event_profile_i,2'b00}+3];
                            velocity[j]<={1'b0,event_velocity_i,event_velocity_i,event_velocity_i[6]};
                        end
                    end else for(j=0;j<VOICES;j=j+1) if(release_select[j]) env_state[j]<=RELEASE;
                end
                case(state)
                    0:if(sample_ce_i) begin
                        if(morph_q15_i>32768 || scale_q15_i>32768 || pitch_q20_i==0 || cal_x_q14_i<=0 || cal_y_q14_i<=0) begin
                            config_error_o<=1;frame_scale<=0;
                        end else frame_scale<=slew(scale,scale_q15_i,slew_step);
                        morph<=slew(morph,morph_q15_i,slew_step);scale<=slew(scale,scale_q15_i,slew_step);
                        frame_morph<=slew(morph,morph_q15_i,slew_step);
                        // Shortest angular path, rate-correct fractional slew.
                        frame_44k1<=rate_44k1_i;
                        if(rate_44k1_i)begin
                            slew_remainder<=8'(slew_numerator%17'd147);
                            rotation_remainder<=8'(rotation_numerator%9'd147);
                        end
                        if(rotation!={rotation_i,2'b00}) rotation<=rotation+(rotation_delta>0 ? rotation_increment : -rotation_increment);
                        frame_pitch<=pitch_q20_i;frame_cal_x<=cal_x_q14_i;frame_cal_y<=cal_y_q14_i;
                        frame_offset_x<=offset_x_i;frame_offset_y<=offset_y_i;
                        sum_x<=0;sum_y<=0;voice_index<=0;frame_envelope_max<=0;frame_active<=active_mask_o;frame_frequency_error<=0;state<=1;
                    end
                    1:begin
                        own_product<=base_step[voice_index]*own_pitch[voice_index];scan_phase<=phase[voice_index];
                        // Keep each voice arithmetic local; decode only its write enable.
                        for(j=0;j<VOICES;j=j+1) if(32'(voice_index)==j) begin
                            case(env_state[j])
                                ATTACK:if(attack[j]==0 || voice_attack_sum[j]>=25'hffffff) begin envelope[j]<=24'hffffff;env_state[j]<=DECAY;end
                                       else envelope[j]<=voice_attack_sum[j][23:0];
                                DECAY:if(decay[j]==0 || {1'b0,envelope[j]}<=voice_decay_threshold[j]) begin
                                          envelope[j]<=sustain[j];env_state[j]<=SUSTAIN;
                                      end else envelope[j]<=envelope[j]-envelope_step(decay[j],frame_44k1);
                                SUSTAIN:envelope[j]<=sustain[j];
                                RELEASE:if(release_step[j]==0 || envelope[j]<=envelope_step(release_step[j],frame_44k1)) begin envelope[j]<=0;env_state[j]<=IDLE;end
                                        else envelope[j]<=envelope[j]-envelope_step(release_step[j],frame_44k1);
                                default:envelope[j]<=0;
                            endcase
                        end
                        state<=2;
                    end
                    2:begin pitch_product<=own_product[51:20]*frame_pitch;own_overflow<=|own_product[53:52];state<=3;end
                    3:begin
                        if(own_overflow || pitch_product[53:52]!=0 || effective_step>step_limit || effective_step==0) begin
                            if(frame_active[voice_index]) begin frequency_error_o<=1;frame_frequency_error<=1;end
                        end else phase[voice_index]<=phase[voice_index]+effective_step[31:0];
                        if(envelope[voice_index]>frame_envelope_max) frame_envelope_max<=envelope[voice_index];
                        state<=4;
                    end
                    4:state<=5;
                    5:begin a0<=rom_q;state<=6;end
                    6:begin a1<=rom_q;state<=7;end
                    7:begin b0<=rom_q;state<=8;end
                    8:begin b1<=rom_q;state<=9;end
                    9:begin
                        rotation_xy<=rotation_q;
                        ax<=interpolate(a0[31:16],a1[31:16],fraction);ay<=interpolate(a0[15:0],a1[15:0],fraction);
                        bx<=interpolate(b0[31:16],b1[31:16],fraction);by<=interpolate(b0[15:0],b1[15:0],fraction);state<=10;
                    end
                    10:begin mx<=morph_point(ax,bx,frame_morph);my<=morph_point(ay,by,frame_morph);state<=11;end
                    11:begin
                        // Rotation coefficients are Q1.15, independent of the shape set.
                        rotated_x<=18'(rotation_product_x>>>15);
                        rotated_y<=18'(rotation_product_y>>>15);state<=12;
                    end
                    12:begin env_x<=rotated_x*$signed({1'b0,envelope[voice_index]});env_y<=rotated_y*$signed({1'b0,envelope[voice_index]});state<=13;end
                    13:begin voice_x<=18'(env_x>>>24)*$signed({1'b0,velocity[voice_index]});voice_y<=18'(env_y>>>24)*$signed({1'b0,velocity[voice_index]});state<=14;end
                    14:begin
                        sum_x<=sum_x+(36'(voice_x>>>15)<<<13);sum_y<=sum_y+(36'(voice_y>>>15)<<<13);
                        if(32'(voice_index)==VOICES-1) state<=15;
                        else begin voice_index<=voice_index+1'b1;state<=1;end
                    end
                    15:begin
                        cal_product_x<=sum_x*$signed(frame_cal_x);cal_product_y<=sum_y*$signed(frame_cal_y);
                        offset_product_x<=$signed(frame_offset_x)*$signed({1'b0,frame_envelope_max});
                        offset_product_y<=$signed(frame_offset_y)*$signed({1'b0,frame_envelope_max});state<=16;
                    end
                    16:begin
                        scaled_x<=calibrated_x*$signed({1'b0,frame_scale});
                        scaled_y<=calibrated_y*$signed({1'b0,frame_scale});state<=17;
                    end
                    17:begin
                        left_o<=frame_frequency_error ? 32'sd0 : saturate(64'(scaled_x)>>>15);
                        right_o<=frame_frequency_error ? 32'sd0 : saturate(64'(scaled_y)>>>15);
                        clip_o<=!frame_frequency_error && ((scaled_x>>>15)>56'sd2147483647 || (scaled_x>>>15)< -56'sd2147483648 ||
                            (scaled_y>>>15)>56'sd2147483647 || (scaled_y>>>15)< -56'sd2147483648);
                        sample_valid_o<=1;state<=0;
                    end
                    default:begin state<=0;config_error_o<=1;end
                endcase
            end
        end
    end
endmodule
