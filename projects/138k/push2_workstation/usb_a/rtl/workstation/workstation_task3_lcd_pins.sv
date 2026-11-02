`timescale 1ns/1ps
// Experimental FPC4 n->n mapping. The user confirmed same-number networks;
// cable contact orientation does not imply n->41-n. M/W are fixed recipes.
// Both compile-time and runtime enables are required to drive ANY pad.
module workstation_task3_lcd_pins #(
    parameter bit EXPERIMENT_ENABLE=1'b0,
    parameter bit ROLE_M=1'b1
)(
    input wire drive_enable_i,
    input wire [3:0] tx_data_i,
    input wire tx_req_i,rx_ack_i,panic_i,
    output wire [3:0] rx_data_o,
    output wire rx_req_o,tx_ack_o,peer_panic_o,
    inout wire [4:0] lcd_r,lcd_b,
    inout wire [5:0] lcd_g,
    inout wire lcd_pclk,lcd_hsync,lcd_vsync,lcd_de,lcd_bl,
    inout wire lcd_ctp_rst,lcd_ctp_sda,lcd_ctp_scl,lcd_ctp_int
);
    wire drive=EXPERIMENT_ENABLE && drive_enable_i;
    generate if(ROLE_M)begin: g_m
        // M->W data FPC4.3..6, req .7; W->M ACK .12.
        assign lcd_r=drive?{tx_req_i,tx_data_i}:5'bzzzzz;
        // W->M data .13..16, req .17; .12 belongs to W.
        assign lcd_g=6'bzzzzzz;
        assign lcd_b[0]=drive?rx_ack_i:1'bz; // M acknowledges W, .21
        assign lcd_b[1]=drive?panic_i:1'bz;  // M emergency, .22
        assign lcd_b[4:2]=3'bzzz;
        assign rx_data_o=lcd_g[4:1];assign rx_req_o=lcd_g[5];
        assign tx_ack_o=lcd_g[0];assign peer_panic_o=lcd_b[2];
    end else begin: g_w
        assign lcd_r=5'bzzzzz;
        assign lcd_g=drive?{tx_req_i,tx_data_i,rx_ack_i}:6'bzzzzzz;
        assign lcd_b[1:0]=2'bzz;
        assign lcd_b[2]=drive?panic_i:1'bz; // W emergency, .23
        assign lcd_b[4:3]=2'bzz;
        assign rx_data_o=lcd_r[3:0];assign rx_req_o=lcd_r[4];
        assign tx_ack_o=lcd_b[0];assign peer_panic_o=lcd_b[1];
    end endgenerate
    // These eleven programmable wires remain reserved and never driven by
    // this probe. FPC4 hard GND/+5V/NC are not represented as FPGA ports.
    assign {lcd_pclk,lcd_hsync,lcd_vsync,lcd_de,lcd_bl}=5'bzzzzz;
    assign {lcd_ctp_rst,lcd_ctp_sda,lcd_ctp_scl,lcd_ctp_int}=4'bzzzz;
endmodule
