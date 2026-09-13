`timescale 1ns/1ps
// Real four-voice synth -> 1024-point capture -> pattern trigger -> raster.
// Audio cadence is the board rate (one sample per 1024 system clocks).
module tb_feedback_stable_display;
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
    // Keep this four-note waveform scenario independent of the production
    // bank size; the shared engine's 32-slot coverage has separate tests.
    synth_engine #(.VOICE_COUNT(4)) engine(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),.latency_diagnostics(512'd0),.trace_commit(),.trace_header(),.trace_revision(),
        .trace_frame_start(),.trace_sample_event(),.trace_sample_revision(),.trace_nonzero_voices(),
        .sample_nonzero_voices(),.mix_sum(),.voice_sample_event(),.voice_sample_data(),
        .voice_sample_index(),.master_volume(),.lr_balance(),.*);
    reg start=0;
    wire frame_ready, busy, done, pixel_valid;
    wire [63:0] pixel_data;
    feedback_renderer #(.WIDTH(128),.HEIGHT(800)) renderer(
        .clk(render_clk),.rst_n(capture_reset_n),.start(start),.frame_ready(frame_ready),
        .busy(busy),.frame_done(done),.pixel_valid(pixel_valid),.pixel_ready(1'b1),.pixel_data(pixel_data),
        .source_clk(clk),.source_reset_n(capture_reset_n),.sample_data(sample_data),.sample_valid(sample_valid),
        .trigger_reference(trigger_reference),.active_voices(active_voices),.status_data(32'h12345678),
        .memory_status(32'hcb),.underruns(32'd0),.frame_count(32'd0));

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
    reg [23:0] history_revision[0:16383];
    integer reference_changes=0, mixed_edges=0, ignored_mixed_edges=0;
    reg [31:0] previous_mix=0;
    task frame;
        integer v, c, selected, valid_count;
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
            @(negedge clk); sample_tick=1;
            for(v=0;v<4;v=v+1) begin
                addition={1'b0,model_phase[v]}+{1'b0,model_step[v]};
                if(model_active[v]) begin model_phase[v]=addition[31:0]; model_wrap[v]=addition[32]; end
            end
            model_attack=0;
            model_active=model_active & ~model_release; model_release=0;
            @(negedge clk); sample_tick=0;
            valid_count=0;
            // The time-shared bank has a bounded completion deadline, not
            // the old parallel bank's fixed five-cycle latency. Preserve
            // the physical 1024-clock audio cadence and reject duplicates.
            for(c=1;c<=1022;c=c+1) begin
                @(negedge clk);
                if(sample_valid) valid_count=valid_count+1;
                if(checking && sample_valid) begin
                    if(trigger_reference[0]!==found || trigger_reference[1]!==edge_expected ||
                        (found && trigger_reference[7:2]!==selected) || trigger_reference[31:8]!==model_revision)
                        $fatal(1,"DDS reference mismatch sample %0d tag=%h expected voice=%0d valid=%0d edge=%0d",
                            history_count,trigger_reference,selected,found,edge_expected);
                    history[history_count]=sample_data;
                    history_voices[history_count]=active_voices;
                    history_edge[history_count]=edge_expected;
                    history_revision[history_count]=model_revision;
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
            if(valid_count!=1) $fatal(1,"shared bank must emit one sample within its 1024-clock frame, got %0d",valid_count);
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

    reg [31:0] observed[0:511], previous_trace[0:511];
    reg previous_valid=0;
    reg [31:0] previous_revision=0;
    integer frames_checked=0, holds_checked=0, rearms_checked=0, accepted_checked=0;
    integer i,j,start_index,total_error,max_error=0,beats;
    integer height_a,height_b;
    reg candidate_matches;
    initial begin
        forever begin
            wait(frame_ready); #1;
            total_error=0;
            for(i=0;i<512;i=i+1) begin
                // These are the exact RAM words used by the renderer's pixel
                // path, checked separately through its synchronous read port.
                observed[i]=renderer.u_align.trace_samples[i];
                height_a=$signed(observed[i]) >>> 23;
                height_b=$signed(previous_trace[i]) >>> 23;
                if(previous_valid) total_error=total_error+(height_a>height_b ? height_a-height_b : height_b-height_a);
                if(previous_valid && renderer.waveform_held && observed[i]!==previous_trace[i])
                    $fatal(1,"HOLD changed a displayed chord sample");
            end
            if(!previous_valid || previous_revision!==renderer.snapshot_revision) begin
                if(renderer.waveform_held) $fatal(1,"sound change failed to rearm display");
                rearms_checked=rearms_checked+1;
            end else if(!renderer.waveform_held) begin
                if(total_error>2048) $fatal(1,"accepted chord trace jumped beyond full-window match limit");
                if(total_error>max_error) max_error=total_error;
            end
            if(renderer.waveform_held) holds_checked=holds_checked+1;
            else begin
                accepted_checked=accepted_checked+1;
                start_index=-1;
                for(i=0;i<history_count-511;i=i+1) begin
                    if(start_index<0 && history_revision[i]===renderer.snapshot_revision[23:0] && history[i]===observed[0]) begin
                        candidate_matches=1;
                        for(j=0;j<512;j=j+1)
                            if(history[i+j]!==observed[j] || history_revision[i+j]!==renderer.snapshot_revision[23:0]) candidate_matches=0;
                        if(candidate_matches) start_index=i;
                    end
                end
                if(start_index<0) $fatal(1,"displayed trace is not a real consecutive mixed window from its revision");
            end
            previous_revision=renderer.snapshot_revision; previous_valid=1;
            for(i=0;i<512;i=i+1) previous_trace[i]=observed[i];
            @(negedge render_clk); start=1;
            @(negedge render_clk); start=0; beats=0;
            while(!done) begin
                if(pixel_valid) beats=beats+1;
                @(negedge render_clk);
            end
            if(beats!=51200) $fatal(1,"stable-display raster length mismatch: %0d",beats);
            frames_checked=frames_checked+1;
        end
    end

    integer voice;
    initial begin
        for(voice=0;voice<4;voice=voice+1) begin model_phase[voice]=0; model_step[voice]=0; model_gain[voice]=32'h60000000; end
        repeat(4) @(negedge clk); rst_n=1;
        wait(engine.bank_ready);
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
        command(4,1,0); repeat(1500) frame();
        command(4,1,32'h80000000); repeat(1500) frame();
        command(2,1,0); repeat(1500) frame();
        command(1,1,32'd19351405); repeat(1500) frame();
        if(frames_checked<6 || holds_checked<1 || rearms_checked<2 || reference_changes<4 || ignored_mixed_edges<50)
            $fatal(1,"insufficient coverage frames=%0d holds=%0d rearms=%0d refs=%0d mixed=%0d",
                frames_checked,holds_checked,rearms_checked,reference_changes,ignored_mixed_edges);
        // Stop capture after the mixed-window checks; verify silent reference
        // removal and reset without treating a flat auto snapshot as phase-locked.
        capture_reset_n=0;
        command(10,8'hff,0); repeat(4) frame();
        if(active_voices!==0 || sample_data!==0) $fatal(1,"panic did not clear audio");
        rst_n=0; repeat(8) @(negedge clk);
        if(trigger_reference!==0) $fatal(1,"reference survived reset");
        $display("PASS stable chord display: %0d actual rasters, %0d HOLD frames unchanged, %0d new real windows, %0d sound-revision rearms, maximum accepted same-revision mean change %0f pixels; live audio and full capture/matcher/renderer chain",
            frames_checked,holds_checked,accepted_checked,rearms_checked,max_error/512.0);
        $finish;
    end
    initial begin #400000000; $fatal(1,"polyphonic test timeout"); end
endmodule
