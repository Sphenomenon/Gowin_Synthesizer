`timescale 1ns/1fs
module tb_workstation_pcm_frame_bridge;
    parameter integer CLOCK_CASE=0;
    reg serial_clk=0, compute_clk=0, global_reset_n=0, serial_reset_n=0;
    reg serial_clock_run=1;
    real serial_half=40.690;
    // Independent 76.8 MHz compute reference; no free-running sample enable.
    always #6.510416667 compute_clk=!compute_clk;
    initial begin
        #(CLOCK_CASE ? 11.173 : 3.701);
        forever begin
            #(serial_half);
            if(serial_clock_run) serial_clk=!serial_clk;
        end
    end
    reg mode=0,quiesce=1,resume_output=0,permit_reply=1;
    reg [31:0] epoch=1;
    reg [1:0] serial_quiesce_sync=3;
    always @(posedge serial_clk or negedge serial_reset_n)
        if(!serial_reset_n) serial_quiesce_sync<=3;
        else serial_quiesce_sync<={serial_quiesce_sync[0],quiesce};
    wire serial_quiet,running,prefill,request,request_mode,sample_ready;
    wire [31:0] request_epoch,request_sequence;
    wire bridge_ready,sample_valid,sample_mode,render_request,render_mode,render_busy,bridge_quiet;
    wire [31:0] sample_epoch,sample_sequence,sample_pcm,render_epoch,render_sequence;
    wire [31:0] request_drops,return_discards,cancel_requests,cancel_renders,unexpected;
    reg render_ready=1,model_done=0,inject_done=0;
    reg [31:0] model_pcm=0;
    wire mclk,bck,lrck,sd,pdn,smute,frame_valid,frame_error,frame_mode;
    wire [31:0] frame_pcm,frame_sequence,frame_epoch,underruns,rejected;
    workstation_i2s_serializer #(.PDN_HOLD_FRAMES(1),.STARTUP_MUTE_FRAMES(3)) serial(
        .clk_i(serial_clk),.rst_ni(serial_reset_n),.rate_44k1_i(mode),.epoch_i(epoch),
        .quiesce_i(serial_quiesce_sync[1]),.resume_i(resume_output),
        .serial_quiescent_o(serial_quiet),.output_running_o(running),.prefill_ready_o(prefill),
        .request_o(request),.request_sequence_o(request_sequence),
        .request_44k1_o(request_mode),.request_epoch_o(request_epoch),
        .sample_valid_i(sample_valid && permit_reply),.sample_ready_o(sample_ready),
        .sample_44k1_i(sample_mode),.sample_epoch_i(sample_epoch),
        .sample_sequence_i(sample_sequence),.sample_pcm_i(sample_pcm),
        .mclk_o(mclk),.bck_o(bck),.lrck_o(lrck),.data_o(sd),.pdn_no(pdn),.smute_o(smute),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_pcm_o(frame_pcm),
        .frame_sequence_o(frame_sequence),.frame_44k1_o(frame_mode),.frame_epoch_o(frame_epoch),
        .underrun_count_o(underruns),.rejected_sample_count_o(rejected));
    workstation_pcm_frame_bridge dut(
        .reset_ni(global_reset_n),.serial_clk_i(serial_clk),.compute_clk_i(compute_clk),
        .serial_reset_ni(serial_reset_n),.serial_quiet_i(serial_quiet),.quiesce_i(quiesce),
        .request_i(request),.request_44k1_i(request_mode),.request_epoch_i(request_epoch),
        .request_sequence_i(request_sequence),.request_ready_o(bridge_ready),
        .sample_valid_o(sample_valid),.sample_ready_i(sample_ready && permit_reply),
        .sample_44k1_o(sample_mode),.sample_epoch_o(sample_epoch),
        .sample_sequence_o(sample_sequence),.sample_pcm_o(sample_pcm),
        .render_ready_i(render_ready),.render_done_i(model_done || inject_done),
        .rendered_pcm_i(model_pcm),.render_request_o(render_request),
        .render_44k1_o(render_mode),.render_epoch_o(render_epoch),.render_sequence_o(render_sequence),
        .render_busy_o(render_busy),.quiescent_o(bridge_quiet),
        .request_drop_count_o(request_drops),.return_discard_count_o(return_discards),
        .cancelled_request_count_o(cancel_requests),.cancelled_render_count_o(cancel_renders),
        .unexpected_render_count_o(unexpected));

    function automatic [31:0] pcm(input [31:0] seq,input [31:0] ep,input bit rate);
        pcm={16'h9137 ^ ep[15:0] ^ seq[15:0],16'h35c2 ^ ep[15:0] ^ seq[15:0] ^ {15'd0,rate}};
    endfunction
    integer accepted=0,starts=0,completed=0,delivered=0,request_pulses=0;
    reg [64:0] accepted_tags[0:8191];
    realtime accepted_at[0:8191];
    integer accepted_read=0;
    reg model_busy=0;
    integer countdown=0,normal_delay=1400,slow_sequence=-1,slow_delay=3600;
    reg [64:0] active_tag=0;
    integer compute_cycles=0,last_start_cycle=0,min_start_gap=1000000;
    integer model_max_cycles=0;
    realtime max_request_to_sample_ns=0,previous_frame_at=0;
    reg measure_normal=0,request_was_pending=0,reply_was_stalled=0;
    reg [64:0] prior_request;
    reg [96:0] prior_reply;
    integer sample_index;
    always @(posedge serial_clk) if(global_reset_n) begin
        if(request_was_pending && dut.request_toggle!=dut.request_ack_sync[1] &&
           dut.held_request!==prior_request) $fatal(1,"unacknowledged request payload changed");
        request_was_pending=dut.request_toggle!=dut.request_ack_sync[1];
        prior_request=dut.held_request;
        if(reply_was_stalled && sample_valid && dut.held_reply!==prior_reply)
            $fatal(1,"stalled reply payload changed");
        reply_was_stalled=sample_valid && !(sample_ready && permit_reply);
        prior_reply=dut.held_reply;
        if(request) begin
            request_pulses=request_pulses+1;
            if(bridge_ready) begin
                accepted_tags[accepted]={request_mode,request_epoch,request_sequence};
                accepted_at[accepted]=$realtime;
                accepted=accepted+1;
            end
        end
        if(sample_valid && sample_ready && permit_reply) begin
            delivered=delivered+1;
            if(measure_normal) begin
                sample_index=0;
                while(sample_index<accepted && accepted_tags[sample_index]!=={sample_mode,sample_epoch,sample_sequence})
                    sample_index=sample_index+1;
                if(sample_index==accepted) $fatal(1,"returned tag never accepted");
                if($realtime-accepted_at[sample_index]>max_request_to_sample_ns)
                    max_request_to_sample_ns=$realtime-accepted_at[sample_index];
                if($realtime-accepted_at[sample_index]>serial_half*2*(mode ? 384 : 256))
                    $fatal(1,"bounded normal reply exceeded one physical frame");
            end
        end
    end
    always @(posedge compute_clk) compute_cycles=compute_cycles+1;
    // Core model retains the identity for the entire render, independently of
    // serial reset/clock stoppage. Done is a single compute-domain pulse.
    always @(negedge compute_clk) begin
        model_done=0;
        if(render_request) begin
            if(model_busy) $fatal(1,"render overlap");
            if(accepted_read>=accepted ||
               accepted_tags[accepted_read]!=={render_mode,render_epoch,render_sequence})
                $fatal(1,"render did not preserve accepted request identity");
            accepted_read=accepted_read+1;
            if(last_start_cycle>0 && compute_cycles-last_start_cycle<min_start_gap)
                min_start_gap=compute_cycles-last_start_cycle;
            last_start_cycle=compute_cycles;
            starts=starts+1; model_busy=1;
            active_tag={render_mode,render_epoch,render_sequence};
            countdown=render_sequence==32'(slow_sequence) ? slow_delay : normal_delay+integer'(render_sequence%17);
            if(countdown>model_max_cycles) model_max_cycles=countdown;
        end else if(model_busy) begin
            if({render_mode,render_epoch,render_sequence}!==active_tag)
                $fatal(1,"inflight render identity changed");
            if(countdown>1) countdown=countdown-1;
            else begin
                model_pcm=pcm(active_tag[31:0],active_tag[63:32],active_tag[64]);
                model_done=1; model_busy=0; countdown=0; completed=completed+1;
            end
        end
    end

    integer serial_position=0,checked=0,good_frames=0,error_frames=0;
    reg [31:0] decoded=0,last_decoded=0;
    reg allow_errors=0;
    always @(negedge serial_reset_n) begin
        serial_position=0; checked=0; decoded=0; last_decoded=0;
    end
    always @(posedge bck) begin
        #0.1;
        if(serial_reset_n) begin
            if(lrck !== (serial_position>=32)) $fatal(1,"LRCK slot mismatch");
            if(serial_position>=1 && serial_position<=16) decoded[32-serial_position]=sd;
            else if(serial_position>=33 && serial_position<=48) decoded[48-serial_position]=sd;
            else if(sd!==0) $fatal(1,"nonzero I2S delay/padding");
            if(serial_position==63) begin
                last_decoded=decoded; serial_position=0; decoded=0;
            end else serial_position=serial_position+1;
        end
    end
    always @(posedge serial_clk) begin
        #0.2;
        if(serial_reset_n && frame_valid) begin
            if(frame_epoch!==epoch || frame_mode!==mode || frame_sequence!==32'(checked))
                $fatal(1,"completed frame identity duplicated/skipped");
            if(frame_pcm!==last_decoded) $fatal(1,"physical I2S differs from completed frame");
            if(frame_error) begin
                if(!allow_errors || frame_pcm!==0) $fatal(1,"hidden/unexpected underrun");
                error_frames=error_frames+1;
            end else begin
                if(frame_pcm!==pcm(frame_sequence,epoch,mode)) $fatal(1,"wrong PCM for completed identity");
                good_frames=good_frames+1;
            end
            if(measure_normal && previous_frame_at!=0 &&
               ($realtime-previous_frame_at<serial_half*2*(mode ? 384 : 256)-0.01 ||
                $realtime-previous_frame_at>serial_half*2*(mode ? 384 : 256)+0.01))
                $fatal(1,"normal physical frame schedule drifted");
            previous_frame_at=$realtime;
            checked=checked+1;
        end
    end
    task automatic ledger;
        begin
            if(!bridge_quiet || model_busy || render_busy) $fatal(1,"ledger checked before drain");
            if(accepted!=starts+cancel_requests || starts!=completed ||
               completed!=delivered+return_discards+cancel_renders)
                $fatal(1,"ledger mismatch accepted=%0d starts=%0d complete=%0d delivered=%0d cancelreq=%0d cancelrender=%0d discard=%0d",
                       accepted,starts,completed,delivered,cancel_requests,cancel_renders,return_discards);
            if(request_pulses!=accepted+request_drops) $fatal(1,"request drops not accounted");
            accepted_read=accepted;
        end
    endtask
    task automatic stop_stream;
        begin
            @(negedge serial_clk); quiesce=1;
            wait(serial_quiet); wait(bridge_quiet);
            repeat(5) @(negedge compute_clk);
            ledger();
            @(negedge serial_clk); serial_reset_n=0; resume_output=0;
        end
    endtask
    task automatic start_stream(input bit target,input [31:0] ep);
        begin
            if(!bridge_quiet) $fatal(1,"new stream before bridge drained");
            mode=target; epoch=ep;
            // Opposite ppm offsets and unrelated phases in the two runs.
            serial_half=(target ? 29.525983372 : 40.690104167)*(CLOCK_CASE ? 0.9998 : 1.0002);
            min_start_gap=1000000; last_start_cycle=0;
            max_request_to_sample_ns=0; previous_frame_at=0;
            repeat(5) @(negedge serial_clk);
            serial_reset_n=1; quiesce=0;
            wait(prefill); @(negedge serial_clk); resume_output=1;
        end
    endtask
    integer before_good,before_error,before_drops,before_starts,before_cancel,before_discard;
    reg [96:0] saved_reply;
    reg saved_reply_toggle;
    initial begin
        repeat(5) @(negedge compute_clk); global_reset_n=1;
        wait(bridge_quiet);
        // Under bounded normal work every output frame is new, never repeated,
        // and neither long-term clock mismatch nor phase changes create drops.
        measure_normal=1; start_stream(0,11); wait(checked>=160);
        if(underruns || rejected || request_drops) $fatal(1,"48k normal stream lost frame");
        $display("NORMAL mode=48000 clock_case=%0d frames=%0d min_render_gap_compute=%0d max_request_to_sample_ns=%0.3f physical_frame_ns=%0.3f",CLOCK_CASE,checked,min_start_gap,max_request_to_sample_ns,serial_half*512);
        stop_stream();
        start_stream(1,12); wait(checked>=160);
        if(underruns || rejected || request_drops) $fatal(1,"44k1 normal stream lost frame");
        $display("NORMAL mode=44100 clock_case=%0d frames=%0d min_render_gap_compute=%0d max_request_to_sample_ns=%0.3f physical_frame_ns=%0.3f",CLOCK_CASE,checked,min_start_gap,max_request_to_sample_ns,serial_half*768);
        stop_stream();

        // A real late render remains tagged with its old slot. Output slot
        // numbering still advances; late results are consumed/rejected.
        measure_normal=0; allow_errors=1; slow_sequence=4; before_error=error_frames;
        start_stream(0,13); wait(checked>=24);
        if(error_frames<=before_error || !rejected) $fatal(1,"deadline miss was hidden");
        if(frame_error) $fatal(1,"late-render recovery did not resume new frames");
        stop_stream(); slow_sequence=-1;

        // Hold the reply mailbox full while the real serializer keeps ticking.
        start_stream(1,14); wait(checked>=3);
        @(negedge serial_clk); permit_reply=0;
        wait(dut.reply_toggle!=dut.reply_ack_sync[1]);
        saved_reply=dut.held_reply; before_starts=starts; before_drops=request_drops;
        repeat(2300) @(negedge serial_clk);
        if(dut.held_reply!==saved_reply || starts!=before_starts || request_drops<=before_drops)
            $fatal(1,"full reply mailbox overwritten or backpressure unaccounted");
        permit_reply=1; before_good=good_frames;
        wait(good_frames>=before_good+8);
        stop_stream();

        // Core readiness can keep one request pending; later output slots are
        // counted drops/zero frames and cannot mutate the held request tag.
        start_stream(0,141); wait(checked>=3);
        @(negedge compute_clk); render_ready=0;
        wait(dut.request_pending); before_starts=starts; before_drops=request_drops;
        repeat(1100) @(negedge serial_clk);
        if(starts!=before_starts || request_drops<=before_drops)
            $fatal(1,"render-ready request backpressure was ignored");
        render_ready=1; before_good=good_frames; wait(good_frames>=before_good+8);
        stop_stream();

        // Serial quiet alone cannot approve quiescence while core work is slow.
        slow_sequence=2; slow_delay=8000;
        start_stream(0,15); wait(render_busy && render_sequence==2);
        before_cancel=cancel_renders;
        @(negedge serial_clk); quiesce=1;
        wait(serial_quiet);
        if(!model_busy || bridge_quiet) $fatal(1,"quiesce ignored in-flight render");
        wait(!model_busy); wait(bridge_quiet);
        if(cancel_renders!=before_cancel+1) $fatal(1,"old render not cancelled exactly once");
        ledger(); @(negedge serial_clk); serial_reset_n=0; resume_output=0;

        // Stop MCLK high and reset only the serializer while an old render
        // remains alive. Compute must retain the old tag and the full reply.
        slow_sequence=1; slow_delay=5000;
        start_stream(1,16); wait(render_busy && render_sequence==1);
        @(posedge serial_clk); #0.5; serial_clock_run=0; serial_reset_n=0; resume_output=0;
        before_discard=return_discards;
        wait(!model_busy); repeat(12) @(negedge compute_clk);
        if(serial_clk!==1 || bridge_quiet || dut.reply_free ||
           dut.held_reply!=={1'b1,32'd16,32'd1,pcm(1,16,1)})
            $fatal(1,"stopped source lost old reply identity");
        saved_reply=dut.held_reply; saved_reply_toggle=dut.reply_toggle;
        repeat(200) @(negedge compute_clk);
        if(dut.held_reply!==saved_reply || dut.reply_toggle!==saved_reply_toggle || bridge_quiet)
            $fatal(1,"stopped-domain handshake was erased");
        serial_clock_run=1; wait(return_discards==before_discard+1);
        @(negedge serial_clk); quiesce=1;
        wait(bridge_quiet); ledger(); slow_sequence=-1;
        start_stream(0,17); before_good=good_frames; wait(good_frames>=before_good+16);
        if(underruns || rejected) $fatal(1,"old stream response leaked into new epoch");
        stop_stream();

        // A done pulse with no render must not manufacture a reply.
        saved_reply=dut.held_reply; saved_reply_toggle=dut.reply_toggle;
        @(negedge compute_clk); inject_done=1;
        @(negedge compute_clk); inject_done=0;
        repeat(4) @(negedge compute_clk);
        if(unexpected!=1 || dut.held_reply!==saved_reply || dut.reply_toggle!==saved_reply_toggle)
            $fatal(1,"unexpected done created reply or was not counted");
        ledger();
        $display("COUNTERS accepted=%0d renders=%0d completed=%0d delivered=%0d request_drops=%0d return_discards=%0d cancel_requests=%0d cancel_renders=%0d unexpected=%0d good_frames=%0d error_frames=%0d max_model_cycles=%0d",
                 accepted,starts,completed,delivered,request_drops,return_discards,cancel_requests,cancel_renders,unexpected,good_frames,error_frames,model_max_cycles);
        $display("PASS PCM frame bridge: real dual-rate I2S, independent 76.8MHz render, exact identities/ledger, deadline/pressure recovery, quiesce drain, stopped-high/local-reset old reply, unexpected done");
        $finish;
    end
    initial begin #20000000; $fatal(1,"timeout"); end
endmodule
