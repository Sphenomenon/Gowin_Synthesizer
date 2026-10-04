`timescale 1ns/1ps
module tb_tf_hotplug_probe;
    reg clk=0,rstn=0,card_present=1,sector_allow=0,track_start=0;
    wire [2:0] filesystem_stat;
    wire scan_done,sector_busy,spi_ssn,spi_sck,spi_mosi,outen;
    wire [4:0] track_count;
    wire [7:0] name_rdata;
    integer probes=0;
    always #10 clk=~clk;
    tf_sd_file_reader #(.PROBE_INTERVAL_CYCLES(26'd20)) dut(
        .rstn,.clk,.spi_ssn,.spi_sck,.spi_mosi,.spi_miso(card_present),
        .card_type(),.card_stat(),.filesystem_type(),.filesystem_stat,
        .scan_done,.sector_busy,.track_count,.track_index(4'd0),
        .track_start(track_start),.playing(),.eof(),.sector_allow(sector_allow),
        .outen,.outbyte(),.name_raddr(8'd0),.name_rdata,
        .debug_cmdrsp(),.debug_rwrsp(),.debug_cardstate(),
        .debug_spidone(),.debug_rvalid_session());
    always @(posedge clk) if(rstn && dut.read_start && dut.read_sector_no==0)
        probes=probes+1;
    initial begin
        repeat(3) @(negedge clk);rstn=1;
        repeat(4) @(negedge clk);
        if(dut.inflight || dut.read_start)
            $fatal(1,"boot request launched before card initialization");
        repeat(6) @(negedge clk);
        if(!dut.inflight)
            $fatal(1,"boot request did not launch after card initialization");
        dut.filesystem_state=3'd7;
        dut.inflight=0;
        repeat(70) @(negedge clk);
        if(probes<2 || !scan_done || sector_busy)
            $fatal(1,"idle poll failed probes=%0d busy=%b",probes,sector_busy);
        card_present=0;
        repeat(40) @(negedge clk);
        if(!sector_busy || !dut.probe_pending)
            $fatal(1,"missing card did not leave outstanding probe");
        rstn=0;
        repeat(3) @(negedge clk);
        if(scan_done || sector_busy || track_count!=0)
            $fatal(1,"fault reset retained stale directory");
        card_present=1;rstn=1;
        @(negedge clk);dut.filesystem_state=3'd7;
        repeat(40) @(negedge clk);
        if(!scan_done || sector_busy)
            $fatal(1,"reader did not recover after reinsertion");
        // A full downstream FIFO stalls an open file. Hotplug must still be
        // detected, and sector-0 probe bytes must never enter file output.
        dut.filesystem_state=3'd5;
        dut.file_size=32'd4096;
        dut.fptr=0;
        dut.read_sector_no=32'd123;
        sector_allow=1;
        @(negedge clk);
        if(!dut.read_start || !dut.inflight)
            $fatal(1,"file sector request did not start");
        repeat(3) begin
            @(negedge clk);
            if(dut.read_start)
                $fatal(1,"file sector request repeated while in flight");
        end
        sector_allow=0;
        while(dut.inflight) @(negedge clk);
        dut.read_sector_no=32'd123;
        probes=0;
        begin : wait_paused_probe
            integer i;
            for(i=0;i<90 && !dut.probe_pending;i=i+1) @(negedge clk);
        end
        @(negedge clk);
        if(probes==0 || !sector_busy || !dut.probe_pending)
            $fatal(1,"paused file did not probe card state=%0d timer=%0d inflight=%b probes=%0d",
                   dut.filesystem_state,dut.probe_timer,dut.inflight,probes);
        dut.u_sector_reader.inject_rvalid=1;
        repeat(2) @(negedge clk);
        if(outen || dut.fptr!=0)
            $fatal(1,"probe bytes leaked into paused file");
        dut.u_sector_reader.inject_rvalid=0;
        begin : wait_resume
            integer i;
            for(i=0;i<20 && dut.probe_pending;i=i+1) @(negedge clk);
        end
        if(dut.probe_pending || dut.read_sector_no!=32'd123)
            $fatal(1,"probe did not resume file sector %0d",dut.read_sector_no);
        card_present=0;
        repeat(35) @(negedge clk);
        if(!sector_busy)
            $fatal(1,"removed card was not detected in paused file state");
        card_present=1;
        rstn=0;
        repeat(3) @(negedge clk);
        rstn=1;
        repeat(10) @(negedge clk);
        while(dut.inflight) @(negedge clk);
        dut.filesystem_state=3'd5;
        dut.playing=1;
        dut.file_size=32'd4096;
        dut.fptr=0;
        sector_allow=0;
        track_start=1;
        @(negedge clk);
        track_start=0;
        @(negedge clk);
        if(dut.filesystem_state!=3'd7 || dut.playing || dut.inflight)
            $fatal(1,"paused file did not accept track change state=%0d playing=%b inflight=%b start_req=%b",
                   dut.filesystem_state,dut.playing,dut.inflight,dut.start_req);
        $display("PASS TF idle probe, removal stall, reset and reinsertion");$finish;
    end
endmodule

module tf_sd_spi_sector_reader #(
    parameter SPI_CLK_DIV=50,SPI_CLK_DIV_FAST=3
)(
    input wire rstn,clk,output wire spi_ssn,spi_sck,spi_mosi,
    input wire spi_miso,output wire [1:0] card_type,
    output wire [3:0] card_stat,input wire start,input wire [31:0] sector_no,
    output reg done,output wire rvalid,output wire [8:0] raddr,
    output wire [7:0] rdata,debug_cmdrsp,debug_rwrsp,
    output wire [3:0] debug_cardstate,
    output wire debug_spidone,debug_rvalid_session
);
    reg [2:0] delay_count;
    reg [3:0] init_cycles;
    reg inject_rvalid=0;
    assign spi_ssn=1;assign spi_sck=0;assign spi_mosi=1;
    assign card_type=3;assign card_stat=(init_cycles==4'd8) ? 4'd8 : 4'd3;
    assign rvalid=inject_rvalid;assign raddr=0;assign rdata=8'hA5;
    assign debug_cmdrsp=0;assign debug_rwrsp=0;
    assign debug_cardstate=8;assign debug_spidone=0;
    assign debug_rvalid_session=0;
    always @(posedge clk or negedge rstn) begin
        if(!rstn)begin delay_count<=0;done<=0;init_cycles<=0;end
        else begin
            if(init_cycles!=4'd8)init_cycles<=init_cycles+1'b1;
            done<=0;
            if(start && delay_count==0 && spi_miso)delay_count<=3'd4;
            else if(delay_count!=0)begin
                delay_count<=delay_count-1'b1;
                if(delay_count==1)done<=1;
            end
        end
    end
endmodule
