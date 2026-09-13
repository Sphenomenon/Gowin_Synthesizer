`timescale 1ns/1ps
module tb_audio_latency_tags;
    reg clk=0; always #10 clk=~clk;
    reg rst_n=0, cmd_valid=0, cmd_first=0, cmd_last=0, rsp_ready=0;
    reg [31:0] cmd_data=0;
    reg [511:0] latency_diagnostics=0;
    wire [7:0] memory_flags=0;
    wire [127:0] video_diagnostics=0;
    wire cmd_ready, rsp_valid, sample_tick, sample_valid;
    wire [31:0] rsp_data, active_voices, trigger_reference, sample_nonzero_voices;
    wire signed [31:0] sample_data;
    wire trace_commit, trace_frame_start, trace_sample_event;
    wire [31:0] trace_header, trace_nonzero_voices;
    wire [23:0] trace_revision, trace_sample_revision;
    wire trace_dac_done;
    wire [23:0] trace_dac_revision;
    wire [31:0] trace_dac_nonzero_voices;
    wire hp_bck,hp_ws,hp_din,pa_en;
    wire [31:0] underrun_count,frame_count;
    synth_engine engine(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),.mix_sum(),
        .voice_sample_event(),.voice_sample_data(),.voice_sample_index(),.master_volume(),.lr_balance(),.*);
    pt8211_tx dac(.clk(clk),.reset_n(rst_n),.sample_data(sample_data),.sample_valid(sample_valid),
        .sample_tick(sample_tick),.hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),
        .underrun_count(underrun_count),.frame_count(frame_count),
        .sample_revision(trigger_reference[31:8]),.sample_nonzero_voices(sample_nonzero_voices),
        .trace_dac_done(trace_dac_done),.trace_dac_revision(trace_dac_revision),
        .trace_dac_nonzero_voices(trace_dac_nonzero_voices));

    integer cycle=0, accepted_cycle=0, sample_events=0, dac_events=0;
    reg [23:0] expected_revision=0, expected_frame_revision=0;
    reg [23:0] pending_revision=0, serial_revision=0;
    reg [31:0] pending_mask=0, serial_mask=0;
    reg pending_tag=0, serial_tag=0;
    reg [23:0] event_revision;
    reg [31:0] event_mask;
    reg event_seen, done_seen;
    always @(posedge clk) begin
        if(rst_n) begin
            cycle=cycle+1;
            if(trace_frame_start) begin expected_frame_revision=expected_revision; accepted_cycle=cycle; end
            if(trace_commit) begin
                expected_revision=expected_revision+1'b1;
                if(trace_revision !== expected_revision || trace_header[23:16]<1 || trace_header[23:16]>10)
                    $fatal(1,"commit token/opcode mismatch");
            end
            event_seen=trace_sample_event; event_revision=trace_sample_revision; event_mask=trace_nonzero_voices;
            if(event_seen) begin
                if(cycle-accepted_cycle != 226 || event_revision !== expected_frame_revision)
                    $fatal(1,"sample trace is not the pre-edge event for the correct 226-clock frame");
                sample_events=sample_events+1;
            end
            // Independent model of which metadata accompanies the DAC's
            // actual sample consumption, including valid zero-valued PCM.
            if(dac.divider == 15 && hp_bck && dac.bit_index == 31) begin
                if(sample_valid) begin serial_revision=trigger_reference[31:8]; serial_mask=sample_nonzero_voices; serial_tag=1; end
                else begin serial_revision=pending_revision; serial_mask=pending_mask; serial_tag=pending_tag; end
                pending_tag=0;
            end else if(sample_valid) begin
                pending_revision=trigger_reference[31:8]; pending_mask=sample_nonzero_voices; pending_tag=1;
            end
            done_seen=trace_dac_done;
            if(done_seen) begin
                if(!serial_tag || trace_dac_revision !== serial_revision || trace_dac_nonzero_voices !== serial_mask)
                    $fatal(1,"DAC completion metadata lost its PCM association");
                dac_events=dac_events+1;
            end
            #1;
            if(sample_valid !== event_seen) $fatal(1,"trace_sample_event gained an extra observation clock");
            if(event_seen && (trigger_reference[31:8] !== event_revision || sample_nonzero_voices !== event_mask))
                $fatal(1,"registered audio/tag outputs are not aligned");
            if(done_seen && (hp_bck !== 1 || hp_ws !== 1 || dac.bit_index != 31))
                $fatal(1,"DAC done did not mark the last left-slot BCK rising edge");
            if(underrun_count !== 0) $fatal(1,"engine/DAC tags changed the real-time schedule");
        end
    end

    integer seq=0, n;
    task send_word(input [31:0] value,input first,input last);
        begin
            @(negedge clk); while(!cmd_ready) @(negedge clk);
            cmd_data=value; cmd_valid=1; cmd_first=first; cmd_last=last;
            @(negedge clk); cmd_valid=0; cmd_first=0; cmd_last=0;
        end
    endtask
    task command(input [7:0] op,input [7:0] voice_id,input [31:0] value,
                 input [7:0] flags,input [7:0] status,input [7:0] diagnostic_byte);
        reg [23:0] revision_before;
        begin
            revision_before=expected_revision;
            send_word({seq[7:0],op,voice_id,flags},1,0); send_word(value,0,1);
            while(!rsp_valid) @(negedge clk);
            if(rsp_data[31:24] !== seq[7:0] || rsp_data[23:16] !== status || rsp_data[7:0] !== op)
                $fatal(1,"command response mismatch %h",rsp_data);
            if(op == 8'h0e && (rsp_data[15:8] !== diagnostic_byte || expected_revision !== revision_before))
                $fatal(1,"latency diagnostic snapshot changed or disturbed sound revision");
            rsp_ready=1; @(negedge clk); rsp_ready=0; seq=seq+1;
        end
    endtask
    task next_sample;
        integer target;
        begin target=sample_events+1; while(sample_events<target) @(negedge clk); end
    endtask
    task expect_sample(input [23:0] revision,input [31:0] mask,input signed [31:0] value);
        begin
            next_sample;
            if(trigger_reference[31:8] !== revision || sample_nonzero_voices !== mask || sample_data !== value)
                $fatal(1,"sample/tag mismatch got %h/%h/%h expected %h/%h/%h",trigger_reference[31:8],sample_nonzero_voices,sample_data,revision,mask,value);
        end
    endtask

    // A second transmitter exercises its difficult same-edge input path
    // without disturbing the real engine's regular requests.
    reg aux_reset_n=0, aux_valid=0;
    reg signed [31:0] aux_sample=0;
    reg [23:0] aux_revision=0;
    reg [31:0] aux_mask=0;
    wire aux_tick,aux_bck,aux_ws,aux_din,aux_pa,aux_done;
    wire [23:0] aux_done_revision;
    wire [31:0] aux_done_mask,aux_underrun,aux_frames;
    integer aux_events=0;
    reg aux_fired;
    pt8211_tx #(.BCK_HALF_CYCLES(2)) direct_dac(.clk(clk),.reset_n(aux_reset_n),
        .sample_data(aux_sample),.sample_valid(aux_valid),.sample_tick(aux_tick),
        .hp_bck(aux_bck),.hp_ws(aux_ws),.hp_din(aux_din),.pa_en(aux_pa),
        .underrun_count(aux_underrun),.frame_count(aux_frames),
        .sample_revision(aux_revision),.sample_nonzero_voices(aux_mask),
        .trace_dac_done(aux_done),.trace_dac_revision(aux_done_revision),.trace_dac_nonzero_voices(aux_done_mask));
    always @(posedge clk) if(aux_reset_n) begin
        aux_fired=aux_done;
        if(aux_done) begin
            aux_events=aux_events+1;
            if(aux_events == 1 && (aux_done_revision !== 24'h22 || aux_done_mask !== 32'h80000000))
                $fatal(1,"same-edge sample did not override pending metadata");
            if(aux_events == 2 && (aux_done_revision !== 24'h33 || aux_done_mask !== 0))
                $fatal(1,"valid zero PCM lost its completion tag");
            if(aux_events>2) $fatal(1,"underrun reused a stale completion tag");
        end
        #1;
        if(aux_fired && (aux_bck !== 1 || aux_ws !== 1 || direct_dac.bit_index != 31))
            $fatal(1,"aux completion is not the final serial bit rising edge");
    end

    reg [23:0] note_revision;
    initial begin
        for(n=0;n<64;n=n+1) latency_diagnostics[n*8 +: 8]=n^8'h5a;
        repeat(3) @(negedge clk); rst_n=1;
        next_sample;
        command(14,255,1,0,3,0); command(14,255,64,0,3,0);
        command(14,31,0,0,2,0); command(14,255,0,1,3,0);
        command(14,255,0,0,0,8'h5a);
        latency_diagnostics={512{1'b1}};
        command(14,255,1,0,0,8'h5b); command(14,255,63,0,0,8'h65);
        command(6,31,0,0,0,0); command(7,31,0,0,0,0);
        command(8,31,32'h80000000,0,0,0); command(4,31,32'h80000000,0,0,0);
        command(5,31,1,0,0,0);
        command(1,31,0,0,0,0); note_revision=expected_revision;
        if(sample_nonzero_voices !== 0 || sample_data !== 0)
            $fatal(1,"NOTE_ON commit frame falsely attributed old audio as sounding");
        expect_sample(note_revision,0,0); // new state but envelope is still zero
        expect_sample(note_revision,32'h80000000,32'h7fffffff);
        // Positive contribution one step below and at the PCM16 rounding
        // threshold for the voice's unscaled Q1.31 contribution.
        command(4,31,32'h00008000,0,0,0);
        expect_sample(expected_revision,0,32'h00007fff);
        command(4,31,32'h00008001,0,0,0);
        expect_sample(expected_revision,32'h80000000,32'h00008000);
        command(10,255,0,0,0,0);
        expect_sample(expected_revision,0,0);
        command(4,31,32'h80000000,0,0,0); command(5,31,2,0,0,0);
        command(1,31,32'h40000000,0,0,0); note_revision=expected_revision;
        expect_sample(note_revision,0,0);
        expect_sample(note_revision,32'h80000000,32'h7fffffff);
        expect_sample(note_revision,0,0);
        expect_sample(note_revision,32'h80000000,32'h80000001);
        command(14,255,0,0,0,8'hff); // diagnostics while oscillating do not create revisions
        command(14,255,63,0,0,8'hff);

        @(negedge clk); aux_reset_n=1; aux_valid=1; aux_sample=32'h12340000; aux_revision=24'h11; aux_mask=32'h1;
        @(negedge clk);
        if(direct_dac.divider != 1 || !aux_bck || direct_dac.bit_index != 31)
            $fatal(1,"aux same-edge stimulus missed the consume boundary");
        aux_sample=0; aux_revision=24'h22; aux_mask=32'h80000000;
        @(negedge clk); aux_valid=0;
        while(aux_events<1) @(negedge clk);
        repeat(270) @(negedge clk);
        if(aux_events != 1 || aux_underrun == 0) $fatal(1,"underrun tag invalidation was not exercised");
        aux_sample=0; aux_revision=24'h33; aux_mask=0; aux_valid=1;
        @(negedge clk); aux_valid=0;
        while(aux_events<2) @(negedge clk);
        repeat(270) @(negedge clk);
        if(aux_events != 2 || dac_events<20) $fatal(1,"insufficient serial tag coverage");
        $display("PASS tb_audio_latency_tags: %0d sample/%0d DAC events, 226-clock pre-edge events, slot31 pulse/sine onset, old/new revision, PCM16 threshold, atomic 64-byte diagnostics, same-edge consume, valid zero PCM and underrun tag invalidation",sample_events,dac_events);
        $finish;
    end
    initial begin #4000000; $fatal(1,"audio latency tag timeout"); end
endmodule
