`timescale 1ns/1ps
module tb_workstation_tf_direct_native_wire #(
    parameter integer MODE=0,RATE=48000,FRAMES0=3800,FRAMES1=97,
    parameter integer WATCHDOG=500000,PROBE=50000000,FAST_DIV=(MODE==13 ? 12:2)
);
    reg clk=0;always #10 clk=~clk;
    reg rst=0,req=0,stop=0,pause=0;
    reg [3:0] track=0;
    reg [31:0] generation=32'hffffffff;
    reg [19:0] rate=RATE;
    wire ready,accepted,applied,command_failed,command_cancelled,pending,cancelled,stop_completed,stop_failed;
    wire ssn,sck,mosi,miso,valid,last,active,prefill,eos,drained,empty,failed,file_error;
    wire [15:0] pcm_left,pcm_right;
    wire [3:0] failure,file_failure,request_failure;
    wire [31:0] output_generation,byte_level,pcm_level,byte_high,pcm_high;
    wire [19:0] output_rate;
    wire scan,playing,busy,file_byte,sector_start,file_eof;
    wire [4:0] tracks;
    integer cycles=0,deadlines=0,received=0,total_frames=0,accepts=0,applies=0,cancels=0,cmd_failures=0,cmd_cancels=0;
    integer byte_peak=0,pcm_peak=0;
    integer stop_completions=0,stop_failures=0;
    integer active_track=0,held_track=0,checks=0,sectors=0,file_bytes=0,eofs=0,desired_application=0;
    reg [31:0] held_generation=0,active_generation=0;
    reg [19:0] held_rate=0,active_rate=0;
    // Exact average rate against the independent, continuously running 50 MHz
    // clock. No pause, stop, owner reset or SPI wait may stop this schedule.
    localparam integer DEADLINE_GAP=(50000000+RATE-1)/RATE;
    reg [31:0] phase=0;
    wire [32:0] next_phase={1'b0,phase}+33'(RATE);
    wire tick=next_phase>=33'd50000000;
    always @(posedge clk)phase<=tick ? 32'(next_phase-33'd50000000):32'(next_phase);
    wire consume=tick;
    reg [31:0] oracle0[0:20000],oracle1[0:20000];
    reg [2047:0] path0,path1;
    reg remove_card=0;
    integer fault_kind=0;
    reg [31:0] fault_lba=32'hffffffff;
    wire integer commands,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,high_clocks;
    wire [31:0] last_argument;
    workstation_tf_direct_native_v1 #(.SPI_CLK_DIV(2),.SPI_CLK_DIV_FAST(FAST_DIV),
        .TOKEN_WAIT_CLOCKS(1000),.WATCHDOG_CLOCKS(WATCHDOG),.PROBE_INTERVAL_CYCLES(PROBE)) dut(
        .clk_i(clk),.rst_ni(rst),.spi_ssn_o(ssn),.spi_sck_o(sck),.spi_mosi_o(mosi),.spi_miso_i(miso),
        .request_valid_i(req),.request_ready_o(ready),.track_index_i(track),.generation_i(generation),.expected_rate_i(rate),
        .stop_i(stop),.pause_i(pause),.sample_request_i(tick),.request_accepted_o(accepted),.request_applied_o(applied),
        .request_failed_o(command_failed),.request_cancelled_o(command_cancelled),.request_failure_code_o(request_failure),
        .request_pending_o(pending),.cancelled_o(cancelled),.pcm_valid_o(valid),.pcm_ready_i(consume),
        .stop_completed_o(stop_completed),.stop_failed_o(stop_failed),
        .pcm_left_o(pcm_left),.pcm_right_o(pcm_right),.pcm_last_o(last),.generation_o(output_generation),.session_rate_o(output_rate),
        .active_o(active),.prefill_ready_o(prefill),.decoded_eos_o(eos),.local_tail_drained_o(drained),.empty_o(empty),
        .ingress_failed_o(failed),.ingress_failure_code_o(failure),.file_error_o(file_error),.file_error_code_o(file_failure),
        .scan_done_o(scan),.playing_o(playing),.sector_busy_o(busy),.track_count_o(tracks),
        .name_raddr_i(8'd0),.name_rdata_o(),.card_type_o(),.filesystem_type_o(),.card_stat_o(),.filesystem_stat_o(),
        .byte_level_o(byte_level),.pcm_level_o(pcm_level),.byte_high_water_o(byte_high),.pcm_high_water_o(pcm_high),
        .file_byte_valid_o(file_byte),.data_sector_start_o(sector_start),.file_eof_o(file_eof));
    workstation_tf_file_wire_card card(.ssn(ssn),.sck(sck),.mosi(mosi),.miso(miso),.token_delay_bytes(2),
        .hold_init(1'b0),.fault_lba(fault_lba),.fault_kind(fault_kind),.suppress_token(1'b0),.command_error(1'b0),.suppress_r1(remove_card),
        .cmd17_count(commands),.payload_bytes(payload_bytes),.crc_bytes(crc_bytes),.post_crc_bytes(post_crc_bytes),
        .cs_releases(cs_releases),.high_clocks(high_clocks),.last_argument(last_argument));
    reg stalled=0;
    reg [32:0] held_pair;
    always @(posedge clk)begin
        cycles<=cycles+1;
        if(cycles>24000000)$fatal(1,"wire integration timeout mode=%0d received=%0d failure=%0d file=%0d pending=%0b",MODE,received,failure,file_failure,pending);
        if(rst)begin
            if(byte_high>byte_peak)byte_peak=byte_high;
            if(pcm_high>pcm_peak)pcm_peak=pcm_high;
            if(tick)deadlines=deadlines+1;
            if(accepted)begin held_track=track;held_generation=generation;held_rate=rate;accepts=accepts+1;end
            if(applied)begin
                if(stop || !pending)$fatal(1,"applied outside live accepted slot");
                active_track=held_track;active_generation=held_generation;active_rate=held_rate;received=0;applies=applies+1;
            end
            if(command_failed)begin
                if(applied || command_cancelled)$fatal(1,"multiple command terminal results");cmd_failures=cmd_failures+1;
            end
            if(command_cancelled)begin if(applied || command_failed)$fatal(1,"cancel terminal priority");cmd_cancels=cmd_cancels+1;end
            if(cancelled)cancels=cancels+1;
            if(stop_completed && stop_failed)$fatal(1,"multiple stop terminal results");
            if(stop_completed)stop_completions=stop_completions+1;
            if(stop_failed)stop_failures=stop_failures+1;
            if(file_eof)begin if(stop || file_byte)$fatal(1,"cancel/EOF or byte/EOF overlap");eofs=eofs+1;end
            if(sector_start)sectors=sectors+1;
            if(file_byte)file_bytes=file_bytes+1;
            if(stalled && !stop && !pause && !failed && !file_error && !applied)
                if(!valid || {last,pcm_right,pcm_left}!==held_pair)$fatal(1,"held PCM changed under wire backpressure");
            stalled=valid && !consume;held_pair={last,pcm_right,pcm_left};
            if(valid && consume)begin
                if(output_generation!==active_generation || output_rate!==active_rate)$fatal(1,"snapshot/old-generation leak");
                if(active_track==0)begin
                    if(received>=FRAMES0 || {pcm_right,pcm_left}!==oracle0[received])$fatal(1,"wire PCM oracle track0 index=%0d",received);
                    if(last !== (received==FRAMES0-1))$fatal(1,"wire last track0");
                end else begin
                    if(received>=FRAMES1 || {pcm_right,pcm_left}!==oracle1[received])$fatal(1,"wire PCM oracle track1 index=%0d got=%08x expected=%08x",received,{pcm_right,pcm_left},oracle1[received]);
                    if(last !== (received==FRAMES1-1))$fatal(1,"wire last track1");
                end
                received=received+1;total_frames=total_frames+1;
            end
            if(stop && (valid || accepted || file_byte || sector_start))$fatal(1,"stop did not revoke local paths");
            if(byte_level>4096 || pcm_level>4096)$fatal(1,"wire capacity overflow");
        end else begin stalled=0;received=0;end
    end
    task clocks(input integer n);repeat(n)@(negedge clk);endtask
    task check(input reg ok,input string why);begin checks=checks+1;if(!ok)$fatal(1,"%s",why);end endtask
    task mount;begin wait(scan || file_error);clocks(1);check(scan && !file_error && tracks==2,"wire mount/playlist failed");end endtask
    task request_track(input integer index,input [31:0] identity,input [19:0] snapshot);
        begin
            desired_application=applies+1;@(negedge clk);while(!ready)@(negedge clk);
            track=4'(index);generation=identity;rate=snapshot;req=1;clocks(1);req=0;
        end
    endtask
    task finish_track(input integer index);
        begin
            wait(applies>=desired_application || file_error);clocks(2);
            wait(drained || failed || file_error);clocks(2);
            check(!failed && !file_error && eos && drained && received==(index==0 ? FRAMES0:FRAMES1),"wire EOS/oracle completion failed");
            clocks(DEADLINE_GAP*3);check(!failed && !valid,"post-last wire deadline reported underrun");
        end
    endtask
    task restart_owner;begin rst=0;clocks(10);remove_card=0;fault_kind=0;fault_lba=32'hffffffff;rst=1;mount();end endtask
    integer before_apply,before_cancel,before_cmd,before_recv,before_ticks,before_eofs,before_accept,before_stop;
    reg [32:0] pause_head;
    initial begin
        if(!$value$plusargs("ORACLE0=%s",path0) || !$value$plusargs("ORACLE1=%s",path1))$fatal(1,"missing PCM oracles");
        if(FRAMES0>0)$readmemh(path0,oracle0,0,FRAMES0-1);if(FRAMES1>0)$readmemh(path1,oracle1,0,FRAMES1-1);
        clocks(10);rst=1;mount();
        if(MODE==6 || MODE==11)begin
            before_apply=applies;request_track(15,32'd17,20'(RATE));wait(file_error);
            if(MODE==11)begin @(negedge clk);stop=1;clocks(3);check(cmd_failures==0 && cmd_cancels==1 && !pending && stop_failures==1 && stop_completions==0,"stop/file-error terminal priority");stop=0;end
            else clocks(3);
            if(MODE==6)check(cmd_failures==1 && request_failure==8 && !pending && file_error && applies==before_apply,"invalid track slot lacked failure terminal");
            restart_owner();request_track(1,32'd18,20'(RATE));finish_track(1);
        end else if(MODE==8 || MODE==9)begin
            before_apply=applies;before_cancel=cancels;before_eofs=eofs;
            request_track(0,32'hffffffff,20'(RATE));wait(applied);@(negedge clk);stop=1;
            wait(cancelled);clocks(3);check(applies==before_apply && !active && !valid && cmd_cancels==1 && eofs==before_eofs && stop_completions==1,"stop/apply/EOF priority failed");
            stop=0;clocks(100);request_track(1,0,20'(RATE));finish_track(1);
        end else begin
            request_track(0,32'hffffffff,20'(RATE));
            // Caller input changes after acceptance do not replace the held
            // command snapshot while native SPI/FAT is still applying it.
            generation=32'h12345678;rate=20'd12345;track=1;
            if(MODE==5 || MODE==7 || MODE==14 || MODE==15 || MODE==16)begin
                wait(failed);
                if(MODE==16)begin before_cancel=cancels;before_stop=stop_completions;@(negedge clk);stop=1;end
                clocks(2);check(failure==(MODE==7 ? 4:5),"rate/malformed local failure code");
                if(MODE!=7)check(!ready,"failed source admitted before real cancellation drain");
                wait(cancelled);
                if(MODE==15)begin before_stop=stop_completions;@(negedge clk);stop=1;clocks(1);stop=0;end
                clocks(3);
                if(MODE==15)check(!active && !valid && !busy && ssn && ready && stop_completions==before_stop+1,"stop/ACK collision stuck request readiness");
                else if(MODE==16)check(!active && !valid && !busy && ssn && !ready,"failure/held-stop failed to drain/fence");
                else check(!active && !valid && !busy && ssn && ready,"local failure did not stop/drain native owner");
                if(MODE==14)begin
                    before_stop=stop_completions;before_cancel=cancels;
                    @(negedge clk);stop=1;clocks(1);stop=0;clocks(100);
                    check(ready && !busy && !valid && stop_completions==before_stop+1 && cancels==before_cancel,"post-failure-drain stop pulse stuck request readiness");
                end
                if(MODE==16)begin
                    stop=0;
                    clocks(100);check(ready && stop_completions==before_stop+1 && cancels==before_cancel+1 && stop_failures==0,"failure/stop overlap did not retain one drain/stop terminal");
                end
                request_track(1,0,20'(RATE));finish_track(1);
            end else begin
                wait(received>=5 || failed || file_error);check(!failed && !file_error,"playback failed before wire PCM");
                if(MODE==1)begin
                    @(negedge clk);pause=1;before_recv=received;before_ticks=deadlines;pause_head={last,pcm_right,pcm_left};
                    clocks(2000000);check(received==before_recv && !failed && deadlines>before_ticks,"wire pause lost next frame or stopped schedule");
                    check({last,pcm_right,pcm_left}==pause_head && pcm_high==4096 && byte_high>3000,"wire pause capacity/held head not exercised");pause=0;
                end
                if(MODE==2)begin
                    before_apply=applies;request_track(1,0,20'(RATE));check(active && output_generation==32'hffffffff,"request revoked old session before actual apply");wait(applies>before_apply);finish_track(1);
                    before_apply=applies;before_cancel=cancels;request_track(0,1,20'(RATE));stop=1;wait(cancelled);clocks(3);
                    check(applies==before_apply && cmd_cancels==1 && !pending,"pending switch was not cancelled exactly once");
                    stop=0;clocks(1000);check(applies==before_apply && !active,"cancelled pending request replayed");
                    request_track(1,2,20'(RATE));finish_track(1);
                end else if(MODE==3 || MODE==12)begin
                    before_cancel=cancels;before_eofs=eofs;before_ticks=deadlines;before_stop=stop_completions;@(negedge clk);stop=1;
                    if(MODE==12)begin clocks(1);stop=0;while(cancels==before_cancel)begin check(!ready,"stop pulse admitted before CRC drain ACK");clocks(1);end end
                    else wait(cancelled);clocks(3);
                    check(!busy && ssn && !active && !valid && eofs==before_eofs && stop_completions==before_stop+1,"stop did not drain actual payload/CRC");
                    stop=1;req=1;track=1;clocks(1000);req=0;check(!ready && deadlines>before_ticks,"held stop admitted command or stopped clock");
                    stop=0;clocks(1000);before_accept=accepts;clocks(1000);check(accepts==before_accept && !active,"release auto replayed stopped track");
                    request_track(1,0,20'(RATE));finish_track(1);
                end else if(MODE==13)begin
                    before_ticks=deadlines;wait(failed || file_error);check(failed && failure==6 && !file_error,"default FAST12 did not report real supply underrun");
                    wait(cancelled);clocks(3);check(!busy && ssn && !active && deadlines>before_ticks,"default FAST12 failure did not drain with continuous schedule");
                    request_track(1,0,20'(RATE));finish_track(1);
                end else if(MODE==4 || MODE==10)begin
                    before_ticks=deadlines;before_cmd=commands;
                    if(MODE==10)begin pause=1;fault_lba=0;fault_kind=1;end else remove_card=1;
                    wait(file_error);clocks(10);check(file_failure==1 && failed && !valid && !ready && !pending,"removal not terminal/fenced");
                    before_cmd=commands;remove_card=0;fault_kind=0;clocks(2000);check(file_error && commands==before_cmd && deadlines>before_ticks,"card return auto-recovered or stopped scheduling");
                    pause=0;restart_owner();request_track(1,0,20'(RATE));finish_track(1);
                end else begin finish_track(0);request_track(1,0,20'(RATE));finish_track(1);end
            end
        end
        check(sectors>0 && commands>sectors && crc_bytes>=2 && payload_bytes>=file_bytes,"real metadata/data SPI path absent");
        $display("PASS direct_native_wire mode=%0d rate=%0d PCM=%0d checks=%0d commands=%0d sectors=%0d file_bytes=%0d accepts=%0d applies=%0d cancels=%0d command_failures=%0d deadlines=%0d byte_high=%0d pcm_high=%0d byte_peak=%0d pcm_peak=%0d stop_completions=%0d stop_failures=%0d",MODE,RATE,total_frames,checks,commands,sectors,file_bytes,accepts,applies,cancels,cmd_failures,deadlines,byte_high,pcm_high,byte_peak,pcm_peak,stop_completions,stop_failures);
        $finish;
    end
endmodule
