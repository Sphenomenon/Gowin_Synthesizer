`timescale 1ns/1ps
// Candidate NV3007 142x428 bring-up. See README before selecting a panel profile.
// The PCB has NO controllable LCD reset and NO backlight control signal.
module lcd_bringup_top #(
    parameter integer ENABLE_PANEL_INIT = 1,
    parameter integer CLK_HZ = 50000000,
    parameter integer MS_TICKS = CLK_HZ / 1000,
    parameter integer SPI_HALF_PERIOD = 25,
    parameter integer BOOT_MS = 250,
    parameter integer POST_INIT_MS = 150,
    parameter integer FRAME_GAP_MS = 500,
    parameter integer WIDTH = 142,
    parameter integer HEIGHT = 428,
    parameter [15:0] COL_OFFSET = 12,
    parameter [15:0] ROW_OFFSET = 0,
    parameter [7:0] MADCTL = 8'h00,
    parameter integer INVERT_DISPLAY = 0,
    parameter integer ENABLE_ROW_LABELS = 1
) (
    input wire clk,
    input wire lcd_te,
    output wire lcd_ncs,
    output wire lcd_dc,
    output wire lcd_sck,
    output wire lcd_mosi
);
    // 64 clocks of synchronous local reset, generated after FPGA configuration.
    reg [5:0] por_count = 0;
    wire reset = !(&por_count);
    always @(posedge clk)
        if (reset) por_count <= por_count + 1'b1;

    reg ncs = 1'b1;
    reg dc = 1'b0;
    assign lcd_ncs = ncs;
    assign lcd_dc = dc;

    reg tx_start = 1'b0;
    reg [7:0] tx_data = 0;
    wire tx_busy;
    wire tx_done;
    lcd_spi_byte #(.HALF_PERIOD_CYCLES(SPI_HALF_PERIOD)) spi (
        .clk(clk), .reset(reset), .start(tx_start), .data(tx_data),
        .busy(tx_busy), .done(tx_done), .sck(lcd_sck), .mosi(lcd_mosi)
    );

    // ROM format: kind=0 command, 1 data, 2 delay in milliseconds, 3 end.
    reg [8:0] rom_index = 0;
    wire [1:0] rom_kind;
    wire [15:0] rom_value;
    lcd_init_rom init_rom (.index(rom_index), .kind(rom_kind), .value(rom_value));

    localparam [3:0] ST_BOOT=0, ST_INIT=1, ST_INIT_DELAY=2, ST_POST_INIT=3,
                     ST_WINDOW=4, ST_PIXELS=5, ST_FRAME_END=6, ST_GAP=7,
                     ST_DISABLED=8;
    reg [3:0] state = ST_BOOT;
    reg [31:0] delay_count = 0;
    reg waiting_tx = 1'b0;
    reg [3:0] window_index = 0;
    reg [15:0] pixel_x = 0;
    reg [15:0] pixel_y = 0;
    reg pixel_low_byte = 0;
    reg [31:0] completed_frames = 0;
    localparam [15:0] COL_END = COL_OFFSET + WIDTH - 1;
    localparam [15:0] ROW_END = ROW_OFFSET + HEIGHT - 1;

    // Small 5x7 decimal glyphs, stored from top left to bottom right.
    function digit_on;
        input [3:0] digit;
        input [2:0] glyph_x;
        input [2:0] glyph_y;
        reg [34:0] glyph;
        reg [4:0] glyph_row;
        begin
            case (digit)
                0: glyph = {5'b01110,5'b10001,5'b10001,5'b10001,5'b10001,5'b10001,5'b01110};
                1: glyph = {5'b00100,5'b01100,5'b00100,5'b00100,5'b00100,5'b00100,5'b01110};
                2: glyph = {5'b01110,5'b10001,5'b00001,5'b00010,5'b00100,5'b01000,5'b11111};
                3: glyph = {5'b11110,5'b00001,5'b00001,5'b01110,5'b00001,5'b00001,5'b11110};
                4: glyph = {5'b00010,5'b00110,5'b01010,5'b10010,5'b11111,5'b00010,5'b00010};
                5: glyph = {5'b11111,5'b10000,5'b10000,5'b11110,5'b00001,5'b00001,5'b11110};
                6: glyph = {5'b01110,5'b10000,5'b10000,5'b11110,5'b10001,5'b10001,5'b01110};
                7: glyph = {5'b11111,5'b00001,5'b00010,5'b00100,5'b01000,5'b01000,5'b01000};
                8: glyph = {5'b01110,5'b10001,5'b10001,5'b01110,5'b10001,5'b10001,5'b01110};
                default: glyph = {5'b01110,5'b10001,5'b10001,5'b01111,5'b00001,5'b00001,5'b01110};
            endcase
            // Fixed slices/bits keep font addressing in LUT logic. The prior
            // dynamic index inferred a MULT12X12 for glyph_y*5; avoiding that
            // new DSP is a workaround candidate for a downstream tool crash.
            case (glyph_y)
                0: glyph_row = glyph[34:30];
                1: glyph_row = glyph[29:25];
                2: glyph_row = glyph[24:20];
                3: glyph_row = glyph[19:15];
                4: glyph_row = glyph[14:10];
                5: glyph_row = glyph[9:5];
                6: glyph_row = glyph[4:0];
                default: glyph_row = 5'b00000;
            endcase
            case (glyph_x)
                0: digit_on = glyph_row[4];
                1: digit_on = glyph_row[3];
                2: digit_on = glyph_row[2];
                3: digit_on = glyph_row[1];
                4: digit_on = glyph_row[0];
                default: digit_on = 1'b0;
            endcase
        end
    endfunction

    // Constant BCD lookup avoids synthesizing decimal division hardware.
    function [11:0] row_label_bcd;
        input [3:0] block;
        begin
            case (block)
                0: row_label_bcd=12'h000;  1: row_label_bcd=12'h032;
                2: row_label_bcd=12'h064;  3: row_label_bcd=12'h096;
                4: row_label_bcd=12'h128;  5: row_label_bcd=12'h160;
                6: row_label_bcd=12'h192;  7: row_label_bcd=12'h224;
                8: row_label_bcd=12'h256;  9: row_label_bcd=12'h288;
                10: row_label_bcd=12'h320; 11: row_label_bcd=12'h352;
                12: row_label_bcd=12'h384; 13: row_label_bcd=12'h416;
                default: row_label_bcd=12'h000;
            endcase
        end
    endfunction

    function row_label_ink;
        input [15:0] x;
        input [15:0] y;
        reg [11:0] bcd;
        reg [3:0] digit;
        reg [2:0] glyph_x;
        reg [2:0] glyph_y;
        begin
            row_label_ink = 1'b0;
            bcd = row_label_bcd(y[8:5]);
            digit = 0;
            glyph_x = 0;
            glyph_y = y[4:0] - 2;
            if (y[4:0] >= 2 && y[4:0] <= 8) begin
                if (x >= 3 && x <= 7) begin
                    digit = bcd[11:8]; glyph_x = x-3;
                    row_label_ink = digit_on(digit, glyph_x, glyph_y);
                end else if (x >= 9 && x <= 13) begin
                    digit = bcd[7:4]; glyph_x = x-9;
                    row_label_ink = digit_on(digit, glyph_x, glyph_y);
                end else if (x >= 15 && x <= 19) begin
                    digit = bcd[3:0]; glyph_x = x-15;
                    row_label_ink = digit_on(digit, glyph_x, glyph_y);
                end
            end
            if (x >= 21 && x <= 24 && y[4:0] == 5)
                row_label_ink = 1'b1;
        end
    endfunction

    // White one-pixel border and eight RGB565 bars: W,Y,C,G,M,R,B,K.
    // Labels 000,032,...416 sit at x=2..25 in each 32-row block. Their
    // white backing occupies rows +1..+10; glyphs occupy +2..+8.
    // Width thresholds use constant arithmetic, with no runtime divider.
    function [15:0] color_at;
        input [15:0] x;
        input [15:0] y;
        begin
            if (x == 0 || x == WIDTH-1 || y == 0 || y == HEIGHT-1)
                color_at = 16'hffff;
            else if (ENABLE_ROW_LABELS && x >= 2 && x <= 25 &&
                     y[4:0] >= 1 && y[4:0] <= 10)
                color_at = row_label_ink(x,y) ? 16'h0000 : 16'hffff;
            else if (x < WIDTH/8) color_at = 16'hffff;
            else if (x < WIDTH*2/8) color_at = 16'hffe0;
            else if (x < WIDTH*3/8) color_at = 16'h07ff;
            else if (x < WIDTH*4/8) color_at = 16'h07e0;
            else if (x < WIDTH*5/8) color_at = 16'hf81f;
            else if (x < WIDTH*6/8) color_at = 16'hf800;
            else if (x < WIDTH*7/8) color_at = 16'h001f;
            else color_at = 16'h0000;
        end
    endfunction
    wire [15:0] pixel_color = color_at(pixel_x, pixel_y);

    // TE is an input only. No TE wait is used in this slow first-light test.
    // No readback is attempted on MOSI; this board has no separate MISO.
    always @(posedge clk) begin
        tx_start <= 1'b0;
        if (reset) begin
            ncs <= 1'b1;
            dc <= 1'b0;
            tx_data <= 0;
            state <= ST_BOOT;
            delay_count <= BOOT_MS * MS_TICKS - 1;
            waiting_tx <= 1'b0;
            rom_index <= 0;
            window_index <= 0;
            pixel_x <= 0;
            pixel_y <= 0;
            pixel_low_byte <= 0;
            completed_frames <= 0;
        end else if (!ENABLE_PANEL_INIT) begin
            ncs <= 1'b1;
            dc <= 1'b0;
            state <= ST_DISABLED;
        end else if (waiting_tx) begin
            if (tx_done) waiting_tx <= 1'b0;
        end else begin
            case (state)
                ST_BOOT: begin
                    if (delay_count == 0) state <= ST_INIT;
                    else delay_count <= delay_count - 1'b1;
                end
                ST_INIT: begin
                    case (rom_kind)
                        0, 1: begin
                            ncs <= 1'b0;
                            dc <= rom_kind[0];
                            tx_data <= rom_value[7:0];
                            tx_start <= 1'b1;
                            waiting_tx <= 1'b1;
                            rom_index <= rom_index + 1'b1;
                        end
                        2: begin
                            ncs <= 1'b1;
                            delay_count <= rom_value * MS_TICKS - 1;
                            rom_index <= rom_index + 1'b1;
                            state <= ST_INIT_DELAY;
                        end
                        default: begin
                            ncs <= 1'b1;
                            delay_count <= POST_INIT_MS * MS_TICKS - 1;
                            state <= ST_POST_INIT;
                        end
                    endcase
                end
                ST_INIT_DELAY: begin
                    if (delay_count == 0) state <= ST_INIT;
                    else delay_count <= delay_count - 1'b1;
                end
                ST_POST_INIT: begin
                    if (delay_count == 0) begin
                        window_index <= 0;
                        state <= ST_WINDOW;
                    end else delay_count <= delay_count - 1'b1;
                end
                ST_WINDOW: begin
                    if (window_index == 14) begin
                        pixel_x <= 0;
                        pixel_y <= 0;
                        pixel_low_byte <= 0;
                        state <= ST_PIXELS;
                    end else begin
                        ncs <= 1'b0;
                        dc <= 1'b1;
                        case (window_index)
                            0: begin tx_data <= 8'h36; dc <= 1'b0; end
                            1: tx_data <= MADCTL;
                            2: begin
                                tx_data <= INVERT_DISPLAY ? 8'h21 : 8'h20;
                                dc <= 1'b0;
                            end
                            3: begin tx_data <= 8'h2a; dc <= 1'b0; end
                            4: tx_data <= COL_OFFSET[15:8];
                            5: tx_data <= COL_OFFSET[7:0];
                            6: tx_data <= COL_END[15:8];
                            7: tx_data <= COL_END[7:0];
                            8: begin tx_data <= 8'h2b; dc <= 1'b0; end
                            9: tx_data <= ROW_OFFSET[15:8];
                            10: tx_data <= ROW_OFFSET[7:0];
                            11: tx_data <= ROW_END[15:8];
                            12: tx_data <= ROW_END[7:0];
                            default: begin tx_data <= 8'h2c; dc <= 1'b0; end
                        endcase
                        window_index <= window_index + 1'b1;
                        tx_start <= 1'b1;
                        waiting_tx <= 1'b1;
                    end
                end
                ST_PIXELS: begin
                    dc <= 1'b1;
                    tx_data <= pixel_low_byte ? pixel_color[7:0] : pixel_color[15:8];
                    tx_start <= 1'b1;
                    waiting_tx <= 1'b1;
                    pixel_low_byte <= !pixel_low_byte;
                    if (pixel_low_byte) begin
                        if (pixel_x == WIDTH-1) begin
                            pixel_x <= 0;
                            if (pixel_y == HEIGHT-1) state <= ST_FRAME_END;
                            else pixel_y <= pixel_y + 1'b1;
                        end else pixel_x <= pixel_x + 1'b1;
                    end
                end
                ST_FRAME_END: begin
                    // This state is reached only after the final byte's falling edge.
                    ncs <= 1'b1;
                    dc <= 1'b0;
                    completed_frames <= completed_frames + 1'b1;
                    delay_count <= FRAME_GAP_MS * MS_TICKS - 1;
                    state <= ST_GAP;
                end
                ST_GAP: begin
                    if (delay_count == 0) begin
                        window_index <= 0;
                        state <= ST_WINDOW;
                    end else delay_count <= delay_count - 1'b1;
                end
                default: begin ncs <= 1'b1; dc <= 1'b0; end
            endcase
        end
    end
endmodule
