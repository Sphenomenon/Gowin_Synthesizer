`timescale 1ns/1ps
`default_nettype none
// The DUT is driven only through its normal request/STOP/audio/SPI ports.
// Hierarchical observations below instrument metadata ownership and cache
// publication; no DUT state is forced, deposited or used as a card substitute.
module tb_workstation_tf_fat_cache_wire #(
    parameter integer MODE=0,RATE=48000,FRAMES0=11000,EXPECTED_FAT_MISSES=2,
    parameter integer EXPECT_CACHE_HITS=1
);
    reg clk=0;always #10 clk=~clk;
    reg rst=0,request=0,stop=0;
    reg [3:0] track=0;
    reg [31:0] generation=1;
    reg [31:0] phase=0;
    wire [32:0] next_phase={1'b0,phase}+33'(RATE);
    wire tick=next_phase>=33'd50000000;
    always @(posedge clk)phase<=tick?32'(next_phase-33'd50000000):32'(next_phase);
    wire ssn,sck,mosi,miso,ready,accepted,applied,cancelled,stop_completed,stop_failed;
    wire valid,last,active,prefill,eos,drained,empty,failed,file_error,scan,playing,busy,file_byte,sector_start,file_eof;
    wire [15:0] left,right;
    wire [3:0] failure,file_failure;
    wire [31:0] output_generation,byte_level,pcm_level,byte_high,pcm_high;
    wire [4:0] tracks;
    workstation_tf_direct_native_v1 #(.SPI_CLK_DIV(2),.SPI_CLK_DIV_FAST(12),
        .VERIFY_DATA_CRC(1),.FAT_SECTOR_CACHE(1),.TOKEN_WAIT_CLOCKS(1000),
        .WATCHDOG_CLOCKS(500000),.BYTE_DEPTH(4096),.PCM_DEPTH(4096),.PREFILL_FRAMES(3072)) dut(
        .clk_i(clk),.rst_ni(rst),.spi_ssn_o(ssn),.spi_sck_o(sck),.spi_mosi_o(mosi),.spi_miso_i(miso),
        .request_valid_i(request),.request_ready_o(ready),.track_index_i(track),.generation_i(generation),.expected_rate_i(20'(RATE)),
        .stop_i(stop),.pause_i(1'b0),.sample_request_i(tick),.request_accepted_o(accepted),.request_applied_o(applied),
        .request_failed_o(),.request_cancelled_o(),.request_failure_code_o(),.request_pending_o(),.cancelled_o(cancelled),
        .pcm_valid_o(valid),.pcm_ready_i(tick),.stop_completed_o(stop_completed),.stop_failed_o(stop_failed),
        .pcm_left_o(left),.pcm_right_o(right),.pcm_last_o(last),.generation_o(output_generation),.session_rate_o(),
        .active_o(active),.prefill_ready_o(prefill),.decoded_eos_o(eos),.local_tail_drained_o(drained),.empty_o(empty),
        .ingress_failed_o(failed),.ingress_failure_code_o(failure),.file_error_o(file_error),.file_error_code_o(file_failure),
        .scan_done_o(scan),.playing_o(playing),.sector_busy_o(busy),.track_count_o(tracks),
        .name_raddr_i(8'd0),.name_rdata_o(),.card_type_o(),.filesystem_type_o(),.card_stat_o(),.filesystem_stat_o(),
        .byte_level_o(byte_level),.pcm_level_o(pcm_level),.byte_high_water_o(byte_high),.pcm_high_water_o(pcm_high),
        .file_byte_valid_o(file_byte),.data_sector_start_o(sector_start),.file_eof_o(file_eof));
    integer fault_kind=MODE==1?2:0;
    wire integer commands,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,high_clocks;
    wire integer transaction_payload_bytes,transaction_crc_bytes;
    wire transaction_live;
    wire [31:0] last_argument,last_lba;
    workstation_tf_sd_crc_wire_card card(
        .ssn(ssn),.sck(sck),.mosi(mosi),.miso(miso),.token_delay_bytes(2),.hold_init(1'b0),
        .fault_lba(32'd1),.fault_kind(fault_kind),.suppress_token(1'b0),.command_error(1'b0),.suppress_r1(1'b0),
        .cmd17_count(commands),.payload_bytes(payload_bytes),.crc_bytes(crc_bytes),.post_crc_bytes(post_crc_bytes),
        .cs_releases(cs_releases),.high_clocks(high_clocks),.last_argument(last_argument),.last_lba(last_lba),
        .transaction_payload_bytes(transaction_payload_bytes),.transaction_crc_bytes(transaction_crc_bytes),.transaction_live(transaction_live));
    reg [31:0] oracle0[0:20000],oracle1[0:96];reg [2047:0] path0,path1;
    integer cycles=0,deadlines=0,received=0,total_frames=0,applies=0,eofs=0,cancels=0,completions=0,stop_errors=0;
    integer active_track=0,active_generation=0,window=0,apply_cycle=0,prefill_cycle=0;
    integer data_reads=0,fat_reads=0,hits=0,first_data_cycle=0,last_data_cycle=0;
    integer max_data_gap=0,first_file_cycle=0,last_file_cycle=0,file_bytes=0,max_file_gap=0;
    integer prev_file_cycle=0,prev_spi_payload=0,payload_delta_min=100000000,payload_delta_max=0;
    integer fat_lba_changes=0,previous_fat_lba=0,byte_stall=0,byte_peak=0,pcm_peak=0,min_pcm=100000000;
    integer commands_stop=0,high_stop=0,releases_stop=0,payload_stop=0,crc_stop=0;
    integer fat_at_recovery=0,commands_park=0,applies_park=0,deadlines_park=0;
    integer first_data_reads=0,first_fat_reads=0,first_hits=0;
    integer first_file_bytes=0,first_data_start=0,first_data_end=0;
    reg first_prefill=0,drain_check=0,drain_checked=0;
    always @(posedge clk)begin
        cycles=cycles+1;if(tick)deadlines=deadlines+1;
        if(cycles>30000000)$fatal(1,"FAT cache wire timeout mode=%0d received=%0d failure=%0d file=%0d",MODE,received,failure,file_failure);
        if(rst)begin
            if(applied)begin
                applies=applies+1;received=0;active_track=track;active_generation=generation;
                window=1;apply_cycle=cycles;first_prefill=0;
            end
            if(cancelled)cancels=cancels+1;
            if(stop_completed)completions=completions+1;
            if(stop_failed)stop_errors=stop_errors+1;
            if(file_eof)eofs=eofs+1;
            if(byte_high>byte_peak)byte_peak=byte_high;
            if(pcm_high>pcm_peak)pcm_peak=pcm_high;
            if(window && active_track==0)begin
                if(dut.file_owner.read_start && dut.file_owner.filesystem_stat==5)begin
                    prev_spi_payload=0;
                    if(dut.file_owner.search_fat)begin
                        fat_reads=fat_reads+1;
                        if(previous_fat_lba!=0 && previous_fat_lba!=dut.file_owner.read_sector_no)fat_lba_changes=fat_lba_changes+1;
                        previous_fat_lba=dut.file_owner.read_sector_no;
                        $display("METRIC_FAT cycle=%0d lba=%0d pcm=%0d",cycles,dut.file_owner.read_sector_no,pcm_level);
                    end else begin
                        data_reads=data_reads+1;
                        if(first_data_cycle==0)first_data_cycle=cycles;
                        if(last_data_cycle!=0 && cycles-last_data_cycle>max_data_gap)max_data_gap=cycles-last_data_cycle;
                        last_data_cycle=cycles;
                        $display("METRIC_DATA cycle=%0d lba=%0d pcm=%0d bytelevel=%0d",cycles,dut.file_owner.read_sector_no,pcm_level,byte_level);
                    end
                end
                if(dut.file_owner.cache_lookup_request)hits=hits+1;
                if(dut.file_owner.rvalid)begin
                    if(prev_spi_payload!=0)begin
                        if(cycles-prev_spi_payload<payload_delta_min)payload_delta_min=cycles-prev_spi_payload;
                        if(cycles-prev_spi_payload>payload_delta_max)payload_delta_max=cycles-prev_spi_payload;
                    end
                    prev_spi_payload=cycles;
                end
                if(file_byte)begin
                    file_bytes=file_bytes+1;
                    if(first_file_cycle==0)first_file_cycle=cycles;
                    if(prev_file_cycle!=0 && cycles-prev_file_cycle>max_file_gap)max_file_gap=cycles-prev_file_cycle;
                    prev_file_cycle=cycles;last_file_cycle=cycles;
                end
                if(dut.ingress.byte_held_valid && !dut.ingress.decoder_ready)byte_stall=byte_stall+1;
                if(prefill && !first_prefill)begin
                    first_prefill=1;prefill_cycle=cycles;
                    $display("METRIC_PREFILL cycle=%0d pcm=%0d filebytes=%0d",cycles,pcm_level,file_bytes);
                end
                if(prefill && valid && tick && pcm_level<min_pcm)min_pcm=pcm_level;
            end
            // A fill is not a cache line until all payload/CRC/CS-high clocks
            // have completed successfully on the actual single sector owner.
            if(dut.file_owner.inflight && dut.file_owner.search_fat &&
               !dut.file_owner.read_done && dut.file_owner.cache_hit)
                $fatal(1,"unverified FAT fill published early");
            if(stop && (valid || accepted || file_byte || sector_start || dut.file_owner.cache_hit || dut.file_owner.cache_lookup_valid))
                $fatal(1,"FAT cache STOP failed immediate fence");
            if(drain_check && !drain_checked && (cancelled || stop_completed || stop_failed || file_error))begin
                if(transaction_payload_bytes!=512 || transaction_crc_bytes!=2 || !ssn ||
                   high_clocks<high_stop+8 || cs_releases!=releases_stop+1 ||
                   payload_bytes!=payload_stop+512 || crc_bytes!=crc_stop+2 || commands!=commands_stop)
                    $fatal(1,"FAT cache STOP preceded exact physical drain");
                drain_checked=1;
            end
            if(valid && tick)begin
                if(output_generation!=active_generation)$fatal(1,"FAT cache stale generation");
                if(active_track==0)begin
                    if(MODE!=0 || received>=FRAMES0 || {right,left}!==oracle0[received] || last!==(received==FRAMES0-1))
                        $fatal(1,"FAT cache first-track PCM oracle mismatch index=%0d",received);
                end else if(received>=97 || {right,left}!==oracle1[received] || last!==(received==96))
                    $fatal(1,"FAT cache recovery PCM oracle mismatch index=%0d",received);
                received=received+1;total_frames=total_frames+1;
            end
            if(byte_level>4096 || pcm_level>4096)$fatal(1,"FAT cache capacity exceeded");
        end
    end
    task clocks(input integer n);repeat(n)@(negedge clk);endtask
    task mount;begin wait(scan || file_error);clocks(2);if(!scan || file_error || tracks!=2)$fatal(1,"FAT cache mount failed");end endtask
    task request_track(input [3:0] selected,input [31:0] identity);
        begin wait(ready);@(negedge clk);track=selected;generation=identity;request=1;clocks(1);request=0;end
    endtask
    task finish_track(input integer count);
        begin
            wait(drained || failed || file_error);clocks(3);
            if(failed || file_error || !eos || !drained || received!=count)
                $fatal(1,"FAT cache supply/oracle completion failed got=%0d expected=%0d failure=%0d file=%0d",received,count,failure,file_failure);
        end
    endtask
    task check_park;
        begin
            commands_park=commands;applies_park=applies;deadlines_park=deadlines;
            clocks(3000);
            if(commands!=commands_park || applies!=applies_park || active || valid || deadlines<=deadlines_park)
                $fatal(1,"FAT cache stop/error replayed session or stopped sample clock");
            if(dut.file_owner.cache_hit || dut.file_owner.g_fat_cache.cache.valid)
                $fatal(1,"FAT cache STOP/error retained or republished line");
        end
    endtask
    initial begin
        if(!$value$plusargs("ORACLE0=%s",path0) || !$value$plusargs("ORACLE1=%s",path1))$fatal(1,"missing FAT cache PCM oracles");
        $readmemh(path0,oracle0,0,FRAMES0-1);$readmemh(path1,oracle1);
        clocks(10);rst=1;mount();request_track(0,1);
        if(MODE==0)begin
            finish_track(FRAMES0);
            if(fat_reads!=EXPECTED_FAT_MISSES || (EXPECT_CACHE_HITS && hits==0))
                $fatal(1,"FAT cache expected miss/hit ownership differs fat=%0d expected=%0d hit=%0d",fat_reads,EXPECTED_FAT_MISSES,hits);
            if(FRAMES0>10000 && fat_lba_changes!=1)$fatal(1,"long FAT cache fixture did not cross exact LBA key");
            first_data_reads=data_reads;first_fat_reads=fat_reads;first_hits=hits;first_file_bytes=file_bytes;
            first_data_start=first_data_cycle;first_data_end=last_data_cycle;
        end else if(MODE==1)begin
            wait(file_error);clocks(4);
            if(!failed || file_failure!=1 || received!=0 || eofs!=0 || dut.file_owner.g_fat_cache.cache.valid)
                $fatal(1,"CRC-bad FAT fill escaped integrity failure or published line");
            window=0;check_park();fault_kind=0;rst=0;clocks(10);rst=1;mount();clocks(2000);
            if(active || valid)$fatal(1,"FAT cache explicit remount auto-played");
        end else begin
            if(MODE==2)begin
                wait(last_lba==1 && transaction_live && transaction_payload_bytes==511);
                @(negedge clk);commands_stop=commands;high_stop=high_clocks;releases_stop=cs_releases;
                payload_stop=payload_bytes-transaction_payload_bytes;crc_stop=crc_bytes-transaction_crc_bytes;
                drain_check=1;
            end else begin
                wait(dut.file_owner.cache_lookup_pending);@(negedge clk);
                if(!ssn || dut.file_owner.inflight)$fatal(1,"cache-hit STOP unexpectedly owned a real SPI request");
                commands_stop=commands;
            end
            stop=1;clocks(1);stop=0;wait(stop_completed || stop_failed || file_error);clocks(4);
            if(file_error || failed || stop_errors!=0 || completions!=1 || cancels!=1 || busy || !ssn || !ready ||
               commands!=commands_stop || eofs!=0 || (MODE==2 && !drain_checked))
                $fatal(1,"FAT cache STOP missing unique correct cancellation");
            drain_check=0;window=0;check_park();
        end
        // A new task must discard a prior line even when its FAT LBA is equal.
        // Count the physical metadata request for the explicit new generation.
        fat_at_recovery=commands;window=0;request_track(1,2);wait(applies>=2);clocks(2);finish_track(97);clocks(3000);
        if(commands<fat_at_recovery+2 || failed || file_error || valid || !eos)
            $fatal(1,"FAT cache new task skipped physical FAT fill or failed recovery");
        $display("PASS tf_fat_cache_wire mode=%0d rate=%0d first_PCM=%0d total_PCM=%0d first_data_reads=%0d first_fat_reads=%0d first_hits=%0d data_reads=%0d fat_reads=%0d hits=%0d FAT_LBA_changes=%0d filebytes=%0d first_data_cycle=%0d last_data_cycle=%0d first_file_cycle=%0d last_file_cycle=%0d max_data_gap=%0d max_file_gap=%0d SPI_byte_min=%0d SPI_byte_max=%0d byte_peak=%0d pcm_peak=%0d byte_stall=%0d min_PCM=%0d prefill_cycle=%0d deadlines=%0d commands=%0d cancels=%0d stop_completed=%0d stop_failed=%0d",MODE,RATE,MODE==0?FRAMES0:0,total_frames,first_data_reads,first_fat_reads,first_hits,data_reads,fat_reads,hits,fat_lba_changes,file_bytes,first_data_cycle,last_data_cycle,first_file_cycle,last_file_cycle,max_data_gap,max_file_gap,payload_delta_min,payload_delta_max,byte_peak,pcm_peak,byte_stall,min_pcm,prefill_cycle,deadlines,commands,cancels,completions,stop_errors);
        $finish;
    end
endmodule
`default_nettype wire
