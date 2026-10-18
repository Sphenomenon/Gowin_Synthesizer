`timescale 1ns/1ps
// Local-v1 adaptation of the PL panel proposal; USB supplies link CRC.
// All integers and RGB565 pixels are little endian. Header (16 bytes):
// PL,version=1,type,session:u32,seq:u16,ack:u16,length:u16,flags,credit.
// flags=1 control or 3 display; no other channels/flag bits are accepted.
// HELLO01(0B)->CAPS81(12B): width:u16,height:u16,format:u8=1,reserved:u8=0,
// max_pixels:u16=248,max_payload:u16=512,heartbeat_ms:u16.
// HEALTH02(0B)->STATUS82. TILE20: page:u16,reserved:u16=0,frame:u32,
// x:u16,y:u16,w:u16,h:u16 followed by 1..248 RGB565 pixels -> ACK A0.
// FRAME_END21: page:u16,reserved:u16=0,frame:u32 -> DRAWN A1 only after SPI
// completion; hidden/expired frames return ACK with SUPPRESSED instead.
// All non-CAPS replies have 8 bytes: status:u8,state_flags:u8,page:u16,
// frame:u32. state_flags: manual=bit0,remote=bit1,redraw=bit2.
// Status: OK0,SUPPRESSED1,BUSY2,VERSION3,SESSION4,SEQUENCE5,FORMAT6,
// BOUNDS7,UNKNOWN8. Errors use FF. Response seq/ack echo the request seq;
// credit is 0 while a display tile is locked, otherwise 1. BUSY does not
// consume a sequence. HELLO seeds control seq+1 and display seq=0.
// Repeated last accepted seq replays its cached response without execution.
// There are no unsolicited messages. A partial packet times out after 50 ms.
// link_reset/expiry/new sessions keep a physically started tile immutable;
// only hard reset or tile_done can release that RAM lock.
module panel_display_endpoint #(
    parameter integer CLK_HZ = 50000000,
    parameter integer HEARTBEAT_MS = 250
) (
    input wire clk,
    input wire reset,
    input wire link_reset,
    input wire rx_valid,
    output wire rx_ready,
    input wire [7:0] rx_data,
    output wire tx_valid,
    input wire tx_ready,
    output reg [7:0] tx_data,
    input wire settings_toggle,
    output reg remote_enable,
    output reg manual_settings,
    output reg redraw_required,
    output reg [15:0] protocol_errors,
    output reg tile_valid,
    input wire tile_ready,
    output reg [8:0] tile_x,
    output reg [7:0] tile_y,
    output reg [8:0] tile_width,
    output reg [7:0] tile_height,
    input wire [7:0] tile_read_addr,
    output reg [15:0] tile_read_data,
    input wire tile_done
);
    localparam [63:0] CLOCK_VALUE=CLK_HZ;
    localparam [63:0] HEART_RAW=(CLOCK_VALUE*HEARTBEAT_MS+999)/1000;
    localparam [63:0] PACKET_RAW=(CLOCK_VALUE*50+999)/1000;
    localparam [31:0] HEART_CYCLES=HEART_RAW>0?HEART_RAW[31:0]:32'd1;
    localparam [31:0] PACKET_CYCLES=PACKET_RAW>0?PACKET_RAW[31:0]:32'd1;
    localparam [15:0] HEARTBEAT_VALUE=HEARTBEAT_MS;
    localparam [3:0] SEEK_P=0,SEEK_L=1,HEADER=2,LENGTH=3,PAYLOAD=4,
                     VALIDATE=5,COPY_READ=6,COPY_WRITE=7,WAIT_DONE=8,TX=9;
    reg [3:0] state;
    reg [127:0] header;
    reg [127:0] metadata;
    reg [4:0] header_index;
    reg [9:0] payload_index;
    reg [7:0] pixel_low;
    reg [15:0] staging_pixels [0:247];
    reg [15:0] tile_pixels [0:255];
    reg [15:0] copy_data;
    reg [7:0] copy_index;
    reg [8:0] copy_pixels;
    reg tile_busy,tile_started;
    reg session_valid;
    reg [31:0] session;
    reg [31:0] heartbeat_count,packet_count;
    reg [15:0] control_expected,display_expected;
    reg control_last_valid,display_last_valid;
    reg [15:0] control_last_seq,display_last_seq;
    reg [15:0] request_crc,control_last_crc,display_last_crc;
    reg [7:0] control_last_type,display_last_type;
    reg [95:0] control_last_payload,display_last_payload;
    reg [4:0] control_last_length,display_last_length;
    reg frame_valid,frame_drawn;
    reg [15:0] current_page;
    reg [31:0] current_frame;
    reg [7:0] response_type,response_flags,response_credit;
    reg [31:0] response_session;
    reg [15:0] response_seq;
    reg [4:0] response_length;
    reg [95:0] response_payload;
    reg [5:0] tx_index;

    wire [7:0] request_version=header[23:16];
    wire [7:0] request_type=header[31:24];
    wire [31:0] request_session=header[63:32];
    wire [15:0] request_seq=header[79:64];
    wire [15:0] request_length=header[111:96];
    wire [7:0] request_flags=header[119:112];
    wire display_channel=request_flags[2:1]==1;
    wire [15:0] meta_page=metadata[15:0];
    wire [31:0] meta_frame=metadata[63:32];
    wire [15:0] meta_x=metadata[79:64],meta_y=metadata[95:80];
    wire [15:0] meta_width=metadata[111:96],meta_height=metadata[127:112];
    wire [16:0] pixel_count=meta_width[8:0]*meta_height[7:0];
    wire [16:0] x_end={1'b0,meta_x}+{1'b0,meta_width};
    wire [16:0] y_end={1'b0,meta_y}+{1'b0,meta_height};
    wire session_expired=session_valid&&heartbeat_count>=HEART_CYCLES-1;
    wire toggling_page=settings_toggle&&(manual_settings||remote_enable);
    wire effective_manual=settings_toggle?(manual_settings?1'b0:remote_enable):manual_settings;
    wire [7:0] state_flags={5'd0,(redraw_required||session_expired||toggling_page),
                           (remote_enable&&!session_expired&&!toggling_page),effective_manual};
    wire accepting=rx_valid&&rx_ready;
    assign rx_ready=!reset&&!link_reset&&
                    (state==SEEK_P||state==SEEK_L||state==HEADER||state==PAYLOAD);
    assign tx_valid=!reset&&!link_reset&&state==TX;

    function [15:0] crc_byte;
        input [15:0] initial_crc;
        input [7:0] value;
        integer i;
        reg [15:0] crc;
        begin
            crc=initial_crc^{value,8'd0};
            for(i=0;i<8;i=i+1) crc=crc[15]?(crc<<1)^16'h1021:(crc<<1);
            crc_byte=crc;
        end
    endfunction

    // Dedicated synchronous read port. Contents stay fixed while tile_busy.
    always @(posedge clk) tile_read_data <= tile_pixels[tile_read_addr];

    always @* begin
        case(tx_index)
            0:tx_data=8'h50; 1:tx_data=8'h4c; 2:tx_data=1;
            3:tx_data=response_type;
            4:tx_data=response_session[7:0]; 5:tx_data=response_session[15:8];
            6:tx_data=response_session[23:16]; 7:tx_data=response_session[31:24];
            8,10:tx_data=response_seq[7:0]; 9,11:tx_data=response_seq[15:8];
            12:tx_data={3'd0,response_length}; 13:tx_data=0;
            14:tx_data=response_flags; 15:tx_data=response_credit;
            default:tx_data=response_payload[(tx_index-16)*8+:8];
        endcase
    end

    task count_error;
        begin if(protocol_errors!=16'hffff) protocol_errors<=protocol_errors+1'b1; end
    endtask
    task start_reply;
        input [7:0] kind;
        input [7:0] status;
        input [15:0] page;
        input [31:0] frame;
        input remember;
        reg [95:0] contents;
        begin
            contents={32'd0,frame,page,((kind==8'ha1&&status==0)?(state_flags&8'hfb):state_flags),status};
            if(kind==8'ha1&&status==0) redraw_required<=0;
            response_type<=kind; response_session<=request_session;
            response_seq<=request_seq; response_flags<=display_channel?8'h03:8'h01;
            response_credit<=(display_channel&&tile_busy)?0:1;
            response_length<=8; response_payload<=contents; tx_index<=0; state<=TX;
            if(status==2)heartbeat_count<=0;
            if(remember) begin
                heartbeat_count<=0;
                if(display_channel) begin
                    display_last_valid<=1; display_last_seq<=request_seq;
                    display_last_crc<=request_crc;
                    display_last_type<=kind;display_last_payload<=contents;display_last_length<=8;
                    display_expected<=request_seq+1'b1;
                end else begin
                    control_last_valid<=1;control_last_seq<=request_seq;
                    control_last_crc<=request_crc;
                    control_last_type<=kind;control_last_payload<=contents;control_last_length<=8;
                    control_expected<=request_seq+1'b1;
                end
            end
        end
    endtask
    task reject;
        input [7:0] status;
        begin count_error;start_reply(8'hff,status,0,0,0);end
    endtask
    task replay;
        reg [95:0] contents;
        reg [7:0] kind;
        begin
            kind=display_channel?display_last_type:control_last_type;
            contents=display_channel?display_last_payload:control_last_payload;
            if(kind!=8'h81)contents[15:8]=state_flags;
            // Cached transport success cannot resurrect a discarded canvas.
            if(display_channel&&(manual_settings||!remote_enable||!frame_valid||toggling_page))begin
                kind=8'ha0;contents[7:0]=1;
            end
            response_session<=request_session;response_seq<=request_seq;
            response_flags<=display_channel?8'h03:8'h01;
            response_credit<=(display_channel&&tile_busy)?0:1;
            response_type<=kind;
            response_length<=display_channel?display_last_length:control_last_length;
            response_payload<=contents;
            tx_index<=0;state<=TX;
            // A valid retransmission is live traffic, but never re-executes.
            heartbeat_count<=0;
        end
    endtask
    task discard_canvas;
        begin
            remote_enable<=0;redraw_required<=1;frame_valid<=0;frame_drawn<=0;
            tile_valid<=0;
            if(!tile_done&&(tile_started||(tile_valid&&tile_ready))) begin
                tile_busy<=1;tile_started<=1;
            end else begin tile_busy<=0;tile_started<=0;end
        end
    endtask

    always @(posedge clk) begin
        if(reset) begin
            state<=SEEK_P;header<=0;metadata<=0;header_index<=0;payload_index<=0;
            pixel_low<=0;copy_data<=0;copy_index<=0;copy_pixels<=0;
            remote_enable<=0;manual_settings<=0;redraw_required<=1;protocol_errors<=0;
            tile_valid<=0;tile_x<=0;tile_y<=0;tile_width<=0;tile_height<=0;
            tile_busy<=0;tile_started<=0;session_valid<=0;session<=0;
            heartbeat_count<=0;packet_count<=0;control_expected<=0;display_expected<=0;
            control_last_valid<=0;display_last_valid<=0;control_last_seq<=0;display_last_seq<=0;
            request_crc<=16'hffff;control_last_crc<=0;display_last_crc<=0;
            control_last_type<=0;display_last_type<=0;control_last_payload<=0;
            display_last_payload<=0;control_last_length<=0;display_last_length<=0;
            frame_valid<=0;frame_drawn<=0;current_page<=0;current_frame<=0;
            response_type<=0;response_flags<=0;response_credit<=0;response_session<=0;
            response_seq<=0;response_length<=0;response_payload<=0;tx_index<=0;
        end else if(link_reset) begin
            state<=SEEK_P;header<=0;metadata<=0;packet_count<=0;heartbeat_count<=0;
            session_valid<=0;control_last_valid<=0;display_last_valid<=0;
            discard_canvas;
        end else begin
            if(tile_valid&&tile_ready) begin tile_valid<=0;tile_started<=1;end
            if(tile_done) begin
                tile_busy<=0;tile_started<=0;tile_valid<=0;
                if(tile_busy&&tile_started&&session_valid&&remote_enable&&
                   !manual_settings&&frame_valid) frame_drawn<=1;
            end
            if(session_valid) begin
                if(session_expired) begin
                    session_valid<=0;heartbeat_count<=0;discard_canvas;
                end else heartbeat_count<=heartbeat_count+1'b1;
            end
            if(settings_toggle) begin
                if(manual_settings) begin manual_settings<=0;discard_canvas;end
                else if(remote_enable) begin manual_settings<=1;discard_canvas;end
            end
            if(state==SEEK_L||state==HEADER||state==PAYLOAD) begin
                if(accepting) packet_count<=0;
                else packet_count<=packet_count+1'b1;
            end else packet_count<=0;

            if((state==SEEK_L||state==HEADER||state==PAYLOAD)&&
               !accepting&&packet_count>=PACKET_CYCLES-1) begin
                packet_count<=0;reject(6);
            end else case(state)
                SEEK_P:if(accepting&&rx_data==8'h50) begin
                    header<=128'h50;metadata<=0;state<=SEEK_L;request_crc<=crc_byte(16'hffff,rx_data);
                end
                SEEK_L:if(accepting) begin
                    if(rx_data==8'h4c) begin header[15:8]<=rx_data;header_index<=2;state<=HEADER;
                        request_crc<=crc_byte(request_crc,rx_data);end
                    else if(rx_data==8'h50) request_crc<=crc_byte(16'hffff,rx_data);
                    else if(rx_data!=8'h50) state<=SEEK_P;
                end
                HEADER:if(accepting) begin
                    request_crc<=crc_byte(request_crc,rx_data);
                    header[header_index*8+:8]<=rx_data;
                    if(header_index==15) state<=LENGTH;else header_index<=header_index+1'b1;
                end
                LENGTH:begin
                    if(request_length>512) reject(6);
                    else if(request_length==0) state<=VALIDATE;
                    else begin payload_index<=0;state<=PAYLOAD;end
                end
                PAYLOAD:if(accepting) begin
                    request_crc<=crc_byte(request_crc,rx_data);
                    if(payload_index<16) metadata[payload_index*8+:8]<=rx_data;
                    else if(!payload_index[0]) pixel_low<=rx_data;
                    else staging_pixels[(payload_index-16)>>1]<={rx_data,pixel_low};
                    if(payload_index+1'b1==request_length) state<=VALIDATE;
                    else payload_index<=payload_index+1'b1;
                end
                VALIDATE:begin
                    if(request_version!=1) reject(3);
                    else if(request_flags!=1&&request_flags!=3) reject(6);
                    else if(request_type==8'h01) begin
                        if(display_channel||request_length!=0) reject(6);
                        else if(request_session==0) reject(4);
                        else if(session_valid&&!session_expired&&session==request_session) begin
                            if(control_last_valid&&request_seq==control_last_seq&&control_last_type==8'h81&&
                               request_crc==control_last_crc) replay;
                            else reject(5);
                        end else begin
                            session<=request_session;session_valid<=1;heartbeat_count<=0;
                            control_expected<=request_seq+1'b1;display_expected<=0;
                            control_last_valid<=1;display_last_valid<=0;control_last_seq<=request_seq;
                            control_last_crc<=request_crc;
                            control_last_type<=8'h81;control_last_length<=12;
                            control_last_payload<={HEARTBEAT_VALUE,16'd512,16'd248,8'd0,8'd1,16'd142,16'd428};
                            response_payload<={HEARTBEAT_VALUE,16'd512,16'd248,8'd0,8'd1,16'd142,16'd428};
                            response_type<=8'h81;response_length<=12;response_session<=request_session;
                            response_seq<=request_seq;response_flags<=1;response_credit<=1;tx_index<=0;state<=TX;
                            discard_canvas;
                        end
                    end else if(!session_valid||session_expired||request_session!=session) reject(4);
                    else if((display_channel&&display_last_valid&&request_seq==display_last_seq)||
                            (!display_channel&&control_last_valid&&request_seq==control_last_seq)) begin
                        if(request_crc==(display_channel?display_last_crc:control_last_crc)) replay;
                        else reject(5);
                    end
                    else if(request_seq!=(display_channel?display_expected:control_expected)) reject(5);
                    else case(request_type)
                        8'h02:if(display_channel||request_length!=0) reject(6);
                              else start_reply(8'h82,0,0,0,1);
                        8'h20:begin
                            if(!display_channel||request_length<18||metadata[31:16]!=0) reject(6);
                            else if(meta_width==0||meta_height==0||meta_width>428||meta_height>142||
                                    x_end>428||y_end>142||pixel_count>248) reject(7);
                            else if(request_length!=16+pixel_count*2) reject(6);
                            else if(manual_settings||(settings_toggle&&remote_enable))
                                start_reply(8'ha0,1,meta_page,meta_frame,1);
                            else if(tile_busy) start_reply(8'ha0,2,meta_page,meta_frame,0);
                            else begin
                                heartbeat_count<=0;remote_enable<=1;frame_valid<=1;frame_drawn<=0;
                                current_page<=meta_page;current_frame<=meta_frame;
                                tile_x<=meta_x[8:0];tile_y<=meta_y[7:0];
                                tile_width<=meta_width[8:0];tile_height<=meta_height[7:0];
                                tile_busy<=1;tile_started<=0;tile_valid<=0;
                                copy_index<=0;copy_pixels<=pixel_count[8:0];state<=COPY_READ;
                            end
                        end
                        8'h21:begin
                            if(!display_channel||request_length!=8||metadata[31:16]!=0) reject(6);
                            else if(manual_settings||!remote_enable||(settings_toggle&&remote_enable))
                                start_reply(8'ha0,1,meta_page,meta_frame,1);
                            else if(!frame_valid||meta_page!=current_page||meta_frame!=current_frame) reject(7);
                            else if(tile_busy&&!tile_started)start_reply(8'ha0,2,meta_page,meta_frame,0);
                            else if(tile_busy) begin heartbeat_count<=0;state<=WAIT_DONE;end
                            else if(frame_drawn) start_reply(8'ha1,0,meta_page,meta_frame,1);
                            else reject(7);
                        end
                        default:reject(8);
                    endcase
                end
                COPY_READ:begin copy_data<=staging_pixels[copy_index];state<=COPY_WRITE;end
                COPY_WRITE:begin
                    tile_pixels[copy_index]<=copy_data;
                    if(copy_index+1'b1==copy_pixels) begin
                        if(manual_settings||!session_valid||session_expired||(settings_toggle&&remote_enable)) begin
                            tile_valid<=0;tile_busy<=0;start_reply(8'ha0,1,current_page,current_frame,1);
                        end else begin tile_valid<=1;start_reply(8'ha0,0,current_page,current_frame,1);end
                    end else begin copy_index<=copy_index+1'b1;state<=COPY_READ;end
                end
                WAIT_DONE:begin
                    if(manual_settings||!session_valid||session_expired||!remote_enable||!frame_valid||
                       (settings_toggle&&remote_enable)) start_reply(8'ha0,1,meta_page,meta_frame,1);
                    else if(!tile_busy&&frame_drawn) start_reply(8'ha1,0,meta_page,meta_frame,1);
                end
                TX:if(tx_valid&&tx_ready) begin
                    if(tx_index==15+response_length) begin state<=SEEK_P;header<=0;metadata<=0;end
                    else tx_index<=tx_index+1'b1;
                end
                default:state<=SEEK_P;
            endcase
        end
    end
endmodule
