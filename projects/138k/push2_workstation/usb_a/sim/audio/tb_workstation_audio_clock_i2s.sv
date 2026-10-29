`timescale 1ns/1ps

// Standalone production clock composition + real serializer. CDC here belongs
// to this test fixture; it is not the future production render/command bridge.
module tb_workstation_audio_clock_i2s;
    reg clk50=0,rst_n=0,ref48=0,ref44=0,run48=1,run44=1;
    always #10 clk50=~clk50;
    initial begin #3.7;forever begin #40.690104;if(run48)ref48=~ref48;end end
    initial begin #17.2;forever begin #29.525699;if(run44)ref44=~ref44;end end
    reg request=0,target44=0,recover=0;
    wire selected_clk,audio_reset_n,ready,busy,fault,accepted,applied,rejected,failed;
    wire [2:0] reject_code;
    wire [3:0] fault_code,selection;
    wire quiesce50,mute50,flush50,active44,active_valid,staged44;
    wire [31:0] epoch,staged_epoch;
    wire [1:0] raw_good,raw_present;
    wire selected_good,selected_low;
    wire [11:0] edges48,edges44,edges_selected;
    wire quiet_audio,prefill_audio,running_audio,render_idle;
    // Control requests cross only as stable single-bit state. Async assertion
    // initializes quiesce=1/resume=0; release stays in the selected domain.
    reg [1:0] quiesce_sync=3,resume_sync=0;
    always @(posedge selected_clk or negedge audio_reset_n)
        if(!audio_reset_n)begin quiesce_sync<=3;resume_sync<=0;end
        else begin quiesce_sync<={quiesce_sync[0],quiesce50};resume_sync<={resume_sync[0],!mute50};end
    // Return acknowledgements are cleared in the always-on domain on each
    // flush. Quiet is combined with actual response-model drain, not tied high.
    reg [1:0] quiet_sync=0,prefill_sync=0,running_sync=0,idle_sync=0;
    always @(posedge clk50 or negedge rst_n)
        if(!rst_n)begin quiet_sync<=0;prefill_sync<=0;running_sync<=0;idle_sync<=0;end
        else if(flush50)begin quiet_sync<=0;prefill_sync<=0;running_sync<=0;idle_sync<=0;end
        else begin
            quiet_sync<={quiet_sync[0],quiet_audio};prefill_sync<={prefill_sync[0],prefill_audio};
            running_sync<={running_sync[0],running_audio};idle_sync<={idle_sync[0],render_idle};
        end
    workstation_audio_clock_domain #(
        .WINDOW_CYCLES(500),.STABLE_WINDOWS(3),.LOSS_TIMEOUT_CYCLES(25),
        .STOP_LOW_CYCLES(8),.COUNTER_BITS(12)
        // Keep the actual production 40 ms per-phase switch timeout.
    ) domain (
        .clk_50m_i(clk50),.rst_ni(rst_n),.reference_48_i(ref48),.reference_44_i(ref44),
        .request_i(request),.request_44k1_i(target44),.recover_i(recover),
        .frame_quiescent_i(quiet_sync[1] && idle_sync[1]),
        .prefill_ready_i(prefill_sync[1]),.output_running_i(running_sync[1]),
        .selected_clock_o(selected_clk),.audio_reset_no(audio_reset_n),
        .request_ready_o(ready),.busy_o(busy),.fault_o(fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(rejected),.failed_o(failed),.reject_code_o(reject_code),.fault_code_o(fault_code),
        .clock_select_o(selection),.quiesce_o(quiesce50),.dac_mute_o(mute50),.stream_flush_o(flush50),
        .active_44k1_o(active44),.active_valid_o(active_valid),.staged_44k1_o(staged44),
        .stream_epoch_o(epoch),.staged_epoch_o(staged_epoch),.source_qualified_o(raw_good),
        .source_present_o(raw_present),.selected_qualified_o(selected_good),
        .selected_stopped_low_o(selected_low),.measured_48_o(edges48),.measured_44_o(edges44),
        .measured_selected_o(edges_selected)
    );
    wire render_request,render_ready,render_mode;
    wire [31:0] render_epoch,render_sequence;
    reg sample_valid=0,sample_mode=0;
    reg [31:0] sample_epoch=0,sample_sequence=0,sample_pcm=0;
    wire mclk,bck,lrck,data,pdn,smute,frame_valid,frame_error,frame_mode;
    wire [31:0] frame_pcm,frame_sequence,frame_epoch,underruns,rejections;
    // The transaction stages its next identity while the previous physical
    // frame is still draining. Capture this stream's identity at local release.
    reg expected_configured=0,expected_mode=0;
    reg [31:0] expected_epoch=0;
    always @(posedge selected_clk or negedge audio_reset_n)
        if(!audio_reset_n)begin expected_configured<=0;expected_mode<=0;expected_epoch<=0;end
        else if(!expected_configured)begin
            expected_configured<=1;expected_mode<=staged44;expected_epoch<=staged_epoch;
        end
    // Intentionally use the real default 4/1028-frame DAC startup counts.
    workstation_i2s_serializer serializer (
        .clk_i(selected_clk),.rst_ni(audio_reset_n),.rate_44k1_i(staged44),.epoch_i(staged_epoch),
        .quiesce_i(quiesce_sync[1]),.resume_i(resume_sync[1]),
        .serial_quiescent_o(quiet_audio),.output_running_o(running_audio),.prefill_ready_o(prefill_audio),
        .request_o(render_request),.request_sequence_o(render_sequence),.request_44k1_o(render_mode),
        .request_epoch_o(render_epoch),.sample_valid_i(sample_valid),.sample_ready_o(render_ready),
        .sample_44k1_i(sample_mode),.sample_epoch_i(sample_epoch),.sample_sequence_i(sample_sequence),
        .sample_pcm_i(sample_pcm),.mclk_o(mclk),.bck_o(bck),.lrck_o(lrck),.data_o(data),
        .pdn_no(pdn),.smute_o(smute),.frame_valid_o(frame_valid),.frame_error_o(frame_error),
        .frame_pcm_o(frame_pcm),.frame_sequence_o(frame_sequence),.frame_44k1_o(frame_mode),
        .frame_epoch_o(frame_epoch),.underrun_count_o(underruns),.rejected_sample_count_o(rejections)
    );
    function automatic [31:0] pcm(input [31:0] sequence_id,input [31:0] epoch_id);
        pcm={16'h9137 ^ epoch_id[15:0] ^ sequence_id[15:0],16'h35c2 ^ epoch_id[15:0] ^ sequence_id[15:0]};
    endfunction
    integer response_delay=0,discarded_responses=0,drain_wait_cycles=0;
    reg slow_response=0;
    reg pending_mode;
    reg [31:0] pending_epoch,pending_sequence;
    assign render_idle=response_delay==0 && !sample_valid;
    always @(negedge selected_clk or negedge audio_reset_n)begin
        if(!audio_reset_n)begin sample_valid=0;response_delay=0;pending_mode=0;pending_epoch=0;pending_sequence=0;end
        else begin
            sample_valid=0;
            if(render_request && !quiesce_sync[1])begin
                if(response_delay!=0)$fatal(1,"response model overflow");
                if(render_mode!=expected_mode || render_epoch!=expected_epoch)$fatal(1,"render request stale tag");
                pending_mode=render_mode;pending_epoch=render_epoch;pending_sequence=render_sequence;
                response_delay=slow_response ? 512 : 8+integer'(render_sequence%5);
            end else if(response_delay>1)response_delay=response_delay-1;
            else if(response_delay==1)begin
                if(quiesce_sync[1])begin
                    // This fixture models a renderer that cannot cancel: let
                    // its entire latency elapse, then discard the old result.
                    // Serial ACK alone must not release the transaction.
                    response_delay=0;discarded_responses=discarded_responses+1;
                end else if(render_ready)begin
                    sample_valid=1;sample_mode=pending_mode;sample_epoch=pending_epoch;
                    sample_sequence=pending_sequence;sample_pcm=pcm(pending_sequence,pending_epoch);response_delay=0;
                end
            end
        end
    end
    integer serial_position=0,current_frames=0,total_frames=0,mclk_edges=0,last_bck_edge=0,last_lrck_edge=0;
    reg [31:0] decoded=0,last_decoded=0;
    always @(posedge selected_clk or negedge audio_reset_n)
        if(!audio_reset_n)mclk_edges=0;else mclk_edges=mclk_edges+1;
    always @(posedge bck or negedge audio_reset_n)begin
        if(!audio_reset_n)begin serial_position=0;decoded=0;last_decoded=0;last_bck_edge=0;end
        else begin
            #0.1;
            if(last_bck_edge!=0 && mclk_edges-last_bck_edge!=(expected_mode ? 6 : 4))$fatal(1,"BCK divider");
            last_bck_edge=mclk_edges;
            if(lrck!==(serial_position>=32))$fatal(1,"I2S LRCK slot %0d",serial_position);
            if(serial_position>=1 && serial_position<=16)decoded[32-serial_position]=data;
            else if(serial_position>=33 && serial_position<=48)decoded[48-serial_position]=data;
            else if(data!==0)$fatal(1,"I2S delay/padding");
            if(serial_position==63)begin last_decoded=decoded;decoded=0;serial_position=0;end
            else serial_position=serial_position+1;
        end
    end
    always @(posedge lrck or negedge audio_reset_n)begin
        if(!audio_reset_n)last_lrck_edge=0;
        else begin
            #0.1;
            if(last_lrck_edge!=0 && mclk_edges-last_lrck_edge!=(expected_mode ? 384 : 256))$fatal(1,"LRCK frame divider");
            last_lrck_edge=mclk_edges;
        end
    end
    always @(posedge selected_clk or negedge audio_reset_n)begin
        if(!audio_reset_n)current_frames=0;
        else begin
            #0.2;
            if(frame_valid)begin
                if(frame_mode!=expected_mode || frame_epoch!=expected_epoch || frame_sequence!=32'(current_frames))
                    $fatal(1,"completed frame identity");
                if(frame_error || frame_pcm!=pcm(frame_sequence,frame_epoch) || frame_pcm!=last_decoded)
                    $fatal(1,"completed tap/physical PCM mismatch");
                current_frames=current_frames+1;total_frames=total_frames+1;
            end
        end
    end
    integer previous_state=0,prefill_count=0;
    realtime prefill_start=0;
    always @(negedge clk50)begin
        if(rst_n)begin
            if(domain.transaction.state==7 && previous_state!=7)prefill_start=$realtime;
            if(domain.transaction.state==9 && previous_state==7)begin
                if($realtime-prefill_start<20000000 || $realtime-prefill_start>=40000000)
                    $fatal(1,"real 1028-frame startup outside 20..40ms: %0.3f",$realtime-prefill_start);
                prefill_count=prefill_count+1;
                $display("PREFILL actual rate44=%0d epoch=%0d ns=%0.3f timeout_ns=40000000",staged44,staged_epoch,$realtime-prefill_start);
            end
            previous_state=domain.transaction.state;
            if(applied && (!running_sync[1] || !active_valid))$fatal(1,"applied without real complete-frame output ack");
            if(fault && (!mute50 || audio_reset_n))$fatal(1,"fault did not isolate serializer");
            if(quiet_sync[1] && !idle_sync[1] && !flush50)begin
                if(domain.transaction.state!=2 || !audio_reset_n)
                    $fatal(1,"serial ACK bypassed in-flight response drain");
                drain_wait_cycles=drain_wait_cycles+1;
            end
        end
    end
    task tick;begin @(posedge clk50);#1;end endtask
    task ticks(input integer n);begin repeat(n)tick();end endtask
    task wait_ready(input bit rate44,input integer expected_epoch);
        begin
            while(!ready && !fault)tick();
            if(fault || active44!=rate44 || epoch!=expected_epoch || !running_sync[1] || current_frames<1)
                $fatal(1,"real output ready failed fault=%0d epoch=%0d frames=%0d",fault_code,epoch,current_frames);
            wait(current_frames>=8);
            if(underruns || rejections || smute || !pdn)$fatal(1,"real playing diagnostics");
        end
    endtask
    task switch_rate(input bit rate44,input integer expected_epoch);
        begin
            // Deliberately ask inside a nonzero sample, never at a frame ack.
            // Give the pending old render longer than a full serial frame.
            slow_response=1;wait(response_delay>400);slow_response=0;
            wait(serial_position==8);
            @(negedge clk50);target44=rate44;request=1;tick();request=0;
            if(!accepted || quiet_sync[1])$fatal(1,"switch acceptance/current frame");
            wait_ready(rate44,expected_epoch);
        end
    endtask
    integer n;
    initial begin
        ticks(5);rst_n=1;
        wait_ready(0,0);
        switch_rate(1,1);
        switch_rate(0,2);
        // The reference stops high during real playback; no output-clock edge
        // is needed for reference-domain qualification loss/reset assertion.
        wait(ref48===1'b1);run48=0;n=0;
        while(!fault && n<40)begin tick();n=n+1;end
        if(!fault || fault_code!=6 || epoch!=2 || audio_reset_n)$fatal(1,"real-playback missing-clock isolation");
        run48=1;
        while(raw_good!=3)tick();
        @(negedge clk50);recover=1;tick();recover=0;
        wait_ready(0,3);
        if(prefill_count!=4 || total_frames<32 || discarded_responses!=2 || drain_wait_cycles<500)
            $fatal(1,"insufficient real-stream/drain coverage");
        $display("DRAIN actual completed/discarded old responses=%0d serial-quiet waiting reference_cycles=%0d",discarded_responses,drain_wait_cycles);
        $display("PASS clock+I2S actual default PDN=4/startup=1028, 48->44.1->48, real CDC frame/drain/prefill/running handshakes, tagged PCM/physical decode, lost-clock recovery; streams=%0d frames=%0d",prefill_count,total_frames);
        $finish;
    end
    initial begin #180000000;$fatal(1,"clock+I2S watchdog");end
endmodule
