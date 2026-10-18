`timescale 1ns/1ps
// 60 Hz coherent scene updates. RGB565 regions use a continuous 50 MHz SPI
// stream; a four-pixel FIFO overlaps the renderer with transmission. Full
// repaint needs >16.67 ms, so a scene is never replaced until every region ends.
module midi_landscape_display #(
    parameter integer ROTATE_CW = 0,
    parameter integer CLK_HZ = 50000000,
    parameter integer MS_TICKS = CLK_HZ / 1000,
    parameter integer REFRESH_HZ = 60,
    parameter integer PIXEL_PIPELINE_CYCLES = 4,
    parameter integer BOOT_MS = 250,
    parameter integer POST_INIT_MS = 150
) (
    input wire clk, reset,
    input wire [15:0] pixel_color,
    input wire [26:0] dirty_regions,
    input wire remote_enable,
    input wire tile_valid,
    output wire tile_ready,
    input wire [8:0] tile_x, tile_width,
    input wire [7:0] tile_y, tile_height,
    output wire [7:0] tile_read_addr,
    input wire [15:0] tile_read_data,
    output reg tile_done = 0,
    output wire [8:0] pixel_x,
    output wire [7:0] pixel_y,
    output reg snapshot = 0,
    output reg [31:0] completed_refreshes = 0,
    output reg [31:0] overrun_count = 0,
    output wire lcd_ncs, lcd_dc, lcd_sck, lcd_mosi
);
    localparam [3:0] BOOT=0, INIT=1, INIT_DELAY=2, POST_INIT=3,
        WAIT_FRAME=4, SETTLE=5, SELECT_REGION=6, SETUP=7,
        HEADER=8, PIXELS=9, DRAIN=10, REMOTE_WAIT=11;
    localparam [1:0] LOCAL=0, CLEAR=1, TILE=2;
    reg [3:0] state = BOOT;
    reg [1:0] window_kind = LOCAL;
    reg force_full = 0;
    reg [8:0] saved_tile_x=0, saved_tile_width=0;
    reg [7:0] saved_tile_y=0, saved_tile_height=0;
    reg [15:0] saved_tile_pixels=0;
    reg [7:0] tile_address=0, tile_column_address=0;
    reg [31:0] delay_count = 0, refresh_phase = 0;
    wire frame_tick = refresh_phase >= CLK_HZ - REFRESH_HZ;
    always @(posedge clk) begin
        if (reset) refresh_phase <= 0;
        else if (frame_tick) refresh_phase <= refresh_phase - (CLK_HZ - REFRESH_HZ);
        else refresh_phase <= refresh_phase + REFRESH_HZ;
    end

    reg [8:0] rom_index = 0;
    wire [1:0] rom_kind, next_rom_kind;
    wire [15:0] rom_value;
    lcd_init_rom init_rom(.index(rom_index), .kind(rom_kind), .value(rom_value));
    lcd_init_rom init_lookahead(.index(rom_index+9'd1), .kind(next_rom_kind), .value());
    reg [26:0] pending = 0;
    reg [4:0] region_id = 0;
    reg [3:0] header_index = 0;
    wire [8:0] logical_left, logical_right;
    wire [7:0] logical_top, logical_bottom;
    reg [7:0] column_first = 0, column_last = 141;
    reg [8:0] row_first = 0, row_last = 427;
    reg [7:0] native_x = 0;
    reg [8:0] native_y = 0;
    assign pixel_x = ROTATE_CW ? native_y : 9'd427-native_y;
    assign pixel_y = ROTATE_CW ? 8'd141-native_x : native_x;
    function [4:0] first_region;
        input [26:0] mask;
        integer i;
        begin
            first_region=0;
            for(i=26;i>=0;i=i-1) if(mask[i]) first_region=i;
        end
    endfunction
    // Exact, disjoint renderer regions. Region 0 supersedes all others.
    function [33:0] region_bounds;
        input [4:0] id;
        reg [8:0] left,right,card_left;
        reg [7:0] top,bottom;
        begin
        left=0;right=427;top=0;bottom=141;card_left=0;
        if(id==1)begin left=168;right=369;top=7;bottom=13;end
        else if(id>=2 && id<=7)begin
            case(id)
                2:card_left=8;3:card_left=70;4:card_left=132;
                5:card_left=194;6:card_left=256;default:card_left=318;
            endcase
            left=card_left;right=card_left+57;top=29;bottom=71;
        end else if(id==8)begin left=8;right=139;top=74;bottom=80;end
        else if(id>=9 && id<=24)begin
            left=9'd8+(id-5'd9)*9'd23;right=left+19;
            top=82;bottom=126;
        end else if(id==25)begin left=384;right=419;top=29;bottom=126;end
        else if(id==26)begin left=208;right=297;top=133;bottom=139;end
            region_bounds={left,right,top,bottom};
        end
    endfunction
    assign {logical_left,logical_right,logical_top,logical_bottom} =
        window_kind==LOCAL ? region_bounds(region_id) :
        window_kind==CLEAR ? {9'd0,9'd427,8'd0,8'd141} :
        {saved_tile_x, (saved_tile_x+saved_tile_width-9'd1),
         saved_tile_y, (saved_tile_y+saved_tile_height-8'd1)};
    assign tile_read_addr = tile_address;
    reg [15:0] fifo [0:3];
    reg [1:0] read_pointer=0, write_pointer=0;
    reg [2:0] fifo_count=0;
    reg [15:0] fetch_remaining=0, send_remaining=0;
    reg [3:0] fetch_wait=0;
    reg low_byte=0;
    wire fetch_pixel = fetch_remaining!=0 && fetch_wait==0 && fifo_count<4;
    reg tx_valid, tx_dc, tx_last;
    reg [7:0] tx_data;
    wire tx_ready, spi_idle;
    assign tile_ready = state==REMOTE_WAIT && remote_enable && spi_idle;
    wire byte_accepted = tx_valid && tx_ready;
    wire pop_pixel = state==PIXELS && byte_accepted && low_byte;
    wire setup_window = state==SETUP;
    lcd_spi_stream spi(.clk(clk),.reset(reset),.valid(tx_valid),.data(tx_data),
        .data_dc(tx_dc),.last(tx_last),.ready(tx_ready),.idle(spi_idle),
        .lcd_ncs(lcd_ncs),.lcd_dc(lcd_dc),.lcd_sck(lcd_sck),.lcd_mosi(lcd_mosi));
    always @* begin
        tx_valid=0;tx_dc=0;tx_data=0;tx_last=0;
        if(state==INIT && rom_kind<2)begin
            tx_valid=1;tx_dc=rom_kind[0];tx_data=rom_value[7:0];tx_last=next_rom_kind>=2;
        end else if(state==HEADER)begin
            tx_valid=1;tx_dc=1;
            case(header_index)
                0:begin tx_data=8'h36;tx_dc=0;end
                1:tx_data=8'h00;
                2:begin tx_data=8'h20;tx_dc=0;end
                3:begin tx_data=8'h2a;tx_dc=0;end
                4:tx_data=0;
                5:tx_data=column_first+8'd12;
                6:tx_data=0;
                7:tx_data=column_last+8'd12;
                8:begin tx_data=8'h2b;tx_dc=0;end
                9:tx_data={7'd0,row_first[8]};10:tx_data=row_first[7:0];
                11:tx_data={7'd0,row_last[8]};12:tx_data=row_last[7:0];
                default:begin tx_data=8'h2c;tx_dc=0;end
            endcase
        end else if(state==PIXELS)begin
            tx_valid=fifo_count!=0;tx_dc=1;
            tx_data=low_byte ? fifo[read_pointer][7:0] : fifo[read_pointer][15:8];
            tx_last=low_byte && send_remaining==1;
        end
    end
    // Producer runs during command setup and while the serializer consumes
    // older FIFO entries. Coordinates stay fixed until the four stages settle.
    always @(posedge clk) begin
        if(reset)begin
            native_x<=0;native_y<=0;read_pointer<=0;write_pointer<=0;
            fifo_count<=0;fetch_remaining<=0;fetch_wait<=0;
            tile_address<=0;tile_column_address<=0;
        end else if(setup_window)begin
            native_x<=ROTATE_CW ? 8'd141-logical_bottom : logical_top;
            native_y<=ROTATE_CW ? logical_left : 9'd427-logical_right;
            read_pointer<=0;write_pointer<=0;fifo_count<=0;
            fetch_remaining<=(logical_right-logical_left+9'd1)*(logical_bottom-logical_top+8'd1);
            fetch_wait<=PIXEL_PIPELINE_CYCLES;
            // RAM stores logical row-major pixels. The panel scans native
            // columns first, so advance through a logical column instead.
            // Incremental addresses avoid a multiplier in the pixel path.
            tile_address<=ROTATE_CW ? saved_tile_pixels-saved_tile_width : saved_tile_width-1'b1;
            tile_column_address<=ROTATE_CW ? saved_tile_pixels-saved_tile_width : saved_tile_width-1'b1;
        end else begin
            if(fetch_wait!=0) fetch_wait<=fetch_wait-1'b1;
            if(fetch_pixel)begin
                fifo[write_pointer]<=window_kind==CLEAR ? 16'd0 :
                    window_kind==TILE ? tile_read_data : pixel_color;
                write_pointer<=write_pointer+1'b1;
                fetch_remaining<=fetch_remaining-1'b1;fetch_wait<=PIXEL_PIPELINE_CYCLES;
                if(fetch_remaining!=1)begin
                    if(native_x==column_last)begin
                        native_x<=column_first;native_y<=native_y+1'b1;
                        tile_column_address<=ROTATE_CW ? tile_column_address+1'b1 : tile_column_address-1'b1;
                        tile_address<=ROTATE_CW ? tile_column_address+1'b1 : tile_column_address-1'b1;
                    end else begin
                        native_x<=native_x+1'b1;
                        tile_address<=ROTATE_CW ? tile_address-saved_tile_width : tile_address+saved_tile_width;
                    end
                end
            end
            if(pop_pixel)read_pointer<=read_pointer+1'b1;
            case({fetch_pixel,pop_pixel})
                2'b10:fifo_count<=fifo_count+1'b1;
                2'b01:fifo_count<=fifo_count-1'b1;
                default:;
            endcase
        end
    end
    always @(posedge clk) begin
        snapshot<=0;tile_done<=0;
        if(reset)begin
            state<=BOOT;delay_count<=BOOT_MS*MS_TICKS;rom_index<=0;
            pending<=0;region_id<=0;header_index<=0;low_byte<=0;send_remaining<=0;
            column_first<=0;column_last<=141;row_first<=0;row_last<=427;
            completed_refreshes<=0;overrun_count<=0;
            window_kind<=LOCAL;force_full<=0;
            saved_tile_x<=0;saved_tile_y<=0;saved_tile_width<=0;saved_tile_height<=0;saved_tile_pixels<=0;
        end else begin
            // Long full repaints can miss a tick; keep the same scene until
            // completion and count the miss, rather than mixing frame states.
            if(frame_tick && window_kind==LOCAL && state>=SETTLE && state<=DRAIN)
                overrun_count<=overrun_count+1'b1;
            case(state)
                BOOT:if(delay_count==0)state<=INIT;else delay_count<=delay_count-1'b1;
                INIT:begin
                    if(rom_kind<2)begin if(byte_accepted)rom_index<=rom_index+1'b1;end
                    else if(spi_idle)begin
                        if(rom_kind==2)begin
                            delay_count<=rom_value*MS_TICKS;rom_index<=rom_index+1'b1;state<=INIT_DELAY;
                        end else begin delay_count<=POST_INIT_MS*MS_TICKS;state<=POST_INIT;end
                    end
                end
                INIT_DELAY:if(delay_count==0)state<=INIT;else delay_count<=delay_count-1'b1;
                POST_INIT:if(delay_count==0)state<=WAIT_FRAME;else delay_count<=delay_count-1'b1;
                WAIT_FRAME:begin
                    if(remote_enable && spi_idle)begin
                        pending<=0;window_kind<=CLEAR;state<=SETUP;
                    end else if(frame_tick)begin snapshot<=1;delay_count<=5;state<=SETTLE;end
                end
                SETTLE:if(delay_count==0)begin
                        pending<=force_full ? 27'd1 : dirty_regions;
                        force_full<=0;state<=SELECT_REGION;
                    end
                    else delay_count<=delay_count-1'b1;
                SELECT_REGION:begin
                    if(remote_enable && spi_idle)begin
                        pending<=0;window_kind<=CLEAR;state<=SETUP;
                    end else if(pending==0)begin completed_refreshes<=completed_refreshes+1'b1;state<=WAIT_FRAME;end
                    else begin
                        region_id<=first_region(pending);
                        if(pending[0])pending<=0;
                        else pending<=pending & ~(27'd1<<first_region(pending));
                        state<=SETUP;
                    end
                end
                SETUP:begin
                    if(window_kind==LOCAL && remote_enable && spi_idle)begin
                        // This local window has not emitted its first byte.
                        // Discard it with the rest of the old local scene.
                        pending<=0;window_kind<=CLEAR;
                    end else begin
                        column_first<=ROTATE_CW ? 8'd141-logical_bottom : logical_top;
                        column_last<=ROTATE_CW ? 8'd141-logical_top : logical_bottom;
                        row_first<=ROTATE_CW ? logical_left : 9'd427-logical_right;
                        row_last<=ROTATE_CW ? logical_right : 9'd427-logical_left;
                        send_remaining<=(logical_right-logical_left+9'd1)*(logical_bottom-logical_top+8'd1);
                        header_index<=0;low_byte<=0;state<=HEADER;
                    end
                end
                HEADER:if(byte_accepted)begin
                    if(header_index==13)state<=PIXELS;
                    else header_index<=header_index+1'b1;
                end
                PIXELS:if(byte_accepted)begin
                    low_byte<=!low_byte;
                    if(low_byte)begin
                        send_remaining<=send_remaining-1'b1;
                        if(send_remaining==1)state<=DRAIN;
                    end
                end
                DRAIN:if(spi_idle)begin
                    if(window_kind==TILE)tile_done<=1;
                    if(window_kind!=LOCAL)begin
                        if(remote_enable)state<=REMOTE_WAIT;
                        else begin
                            window_kind<=LOCAL;pending<=0;force_full<=1;state<=WAIT_FRAME;
                        end
                    end else if(remote_enable)begin
                        pending<=0;window_kind<=CLEAR;state<=SETUP;
                    end else state<=SELECT_REGION;
                end
                REMOTE_WAIT:begin
                    if(!remote_enable)begin
                        window_kind<=LOCAL;pending<=0;force_full<=1;state<=WAIT_FRAME;
                    end else if(tile_valid && tile_ready)begin
                        saved_tile_x<=tile_x;saved_tile_y<=tile_y;
                        saved_tile_width<=tile_width;saved_tile_height<=tile_height;
                        saved_tile_pixels<=tile_width*tile_height;
                        window_kind<=TILE;state<=SETUP;
                    end
                end
                default:state<=BOOT;
            endcase
        end
    end
endmodule
