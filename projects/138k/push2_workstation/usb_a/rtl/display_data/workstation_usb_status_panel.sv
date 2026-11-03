`default_nettype none
// Read-only decoration of the renderer stream before its existing DDR writer.
// No ready generation, DDR allocation, audio dependency or scanout overlay.
module workstation_usb_status_panel #(
    parameter integer STALE_CYCLES=100000000,
    parameter integer PIPELINED=0
) (
    input wire source_clk, source_reset_n,
    // {CPU fault, link failed, traffic enabled, transaction ready, HS,
    //  GW25K, generic MIDI, owner connected}; all in source_clk domain.
    input wire [7:0] source_status,
    input wire clk, reset_n, frame_start, pixel_valid, pixel_ready,
    input wire [31:0] active_voices,
    input wire [63:0] pixel_data,
    output wire [63:0] decorated_data,
    output wire input_ready,output_valid,
    input wire renderer_done,
    output wire output_done
);
    wire snapshot_valid;
    wire [7:0] snapshot;
    gw138k_stream_cdc #(.WIDTH(8)) u_status_cdc (
        .reset_n(source_reset_n && reset_n),.source_clk(source_clk),.destination_clk(clk),
        .source_valid(1'b1),.source_data(source_status),
        .destination_valid(snapshot_valid),.destination_data(snapshot),.drop_count()
    );
    reg [26:0] age;
    reg fresh;
    reg [7:0] frame_status;
    reg frame_fresh;
    reg [10:0] x,y;
    reg [5:0] frame_voices;
    function automatic [5:0] voice_count(input [31:0] mask);
        integer bit_index;
        begin
            voice_count=0;
            for(bit_index=0;bit_index<32;bit_index=bit_index+1)
                voice_count=voice_count+{5'd0,mask[bit_index]};
        end
    endfunction
    // The production pipeline samples CPU reset as a level in the local
    // memory clock. Never release local age/fresh FFs from the USB clock.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] source_reset_sync;
    always @(posedge clk or negedge reset_n)
        if(!reset_n)source_reset_sync<=0;
        else source_reset_sync<={source_reset_sync[0],source_reset_n};
    wire status_reset_n=PIPELINED ? reset_n : source_reset_n && reset_n;
    always @(posedge clk or negedge status_reset_n) begin
        if(!status_reset_n) begin age<=0;fresh<=0;end
        else begin
            if(PIPELINED && !source_reset_sync[1])begin age<=0;fresh<=0;end
            else if(snapshot_valid) begin age<=0;fresh<=1;end
            else if(age<STALE_CYCLES-1) age<=age+1'b1;
            else fresh<=0;
        end
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin frame_status<=0;frame_fresh<=0;frame_voices<=0;x<=0;y<=0;end
        else begin
            if(frame_start) begin
                frame_status<=snapshot;frame_fresh<=fresh && (!PIPELINED || source_reset_sync[1]);x<=0;y<=0;
                frame_voices<=voice_count(active_voices);
            end else if(pixel_valid && input_ready) begin
                if(x==1918) begin x<=0;y<=y+1'b1;end
                else x<=x+11'd2;
            end
        end
    end
    wire connected=frame_fresh && !frame_status[7] && !frame_status[6] &&
                   frame_status[5] && frame_status[4] && frame_status[0];
    reg [255:0] status_line,device_line,speed_line;
    always @* begin
        status_line="DISCONNECTED                    ";
        device_line="DEVICE  NONE                    ";
        speed_line="LINK    --                      ";
        if(!frame_fresh) status_line="NO STATUS                       ";
        else if(frame_status[7] || frame_status[6]) status_line="USB ERROR                       ";
        else if(connected) begin
            status_line="CONNECTED                       ";
            if(frame_status[2:1]==2'b11) device_line="DEVICE  25K KEYBOARD            ";
            else if(frame_status[1]) device_line="DEVICE  USB MIDI                ";
            else device_line="DEVICE  PUSH 2                  ";
            speed_line=frame_status[3] ? "LINK    HIGH SPEED              " :
                                                     "LINK    FULL SPEED              ";
        end else if(frame_status[5] && frame_status[4]) status_line="ENUMERATING                     ";
    end
    wire [10:0] local_x=x-11'd1248;
    reg [10:0] font_y;
    reg [255:0] text_line;
    reg text_row;
    wire [7:0] voice_tens=frame_voices>=30 ? "3" : frame_voices>=20 ? "2" :
                                frame_voices>=10 ? "1" : "0";
    wire [5:0] voice_units=frame_voices>=30 ? frame_voices-6'd30 :
                           frame_voices>=20 ? frame_voices-6'd20 :
                           frame_voices>=10 ? frame_voices-6'd10 : frame_voices;
    wire [7:0] voice_digit=8'd48+{2'd0,voice_units};
    always @* begin
        text_line=0;font_y=0;text_row=0;
        if(y>=864 && y<878) begin text_line="USB CONNECTION                  ";font_y=y-11'd864;text_row=1;end
        else if(y>=888 && y<902) begin text_line=status_line;font_y=y-11'd888;text_row=1;end
        else if(y>=912 && y<926) begin text_line=device_line;font_y=y-11'd912;text_row=1;end
        else if(y>=936 && y<950) begin text_line=speed_line;font_y=y-11'd936;text_row=1;end
        else if(y>=968 && y<982) begin
            text_line={"VOICES  ",voice_tens,voice_digit," / 32                 "};
            font_y=y-11'd968;text_row=1;
        end
    end
    // 16-pixel cells / 2x font. Even-x stream means each pixel pair shares ink.
    wire [4:0] character_index=local_x[8:4];
    wire [7:0] character=text_line[255-character_index*8-:8];
    wire ink;
    video_font_5x7 u_font(.character(character),.column(local_x[3:1]),
                         .row(font_y[3:1]),.ink(ink),.glyph());
    wire panel=x>=1216 && x<1856 && y>=848 && y<1040;
    wire text_hit=x>=1248 && x<1760 && text_row && ink;
    wire border=x==1216 || x==1854 || y==848 || y==1039;
    wire progress=x>=1248 && x<1760 && y>=1000 && y<1016;
    wire filled=local_x < {frame_voices,4'b0000};
    wire [23:0] voice_color=frame_voices==32 ? 24'hfbbf24 : 24'h38bdf8;
    wire [23:0] accent=connected ? 24'h4ade80 : 24'hfbbf24;
    wire [23:0] rgb=text_hit ? (y>=888 && y<902 ? accent : 24'he2e8f0) :
                     progress ? (filled ? voice_color : 24'h334155) :
                         border ? 24'h334155 : 24'h101b2b;
    generate if(!PIPELINED)begin:g_legacy
        assign input_ready=pixel_ready;
        assign output_valid=pixel_valid;
        assign output_done=renderer_done;
        assign decorated_data=panel ? {8'd0,rgb,8'd0,rgb} : pixel_data;
    end else begin:g_pipeline
        // Four elastic stages split row decode, character selection, glyph
        // lookup and glyph-bit selection. Every field stalls with its pixel.
        reg [3:0] valid;
        wire [3:0] ready;
        assign ready[3]=!valid[3] || pixel_ready;
        assign ready[2]=!valid[2] || ready[3];
        assign ready[1]=!valid[1] || ready[2];
        assign ready[0]=!valid[0] || ready[1];
        assign input_ready=ready[0] && !frame_start;
        assign output_valid=valid[3];
        reg [255:0] line0;
        reg [4:0] index0;
        reg [7:0] character1;
        reg [2:0] column0,column1,column2,row0,row1,row2;
        reg [34:0] glyph2;
        wire [34:0] glyph1;
        reg [63:0] data0,data1,data2,data3;
        reg [7:0] flags0,flags1,flags2,flags3;
        reg ink3,done_pending,done_pulse;
        wire [7:0] flags={panel,x>=1248 && x<1760 && text_row,
            y>=888 && y<902,progress,filled,border,connected,frame_voices==32};
        video_font_5x7 pipeline_font(.character(character1),.column(3'd0),
            .row(3'd0),.ink(),.glyph(glyph1));
        reg [4:0] glyph_row;
        always @*begin
            case(row2)
                0:glyph_row=glyph2[34:30];1:glyph_row=glyph2[29:25];
                2:glyph_row=glyph2[24:20];3:glyph_row=glyph2[19:15];
                4:glyph_row=glyph2[14:10];5:glyph_row=glyph2[9:5];
                6:glyph_row=glyph2[4:0];default:glyph_row=0;
            endcase
        end
        always @(posedge clk or negedge reset_n)begin
            if(!reset_n)begin valid<=0;done_pending<=0;done_pulse<=0;end
            else if(frame_start)begin valid<=0;done_pending<=0;done_pulse<=0;end
            else begin
                done_pulse<=done_pending && !(|valid);
                if(renderer_done)done_pending<=1;
                else if(done_pending && !(|valid))done_pending<=0;
                if(ready[0])begin
                    valid[0]<=pixel_valid;
                    if(pixel_valid)begin
                        line0<=text_line;index0<=character_index;
                        column0<=local_x[3:1];row0<=font_y[3:1];
                        data0<=pixel_data;flags0<=flags;
                    end
                end
                if(ready[1])begin
                    valid[1]<=valid[0];
                    if(valid[0])begin
                        character1<=line0[255-index0*8-:8];
                        column1<=column0;row1<=row0;data1<=data0;flags1<=flags0;
                    end
                end
                if(ready[2])begin
                    valid[2]<=valid[1];
                    if(valid[1])begin
                        glyph2<=glyph1;column2<=column1;row2<=row1;
                        data2<=data1;flags2<=flags1;
                    end
                end
                if(ready[3])begin
                    valid[3]<=valid[2];
                    if(valid[2])begin
                        ink3<=column2<5 && row2<7 && glyph_row[4-column2];
                        data3<=data2;flags3<=flags2;
                    end
                end
            end
        end
        assign output_done=done_pulse;
        wire [23:0] pipe_accent=flags3[1] ? 24'h4ade80 : 24'hfbbf24;
        wire [23:0] pipe_voice=flags3[0] ? 24'hfbbf24 : 24'h38bdf8;
        wire [23:0] pipe_rgb=(flags3[6] && ink3) ? (flags3[5] ? pipe_accent : 24'he2e8f0) :
            flags3[4] ? (flags3[3] ? pipe_voice : 24'h334155) :
            flags3[2] ? 24'h334155 : 24'h101b2b;
        assign decorated_data=flags3[7] ? {8'd0,pipe_rgb,8'd0,pipe_rgb} : data3;
    end endgenerate
endmodule
`default_nettype wire
