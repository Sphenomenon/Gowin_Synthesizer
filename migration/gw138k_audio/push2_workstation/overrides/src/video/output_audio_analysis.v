`default_nettype none
// Two independent 2048-point, periodic-Hann, radix-2 FFTs of the exact DAC
// PCM channels. Stereo images use the same unwindowed immutable PCM block.
// All displayed results stay fixed until release_frame, even under stalls.
module output_audio_analysis #(parameter integer ASYNC_DISPLAY=0) (
    input wire clk, reset_n,
    input wire source_clk, source_reset_n,
    input wire [31:0] pcm_pair,
    input wire sample_valid,
    input wire release_frame,
    output reg ready,
    output wire [15:0] peak_left, peak_right,
    output wire [2:0] image_gain,
    output wire [31:0] sequence_data, skipped_data,
    input wire display_read_enable,
    input wire [8:0] spectrum_column,
    input wire [15:0] image_addr,
    output reg [7:0] spectrum_left, spectrum_right,
    output reg image_hit
);
    // ASYNC_DISPLAY publishes a completed back bank only between rasters.
    // In legacy mode ready/release and single-bank reads remain unchanged.
    reg write_bank,read_bank,front_valid;
    reg [15:0] work_peak_left,work_peak_right,front_peak_left,front_peak_right;
    reg [2:0] work_image_gain,front_image_gain;
    wire [31:0] work_sequence_data,work_skipped_data;
    reg [31:0] front_sequence,front_skipped;
    assign peak_left=ASYNC_DISPLAY ? front_peak_left : work_peak_left;
    assign peak_right=ASYNC_DISPLAY ? front_peak_right : work_peak_right;
    assign image_gain=ASYNC_DISPLAY ? front_image_gain : work_image_gain;
    assign sequence_data=ASYNC_DISPLAY ? front_sequence : work_sequence_data;
    assign skipped_data=ASYNC_DISPLAY ? front_skipped : work_skipped_data;
    localparam IMAGE_ADDR_BITS=16+ASYNC_DISPLAY;
    localparam DISPLAY_ADDR_BITS=9+ASYNC_DISPLAY;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n)begin
            write_bank<=ASYNC_DISPLAY!=0;read_bank<=0;front_valid<=0;
            front_peak_left<=0;front_peak_right<=0;front_image_gain<=0;
            front_sequence<=0;front_skipped<=0;
        end else if(ASYNC_DISPLAY && ready && release_frame)begin
            read_bank<=write_bank;write_bank<=~write_bank;front_valid<=1;
            front_peak_left<=work_peak_left;front_peak_right<=work_peak_right;
            front_image_gain<=work_image_gain;front_sequence<=work_sequence_data;front_skipped<=work_skipped_data;
        end
    end
    localparam [4:0] WAIT_BLOCK=0, LOAD_READ=1, LOAD_MULT=2, LOAD_WRITE=3,
        GAIN=4, CLEAR_IMAGE=5, IMAGE_READ=6, IMAGE_WRITE=7,
        FFT_READ_A=8, FFT_READ_B=9, FFT_MULT=10, FFT_ROTATE=11,
        FFT_WRITE_A=12, FFT_WRITE_B=13, POWER_READ=14, POWER_MULT=15,
        POWER_SUM=16, POWER_EXPONENT=17, POWER_WRITE=18, FRAME_READY=19,
        MAP_CLEAR=20, MAP_BEGIN=21, MAP_READ=22, MAP_PEAK=23, MAP_WRITE=24, IMAGE_SUM=25;
    reg [4:0] state;
    reg channel;
    reg [10:0] index, group_base, butterfly;
    reg [3:0] stage;
    reg [11:0] span;
    reg [15:0] clear_addr;
    wire capture_ready;
    wire [31:0] captured;
    wire capture_read = state==LOAD_READ || state==IMAGE_READ;
    output_audio_capture #(.SAMPLE_BITS(11)) u_capture(
        .source_clk(source_clk),.source_reset_n(source_reset_n),
        .pcm_pair(pcm_pair),.sample_valid(sample_valid),.clk(clk),.reset_n(reset_n),
        .ready(capture_ready),.release_block(ready && release_frame),
        .snapshot_sequence(work_sequence_data),.snapshot_skipped(work_skipped_data),
        .read_enable(capture_read),.read_addr(index),.read_data(captured));
    wire signed [15:0] left_pcm=$signed(captured[31:16]);
    wire signed [15:0] right_pcm=$signed(captured[15:0]);
    wire [15:0] left_abs=left_pcm[15] ? (~left_pcm+16'd1) : left_pcm;
    wire [15:0] right_abs=right_pcm[15] ? (~right_pcm+16'd1) : right_pcm;
    // Register absolute values before peak comparison; reuses LOAD_WRITE.
    reg [15:0] peak_abs_left,peak_abs_right;
    wire [15:0] max_peak=work_peak_left>work_peak_right ? work_peak_left : work_peak_right;
    reg [2:0] computed_gain;
    integer gain_bit;
    always @* begin
        computed_gain=0;
        for(gain_bit=0;gain_bit<7;gain_bit=gain_bit+1)
            if(max_peak!=0 && max_peak < (16'h4000 >> gain_bit)) computed_gain=gain_bit[2:0]+3'd1;
    end
    wire signed [16:0] mid_sum={left_pcm[15],left_pcm}+{right_pcm[15],right_pcm};
    wire signed [16:0] side_sum={right_pcm[15],right_pcm}-{left_pcm[15],left_pcm};
    // Split capture-BRAM -> add/subtract -> shift/clamp -> image-BRAM path.
    // One extra cycle per image point keeps the image path short.
    reg signed [16:0] plot_mid,plot_side;
    reg plot_nonzero;
    always @(posedge clk) if(state==IMAGE_SUM) begin
        plot_mid<=mid_sum;plot_side<=side_sum;plot_nonzero<=captured!=0;
    end
    wire [3:0] image_shift=4'd9-{1'b0,work_image_gain};
    wire signed [17:0] plot_x=18'sd128+($signed(plot_side) >>> image_shift);
    wire signed [17:0] plot_y=18'sd128-($signed(plot_mid) >>> image_shift);
    wire [7:0] image_x=plot_x<0 ? 8'd0 : plot_x>255 ? 8'd255 : plot_x[7:0];
    wire [7:0] image_y=plot_y<0 ? 8'd0 : plot_y>255 ? 8'd255 : plot_y[7:0];
    wire [IMAGE_ADDR_BITS-1:0] image_clear_index=ASYNC_DISPLAY ? {write_bank,clear_addr}:clear_addr;
    wire [IMAGE_ADDR_BITS-1:0] image_write_index=ASYNC_DISPLAY ? {write_bank,image_y,image_x}:{image_y,image_x};
    wire [IMAGE_ADDR_BITS-1:0] image_read_index=ASYNC_DISPLAY ? {read_bank,image_addr}:image_addr;
    reg image_pixels[0:(65536 << ASYNC_DISPLAY)-1];
    always @(posedge clk) begin
        if(state==CLEAR_IMAGE) image_pixels[image_clear_index]<=0;
        else if(state==IMAGE_WRITE && plot_nonzero) image_pixels[image_write_index]<=1;
        if(display_read_enable) image_hit<=(ASYNC_DISPLAY && !front_valid) ? 1'b0 : image_pixels[image_read_index];
    end

    wire [15:0] window_gain;
    wire signed [17:0] twiddle_re,twiddle_im;
    wire [9:0] twiddle_addr=butterfly[9:0] << (4'd10-stage);
    audio_analysis_rom u_rom(.clk(clk),.window_addr(index),.twiddle_addr(twiddle_addr),
        .window_gain(window_gain),.twiddle_re(twiddle_re),.twiddle_im(twiddle_im));
    // Six fractional guard bits retain low-level spectral detail; each
    // butterfly scales by 1/2. 24 bits cover the complex intermediate bound.
    reg signed [23:0] real_ram[0:2047], imag_ram[0:2047];
    reg signed [23:0] ram_real,ram_imag,a_real,a_imag,rot_real,rot_imag;
    reg signed [32:0] window_product;
    reg signed [41:0] product_rr,product_ii,product_ri,product_ir;
    wire signed [42:0] rotated_real={product_rr[41],product_rr}-{product_ii[41],product_ii};
    wire signed [42:0] rotated_imag={product_ri[41],product_ri}+{product_ir[41],product_ir};
    wire [10:0] address_a=group_base+butterfly;
    wire [10:0] address_b=address_a+span[11:1];
    wire [10:0] work_read_addr=state==POWER_READ ? index : state==FFT_READ_B ? address_b : address_a;
    wire signed [24:0] sum_real={a_real[23],a_real}+{rot_real[23],rot_real};
    wire signed [24:0] sum_imag={a_imag[23],a_imag}+{rot_imag[23],rot_imag};
    wire signed [24:0] diff_real={a_real[23],a_real}-{rot_real[23],rot_real};
    wire signed [24:0] diff_imag={a_imag[23],a_imag}-{rot_imag[23],rot_imag};
    wire [10:0] reverse_index={index[0],index[1],index[2],index[3],index[4],index[5],index[6],index[7],index[8],index[9],index[10]};
    always @(posedge clk) begin
        if(state==FFT_READ_A || state==FFT_READ_B || state==POWER_READ) begin
            ram_real<=real_ram[work_read_addr]; ram_imag<=imag_ram[work_read_addr];
        end
        if(state==LOAD_WRITE) begin real_ram[reverse_index]<={window_product[32],window_product[32:10]}; imag_ram[reverse_index]<=0; end
        else if(state==FFT_WRITE_A) begin real_ram[address_a]<=sum_real[24:1]; imag_ram[address_a]<=sum_imag[24:1]; end
        else if(state==FFT_WRITE_B) begin real_ram[address_b]<=diff_real[24:1]; imag_ram[address_b]<=diff_imag[24:1]; end
    end
    reg [47:0] square_real,square_imag;
    reg [48:0] power_value;
    reg [5:0] power_exponent;
    reg [5:0] detected_exponent;
    integer power_bit;
    always @* begin
        detected_exponent=0;
        for(power_bit=0;power_bit<49;power_bit=power_bit+1)
            if(power_value[power_bit]) detected_exponent=power_bit;
    end
    wire [48:0] normalized_power=power_exponent>=3 ? power_value>>(power_exponent-6'd3) : power_value<<(6'd3-power_exponent);
    // 8 pixels per octave of power (~3.0103 dB); 224px covers ~84.3 dB.
    // Full-scale bin-centred Hann sine: |FFT/N|=32768/4 * 64=2^19.
    wire signed [10:0] log_height=$signed({2'd0,power_exponent,3'd0})+
        $signed({8'd0,normalized_power[2:0]})-(index==0 || index==1024 ? 11'sd96 : 11'sd80);
    wire [7:0] level_height=power_value==0 || log_height<0 ? 8'd0 : log_height>224 ? 8'd224 : log_height[7:0];
    reg [7:0] levels_left[0:1023],levels_right[0:1023];
    reg [7:0] display_left[0:(512 << ASYNC_DISPLAY)-1],display_right[0:(512 << ASYNC_DISPLAY)-1];
    // Independent logarithmic bars. Visible bins 2..853 cover
    // 46.875..19992.1875 Hz at 48k/2048. Same-column bins are peak-pooled;
    // columns without a measured bin remain blank. No interpolation.
    wire [8:0] bin_column;
    gw138k_spectrum_column_rom u_columns(.clk(clk),.bin(index[9:0]),.column(bin_column));
    reg [8:0] group_column,clear_column,column_registered;
    reg [7:0] band_left,band_right,read_level_left,read_level_right;
    reg map_finishing;
    wire [DISPLAY_ADDR_BITS-1:0] display_clear_index=ASYNC_DISPLAY ? {write_bank,clear_column}:clear_column;
    wire [DISPLAY_ADDR_BITS-1:0] display_write_index=ASYNC_DISPLAY ? {write_bank,group_column}:group_column;
    wire [DISPLAY_ADDR_BITS-1:0] display_read_index=ASYNC_DISPLAY ? {read_bank,column_registered}:column_registered;

    // Keep the established two-register read latency and stalled-read hold.
    always @(posedge clk) column_registered<=spectrum_column;
    always @(posedge clk) begin
        if(state==POWER_WRITE && !index[10]) begin
            if(channel) levels_right[index[9:0]]<=level_height;
            else levels_left[index[9:0]]<=level_height;
        end
        if(state==MAP_READ) begin
            read_level_left<=levels_left[index[9:0]]; read_level_right<=levels_right[index[9:0]];
        end
        if(state==MAP_CLEAR) begin
            display_left[display_clear_index]<=0; display_right[display_clear_index]<=0;
        end else if(state==MAP_WRITE) begin
            display_left[display_write_index]<=band_left; display_right[display_write_index]<=band_right;
        end
        if(display_read_enable) begin
            spectrum_left<=(ASYNC_DISPLAY && !front_valid) ? 8'd0 : display_left[display_read_index]; spectrum_right<=(ASYNC_DISPLAY && !front_valid) ? 8'd0 : display_right[display_read_index];
        end
    end

    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            state<=WAIT_BLOCK; ready<=0; channel<=0; index<=0;
            work_peak_left<=0; work_peak_right<=0; work_image_gain<=0; clear_addr<=0;
            peak_abs_left<=0;peak_abs_right<=0;
            group_base<=0; butterfly<=0; stage<=0; span<=2;
            window_product<=0; a_real<=0; a_imag<=0; rot_real<=0; rot_imag<=0;
            product_rr<=0; product_ii<=0; product_ri<=0; product_ir<=0;
            square_real<=0; square_imag<=0; power_value<=0; power_exponent<=0;
            group_column<=0;clear_column<=0;band_left<=0;band_right<=0;map_finishing<=0;
        end else case(state)
            WAIT_BLOCK: if(capture_ready) begin
                ready<=0; work_peak_left<=0; work_peak_right<=0; channel<=0; index<=0; state<=LOAD_READ;
            end
            LOAD_READ: state<=LOAD_MULT;
            LOAD_MULT: begin
                window_product<=(channel ? right_pcm : left_pcm)*$signed({1'b0,window_gain});
                peak_abs_left<=left_abs;peak_abs_right<=right_abs;
                state<=LOAD_WRITE;
            end
            LOAD_WRITE: begin
                if(!channel) begin
                    if(peak_abs_left>work_peak_left) work_peak_left<=peak_abs_left;
                    if(peak_abs_right>work_peak_right) work_peak_right<=peak_abs_right;
                end
                if(index==2047) begin
                    index<=0; group_base<=0; butterfly<=0; stage<=0; span<=2;
                    if(!channel) state<=GAIN; else state<=FFT_READ_A;
                end else begin index<=index+1'b1; state<=LOAD_READ; end
            end
            GAIN: begin work_image_gain<=computed_gain; clear_addr<=0; state<=CLEAR_IMAGE; end
            CLEAR_IMAGE: if(clear_addr==65535) begin index<=0; state<=IMAGE_READ; end
                         else clear_addr<=clear_addr+1'b1;
            IMAGE_READ: state<=IMAGE_SUM;
            IMAGE_SUM: state<=IMAGE_WRITE;
            IMAGE_WRITE: if(index==2047) begin index<=0; state<=FFT_READ_A; end
                         else begin index<=index+1'b1; state<=IMAGE_READ; end
            FFT_READ_A: state<=FFT_READ_B;
            FFT_READ_B: begin a_real<=ram_real; a_imag<=ram_imag; state<=FFT_MULT; end
            FFT_MULT: begin
                product_rr<=ram_real*twiddle_re; product_ii<=ram_imag*twiddle_im;
                product_ri<=ram_real*twiddle_im; product_ir<=ram_imag*twiddle_re;
                state<=FFT_ROTATE;
            end
            FFT_ROTATE: begin rot_real<=rotated_real[40:17]; rot_imag<=rotated_imag[40:17]; state<=FFT_WRITE_A; end
            FFT_WRITE_A: state<=FFT_WRITE_B;
            FFT_WRITE_B: begin
                if(butterfly==span[11:1]-1'b1) begin
                    butterfly<=0;
                    if({1'b0,group_base}+span==12'd2048) begin
                        group_base<=0;
                        if(stage==10) begin index<=0; state<=POWER_READ; end
                        else begin stage<=stage+1'b1; span<=span<<1; state<=FFT_READ_A; end
                    end else begin group_base<=group_base+span[10:0]; state<=FFT_READ_A; end
                end else begin butterfly<=butterfly+1'b1; state<=FFT_READ_A; end
            end
            POWER_READ: state<=POWER_MULT;
            POWER_MULT: begin square_real<=ram_real*ram_real; square_imag<=ram_imag*ram_imag; state<=POWER_SUM; end
            POWER_SUM: begin power_value<={1'b0,square_real}+{1'b0,square_imag}; state<=POWER_EXPONENT; end
            POWER_EXPONENT: begin power_exponent<=detected_exponent; state<=POWER_WRITE; end
            POWER_WRITE: if(index==1023) begin
                index<=0;
                if(channel) begin
                    index<=2;group_column<=0;clear_column<=0;band_left<=0;band_right<=0;
                    map_finishing<=0;state<=MAP_CLEAR;
                end
                else begin channel<=1; state<=LOAD_READ; end
            end else begin index<=index+1'b1; state<=POWER_READ; end
            MAP_CLEAR: if(clear_column==511) state<=MAP_READ;
                       else clear_column<=clear_column+1'b1;
            MAP_READ: state<=MAP_PEAK;
            MAP_PEAK: begin
                if(bin_column!=group_column) state<=MAP_WRITE;
                else begin
                    if(read_level_left>band_left) band_left<=read_level_left;
                    if(read_level_right>band_right) band_right<=read_level_right;
                    if(index==853) begin map_finishing<=1;state<=MAP_WRITE;end
                    else begin index<=index+1'b1;state<=MAP_READ;end
                end
            end
            MAP_WRITE: state<=MAP_BEGIN;
            MAP_BEGIN: begin
                if(map_finishing) begin ready<=1;state<=FRAME_READY;end
                else begin
                    // Revisit the unconsumed first bin of the next column.
                    group_column<=bin_column;band_left<=0;band_right<=0;state<=MAP_READ;
                end
            end
            FRAME_READY: if(release_frame) begin ready<=0; state<=WAIT_BLOCK; end
            default: begin ready<=0; state<=WAIT_BLOCK; end
        endcase
    end
endmodule

// Generated bin-to-column map. Each measured peak belongs to one bar.
module gw138k_spectrum_column_rom(input wire clk,input wire [9:0] bin,output reg [8:0] column);
    always @(posedge clk) case(bin)
        10'd0: column<=9'd0;
        10'd1: column<=9'd0;
        10'd2: column<=9'd0;
        10'd3: column<=9'd34;
        10'd4: column<=9'd58;
        10'd5: column<=9'd77;
        10'd6: column<=9'd93;
        10'd7: column<=9'd106;
        10'd8: column<=9'd117;
        10'd9: column<=9'd127;
        10'd10: column<=9'd136;
        10'd11: column<=9'd144;
        10'd12: column<=9'd151;
        10'd13: column<=9'd158;
        10'd14: column<=9'd164;
        10'd15: column<=9'd170;
        10'd16: column<=9'd175;
        10'd17: column<=9'd181;
        10'd18: column<=9'd185;
        10'd19: column<=9'd190;
        10'd20: column<=9'd194;
        10'd21: column<=9'd198;
        10'd22: column<=9'd202;
        10'd23: column<=9'd206;
        10'd24: column<=9'd210;
        10'd25: column<=9'd213;
        10'd26: column<=9'd216;
        10'd27: column<=9'd220;
        10'd28: column<=9'd223;
        10'd29: column<=9'd226;
        10'd30: column<=9'd229;
        10'd31: column<=9'd231;
        10'd32: column<=9'd234;
        10'd33: column<=9'd237;
        10'd34: column<=9'd239;
        10'd35: column<=9'd242;
        10'd36: column<=9'd244;
        10'd37: column<=9'd246;
        10'd38: column<=9'd248;
        10'd39: column<=9'd251;
        10'd40: column<=9'd253;
        10'd41: column<=9'd255;
        10'd42: column<=9'd257;
        10'd43: column<=9'd259;
        10'd44: column<=9'd261;
        10'd45: column<=9'd263;
        10'd46: column<=9'd265;
        10'd47: column<=9'd266;
        10'd48: column<=9'd268;
        10'd49: column<=9'd270;
        10'd50: column<=9'd272;
        10'd51: column<=9'd273;
        10'd52: column<=9'd275;
        10'd53: column<=9'd277;
        10'd54: column<=9'd278;
        10'd55: column<=9'd280;
        10'd56: column<=9'd281;
        10'd57: column<=9'd283;
        10'd58: column<=9'd284;
        10'd59: column<=9'd286;
        10'd60: column<=9'd287;
        10'd61: column<=9'd288;
        10'd62: column<=9'd290;
        10'd63: column<=9'd291;
        10'd64: column<=9'd292;
        10'd65: column<=9'd294;
        10'd66: column<=9'd295;
        10'd67: column<=9'd296;
        10'd68: column<=9'd298;
        10'd69: column<=9'd299;
        10'd70: column<=9'd300;
        10'd71: column<=9'd301;
        10'd72: column<=9'd302;
        10'd73: column<=9'd304;
        10'd74: column<=9'd305;
        10'd75: column<=9'd306;
        10'd76: column<=9'd307;
        10'd77: column<=9'd308;
        10'd78: column<=9'd309;
        10'd79: column<=9'd310;
        10'd80: column<=9'd311;
        10'd81: column<=9'd312;
        10'd82: column<=9'd313;
        10'd83: column<=9'd314;
        10'd84: column<=9'd315;
        10'd85: column<=9'd316;
        10'd86: column<=9'd317;
        10'd87: column<=9'd318;
        10'd88: column<=9'd319;
        10'd89: column<=9'd320;
        10'd90: column<=9'd321;
        10'd91: column<=9'd322;
        10'd92: column<=9'd323;
        10'd93: column<=9'd324;
        10'd94: column<=9'd325;
        10'd95: column<=9'd326;
        10'd96: column<=9'd327;
        10'd97: column<=9'd328;
        10'd98: column<=9'd328;
        10'd99: column<=9'd329;
        10'd100: column<=9'd330;
        10'd101: column<=9'd331;
        10'd102: column<=9'd332;
        10'd103: column<=9'd333;
        10'd104: column<=9'd333;
        10'd105: column<=9'd334;
        10'd106: column<=9'd335;
        10'd107: column<=9'd336;
        10'd108: column<=9'd337;
        10'd109: column<=9'd337;
        10'd110: column<=9'd338;
        10'd111: column<=9'd339;
        10'd112: column<=9'd340;
        10'd113: column<=9'd340;
        10'd114: column<=9'd341;
        10'd115: column<=9'd342;
        10'd116: column<=9'd343;
        10'd117: column<=9'd343;
        10'd118: column<=9'd344;
        10'd119: column<=9'd345;
        10'd120: column<=9'd345;
        10'd121: column<=9'd346;
        10'd122: column<=9'd347;
        10'd123: column<=9'd348;
        10'd124: column<=9'd348;
        10'd125: column<=9'd349;
        10'd126: column<=9'd350;
        10'd127: column<=9'd350;
        10'd128: column<=9'd351;
        10'd129: column<=9'd352;
        10'd130: column<=9'd352;
        10'd131: column<=9'd353;
        10'd132: column<=9'd354;
        10'd133: column<=9'd354;
        10'd134: column<=9'd355;
        10'd135: column<=9'd355;
        10'd136: column<=9'd356;
        10'd137: column<=9'd357;
        10'd138: column<=9'd357;
        10'd139: column<=9'd358;
        10'd140: column<=9'd359;
        10'd141: column<=9'd359;
        10'd142: column<=9'd360;
        10'd143: column<=9'd360;
        10'd144: column<=9'd361;
        10'd145: column<=9'd361;
        10'd146: column<=9'd362;
        10'd147: column<=9'd363;
        10'd148: column<=9'd363;
        10'd149: column<=9'd364;
        10'd150: column<=9'd364;
        10'd151: column<=9'd365;
        10'd152: column<=9'd365;
        10'd153: column<=9'd366;
        10'd154: column<=9'd367;
        10'd155: column<=9'd367;
        10'd156: column<=9'd368;
        10'd157: column<=9'd368;
        10'd158: column<=9'd369;
        10'd159: column<=9'd369;
        10'd160: column<=9'd370;
        10'd161: column<=9'd370;
        10'd162: column<=9'd371;
        10'd163: column<=9'd371;
        10'd164: column<=9'd372;
        10'd165: column<=9'd372;
        10'd166: column<=9'd373;
        10'd167: column<=9'd373;
        10'd168: column<=9'd374;
        10'd169: column<=9'd374;
        10'd170: column<=9'd375;
        10'd171: column<=9'd375;
        10'd172: column<=9'd376;
        10'd173: column<=9'd376;
        10'd174: column<=9'd377;
        10'd175: column<=9'd377;
        10'd176: column<=9'd378;
        10'd177: column<=9'd378;
        10'd178: column<=9'd379;
        10'd179: column<=9'd379;
        10'd180: column<=9'd380;
        10'd181: column<=9'd380;
        10'd182: column<=9'd381;
        10'd183: column<=9'd381;
        10'd184: column<=9'd382;
        10'd185: column<=9'd382;
        10'd186: column<=9'd382;
        10'd187: column<=9'd383;
        10'd188: column<=9'd383;
        10'd189: column<=9'd384;
        10'd190: column<=9'd384;
        10'd191: column<=9'd385;
        10'd192: column<=9'd385;
        10'd193: column<=9'd386;
        10'd194: column<=9'd386;
        10'd195: column<=9'd386;
        10'd196: column<=9'd387;
        10'd197: column<=9'd387;
        10'd198: column<=9'd388;
        10'd199: column<=9'd388;
        10'd200: column<=9'd389;
        10'd201: column<=9'd389;
        10'd202: column<=9'd389;
        10'd203: column<=9'd390;
        10'd204: column<=9'd390;
        10'd205: column<=9'd391;
        10'd206: column<=9'd391;
        10'd207: column<=9'd392;
        10'd208: column<=9'd392;
        10'd209: column<=9'd392;
        10'd210: column<=9'd393;
        10'd211: column<=9'd393;
        10'd212: column<=9'd394;
        10'd213: column<=9'd394;
        10'd214: column<=9'd394;
        10'd215: column<=9'd395;
        10'd216: column<=9'd395;
        10'd217: column<=9'd395;
        10'd218: column<=9'd396;
        10'd219: column<=9'd396;
        10'd220: column<=9'd397;
        10'd221: column<=9'd397;
        10'd222: column<=9'd397;
        10'd223: column<=9'd398;
        10'd224: column<=9'd398;
        10'd225: column<=9'd399;
        10'd226: column<=9'd399;
        10'd227: column<=9'd399;
        10'd228: column<=9'd400;
        10'd229: column<=9'd400;
        10'd230: column<=9'd400;
        10'd231: column<=9'd401;
        10'd232: column<=9'd401;
        10'd233: column<=9'd401;
        10'd234: column<=9'd402;
        10'd235: column<=9'd402;
        10'd236: column<=9'd403;
        10'd237: column<=9'd403;
        10'd238: column<=9'd403;
        10'd239: column<=9'd404;
        10'd240: column<=9'd404;
        10'd241: column<=9'd404;
        10'd242: column<=9'd405;
        10'd243: column<=9'd405;
        10'd244: column<=9'd405;
        10'd245: column<=9'd406;
        10'd246: column<=9'd406;
        10'd247: column<=9'd406;
        10'd248: column<=9'd407;
        10'd249: column<=9'd407;
        10'd250: column<=9'd407;
        10'd251: column<=9'd408;
        10'd252: column<=9'd408;
        10'd253: column<=9'd408;
        10'd254: column<=9'd409;
        10'd255: column<=9'd409;
        10'd256: column<=9'd409;
        10'd257: column<=9'd410;
        10'd258: column<=9'd410;
        10'd259: column<=9'd410;
        10'd260: column<=9'd411;
        10'd261: column<=9'd411;
        10'd262: column<=9'd411;
        10'd263: column<=9'd412;
        10'd264: column<=9'd412;
        10'd265: column<=9'd412;
        10'd266: column<=9'd413;
        10'd267: column<=9'd413;
        10'd268: column<=9'd413;
        10'd269: column<=9'd414;
        10'd270: column<=9'd414;
        10'd271: column<=9'd414;
        10'd272: column<=9'd415;
        10'd273: column<=9'd415;
        10'd274: column<=9'd415;
        10'd275: column<=9'd415;
        10'd276: column<=9'd416;
        10'd277: column<=9'd416;
        10'd278: column<=9'd416;
        10'd279: column<=9'd417;
        10'd280: column<=9'd417;
        10'd281: column<=9'd417;
        10'd282: column<=9'd418;
        10'd283: column<=9'd418;
        10'd284: column<=9'd418;
        10'd285: column<=9'd418;
        10'd286: column<=9'd419;
        10'd287: column<=9'd419;
        10'd288: column<=9'd419;
        10'd289: column<=9'd420;
        10'd290: column<=9'd420;
        10'd291: column<=9'd420;
        10'd292: column<=9'd421;
        10'd293: column<=9'd421;
        10'd294: column<=9'd421;
        10'd295: column<=9'd421;
        10'd296: column<=9'd422;
        10'd297: column<=9'd422;
        10'd298: column<=9'd422;
        10'd299: column<=9'd423;
        10'd300: column<=9'd423;
        10'd301: column<=9'd423;
        10'd302: column<=9'd423;
        10'd303: column<=9'd424;
        10'd304: column<=9'd424;
        10'd305: column<=9'd424;
        10'd306: column<=9'd424;
        10'd307: column<=9'd425;
        10'd308: column<=9'd425;
        10'd309: column<=9'd425;
        10'd310: column<=9'd426;
        10'd311: column<=9'd426;
        10'd312: column<=9'd426;
        10'd313: column<=9'd426;
        10'd314: column<=9'd427;
        10'd315: column<=9'd427;
        10'd316: column<=9'd427;
        10'd317: column<=9'd427;
        10'd318: column<=9'd428;
        10'd319: column<=9'd428;
        10'd320: column<=9'd428;
        10'd321: column<=9'd429;
        10'd322: column<=9'd429;
        10'd323: column<=9'd429;
        10'd324: column<=9'd429;
        10'd325: column<=9'd430;
        10'd326: column<=9'd430;
        10'd327: column<=9'd430;
        10'd328: column<=9'd430;
        10'd329: column<=9'd431;
        10'd330: column<=9'd431;
        10'd331: column<=9'd431;
        10'd332: column<=9'd431;
        10'd333: column<=9'd432;
        10'd334: column<=9'd432;
        10'd335: column<=9'd432;
        10'd336: column<=9'd432;
        10'd337: column<=9'd433;
        10'd338: column<=9'd433;
        10'd339: column<=9'd433;
        10'd340: column<=9'd433;
        10'd341: column<=9'd434;
        10'd342: column<=9'd434;
        10'd343: column<=9'd434;
        10'd344: column<=9'd434;
        10'd345: column<=9'd435;
        10'd346: column<=9'd435;
        10'd347: column<=9'd435;
        10'd348: column<=9'd435;
        10'd349: column<=9'd436;
        10'd350: column<=9'd436;
        10'd351: column<=9'd436;
        10'd352: column<=9'd436;
        10'd353: column<=9'd437;
        10'd354: column<=9'd437;
        10'd355: column<=9'd437;
        10'd356: column<=9'd437;
        10'd357: column<=9'd437;
        10'd358: column<=9'd438;
        10'd359: column<=9'd438;
        10'd360: column<=9'd438;
        10'd361: column<=9'd438;
        10'd362: column<=9'd439;
        10'd363: column<=9'd439;
        10'd364: column<=9'd439;
        10'd365: column<=9'd439;
        10'd366: column<=9'd440;
        10'd367: column<=9'd440;
        10'd368: column<=9'd440;
        10'd369: column<=9'd440;
        10'd370: column<=9'd441;
        10'd371: column<=9'd441;
        10'd372: column<=9'd441;
        10'd373: column<=9'd441;
        10'd374: column<=9'd441;
        10'd375: column<=9'd442;
        10'd376: column<=9'd442;
        10'd377: column<=9'd442;
        10'd378: column<=9'd442;
        10'd379: column<=9'd443;
        10'd380: column<=9'd443;
        10'd381: column<=9'd443;
        10'd382: column<=9'd443;
        10'd383: column<=9'd443;
        10'd384: column<=9'd444;
        10'd385: column<=9'd444;
        10'd386: column<=9'd444;
        10'd387: column<=9'd444;
        10'd388: column<=9'd445;
        10'd389: column<=9'd445;
        10'd390: column<=9'd445;
        10'd391: column<=9'd445;
        10'd392: column<=9'd445;
        10'd393: column<=9'd446;
        10'd394: column<=9'd446;
        10'd395: column<=9'd446;
        10'd396: column<=9'd446;
        10'd397: column<=9'd446;
        10'd398: column<=9'd447;
        10'd399: column<=9'd447;
        10'd400: column<=9'd447;
        10'd401: column<=9'd447;
        10'd402: column<=9'd448;
        10'd403: column<=9'd448;
        10'd404: column<=9'd448;
        10'd405: column<=9'd448;
        10'd406: column<=9'd448;
        10'd407: column<=9'd449;
        10'd408: column<=9'd449;
        10'd409: column<=9'd449;
        10'd410: column<=9'd449;
        10'd411: column<=9'd449;
        10'd412: column<=9'd450;
        10'd413: column<=9'd450;
        10'd414: column<=9'd450;
        10'd415: column<=9'd450;
        10'd416: column<=9'd450;
        10'd417: column<=9'd451;
        10'd418: column<=9'd451;
        10'd419: column<=9'd451;
        10'd420: column<=9'd451;
        10'd421: column<=9'd451;
        10'd422: column<=9'd452;
        10'd423: column<=9'd452;
        10'd424: column<=9'd452;
        10'd425: column<=9'd452;
        10'd426: column<=9'd452;
        10'd427: column<=9'd453;
        10'd428: column<=9'd453;
        10'd429: column<=9'd453;
        10'd430: column<=9'd453;
        10'd431: column<=9'd453;
        10'd432: column<=9'd454;
        10'd433: column<=9'd454;
        10'd434: column<=9'd454;
        10'd435: column<=9'd454;
        10'd436: column<=9'd454;
        10'd437: column<=9'd455;
        10'd438: column<=9'd455;
        10'd439: column<=9'd455;
        10'd440: column<=9'd455;
        10'd441: column<=9'd455;
        10'd442: column<=9'd456;
        10'd443: column<=9'd456;
        10'd444: column<=9'd456;
        10'd445: column<=9'd456;
        10'd446: column<=9'd456;
        10'd447: column<=9'd456;
        10'd448: column<=9'd457;
        10'd449: column<=9'd457;
        10'd450: column<=9'd457;
        10'd451: column<=9'd457;
        10'd452: column<=9'd457;
        10'd453: column<=9'd458;
        10'd454: column<=9'd458;
        10'd455: column<=9'd458;
        10'd456: column<=9'd458;
        10'd457: column<=9'd458;
        10'd458: column<=9'd459;
        10'd459: column<=9'd459;
        10'd460: column<=9'd459;
        10'd461: column<=9'd459;
        10'd462: column<=9'd459;
        10'd463: column<=9'd459;
        10'd464: column<=9'd460;
        10'd465: column<=9'd460;
        10'd466: column<=9'd460;
        10'd467: column<=9'd460;
        10'd468: column<=9'd460;
        10'd469: column<=9'd461;
        10'd470: column<=9'd461;
        10'd471: column<=9'd461;
        10'd472: column<=9'd461;
        10'd473: column<=9'd461;
        10'd474: column<=9'd461;
        10'd475: column<=9'd462;
        10'd476: column<=9'd462;
        10'd477: column<=9'd462;
        10'd478: column<=9'd462;
        10'd479: column<=9'd462;
        10'd480: column<=9'd462;
        10'd481: column<=9'd463;
        10'd482: column<=9'd463;
        10'd483: column<=9'd463;
        10'd484: column<=9'd463;
        10'd485: column<=9'd463;
        10'd486: column<=9'd464;
        10'd487: column<=9'd464;
        10'd488: column<=9'd464;
        10'd489: column<=9'd464;
        10'd490: column<=9'd464;
        10'd491: column<=9'd464;
        10'd492: column<=9'd465;
        10'd493: column<=9'd465;
        10'd494: column<=9'd465;
        10'd495: column<=9'd465;
        10'd496: column<=9'd465;
        10'd497: column<=9'd465;
        10'd498: column<=9'd466;
        10'd499: column<=9'd466;
        10'd500: column<=9'd466;
        10'd501: column<=9'd466;
        10'd502: column<=9'd466;
        10'd503: column<=9'd466;
        10'd504: column<=9'd467;
        10'd505: column<=9'd467;
        10'd506: column<=9'd467;
        10'd507: column<=9'd467;
        10'd508: column<=9'd467;
        10'd509: column<=9'd467;
        10'd510: column<=9'd468;
        10'd511: column<=9'd468;
        10'd512: column<=9'd468;
        10'd513: column<=9'd468;
        10'd514: column<=9'd468;
        10'd515: column<=9'd468;
        10'd516: column<=9'd469;
        10'd517: column<=9'd469;
        10'd518: column<=9'd469;
        10'd519: column<=9'd469;
        10'd520: column<=9'd469;
        10'd521: column<=9'd469;
        10'd522: column<=9'd470;
        10'd523: column<=9'd470;
        10'd524: column<=9'd470;
        10'd525: column<=9'd470;
        10'd526: column<=9'd470;
        10'd527: column<=9'd470;
        10'd528: column<=9'd471;
        10'd529: column<=9'd471;
        10'd530: column<=9'd471;
        10'd531: column<=9'd471;
        10'd532: column<=9'd471;
        10'd533: column<=9'd471;
        10'd534: column<=9'd471;
        10'd535: column<=9'd472;
        10'd536: column<=9'd472;
        10'd537: column<=9'd472;
        10'd538: column<=9'd472;
        10'd539: column<=9'd472;
        10'd540: column<=9'd472;
        10'd541: column<=9'd473;
        10'd542: column<=9'd473;
        10'd543: column<=9'd473;
        10'd544: column<=9'd473;
        10'd545: column<=9'd473;
        10'd546: column<=9'd473;
        10'd547: column<=9'd474;
        10'd548: column<=9'd474;
        10'd549: column<=9'd474;
        10'd550: column<=9'd474;
        10'd551: column<=9'd474;
        10'd552: column<=9'd474;
        10'd553: column<=9'd474;
        10'd554: column<=9'd475;
        10'd555: column<=9'd475;
        10'd556: column<=9'd475;
        10'd557: column<=9'd475;
        10'd558: column<=9'd475;
        10'd559: column<=9'd475;
        10'd560: column<=9'd475;
        10'd561: column<=9'd476;
        10'd562: column<=9'd476;
        10'd563: column<=9'd476;
        10'd564: column<=9'd476;
        10'd565: column<=9'd476;
        10'd566: column<=9'd476;
        10'd567: column<=9'd477;
        10'd568: column<=9'd477;
        10'd569: column<=9'd477;
        10'd570: column<=9'd477;
        10'd571: column<=9'd477;
        10'd572: column<=9'd477;
        10'd573: column<=9'd477;
        10'd574: column<=9'd478;
        10'd575: column<=9'd478;
        10'd576: column<=9'd478;
        10'd577: column<=9'd478;
        10'd578: column<=9'd478;
        10'd579: column<=9'd478;
        10'd580: column<=9'd478;
        10'd581: column<=9'd479;
        10'd582: column<=9'd479;
        10'd583: column<=9'd479;
        10'd584: column<=9'd479;
        10'd585: column<=9'd479;
        10'd586: column<=9'd479;
        10'd587: column<=9'd479;
        10'd588: column<=9'd480;
        10'd589: column<=9'd480;
        10'd590: column<=9'd480;
        10'd591: column<=9'd480;
        10'd592: column<=9'd480;
        10'd593: column<=9'd480;
        10'd594: column<=9'd480;
        10'd595: column<=9'd481;
        10'd596: column<=9'd481;
        10'd597: column<=9'd481;
        10'd598: column<=9'd481;
        10'd599: column<=9'd481;
        10'd600: column<=9'd481;
        10'd601: column<=9'd481;
        10'd602: column<=9'd482;
        10'd603: column<=9'd482;
        10'd604: column<=9'd482;
        10'd605: column<=9'd482;
        10'd606: column<=9'd482;
        10'd607: column<=9'd482;
        10'd608: column<=9'd482;
        10'd609: column<=9'd483;
        10'd610: column<=9'd483;
        10'd611: column<=9'd483;
        10'd612: column<=9'd483;
        10'd613: column<=9'd483;
        10'd614: column<=9'd483;
        10'd615: column<=9'd483;
        10'd616: column<=9'd484;
        10'd617: column<=9'd484;
        10'd618: column<=9'd484;
        10'd619: column<=9'd484;
        10'd620: column<=9'd484;
        10'd621: column<=9'd484;
        10'd622: column<=9'd484;
        10'd623: column<=9'd484;
        10'd624: column<=9'd485;
        10'd625: column<=9'd485;
        10'd626: column<=9'd485;
        10'd627: column<=9'd485;
        10'd628: column<=9'd485;
        10'd629: column<=9'd485;
        10'd630: column<=9'd485;
        10'd631: column<=9'd486;
        10'd632: column<=9'd486;
        10'd633: column<=9'd486;
        10'd634: column<=9'd486;
        10'd635: column<=9'd486;
        10'd636: column<=9'd486;
        10'd637: column<=9'd486;
        10'd638: column<=9'd486;
        10'd639: column<=9'd487;
        10'd640: column<=9'd487;
        10'd641: column<=9'd487;
        10'd642: column<=9'd487;
        10'd643: column<=9'd487;
        10'd644: column<=9'd487;
        10'd645: column<=9'd487;
        10'd646: column<=9'd488;
        10'd647: column<=9'd488;
        10'd648: column<=9'd488;
        10'd649: column<=9'd488;
        10'd650: column<=9'd488;
        10'd651: column<=9'd488;
        10'd652: column<=9'd488;
        10'd653: column<=9'd488;
        10'd654: column<=9'd489;
        10'd655: column<=9'd489;
        10'd656: column<=9'd489;
        10'd657: column<=9'd489;
        10'd658: column<=9'd489;
        10'd659: column<=9'd489;
        10'd660: column<=9'd489;
        10'd661: column<=9'd489;
        10'd662: column<=9'd490;
        10'd663: column<=9'd490;
        10'd664: column<=9'd490;
        10'd665: column<=9'd490;
        10'd666: column<=9'd490;
        10'd667: column<=9'd490;
        10'd668: column<=9'd490;
        10'd669: column<=9'd490;
        10'd670: column<=9'd491;
        10'd671: column<=9'd491;
        10'd672: column<=9'd491;
        10'd673: column<=9'd491;
        10'd674: column<=9'd491;
        10'd675: column<=9'd491;
        10'd676: column<=9'd491;
        10'd677: column<=9'd491;
        10'd678: column<=9'd492;
        10'd679: column<=9'd492;
        10'd680: column<=9'd492;
        10'd681: column<=9'd492;
        10'd682: column<=9'd492;
        10'd683: column<=9'd492;
        10'd684: column<=9'd492;
        10'd685: column<=9'd492;
        10'd686: column<=9'd493;
        10'd687: column<=9'd493;
        10'd688: column<=9'd493;
        10'd689: column<=9'd493;
        10'd690: column<=9'd493;
        10'd691: column<=9'd493;
        10'd692: column<=9'd493;
        10'd693: column<=9'd493;
        10'd694: column<=9'd494;
        10'd695: column<=9'd494;
        10'd696: column<=9'd494;
        10'd697: column<=9'd494;
        10'd698: column<=9'd494;
        10'd699: column<=9'd494;
        10'd700: column<=9'd494;
        10'd701: column<=9'd494;
        10'd702: column<=9'd495;
        10'd703: column<=9'd495;
        10'd704: column<=9'd495;
        10'd705: column<=9'd495;
        10'd706: column<=9'd495;
        10'd707: column<=9'd495;
        10'd708: column<=9'd495;
        10'd709: column<=9'd495;
        10'd710: column<=9'd496;
        10'd711: column<=9'd496;
        10'd712: column<=9'd496;
        10'd713: column<=9'd496;
        10'd714: column<=9'd496;
        10'd715: column<=9'd496;
        10'd716: column<=9'd496;
        10'd717: column<=9'd496;
        10'd718: column<=9'd496;
        10'd719: column<=9'd497;
        10'd720: column<=9'd497;
        10'd721: column<=9'd497;
        10'd722: column<=9'd497;
        10'd723: column<=9'd497;
        10'd724: column<=9'd497;
        10'd725: column<=9'd497;
        10'd726: column<=9'd497;
        10'd727: column<=9'd498;
        10'd728: column<=9'd498;
        10'd729: column<=9'd498;
        10'd730: column<=9'd498;
        10'd731: column<=9'd498;
        10'd732: column<=9'd498;
        10'd733: column<=9'd498;
        10'd734: column<=9'd498;
        10'd735: column<=9'd498;
        10'd736: column<=9'd499;
        10'd737: column<=9'd499;
        10'd738: column<=9'd499;
        10'd739: column<=9'd499;
        10'd740: column<=9'd499;
        10'd741: column<=9'd499;
        10'd742: column<=9'd499;
        10'd743: column<=9'd499;
        10'd744: column<=9'd499;
        10'd745: column<=9'd500;
        10'd746: column<=9'd500;
        10'd747: column<=9'd500;
        10'd748: column<=9'd500;
        10'd749: column<=9'd500;
        10'd750: column<=9'd500;
        10'd751: column<=9'd500;
        10'd752: column<=9'd500;
        10'd753: column<=9'd500;
        10'd754: column<=9'd501;
        10'd755: column<=9'd501;
        10'd756: column<=9'd501;
        10'd757: column<=9'd501;
        10'd758: column<=9'd501;
        10'd759: column<=9'd501;
        10'd760: column<=9'd501;
        10'd761: column<=9'd501;
        10'd762: column<=9'd501;
        10'd763: column<=9'd502;
        10'd764: column<=9'd502;
        10'd765: column<=9'd502;
        10'd766: column<=9'd502;
        10'd767: column<=9'd502;
        10'd768: column<=9'd502;
        10'd769: column<=9'd502;
        10'd770: column<=9'd502;
        10'd771: column<=9'd502;
        10'd772: column<=9'd503;
        10'd773: column<=9'd503;
        10'd774: column<=9'd503;
        10'd775: column<=9'd503;
        10'd776: column<=9'd503;
        10'd777: column<=9'd503;
        10'd778: column<=9'd503;
        10'd779: column<=9'd503;
        10'd780: column<=9'd503;
        10'd781: column<=9'd504;
        10'd782: column<=9'd504;
        10'd783: column<=9'd504;
        10'd784: column<=9'd504;
        10'd785: column<=9'd504;
        10'd786: column<=9'd504;
        10'd787: column<=9'd504;
        10'd788: column<=9'd504;
        10'd789: column<=9'd504;
        10'd790: column<=9'd505;
        10'd791: column<=9'd505;
        10'd792: column<=9'd505;
        10'd793: column<=9'd505;
        10'd794: column<=9'd505;
        10'd795: column<=9'd505;
        10'd796: column<=9'd505;
        10'd797: column<=9'd505;
        10'd798: column<=9'd505;
        10'd799: column<=9'd505;
        10'd800: column<=9'd506;
        10'd801: column<=9'd506;
        10'd802: column<=9'd506;
        10'd803: column<=9'd506;
        10'd804: column<=9'd506;
        10'd805: column<=9'd506;
        10'd806: column<=9'd506;
        10'd807: column<=9'd506;
        10'd808: column<=9'd506;
        10'd809: column<=9'd507;
        10'd810: column<=9'd507;
        10'd811: column<=9'd507;
        10'd812: column<=9'd507;
        10'd813: column<=9'd507;
        10'd814: column<=9'd507;
        10'd815: column<=9'd507;
        10'd816: column<=9'd507;
        10'd817: column<=9'd507;
        10'd818: column<=9'd507;
        10'd819: column<=9'd508;
        10'd820: column<=9'd508;
        10'd821: column<=9'd508;
        10'd822: column<=9'd508;
        10'd823: column<=9'd508;
        10'd824: column<=9'd508;
        10'd825: column<=9'd508;
        10'd826: column<=9'd508;
        10'd827: column<=9'd508;
        10'd828: column<=9'd508;
        10'd829: column<=9'd509;
        10'd830: column<=9'd509;
        10'd831: column<=9'd509;
        10'd832: column<=9'd509;
        10'd833: column<=9'd509;
        10'd834: column<=9'd509;
        10'd835: column<=9'd509;
        10'd836: column<=9'd509;
        10'd837: column<=9'd509;
        10'd838: column<=9'd510;
        10'd839: column<=9'd510;
        10'd840: column<=9'd510;
        10'd841: column<=9'd510;
        10'd842: column<=9'd510;
        10'd843: column<=9'd510;
        10'd844: column<=9'd510;
        10'd845: column<=9'd510;
        10'd846: column<=9'd510;
        10'd847: column<=9'd510;
        10'd848: column<=9'd511;
        10'd849: column<=9'd511;
        10'd850: column<=9'd511;
        10'd851: column<=9'd511;
        10'd852: column<=9'd511;
        10'd853: column<=9'd511;
        10'd854: column<=9'd511;
        10'd855: column<=9'd511;
        10'd856: column<=9'd511;
        10'd857: column<=9'd511;
        10'd858: column<=9'd511;
        10'd859: column<=9'd511;
        10'd860: column<=9'd511;
        10'd861: column<=9'd511;
        10'd862: column<=9'd511;
        10'd863: column<=9'd511;
        10'd864: column<=9'd511;
        10'd865: column<=9'd511;
        10'd866: column<=9'd511;
        10'd867: column<=9'd511;
        10'd868: column<=9'd511;
        10'd869: column<=9'd511;
        10'd870: column<=9'd511;
        10'd871: column<=9'd511;
        10'd872: column<=9'd511;
        10'd873: column<=9'd511;
        10'd874: column<=9'd511;
        10'd875: column<=9'd511;
        10'd876: column<=9'd511;
        10'd877: column<=9'd511;
        10'd878: column<=9'd511;
        10'd879: column<=9'd511;
        10'd880: column<=9'd511;
        10'd881: column<=9'd511;
        10'd882: column<=9'd511;
        10'd883: column<=9'd511;
        10'd884: column<=9'd511;
        10'd885: column<=9'd511;
        10'd886: column<=9'd511;
        10'd887: column<=9'd511;
        10'd888: column<=9'd511;
        10'd889: column<=9'd511;
        10'd890: column<=9'd511;
        10'd891: column<=9'd511;
        10'd892: column<=9'd511;
        10'd893: column<=9'd511;
        10'd894: column<=9'd511;
        10'd895: column<=9'd511;
        10'd896: column<=9'd511;
        10'd897: column<=9'd511;
        10'd898: column<=9'd511;
        10'd899: column<=9'd511;
        10'd900: column<=9'd511;
        10'd901: column<=9'd511;
        10'd902: column<=9'd511;
        10'd903: column<=9'd511;
        10'd904: column<=9'd511;
        10'd905: column<=9'd511;
        10'd906: column<=9'd511;
        10'd907: column<=9'd511;
        10'd908: column<=9'd511;
        10'd909: column<=9'd511;
        10'd910: column<=9'd511;
        10'd911: column<=9'd511;
        10'd912: column<=9'd511;
        10'd913: column<=9'd511;
        10'd914: column<=9'd511;
        10'd915: column<=9'd511;
        10'd916: column<=9'd511;
        10'd917: column<=9'd511;
        10'd918: column<=9'd511;
        10'd919: column<=9'd511;
        10'd920: column<=9'd511;
        10'd921: column<=9'd511;
        10'd922: column<=9'd511;
        10'd923: column<=9'd511;
        10'd924: column<=9'd511;
        10'd925: column<=9'd511;
        10'd926: column<=9'd511;
        10'd927: column<=9'd511;
        10'd928: column<=9'd511;
        10'd929: column<=9'd511;
        10'd930: column<=9'd511;
        10'd931: column<=9'd511;
        10'd932: column<=9'd511;
        10'd933: column<=9'd511;
        10'd934: column<=9'd511;
        10'd935: column<=9'd511;
        10'd936: column<=9'd511;
        10'd937: column<=9'd511;
        10'd938: column<=9'd511;
        10'd939: column<=9'd511;
        10'd940: column<=9'd511;
        10'd941: column<=9'd511;
        10'd942: column<=9'd511;
        10'd943: column<=9'd511;
        10'd944: column<=9'd511;
        10'd945: column<=9'd511;
        10'd946: column<=9'd511;
        10'd947: column<=9'd511;
        10'd948: column<=9'd511;
        10'd949: column<=9'd511;
        10'd950: column<=9'd511;
        10'd951: column<=9'd511;
        10'd952: column<=9'd511;
        10'd953: column<=9'd511;
        10'd954: column<=9'd511;
        10'd955: column<=9'd511;
        10'd956: column<=9'd511;
        10'd957: column<=9'd511;
        10'd958: column<=9'd511;
        10'd959: column<=9'd511;
        10'd960: column<=9'd511;
        10'd961: column<=9'd511;
        10'd962: column<=9'd511;
        10'd963: column<=9'd511;
        10'd964: column<=9'd511;
        10'd965: column<=9'd511;
        10'd966: column<=9'd511;
        10'd967: column<=9'd511;
        10'd968: column<=9'd511;
        10'd969: column<=9'd511;
        10'd970: column<=9'd511;
        10'd971: column<=9'd511;
        10'd972: column<=9'd511;
        10'd973: column<=9'd511;
        10'd974: column<=9'd511;
        10'd975: column<=9'd511;
        10'd976: column<=9'd511;
        10'd977: column<=9'd511;
        10'd978: column<=9'd511;
        10'd979: column<=9'd511;
        10'd980: column<=9'd511;
        10'd981: column<=9'd511;
        10'd982: column<=9'd511;
        10'd983: column<=9'd511;
        10'd984: column<=9'd511;
        10'd985: column<=9'd511;
        10'd986: column<=9'd511;
        10'd987: column<=9'd511;
        10'd988: column<=9'd511;
        10'd989: column<=9'd511;
        10'd990: column<=9'd511;
        10'd991: column<=9'd511;
        10'd992: column<=9'd511;
        10'd993: column<=9'd511;
        10'd994: column<=9'd511;
        10'd995: column<=9'd511;
        10'd996: column<=9'd511;
        10'd997: column<=9'd511;
        10'd998: column<=9'd511;
        10'd999: column<=9'd511;
        10'd1000: column<=9'd511;
        10'd1001: column<=9'd511;
        10'd1002: column<=9'd511;
        10'd1003: column<=9'd511;
        10'd1004: column<=9'd511;
        10'd1005: column<=9'd511;
        10'd1006: column<=9'd511;
        10'd1007: column<=9'd511;
        10'd1008: column<=9'd511;
        10'd1009: column<=9'd511;
        10'd1010: column<=9'd511;
        10'd1011: column<=9'd511;
        10'd1012: column<=9'd511;
        10'd1013: column<=9'd511;
        10'd1014: column<=9'd511;
        10'd1015: column<=9'd511;
        10'd1016: column<=9'd511;
        10'd1017: column<=9'd511;
        10'd1018: column<=9'd511;
        10'd1019: column<=9'd511;
        10'd1020: column<=9'd511;
        10'd1021: column<=9'd511;
        10'd1022: column<=9'd511;
        10'd1023: column<=9'd511;
        default: column<=0;
    endcase
endmodule
`default_nettype wire
