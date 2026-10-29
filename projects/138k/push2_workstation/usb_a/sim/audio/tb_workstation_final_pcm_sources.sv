`timescale 1ns/1ps
module tb_workstation_final_pcm_sources;
    reg clk=0,dac_clk=0,rst=0,request=0,rate=0,tf_active=0;
    always #6.510417 clk=!clk;
    always #40.690 dac_clk=!dac_clk;
    reg [31:0] epoch=1,sequence_number=0,generation=1;
    reg event_valid=0;
    reg [17:0] event_data=0;
    wire event_ready,source_ready,source_request,source_rate,source_done,source_error;
    wire signed [31:0] source_left,source_right;
    wire [15:0] volume;
    wire [31:0] active,scope_status;
    wire [9:0] panic_epoch;
    wire [1:0] mode;
    wire ready,done,error,tf_ready,frame_rate,frame_tf;
    wire [31:0] pcm,frame_epoch,frame_seq;
    wire [15:0] gain;
    wire dwr_valid;
    wire [64:0] dwr_data;
    reg marker=0;
    reg [64:0] marker_data=0;
    always @(negedge clk)begin
        marker=0;
        if(dwr_valid && dwr_data[64])begin marker=1;marker_data=dwr_data;end
    end
    workstation_audio_render_service #(.ECHO_SAMPLES(32)) render(
        .clk_i(clk),.rst_ni(rst),.render_request_i(source_request),.render_44k1_i(source_rate),
        .render_ready_o(source_ready),.render_done_o(source_done),.render_error_o(source_error),
        .render_left_o(source_left),.render_right_o(source_right),
        .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
        .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(event_ready),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.master_volume_o(volume),.active_mask_o(active),
        .scope_status_o(scope_status),.panic_epoch_o(panic_epoch),.mode_o(mode),
        .delay_mem_clk_i(clk),.delay_mem_rst_ni(rst),.delay_dwr_valid_o(dwr_valid),.delay_dwr_data_o(dwr_data),
        .delay_dwr_pop_i(dwr_valid),.delay_drd_push_i(marker),.delay_drd_data_i(marker_data),.delay_drd_ready_o());
    reg decoder_restart=0,byte_valid=0;
    reg [7:0] byte_data=0,wave_bytes[0:8191];
    integer byte_index=0,byte_length=0,tf_consumed=0;
    wire byte_ready,header,decoder_valid,decoder_unsupported;
    wire [19:0] decoder_rate;
    wire signed [15:0] tf_left,tf_right;
    tf_wav_pcm_decoder decoder(
        .clk(clk),.rst_n(rst),.restart(decoder_restart),.in_valid(byte_valid),.in_byte(byte_data),.in_ready(byte_ready),
        .header_valid(header),.sample_rate_hz(decoder_rate),.stereo(),.bits_per_sample(),
        .pcm_valid(decoder_valid),.pcm_ready(tf_ready),.pcm_left(tf_left),.pcm_right(tf_right),.unsupported(decoder_unsupported));
    always @(negedge clk)begin
        byte_valid=0;
        if(rst && !decoder_restart && byte_index<byte_length && byte_ready)begin
            byte_valid=1;byte_data=wave_bytes[byte_index];byte_index=byte_index+1;
        end
    end
    always @(posedge clk)if(rst && tf_ready && decoder_valid)tf_consumed=tf_consumed+1;
    workstation_final_pcm_router router(
        .clk_i(clk),.rst_ni(rst),.request_i(request),.request_44k1_i(rate),.request_epoch_i(epoch),
        .request_sequence_i(sequence_number),.request_ready_o(ready),.active_44k1_i(rate),.active_epoch_i(epoch),
        .cancel_epoch_i({22'd0,panic_epoch}),.scope_enable_i(scope_status[8]),.tf_active_i(tf_active),.master_volume_i(volume),.mute_i(1'b0),
        .tf_valid_i(decoder_valid),.tf_error_i(decoder_unsupported),.tf_left_i(tf_left),.tf_right_i(tf_right),
        .tf_sample_rate_i(decoder_rate),.tf_generation_i(generation),.expected_tf_generation_i(generation),.tf_ready_o(tf_ready),
        .render_ready_i(source_ready),.render_done_i(source_done),.render_error_i(source_error),
        .render_left_i(source_left),.render_right_i(source_right),.render_request_o(source_request),.render_44k1_o(source_rate),
        .frame_valid_o(done),.frame_error_o(error),.frame_44k1_o(frame_rate),.frame_source_tf_o(frame_tf),
        .frame_epoch_o(frame_epoch),.frame_sequence_o(frame_seq),.frame_pcm_o(pcm),.frame_error_bits_o(),.frame_gain_o(gain),
        .quiescent_o(),.rejected_request_count_o(),.tf_underrun_count_o(),.rate_mismatch_count_o(),.stale_source_count_o(),
        .cancelled_frame_count_o(),.unexpected_render_count_o(),.clipped_frame_count_o());
    wire sb,sw,sd,sp,st,tb,tw,td,tp,tt,old_valid;
    wire [31:0] source_reference;
    wire [127:0] old_snapshot;
    pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1)) old_synth(
        .clk(clk),.reset_n(rst),.sample_data(source_left),.sample_right(source_right),.sample_valid(source_done && !source_error),
        .sample_tick(st),.hp_bck(sb),.hp_ws(sw),.hp_din(sd),.pa_en(sp),.underrun_count(),.frame_count(),
        .sample_revision(24'd0),.sample_nonzero_voices(active),.trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(sequence_number),.frame_trigger_reference(source_reference));
    tf_rate_pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1),.RATE_MUL(916260)) old_tf(
        .clk(clk),.reset_n(rst),.sample_data($signed({tf_left,16'd0})),.sample_right($signed({tf_right,16'd0})),
        .sample_valid(tf_ready && decoder_valid),.rate_hz(decoder_rate),.sample_tick(tt),.hp_bck(tb),.hp_ws(tw),.hp_din(td),.pa_en(tp),
        .underrun_count(),.frame_count(),.sample_revision(24'd0),.sample_nonzero_voices(32'd0),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),.sample_trigger_reference(32'd0),.frame_trigger_reference());
    workstation_output_router old_router(
        .clk_i(clk),.rst_ni(rst),.scope_enable_i(scope_status[8]),.tf_active_i(tf_active),.synth_tick_i(st),.tf_tick_i(tt),
        .synth_bck_i(sb),.synth_ws_i(sw),.synth_data_i(sd),.synth_pa_i(sp),.tf_bck_i(tb),.tf_ws_i(tw),.tf_data_i(td),.tf_pa_i(tp),
        .synth_reference_i(source_reference),.synth_voices_i(active),.synth_health_i(32'd0),
        .bck_o(),.ws_o(),.data_o(),.pa_o(),.tap_valid_o(old_valid),.tap_snapshot_o(old_snapshot));
    wire fpc_valid;
    wire [31:0] fpc_pcm;
    workstation_fpc_audio old_fpc(
        .clk_50m_i(clk),.dac_reference_clk_i(dac_clk),.audio_clk_i(clk),.rst_ni(rst),.audio_rst_ni(rst),
        .master_volume_i(volume),.sample_valid_i(old_valid),.enable_i(1'b1),.pcm_pair_i(old_snapshot[127:96]),
        .mclk_o(),.bck_o(),.lrck_o(),.data_o(),.pdn_no(),.smute_o(),.sslow_o(),.sd_o(),.slow_o(),
        .frame_clock_o(),.frame_valid_o(fpc_valid),.frame_pcm_o(fpc_pcm),.frame_sequence_o(),.mailbox_drop_count_o());
    integer frames=0,legacy_matches=0,render_matches=0,tf_matches=0,nonzero=0,max_latency=0;
    task automatic send(input integer kind,address,value);
        begin
            @(negedge clk);event_data={4'(kind),7'(address),7'(value)};event_valid=1;
            do @(posedge clk);while(!event_ready);
            @(negedge clk);event_valid=0;repeat(3)@(negedge clk);
        end
    endtask
    task automatic frame(input bit compare_legacy,input bit expect_error);
        integer n;
        reg [31:0] expected;
        begin
            @(negedge clk);while(!ready || (!tf_active && !source_ready))@(negedge clk);
            if(tf_active && !scope_status[8])wait(decoder_valid);
            request=1;@(negedge clk);request=0;n=0;
            while(!done)begin @(negedge clk);n=n+1;if(n>2000)$fatal(1,"real source render exceeded bound");end
            if(n>max_latency)max_latency=n;
            if(error!==expect_error || {frame_rate,frame_epoch,frame_seq}!=={rate,epoch,sequence_number})$fatal(1,"real source identity/error");
            if(pcm!=0)nonzero=nonzero+1;
            expected=pcm;frames=frames+1;
            if(compare_legacy)begin
                n=0;
                while(!(fpc_valid && fpc_pcm===expected && old_fpc.gain==gain))begin
                    @(negedge clk);n=n+1;if(n>12000)$fatal(1,"legacy PT/router/FPC differs seq=%0d expected=%h got=%h gain=%0d/%0d",sequence_number,expected,fpc_pcm,gain,old_fpc.gain);
                end
                legacy_matches=legacy_matches+1;if(frame_tf)tf_matches=tf_matches+1;else render_matches=render_matches+1;
            end
            @(negedge clk);sequence_number=sequence_number+1;
        end
    endtask
    task automatic load_wave(input bit rate44);
        begin
            @(negedge clk);decoder_restart=1;byte_length=0;byte_index=0;
            @(negedge clk);decoder_restart=0;
            if(rate44)$readmemh("tf44100.mem",wave_bytes);else $readmemh("tf48000.mem",wave_bytes);
            byte_length=4140;generation=generation+1;wait(header && decoder_valid);
        end
    endtask
    initial begin
        repeat(8)@(negedge clk);rst=1;load_wave(0);
        repeat(128)frame(0,0);
        // Preserve the actual old1028-frame startup and gain ramp in the
        // comparison path; no hierarchical state forcing or source patches.
        repeat(1700000)@(negedge clk);
        for(integer src=0;src<4;src=src+1)begin
            send(2,120,0);wait(source_ready);send(2,90,0);send(2,80,src<3 ? src:2);wait(mode==(src<3 ? src:2));
            if(src==3)send(2,90,127);
            send(2,81,0);send(3,16,0);
            for(integer n=0;n<(src==3 ? 8:32);n=n+1)send(1,48+n,96);
            repeat(4)frame(0,0);repeat(16)frame(1,0);
        end
        send(2,120,0);wait(source_ready);send(2,90,0);tf_active=1;
        repeat(10000)@(negedge clk);repeat(32)frame(1,0);
        // Real common CC7 changes both paths. Compare only after each
        // per-slot slew reaches its target; the final multiply occurs once.
        send(2,7,64);repeat(64)frame(0,0);repeat(120000)@(negedge clk);
        repeat(16)frame(1,0);
        if(volume!=16384 || gain!=16384)$fatal(1,"common CC7 not projected exactly once");
        rate=1;epoch=2;sequence_number=0;frame(0,1); //48k file is rejected, not consumed as44.
        load_wave(1);repeat(32)frame(0,0);
        rate=0;epoch=3;sequence_number=0;frame(0,1);
        load_wave(0);repeat(16)frame(1,0);
        if(render_matches!=64 || tf_matches!=64 || nonzero<100 || decoder_unsupported)$fatal(1,"real-source matrix incomplete");
        $display("PASS final_pcm_sources: frames=%0d legacy_matches=%0d render_matches=%0d tf_matches=%0d nonzero=%0d tf_consumed=%0d max_latency=%0d",frames,legacy_matches,render_matches,tf_matches,nonzero,tf_consumed,max_latency);
        $finish;
    end
    initial begin #100000000;$fatal(1,"timeout");end
endmodule
