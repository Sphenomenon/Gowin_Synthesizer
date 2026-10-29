`timescale 1ns/1ps
module tb_workstation_pcm_physical_fanout;
    reg compute_clk=0,serial_clk=0,rst=0,serial_rst=0,quiesce=1,resume_output=0,rate=0;
    always #6.510417 compute_clk=!compute_clk;
    real serial_half=40.690;
    always begin #(serial_half);serial_clk=!serial_clk;end
    reg [31:0] epoch=20;
    wire request,request_rate,sample_valid,sample_ready,sample_rate,sample_error;
    wire [31:0] request_epoch,request_seq,sample_epoch,sample_seq,sample_pcm;
    wire router_request,router_ready,router_rate,router_valid,router_error,router_frame_rate,router_tf;
    wire [31:0] router_epoch,router_seq,router_pcm,render_epoch,render_seq;
    wire render_rate,bridge_quiet,serial_quiet,running,prefill;
    wire bck,lrck,sd,frame_valid,frame_error,frame_rate;
    wire [31:0] frame_epoch,frame_seq,frame_pcm,underruns,source_errors,rejected;
    reg reply=0,reply_error=0;
    reg [31:0] reply_pcm=0;
    integer response_delay=0;
    wire tf_missing=render_seq%7==3;
    wire tf_wrong_rate=render_seq%11==5;
    workstation_final_pcm_router router(
        .clk_i(compute_clk),.rst_ni(rst),.request_i(router_request),.request_44k1_i(render_rate),
        .request_epoch_i(render_epoch),.request_sequence_i(render_seq),.request_ready_o(router_ready),
        .active_44k1_i(rate),.active_epoch_i(epoch),.cancel_epoch_i(32'd0),
        .scope_enable_i(1'b0),.tf_active_i(1'b1),.master_volume_i(16'd16384),.mute_i(1'b0),
        .tf_valid_i(!tf_missing),.tf_error_i(1'b0),.tf_left_i($signed(16'h6510^render_seq[15:0])),
        .tf_right_i($signed(16'ha987^render_seq[15:0])),
        .tf_sample_rate_i((rate^tf_wrong_rate)?20'd44100:20'd48000),
        .tf_generation_i(32'd1),.expected_tf_generation_i(32'd1),.tf_ready_o(),
        .render_ready_i(1'b0),.render_done_i(1'b0),.render_error_i(1'b0),.render_left_i(32'sd0),.render_right_i(32'sd0),
        .render_request_o(),.render_44k1_o(),.frame_valid_o(router_valid),.frame_error_o(router_error),
        .frame_44k1_o(router_frame_rate),.frame_source_tf_o(router_tf),.frame_epoch_o(router_epoch),
        .frame_sequence_o(router_seq),.frame_pcm_o(router_pcm),.frame_error_bits_o(),.frame_gain_o(),.quiescent_o(),
        .rejected_request_count_o(),.tf_underrun_count_o(),.rate_mismatch_count_o(),.stale_source_count_o(),
        .cancelled_frame_count_o(),.unexpected_render_count_o(),.clipped_frame_count_o());
    workstation_pcm_frame_bridge bridge(
        .reset_ni(rst),.serial_clk_i(serial_clk),.compute_clk_i(compute_clk),.serial_reset_ni(serial_rst),
        .serial_quiet_i(serial_quiet),.quiesce_i(quiesce),.request_i(request),.request_44k1_i(request_rate),
        .request_epoch_i(request_epoch),.request_sequence_i(request_seq),.request_ready_o(),
        .sample_valid_o(sample_valid),.sample_ready_i(sample_ready),.sample_44k1_o(sample_rate),
        .sample_epoch_o(sample_epoch),.sample_sequence_o(sample_seq),.sample_pcm_o(sample_pcm),.sample_error_o(sample_error),
        .render_ready_i(router_ready),.render_done_i(reply),.rendered_pcm_i(reply_pcm),.rendered_error_i(reply_error),
        .render_request_o(router_request),.render_44k1_o(render_rate),.render_epoch_o(render_epoch),
        .render_sequence_o(render_seq),.render_busy_o(),.quiescent_o(bridge_quiet),
        .request_drop_count_o(),.return_discard_count_o(),.cancelled_request_count_o(),
        .cancelled_render_count_o(),.unexpected_render_count_o());
    workstation_i2s_serializer #(.PDN_HOLD_FRAMES(1),.STARTUP_MUTE_FRAMES(3),.SAMPLE_ERROR_ENABLE(1)) serializer(
        .clk_i(serial_clk),.rst_ni(serial_rst),.rate_44k1_i(rate),.epoch_i(epoch),.quiesce_i(quiesce),.resume_i(resume_output),
        .serial_quiescent_o(serial_quiet),.output_running_o(running),.prefill_ready_o(prefill),
        .request_o(request),.request_sequence_o(request_seq),.request_44k1_o(request_rate),.request_epoch_o(request_epoch),
        .sample_valid_i(sample_valid),.sample_ready_o(sample_ready),.sample_44k1_i(sample_rate),
        .sample_epoch_i(sample_epoch),.sample_sequence_i(sample_seq),.sample_pcm_i(sample_pcm),.sample_error_i(sample_error),
        .mclk_o(),.bck_o(bck),.lrck_o(lrck),.data_o(sd),.pdn_no(),.smute_o(),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_pcm_o(frame_pcm),.frame_sequence_o(frame_seq),
        .frame_44k1_o(frame_rate),.frame_epoch_o(frame_epoch),.underrun_count_o(underruns),
        .rejected_sample_count_o(rejected),.source_error_count_o(source_errors));
    wire analysis_valid,record_valid,tap_error,tap_rate,stream_change,seq_gap,analysis_gap,record_fault;
    wire [31:0] tap_epoch,tap_seq,tap_pcm,analysis_drops,record_drops,seq_gaps,changes,error_frames;
    wire analysis_ready=frame_seq%3!=0,record_ready=frame_seq%5<2;
    workstation_pcm_frame_fanout fanout(
        .clk_i(serial_clk),.rst_ni(rst),.frame_valid_i(frame_valid),.frame_error_i(frame_error),.frame_44k1_i(frame_rate),
        .frame_epoch_i(frame_epoch),.frame_sequence_i(frame_seq),.frame_pcm_i(frame_pcm),
        .analysis_enable_i(1'b1),.analysis_ready_i(analysis_ready),.record_enable_i(1'b1),.record_ready_i(record_ready),
        .analysis_valid_o(analysis_valid),.record_valid_o(record_valid),.frame_error_o(tap_error),.frame_44k1_o(tap_rate),
        .frame_epoch_o(tap_epoch),.frame_sequence_o(tap_seq),.frame_pcm_o(tap_pcm),
        .stream_change_o(stream_change),.sequence_gap_o(seq_gap),.analysis_gap_o(analysis_gap),.record_fault_o(record_fault),
        .analysis_drop_count_o(analysis_drops),.record_drop_count_o(record_drops),.sequence_gap_count_o(seq_gaps),
        .stream_change_count_o(changes),.error_frame_count_o(error_frames));
    reg [31:0] expected_pcm[0:2][0:127];
    reg expected_valid[0:2][0:127];
    integer checked=0,good=0,bad=0,physical=0,serial_position=0,late=0,total_underruns=0,total_source_errors=0;
    reg [31:0] decoded=0,last_decoded=0;
    always @(negedge compute_clk)begin
        reply=0;
        if(router_valid)begin
            if(router_epoch>=20 && router_epoch<=22 && router_seq<128)begin
                expected_pcm[router_epoch-20][router_seq]=router_pcm;
                expected_valid[router_epoch-20][router_seq]=1;
            end
            reply_pcm=router_pcm;reply_error=router_error;
            if(router_seq==7)begin response_delay=1800;late=late+1;end
            else reply=1;
        end else if(response_delay>1)response_delay=response_delay-1;
        else if(response_delay==1)begin reply=1;response_delay=0;end
    end
    always @(posedge bck)begin
        #0.1;
        if(serial_rst)begin
            if(lrck!==(serial_position>=32))$fatal(1,"physical LRCK slot");
            if(serial_position>=1 && serial_position<=16)decoded[32-serial_position]=sd;
            else if(serial_position>=33 && serial_position<=48)decoded[48-serial_position]=sd;
            else if(sd!==0)$fatal(1,"physical delay/padding");
            if(serial_position==63)begin last_decoded=decoded;physical=physical+1;serial_position=0;decoded=0;end
            else serial_position=serial_position+1;
        end
    end
    always @(negedge serial_clk)if(serial_rst && frame_valid)begin
        if(last_decoded!==frame_pcm)$fatal(1,"physical PCM differs from completed frame");
        if({tap_rate,tap_epoch,tap_seq,tap_pcm,tap_error}!=={frame_rate,frame_epoch,frame_seq,frame_pcm,frame_error} ||
            !analysis_valid || !record_valid)$fatal(1,"tap changed physical identity");
        if((!analysis_ready || frame_error) && !analysis_gap)$fatal(1,"analysis hid loss/error");
        if((!record_ready || frame_error) && !record_fault)$fatal(1,"record hid loss/error");
        if(frame_error)begin if(frame_pcm)$fatal(1,"error frame not zero");bad=bad+1;end
        else begin
            if(frame_epoch<20 || frame_epoch>22 || frame_seq>=128 ||
                !expected_valid[frame_epoch-20][frame_seq] || expected_pcm[frame_epoch-20][frame_seq]!==frame_pcm)
                $fatal(1,"serializer added volume or changed source PCM");
            good=good+1;
        end
        checked=checked+1;
    end
    integer target;
    initial begin
        for(integer e=0;e<3;e=e+1)for(integer s=0;s<128;s=s+1)expected_valid[e][s]=0;
        repeat(8)@(negedge compute_clk);rst=1;
        for(integer run=0;run<3;run=run+1)begin
            rate=run==1;epoch=32'(20+run);serial_half=rate ? 29.525:40.690;
            serial_position=0;decoded=0;last_decoded=0;quiesce=0;
            // Bring the always-on bridge out of its global release/quiesce
            // synchronizers before enabling the serializer first request.
            repeat(8)@(negedge serial_clk);serial_rst=1;
            wait(prefill);@(negedge serial_clk);resume_output=1;
            wait(running);target=checked+80;wait(checked>=target);
            @(negedge serial_clk);quiesce=1;resume_output=0;
            wait(serial_quiet && bridge_quiet);repeat(3)@(negedge serial_clk);
            total_underruns=total_underruns+integer'(underruns);total_source_errors=total_source_errors+integer'(source_errors);
            serial_rst=0;repeat(8)@(negedge compute_clk);
        end
        if(good<100 || bad==0 || total_underruns==0 || total_source_errors==0 || analysis_drops==0 || record_drops==0 || changes!=3 || seq_gaps!=0)
            $fatal(1,"incomplete physical fanout coverage");
        $display("PASS physical_pcm_fanout: physical=%0d checked=%0d good=%0d errors=%0d late=%0d underruns=%0d source_errors=%0d analysis_drops=%0d record_drops=%0d epochs=%0d",physical,checked,good,bad,late,total_underruns,total_source_errors,analysis_drops,record_drops,changes);
        $finish;
    end
    initial begin #30000000;$fatal(1,"timeout checked=%0d epoch=%0d prefill=%b running=%b quiet=%b/%b bridge_busy=%b req=%b quiesce=%b replies=%0d",checked,epoch,prefill,running,serial_quiet,bridge_quiet,bridge.render_busy_o,request,quiesce,response_delay);end
endmodule
