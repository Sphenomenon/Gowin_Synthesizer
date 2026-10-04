`timescale 1ns/1ps
// Actual USB-managed audio wrapper + TF bridge/FIFO + DAC selector. The card
// decoder endpoint generates counter samples; analysis ready is a behavioral
// consumer. This checks coexistence, not CNN arithmetic or SD file decoding.
module tb_scope_tf_coexist;
    reg audio_clk=0,clk_50m=0,memory_clk=0;
    always #6.5 audio_clk=~audio_clk;
    always #10 clk_50m=~clk_50m;
    always #5 memory_clk=~memory_clk;
    reg reset_n=0,usb_valid=0;
    reg [17:0] usb_event=0;
    wire usb_ready,sample_ce,sample_valid;
    wire signed [31:0] left,right;
    wire [31:0] scope_status,active,deadline,overflow,dropped;
    wire s_bck,s_ws,s_din,s_pa,t_bck,t_ws,t_din,t_pa,t_tick;
    wire bck,ws,din,pa,tf_selected,switching,display_valid;
    wire [31:0] display_pcm;
    wire [447:0] performance;
    wire signed [31:0] tf_left,tf_right;
    wire tf_valid,tf_active,format_ready,unsupported;
    wire [19:0] rate,analysis_rate;
    wire analysis_valid;
    wire signed [15:0] analysis_left,analysis_right;
    reg consumer_run=1;
    reg [7:0] consumer_phase=0;
    wire analysis_ready=consumer_run && consumer_phase[4:0]!=0 && consumer_phase[4:0]!=1;
    integer accepted=0,expected=0,active_frames=0,muted_frames=0,xy_frames=0;
    integer previous_accepted,previous_frames,n;
    reg check_dry=0,check_muted=0;
    gw138k_usb_controlled_audio managed(
        .usb_event_valid(usb_valid),.usb_event_data(usb_event),.usb_event_ready(usb_ready),
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(reset_n),.midi_rx_i(1'b1),.pc_uart_rx_i(1'b1),
        .performance_words_o(performance),.pclk(clk_50m),.preset_n(reset_n),.psel(1'b0),.penable(1'b0),.pwrite(1'b0),
        .paddr(12'd0),.pwdata(32'd0),.pstrb(4'd0),.pready(),.pslverr(),.prdata(),
        .hp_bck(s_bck),.hp_ws(s_ws),.hp_din(s_din),.pa_en(s_pa),
        .sample_ce_o(sample_ce),.sample_valid_o(sample_valid),.scope_status_o(scope_status),.tf_scope_control_o(),
        .audio_left_o(left),.audio_right_o(right),.active_mask_o(active),.deadline_miss_o(deadline),
        .midi_overflow_o(overflow),.note_drop_o(dropped),.underrun_count_o(),.midi_cdc_drop_o(),
        .observation_drop_o(),.uart_error_o(),.record_drop_o(),.led_mask_o(),.score_frame_o(),
        .score_running_o(),.score_done_o(),.record_enabled_o(),
        .display_valid_o(display_valid),.display_pcm_o(display_pcm),.display_reference_o(),
        .display_voices_o(),.display_status_o(),.effect_mask_o(),.effect_order_o());
    tf_workstation_audio_bridge tf(
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(reset_n),
        .memory_clk(memory_clk),.memory_reset_n(reset_n),.memory_ready(1'b1),.restart(1'b0),.track_index(4'd0),
        .sd_miso(1'b1),.sd_cs_n(),.sd_sck(),.sd_mosi(),.sample_ce(t_tick),
        .pcm_left(tf_left),.pcm_right(tf_right),.pcm_active(tf_valid),.source_active(tf_active),
        .sample_rate_hz(rate),.format_ready(format_ready),.unsupported(unsupported),.ddr_error(),.file_size(),.track_count(),
        .playback_hold_i(1'b0),.analysis_hold_i(1'b1),.analysis_enable_i(1'b1),.analysis_pcm_ready_i(analysis_ready),
        .analysis_pcm_valid(analysis_valid),.analysis_pcm_left(analysis_left),.analysis_pcm_right(analysis_right),
        .analysis_sample_rate(analysis_rate),.ddr_valid(),.ddr_write(),.ddr_address(),.ddr_data(),
        .ddr_ready(1'b0),.ddr_response(1'b0),.ddr_response_data(256'd0));
    tf_rate_pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1),.RATE_MUL(916260)) tf_dac(
        .clk(audio_clk),.reset_n(reset_n),.sample_data(tf_left),.sample_right(tf_right),.sample_valid(tf_valid),.rate_hz(rate),
        .sample_tick(t_tick),.hp_bck(t_bck),.hp_ws(t_ws),.hp_din(t_din),.pa_en(t_pa),
        .underrun_count(),.frame_count(),.sample_revision(24'd0),.sample_nonzero_voices(32'd0),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(32'd0),.frame_trigger_reference());
    scope_dac_select output_select(.clk_i(audio_clk),.rst_ni(reset_n),.scope_enable_i(scope_status[8]),.tf_source_active_i(tf_active),
        .synth_frame_tick_i(sample_ce),.tf_frame_tick_i(t_tick),
        .synth_bck_i(s_bck),.synth_ws_i(s_ws),.synth_din_i(s_din),.synth_pa_i(s_pa),
        .tf_bck_i(t_bck),.tf_ws_i(t_ws),.tf_din_i(t_din),.tf_pa_i(t_pa),
        .hp_bck_o(bck),.hp_ws_o(ws),.hp_din_o(din),.pa_en_o(pa),.tf_selected_o(tf_selected),.switching_o(switching));
    always @(posedge clk_50m) begin
        if(reset_n) begin
            consumer_phase<=consumer_phase+1'b1;
            if(analysis_valid) begin
                if(!analysis_ready || analysis_rate!=48000)$fatal(1,"analysis ready/rate violation");
                if(analysis_left!==16'(expected) || analysis_right!==~16'(expected))
                    $fatal(1,"lost/reordered analysis sample %0d got %0d/%0d",expected,analysis_left,analysis_right);
                accepted=accepted+1;expected=expected+1;
            end
            if(display_valid && scope_status[8] && display_pcm[31:16]!=display_pcm[15:0])xy_frames=xy_frames+1;
        end
    end
    always @(negedge audio_clk) begin
        if(reset_n && sample_valid) begin
            if(check_dry) begin
                if(left!==managed.u_audio.u_workstation.held_vec_l || right!==managed.u_audio.u_workstation.held_vec_r)
                    $fatal(1,"USB wrapper final stereo differs from vector dry sample");
                if(left!=0 || right!=0)active_frames=active_frames+1;
            end
            if(check_muted) begin
                if(left!=0 || right!=0)$fatal(1,"live mute did not zero vector output");
                muted_frames=muted_frames+1;
                if(tf_selected || switching)$fatal(1,"mute fell back to TF audio");
            end
        end
    end
    task automatic event_send(input [3:0] kind,input [6:0] a,input [6:0] b);
        reg [31:0] before_count;
        integer elapsed;
        begin
            @(negedge audio_clk);before_count=performance[31:0];usb_event={kind,a,b};usb_valid=1;
            @(posedge audio_clk);while(!usb_ready)@(posedge audio_clk);
            @(negedge audio_clk);usb_valid=0;elapsed=0;
            // Ready at the wrapper means queued, not yet applied. Dispatch can
            // wait for the ongoing synthesis frame (up to 1600 audio cycles).
            while(performance[31:0]==before_count) begin
                @(negedge audio_clk);elapsed=elapsed+1;
                if(elapsed>4000)$fatal(1,"USB event never dispatched");
            end
            repeat(4)@(negedge audio_clk);
        end
    endtask
    task automatic frames(input integer count);
        begin repeat(count)@(posedge sample_ce);@(negedge audio_clk);end
    endtask
    initial begin #100000000;$fatal(1,"coexist timeout");end
    initial begin
        repeat(32)@(negedge audio_clk);reset_n=1;
        frames(600);
        if(!tf_active || !tf_selected || switching || accepted<500)$fatal(1,"TF/analysis startup");
        event_send(2,90,127);frames(5);
        if(!scope_status[8] || tf_selected || switching)$fatal(1,"scope mode did not own real DAC boundary");
        if(managed.effect_mask_audio!=0)$fatal(1,"scope default is not dry");
        previous_accepted=accepted;
        for(n=60;n<68;n=n+1)event_send(1,7'(n),50);
        check_dry=1;frames(400);
        if(scope_status[7:0]!=8'hff || active!=255 || active_frames<200)$fatal(1,"8 live vector voices");
        if(accepted-previous_accepted<350)$fatal(1,"scope mode blocked TF analysis");
        event_send(2,90,0);
        if(!scope_status[8] || !scope_status[11] || tf_selected)$fatal(1,"rejected mode switch changed DAC owner");
        event_send(2,95,127);frames(256);check_muted=1;
        previous_accepted=accepted;frames(100);
        if(accepted-previous_accepted<80 || muted_frames<50)$fatal(1,"muted scope blocked analysis");
        previous_frames=active_frames;previous_accepted=accepted;consumer_run=0;
        frames(100);
        if(accepted-previous_accepted>1 || active_frames-previous_frames!=0)$fatal(1,"analysis backpressure/mute isolation");
        consumer_run=1;check_muted=0;event_send(2,95,0);frames(256);
        if(accepted-previous_accepted<200 || left==0 && right==0)$fatal(1,"unmute/analysis resume");
        if(deadline!=0)$fatal(1,"deadline before PANIC");
        event_send(2,120,0);frames(32);
        if(active!=0 || left!=0 || right!=0 || tf_selected)$fatal(1,"PANIC must stay live silence");
        check_dry=0;event_send(2,90,0);frames(6);
        if(scope_status[8] || !tf_selected || switching)$fatal(1,"explicit exit did not restore TF monitor");
        if(deadline!=0 || overflow!=0 || dropped!=1 || xy_frames<100)$fatal(1,"deadline/status or stereo display observation deadline=%0d overflow=%0d dropped=%0d XY=%0d",deadline,overflow,dropped,xy_frames);
        $display("M coexist_deadline_misses %0d",deadline);
        $display("M coexist_analysis_samples %0d",accepted);
        $display("M coexist_vector_frames %0d",active_frames);
        $display("M coexist_muted_frames %0d",muted_frames);
        $display("M coexist_xy_observation_frames %0d",xy_frames);
        $display("PASS scope_tf_coexist actual USB event pipeline, 8 voices, dry XY, mute/PANIC priority, TF ready backpressure and sample order");
        $finish;
    end
endmodule
