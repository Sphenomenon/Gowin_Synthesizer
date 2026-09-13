`timescale 1ns/1ps
// Real four-voice synth -> sample-aligned DDS reference -> async capture RAM.
module tb_feedback_polyphonic;
    reg clk=0, render_clk=0, rst_n=0, capture_reset_n=0;
    always #10 clk=~clk;
    always #7 render_clk=~render_clk;
    reg sample_tick=0, cmd_valid=0, cmd_first=0, cmd_last=0, rsp_ready=0;
    reg [31:0] cmd_data=0;
    wire cmd_ready, rsp_valid, sample_valid;
    wire [31:0] rsp_data, active_voices, trigger_reference;
    wire signed [31:0] sample_data;
    wire [7:0] memory_flags=8'hcb;
    wire [127:0] video_diagnostics=0;
    synth_engine #(.VOICE_COUNT(4)) engine(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),.latency_diagnostics(512'd0),.trace_commit(),.trace_header(),.trace_revision(),
        .trace_frame_start(),.trace_sample_event(),.trace_sample_revision(),.trace_nonzero_voices(),
        .sample_nonzero_voices(),.mix_sum(),.voice_sample_event(),.voice_sample_data(),
        .voice_sample_index(),.master_volume(),.lr_balance(),.*);
    reg release_snapshot=0, rd_en=0;
    reg [8:0] addr=0;
    wire ready;
    wire [31:0] data, peak, sequence_word, skipped, snap_voices, snap_status;
    // +LEGACY deliberately restores the previous mixed-zero-crossing path.
    wire [31:0] capture_reference=$test$plusargs("LEGACY") ? 32'd0 : trigger_reference;
    feedback_capture capture(.source_clk(clk),.source_reset_n(capture_reset_n),
        .sample_data(sample_data),.sample_valid(sample_valid),.trigger_reference(capture_reference),
        .active_voices(active_voices),.status_data(32'h12345678),
        .render_clk(render_clk),.render_reset_n(capture_reset_n),
        .snapshot_ready(ready),.snapshot_release(release_snapshot),.snapshot_peak(peak),
        .snapshot_sequence(sequence_word),.snapshot_skipped(skipped),
        .snapshot_voices(snap_voices),.snapshot_status(snap_status),
        .wave_read_enable(rd_en),.wave_read_addr(addr),.wave_read_data(data));

    // Independent phase model is driven only by test commands. Wraps come
    // from the 33-bit DDS addition, not the DUT's phase-comparison logic.
    reg [31:0] model_phase[0:3], model_step[0:3], model_gain[0:3];
    reg [3:0] model_active=0, model_attack=0, model_release=0, model_wrap=0;
    reg previous_ref_valid=0;
    integer previous_ref=0;
    reg checking=0, finished=0;
    integer seq=0, n, verified=0, history_count=0;
    reg [23:0] model_revision=0;
    reg [31:0] history[0:16383], history_voices[0:16383];
    reg history_edge[0:16383];
    integer reference_changes=0, mixed_edges=0, ignored_mixed_edges=0;
    reg [31:0] previous_mix=0;
    task frame;
        integer v, c, selected;
        reg found, edge_expected;
        reg [31:0] minimum_step;
        reg [32:0] addition;
        begin
            found=0; selected=0; minimum_step=32'hffffffff;
            for(v=0;v<4;v=v+1) begin
                if(model_active[v] && !model_attack[v] && model_gain[v]!=0 &&
                    model_step[v]!=0 && model_step[v]<minimum_step) begin
                    found=1; selected=v; minimum_step=model_step[v];
                end
            end
            edge_expected=found && previous_ref_valid && selected==previous_ref && model_wrap[selected];
            if(checking && found && previous_ref_valid && selected!=previous_ref)
                reference_changes=reference_changes+1;
            previous_ref_valid=found; previous_ref=selected;
            while(!engine.bank_ready) @(negedge clk);
            @(negedge clk); sample_tick=1;
            for(v=0;v<4;v=v+1) begin
                addition={1'b0,model_phase[v]}+{1'b0,model_step[v]};
                if(model_active[v]) begin model_phase[v]=addition[31:0]; model_wrap[v]=addition[32]; end
            end
            model_attack=0;
            model_active=model_active & ~model_release; model_release=0;
            @(negedge clk); sample_tick=0;
            for(c=1;c<=33;c=c+1) begin
                @(negedge clk);
                if(sample_valid !== (c==30)) $fatal(1,"audio sample latency changed");
                if(checking && sample_valid) begin
                    if(trigger_reference[0]!==found || trigger_reference[1]!==edge_expected ||
                        (found && trigger_reference[7:2]!==selected) || trigger_reference[31:8]!==model_revision)
                        $fatal(1,"DDS reference mismatch sample %0d tag=%h expected voice=%0d valid=%0d edge=%0d",
                            history_count,trigger_reference,selected,found,edge_expected);
                    history[history_count]=sample_data;
                    history_voices[history_count]=active_voices;
                    history_edge[history_count]=edge_expected;
                    if(previous_mix[31] && !sample_data[31]) begin
                        mixed_edges=mixed_edges+1;
                        if(!edge_expected) ignored_mixed_edges=ignored_mixed_edges+1;
                    end
                    previous_mix=sample_data;
                    history_count=history_count+1; verified=verified+1;
                end
                if(!sample_valid && trigger_reference!==0)
                    $fatal(1,"reference tag not aligned to sample_valid");
            end
        end
    endtask
    task command(input [7:0] op, input [7:0] voice, input [31:0] value);
        begin
            @(negedge clk);
            while(!cmd_ready) @(negedge clk);
            cmd_valid=1; cmd_first=1; cmd_last=0; cmd_data={seq[7:0],op,voice,8'd0};
            @(negedge clk); cmd_first=0; cmd_last=1; cmd_data=value;
            @(negedge clk); cmd_valid=0; cmd_last=0;
            frame();
            if(!rsp_valid || rsp_data[23:16]!==0 || rsp_data[31:24]!==seq[7:0]) $fatal(1,"command failed");
            if(op>=1 && op<=10) model_revision=model_revision+1'b1;
            case(op)
                1: begin model_phase[voice]=0; model_step[voice]=value; model_active[voice]=1; model_attack[voice]=1; model_wrap[voice]=1; end
                2: model_release[voice]=1;
                3: model_step[voice]=value;
                4: model_gain[voice]=value;
                10: begin model_active=0; model_attack=0; model_release=0; model_wrap=0; for(n=0;n<4;n=n+1) model_phase[n]=0; end
            endcase
            rsp_ready=1; @(negedge clk); rsp_ready=0; seq=seq+1;
        end
    endtask

    reg [31:0] observed[0:511];
    integer frames_checked=0, search_start=0, start_index, i, j;
    reg candidate_matches;
    reg [31:0] expected_peak, magnitude, held_sequence, held_peak, held_voices, held_skipped;
    task read_word(input integer index);
        begin
            @(negedge render_clk); rd_en=1; addr=index;
            @(posedge render_clk); #1;
            @(negedge render_clk); rd_en=0;
        end
    endtask
    initial begin
        forever begin
            wait(ready); #1;
            held_sequence=sequence_word; held_peak=peak; held_voices=snap_voices; held_skipped=skipped;
            if(snap_status!==32'h12345678 || sequence_word!==frames_checked)
                $fatal(1,"snapshot metadata mismatch");
            expected_peak=0;
            for(i=0;i<512;i=i+1) begin
                read_word(i); observed[i]=data;
                magnitude=data[31] ? (~data+1'b1) : data;
                if(magnitude>expected_peak) expected_peak=magnitude;
            end
            start_index=-1;
            for(i=search_start;i<history_count-511;i=i+1) begin
                if(start_index<0 && history_edge[i] && history[i]===observed[0]) begin
                    candidate_matches=1;
                    for(j=0;j<512;j=j+1) if(history[i+j]!==observed[j]) candidate_matches=0;
                    if(candidate_matches) start_index=i;
                end
            end
            if(start_index<0) $fatal(1,"chord snapshot %0d jumped away from its reference phase",frames_checked);
            if(peak!==expected_peak || snap_voices!==history_voices[start_index+511])
                $fatal(1,"chord snapshot does not describe its exact 512 mixed samples");
            search_start=start_index+512;
            // Keep rendering busy through several further oscillator cycles.
            repeat(10000+frames_checked*37) @(negedge render_clk);
            read_word(0);
            if(data!==observed[0] || sequence_word!==held_sequence || peak!==held_peak ||
                snap_voices!==held_voices || skipped!==held_skipped)
                $fatal(1,"published chord snapshot changed while held");
            frames_checked=frames_checked+1;
            @(negedge render_clk); release_snapshot=1;
            @(negedge render_clk); release_snapshot=0;
        end
    end

    integer voice;
    initial begin
        for(voice=0;voice<4;voice=voice+1) begin model_phase[voice]=0; model_step[voice]=0; model_gain[voice]=32'h60000000; end
        repeat(4) @(negedge clk); rst_n=1;
        for(voice=0;voice<4;voice=voice+1) begin
            command(6,voice,0); command(7,voice,0); command(8,voice,32'h80000000);
            command(9,voice,0); command(4,voice,32'h80000000); command(5,voice,2);
        end
        // Equal-tempered C4/E4/G4/C5, deliberately staggered and out of slot order.
        command(1,0,32'd28994031); command(1,1,32'd34479737);
        command(1,2,32'd23013058); command(1,3,32'd46026117);
        repeat(4) frame(); checking=1; capture_reset_n=1;
        repeat(3000) frame();
        // Change the reference by pitch, then use a mixture of oscillator shapes.
        command(3,1,32'd15342039); command(5,0,1); command(5,2,0);
        repeat(2000) frame();
        // A muted low voice must not control the trace. Re-enabling it at an
        // arbitrary phase must wait for a real subsequent cycle boundary.
        command(4,1,0); repeat(1000) frame();
        command(4,1,32'h80000000); repeat(1000) frame();
        command(2,1,0); repeat(1000) frame();
        command(1,1,32'd19351405); repeat(1000) frame();
        if(frames_checked<8 || reference_changes<4 || ignored_mixed_edges<50)
            $fatal(1,"insufficient chord/reference/busy-buffer coverage");
        // Stop capture after the mixed-window checks; verify silent reference
        // removal and reset without treating a flat auto snapshot as phase-locked.
        capture_reset_n=0;
        command(10,8'hff,0); repeat(4) frame();
        if(active_voices!==0 || sample_data!==0) $fatal(1,"panic did not clear audio");
        rst_n=0; repeat(8) @(negedge clk);
        if(trigger_reference!==0) $fatal(1,"reference survived reset");
        $display("PASS polyphonic feedback: %0d aligned samples, %0d exact chord snapshots, %0d reference changes, %0d/%0d mixed zero crossings ignored; pitch, shapes, mute, release, retrigger, panic and reset",
            verified,frames_checked,reference_changes,ignored_mixed_edges,mixed_edges);
        $finish;
    end
    initial begin #40000000; $fatal(1,"polyphonic test timeout"); end
endmodule
