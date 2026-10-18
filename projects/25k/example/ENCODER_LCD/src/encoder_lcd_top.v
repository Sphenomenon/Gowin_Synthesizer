`timescale 1ns/1ps
// Independent board bring-up: SW1/SW2 inputs and the verified NV3007 panel.
module encoder_lcd_top #(
    parameter integer CLK_HZ = 50000000,
    parameter integer AB_FILTER_CYCLES = CLK_HZ / 50000,
    parameter integer KEY_FILTER_CYCLES = CLK_HZ / 1000,
    parameter integer MS_TICKS = CLK_HZ / 1000,
    parameter integer SPI_HALF_PERIOD = 5,
    parameter integer BOOT_MS = 250,
    parameter integer POST_INIT_MS = 150,
    parameter integer REFRESH_GAP_MS = 2
) (
    input wire clk,
    input wire sw1_a, sw1_b, sw1_key_n,
    input wire sw2_a, sw2_b, sw2_key_n,
    input wire lcd_te,
    output wire lcd_ncs, lcd_dc, lcd_sck, lcd_mosi
);
    reg [5:0] por_count = 0;
    wire reset = !(&por_count);
    always @(posedge clk)
        if (reset) por_count <= por_count + 1'b1;

    wire signed [15:0] position1, position2;
    wire [15:0] press_count1, press_count2, invalid_count1, invalid_count2;
    wire [1:0] ab1, ab2;
    wire key1, key2;
    wire signed [1:0] direction1, direction2;
    encoder_input #(.CLK_HZ(CLK_HZ), .AB_FILTER_CYCLES(AB_FILTER_CYCLES),
                    .KEY_FILTER_CYCLES(KEY_FILTER_CYCLES)) enc1 (
        .clk(clk), .reset(reset), .a(sw1_a), .b(sw1_b), .key_n(sw1_key_n),
        .position(position1), .press_count(press_count1), .invalid_count(invalid_count1),
        .ab_state(ab1), .key_pressed(key1), .direction(direction1),
        .step_pulse(), .press_pulse()
    );
    encoder_input #(.CLK_HZ(CLK_HZ), .AB_FILTER_CYCLES(AB_FILTER_CYCLES),
                    .KEY_FILTER_CYCLES(KEY_FILTER_CYCLES)) enc2 (
        .clk(clk), .reset(reset), .a(sw2_a), .b(sw2_b), .key_n(sw2_key_n),
        .position(position2), .press_count(press_count2), .invalid_count(invalid_count2),
        .ab_state(ab2), .key_pressed(key2), .direction(direction2),
        .step_pulse(), .press_pulse()
    );

    wire [15:0] pixel_x, pixel_y, pixel_color;
    wire snapshot;
    wire [31:0] completed_refreshes;
    encoder_lcd_view view (
        .clk(clk), .reset(reset), .snapshot(snapshot),
        .position1(position1), .position2(position2),
        .press_count1(press_count1), .press_count2(press_count2),
        .invalid_count1(invalid_count1), .invalid_count2(invalid_count2),
        .ab1(ab1), .ab2(ab2), .key1(key1), .key2(key2),
        .direction1(direction1), .direction2(direction2),
        .pixel_x(pixel_x), .pixel_y(pixel_y), .pixel_color(pixel_color)
    );
    encoder_lcd_display #(.CLK_HZ(CLK_HZ), .MS_TICKS(MS_TICKS),
        .SPI_HALF_PERIOD(SPI_HALF_PERIOD), .BOOT_MS(BOOT_MS),
        .POST_INIT_MS(POST_INIT_MS), .REFRESH_GAP_MS(REFRESH_GAP_MS)) display (
        .clk(clk), .reset(reset), .pixel_color(pixel_color),
        .pixel_x(pixel_x), .pixel_y(pixel_y), .snapshot(snapshot),
        .completed_refreshes(completed_refreshes),
        .lcd_ncs(lcd_ncs), .lcd_dc(lcd_dc), .lcd_sck(lcd_sck), .lcd_mosi(lcd_mosi)
    );
    // lcd_te is deliberately not used: 1 MHz writes are independent of TE.
endmodule
