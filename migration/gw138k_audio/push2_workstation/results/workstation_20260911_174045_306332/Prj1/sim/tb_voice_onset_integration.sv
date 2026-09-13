`timescale 1ns/1ps
// Actual engine32 -> PT8211 pin decoding -> per-voice onset records -> 0F
// byte snapshots. Direct engine commands omit UART transport intentionally;
// all clocks and the 1024-clock audio cadence match the board.
module tb_voice_onset_integration;
    localparam [7:0] COLD_SEQUENCE=8'h31, RETRIGGER_SEQUENCE=8'h32;
    reg clk=0;
    always #10 clk=~clk;
    reg rst_n=0;
    reg [31:0] time_cycles=0;
    always @(posedge clk or negedge rst_n)
        if(!rst_n) time_cycles<=0; else time_cycles<=time_cycles+1'b1;
    reg [31:0] cmd_data=0;
    reg cmd_valid=0,cmd_first=0,cmd_last=0,rsp_ready=0;
    wire cmd_ready,rsp_valid;
    wire [31:0] rsp_data;
    wire signed [31:0] sample_data;
    wire sample_valid,sample_tick;
    wire [31:0] active_voices,trigger_reference,sample_nonzero_voices;
    wire trace_commit,trace_frame_start,trace_sample_event;
    wire [31:0] trace_header,trace_nonzero_voices;
    wire [23:0] trace_revision,trace_sample_revision;
    wire onset_query_request,onset_query_done;
    wire [4:0] onset_query_voice;
    wire [255:0] onset_query_data;
    synth_engine #(.VOICE_COUNT(32)) engine(
        .clk(clk),.rst_n(rst_n),.sample_tick(sample_tick),
        .cmd_data(cmd_data),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_first(cmd_first),.cmd_last(cmd_last),
        .rsp_data(rsp_data),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),
        .sample_data(sample_data),.sample_valid(sample_valid),.active_voices(active_voices),.trigger_reference(trigger_reference),
        .memory_flags(8'd0),.video_diagnostics(128'd0),.latency_diagnostics(512'd0),
        .trace_commit(trace_commit),.trace_header(trace_header),.trace_revision(trace_revision),
        .trace_frame_start(trace_frame_start),.trace_sample_event(trace_sample_event),
        .trace_sample_revision(trace_sample_revision),.trace_nonzero_voices(trace_nonzero_voices),
        .sample_nonzero_voices(sample_nonzero_voices),
        .onset_query_request(onset_query_request),.onset_query_voice(onset_query_voice),
        .onset_query_done(onset_query_done),.onset_query_data(onset_query_data));
    wire hp_bck,hp_ws,hp_din,pa_en,trace_dac_done;
    wire [31:0] underrun_count,frame_count,trace_dac_nonzero_voices;
    wire [23:0] trace_dac_revision;
    pt8211_tx audio_output(
        .clk(clk),.reset_n(rst_n),.sample_data(sample_data),.sample_valid(sample_valid),
        .sample_tick(sample_tick),.hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),
        .underrun_count(underrun_count),.frame_count(frame_count),
        .sample_revision(trigger_reference[31:8]),.sample_nonzero_voices(sample_nonzero_voices),
        .trace_dac_done(trace_dac_done),.trace_dac_revision(trace_dac_revision),
        .trace_dac_nonzero_voices(trace_dac_nonzero_voices));
    voice_onset_monitor monitor(
        .clk(clk),.rst_n(rst_n),.time_cycles(time_cycles),
        .command_commit(trace_commit),.command_header(trace_header),.command_revision(trace_revision),
        .command_active_voices(active_voices),
        .sample_event(trace_sample_event),.sample_revision(trace_sample_revision),.nonzero_voices(trace_nonzero_voices),
        .dac_done(trace_dac_done),.dac_revision(trace_dac_revision),.dac_nonzero_voices(trace_dac_nonzero_voices),
        .dac_muted(pa_en),.query_request(onset_query_request),.query_voice(onset_query_voice),
        .query_done(onset_query_done),.query_data(onset_query_data));

    reg [31:0] latest_response;
    task transact(input [7:0] seq,input [7:0] opcode,input [7:0] voice,input [31:0] value);
        integer deadline;
        begin
            @(negedge clk);
            deadline=0;
            while(!cmd_ready && deadline<8192) begin @(negedge clk); deadline=deadline+1; end
            if(!cmd_ready) $fatal(1,"command header ready timeout");
            cmd_valid=1; cmd_first=1; cmd_last=0; cmd_data={seq,opcode,voice,8'd0};
            @(negedge clk); cmd_first=0; cmd_last=1; cmd_data=value;
            while(!cmd_ready) @(negedge clk);
            @(negedge clk); cmd_valid=0; cmd_last=0;
            deadline=0;
            while(!rsp_valid && deadline<8192) begin @(negedge clk); deadline=deadline+1; end
            if(!rsp_valid || rsp_data[31:24]!==seq || rsp_data[23:16]!==0 || rsp_data[7:0]!==opcode)
                $fatal(1,"unexpected response seq=%h opcode=%h data=%h",seq,opcode,rsp_data);
            latest_response=rsp_data;
            rsp_ready=1; @(negedge clk); rsp_ready=0;
        end
    endtask

    reg [7:0] query_sequence=8'h80;
    task query_byte(input [4:0] voice,input integer index,output [7:0] value);
        begin
            transact(query_sequence,8'h0f,{3'd0,voice},index);
            query_sequence=query_sequence+1'b1;
            value=latest_response[15:8];
        end
    endtask
    task read_record(input [4:0] voice,output [255:0] value);
        integer b;
        reg [7:0] octet;
        begin
            value=0;
            for(b=0;b<32;b=b+1) begin
                query_byte(voice,b,octet); value[b*8+:8]=octet;
            end
        end
    endtask
    function [31:0] word(input [255:0] record,input integer index);
        word=record[index*32+:32];
    endfunction

    reg cold_committed=0,retrigger_committed=0,cold_sample_seen=0,retrigger_sample_seen=0;
    reg cold_old_frame_seen=0,retrigger_old_frame_seen=0;
    reg [31:0] cold_commit_time,retrigger_commit_time,cold_sample_time,retrigger_sample_time;
    reg [23:0] cold_revision,retrigger_revision;
    always @(posedge clk) begin
        if(rst_n) begin
            if(trace_commit && trace_header[23:16]==1 && trace_header[15:8]==31) begin
                if(trace_header[31:24]==COLD_SEQUENCE) begin
                    if(active_voices[31]) $fatal(1,"cold trigger already active");
                    cold_committed=1; cold_commit_time=time_cycles; cold_revision=trace_revision;
                end else if(trace_header[31:24]==RETRIGGER_SEQUENCE) begin
                    if(!active_voices[31]) $fatal(1,"retrigger fixture was not already active");
                    retrigger_committed=1; retrigger_commit_time=time_cycles; retrigger_revision=trace_revision;
                end
            end
            if(trace_sample_event) begin
                if(cold_committed && time_cycles-cold_commit_time==226) begin
                    if(trace_sample_revision==cold_revision || trace_nonzero_voices[31])
                        $fatal(1,"cold commit frame's old state attributed to new trigger");
                    cold_old_frame_seen=1;
                end
                if(retrigger_committed && time_cycles-retrigger_commit_time==226) begin
                    if(trace_sample_revision==retrigger_revision || !trace_nonzero_voices[31])
                        $fatal(1,"active retrigger did not leave an old-revision nonzero frame in flight");
                    retrigger_old_frame_seen=1;
                end
                if(cold_committed && !cold_sample_seen && trace_sample_revision==cold_revision && trace_nonzero_voices[31]) begin
                    cold_sample_seen=1; cold_sample_time=time_cycles;
                end
                if(retrigger_committed && !retrigger_sample_seen && trace_sample_revision==retrigger_revision && trace_nonzero_voices[31]) begin
                    retrigger_sample_seen=1; retrigger_sample_time=time_cycles;
                end
            end
        end
    end

    // Only external PCM pins determine the digital endpoint below. The
    // full-gain pulse is +32767 PCM; a half-gain edit one frame before the
    // retrigger creates +16384 PCM. Its first serialized frame still predates
    // the retrigger revision; the second half-gain frame is the new generation.
    integer pcm_bit=0,pcm_frames=0,half_frames=0;
    reg [15:0] pcm_shift=0,right_pcm=0,last_pcm=0;
    reg cold_physical_seen=0,half_armed=0;
    reg [31:0] cold_physical_done,old_half_done,retrigger_physical_done;
    always @(posedge hp_bck) begin
        if(rst_n) begin
            #1;
            if(hp_ws!==(pcm_bit>=16)) $fatal(1,"PT8211 WS/independent bit index mismatch");
            pcm_shift={pcm_shift[14:0],hp_din};
            if(pcm_bit==15) right_pcm=pcm_shift;
            if(pcm_bit==31) begin
                if(pcm_shift!==right_pcm) $fatal(1,"PT8211 stereo PCM mismatch");
                if(pcm_shift!==0 && pcm_shift!==16'h7fff && pcm_shift!==16'h4000)
                    $fatal(1,"unexpected PCM signature from unrelated/muted voices: %h",pcm_shift);
                pcm_frames=pcm_frames+1; last_pcm=pcm_shift;
                if(!cold_physical_seen && pcm_shift!=0) begin
                    if(!cold_committed || pcm_shift!==16'h7fff || !pa_en)
                        $fatal(1,"cold pulse/muted-startup fixture incorrect");
                    cold_physical_seen=1; cold_physical_done=time_cycles-1'b1;
                end
                if(half_armed && pcm_shift==16'h4000) begin
                    half_frames=half_frames+1;
                    if(half_frames==1) old_half_done=time_cycles-1'b1;
                    if(half_frames==2) retrigger_physical_done=time_cycles-1'b1;
                end
            end
            pcm_bit=(pcm_bit+1)%32;
        end
    end

    reg [255:0] cold_snapshot,old_snapshot_bytes,retrigger_snapshot,preserved_snapshot,cancelled_snapshot;
    reg [7:0] octet;
    integer b;
    initial begin
        repeat(4) @(negedge clk); rst_n=1;
        transact(1,5,31,1);                         // pulse, phase zero positive
        transact(2,4,31,32'h80000000);              // unity velocity
        transact(3,6,31,0);                         // immediate attack
        transact(4,7,31,0);                         // immediate decay
        transact(5,8,31,32'h80000000);              // unity sustain
        transact(6,9,31,0);                         // immediate release
        transact(COLD_SEQUENCE,1,31,32'h00100000);  // slow enough to keep fixture positive
        wait(cold_physical_seen);
        query_byte(31,0,octet);
        cold_snapshot=onset_query_data; old_snapshot_bytes=0; old_snapshot_bytes[7:0]=octet;
        if(!cold_old_frame_seen || !cold_sample_seen || cold_physical_done-cold_commit_time!=4079 ||
           cold_sample_time-cold_commit_time!=2274)
            $fatal(1,"cold onset stage timing differs from independently decoded PCM");
        if(word(cold_snapshot,0)!==32'h47311f01 || word(cold_snapshot,1)!==1 || word(cold_snapshot,2)!==50000000 ||
           word(cold_snapshot,3)!==cold_sample_time-cold_commit_time || word(cold_snapshot,4)!==cold_physical_done-cold_commit_time ||
           word(cold_snapshot,5)!==word(cold_snapshot,4) || word(cold_snapshot,6)!=={8'd0,cold_revision} || word(cold_snapshot,7)!==0)
            $fatal(1,"cold slot31 record/schema/muted flag mismatch: %h",cold_snapshot);

        // Other voices retain their own pending triggers without clearing a
        // completed slot31 record or altering its already-latched byte view.
        transact(8'h41,4,0,0);
        transact(8'h42,1,0,32'h00100000);            // active but velocity zero
        transact(8'h43,6,0,1);
        half_armed=1;
        transact(8'h44,4,31,32'h40000000);
        transact(RETRIGGER_SEQUENCE,1,31,32'h00100000);
        wait(half_frames>=2);
        if(!retrigger_old_frame_seen || !retrigger_sample_seen ||
           old_half_done-retrigger_commit_time!=2031 || retrigger_physical_done-retrigger_commit_time!=3055 ||
           retrigger_sample_time-retrigger_commit_time!=1250)
            $fatal(1,"retrigger did not exclude old in-flight PCM: first_half=%0d second_half=%0d sample=%0d",
                old_half_done-retrigger_commit_time,retrigger_physical_done-retrigger_commit_time,retrigger_sample_time-retrigger_commit_time);

        // Same-slot NOTE_ON now changed the live monitor row, but bytes 1..31
        // must still be from the cold NOTE_ON captured by the first byte zero.
        for(b=1;b<32;b=b+1) begin
            query_byte(31,b,octet); old_snapshot_bytes[b*8+:8]=octet;
        end
        if(old_snapshot_bytes!==cold_snapshot) $fatal(1,"0F snapshot tore across another voice and same-voice retrigger");
        read_record(31,retrigger_snapshot);
        if(word(retrigger_snapshot,0)!==32'h4f321f01 || word(retrigger_snapshot,1)!==2 || word(retrigger_snapshot,2)!==50000000 ||
           word(retrigger_snapshot,3)!==retrigger_sample_time-retrigger_commit_time ||
           word(retrigger_snapshot,4)!==retrigger_physical_done-retrigger_commit_time ||
           word(retrigger_snapshot,5)!==word(retrigger_snapshot,4) ||
           word(retrigger_snapshot,6)!=={8'd0,retrigger_revision} || word(retrigger_snapshot,7)!==0)
            $fatal(1,"retrigger row did not retain its independent ID/source-edge endpoint: %h",retrigger_snapshot);

        // Completion freezes the entire record. Later releases, parameter
        // edits and another slot's cancellation cannot replace that result.
        transact(8'h45,2,31,0);
        transact(8'h46,2,0,0);
        transact(8'h47,4,5,32'h40000000);
        read_record(31,preserved_snapshot);
        if(preserved_snapshot!==retrigger_snapshot) $fatal(1,"completed onset record changed after NOTE_OFF/other-voice commands");
        read_record(0,cancelled_snapshot);
        if(word(cancelled_snapshot,0)!==32'h11420001 || word(cancelled_snapshot,1)!==1 ||
           word(cancelled_snapshot,3)!==0 || word(cancelled_snapshot,4)!==0 ||
           word(cancelled_snapshot,7)==0 || word(cancelled_snapshot,5)!==word(cancelled_snapshot,7))
            $fatal(1,"muted slot0 did not retain an independent cancelled trigger: %h",cancelled_snapshot);
        if(underrun_count!==0 || active_voices!==0 || last_pcm!==0)
            $fatal(1,"onset observations or snapshot traffic disturbed PCM transport");
        $display("VOICE_ONSET_INTEGRATION ticks@50MHz: cold_commit=%0d cold_sample=%0d cold_pin_done=%0d cold_sample_delta=%0d cold_DAC_delta=%0d",
            cold_commit_time,cold_sample_time,cold_physical_done,word(cold_snapshot,3),word(cold_snapshot,4));
        $display("VOICE_ONSET_INTEGRATION retrigger_commit=%0d old_half_pin_done=%0d new_half_pin_done=%0d sample_delta=%0d DAC_delta=%0d flags=%h note_id=%0d",
            retrigger_commit_time,old_half_done,retrigger_physical_done,word(retrigger_snapshot,3),word(retrigger_snapshot,4),retrigger_snapshot[31:24],word(retrigger_snapshot,1));
        $display("PASS voice onset integration: engine32/DAC real cadence, independent stereo PCM endpoints, slot31 cold/retrigger and old in-flight exclusion, amplifier-muted flags, per-voice retention/cancellation, atomic 0F bytes across retrigger, zero underruns over %0d PCM frames",pcm_frames);
        $finish;
    end
    initial begin #20000000; $fatal(1,"voice onset integration timeout"); end
endmodule
