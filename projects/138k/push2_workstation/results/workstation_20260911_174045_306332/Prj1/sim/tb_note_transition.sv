`timescale 1ns/1ps
// Audible regression: release a key, then reuse its still-sounding slot at
// another pitch. Check actual mixed samples, not just the envelope registers.
module tb_note_transition;
    reg clk=0; always #10 clk=~clk;
    reg rst_n=0, sample_tick=0, cmd_valid=0, cmd_first=0, cmd_last=0, rsp_ready=0;
    reg [31:0] cmd_data=0;
    wire cmd_ready, rsp_valid, sample_valid;
    wire [31:0] rsp_data, active_voices, trigger_reference;
    wire signed [31:0] sample_data;
    wire [7:0] memory_flags=0;
    wire [127:0] video_diagnostics=0;
    synth_engine #(.VOICE_COUNT(4)) dut(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),.latency_diagnostics(512'd0),.trace_commit(),.trace_header(),.trace_revision(),
        .trace_frame_start(),.trace_sample_event(),.trace_sample_revision(),.trace_nonzero_voices(),
        .sample_nonzero_voices(),.mix_sum(),.voice_sample_event(),.voice_sample_data(),
        .voice_sample_index(),.master_volume(),.lr_balance(),.*);
    integer seq=0, samples_checked=0, transitions=0, max_delta=0, delta;
    integer trace_fd;
    reg checking=0;
    reg signed [31:0] previous_sample=0;
    // One quarter-gain voice retains the original physical fixture level
    // after removal of mixer /4. For sine <=880Hz, natural sample motion
    // plus the 1/128 envelope step remains below the same absolute bound.
    localparam integer MAX_DELTA=134217728;
    task frame;
        integer c;
        begin
            while(!dut.bank_ready) @(negedge clk);
            @(negedge clk); sample_tick=1;
            @(negedge clk); sample_tick=0;
            for(c=1;c<=33;c=c+1) begin
                @(negedge clk);
                if(sample_valid !== (c==30)) $fatal(1,"sample latency changed");
                if(sample_valid) begin
                    delta=$signed(sample_data)-$signed(previous_sample);
                    if(delta<0) delta=-delta;
                    if(checking) begin
                        $fwrite(trace_fd,"%0d %0d\n",samples_checked,$signed(sample_data));
                        if(delta>max_delta) max_delta=delta;
                        if(delta>MAX_DELTA)
                            $fatal(1,"note-switch discontinuity: delta=%0d > %0d, previous=%0d current=%0d",delta,MAX_DELTA,$signed(previous_sample),$signed(sample_data));
                        samples_checked=samples_checked+1;
                    end
                    previous_sample=sample_data;
                end
            end
        end
    endtask
    task command(input [7:0] op,input [7:0] voice,input [31:0] value);
        begin
            @(negedge clk); while(!cmd_ready) @(negedge clk);
            cmd_valid=1; cmd_first=1; cmd_last=0; cmd_data={seq[7:0],op,voice,8'd0};
            @(negedge clk); cmd_first=0; cmd_last=1; cmd_data=value;
            @(negedge clk); cmd_valid=0; cmd_last=0;
            frame();
            if(!rsp_valid || rsp_data[23:16]!==0 || rsp_data[31:24]!==seq[7:0]) $fatal(1,"bad command response");
            rsp_ready=1; @(negedge clk); rsp_ready=0; seq=seq+1;
        end
    endtask
    task loud_phase;
        integer limit;
        begin
            limit=0;
            while(previous_sample<32'sh10000000 && previous_sample>-32'sh10000000) begin
                frame(); limit=limit+1;
                if(limit>5000) $fatal(1,"fixture never reached a loud waveform phase");
            end
        end
    endtask
    integer k;
    reg [31:0] next_pitch;
    reg [31:0] phase_before, envelope_before, other_phase, other_step;
    initial begin
        trace_fd=$fopen("build/sim/note_transition_samples.txt","w");
        repeat(4) @(negedge clk); rst_n=1;
        command(5,0,2); command(4,0,32'h20000000);
        // Default-like attack, long release, and a sustain below full scale.
        command(6,0,32'd8800000); command(7,0,32'd128000);
        command(8,0,32'h60000000); command(9,0,32'd175922);
        command(1,0,32'd38682809); // A4, 440 Hz at 48,828.125 Hz.
        repeat(5000) frame();
        loud_phase(); checking=1;
        command(2,0,0); repeat(20) frame();
        loud_phase(); command(1,0,32'd58024214); transitions=transitions+1;
        repeat(400) frame();
        // Many different release gaps, both waveform signs and attack/decay
        // stages. The released key's slot is reused before its tail ends.
        for(k=0;k<16;k=k+1) begin
            command(2,0,0); repeat(5+k*7) frame();
            next_pitch=k[0] ? 32'd77365619 : 32'd28994031;
            command(1,0,next_pitch); transitions=transitions+1;
            repeat(31+k*9) frame();
        end
        // Zero-time A/D remain valid settings. A reused sounding voice must
        // not jump from its current level to unity or back to sustain.
        checking=0; command(10,8'hff,0);
        command(6,0,0); command(7,0,0); command(8,0,32'h60000000);
        command(1,0,32'd38682809); repeat(10) frame();
        loud_phase(); checking=1;
        command(2,0,0); repeat(17) frame();
        loud_phase(); command(1,0,32'd58024214); transitions=transitions+1;
        repeat(350) frame();
        // Direct PITCH already has phase continuity; guard this path too.
        command(3,0,32'd77365619); repeat(150) frame();
        command(3,0,32'd23013058); repeat(150) frame();
        // NOTE_ON while held: no phase reset, no envelope reset, unaffected
        // neighbour. Pulse's intentional edges are excluded from delta test.
        checking=0; command(5,1,1); command(1,1,32'd23013058);
        command(5,0,1); repeat(10) frame();
        phase_before=dut.bank.state_memory[0][261:230];
        envelope_before=dut.bank.state_memory[0][197:166];
        other_phase=dut.bank.state_memory[1][261:230]; other_step=dut.bank.state_memory[1][229:198];
        command(1,0,32'd38682809);
        if(dut.bank.state_memory[0][261:230]!==phase_before+32'd23013058 ||
           dut.bank.state_memory[0][197:166]!==envelope_before)
            $fatal(1,"active NOTE_ON reset oscillator or level");
        if(dut.bank.state_memory[1][261:230]!==other_phase+other_step)
            $fatal(1,"note transition affected another voice");
        // NOTE_OFF during a reattack must cancel it; idle restart is still
        // deterministic, while PANIC keeps its immediate emergency semantics.
        command(2,0,0); command(9,0,0); repeat(4) frame();
        if(active_voices[0]) $fatal(1,"release during reattack failed");
        command(1,0,32'd28994031);
        if(dut.bank.state_memory[0][261:230]!==0 || dut.bank.state_memory[0][197:166]!==0)
            $fatal(1,"idle note-on no longer starts from silence");
        command(10,8'hff,0); repeat(3) frame();
        if(sample_data!==0 || active_voices!==0) $fatal(1,"panic failed");
        rst_n=0; repeat(4) @(negedge clk);
        if(sample_valid || active_voices!==0) $fatal(1,"reset failed");
        $fclose(trace_fd);
        $display("PASS note transition: %0d release-tail reuses, %0d real mixed samples, maximum adjacent delta=%0d (limit=%0d); zero-time reattack, direct pitch, pulse continuity, voice isolation, release cancellation, idle restart, panic and reset",transitions,samples_checked,max_delta,MAX_DELTA);
        $finish;
    end
    initial begin #40000000; $fatal(1,"note transition timeout"); end
endmodule
