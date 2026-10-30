`default_nettype none
// Copy one committed compact display snapshot from DDR into the HDMI working
// cache. Legacy minor0 stops its renderer during an automatic retry. Explicit
// minor1 uses two compact local banks to retain the last validated image on
// failure. One DDR read may be outstanding; neither mode backpressures audio.
module display_data_reader #(
    parameter integer METADATA_MINOR=0
) (
    input wire clk,rst_n,enabled,start,
    output wire busy,
    output reg done,valid,fault,
    output wire req_valid,
    input wire req_ready,
    output reg [28:0] req_addr,
    input wire rsp_valid,
    input wire [255:0] rsp_data,
    input wire render_read_enable,
    input wire [8:0] render_wave_addr,
    input wire [15:0] render_image_addr,
    input wire [8:0] render_spectrum_column,
    output wire [31:0] render_wave_data,
    output wire render_image_hit,
    output wire [7:0] render_spectrum_left,render_spectrum_right,
    output reg [255:0] render_meta,
    output reg [31:0] render_analysis_sequence,render_analysis_skipped,render_stereo_peaks,
    output reg [2:0] render_image_gain,
    output reg render_analysis_valid,
    output reg [31:0] render_frame_sequence,
    output reg [31:0] render_sample_rate_o,render_epoch_o,render_generation_o,
    output reg render_context_changed_o,incompatible_o,
    output reg [3:0] diagnostic_code_o
);
    import display_data_layout_pkg::*;
    localparam [7:0] SELECTED_MINOR=8'(METADATA_MINOR);
    localparam integer CACHE_BANKS=METADATA_MINOR==1 ? 2:1;
    localparam integer WAVE_ADDR_BITS=9+(METADATA_MINOR==1),IMAGE_ADDR_BITS=11+(METADATA_MINOR==1);
    initial if(METADATA_MINOR<0 || METADATA_MINOR>1)$fatal(1,"display reader minor selection unsupported");
    localparam [4:0] IDLE=0,REQ_GLOBAL=1,WAIT_GLOBAL=2,PARSE_GLOBAL=3,REQ_HEADER=4,WAIT_HEADER=5,
        PARSE_HEADER=6,REQ_DESC=7,WAIT_DESC=8,PARSE_DESC=9,REQ_PAYLOAD=10,WAIT_PAYLOAD=11,
        PARSE_PAYLOAD=12,REQ_FINAL=13,WAIT_FINAL=14,PARSE_FINAL=15,STORE_PAYLOAD=16,
        FINAL_CMP0=17,FINAL_CMP1=18,FINAL_CMP2=19,FINAL_CMP3=20,FINAL_CHECK=21,PUBLISH=22,
        GLOBAL_CHECK=23,HEADER_CMP0=24,HEADER_CMP1=25,HEADER_CMP2=26,HEADER_CMP3=27,HEADER_CHECK=28,DESC_CHECK=29;
    reg [4:0] state;
    reg bank,analysis_valid_q;
    reg [2:0] descriptor_beat;
    reg [1:0] payload_kind;
    reg [7:0] payload_beat;
    reg [28:0] header_addr,descriptor_base;
    reg [28:0] payload_base[0:3];
    reg [31:0] descriptor_source[0:3],descriptor_gain[0:3];
    reg [255:0] global_q,header_q,meta_lo_q,meta_hi_q;
    reg [3:0] unpack_lane;
    reg [8:0] spectrum_address_q;
    // Minor1 keeps the previous validated local image while a working bank is
    // copied. A failed final seqlock never changes this published bank.
    reg [31:0] wave_cache[0:CACHE_BANKS*512-1],image_cache[0:CACHE_BANKS*2048-1];
    reg [15:0] spectrum_cache[0:CACHE_BANKS*512-1];
    reg published_bank;
    wire working_bank=METADATA_MINOR==1 ? !published_bank : 1'b0;
    wire render_bank=METADATA_MINOR==1 && state==PUBLISH ? working_bank : published_bank;
    wire [WAVE_ADDR_BITS-1:0] wave_write_addr=WAVE_ADDR_BITS'({working_bank,payload_beat[5:0],unpack_lane[2:0]});
    wire [IMAGE_ADDR_BITS-1:0] image_write_addr=IMAGE_ADDR_BITS'({working_bank,payload_beat,unpack_lane[2:0]});
    wire [WAVE_ADDR_BITS-1:0] spectrum_write_addr=WAVE_ADDR_BITS'({working_bank,payload_beat[4:0],unpack_lane});
    wire [WAVE_ADDR_BITS-1:0] wave_render_addr=WAVE_ADDR_BITS'({render_bank,render_wave_addr});
    wire [IMAGE_ADDR_BITS-1:0] image_render_addr=IMAGE_ADDR_BITS'({render_bank,render_image_addr[15:5]});
    wire [WAVE_ADDR_BITS-1:0] spectrum_render_addr=WAVE_ADDR_BITS'({render_bank,spectrum_address_q});
    reg [31:0] snapshot_rate_q,snapshot_epoch_q;
    reg [255:0] payload_q;
    reg [255:0] rsp_q;
    reg final_bad_q,final_meta_ok_q,global_ok_q,header_bad_q,desc_ok_q;
    reg [31:0] wave_data_q,image_word_q;
    reg [15:0] spectrum_data_q;
    reg [4:0] image_bit_q;
    wire [1:0] descriptor=descriptor_beat[2:1];
    wire descriptor_high=descriptor_beat[0];
    wire [7:0] descriptor_type={6'd0,descriptor}+8'd1;
    wire [28:0] expected_payload_base=(bank ? PAYLOAD_BANK1_WORD : PAYLOAD_BANK0_WORD)+
        (descriptor==0 ? WAVEFORM_OFFSET_WORD : descriptor==1 ? LISSAJOUS_OFFSET_WORD :
         descriptor==2 ? SPECTRUM_OFFSET_WORD : EFFECT_META_OFFSET_WORD);
    wire [31:0] expected_payload_words=descriptor==0 ? 512 : descriptor==1 ? 2048 : descriptor==2 ? 256 : 16;
    wire [31:0] expected_length=descriptor==0 ? 512 : descriptor==3 ? 16 :
        !analysis_valid_q ? 0 : descriptor==1 ? 65536 : 512;
    wire [31:0] expected_window=descriptor==0 ? 32'h0d010200 : descriptor==1 ? 32'h00000800 :
        descriptor==2 ? 32'h00020800 : 0;
    wire [31:0] expected_skipped=descriptor==0 ? global_q[223:192] :
        descriptor==3 ? 0 : global_q[255:224];
    wire [31:0] expected_aux0=descriptor==1 ? 32'h01000100 : descriptor==2 ? 32'h03550002 : 0;
    wire [31:0] expected_aux1=descriptor==2 ? 224 : 0;
    wire descriptor_low_ok=
        rsp_q[31:0]==BLOCK_MAGIC &&
        rsp_q[63:32]=={descriptor_type,descriptor_type,VERSION_MAJOR,SELECTED_MINOR} &&
        rsp_q[95:64]==global_q[95:64] &&
        (descriptor==3 ? rsp_q[159:128]==0 : METADATA_MINOR==0 ? rsp_q[159:128]==SAMPLE_RATE_HZ :
         descriptor==0 ? (rsp_q[159:128]==32'd48000 || rsp_q[159:128]==32'd44100) : rsp_q[159:128]==snapshot_rate_q) &&
        rsp_q[191:160]==expected_window && rsp_q[223:192]==expected_length &&
        rsp_q[255:224]==((descriptor==0 || descriptor==3 || analysis_valid_q) ? 1 : 0);
    wire descriptor_high_ok=
        rsp_q[31:0]=={3'd0,expected_payload_base} && rsp_q[63:32]==expected_payload_words &&
        rsp_q[95:64]==expected_skipped &&
        (descriptor!=1 || rsp_q[127:99]==0) &&
        (METADATA_MINOR==0 || descriptor==1 || rsp_q[127:96]==0) &&
        rsp_q[159:128]==expected_aux0 && rsp_q[191:160]==expected_aux1 &&
        (METADATA_MINOR==0 ? rsp_q[223:192]==0 :
         descriptor==0 ? rsp_q[223:192]!=0 : rsp_q[223:192]==snapshot_epoch_q) &&
        rsp_q[255:224]=={3'd0,header_addr};
    wire meta_ok=
        meta_lo_q[255:224]==32'h44495350 &&
        meta_lo_q[63:32]==global_q[223:192] &&
        meta_lo_q[95:64]==descriptor_source[0] &&
        meta_hi_q[31:0]==descriptor_source[1] &&
        descriptor_source[1]==descriptor_source[2] &&
        descriptor_source[3]==global_q[95:64] &&
        meta_hi_q[63:32]==global_q[255:224] &&
        meta_hi_q[127:96]==descriptor_gain[1] &&
        meta_hi_q[159:128]==global_q[191:160] &&
        (METADATA_MINOR==0 ? meta_hi_q[191:160]==SAMPLE_RATE_HZ && meta_hi_q[255:192]==0 :
         meta_hi_q[191:160]==snapshot_rate_q && meta_hi_q[223:192]==snapshot_epoch_q &&
         meta_hi_q[255:224]==0 && meta_lo_q[223:201]==0);
    wire last_payload_beat=payload_kind==0 ? payload_beat==63 : payload_kind==1 ? payload_beat==255 :
        payload_kind==2 ? payload_beat==31 : payload_beat==1;
    wire last_unpack_lane=payload_kind==2 ? unpack_lane==15 : unpack_lane==7;
    assign busy=state!=IDLE;
    assign req_valid=enabled && (state==REQ_GLOBAL || state==REQ_HEADER || state==REQ_DESC ||
        state==REQ_PAYLOAD || state==REQ_FINAL);
    always @* begin
        req_addr=0;
        case(state)
            REQ_GLOBAL:req_addr=DISPLAY_CONTROL_WORD;
            REQ_HEADER,REQ_FINAL:req_addr=header_addr;
            REQ_DESC:req_addr=descriptor_base+{23'd0,descriptor_beat,3'd0};
            REQ_PAYLOAD:req_addr=payload_base[payload_kind]+{18'd0,payload_beat,3'd0};
            default:begin end
        endcase
    end
    assign render_wave_data=wave_data_q;
    assign render_image_hit=image_word_q[image_bit_q];
    assign render_spectrum_left=spectrum_data_q[7:0];
    assign render_spectrum_right=spectrum_data_q[15:8];
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;done<=0;valid<=0;fault<=0;bank<=0;analysis_valid_q<=0;published_bank<=0;
            descriptor_beat<=0;payload_kind<=0;payload_beat<=0;header_addr<=0;descriptor_base<=0;
            global_q<=0;header_q<=0;meta_lo_q<=0;meta_hi_q<=0;rsp_q<=0;final_bad_q<=0;final_meta_ok_q<=0;
            global_ok_q<=0;header_bad_q<=0;desc_ok_q<=0;
            render_meta<=0;render_analysis_sequence<=0;render_analysis_skipped<=0;render_stereo_peaks<=0;
            render_image_gain<=0;render_analysis_valid<=0;render_frame_sequence<=0;
            snapshot_rate_q<=0;snapshot_epoch_q<=0;
            render_sample_rate_o<=0;render_epoch_o<=0;render_generation_o<=0;
            render_context_changed_o<=0;incompatible_o<=0;diagnostic_code_o<=0;
            payload_q<=0;unpack_lane<=0;spectrum_address_q<=0;wave_data_q<=0;image_word_q<=0;
            spectrum_data_q<=0;image_bit_q<=0;
        end else begin
            done<=0;
            render_context_changed_o<=0;
            spectrum_address_q<=render_spectrum_column;
            // Unpack each BL8 response into naturally sized RAM words. This
            // keeps the compact cache near its 90 Kbit payload size.
            if(state==STORE_PAYLOAD)begin
                case(payload_kind)
                    0:wave_cache[wave_write_addr]<=payload_q[unpack_lane*32+:32];
                    1:image_cache[image_write_addr]<=payload_q[unpack_lane*32+:32];
                    2:spectrum_cache[spectrum_write_addr]<=payload_q[unpack_lane*16+:16];
                    default:begin end
                endcase
            end else if(render_read_enable)begin
                wave_data_q<=wave_cache[wave_render_addr];
                image_word_q<=image_cache[image_render_addr];image_bit_q<=render_image_addr[4:0];
                spectrum_data_q<=spectrum_cache[spectrum_render_addr];
            end
            case(state)
                IDLE:if(start)begin fault<=0;incompatible_o<=0;diagnostic_code_o<=0;state<=REQ_GLOBAL;end
                REQ_GLOBAL:if(req_valid && req_ready)state<=WAIT_GLOBAL;
                WAIT_GLOBAL:if(rsp_valid)begin rsp_q<=rsp_data;state<=PARSE_GLOBAL;end
                PARSE_GLOBAL:begin
                    global_q<=rsp_q;
                    global_ok_q<=!(rsp_q[31:0]!=DISPLAY_MAGIC ||
                       rsp_q[63:32]!={8'd4,7'd0,rsp_q[48],VERSION_MAJOR,SELECTED_MINOR} ||
                       rsp_q[95:64]==0 || rsp_q[127:96]!=(rsp_q[95:64]<<1) ||
                       (rsp_q[191:160]!=32'hf && rsp_q[191:160]!=32'h9) ||
                       rsp_q[159:128]!=(rsp_q[48] ? {3'd0,DESC_BANK1_WORD}:{3'd0,DESC_BANK0_WORD}));
                    state<=GLOBAL_CHECK;
                end
                GLOBAL_CHECK:begin
                    if(!global_ok_q)begin
                        fault<=1;incompatible_o<=rsp_q[47:32]!={VERSION_MAJOR,SELECTED_MINOR};
                        diagnostic_code_o<=rsp_q[47:32]!={VERSION_MAJOR,SELECTED_MINOR} ? 1:2;
                        if(METADATA_MINOR==1)begin done<=1;state<=IDLE;end else state<=REQ_GLOBAL;
                    end else begin
                        bank<=rsp_q[48];analysis_valid_q<=rsp_q[161] && rsp_q[162];
                        header_addr<=rsp_q[48] ? BANK1_HEADER_WORD:BANK0_HEADER_WORD;
                        descriptor_base<=rsp_q[156:128];state<=REQ_HEADER;
                    end
                end
                REQ_HEADER:if(req_valid && req_ready)state<=WAIT_HEADER;
                WAIT_HEADER:if(rsp_valid)begin rsp_q<=rsp_data;state<=PARSE_HEADER;end
                PARSE_HEADER:begin
                    header_q<=rsp_q;
                    header_bad_q<=rsp_q[63:0]!=global_q[63:0] || rsp_q[96];state<=HEADER_CMP1;
                end
                HEADER_CMP1:begin header_bad_q<=header_bad_q || (rsp_q[127:64]!=global_q[127:64]);state<=HEADER_CMP2;end
                HEADER_CMP2:begin header_bad_q<=header_bad_q || (rsp_q[191:128]!=global_q[191:128]);state<=HEADER_CMP3;end
                HEADER_CMP3:begin header_bad_q<=header_bad_q || (rsp_q[255:192]!=global_q[255:192]);state<=HEADER_CHECK;end
                HEADER_CHECK:begin
                    if(header_bad_q)begin
                        fault<=1;diagnostic_code_o<=3;
                        if(METADATA_MINOR==1)begin done<=1;state<=IDLE;end else state<=REQ_GLOBAL;
                    end
                    else begin descriptor_beat<=0;state<=REQ_DESC;end
                end
                REQ_DESC:if(req_valid && req_ready)state<=WAIT_DESC;
                WAIT_DESC:if(rsp_valid)begin rsp_q<=rsp_data;state<=PARSE_DESC;end
                PARSE_DESC:begin
                    desc_ok_q<=(!descriptor_high && descriptor_low_ok) || (descriptor_high && descriptor_high_ok);
                    state<=DESC_CHECK;
                end
                DESC_CHECK:begin
                    if(!desc_ok_q)begin
                        fault<=1;
                        incompatible_o<=!descriptor_high && rsp_q[47:32]!={VERSION_MAJOR,SELECTED_MINOR};
                        diagnostic_code_o<=!descriptor_high && rsp_q[47:32]!={VERSION_MAJOR,SELECTED_MINOR} ? 1:4;
                        if(METADATA_MINOR==1)begin done<=1;state<=IDLE;end else state<=REQ_GLOBAL;
                    end else begin
                        if(!descriptor_high)begin
                            descriptor_source[descriptor]<=rsp_q[127:96];
                            if(descriptor==0)snapshot_rate_q<=rsp_q[159:128];
                        end else begin
                            payload_base[descriptor]<=rsp_q[28:0];descriptor_gain[descriptor]<=rsp_q[127:96];
                            if(descriptor==0)snapshot_epoch_q<=rsp_q[223:192];
                        end
                        if(descriptor_beat==7)begin payload_kind<=0;payload_beat<=0;state<=REQ_PAYLOAD;end
                        else begin descriptor_beat<=descriptor_beat+1'b1;state<=REQ_DESC;end
                    end
                end
                REQ_PAYLOAD:if(req_valid && req_ready)state<=WAIT_PAYLOAD;
                WAIT_PAYLOAD:if(rsp_valid)begin rsp_q<=rsp_data;state<=PARSE_PAYLOAD;end
                PARSE_PAYLOAD:begin
                    if(payload_kind==3)begin
                        if(payload_beat==0)meta_lo_q<=rsp_q;else meta_hi_q<=rsp_q;
                        if(last_payload_beat)begin payload_beat<=0;state<=REQ_FINAL;end
                        else begin payload_beat<=payload_beat+1'b1;state<=REQ_PAYLOAD;end
                    end else begin payload_q<=rsp_q;unpack_lane<=0;state<=STORE_PAYLOAD;end
                end
                STORE_PAYLOAD:begin
                    if(last_unpack_lane)begin
                        unpack_lane<=0;
                        if(last_payload_beat)begin payload_beat<=0;payload_kind<=payload_kind+1'b1;state<=REQ_PAYLOAD;end
                        else begin payload_beat<=payload_beat+1'b1;state<=REQ_PAYLOAD;end
                    end else unpack_lane<=unpack_lane+1'b1;
                end
                REQ_FINAL:if(req_valid && req_ready)state<=WAIT_FINAL;
                WAIT_FINAL:if(rsp_valid)begin rsp_q<=rsp_data;state<=PARSE_FINAL;end
                PARSE_FINAL:begin
                    final_bad_q<=rsp_q[63:0]!=header_q[63:0];state<=FINAL_CMP1;
                end
                FINAL_CMP1:begin final_bad_q<=final_bad_q || (rsp_q[127:64]!=header_q[127:64]);state<=FINAL_CMP2;end
                FINAL_CMP2:begin final_bad_q<=final_bad_q || (rsp_q[191:128]!=header_q[191:128]);state<=FINAL_CMP3;end
                FINAL_CMP3:begin
                    final_bad_q<=final_bad_q || (rsp_q[255:192]!=header_q[255:192]);
                    final_meta_ok_q<=meta_ok;state<=FINAL_CHECK;
                end
                FINAL_CHECK:begin
                    if(final_bad_q || rsp_q[96] || !final_meta_ok_q)begin
                        fault<=1;diagnostic_code_o<=final_bad_q || rsp_q[96] ? 6:5;
                        if(METADATA_MINOR==1)begin done<=1;state<=IDLE;end else state<=REQ_GLOBAL;
                    end
                    else state<=PUBLISH;
                end
                PUBLISH:begin
                    render_meta<=meta_lo_q;render_analysis_sequence<=meta_hi_q[31:0];
                    render_analysis_skipped<=meta_hi_q[63:32];render_stereo_peaks<=meta_hi_q[95:64];
                    render_image_gain<=meta_hi_q[98:96];render_analysis_valid<=analysis_valid_q;
                    render_frame_sequence<=global_q[95:64];valid<=1;fault<=0;done<=1;state<=IDLE;
                    published_bank<=working_bank;incompatible_o<=0;diagnostic_code_o<=0;
                    render_sample_rate_o<=snapshot_rate_q;render_epoch_o<=snapshot_epoch_q;
                    render_generation_o<=global_q[127:96];
                    render_context_changed_o<=METADATA_MINOR==1 &&
                        (!valid || snapshot_rate_q!=render_sample_rate_o || snapshot_epoch_q!=render_epoch_o);
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
