`timescale 1ns/1ps
module tb_workstation_i2s_serializer;
    reg clk=0, rst_n=0, mode=0;
    reg [31:0] epoch=7;
    // Quantized to this simulator's 1 ps resolution (under 11 ppm error).
    real half_period=40.690;
    always begin #(half_period); clk=!clk; end
    reg quiesce=1, resume_output=0;
    wire quiet, running, prefill, request, request_mode, ready;
    wire [31:0] request_epoch, request_seq;
    reg valid=0, sample_mode=0;
    reg [31:0] sample_epoch=0, sample_seq=0, sample_pcm=0;
    wire mclk,bck,lrck,sd,pdn,smute,frame_valid,frame_error,frame_mode;
    wire [31:0] frame_pcm,frame_seq,frame_epoch,underruns,rejected;
    workstation_i2s_serializer #(.PDN_HOLD_FRAMES(1),.STARTUP_MUTE_FRAMES(3)) dut(
        .clk_i(clk),.rst_ni(rst_n),.rate_44k1_i(mode),.epoch_i(epoch),
        .quiesce_i(quiesce),.resume_i(resume_output),
        .serial_quiescent_o(quiet),.output_running_o(running),.prefill_ready_o(prefill),
        .request_o(request),.request_sequence_o(request_seq),.request_44k1_o(request_mode),
        .request_epoch_o(request_epoch),.sample_valid_i(valid),.sample_ready_o(ready),
        .sample_44k1_i(sample_mode),.sample_epoch_i(sample_epoch),
        .sample_sequence_i(sample_seq),.sample_pcm_i(sample_pcm),
        .mclk_o(mclk),.bck_o(bck),.lrck_o(lrck),.data_o(sd),.pdn_no(pdn),.smute_o(smute),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_pcm_o(frame_pcm),
        .frame_sequence_o(frame_seq),.frame_44k1_o(frame_mode),.frame_epoch_o(frame_epoch),
        .underrun_count_o(underruns),.rejected_sample_count_o(rejected));

    function automatic [31:0] pcm(input [31:0] seq,input [31:0] ep);
        pcm={16'h9137 ^ ep[15:0] ^ seq[15:0],16'h35c2 ^ ep[15:0] ^ seq[15:0]};
    endfunction

    integer response_delay=0;
    reg [31:0] pending_seq;
    reg bad_sent=0;
    // Real bounded renderer response model. Slot 3 deliberately misses its
    // deadline; slot 4 first sends an old epoch, slot 5 the wrong rate.
    always @(negedge clk) begin
        valid=0;
        if (!rst_n) begin response_delay=0; bad_sent=0; end
        else if (request) begin
            if (response_delay!=0) $fatal(1,"renderer request overlap");
            if(request_mode!==mode || request_epoch!==epoch) $fatal(1,"bad request identity");
            pending_seq=request_seq;
            response_delay=request_seq==3 ? 0 : 10+integer'(request_seq%7);
            bad_sent=0;
        end else if(response_delay>1) response_delay=response_delay-1;
        else if(response_delay==1 && ready) begin
            valid=1;
            sample_mode=mode;
            sample_epoch=epoch;
            sample_seq=pending_seq;
            sample_pcm=pcm(pending_seq,epoch);
            if(pending_seq==4 && !bad_sent) begin
                // A late slot-3 response must never fill slot 4.
                sample_seq=3; bad_sent=1; response_delay=4;
            end else if(pending_seq==5 && !bad_sent) begin
                sample_epoch=epoch-1; bad_sent=1; response_delay=4;
            end else if(pending_seq==6 && !bad_sent) begin
                sample_mode=!mode; bad_sent=1; response_delay=4;
            end else response_delay=0;
        end
    end

    integer serial_position=0, physical_frames=0, checked_frames=0;
    reg [31:0] decoded=0,last_decoded=0;
    realtime previous_bck=0,last_lrck_rise=0;
    integer bck_edges=0;
    // Decode independently at the receiving DAC edge, including delay/padding.
    always @(posedge bck) begin
        #0.1;
        if(rst_n) begin
            if(lrck !== (serial_position>=32)) $fatal(1,"LRCK slot mismatch at %0d",serial_position);
            if(serial_position>=1 && serial_position<=16) decoded[32-serial_position]=sd;
            else if(serial_position>=33 && serial_position<=48) decoded[48-serial_position]=sd;
            else if(sd!==0) $fatal(1,"nonzero I2S delay/padding at %0d",serial_position);
            if(serial_position==63) begin
                last_decoded=decoded; physical_frames=physical_frames+1;
                serial_position=0; decoded=0;
            end else serial_position=serial_position+1;
        end
    end
    always @(bck) begin
        if(rst_n && dut.configured && $time>1) begin
            if(previous_bck!=0 &&
               (($realtime-previous_bck)<(mode ? 3.0 : 2.0)*2*half_period-0.01 ||
                ($realtime-previous_bck)>(mode ? 3.0 : 2.0)*2*half_period+0.01))
                $fatal(1,"incorrect BCK half period %f",$realtime-previous_bck);
            previous_bck=$realtime;
            bck_edges=bck_edges+1;
        end
    end
    always @(posedge lrck) begin
        if(rst_n) begin
            if(last_lrck_rise!=0 &&
               (($realtime-last_lrck_rise)<(mode ? 384.0 : 256.0)*2*half_period-0.01 ||
                ($realtime-last_lrck_rise)>(mode ? 384.0 : 256.0)*2*half_period+0.01))
                $fatal(1,"incorrect frame period %f",$realtime-last_lrck_rise);
            last_lrck_rise=$realtime;
        end
    end
    always @(posedge clk) begin
        #0.2;
        if(rst_n && frame_valid) begin
            if(frame_epoch!==epoch || frame_mode!==mode) $fatal(1,"wrong completed identity");
            if(frame_seq!==32'(checked_frames)) $fatal(1,"frame sequence duplicated/skipped");
            if(frame_pcm!==last_decoded) $fatal(1,"tap differs from physical I2S %h %h",frame_pcm,last_decoded);
            if(frame_seq==3) begin
                if(!frame_error || frame_pcm!==0) $fatal(1,"underrun was hidden");
            end else if(frame_error || frame_pcm!==pcm(frame_seq,epoch)) $fatal(1,"wrong PCM/error");
            checked_frames=checked_frames+1;
        end
    end
    task automatic run_mode(input bit target,input [31:0] ep);
        integer count_before;
        begin
            rst_n=0; quiesce=1; resume_output=0;
            repeat(4) @(negedge clk);
            mode=target; epoch=ep;
            half_period=target ? 29.526 : 40.690;
            serial_position=0; physical_frames=0; checked_frames=0; decoded=0; last_decoded=0;
            previous_bck=0; last_lrck_rise=0; bck_edges=0;
            @(negedge clk); rst_n=1;
            repeat(2) @(negedge clk);
            quiesce=0;
            wait(prefill); @(negedge clk);
            if(!smute || running || !pdn) $fatal(1,"prefill/startup controls wrong");
            resume_output=1;
            wait(checked_frames>=8);
            // Quiesce deliberately within a nonzero left sample.
            wait(serial_position==8); @(negedge clk); quiesce=1;
            if(smute) $fatal(1,"quiesce cut a running frame");
            wait(quiet); @(negedge clk);
            if(!smute || running) $fatal(1,"complete-frame stop failed");
            if(underruns!==1 || rejected!==3) $fatal(1,"diagnostics wrong u=%0d r=%0d",underruns,rejected);
            count_before=checked_frames;
            repeat(target ? 900 : 600) @(negedge clk);
            if(checked_frames!=count_before) $fatal(1,"quiescent frame published");
            if(bck_edges<1000) $fatal(1,"insufficient serial coverage");
            $display("MODE %0d epoch=%0d checked=%0d physical=%0d underruns=%0d rejected=%0d",target,ep,checked_frames,physical_frames,underruns,rejected);
        end
    endtask
    initial begin
        run_mode(0,7);
        run_mode(1,8);
        run_mode(0,9);
        $display("PASS dual-rate I2S exact slots, completed tap, identity, underrun and boundary quiesce");
        $finish;
    end
    initial begin #3000000; $fatal(1,"timeout"); end
endmodule
