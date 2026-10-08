`timescale 1ns/1ps
// Shared configuration Flash pads are released during boot/reset/DDR wait and
// after the transaction. Board/CST pulls provide CS/WP/HOLD high, SCK low.
// Only registered active-low SPI CS grants user ownership; this also releases
// IO2/IO3 for configuration/other masters while the model client is idle.
module basic_pitch_flash_io_guard (
    input wire spi_cs_n_i, spi_clk_i, spi_mosi_i,
    output wire flash_cs_n_o, flash_clk_o, flash_mosi_o,
    output wire flash_wp_n_o, flash_hold_n_o,
    output wire owned_o
);
    assign owned_o = !spi_cs_n_i;
    assign flash_cs_n_o = owned_o ? 1'b0 : 1'bz;
    assign flash_clk_o = owned_o ? spi_clk_i : 1'bz;
    assign flash_mosi_o = owned_o ? spi_mosi_i : 1'bz;
    assign flash_wp_n_o = owned_o ? 1'b1 : 1'bz;
    assign flash_hold_n_o = owned_o ? 1'b1 : 1'bz;
endmodule
