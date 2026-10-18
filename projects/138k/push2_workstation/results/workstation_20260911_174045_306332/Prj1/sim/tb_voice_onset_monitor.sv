`timescale 1ns/1ps
module tb_voice_onset_monitor;
    reg clk=0; always #10 clk=~clk;
    reg rst_n=0, advance_time=1;
    reg [31:0] time_cycles=0;
    always @(posedge clk) begin
        if(!rst_n) time_cycles<=0;
        else if(advance_time) time_cycles<=time_cycles+1'b1;
    end
    reg command_commit=0, sample_event=0, dac_done=0, dac_muted=0, query_request=0;
    reg [31:0] command_header=0, command_active_voices=0, nonzero_voices=0, dac_nonzero_voices=0;
    reg [23:0] command_revision=0, sample_revision=0, dac_revision=0;
    reg [4:0] query_voice=0;
    wire query_done;
    wire [255:0] query_data;
    voice_onset_monitor dut(.*);
    integer replies=0, max_query_wait=0, sequence_number=0, i, n, offset;
    reg [31:0] event_time, query_at, start31, start0, sample_at, dac_at, cancel_at, load_start;
    reg [255:0] saved_record;
    reg [7:0] flags;

    task command(input [7:0] op,input [4:0] voice,input [23:0] revision,input was_active);
        begin
            @(negedge clk); command_commit=1;
            command_header={sequence_number[7:0],op,3'd0,voice,8'd0};
            command_revision=revision; command_active_voices=was_active ? (32'd1<<voice) : 0;
            event_time=time_cycles; sequence_number=sequence_number+1;
            @(negedge clk); command_commit=0;
        end
    endtask
    task sample(input [23:0] revision,input [31:0] mask);
        begin
            @(negedge clk); sample_event=1; sample_revision=revision; nonzero_voices=mask; event_time=time_cycles;
            @(negedge clk); sample_event=0;
        end
    endtask
    task dac(input [23:0] revision,input [31:0] mask,input muted);
        begin
            @(negedge clk); dac_done=1; dac_revision=revision; dac_nonzero_voices=mask; dac_muted=muted; event_time=time_cycles;
            @(negedge clk); dac_done=0;
        end
    endtask
    task finish_query;
        integer waited;
        begin
            waited=0;
            while(!query_done) begin
                @(negedge clk); waited=waited+1;
                if(waited>5000) $fatal(1,"query did not complete despite one request in flight");
            end
            if(waited>max_query_wait) max_query_wait=waited;
            replies=replies+1; flags=query_data[31:24];
            if(query_data[7:0] !== 1 || query_data[15:8] !== {3'd0,query_voice} || query_data[95:64] !== 50000000)
                $fatal(1,"query schema/voice/clock mismatch");
            @(negedge clk);
            if(query_done) $fatal(1,"query_done is not a pulse");
        end
    endtask
    task read_voice(input [4:0] voice);
        begin
            @(negedge clk); query_voice=voice; query_request=1; query_at=time_cycles;
            @(negedge clk); query_request=0;
            finish_query;
        end
    endtask
    task check_flags(input [7:0] expected,input [31:0] note_id);
        begin
            if(flags !== expected || query_data[63:32] !== note_id)
                $fatal(1,"voice %0d flags/id got %h/%0d expected %h/%0d",query_voice,flags,query_data[63:32],expected,note_id);
        end
    endtask
    task reset_monitor;
        begin
            @(negedge clk); rst_n=0; advance_time=1;
            command_commit=0; sample_event=0; dac_done=0; query_request=0;
            repeat(3) @(negedge clk); rst_n=1;
        end
    endtask

    initial begin
        reset_monitor;
        // Request during word-RAM initialization must be retained.
        read_voice(7); check_flags(0,0);
        if(query_data[255:96] !== 0) $fatal(1,"initial slot has stale durations/revision");
        command(1,31,24'hfffffe,0); start31=event_time;
        sample(24'hfffffd,32'h80000000); // old rendered audio after the trigger
        dac(24'hfffffd,32'h80000000,0);
        read_voice(31); check_flags(1,1);
        if(query_data[127:96] != 0 || query_data[159:128] != 0 || query_data[191:160] !== query_at-start31)
            $fatal(1,"old revisions qualified or pending age uses scanner completion time");
        command(4,31,24'hffffff,0); // parameter commands never replace onset records
        sample(24'h000000,32'h80000000); sample_at=event_time;
        dac(24'h000001,32'h80000000,1); dac_at=event_time;
        read_voice(31); check_flags(8'h47,1);
        if(query_data[127:96] !== sample_at-start31 || query_data[159:128] !== dac_at-start31 ||
           query_data[191:160] !== dac_at-start31 || query_data[223:192] !== 32'h00fffffe)
            $fatal(1,"revision-wrap result did not preserve event timestamps");
        saved_record=query_data;
        command(2,31,2,1); command(10,0,3,0); command(5,31,4,1);
        sample(5,32'hffffffff); dac(5,32'hffffffff,0);
        read_voice(31);
        if(query_data !== saved_record) $fatal(1,"completed record was overwritten by release/panic/parameters");

        command(1,31,6,1); start31=event_time;
        dac(5,32'h80000000,0); sample(5,32'h80000000);
        read_voice(31); check_flags(9,2);
        sample(7,32'h80000000); sample_at=event_time;
        command(2,31,8,1); // sample already exists: keep its DAC completion in flight
        dac(8,32'h80000000,0); dac_at=event_time;
        read_voice(31); check_flags(8'h0f,2);
        if(query_data[127:96] !== sample_at-start31 || query_data[159:128] !== dac_at-start31 || query_data[255:224] != 0)
            $fatal(1,"active reuse/NOTE_OFF cancelled an already-produced contribution");
        saved_record=query_data;
        command(1,0,9,0); start0=event_time;
        sample(10,32'h80000000); // other voices sounding must not qualify slot zero
        read_voice(0); check_flags(1,1);
        command(2,0,11,1); cancel_at=event_time;
        dac(12,32'h00000001,0); sample(12,32'h00000001);
        read_voice(0); check_flags(8'h11,1);
        if(query_data[255:224] !== cancel_at-start0 || query_data[191:160] !== cancel_at-start0)
            $fatal(1,"cancel endpoint did not freeze at NOTE_OFF");
        read_voice(31);
        if(query_data !== saved_record) $fatal(1,"another voice's onset/cancel changed slot31");

        // A simultaneous sample and NOTE_OFF qualifies first, independent
        // of which queue the scanner happened to be servicing.
        command(1,5,20,0); start0=event_time;
        @(negedge clk);
        command_commit=1; command_header={8'h70,8'h02,8'd5,8'd0}; command_revision=21;
        sample_event=1; sample_revision=20; nonzero_voices=32'h20; sample_at=time_cycles;
        @(negedge clk); command_commit=0; sample_event=0;
        read_voice(5); check_flags(3,1);
        dac(22,32'h20,1); dac_at=event_time;
        read_voice(5); check_flags(8'h47,1);
        if(query_data[127:96] !== sample_at-start0 || query_data[159:128] !== dac_at-start0)
            $fatal(1,"same-edge sample/cancel priority lost a timestamp");
        command(1,6,23,0); start0=event_time;
        command(10,0,24,0); cancel_at=event_time;
        read_voice(6); check_flags(8'h11,1);
        if(query_data[255:224] !== cancel_at-start0) $fatal(1,"PANIC failed to cancel untouched pending slot");
        read_voice(5); check_flags(8'h47,1);

        // Query is a barrier: future events must not leak into its fields,
        // and the published 256-bit word must remain stable afterward.
        command(1,8,30,0); start0=event_time;
        @(negedge clk); query_request=1; query_voice=8; query_at=time_cycles;
        @(negedge clk); query_request=0; sample_event=1; sample_revision=30; nonzero_voices=32'h100;
        sample_at=time_cycles;
        @(negedge clk); sample_event=0;
        finish_query; check_flags(1,1); saved_record=query_data;
        if(query_data[191:160] !== query_at-start0) $fatal(1,"query age is not its captured request timestamp");
        repeat(350) @(negedge clk);
        if(query_data !== saved_record) $fatal(1,"published query data changed between query_done pulses");
        read_voice(8); check_flags(3,1);
        if(query_data[127:96] !== sample_at-start0) $fatal(1,"post-query event was lost");

        // Modular 32-bit time subtraction across natural wrap.
        @(negedge clk); time_cycles=32'hfffffff0;
        command(1,9,31,0); start0=event_time;
        repeat(30) @(negedge clk);
        sample(32,32'h200); sample_at=event_time;
        dac(33,32'h200,0); dac_at=event_time;
        read_voice(9); check_flags(7,1);
        if(query_data[127:96] !== sample_at-start0 || query_data[159:128] !== dac_at-start0)
            $fatal(1,"32-bit timestamp wrap produced an invalid duration");
        command(1,10,34,0); start0=event_time;
        read_voice(10); check_flags(1,1);
        @(negedge clk); time_cycles=start0+32'h80000010;
        read_voice(10); check_flags(8'h21,1);
        if(query_data[191:160] !== 32'h80000000) $fatal(1,"expiry did not freeze at half-range boundary");
        saved_record=query_data;
        sample(35,32'h400); dac(35,32'h400,0); command(2,10,36,1);
        read_voice(10);
        if(query_data !== saved_record) $fatal(1,"expired result accepted a late event");

        // Zero-duration endpoints use flags, not duration==0 sentinels.
        reset_monitor; read_voice(0);
        @(negedge clk); advance_time=0;
        command(1,4,1,0); read_voice(4);
        sample(1,32'h10); read_voice(4); check_flags(3,1);
        dac(1,32'h10,0); read_voice(4); check_flags(7,1);
        if(query_data[191:96] !== 0) $fatal(1,"zero endpoint was not represented faithfully");
        saved_record=query_data;
        @(negedge clk); advance_time=1;
        sample(2,32'h10); dac(2,32'h10,1); read_voice(4);
        if(query_data !== saved_record) $fatal(1,"repeated zero-latency result was overwritten");

        // Sustained real cadence: sample scans and DAC scans for all 32
        // slots, with DAC close to the next command boundary. No overflow.
        reset_monitor; read_voice(0);
        for(n=0;n<48;n=n+1) begin
            for(offset=0;offset<1024;offset=offset+1) begin
                @(negedge clk); command_commit=0; sample_event=0; dac_done=0;
                if(offset==0 && n<32) begin
                    command_commit=1; command_header={n[7:0],8'h01,3'd0,n[4:0],8'd0};
                    command_revision=24'd100+n; command_active_voices=0;
                    if(n==0) load_start=time_cycles;
                end
                if(offset==226) begin
                    sample_event=1; sample_revision=n<32 ? 24'd99+n : 24'd131; nonzero_voices=32'hffffffff;
                end
                if(offset==1008) begin
                    dac_done=1; dac_revision=n<33 ? 24'd98+n : 24'd131;
                    dac_nonzero_voices=32'hffffffff; dac_muted=0;
                end
            end
        end
        @(negedge clk); command_commit=0; sample_event=0; dac_done=0;
        for(i=0;i<32;i=i+1) begin
            read_voice(i); check_flags(7,1);
            if(query_data[127:96] !== 1250 || query_data[159:128] !== 3056 || query_data[191:160] !== 3056)
                $fatal(1,"slot %0d normal-cadence endpoints wrong: %0d/%0d",i,query_data[127:96],query_data[159:128]);
            if(query_data[223:192] !== 100+i) $fatal(1,"slot revision independence failed");
        end

        // Deliberate out-of-contract burst must expose a sticky observer
        // fault and freeze endpoints, rather than silently dropping work.
        command(1,3,200,0); read_voice(3); check_flags(1,2);
        repeat(8) begin
            @(negedge clk); sample_event=1; sample_revision=200; nonzero_voices=32'h8;
        end
        @(negedge clk); sample_event=0;
        read_voice(3);
        if(!flags[7] || flags[2]) $fatal(1,"observer overflow was hidden or fabricated a DAC endpoint");
        dac(201,32'h8,0); read_voice(3);
        if(!flags[7] || flags[2]) $fatal(1,"late event after overflow fabricated completion");
        $display("PASS tb_voice_onset_monitor: %0d atomic queries (max wait %0d clocks), 32 independent slots, retrigger/cancel/retained completion, revision/time wrap, same-edge precedence, expiry/zero endpoints, 48 full-load 1024-clock frames, explicit overflow fault",replies,max_query_wait);
        $finish;
    end
    initial begin #5000000; $fatal(1,"voice onset monitor timeout"); end
endmodule
