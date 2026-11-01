`timescale 1ns/1ps
`default_nettype none
// One real direct/file/sector/session chain; cancel is the public native STOP.
module tb_workstation_tf_sd_crc_stop_wire #(
    parameter integer STOP_PHASE=0
);
    localparam integer BAD_CRC=(STOP_PHASE>=4),PHASE=STOP_PHASE%4;
    reg clk=0;always #10 clk=~clk;
    reg rst=0,request=0,stop=0;
    reg [3:0] track=0;
    reg [31:0] generation=1;
    reg [31:0] phase=0;
    wire [32:0] next_phase={1'b0,phase}+33'd48000;
    wire tick=next_phase>=33'd50000000;
    always @(posedge clk)phase<=tick?32'(next_phase-33'd50000000):32'(next_phase);
    wire ssn,sck,mosi,miso,ready,accepted,applied,cancelled,stop_completed,stop_failed;
    wire valid,last,active,prefill,eos,drained,empty,failed,file_error,scan,playing,busy,file_byte,sector_start,file_eof;
    wire [15:0] left,right;
    wire [3:0] failure,file_failure;
    wire [31:0] output_generation,byte_level,pcm_level;
    wire [4:0] tracks;
    workstation_tf_direct_native_v1 #(.SPI_CLK_DIV(2),.SPI_CLK_DIV_FAST(2),
        .VERIFY_DATA_CRC(1),.TOKEN_WAIT_CLOCKS(1000),.WATCHDOG_CLOCKS(500000)) dut(
        .clk_i(clk),.rst_ni(rst),.spi_ssn_o(ssn),.spi_sck_o(sck),.spi_mosi_o(mosi),.spi_miso_i(miso),
        .request_valid_i(request),.request_ready_o(ready),.track_index_i(track),.generation_i(generation),.expected_rate_i(20'd48000),
        .stop_i(stop),.pause_i(1'b0),.sample_request_i(tick),.request_accepted_o(accepted),.request_applied_o(applied),
        .request_failed_o(),.request_cancelled_o(),.request_failure_code_o(),.request_pending_o(),.cancelled_o(cancelled),
        .pcm_valid_o(valid),.pcm_ready_i(tick),.stop_completed_o(stop_completed),.stop_failed_o(stop_failed),
        .pcm_left_o(left),.pcm_right_o(right),.pcm_last_o(last),.generation_o(output_generation),.session_rate_o(),
        .active_o(active),.prefill_ready_o(prefill),.decoded_eos_o(eos),.local_tail_drained_o(drained),.empty_o(empty),
        .ingress_failed_o(failed),.ingress_failure_code_o(failure),.file_error_o(file_error),.file_error_code_o(file_failure),
        .scan_done_o(scan),.playing_o(playing),.sector_busy_o(busy),.track_count_o(tracks),
        .name_raddr_i(8'd0),.name_rdata_o(),.card_type_o(),.filesystem_type_o(),.card_stat_o(),.filesystem_stat_o(),
        .byte_level_o(byte_level),.pcm_level_o(pcm_level),.byte_high_water_o(),.pcm_high_water_o(),
        .file_byte_valid_o(file_byte),.data_sector_start_o(sector_start),.file_eof_o(file_eof));
    integer fault_kind=BAD_CRC?2:0;
    wire integer commands,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,high_clocks;
    wire integer transaction_payload_bytes,transaction_crc_bytes;
    wire transaction_live;
    wire [31:0] last_argument,last_lba;
    workstation_tf_sd_crc_wire_card card(
        .ssn(ssn),.sck(sck),.mosi(mosi),.miso(miso),.token_delay_bytes(2),.hold_init(1'b0),
        .fault_lba(32'd21),.fault_kind(fault_kind),.suppress_token(1'b0),.command_error(1'b0),.suppress_r1(1'b0),
        .cmd17_count(commands),.payload_bytes(payload_bytes),.crc_bytes(crc_bytes),.post_crc_bytes(post_crc_bytes),
        .cs_releases(cs_releases),.high_clocks(high_clocks),.last_argument(last_argument),.last_lba(last_lba),
        .transaction_payload_bytes(transaction_payload_bytes),.transaction_crc_bytes(transaction_crc_bytes),.transaction_live(transaction_live));
    reg [31:0] oracle[0:96];reg [2047:0] oracle_path;
    integer cycles=0,deadlines=0,cancels=0,completed=0,stop_errors=0,received=0,applies=0,eofs=0;
    integer commands_at_stop,release_before,high_before,payload_before,crc_before,deadlines_before,old_commands,old_applies;
    reg drain_check=0,drain_checked=0,recovery=0;
    always @(posedge clk)begin
        cycles=cycles+1;if(tick)deadlines=deadlines+1;
        if(cycles>10000000)$fatal(1,"bounded CRC STOP timeout phase=%0d error=%0b",STOP_PHASE,file_error);
        if(rst)begin
            if(cancelled)cancels=cancels+1;
            if(stop_completed)completed=completed+1;
            if(stop_failed)stop_errors=stop_errors+1;
            if(applied)applies=applies+1;
            if(file_eof)eofs=eofs+1;
            if(stop && (valid || accepted || file_byte || sector_start))$fatal(1,"CRC STOP did not fence output/admission immediately");
            if(drain_check && !drain_checked && !cancelled && !stop_completed && !stop_failed && !file_error &&
               (ready || valid || file_byte || sector_start))$fatal(1,"pending CRC STOP fence escaped before actual drain");
            if(drain_check && !drain_checked && (cancelled || stop_completed || stop_failed || file_error))begin
                if(transaction_payload_bytes!=512 || transaction_crc_bytes!=2 || !ssn ||
                   high_clocks<high_before+8 || cs_releases!=release_before+1 ||
                   payload_bytes!=payload_before+512 || crc_bytes!=crc_before+2 ||
                   commands!=commands_at_stop || post_crc_bytes!=0)
                    $fatal(1,"CRC STOP terminal preceded exact 512+2/CS-high drain or launched extra CMD17");
                drain_checked=1;
            end
            if(valid && tick)begin
                if(!recovery || received>=97 || output_generation!=2 || {right,left}!==oracle[received] || last!==(received==96))
                    $fatal(1,"CRC STOP stale/recovery PCM oracle mismatch");
                received=received+1;
            end
            if(byte_level>4096 || pcm_level>4096)$fatal(1,"CRC STOP capacity overflow");
        end
    end
    task clocks(input integer count);repeat(count)@(negedge clk);endtask
    task mount;begin wait(scan || file_error);clocks(2);if(!scan || file_error || tracks!=2)$fatal(1,"CRC STOP mount failed");end endtask
    task request_track(input [3:0] selected,input [31:0] identity);
        begin wait(ready);@(negedge clk);track=selected;generation=identity;request=1;clocks(1);request=0;end
    endtask
    initial begin
        if(!$value$plusargs("ORACLE1=%s",oracle_path))$fatal(1,"missing recovery PCM oracle");
        $readmemh(oracle_path,oracle);clocks(10);rst=1;mount();request_track(0,1);
        wait(last_lba==21 && transaction_live);
        if(PHASE==0)wait(transaction_payload_bytes==511);
        else if(PHASE==1)wait(transaction_payload_bytes==512 && transaction_crc_bytes==0);
        else if(PHASE==2)wait(transaction_crc_bytes==1);
        else wait(transaction_crc_bytes==2 && !ssn);
        @(negedge clk);
        if(ssn || last_lba!=21)$fatal(1,"CRC STOP selected wrong physical phase");
        commands_at_stop=commands;release_before=cs_releases;high_before=high_clocks;
        payload_before=payload_bytes-transaction_payload_bytes;crc_before=crc_bytes-transaction_crc_bytes;
        deadlines_before=deadlines;drain_check=1;stop=1;clocks(1);stop=0;
        wait(stop_completed || stop_failed || file_error);clocks(4);
        if(!drain_checked || busy || !ssn || active || valid || eofs!=0)
            $fatal(1,"CRC STOP missing real drain or false EOF");
        if(BAD_CRC)begin
            if(!file_error || file_failure!=1 || stop_errors!=1 || completed!=0 || cancels!=0)
                $fatal(1,"CRCbad+STOP must report one failed stop, never success ACK");
        end else if(file_error || stop_errors!=0 || completed!=1 || cancels!=1 || !ready)
            $fatal(1,"CRCgood+STOP must acknowledge exactly once after drain");
        old_commands=commands;old_applies=applies;fault_kind=0;clocks(2000);
        if(deadlines<=deadlines_before)$fatal(1,"CRC STOP halted independent sampling deadlines");
        if(commands!=old_commands || applies!=old_applies || valid || active)
            $fatal(1,"CRC STOP/card return automatically replayed a session");
        drain_check=0;
        if(BAD_CRC)begin
            if(!file_error || ready)$fatal(1,"CRC failure did not remain parked before remount");
            rst=0;clocks(10);rst=1;mount();clocks(2000);
            if(active || valid)$fatal(1,"CRC explicit remount automatically played");
        end
        recovery=1;request_track(1,2);wait(drained || failed || file_error);clocks(3);
        if(file_error || failed || !eos || !drained || received!=97)$fatal(1,"CRC explicit recovery failed");
        $display("PASS tf_sd_crc_stop_wire phase=%0d bad_crc=%0d cancels=%0d completed=%0d stop_failed=%0d recovery_PCM=%0d deadlines=%0d commands=%0d",STOP_PHASE,BAD_CRC,cancels,completed,stop_errors,received,deadlines,commands);
        $finish;
    end
endmodule
`default_nettype wire
