`timescale 1ns/1ps
// Historical control-FSM observation only. Card initialization and the SPI
// wire protocol are deliberately outside this fixture. The runner retrieves
// the actual sector owner from one fixed committed revision.
module tb_tf_sector_duplicate_command_audit;
    reg clk=0,rst_n=0,start=0;
    always #10 clk=~clk;
    wire done,valid;
    reg previous_start=0;
    integer requests=0,starts=0,completed_sessions=0,logical_done=0;
    integer raw_bytes=0,forwarded_bytes=0;
    tf_sd_spi_sector_reader #(.SPI_CLK_DIV(100),.SPI_CLK_DIV_FAST(12)) dut(
        .rstn(rst_n),.clk,.spi_ssn(),.spi_sck(),.spi_mosi(),.spi_miso(1'b1),
        .card_type(),.card_stat(),.start,.sector_no(32'd123),.done,
        .rvalid(valid),.raddr(),.rdata(),.debug_cmdrsp(),.debug_rwrsp(),
        .debug_cardstate(),.debug_spidone(),.debug_rvalid_session());
    always @(posedge clk)if(rst_n)begin
        previous_start<=dut.spistart;
        if(start)requests=requests+1;
        if(dut.spistart && !previous_start)begin
            starts=starts+1;
            if(dut.cmd!={8'h51,32'd123,8'hff})$fatal(1,"unexpected command/sector");
        end
        if(dut.spidone)completed_sessions=completed_sessions+1;
        if(done)logical_done=logical_done+1;
        if(dut.rvalid_session)raw_bytes=raw_bytes+1;
        if(valid)forwarded_bytes=forwarded_bytes+1;
    end
    initial begin
        repeat(4)@(negedge clk);
        // Deposit the documented initialized SDHC/IDLE state. This test does
        // not claim to run the card initialization or verify physical SPI.
        rst_n=1;dut.cardstate=4'd8;dut.cardtype=2'd3;
        @(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(done);repeat(50)@(negedge clk);
        // The third start lasts one source clock while req_hold clears; it
        // is aborted before any stub byte, so it is not a completed session.
        if(requests!=1 || starts!=3 || completed_sessions!=2 || logical_done!=1 ||
           raw_bytes!=1024 || forwarded_bytes!=512)
            $fatal(1,"historical sector audit mismatch requests=%0d starts=%0d completed=%0d done=%0d raw=%0d forwarded=%0d",
                requests,starts,completed_sessions,logical_done,raw_bytes,forwarded_bytes);
        $display("PASS tf_sector_duplicate_command_audit: requests=%0d starts=%0d completed_sessions=%0d logical_done=%0d raw_bytes=%0d forwarded_bytes=%0d",
            requests,starts,completed_sessions,logical_done,raw_bytes,forwarded_bytes);
        $finish;
    end
    initial begin #100000;$fatal(1,"historical sector audit timeout");end
endmodule

// Successful-session fixture: 512 data bytes and a terminal pulse, with no
// SD signal timing or real SPI implementation. The real parent FSM decides
// whether to execute another command and whether to forward these bytes.
module tf_spi_session(
    input wire rstn,clk,start,
    input wire [31:0] clkdiv,
    input wire [47:0] cmd,acmd,
    input wire [7:0] waitcycle,precycle,startcycle,cmdcycle,cmdrcycle,
        acmdcycle,acmdrcycle,stopcycle,recycle,
    input wire [23:0] midcycle,
    output wire spi_ssn,spi_sck,spi_mosi,done,
    input wire spi_miso,
    output wire [7:0] cmdrsp,acmdrsp,rwrsp,
    output wire [47:0] cmdres,acmdres,
    output wire rvalid,
    output wire [15:0] rindex,
    output wire [7:0] rdata
);
    reg [15:0] cycle;
    always @(posedge clk or negedge rstn)
        if(!rstn)cycle<=0;
        else if(!start)cycle<=0;
        else cycle<=cycle+1'b1;
    assign done=start && cycle==16'd520;
    assign rvalid=start && cycle>=16'd2 && cycle<16'd514;
    assign rindex=16'd515-cycle;
    assign rdata=cycle[7:0];
    assign cmdrsp=8'd0,acmdrsp=8'd0,rwrsp=8'hfe,cmdres=48'd0,acmdres=48'd0;
    assign spi_ssn=1'b1,spi_sck=1'b1,spi_mosi=1'b1;
endmodule
