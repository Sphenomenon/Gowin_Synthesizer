`timescale 1ns/1ps
module tb_workstation_audio_render_service #(parameter bit RUNTIME_ENGINES=0);
    reg clk=0,rst_n=0;
    always #6.510416 clk=!clk;
    reg request=0,rate=0,event_valid=0;
    reg [17:0] event_data=0;
    wire ready,done,error,busy,sample_ce,event_ready,reference_event_ready;
    wire signed [31:0] left,right;
    wire [127:0] held,reference_held;
    wire [31:0] deadline,overflow,note_drops,rejected_requests,unsupported,cancelled,drained,duplicates;
    wire [31:0] active,reference_active,applied,reference_applied;
    wire [9:0] panic_epoch,reference_panic;
    wire muted,reference_muted;
    wire [1:0] mode,reference_mode;
    wire [2:0] profile,effect_mask;
    wire [5:0] effect_order;
    wire [15:0] volume;
    wire dwr_valid,reference_dwr_valid,drd_ready,reference_drd_ready;
    wire [64:0] dwr_data,reference_dwr_data;
    reg marker_push=0;
    reg [64:0] memory_return=0;
    // Shorter ring delay exposes actual wet/feedback arithmetic in every
    // case. Production default remains 9600; storage timing stays unchanged.
    workstation_audio_render_service #(.ECHO_SAMPLES(32),.RUNTIME_RATE_ENABLE(RUNTIME_ENGINES)) dut(
        .clk_i(clk),.rst_ni(rst_n),.render_request_i(request),.render_44k1_i(rate),
        .render_ready_o(ready),.render_done_o(done),.render_error_o(error),
        .render_left_o(left),.render_right_o(right),.render_busy_o(busy),.sample_ce_o(sample_ce),
        .rejected_request_count_o(rejected_requests),.unsupported_rate_count_o(unsupported),
        .cancelled_response_count_o(cancelled),.drained_result_count_o(drained),
        .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
        .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(event_ready),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.held_notes_o(held),
        .applied_events_o(applied),.panic_epoch_o(panic_epoch),.panic_muted_o(muted),
        .active_mask_o(active),.mode_o(mode),.profile_o(profile),
        .deadline_miss_o(deadline),.midi_overflow_o(overflow),.note_drop_o(note_drops),
        .master_volume_o(volume),.effect_mask_o(effect_mask),.effect_order_o(effect_order),
        .delivery_duplicate_count_o(duplicates),
        .delay_mem_clk_i(clk),.delay_mem_rst_ni(rst_n),.delay_dwr_valid_o(dwr_valid),
        .delay_dwr_data_o(dwr_data),.delay_dwr_pop_i(dwr_valid),
        .delay_drd_push_i(marker_push),.delay_drd_data_i(memory_return),.delay_drd_ready_o(drd_ready));
    wire reference_valid,reference_delivery_valid;
    wire signed [31:0] reference_left,reference_right,reference_delivery_left,reference_delivery_right;
    wire [31:0] reference_duplicates;
    wire default_event_ready,default_valid,default_muted,default_dwr_valid,default_drd_ready;
    wire [127:0] default_held;
    wire [31:0] default_active,default_applied;
    wire [9:0] default_panic;
    wire [1:0] default_mode;
    wire signed [31:0] default_left,default_right;
    wire [64:0] default_dwr_data;
    wire full_rate_ready,full_applied44;
    // Current event RTL with its default scheduling must remain cycle-exact
    // to the untouched prepared reference, including cancellation phases.
    gw138k_event_workstation #(.TIMING_OPTIMIZED(1),.EXTERNAL_MASTER_VOLUME(1),.ECHO_SAMPLES(32),.RUNTIME_RATE_ENABLE(RUNTIME_ENGINES)) default_core(
        .clk_i(clk),.rst_ni(rst_n),.midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),
        .pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
        .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(default_event_ready),
        .sample_ce_i(sample_ce),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
        .sample_valid_o(default_valid),.left_o(default_left),.right_o(default_right),
        .held_notes_o(default_held),.active_mask_o(default_active),.applied_events_o(default_applied),
        .panic_epoch_o(default_panic),.panic_muted_o(default_muted),.mode_o(default_mode),
        .rate_commit_i(1'b1),.rate_44100_i(rate),.rate_ready_o(full_rate_ready),.applied_rate_44100_o(full_applied44),
        .delay_mem_clk_i(clk),.delay_mem_rst_ni(rst_n),.delay_dwr_valid_o(default_dwr_valid),
        .delay_dwr_data_o(default_dwr_data),.delay_dwr_pop_i(default_dwr_valid),
        .delay_drd_push_i(marker_push),.delay_drd_data_i(memory_return),.delay_drd_ready_o(default_drd_ready));
    // The runner gives the untouched prepared event source a test-only module
    // name; all of its real oscillator/vector/effects dependencies are shared.
    prepared_reference_event_workstation #(.TIMING_OPTIMIZED(1),.EXTERNAL_MASTER_VOLUME(1),.ECHO_SAMPLES(32)) reference_core(
        .clk_i(clk),.rst_ni(rst_n),.midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),
        .pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
        .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(reference_event_ready),
        .sample_ce_i(sample_ce),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
        .sample_valid_o(reference_valid),.left_o(reference_left),.right_o(reference_right),
        .held_notes_o(reference_held),.active_mask_o(reference_active),
        .applied_events_o(reference_applied),.panic_epoch_o(reference_panic),.panic_muted_o(reference_muted),
        .mode_o(reference_mode),.delay_mem_clk_i(clk),.delay_mem_rst_ni(rst_n),
        .delay_dwr_valid_o(reference_dwr_valid),.delay_dwr_data_o(reference_dwr_data),
        .delay_dwr_pop_i(reference_dwr_valid),.delay_drd_push_i(marker_push),
        .delay_drd_data_i(memory_return),.delay_drd_ready_o(reference_drd_ready));
    workstation_frame_delivery reference_delivery(
        .clk_i(clk),.rst_ni(rst_n),.sample_ce_i(sample_ce),.muted_i(reference_muted),
        .cancel_epoch_i(reference_panic),.render_valid_i(reference_valid),
        .left_i(reference_left),.right_i(reference_right),.reference_i(32'd0),.voices_i(reference_active),
        .valid_o(reference_delivery_valid),.left_o(reference_delivery_left),.right_o(reference_delivery_right),
        .reference_o(),.voices_o(),.duplicate_frames_o(reference_duplicates));

    integer cycles=0,phase=0,requests=0,responses=0,periodic_frames=0;
    integer accepted_at=0,max_latency=0,case_max_latency=0;
    integer normal_cases=0,cc_cases=0,lifecycle_cases=0,load_cancel_cases=0,tail_negative_cycles=0,max_tail_age=0;
    integer last_cancel_cycle=-1000;
    reg observe_cancel_tail=0;
    reg [2:0] wet_seen=0;
    reg fdn_seen=0;
    reg periodic=0,strict_cadence=0,compare_service=1,pressure_test=0,pending_rate=0;
    reg slot_pending=0,expect_pending=0,expected_valid=0;
    reg signed [31:0] expected_left,expected_right;
    reg expected_error;
    reg [9:0] previous_panic=0;
    wire old_pipeline_live;
`ifdef RUNTIME_RENDER_ENGINES_TEST
        assign old_pipeline_live=
        dut.workstation.runtime_engines.engines.oscillator.u_sine_interp.valid_s0 || dut.workstation.runtime_engines.engines.oscillator.u_sine_interp.valid_s1 ||
        dut.workstation.runtime_engines.engines.oscillator.u_sine_interp.valid_s2 || dut.workstation.runtime_engines.engines.oscillator.u_sine_interp.valid_s3 ||
        dut.workstation.runtime_engines.engines.oscillator.sine_valid_o || dut.workstation.runtime_engines.engines.oscillator.gain_product_valid ||
        dut.workstation.runtime_engines.engines.oscillator.envelope_product_valid || dut.workstation.runtime_engines.engines.oscillator.finalize_valid ||
        dut.workstation.runtime_engines.engines.oscillator.quantizer.magnitude_low_valid || dut.workstation.runtime_engines.engines.oscillator.quantizer.magnitude_valid ||
        dut.workstation.runtime_engines.engines.oscillator.quantizer.scale_low_valid || dut.workstation.runtime_engines.engines.oscillator.quantizer.scaled_valid ||
        dut.workstation.runtime_engines.engines.oscillator.quantizer.rounded_valid || dut.workstation.runtime_engines.engines.oscillator.sample_valid_o ||
        dut.workstation.runtime_engines.engines.oscillator.partial_busy || dut.workstation.runtime_engines.engines.oscillator.partial_valid || dut.workstation.runtime_engines.engines.oscillator.gain_valid;
`else
        assign old_pipeline_live=
        dut.workstation.legacy_engines.engine.u_sine_interp.valid_s0 || dut.workstation.legacy_engines.engine.u_sine_interp.valid_s1 ||
        dut.workstation.legacy_engines.engine.u_sine_interp.valid_s2 || dut.workstation.legacy_engines.engine.u_sine_interp.valid_s3 ||
        dut.workstation.legacy_engines.engine.sine_valid_o || dut.workstation.legacy_engines.engine.gain_product_valid ||
        dut.workstation.legacy_engines.engine.envelope_product_valid || dut.workstation.legacy_engines.engine.finalize_valid ||
        dut.workstation.legacy_engines.engine.quantizer.magnitude_low_valid || dut.workstation.legacy_engines.engine.quantizer.magnitude_valid ||
        dut.workstation.legacy_engines.engine.quantizer.scale_low_valid || dut.workstation.legacy_engines.engine.quantizer.scaled_valid ||
        dut.workstation.legacy_engines.engine.quantizer.rounded_valid || dut.workstation.legacy_engines.engine.sample_valid_o ||
        dut.workstation.legacy_engines.engine.partial_busy || dut.workstation.legacy_engines.engine.partial_valid || dut.workstation.legacy_engines.engine.gain_valid;
`endif
    wire unsafe_unfenced_idle=!dut.workstation.pending && !dut.workstation.frame_inflight &&
        !dut.workstation.synth_joined && !dut.workstation.vec_joined && dut.workstation.core_sample_ready &&
        dut.workstation.vec_ready && dut.workstation.fx_ready && !dut.workstation.synth_valid_o &&
        !dut.workstation.vec_valid && !dut.workstation.sample_valid_o;
    reg [63:0] delay_ring[0:4095];
    integer ring_written=0,ring_read=0,wet_returns=0;
    reg marker_pending=0;
    always @(negedge clk) begin
        cycles=cycles+1;
        if(rst_n) begin
            if(full_applied44 || (rate && full_rate_ready))$fatal(1,"full effects chain acknowledged unsupported 44.1 kHz");
            if(dut.workstation.effects.delay_stage.read_l!=0 || dut.workstation.effects.delay_stage.read_r!=0) wet_seen[0]=1;
            if(dut.workstation.effects.chorus_stage.read_l!=0 || dut.workstation.effects.chorus_stage.read_r!=0) wet_seen[1]=1;
            if(dut.workstation.effects.reverb_stage.early_l!=0 || dut.workstation.effects.reverb_stage.early_r!=0) wet_seen[2]=1;
            for(integer lane=0;lane<4;lane=lane+1)
                if(dut.workstation.effects.reverb_stage.tail[lane]!=0) fdn_seen=1;
            phase=phase==1599 ? 0 : phase+1;
            if(periodic) begin
                if(phase==1599) begin
                    if(slot_pending) $fatal(1,"request backlog exceeded one output slot");
                    slot_pending=1;periodic_frames=periodic_frames+1;
                    if(strict_cadence && !ready) $fatal(1,"normal render exceeded 1600-cycle cadence");
                end
                request=slot_pending && ready;
                if(request) slot_pending=0;
            end
            // Ordered bounded storage model through the real delay FIFOs.
            // It is a memory-side model, not DDR timing/hardware acceptance.
            marker_push=0;
            if(dwr_valid) begin
                if(dwr_data[64]) begin ring_written=0;ring_read=0;marker_pending=1;end
                else begin delay_ring[ring_written%4096]=dwr_data[63:0];ring_written=ring_written+1;end
            end
            if(drd_ready) begin
                if(marker_pending) begin marker_push=1;memory_return={1'b1,64'd0};marker_pending=0;end
                else if(ring_written>=32 && ring_read<=ring_written-32) begin
                    marker_push=1;memory_return={1'b0,delay_ring[ring_read%4096]};ring_read=ring_read+1;wet_returns=wet_returns+1;
                end
            end
            if({default_event_ready,default_held,default_active,default_applied,default_panic,default_muted,default_mode,default_dwr_valid,default_dwr_data,default_drd_ready,default_valid,default_left,default_right} !==
               {reference_event_ready,reference_held,reference_active,reference_applied,reference_panic,reference_muted,reference_mode,reference_dwr_valid,reference_dwr_data,reference_drd_ready,reference_valid,reference_left,reference_right})
                $fatal(1,"default current event RTL differs from untouched prepared reference");
            if(compare_service && strict_cadence && {event_ready,held,active,applied,panic_epoch,muted,mode,dwr_valid,dwr_data,drd_ready} !==
               {reference_event_ready,reference_held,reference_active,reference_applied,reference_panic,reference_muted,reference_mode,reference_dwr_valid,reference_dwr_data,reference_drd_ready})
                $fatal(1,"event/parameter/DDR behavior differs from prepared reference");
            if(panic_epoch!=previous_panic) begin
                last_cancel_cycle=cycles;previous_panic=panic_epoch;
            end
            if(observe_cancel_tail && old_pipeline_live) begin
                if(cycles-last_cancel_cycle>max_tail_age) max_tail_age=cycles-last_cancel_cycle;
                if(unsafe_unfenced_idle) tail_negative_cycles=tail_negative_cycles+1;
                if(dut.workstation.render_idle_o) $fatal(1,"cancel fence claimed idle with live old pipeline");
                if(cycles-last_cancel_cycle>=40) $fatal(1,"old valid tail exceeded derived cancellation fence");
            end
            if(deadline || overflow || note_drops || duplicates || reference_duplicates)
                $fatal(1,"render health failure d=%0d o=%0d n=%0d dup=%0d",deadline,overflow,note_drops,duplicates);
        end
    end
    always @(posedge clk) begin
        if(rst_n) begin
            if(dut.workstation.panic_accept) observe_cancel_tail<=1;
            else if(dut.workstation.core_ce ||
                    (dut.workstation.core_event_valid && dut.workstation.core_event_ready)) observe_cancel_tail<=0;
            expected_valid=0;
            if(request && ready) begin
                if(expect_pending) $fatal(1,"accepted second request before response");
                requests=requests+1;accepted_at=cycles;expect_pending=1;pending_rate=rate;
                if(rate && !pressure_test) begin
                    expected_valid=1;expected_left=0;expected_right=0;expected_error=1;
                    expect_pending=0;
                end
            end
            if(!pressure_test && expect_pending && reference_delivery_valid) begin
                expected_valid=1;expected_left=reference_delivery_left;expected_right=reference_delivery_right;
                expected_error=reference_muted;expect_pending=0;
            end
            #0.1;
            if(!pressure_test && done!==expected_valid) $fatal(1,"missing/extra render response");
            if(done) begin
                responses=responses+1;
                if(pressure_test) begin
                    if(!expect_pending || cycles-accepted_at>=1600)
                        $fatal(1,"pressure response missing request or exceeded output slot");
                    expect_pending=0;
                    if(pending_rate ? (!error || left!=0 || right!=0) : error)
                        $fatal(1,"pressure/unsupported response had wrong error identity");
                end else if(left!==expected_left || right!==expected_right || error!==expected_error)
                    $fatal(1,"render response differs from guarded prepared engine %h %h vs %h %h error=%b exp=%b",left,right,expected_left,expected_right,error,expected_error);
                if(cycles-accepted_at>max_latency) max_latency=cycles-accepted_at;
                if(cycles-accepted_at>case_max_latency) case_max_latency=cycles-accepted_at;
            end
        end
    end
    task automatic send(input integer kind,address,value);
        begin
            @(negedge clk);event_data={4'(kind),7'(address),7'(value)};event_valid=1;
            do @(posedge clk);while(!event_ready);
            @(negedge clk);event_valid=0;
            repeat(3) @(negedge clk);
        end
    endtask
    task automatic frames(input integer count);
        integer target;
        begin target=periodic_frames+count;wait(periodic_frames>=target);@(negedge clk);end
    endtask
    task automatic configure(input integer source,input integer timbre);
        begin
            send(2,120,0);wait(ready);
            send(2,90,0);send(2,80,source<3 ? source : 2);wait(mode==(source<3 ? source : 2));
            if(source==3) send(2,90,127);
            case(timbre)
                0:send(3,16,0); 1:send(3,40,0); 2:send(3,56,0); 3:send(3,8,0); 4:send(3,0,0);
            endcase
            for(integer n=0;n<(source==3 ? 8 : 32);n=n+1) send(1,48+n,96);
            frames(3);
            if(profile!=3'(timbre) || held==0 || active==0) $fatal(1,"configuration did not create real voices");
        end
    endtask
    task automatic offer;
        begin wait(ready);@(negedge clk);request=1;@(negedge clk);request=0;end
    endtask
    integer orders[0:5];
    integer phase_limit=1600;
    initial begin
        if($value$plusargs("PHASES=%d",phase_limit)) begin end
        if(phase_limit<1 || phase_limit>1600) $fatal(1,"invalid phase coverage");
        orders[0]=6'b10_01_00;orders[1]=6'b01_10_00;orders[2]=6'b10_00_01;
        orders[3]=6'b00_10_01;orders[4]=6'b01_00_10;orders[5]=6'b00_01_10;
        repeat(8) @(negedge clk);rst_n=1;wait(ready);periodic=1;
        // Real 32-voice A/B/C and eight-voice vector path, five timbres,
        // all eight effect masks and all six effect orders at legacy cadence.
        for(integer source=0;source<4;source=source+1) begin
            for(integer timbre=0;timbre<5;timbre=timbre+1) begin
                strict_cadence=0;configure(source,timbre);case_max_latency=0;strict_cadence=1;
                for(integer mask=0;mask<8;mask=mask+1) begin
                    send(2,81,mask);
                    for(integer order_index=0;order_index<6;order_index=order_index+1) begin
                        send(2,84,orders[order_index]&3);send(2,85,(orders[order_index]>>2)&3);send(2,86,(orders[order_index]>>4)&3);
                        frames(4);normal_cases=normal_cases+1;
                    end
                end
                $display("NORMAL source=%0d timbre=%0d max_latency_compute_cycles=%0d",source,timbre,case_max_latency);
            end
        end
        // Fill every original chorus/reverb delay, including the 2131-frame
        // FDN lane; compare real wet output and all orders after warm-up.
        strict_cadence=0;configure(2,0);send(2,81,7);strict_cadence=1;
        frames(4096);
        for(integer order_index=0;order_index<6;order_index=order_index+1) begin
            send(2,84,orders[order_index]&3);send(2,85,(orders[order_index]>>2)&3);send(2,86,(orders[order_index]>>4)&3);frames(8);
        end
        if(wet_seen!=3'b111 || !fdn_seen) $fatal(1,"real effects wet/FDN paths were not exercised");
        // Trigger every phase for each source. CC PANIC follows existing event
        // acceptance; lifecycle independently reaches the real in-flight DSP.
        strict_cadence=0;compare_service=0;
        for(integer source=0;source<4;source=source+1) begin
            configure(source,0);send(2,81,7);send(2,120,0);wait(ready);
            for(integer kind_index=0;kind_index<2;kind_index=kind_index+1) begin
                for(integer offset=0;offset<phase_limit;offset=offset+1) begin
                    send(1,60,96);frames(2);
                    wait(phase==0);repeat(offset) @(negedge clk);
                    if(kind_index==0) begin send(2,120,0);cc_cases=cc_cases+1;end
                    else begin send(15,0,0);lifecycle_cases=lifecycle_cases+1;end
                    frames(2);wait(ready);
                    if(held || active) $fatal(1,"PANIC/lifecycle did not clear actual held/voices");
                end
            end
        end
        // The loader can start its unreset 32-partial ROM pipeline on the
        // cancellation edge. Exercise that separate tail, not only rendering.
        send(2,90,0);send(2,80,2);wait(mode==2);send(2,7,63);
        for(integer timbre=0;timbre<5;timbre=timbre+1) begin
            case(timbre)
                0:send(3,16,0); 1:send(3,40,0); 2:send(3,56,0); 3:send(3,8,0); 4:send(3,0,0);
            endcase
            for(integer offset=0;offset<41;offset=offset+1) begin
                send(2,120,0);wait(dut.core_idle);send(1,60,96);
                if(offset==0 && !dut.workstation.load_busy) $fatal(1,"load-tail probe missed real loader");
                repeat(offset) @(negedge clk);send(15,0,0);wait(dut.core_idle);
                if(held || active || volume!=16'd16128 || profile!=3'(timbre))
                    $fatal(1,"load cancellation lost authoritative parameters");
                load_cancel_cases=load_cancel_cases+1;
            end
        end
        // Saturated event input still cannot outrank a registered frame.
        send(2,120,0);wait(ready);frames(2);
        for(integer n=0;n<16;n=n+1) send(1,48+n,96);
        // The opt-in cancellation scheduling can change event backpressure
        // relative to old RTL. Here assert bounded one-response/request and
        // sound/error identity; default RTL remains cycle-compared globally.
        strict_cadence=1;pressure_test=1;
        for(integer n=0;n<4096;n=n+1) send(2,(n&1) ? 1 : 11,n%128);
        strict_cadence=0;frames(2);
        periodic=0;request=0;wait(ready);
        // No autonomous production between requests, and no implicit 44.1.
        send(1,60,96);wait(ready);
        begin integer old_responses;reg [127:0] saved_held;old_responses=responses;saved_held=held;
            repeat(5000) @(negedge clk);
            if(responses!=old_responses || held!=saved_held || held==0 || volume!=16'd16128)
                $fatal(1,"idle service free-ran or reset held/parameters");end
        offer();wait(busy);@(negedge clk);rate=1;request=1;
        @(negedge clk);request=0;wait(ready);
        if(unsupported!=0) $fatal(1,"busy unsupported request consumed old 48k response");
        offer();wait(ready);rate=0;
        if(unsupported!=1) $fatal(1,"unsupported rate not explicit");
        if(rejected_requests!=1) $fatal(1,"busy request not counted exactly once: %0d",rejected_requests);
        if(requests!=responses || tail_negative_cycles==0 || max_tail_age>=40 || wet_returns==0)
            $fatal(1,"ledger or tail negative control failed req=%0d response=%0d negative=%0d tail=%0d",requests,responses,tail_negative_cycles,max_tail_age);
        $display("PASS audio_render_service48: normal_cases=%0d warm_frames=4096 warm_orders=6 cc_cases=%0d lifecycle_cases=%0d load_cancel_cases=%0d requests=%0d responses=%0d max_latency_compute_cycles=%0d unsafe_unfenced_idle_cycles=%0d max_observed_tail_age=%0d cancel_zeros=%0d drained_results=%0d unsupported=%0d rejected=%0d wet_returns=%0d wet_seen=%0d fdn_seen=%0d pressure_events=4096",
                 normal_cases,cc_cases,lifecycle_cases,load_cancel_cases,requests,responses,max_latency,tail_negative_cycles,max_tail_age,cancelled,drained,unsupported,rejected_requests,wet_returns,wet_seen,fdn_seen);
        $finish;
    end
    initial begin #3000000000;$fatal(1,"timeout");end
endmodule
