`timescale 1ns/1ps
// SD/FAT byte endpoint fixture derived from the maintained TF local test.
// It replaces only physical card/file enumeration, not DDR, WAV decoding,
// clear/stop mailboxes, atomic PCM transport, runtime clocks or serial audio.
module tf_sd_file_reader #(
    parameter [23:0] EXT="WAV",
    parameter integer SPI_CLK_DIV=100,SPI_CLK_DIV_FAST=12,
    parameter integer FILE_BYTES=16428
) (
    input wire rstn,clk,spi_miso,track_start,sector_allow,
    input wire [3:0] track_index,
    input wire [7:0] name_raddr,
    output wire spi_ssn,spi_sck,spi_mosi,
    output wire [1:0] card_type,filesystem_type,
    output wire [3:0] card_stat,debug_cardstate,
    output wire [2:0] filesystem_stat,
    output wire scan_done,sector_busy,playing,
    output reg eof,outen,
    output reg [7:0] outbyte,
    output wire [4:0] track_count,
    output wire [7:0] name_rdata,debug_cmdrsp,debug_rwrsp,
    output wire debug_spidone,debug_rvalid_session
);
    reg present=1;
    reg active,start_pending;
    integer index;
    reg [3:0] selected;
    reg [7:0] file0[0:FILE_BYTES-1],file1[0:FILE_BYTES-1],file2[0:FILE_BYTES-1],file3[0:FILE_BYTES-1];
    initial begin
        if(FILE_BYTES!=16428)$fatal(1,"SD fixture/WAV length contract changed");
        $readmemh("file0.hex",file0);$readmemh("file1.hex",file1);
        $readmemh("file2.hex",file2);$readmemh("file3.hex",file3);
    end
    assign spi_ssn=1;assign spi_sck=0;assign spi_mosi=0;
    assign card_type=2;assign filesystem_type=1;assign filesystem_stat=0;
    assign card_stat=8;assign debug_cardstate=8;assign scan_done=rstn && present;
    assign track_count=4;assign name_rdata=name_raddr;
    assign sector_busy=!present;assign playing=active;
    assign debug_cmdrsp=present ? 0:8'h80;assign debug_rwrsp=0;
    assign debug_spidone=0;assign debug_rvalid_session=present;
    always @(posedge clk or negedge rstn)begin
        if(!rstn)begin active<=0;start_pending<=0;index<=0;selected<=0;outen<=0;eof<=0;outbyte<=0;end
        else begin
            outen<=0;eof<=0;
            if(track_start && present)begin active<=0;start_pending<=1;index<=0;selected<=track_index;end
            else if(start_pending)begin active<=1;start_pending<=0;end
            else if(active && present && sector_allow)begin
                outen<=1;
                case(selected)
                    0:outbyte<=file0[index];1:outbyte<=file1[index];
                    2:outbyte<=file2[index];default:outbyte<=file3[index];
                endcase
                if(index==FILE_BYTES-1)begin active<=0;eof<=1;end else index<=index+1;
            end
        end
    end
endmodule
