`timescale 1ns/1ps
module tb_workstation_tf_frame_bridge #(
    parameter [31:0] START_GENERATION=32'd0
);
    reg source_clk=0,compute_clk=0,source_run=1,rst_n=0;
    always begin #10;if(source_run)source_clk=~source_clk;end
    always #6.510416667 compute_clk=~compute_clk;
    reg invalidate=0,quiesce=0,manual_valid=0,manual_error=0,tf_ready=1;
    reg signed [15:0] manual_left=0,manual_right=0;
    reg [19:0] manual_rate=48000;
    wire source_ready,tf_valid,tf_error,generation_valid,generation_change,media_quiet,source_quiet,pending;
    wire signed [15:0] tf_left,tf_right;
    wire [19:0] tf_rate;
    wire [31:0] source_generation,tf_generation,expected_generation,accepted,unsupported_count,error_count,stale_count,quiet_count;
    reg use_decoder=0,byte_valid=0,decoder_restart=0;
    reg [7:0] byte_data=0;
    wire byte_ready,decoder_valid,decoder_error,decoder_header;
    wire signed [15:0] decoder_left,decoder_right;
    wire [19:0] decoder_rate;
    wire [5:0] decoder_bits;
    wire decoder_stereo;
    tf_wav_pcm_decoder decoder(.clk(source_clk),.rst_n,.restart(decoder_restart),
        .in_valid(byte_valid),.in_byte(byte_data),.in_ready(byte_ready),
        .header_valid(decoder_header),.sample_rate_hz(decoder_rate),.stereo(decoder_stereo),
        .bits_per_sample(decoder_bits),.pcm_valid(decoder_valid),
        .pcm_ready(use_decoder && source_ready),.pcm_left(decoder_left),.pcm_right(decoder_right),
        .unsupported(decoder_error));
    wire source_valid=use_decoder ? decoder_valid : manual_valid;
    wire source_error=use_decoder ? decoder_error : manual_error;
    wire [19:0] source_rate=use_decoder ? decoder_rate : manual_rate;
    wire signed [15:0] source_left=use_decoder ? decoder_left : manual_left;
    wire signed [15:0] source_right=use_decoder ? decoder_right : manual_right;
    reg use_router=0,router_request=0;
    wire router_tf_ready,router_ready,router_frame_valid,router_frame_error;
    wire [31:0] router_frame_pcm,router_mismatches;
    wire [7:0] router_error_bits;
    wire consumer_ready=use_router ? router_tf_ready : tf_ready;
    workstation_tf_frame_bridge #(.FIFO_ADDRESS_BITS(2),.INITIAL_GENERATION(START_GENERATION)) dut(
        .rst_ni(rst_n),.source_clk_i(source_clk),.compute_clk_i(compute_clk),
        .invalidate_i(invalidate),.source_quiesce_i(quiesce),
        .source_valid_i(source_valid),.source_error_i(source_error),
        .source_sample_rate_i(source_rate),.source_left_i(source_left),.source_right_i(source_right),
        .source_ready_o(source_ready),.source_generation_o(source_generation),
        .source_generation_pending_o(pending),.source_quiescent_o(source_quiet),
        .source_accepted_count_o(accepted),.source_unsupported_count_o(unsupported_count),
        .source_error_count_o(error_count),.tf_valid_o(tf_valid),.tf_ready_i(consumer_ready),
        .tf_error_o(tf_error),.tf_sample_rate_o(tf_rate),.tf_left_o(tf_left),.tf_right_o(tf_right),
        .tf_generation_o(tf_generation),.expected_generation_o(expected_generation),
        .expected_generation_valid_o(generation_valid),.generation_change_o(generation_change),
        .media_quiescent_o(media_quiet),.stale_discard_count_o(stale_count),.quiesce_discard_count_o(quiet_count));
    workstation_final_pcm_router router(.clk_i(compute_clk),.rst_ni(rst_n),
        .request_i(router_request),.request_44k1_i(1'b0),.request_epoch_i(32'd1),.request_sequence_i(32'd0),
        .request_ready_o(router_ready),.active_44k1_i(1'b0),.active_epoch_i(32'd1),.cancel_epoch_i(32'd0),
        .scope_enable_i(1'b0),.tf_active_i(1'b1),.master_volume_i(16'h8000),.mute_i(1'b0),
        .tf_valid_i(tf_valid),.tf_error_i(tf_error),.tf_left_i(tf_left),.tf_right_i(tf_right),
        .tf_sample_rate_i(tf_rate),.tf_generation_i(tf_generation),.expected_tf_generation_i(expected_generation),
        .tf_ready_o(router_tf_ready),.render_ready_i(1'b1),.render_done_i(1'b0),.render_error_i(1'b0),
        .render_left_i(32'sd0),.render_right_i(32'sd0),.frame_valid_o(router_frame_valid),
        .frame_error_o(router_frame_error),.frame_pcm_o(router_frame_pcm),.frame_error_bits_o(router_error_bits),
        .rate_mismatch_count_o(router_mismatches));
    reg [84:0] expected_packets[0:4095];
    integer expected_write=0,expected_read=0,total_accepted=0,total_delivered=0;
    integer total_invalidates=0,stalled_source_cycles=0,stalled_destination_cycles=0;
    integer wav_index=0,wav_frames=0,router_mismatch_checks=0;
    reg [19:0] wav_rate=0;
    reg [31:0] wav_gold[0:7];
    reg [7:0] wav48[0:75],wav44[0:75];
    reg was_stalled=0;
    reg [84:0] stalled_packet;
    wire [84:0] output_packet={tf_generation,tf_rate,tf_error,tf_left,tf_right};
    always @(negedge rst_n)begin expected_read=expected_write;was_stalled=0;end
    always @(posedge source_clk)if(rst_n)begin
        if(invalidate)total_invalidates=total_invalidates+1;
        if(source_valid && !source_ready)stalled_source_cycles=stalled_source_cycles+1;
        if(source_valid && source_ready)begin
            expected_packets[expected_write]={source_generation,source_rate,
                source_error || (source_rate!=48000 && source_rate!=44100),
                (source_rate!=48000 && source_rate!=44100) ? 16'd0 : source_left,
                (source_rate!=48000 && source_rate!=44100) ? 16'd0 : source_right};
            expected_write=expected_write+1;total_accepted=total_accepted+1;
            if(use_decoder)begin
                if(wav_index>=8 || {decoder_left,decoder_right}!==wav_gold[wav_index] ||
                   decoder_rate!==wav_rate || decoder_error || !decoder_header || decoder_bits!=16 || !decoder_stereo)
                    $fatal(1,"actual WAV decoder mismatch index=%0d L=%h R=%h rate=%0d",wav_index,decoder_left,decoder_right,decoder_rate);
                wav_index=wav_index+1;wav_frames=wav_frames+1;
            end
        end
    end
    always @(posedge compute_clk)if(rst_n)begin
        if(was_stalled && source_generation==stalled_packet[84:53] && !quiesce &&
           (!tf_valid || output_packet!==stalled_packet))
            $fatal(1,"stalled payload changed without cancellation valid=%b ready=%b got=%h held=%h generation=%h",tf_valid,consumer_ready,output_packet,stalled_packet,source_generation);
        was_stalled=tf_valid && !consumer_ready;
        if(was_stalled)begin
            stalled_packet=output_packet;
            stalled_destination_cycles=stalled_destination_cycles+1;
        end
        if(tf_valid && consumer_ready)begin
            if(!generation_valid || tf_generation!==expected_generation)$fatal(1,"stale/future packet escaped generation barrier");
            while(expected_read<expected_write && expected_packets[expected_read][84:53]!=tf_generation)
                expected_read=expected_read+1;
            if(expected_read==expected_write || output_packet!==expected_packets[expected_read])
                $fatal(1,"packet mismatch index=%0d got=%h expected=%h",expected_read,output_packet,expected_packets[expected_read]);
            expected_read=expected_read+1;total_delivered=total_delivered+1;
        end
        if(media_quiet && tf_valid)$fatal(1,"false media quiescence");
    end
    task send_frame(input [19:0] rate,input signed [15:0] left_value,right_value,input bit error);
        begin
            @(negedge source_clk);manual_rate=rate;manual_left=left_value;manual_right=right_value;
            manual_error=error;manual_valid=1;
            @(posedge source_clk);while(!source_ready)@(posedge source_clk);
            @(negedge source_clk);manual_valid=0;
        end
    endtask
    task await_delivery(input integer target);
        integer cycles;
        begin
            cycles=0;
            while(total_delivered<target)begin
                @(negedge compute_clk);cycles=cycles+1;
                if(cycles>2000)$fatal(1,"delivery timeout expected=%0d got=%0d",target,total_delivered);
            end
        end
    endtask
    task first_clear_reset(input bit stop_first_edge);
        begin
            @(negedge source_clk);rst_n=0;manual_valid=0;byte_valid=0;use_decoder=0;quiesce=0;tf_ready=1;invalidate=0;
            repeat(3)@(negedge source_clk);
            rst_n=1;invalidate=1;quiesce=stop_first_edge;
            // First post-common-reset edge, before local FIFO reset release.
            @(posedge source_clk);#1;invalidate=0;
            if(stop_first_edge)begin
                source_run=0;repeat(40)@(negedge compute_clk);
                if(!generation_valid || expected_generation!==START_GENERATION+1 || !media_quiet)
                    $fatal(1,"first clear lost when source stopped before local release");
                source_run=1;wait(source_quiet);@(negedge source_clk);quiesce=0;
            end
            repeat(25)@(negedge compute_clk);
            if(!generation_valid || expected_generation!==START_GENERATION+1 || source_generation!==START_GENERATION+1)
                $fatal(1,"first-clear/reset identity lost");
            wait(source_ready);
        end
    endtask
    task play_wav(input bit rate44);
        integer target;
        begin
            target=total_delivered+8;
            @(negedge source_clk);invalidate=1;decoder_restart=1;
            @(negedge source_clk);invalidate=0;decoder_restart=0;use_decoder=1;
            wav_index=0;wav_rate=rate44 ? 44100 : 48000;
            for(integer index=0;index<76;index=index+1)begin
                @(negedge source_clk);byte_valid=1;byte_data=rate44 ? wav44[index] : wav48[index];
                @(posedge source_clk);while(!byte_ready)@(posedge source_clk);
                @(negedge source_clk);byte_valid=0;
            end
            wait(wav_index==8);await_delivery(target);
            @(negedge source_clk);use_decoder=0;
        end
    endtask
    task cancel_and_stop(input bit stop_high,input integer invalidates,input bit request_quiet);
        reg [31:0] final_generation;
        begin
            tf_ready=0;
            for(integer index=0;index<5;index=index+1)
                send_frame(48000,16'(16'h4100+index),16'(16'hb100-index),0);
            wait(tf_valid);
            @(negedge source_clk);quiesce=request_quiet;invalidate=1;
            repeat(invalidates)@(posedge source_clk);
            #1;invalidate=0;final_generation=source_generation;
            if(stop_high)source_run=0;
            else begin @(negedge source_clk);#1;source_run=0;end
            repeat(60)@(negedge compute_clk);
            if(source_clk!==stop_high || expected_generation!==final_generation || tf_valid || media_quiet!==request_quiet)
                $fatal(1,"last cancel/quiet lost with stopped source high=%b expected=%h got=%h quiet=%b",stop_high,final_generation,expected_generation,media_quiet);
            // No source edge or new PCM was needed to publish the final cancel.
            source_run=1;
            if(request_quiet)wait(source_quiet);else wait(!pending);
            @(negedge source_clk);quiesce=0;tf_ready=1;
            wait(source_ready);
        end
    endtask
    integer target,before_accepted;
    reg [31:0] final_stale,final_quiet;
    initial begin
        $readmemh("wav48.hex",wav48);$readmemh("wav44.hex",wav44);$readmemh("wav_gold.hex",wav_gold);
        first_clear_reset(1);
        play_wav(0);play_wav(1);
        // FIFO depth4 plus one held slot; decoder must stall the sixth packet.
        tf_ready=0;before_accepted=total_accepted;target=total_delivered+12;
        fork
            begin
                for(integer index=0;index<12;index=index+1)
                    send_frame(index[0] ? 44100 : 48000,16'(16'h2100+index),16'(16'hd100-index),0);
            end
            begin
                wait(total_accepted==before_accepted+5);repeat(20)@(negedge source_clk);
                if(source_ready || total_accepted!=before_accepted+5)$fatal(1,"bounded FIFO failed to backpressure");
                tf_ready=1;
            end
        join
        await_delivery(target);
        target=total_delivered+2;
        send_frame(32000,16'sh1234,16'shfedc,0);
        send_frame(44100,16'sh7f01,16'sh80fe,1);await_delivery(target);
        if(unsupported_count!=1 || error_count!=1)$fatal(1,"rate/error accounting");
        // Actual final router intentionally does not consume a mismatched-rate
        // TF head. File policy must fail/cancel it; zero/error is not EOF.
        use_router=1;before_accepted=total_delivered;
        send_frame(32000,16'sh4321,16'shbcde,0);wait(tf_valid);
        @(negedge compute_clk);router_request=1;
        @(negedge compute_clk);router_request=0;
        wait(router_frame_valid);#1;
        if(!router_frame_error || router_frame_pcm!=0 || !(router_error_bits & 8'h04) ||
           router_mismatches!=1 || !tf_valid || total_delivered!=before_accepted)
            $fatal(1,"actual router mismatch behavior changed");
        router_mismatch_checks=1;
        @(negedge source_clk);invalidate=1;
        @(negedge source_clk);invalidate=0;
        repeat(25)@(negedge compute_clk);
        if(tf_valid)$fatal(1,"policy cancellation did not clear mismatched router head");
        use_router=0;tf_ready=1;target=total_delivered+1;
        send_frame(48000,16'sh6102,16'sh9efe,0);await_delivery(target);
        cancel_and_stop(1,7,0);target=total_delivered+1;
        send_frame(44100,16'sh5a01,16'sha50f,0);await_delivery(target);
        // A quiesce/resume without changing generation must not discard the
        // first resumed frame while compute is still observing quiesce.
        @(negedge source_clk);quiesce=1;wait(source_quiet);
        @(negedge source_clk);quiesce=0;target=total_delivered+1;
        send_frame(48000,16'sh5b01,16'sha40f,0);await_delivery(target);
        cancel_and_stop(0,3,1);target=total_delivered+1;
        send_frame(48000,16'sh6701,16'sh98ff,0);await_delivery(target);
        final_stale=stale_count;final_quiet=quiet_count;
        if(final_stale+final_quiet<10)$fatal(1,"old held/FIFO cancellation not exercised");
        // Coordinated global reset with an outstanding stalled packet and
        // another first-edge clear cannot reuse or leak its old payload.
        tf_ready=0;send_frame(48000,16'sh7777,16'sh8888,0);wait(tf_valid);
        first_clear_reset(0);target=total_delivered+1;
        send_frame(48000,16'sh7001,16'sh8ffe,0);await_delivery(target);
        if(wav_frames!=16 || stalled_source_cycles==0 || stalled_destination_cycles==0)$fatal(1,"coverage missing");
        $display("PASS tf_frame_bridge: seed=%0d accepted=%0d delivered=%0d invalidates=%0d wav_frames=%0d source_stalls=%0d destination_stalls=%0d stale=%0d quiesced=%0d router_mismatch_checks=%0d",START_GENERATION,total_accepted,total_delivered,total_invalidates,wav_frames,stalled_source_cycles,stalled_destination_cycles,final_stale,final_quiet,router_mismatch_checks);
        $finish;
    end
    initial begin #20000000;$fatal(1,"global timeout");end
endmodule
