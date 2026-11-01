`timescale 1ns/1ps
`default_nettype none
// SPDX-License-Identifier: GPL-3.0-only
// Maintained opt-in adaptation of tang_mp3/vendor/tf_sd_spi_sector_reader.v
// (tang_fm_transmitter modifications, GPL-3.0; license: tang_mp3/LICENSE).
// Origin and immutable input hashes: WORKSTATION_TF_SD_SECTOR_NATIVE_20261030.md.
// This owner is deliberately NOT selected by any workstation build profile.
module workstation_tf_sd_sector_reader #(
    parameter integer SPI_CLK_DIV=100,
    parameter integer SPI_CLK_DIV_FAST=12,
    // 166.4 ms at the native 50-MHz source clock, independent of SPI divider.
    parameter integer TOKEN_WAIT_CLOCKS=8320000,
    // First-party integrity adaptation, opt-in; original manifests unchanged.
    parameter integer VERIFY_DATA_CRC=0
) (
    input wire rstn,clk,
    output wire spi_ssn,spi_sck,spi_mosi,
    input wire spi_miso,
    output wire [1:0] card_type,
    output wire [3:0] card_stat,
    input wire start,
    input wire [31:0] sector_no,
    output reg done,
    output reg rvalid,
    output reg [8:0] raddr,
    output reg [7:0] rdata,
    output wire [7:0] debug_cmdrsp,debug_rwrsp,
    output wire [3:0] debug_cardstate,
    output wire debug_spidone,debug_rvalid_session,
    // Terminal transport failure: no done, no automatic CMD17 replay. Reset
    // aborts/clears the entire owner and is required before explicit restart.
    output reg read_error,
    output reg [1:0] read_error_code
);
    localparam [1:0] NONE=0,SDV1=1,SDV2=2,SDHCV2=3;
    localparam [3:0] RESET=0,CMD0=1,CMD8=2,CMD1=3,CMD8FAILED=4,
        ACMD41=5,CMD58=6,CMD16=7,IDLE=8,READING=9,FAULT=10;
    localparam integer READ_DIV=(SPI_CLK_DIV_FAST==0) ? SPI_CLK_DIV : SPI_CLK_DIV_FAST;
    localparam integer BYTE_CLOCKS=16*(READ_DIV+1);
    // Ceiling preserves the requested patience; never truncate to 8 bits or
    // retain a fixed byte budget while accelerating the wire clock.
    localparam [63:0] WAIT_CLOCKS_WIDE={32'd0,TOKEN_WAIT_CLOCKS[31:0]};
    localparam [63:0] BYTE_CLOCKS_WIDE={32'd0,BYTE_CLOCKS[31:0]};
    localparam [63:0] TOKEN_BYTES_WIDE=(WAIT_CLOCKS_WIDE+BYTE_CLOCKS_WIDE-64'd1)/BYTE_CLOCKS_WIDE;
    localparam [23:0] TOKEN_BYTES=TOKEN_BYTES_WIDE[23:0];
    initial begin
        if(VERIFY_DATA_CRC!=0 && VERIFY_DATA_CRC!=1)
            $fatal(1,"native SD VERIFY_DATA_CRC must be 0 or 1");
        if(SPI_CLK_DIV<2 || SPI_CLK_DIV>255 || READ_DIV<2 || READ_DIV>255)
            $fatal(1,"native SD SPI divider must be in 2..255 (FAST=0 inherits init)");
        if(TOKEN_WAIT_CLOCKS<1 || TOKEN_BYTES_WIDE>64'hffffff)
            $fatal(1,"native SD token wait does not fit session counter");
    end

    reg [1:0] cardtype;
    reg [3:0] cardstate;
    reg start_q,spistart;
    reg [47:0] cmd,acmd;
    reg [7:0] waitcycle,precycle,startcycle,cmdrcycle,acmdcycle;
    reg [23:0] midcycle;
    wire spidone;
    wire [7:0] cmdrsp,acmdrsp,rwrsp;
    wire cmdrsp_valid,acmdrsp_valid;
    wire [47:0] cmdres;
    wire [31:0] read_argument=(cardtype==SDHCV2) ? sector_no : (sector_no<<9);
    wire [31:0] clkdiv_sel=(cardstate==READING) ? READ_DIV : SPI_CLK_DIV;
    wire rvalid_session;
    wire [15:0] rindex_session;
    wire [7:0] rdata_session;
    wire data_crc_complete,data_crc_valid;
    generate if(VERIFY_DATA_CRC!=0) begin: g_data_crc
        workstation_tf_sd_crc16_v1 crc_guard(
            .clk_i(clk),.rst_ni(rstn),
            .clear_i(cardstate==IDLE && !spistart && start && !start_q),
            .byte_valid_i(cardstate==READING && cmdrsp_valid && cmdrsp==8'h00 &&
                          rwrsp==8'hfe && rvalid_session),
            .byte_index_i(rindex_session),.byte_i(rdata_session),
            .complete_o(data_crc_complete),.valid_o(data_crc_valid));
    end else begin: g_no_data_crc
        assign data_crc_complete=1'b1;
        assign data_crc_valid=1'b1;
    end endgenerate
    assign card_type=cardtype;
    assign card_stat=cardstate;
    assign debug_cmdrsp=cmdrsp;
    assign debug_rwrsp=rwrsp;
    assign debug_cardstate=cardstate;
    assign debug_spidone=spidone;
    assign debug_rvalid_session=rvalid_session;

    always @(posedge clk or negedge rstn) begin
        if(!rstn) begin
            cardtype<=NONE; cardstate<=RESET;
            start_q<=0; spistart<=0; done<=0;
            cmd<=0; acmd<=0;
            waitcycle<=0; precycle<=0; startcycle<=0; cmdrcycle<=0;
            acmdcycle<=0; midcycle<=0;
            read_error<=0; read_error_code<=0;
        end else begin
            start_q<=start;
            done<=0;
            if(spidone) begin
                // Drop the held session request before another launch. A
                // completed read returns straight to IDLE, never a second
                // reading state and never a one-cycle ghost session.
                spistart<=0;
                case(cardstate)
                    CMD0: if(cmdrsp_valid && cmdrsp==8'h01) cardstate<=CMD8;
                    CMD1: if(cmdrsp_valid && cmdrsp==8'h00) cardstate<=IDLE;
                    CMD8: if(cmdrsp_valid && cmdrsp==8'h01) begin
                        if(cmdres[7:0]==8'haa) cardstate<=ACMD41;
                        else cardstate<=CMD8FAILED;
                    end else if(cmdrsp_valid) begin cardstate<=CMD1; cardtype<=SDV1; end
                    ACMD41: if(cmdrsp_valid && acmdrsp_valid && cmdrsp==8'h01 && acmdrsp==8'h00) cardstate<=CMD58;
                    CMD58: if(cmdrsp_valid && cmdrsp==8'h00) begin
                        cardtype<=((cmdres[31:24]&8'hc0)==8'hc0) ? SDHCV2 : SDV2;
                        cardstate<=CMD16;
                    end
                    CMD16: if(cmdrsp_valid && cmdrsp==8'h00) cardstate<=IDLE;
                    READING: if(cmdrsp_valid && cmdrsp==8'h00 && rwrsp==8'hfe) begin
                        // Verdict is applied only after the original session
                        // has drained both CRC bytes and its CS-high release.
                        if(VERIFY_DATA_CRC!=0 && (!data_crc_complete || !data_crc_valid)) begin
                            cardstate<=FAULT;
                            read_error<=1;
                            read_error_code<=2'd3;
                        end else begin cardstate<=IDLE;done<=1;end
                    end else begin
                        cardstate<=FAULT;
                        read_error<=1;
                        read_error_code<=(!cmdrsp_valid || cmdrsp!=8'h00) ? 2'd2 : 2'd1;
                    end
                    default: begin end
                endcase
            end else if(!spistart) begin
                // Session parameters are latched once and held until done.
                cmd<=0; acmd<=0; waitcycle<=16; precycle<=0;
                startcycle<=1; cmdrcycle<=0; acmdcycle<=0; midcycle<=0;
                case(cardstate)
                    RESET: cardstate<=CMD0;
                    CMD0: begin
                        spistart<=1; cmd<=48'h40_00000000_95;
                        waitcycle<=255; precycle<=20; startcycle<=0;
                    end
                    CMD1: begin spistart<=1; cmd<=48'h41_00000000_ff; startcycle<=0; end
                    CMD8: begin spistart<=1; cmd<=48'h48_000001aa_87; cmdrcycle<=4; end
                    ACMD41: begin
                        spistart<=1; cmd<=48'h77_00000000_ff;
                        acmd<=48'h69_40000000_ff; acmdcycle<=6;
                    end
                    CMD58: begin spistart<=1; cmd<=48'h7a_00000000_ff; cmdrcycle<=4; end
                    CMD16: begin spistart<=1; cmd<=48'h50_00000200_ff; cmdrcycle<=2; end
                    IDLE: if(start && !start_q) begin
                        cardstate<=READING; spistart<=1;
                        cmd<={8'h51,read_argument,8'hff};
                        waitcycle<=6; startcycle<=0;
                        // CMD17 has no R3/R7 response extension. Start token
                        // recognition immediately after R1, including an
                        // immediate token; do not discard four extra bytes.
                        midcycle<=TOKEN_BYTES;
                    end
                    default: begin end
                endcase
            end
        end
    end

    always @(posedge clk or negedge rstn) begin
        if(!rstn) begin rvalid<=0; raddr<=0; rdata<=0; end
        else begin
            rvalid<=0; raddr<=0; rdata<=0;
            // Session counts 514 received bytes downward: 513..2 are the
            // 512 payload bytes, 1/0 are CRC. Never expose timeout filler.
            if(cardstate==READING && cmdrsp_valid && cmdrsp==8'h00 && rwrsp==8'hfe &&
               rvalid_session && rindex_session>=16'd2 && rindex_session<16'd514) begin
                rvalid<=1;
                raddr<=9'd1-rindex_session[8:0];
                rdata<=rdata_session;
            end
        end
    end

    // Maintained response-valid adaptation; no generated RTL. CRC bytes
    // are drained (not checked, same as the historical reader). One byte of
    // clocks with CS high releases the card; the old 255-byte CS-low delay
    // is removed. Physical qualification remains required before selection.
    workstation_tf_spi_session u_spi_session (
        .rstn(rstn),.clk(clk),.spi_ssn(spi_ssn),.spi_sck(spi_sck),
        .spi_mosi(spi_mosi),.spi_miso(spi_miso),.start(spistart),.done(spidone),
        .clkdiv(clkdiv_sel),.cmd(cmd),.acmd(acmd),.waitcycle(waitcycle),
        .precycle(precycle),.startcycle(startcycle),.cmdcycle(8'd6),
        .cmdrcycle(cmdrcycle),.acmdcycle(acmdcycle),.acmdrcycle(8'd0),
        .midcycle(midcycle),.stopcycle(8'd0),.recycle(8'd1),
        .cmdrsp(cmdrsp),.acmdrsp(acmdrsp),.cmdrsp_valid(cmdrsp_valid),
        .acmdrsp_valid(acmdrsp_valid),.rwrsp(rwrsp),.cmdres(cmdres),.acmdres(),
        .rvalid(rvalid_session),.rindex(rindex_session),.rdata(rdata_session)
    );
endmodule
`default_nettype wire
