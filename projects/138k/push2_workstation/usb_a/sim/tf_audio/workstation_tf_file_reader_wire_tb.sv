`timescale 1ns/1ps
`default_nettype none
// Public file/SPI ports only. No force, deposit, DUT register writes or stub.
module tb_workstation_tf_file_reader_wire #(
    parameter integer MODE=0, EXPECT_ERROR=0, MAX_ROOT=4096,
    parameter integer SIZE0=700, SIZE1=257, EXPECT_TRACKS=2,
    parameter integer PROBE=50000000, WATCHDOG=500000,
    parameter integer INITIAL_FAULT_KIND=0,
    parameter [31:0] INITIAL_FAULT_LBA=32'hffffffff
);
    reg clk=0;always #10 clk=~clk;
    reg rstn=0,track_start=0,stop=0,sector_allow=0;
    reg [3:0] track_index=0;
    reg [7:0] name_raddr=0;
    wire [7:0] name_rdata,outbyte;
    wire ssn,sck,mosi,miso,scan_done,sector_busy,playing,eof,outen;
    wire cancelled,track_applied,data_sector_start,file_error;
    wire [3:0] error_code,card_stat;
    wire [1:0] filesystem_type;
    wire [2:0] filesystem_stat;
    wire [4:0] track_count;
    reg hold_init=(MODE==5);
    reg [31:0] fault_lba=32'hffffffff;
    integer fault_kind=0;
    wire integer commands,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,high_clocks;
    wire [31:0] last_argument;
    workstation_tf_file_reader #(.SPI_CLK_DIV(2),.SPI_CLK_DIV_FAST(2),
        .TOKEN_WAIT_CLOCKS(1000),.WATCHDOG_CLOCKS(WATCHDOG),
        .MAX_ROOT_SECTORS(MAX_ROOT),.PROBE_INTERVAL_CYCLES(PROBE)) dut (
        .rstn(rstn),.clk(clk),.spi_ssn(ssn),.spi_sck(sck),.spi_mosi(mosi),.spi_miso(miso),
        .card_type(),.card_stat(card_stat),.filesystem_type(filesystem_type),.filesystem_stat(filesystem_stat),
        .scan_done(scan_done),.sector_busy(sector_busy),.track_count(track_count),
        .track_index(track_index),.track_start(track_start),.stop(stop),.cancelled(cancelled),
        .track_applied(track_applied),.data_sector_start(data_sector_start),.file_error(file_error),
        .file_error_code(error_code),.playing(playing),.eof(eof),.sector_allow(sector_allow),
        .outen(outen),.outbyte(outbyte),.name_raddr(name_raddr),.name_rdata(name_rdata),
        .debug_cmdrsp(),.debug_rwrsp(),.debug_cardstate(),.debug_spidone(),.debug_rvalid_session()
    );
    workstation_tf_file_wire_card card(.ssn(ssn),.sck(sck),.mosi(mosi),.miso(miso),
        .token_delay_bytes(2),.hold_init(hold_init),.fault_lba(fault_lba),.fault_kind(fault_kind),
        .suppress_token(1'b0),.command_error(1'b0),.suppress_r1(1'b0),
        .cmd17_count(commands),.payload_bytes(payload_bytes),.crc_bytes(crc_bytes),
        .post_crc_bytes(post_crc_bytes),.cs_releases(cs_releases),.high_clocks(high_clocks),.last_argument(last_argument));
    integer cycles=0,bytes_seen=0,events=0,eofs=0,cancels=0,reservations=0,reserved=0;
    integer active_track=0,pending_track=0,last_session_bytes=0,total_bytes=0;
    reg session_live=0;
    function automatic [7:0] oracle(input integer track,input integer offset);
        oracle=(track==0) ? (offset*13+8'h31) : (offset*7+8'ha0);
    endfunction
    always @(posedge clk) begin
        cycles=cycles+1;
        if(cycles>16000000) $fatal(1,"bounded test timeout state=%0d bytes=%0d err=%0d",filesystem_stat,bytes_seen,error_code);
        if(!rstn) begin session_live=0;reserved=0;bytes_seen=0;end
        else begin
            if(track_applied) begin
                last_session_bytes=bytes_seen;active_track=pending_track;bytes_seen=0;
                session_live=1;reserved=0;events=events+1;
            end
            if(data_sector_start) begin
                if(track_applied) $fatal(1,"data sector overlaps track application");
                if(!sector_allow || !session_live || stop || file_error || reserved!=0)
                    $fatal(1,"sector reservation contract allow=%0d reserved=%0d",sector_allow,reserved);
                reserved=512;reservations=reservations+1;
            end
            if(outen) begin
                if(!session_live || reserved<=0 || stop || file_error)
                    $fatal(1,"metadata/stale/unreserved file byte");
                if(outbyte!==oracle(active_track,bytes_seen))
                    $fatal(1,"file byte oracle track=%0d offset=%0d got=%h expected=%h",active_track,bytes_seen,outbyte,oracle(active_track,bytes_seen));
                bytes_seen=bytes_seen+1;total_bytes=total_bytes+1;reserved=reserved-1;
                if(bytes_seen>(active_track==0 ? SIZE0:SIZE1)) $fatal(1,"bytes beyond file size");
            end
            if(eof) begin
                if(MODE==1 || MODE==2 || MODE==4 || MODE==5 || MODE==6 || EXPECT_ERROR!=0)
                    $fatal(1,"error masqueraded as EOF");
                if(outen || bytes_seen!=(active_track==0 ? SIZE0:SIZE1))
                    $fatal(1,"EOF ordering/size bytes=%0d",bytes_seen);
                eofs=eofs+1;session_live=0;reserved=0;
            end
            if(cancelled) begin cancels=cancels+1;session_live=0;reserved=0;end
        end
    end
    task automatic clocks(input integer n);repeat(n) @(negedge clk);endtask
    task automatic mount;
        begin
            while(!scan_done && !file_error) @(negedge clk);
            if(file_error || track_count!=EXPECT_TRACKS) $fatal(1,"mount failed tracks=%0d err=%0d",track_count,error_code);
        end
    endtask
    task automatic request(input integer track);
        begin
            @(negedge clk);pending_track=track;track_index=track;track_start=1;
            @(negedge clk);track_start=0;
        end
    endtask
    task automatic await_eof(input integer before_eof);
        begin while(eofs==before_eof && !file_error) @(negedge clk);
            if(file_error) $fatal(1,"unexpected file error %0d",error_code);end
    endtask
    task automatic terminal_error;
        integer old_cmd,old_bytes;
        begin
            while(!file_error) @(negedge clk);
            if(error_code!=EXPECT_ERROR || eof || playing) $fatal(1,"terminal error mismatch got=%0d expected=%0d",error_code,EXPECT_ERROR);
            old_cmd=commands;old_bytes=total_bytes;clocks(1000);
            if(!file_error || error_code!=EXPECT_ERROR || commands!=old_cmd || total_bytes!=old_bytes || !ssn)
                $fatal(1,"failure not parked/fenced");
        end
    endtask
    integer i,j,old_event,old_eof,old_reserve,old_cmd,old_cancel,wire_before;
    reg [95:0] expected_name;
    initial begin
        fault_lba=INITIAL_FAULT_LBA;fault_kind=INITIAL_FAULT_KIND;
        clocks(10);rstn=1;
        if(MODE==1 || MODE==5) terminal_error();
        else begin
            mount();
            if(MODE==4) begin request(15);terminal_error();end
            else if(MODE==6) begin fault_lba=0;fault_kind=1;terminal_error();end
            else if(MODE==2) begin sector_allow=1;request(0);terminal_error();end
            else if(MODE==3) begin
                old_cmd=commands;old_reserve=reservations;old_eof=eofs;request(0);await_eof(old_eof);
                if(bytes_seen!=0 || commands!=old_cmd || reservations!=old_reserve) $fatal(1,"empty track issued data read");
            end else begin
                // Registered names, including the second partial FAT16 root sector.
                for(i=0;i<2;i=i+1) begin
                    expected_name=(i==0) ? "FIRST   .WAV" : "SECOND  .WAV";
                    for(j=0;j<12;j=j+1) begin
                        @(negedge clk);name_raddr=i*12+j;clocks(2);
                        if(name_rdata!==expected_name[95-j*8-:8]) $fatal(1,"playlist name mismatch track=%0d char=%0d got=%h",i,j,name_rdata);
                    end
                end
                name_raddr=255;clocks(2);if(name_rdata!==0) $fatal(1,"name address bounds");
                // Consecutive requests before acceptance retain the latest index.
                old_event=events;
                @(negedge clk);pending_track=0;track_index=0;track_start=1;
                @(negedge clk);pending_track=1;track_index=1;track_start=1;
                @(negedge clk);track_start=0;
                while(events==old_event) @(negedge clk);
                if(events!=old_event+1) $fatal(1,"duplicate track application");
                old_eof=eofs;sector_allow=1;await_eof(old_eof);sector_allow=0;
                // No data launch before allowance; allowance may fall immediately
                // after a full512 reservation without interrupting that sector.
                old_event=events;old_reserve=reservations;request(0);
                while(events==old_event) @(negedge clk);
                clocks(500);if(reservations!=old_reserve || bytes_seen!=0) $fatal(1,"sector_allow bypass");
                sector_allow=1;while(reservations==old_reserve) @(negedge clk);sector_allow=0;
                while(bytes_seen<512 && !file_error) @(negedge clk);
                clocks(2000);if(bytes_seen!=512 || reservations!=old_reserve+1) $fatal(1,"full sector reservation not retained");
                old_eof=eofs;sector_allow=1;await_eof(old_eof);
                old_eof=eofs;request(1);await_eof(old_eof);
                // Switch while bytes are arriving: finish the old sector, then
                // apply exactly one new session and never expose stale bytes.
                old_event=events;request(0);while(events==old_event) @(negedge clk);
                while(bytes_seen<100) @(negedge clk);
                old_event=events;old_eof=eofs;request(1);
                while(events==old_event && !file_error) @(negedge clk);
                if(last_session_bytes!=512) $fatal(1,"switch was not a drained sector boundary %0d",last_session_bytes);
                await_eof(old_eof);
                // Stop discards late data but drains the actual transaction+CRC.
                old_event=events;request(0);while(events==old_event) @(negedge clk);
                while(bytes_seen<100) @(negedge clk);
                old_cancel=cancels;old_eof=eofs;wire_before=payload_bytes;stop=1;
                track_start=1;track_index=1;pending_track=1;clocks(1);track_start=0;
                while(cancels==old_cancel && !file_error) @(negedge clk);
                clocks(1000);
                if(file_error || eofs!=old_eof || payload_bytes<=wire_before || cancels!=old_cancel+1 || !ssn)
                    $fatal(1,"stop/late-wire drain contract");
                // stop wins a simultaneous start and does not auto replay it.
                old_event=events;request(1);clocks(100);stop=0;clocks(1000);
                if(events!=old_event) $fatal(1,"stopped request replayed");
                old_eof=eofs;request(1);await_eof(old_eof);
                // Physical reset while real payload is still arriving fences
                // that transaction, re-initializes and requires explicit start.
                old_event=events;request(0);while(events==old_event) @(negedge clk);
                while(bytes_seen<100) @(negedge clk);
                rstn=0;clocks(10);if(outen || !ssn) $fatal(1,"reset did not fence wire/output");
                rstn=1;mount();clocks(1000);if(playing || outen) $fatal(1,"reset auto replay");
                old_eof=eofs;request(1);await_eof(old_eof);
            end
        end
        $display("PASS workstation_tf_file_reader_wire: mode=%0d commands=%0d file_bytes=%0d reservations=%0d eofs=%0d cancels=%0d error=%0d",MODE,commands,total_bytes,reservations,eofs,cancels,error_code);
        $finish;
    end
endmodule
`default_nettype wire
