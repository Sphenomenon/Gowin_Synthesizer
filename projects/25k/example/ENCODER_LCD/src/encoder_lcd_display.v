`timescale 1ns/1ps
// NV3007 142x428, RGB565, mode-0 SPI. The board has no LCD reset GPIO.
// Draw the complete static page once, then refresh the two changing panels.
module encoder_lcd_display #(
    parameter integer CLK_HZ = 50000000,
    parameter integer MS_TICKS = CLK_HZ / 1000,
    // 5 MHz SPI (50 MHz / (2 * 5)); the NV3007 panel accepts this
    // conservative rate and it cuts the two changing-window transfer time.
    parameter integer SPI_HALF_PERIOD = 5,
    parameter integer BOOT_MS = 250,
    parameter integer POST_INIT_MS = 150,
    parameter integer REFRESH_GAP_MS = 2
) (
    input wire clk,
    input wire reset,
    input wire [15:0] pixel_color,
    output reg [15:0] pixel_x = 0,
    output reg [15:0] pixel_y = 0,
    output reg snapshot = 1'b0,
    output reg [31:0] completed_refreshes = 0,
    output wire lcd_ncs,
    output wire lcd_dc,
    output wire lcd_sck,
    output wire lcd_mosi
);
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

    // Use the proven panel initialization, including its required delays.
    reg [8:0] rom_index = 0;
    wire [1:0] rom_kind;
    wire [15:0] rom_value;
    lcd_init_rom init_rom (.index(rom_index), .kind(rom_kind), .value(rom_value));

    localparam [3:0] ST_BOOT=0, ST_INIT=1, ST_INIT_DELAY=2, ST_POST_INIT=3,
                     ST_SNAPSHOT=4, ST_SETTLE=5, ST_WINDOW=6, ST_PIXELS=7,
                     ST_WINDOW_END=8, ST_GAP=9;
    localparam integer BOOT_CYCLES = BOOT_MS * MS_TICKS;
    localparam integer POST_INIT_CYCLES = POST_INIT_MS * MS_TICKS;
    localparam integer GAP_CYCLES = REFRESH_GAP_MS * MS_TICKS;
    reg [3:0] state = ST_BOOT;
    reg [31:0] delay_count = 0;
    reg waiting_tx = 1'b0;
    reg [3:0] window_index = 0;
    reg full_frame = 1'b1;
    reg bottom_window = 1'b0;
    reg pixel_low_byte = 1'b0;
    reg [15:0] pixel_hold = 0;

    // Pixel coordinates are logical screen positions. CASET includes the
    // panel's 12-column offset; RASET needs no offset in MADCTL=00 mode.
    wire [15:0] x_first = full_frame ? 16'd0 : 16'd8;
    wire [15:0] x_last = full_frame ? 16'd141 : 16'd133;
    wire [15:0] y_first = full_frame ? 16'd0 :
                         bottom_window ? 16'd256 : 16'd72;
    wire [15:0] y_last = full_frame ? 16'd427 :
                        bottom_window ? 16'd353 : 16'd169;
    wire [15:0] column_first = x_first + 16'd12;
    wire [15:0] column_last = x_last + 16'd12;

    always @(posedge clk) begin
        tx_start <= 1'b0;
        snapshot <= 1'b0;
        if (reset) begin
            ncs <= 1'b1;
            dc <= 1'b0;
            tx_data <= 0;
            state <= ST_BOOT;
            delay_count <= BOOT_CYCLES > 0 ? BOOT_CYCLES - 1 : 0;
            waiting_tx <= 1'b0;
            rom_index <= 0;
            window_index <= 0;
            full_frame <= 1'b1;
            bottom_window <= 1'b0;
            pixel_x <= 0;
            pixel_y <= 0;
            pixel_low_byte <= 1'b0;
            pixel_hold <= 0;
            completed_refreshes <= 0;
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
                            delay_count <= POST_INIT_CYCLES > 0 ? POST_INIT_CYCLES - 1 : 0;
                            state <= ST_POST_INIT;
                        end
                    endcase
                end
                ST_INIT_DELAY: begin
                    if (delay_count == 0) state <= ST_INIT;
                    else delay_count <= delay_count - 1'b1;
                end
                ST_POST_INIT: begin
                    if (delay_count == 0) state <= ST_SNAPSHOT;
                    else delay_count <= delay_count - 1'b1;
                end
                ST_SNAPSHOT: begin
                    // The renderer holds one coherent encoder sample across
                    // both windows. Allow its 32-step BCD conversion to finish.
                    snapshot <= 1'b1;
                    delay_count <= 31;
                    state <= ST_SETTLE;
                end
                ST_SETTLE: begin
                    if (delay_count == 0) begin
                        window_index <= full_frame ? 0 : 3;
                        state <= ST_WINDOW;
                    end else delay_count <= delay_count - 1'b1;
                end
                ST_WINDOW: begin
                    if (window_index == 14) begin
                        pixel_x <= x_first;
                        pixel_y <= y_first;
                        pixel_low_byte <= 1'b0;
                        state <= ST_PIXELS;
                    end else begin
                        ncs <= 1'b0;
                        dc <= 1'b1;
                        case (window_index)
                            0: begin tx_data <= 8'h36; dc <= 1'b0; end
                            1: tx_data <= 8'h00; // MADCTL=00, native 142x428.
                            2: begin tx_data <= 8'h20; dc <= 1'b0; end
                            3: begin tx_data <= 8'h2a; dc <= 1'b0; end
                            4: tx_data <= column_first[15:8];
                            5: tx_data <= column_first[7:0];
                            6: tx_data <= column_last[15:8];
                            7: tx_data <= column_last[7:0];
                            8: begin tx_data <= 8'h2b; dc <= 1'b0; end
                            9: tx_data <= y_first[15:8];
                            10: tx_data <= y_first[7:0];
                            11: tx_data <= y_last[15:8];
                            12: tx_data <= y_last[7:0];
                            default: begin tx_data <= 8'h2c; dc <= 1'b0; end
                        endcase
                        window_index <= window_index + 1'b1;
                        tx_start <= 1'b1;
                        waiting_tx <= 1'b1;
                    end
                end
                ST_PIXELS: begin
                    dc <= 1'b1;
                    tx_data <= pixel_low_byte ? pixel_hold[7:0] : pixel_color[15:8];
                    if (!pixel_low_byte) pixel_hold <= pixel_color;
                    tx_start <= 1'b1;
                    waiting_tx <= 1'b1;
                    pixel_low_byte <= !pixel_low_byte;
                    if (pixel_low_byte) begin
                        if (pixel_x == x_last) begin
                            pixel_x <= x_first;
                            if (pixel_y == y_last) state <= ST_WINDOW_END;
                            else pixel_y <= pixel_y + 1'b1;
                        end else pixel_x <= pixel_x + 1'b1;
                    end
                end
                ST_WINDOW_END: begin
                    // waiting_tx keeps CS asserted through the final falling
                    // edge, including the last byte of each update window.
                    ncs <= 1'b1;
                    dc <= 1'b0;
                    if (full_frame) begin
                        full_frame <= 1'b0;
                        bottom_window <= 1'b0;
                        completed_refreshes <= completed_refreshes + 1'b1;
                        state <= ST_SNAPSHOT;
                    end else if (!bottom_window) begin
                        bottom_window <= 1'b1;
                        window_index <= 3;
                        state <= ST_WINDOW;
                    end else begin
                        bottom_window <= 1'b0;
                        completed_refreshes <= completed_refreshes + 1'b1;
                        delay_count <= GAP_CYCLES > 0 ? GAP_CYCLES - 1 : 0;
                        state <= ST_GAP;
                    end
                end
                ST_GAP: begin
                    if (delay_count == 0) state <= ST_SNAPSHOT;
                    else delay_count <= delay_count - 1'b1;
                end
                default: begin ncs <= 1'b1; dc <= 1'b0; end
            endcase
        end
    end
endmodule
