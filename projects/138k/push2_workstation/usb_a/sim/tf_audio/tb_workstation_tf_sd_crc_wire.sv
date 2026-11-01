`timescale 1ns/1ps
`default_nettype none
// Real public SPI/sector ports. CRC faults do not inject bytes into the DUT.
module tb_workstation_tf_sd_crc_wire #(
    parameter integer FAULT=0,VERIFY_CRC=1,READ_DIV=2,CARD_KIND=0
);
    reg clk=0;always #10 clk=~clk;
    reg rstn=0,start=0;
    wire ssn,sck,mosi,miso,done,rvalid,read_error;
    wire [1:0] card_type,error_code;
    wire [3:0] card_stat;
    wire [8:0] raddr;
    wire [7:0] rdata;
    integer fault_kind=FAULT;
    wire integer commands,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,high_clocks;
    wire integer transaction_payload_bytes,transaction_crc_bytes;
    wire transaction_live;
    wire [31:0] last_argument,last_lba;
    workstation_tf_sd_sector_reader #(.SPI_CLK_DIV(100),.SPI_CLK_DIV_FAST(READ_DIV),
        .TOKEN_WAIT_CLOCKS(8320),.VERIFY_DATA_CRC(VERIFY_CRC)) dut(
        .rstn(rstn),.clk(clk),.spi_ssn(ssn),.spi_sck(sck),.spi_mosi(mosi),.spi_miso(miso),
        .card_type(card_type),.card_stat(card_stat),.start(start),.sector_no(32'd0),
        .done(done),.rvalid(rvalid),.raddr(raddr),.rdata(rdata),.read_error(read_error),
        .read_error_code(error_code),.debug_cmdrsp(),.debug_rwrsp(),.debug_cardstate(),
        .debug_spidone(),.debug_rvalid_session());
    workstation_tf_sd_crc_wire_card #(.CARD_KIND(CARD_KIND)) card(
        .ssn(ssn),.sck(sck),.mosi(mosi),.miso(miso),.token_delay_bytes(2),.hold_init(1'b0),
        .fault_lba(32'd0),.fault_kind(fault_kind),.suppress_token(1'b0),.command_error(1'b0),.suppress_r1(1'b0),
        .cmd17_count(commands),.payload_bytes(payload_bytes),.crc_bytes(crc_bytes),.post_crc_bytes(post_crc_bytes),
        .cs_releases(cs_releases),.high_clocks(high_clocks),.last_argument(last_argument),.last_lba(last_lba),
        .transaction_payload_bytes(transaction_payload_bytes),.transaction_crc_bytes(transaction_crc_bytes),
        .transaction_live(transaction_live));
    reg [7:0] oracle[0:511];
    reg [2047:0] oracle_path;
    integer cycles=0,seen=0,terminals=0,before_cmd,before_payload,before_crc,before_release,before_high;
    reg checking=0;
    localparam integer EXPECT_ERROR=(VERIFY_CRC!=0 && FAULT!=0);
    always @(posedge clk)begin
        cycles=cycles+1;
        if(cycles>10000000)$fatal(1,"bounded CRC wire timeout");
        if(rstn && rvalid)begin
            if(!checking || seen>=512 || raddr!==9'(seen))$fatal(1,"CRC wire payload address/count");
            if(rdata!==(oracle[seen]^((FAULT==1 && seen==257)?8'h01:8'h00)))$fatal(1,"CRC wire payload oracle");
            seen=seen+1;
        end
        if(rstn && checking && (done || read_error) && terminals==0)begin
            if(transaction_payload_bytes!=512 || transaction_crc_bytes!=2 || !ssn ||
               high_clocks<before_high+8 || payload_bytes!=before_payload+512 ||
               crc_bytes!=before_crc+2 || cs_releases!=before_release+1 ||
               post_crc_bytes!=0 || commands!=before_cmd+1 || seen!=512)
                $fatal(1,"CRC terminal preceded exact payload/CRC/CS-high drain payload=%0d crc=%0d high=%0d seen=%0d",transaction_payload_bytes,transaction_crc_bytes,high_clocks-before_high,seen);
            if(EXPECT_ERROR ? (!read_error || done || error_code!=3 || card_stat!=10) :
                              (read_error || !done || error_code!=0 || card_stat!=8))
                $fatal(1,"CRC verdict mismatch fault=%0d verify=%0d error=%0b code=%0d done=%0b",FAULT,VERIFY_CRC,read_error,error_code,done);
            terminals=terminals+1;
        end
    end
    task clocks(input integer count);repeat(count)@(negedge clk);endtask
    initial begin
        if(!$value$plusargs("ORACLE=%s",oracle_path))$fatal(1,"missing independent payload oracle");
        $readmemh(oracle_path,oracle);
        clocks(10);rstn=1;wait(card_stat==8);clocks(3);
        before_cmd=commands;before_payload=payload_bytes;before_crc=crc_bytes;
        before_release=cs_releases;before_high=high_clocks;
        checking=1;start=1;clocks(1);start=0;
        wait(terminals==1);clocks(300);
        if(EXPECT_ERROR)begin start=1;clocks(300);start=0;end
        if(commands!=before_cmd+1 || terminals!=1 || rvalid || !ssn ||
           payload_bytes!=before_payload+512 || crc_bytes!=before_crc+2)
            $fatal(1,"CRC terminal retried or leaked");
        $display("PASS tf_sd_crc_wire fault=%0d verify=%0d divider=%0d kind=%0d payload=%0d crc=%0d terminals=%0d error=%0d commands=%0d",FAULT,VERIFY_CRC,READ_DIV,CARD_KIND,seen,transaction_crc_bytes,terminals,error_code,commands);
        $finish;
    end
endmodule
`default_nettype wire
