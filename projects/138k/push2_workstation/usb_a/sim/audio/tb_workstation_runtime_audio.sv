`timescale 1ns/1ps
module tb_workstation_runtime_audio #(
    parameter integer STARTUP_FRAMES=3, PDN_FRAMES=1,
    parameter bit PRODUCTION_CLOCKS=0
);
    reg control_clk=0,compute_clk=0,memory_clk=0,reference48=0,reference44=0;
    reg run48=1,run44=1,rst_n=0;
    always #10 control_clk=!control_clk;
    always #6.510417 compute_clk=!compute_clk;
    always #5 memory_clk=!memory_clk;
    initial begin #3.7;forever begin #40.690104;if(run48)reference48=!reference48;end end
    initial begin #17.2;forever begin #29.525699;if(run44)reference44=!reference44;end end
    reg request=0,request44=0,permit=1,recover=0,media_quiet=1;
    reg event_valid=0;
    reg [17:0] event_data=0;
    wire ready,busy,fault,accepted,applied,rejected,failed,policy_rejected;
    wire [2:0] reject_code;
    wire [3:0] fault_code,selection;
    wire rate,active_valid,quiesce,flush,dsp_fault,context_ready,event_ready,muted;
    wire [31:0] epoch,scope_status,tf_control,applied_events,options,active;
    wire [127:0] held;
    wire [9:0] panic_epoch;
    wire [5:0] voices;
    wire [1:0] mode,raw_good;
    wire [15:0] volume;
    wire [31:0] pc_overflows,deadlines,midi_overflows,note_drops;
    reg tf_active=0,tf_error=0;
    reg [19:0] tf_rate=48000;
    wire tf_ready;
    wire ddr_req,ddr_write;
    wire [28:0] ddr_address;
    wire [255:0] ddr_data,ddr_read_data;
    wire [31:0] ddr_mask;
    reg ddr_ready=1,ddr_response=0,hold_fence=0;
    wire mclk,bck,lrck,sd,pdn_n,smute;
    wire analysis_valid,record_valid,frame_valid,frame_error,frame_rate,stream_change,sequence_gap,analysis_gap,record_fault;
    wire [31:0] frame_epoch,frame_sequence,frame_pcm,analysis_drops,record_drops,underruns,source_errors,bridge_drops,bridge_discards;
    wire analysis_ready=frame_sequence%3!=0,record_ready=frame_sequence%5<2;
    workstation_runtime_audio #(
        .WINDOW_CYCLES(PRODUCTION_CLOCKS ? 50000:500),.STABLE_WINDOWS(PRODUCTION_CLOCKS ? 4:3),
        .LOSS_TIMEOUT_CYCLES(PRODUCTION_CLOCKS ? 500:25),.STOP_LOW_CYCLES(PRODUCTION_CLOCKS ? 16:8),
        .COUNTER_BITS(32),.SWITCH_TIMEOUT_CYCLES(2000000),.PDN_HOLD_FRAMES(PDN_FRAMES),.STARTUP_MUTE_FRAMES(STARTUP_FRAMES)
    ) dut(
        .rst_ni(rst_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .reference_48_i(reference48),.reference_44_i(reference44),.request_i(request),.request_44k1_i(request44),
        .switch_permit_i(permit),.recover_i(recover),.media_quiescent_i(media_quiet),.request_ready_o(ready),.busy_o(busy),
        .fault_o(fault),.accepted_o(accepted),.applied_o(applied),.rejected_o(rejected),.failed_o(failed),
        .policy_rejected_o(policy_rejected),.reject_code_o(reject_code),.fault_code_o(fault_code),.clock_select_o(selection),
        .active_44k1_o(rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),.source_qualified_o(raw_good),
        .quiesce_o(quiesce),.stream_flush_o(flush),.dsp_fault_o(dsp_fault),.context_ready_o(context_ready),
        .midi_byte_valid_i(1'b0),.pc_byte_valid_i(1'b0),.cpu_event_valid_i(event_valid),.midi_byte_i(8'd0),.pc_byte_i(8'd0),
        .cpu_event_i(event_data),.cpu_event_ready_o(event_ready),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(1'b0),
        .held_notes_o(held),.panic_epoch_o(panic_epoch),.panic_muted_o(muted),.active_mask_o(active),.active_voice_count_o(voices),
        .scope_status_o(scope_status),.tf_scope_control_o(tf_control),.applied_events_o(applied_events),.control_options_o(options),
        .mode_o(mode),.master_volume_o(volume),.tf_active_i(tf_active),.tf_valid_i(1'b1),.tf_error_i(tf_error),
        .pitch_q20_o(),.pc_overflow_o(pc_overflows),.deadline_miss_o(deadlines),.midi_overflow_o(midi_overflows),
        .note_drop_o(note_drops),.clip_o(),.synth_gain_o(),.pcm_gain_o(),.route_o(),.profile_o(),.effect_mask_o(),
        .effect_order_o(),.panel_event_valid_o(),.panel_command_o(),
        .tf_left_i(16'sd25000),.tf_right_i(-16'sd17000),.tf_sample_rate_i(tf_rate),.tf_generation_i(32'd1),
        .expected_tf_generation_i(32'd1),.tf_ready_o(tf_ready),.ddr_req_o(ddr_req),.ddr_write_o(ddr_write),
        .ddr_address_o(ddr_address),.ddr_data_o(ddr_data),.ddr_mask_o(ddr_mask),.ddr_ready_i(ddr_ready),
        .ddr_response_i(ddr_response),.ddr_read_data_i(ddr_read_data),.mclk_o(mclk),.bck_o(bck),.lrck_o(lrck),.data_o(sd),
        .pdn_no(pdn_n),.smute_o(smute),.analysis_enable_i(1'b1),.analysis_ready_i(analysis_ready),
        .record_enable_i(1'b1),.record_ready_i(record_ready),.analysis_valid_o(analysis_valid),.record_valid_o(record_valid),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_44k1_o(frame_rate),.frame_epoch_o(frame_epoch),
        .frame_sequence_o(frame_sequence),.frame_pcm_o(frame_pcm),.stream_change_o(stream_change),.sequence_gap_o(sequence_gap),
        .analysis_gap_o(analysis_gap),.record_fault_o(record_fault),.analysis_drop_count_o(analysis_drops),
        .record_drop_count_o(record_drops),.underrun_count_o(underruns),.source_error_count_o(source_errors),
        .bridge_request_drop_count_o(bridge_drops),.bridge_return_discard_count_o(bridge_discards));

    // Ordered posted-write/read owner-6 model. No replacement DSP or clock mux.
    reg [255:0] memory[0:4095],qdata[0:63],read_data=0;
    reg [28:0] qaddr[0:63];
    reg qwrite[0:63],qfence[0:63];
    integer head=0,tail=0,queued=0,memory_ticks=0,writes=0,fences=0;
    assign ddr_read_data=read_data;
    always @(posedge memory_clk)begin
        ddr_response<=0;
        if(rst_n)begin
            if(ddr_req && ddr_ready)begin
                if(queued>=64 || ddr_address<29'h0c000000 || ddr_address>=29'h0c008000 || ddr_address[2:0]!=0 || ddr_mask!=0)
                    $fatal(1,"owner6 queue/allocation/mask");
                qdata[tail]=ddr_data;qaddr[tail]=ddr_address;qwrite[tail]=ddr_write;qfence[tail]=dut.delay_dma.state==8;
                tail=(tail+1)%64;queued=queued+1;
            end
            if(queued!=0 && !(qfence[head] && hold_fence))begin
                if(memory_ticks==3)begin
                    memory_ticks=0;
                    if(qwrite[head])begin memory[12'((qaddr[head]-29'h0c000000)>>3)]=qdata[head];writes=writes+1;end
                    else begin
                        read_data<=memory[12'((qaddr[head]-29'h0c000000)>>3)];ddr_response<=1;
                        if(qfence[head])fences=fences+1;
                    end
                    head=(head+1)%64;queued=queued-1;
                end else memory_ticks=memory_ticks+1;
            end
        end
    end
    integer cycles=0,checked=0,nonzero=0,good=0,error_frames=0,first_slots=0,config_acks=0,applies=0,faults=0;
    integer max_render_clocks=0,render_started=0,max_config_clocks=0,config_started=0,max_slot_clocks=0;
    integer expected_count=0,physical_position=0;
    integer mid_frame_switches=0;
    integer loader_overlap_slots=0,pressure_events=0,pressure_noteoffs=0;
    reg [2:0] wet48=0,wet44=0;
    reg [1:0] fdn_seen=0;
    reg old_frame_guard=0,old_frame_rate;
    reg [31:0] old_frame_epoch;
    realtime last_bck_edge=0,expected_bck_half;
    realtime slot_request_time=0;
    reg [31:0] expected_pcm[0:15][0:32767],decoded=0,last_decoded=0;
    reg expected_error[0:15][0:32767],expected_valid[0:15][0:32767];
    always @(negedge compute_clk)if(rst_n)begin
        cycles=cycles+1;
        if(dut.config_valid && dut.config_ready)config_started=cycles;
        if(dut.config_applied)begin
            config_acks=config_acks+1;
            if(cycles-config_started>max_config_clocks)max_config_clocks=cycles-config_started;
        end
        if(dut.render_request && dut.service_ready)render_started=cycles;
        if(dut.service.sample_ce_o && dut.service.workstation.load_busy)loader_overlap_slots=loader_overlap_slots+1;
        if(dut.service_done && cycles-render_started>max_render_clocks)max_render_clocks=cycles-render_started;
        if(dut.service.workstation.runtime_effects.effects.delay_valid &&
           dut.service.workstation.runtime_effects.effects.delay_stage.frames>=(dut.service_rate ? 8820:9600) &&
           (dut.service.workstation.runtime_effects.effects.delay_stage.read_l!=0 || dut.service.workstation.runtime_effects.effects.delay_stage.read_r!=0))begin
            if(dut.service_rate)wet44[0]=1;else wet48[0]=1;
        end
        if(dut.service.workstation.runtime_effects.effects.chorus_valid &&
           (dut.service.workstation.runtime_effects.effects.chorus_stage.product_l!=0 || dut.service.workstation.runtime_effects.effects.chorus_stage.product_r!=0))begin
            if(dut.service_rate)wet44[1]=1;else wet48[1]=1;
        end
        if(dut.service.workstation.runtime_effects.effects.reverb_valid)begin
            if(dut.service.workstation.runtime_effects.effects.reverb_stage.early_l!=0 || dut.service.workstation.runtime_effects.effects.reverb_stage.early_r!=0)begin
                if(dut.service_rate)wet44[2]=1;else wet48[2]=1;
            end
            for(integer lane=0;lane<4;lane=lane+1)
                if(dut.service.workstation.runtime_effects.effects.reverb_stage.tail[lane]!=0)fdn_seen[dut.service_rate]=1;
        end
        if(dut.router_done)begin
            if(dut.final_pcm.frame_epoch_o>=16 || dut.final_pcm.frame_sequence_o>=32768)$fatal(1,"scoreboard capacity");
            expected_pcm[dut.final_pcm.frame_epoch_o][dut.final_pcm.frame_sequence_o]=dut.router_pcm;
            expected_error[dut.final_pcm.frame_epoch_o][dut.final_pcm.frame_sequence_o]=dut.router_error;
            expected_valid[dut.final_pcm.frame_epoch_o][dut.final_pcm.frame_sequence_o]=1;expected_count=expected_count+1;
        end
    end
    always @(negedge dut.serial_reset_n)begin physical_position=0;decoded=0;last_decoded=0;last_bck_edge=0;old_frame_guard=0;end
    always @(bck)if(dut.serial_reset_n && dut.serializer.configured)begin
        expected_bck_half=dut.serial_rate ? 177.154194:162.760416;
        if(last_bck_edge>0 && ($realtime-last_bck_edge<expected_bck_half-0.1 || $realtime-last_bck_edge>expected_bck_half+0.1))
            $fatal(1,"old frame BCK changed width during staged switch");
        last_bck_edge=$realtime;
    end
    always @(negedge mclk)if(old_frame_guard && dut.serial_reset_n &&
        ({dut.serial_rate,dut.serial_epoch,dut.serializer.request_44k1_o,dut.serializer.request_epoch_o}!==
         {old_frame_rate,old_frame_epoch,old_frame_rate,old_frame_epoch}))
        $fatal(1,"staged context modified old draining frame");
    always @(posedge dut.serial_reset_n)begin
        if(!context_ready || dut.serial_guard!=7 || !dut.bridge.serial_reset_n || dut.bridge.serial_quiesce_sync[1])
            $fatal(1,"serializer released before all-ACK/bridge ready");
    end
    always @(posedge bck)begin
        #0.1;
        if(dut.serial_reset_n)begin
            if(lrck!==(physical_position>=32))$fatal(1,"physical LRCK");
            if(physical_position>=1 && physical_position<=16)decoded[32-physical_position]=sd;
            else if(physical_position>=33 && physical_position<=48)decoded[48-physical_position]=sd;
            else if(sd!==0)$fatal(1,"I2S delay/padding");
            if(physical_position==63)begin last_decoded=decoded;decoded=0;physical_position=0;end
            else physical_position=physical_position+1;
        end
    end
    always @(negedge mclk)if(rst_n && dut.serial_reset_n)begin
        if(dut.serial_request)slot_request_time=$realtime;
        if(dut.serial_request && dut.serial_request_sequence==0)begin
            if(!dut.bridge.request_ready_o)$fatal(1,"first slot dropped by unready bridge");
            first_slots=first_slots+1;
        end
        if(frame_valid)begin
            if(frame_pcm!==last_decoded || !analysis_valid || !record_valid || sequence_gap)
                $fatal(1,"physical PCM/tap identity or sequence gap");
            if(frame_epoch>=16 || frame_sequence>=32768 || !expected_valid[frame_epoch][frame_sequence] ||
               frame_pcm!==expected_pcm[frame_epoch][frame_sequence] || frame_error!==expected_error[frame_epoch][frame_sequence])
                $fatal(1,"physical frame differs from single final PCM owner epoch=%0d sequence=%0d",frame_epoch,frame_sequence);
            if((!analysis_ready || frame_error) && !analysis_gap)$fatal(1,"analysis hid loss/error");
            if((!record_ready || frame_error) && !record_fault)$fatal(1,"record hid loss/error");
            if(frame_error)begin if(frame_pcm!=0)$fatal(1,"nonzero error frame");error_frames=error_frames+1;end
            else begin good=good+1;if(frame_pcm!=0)nonzero=nonzero+1;end
            checked=checked+1;
        end
    end
    always @(posedge mclk)if(dut.serial_reset_n && dut.sample_valid && dut.sample_ready && slot_request_time>0)begin
        if(integer'($ceil(($realtime-slot_request_time)/13.020834))>max_slot_clocks)
            max_slot_clocks=integer'($ceil(($realtime-slot_request_time)/13.020834));
    end
    always @(negedge control_clk)if(rst_n)begin
        if(applied)begin
            if(!context_ready || !active_valid || !dut.serial_running || dut.service_rate!=rate)
                $fatal(1,"applied before all-ACK/real physical running");
            applies=applies+1;
        end
        if(failed)faults=faults+1;
        if(fault && (!smute || pdn_n || active_valid))$fatal(1,"fault did not isolate pins/public validity");
        if(bridge_drops!=0)$fatal(1,"composition dropped a serializer request");
        if(pc_overflows!=0 || deadlines!=0 || midi_overflows!=0 || note_drops!=0)$fatal(1,"event/render health counter");
    end
    task tick;begin @(posedge control_clk);#1;end endtask
    task wait_ready;
        integer n;
        begin
            n=0;while(!ready && !fault && n<2100000)begin tick();n=n+1;end
            if(!ready || fault)$fatal(1,"ready missing clockfault=%0d dsp=%b clockstate=%0d config=%0d servicequiet=%b",fault_code,dsp_fault,dut.clocks.transaction.state,dut.config_state,dut.service_quiet);
        end
    endtask
    task send(input integer kind,address,value);
        begin
            @(negedge compute_clk);event_data={4'(kind),7'(address),7'(value)};event_valid=1;
            do @(posedge compute_clk);while(!event_ready);
            @(negedge compute_clk);event_valid=0;repeat(3)@(negedge compute_clk);
        end
    endtask
    task frames(input integer count);
        integer target;
        begin target=checked+count;wait(checked>=target);@(negedge compute_clk);end
    endtask
    task switch_rate(input bit next_rate);
        integer previous_epoch,previous_nonzero;
        reg [127:0] previous_held;
        begin
            previous_epoch=epoch;previous_held=held;previous_nonzero=nonzero;
            wait(dut.serializer.playing && dut.serializer.bit_position>=8 && dut.serializer.bit_position<=12);
            old_frame_rate=rate;old_frame_epoch=epoch;old_frame_guard=1;mid_frame_switches=mid_frame_switches+1;
            @(negedge control_clk);request44=next_rate;request=1;tick();request=0;
            if(!accepted)$fatal(1,"switch not accepted");
            wait_ready();frames(16);
            if(rate!=next_rate || epoch!=previous_epoch+1 || held!==previous_held || nonzero<=previous_nonzero)
                $fatal(1,"held-note/nonzero switch failed rate=%b epoch=%0d held=%h",rate,epoch,held);
            if(underruns!=0 || dsp_fault)$fatal(1,"healthy switch underrun/fault");
        end
    endtask
    task wait_clock_fault(input integer code);
        integer n;
        begin
            n=0;while(!fault && n<2100000)begin tick();n=n+1;end
            if(!fault || fault_code!=4'(code) || dsp_fault)$fatal(1,"wrong clock fault expected=%0d got=%0d dsp=%b",code,fault_code,dsp_fault);
        end
    endtask
    task recover_ready;
        begin
            wait(raw_good==3);@(negedge control_clk);recover=1;tick();recover=0;wait_ready();
        end
    endtask
    integer before_nonzero,before_epoch,before_errors;
    bit startup_only;
    initial begin
        startup_only=$test$plusargs("STARTUP_ONLY");
        for(integer e=0;e<16;e=e+1)for(integer s=0;s<32768;s=s+1)expected_valid[e][s]=0;
        repeat(8)@(negedge control_clk);rst_n=1;wait_ready();wait(raw_good==3);
        send(2,7,100);send(2,81,7);send(1,60,127);frames(192);
        if(!held[60] || active==0 || nonzero==0)$fatal(1,"startup real voice is silent held=%h active=%h nonzero=%0d volume=%0d mode=%0d scope=%h service=%h,%h router=%h gain=%0d muted=%b errors=%0d",held,active,nonzero,volume,mode,scope_status,dut.service_left,dut.service_right,dut.router_pcm,dut.final_pcm.applied_gain,muted,error_frames);
        if(startup_only)begin switch_rate(1);end
        else begin
            // A/B/C plus actual vector, each held through both directions.
            for(integer source=0;source<4;source=source+1)begin
                send(2,120,0);send(2,90,0);send(2,80,source<3 ? source:2);
                wait(mode==2'(source<3 ? source:2));
                if(source==3)send(2,90,127);
                // Deliberately start the real NoteOn loader just before the
                // next physical request; the public event FIFO is unchanged.
                wait(dut.serializer.playing && dut.serializer.bit_position==62);
                for(integer note=0;note<(source==3 ? 8:32);note=note+1)send(1,48+note,96);
                frames(source==2 ? 9800:192);
                for(integer step=0;step<64;step=step+1)begin
                    send(2,7,80+step%40);send(2,11,96+step%32);send(3,step[0] ? 16:40,0);
                    pressure_events=pressure_events+3;
                end
                switch_rate(1);if(source==2)frames(9000);switch_rate(0);
                for(integer note=0;note<(source==3 ? 2:8);note=note+1)begin
                    send(0,48+note,0);pressure_noteoffs=pressure_noteoffs+1;
                end
                frames(8);
            end
            send(2,120,0);send(2,90,0);send(1,60,127);frames(192);
            // External policy rejects without touching the transaction/epoch.
            before_epoch=epoch;permit=0;@(negedge control_clk);request44=1;request=1;tick();request=0;
            if(!policy_rejected || accepted || busy || epoch!=before_epoch)$fatal(1,"policy rejection modified stream");
            permit=1;frames(2);
            // TF packet mismatch is a tagged error zero, not old sample hold.
            before_errors=error_frames;tf_active=1;tf_rate=44100;frames(6);
            if(error_frames<=before_errors || tf_ready)$fatal(1,"TF rate mismatch consumed/stale output before=%0d errors=%0d tf_ready=%b scope=%h route_tf=%b rate=%b mismatch=%0d",before_errors,error_frames,tf_ready,scope_status,dut.final_pcm.frame_source_tf_o,rate,dut.final_pcm.rate_mismatch_count_o);
            tf_rate=48000;before_nonzero=nonzero;frames(8);tf_active=0;
            if(nonzero<=before_nonzero)$fatal(1,"coherent TF packet was silent");
            // Clock stops high; local reset/mute must assert without an edge.
            wait(reference48===1'b1);run48=0;wait_clock_fault(6);
            if(mclk!==1'b1 || dut.serial_reset_n || !held[60])$fatal(1,"stopped-high isolation/state");
            run48=1;recover_ready();frames(8);
            // PANIC while a real render is active and a rate switch is pending.
            wait(dut.bridge_busy);@(negedge control_clk);request44=1;request=1;tick();request=0;
            send(2,120,0);wait_ready();frames(4);
            if(held!=0 || active!=0 || !muted || !rate)$fatal(1,"PANIC/switch held cancellation");
            send(1,60,127);frames(192);
            if(!rate || !held[60] || active==0)$fatal(1,"PANIC switch real-note recovery");
            // Clock stops low and recovers the last committed rate/new epoch.
            wait(reference44===1'b0);run44=0;wait_clock_fault(6);run44=1;recover_ready();frames(8);
            // Keep an external media boundary busy: real 40-ms quiesce timeout.
            before_epoch=epoch;media_quiet=0;@(negedge control_clk);request44=0;request=1;tick();request=0;
            wait_clock_fault(1);
            if(epoch!=before_epoch || !held[60])$fatal(1,"timeout changed committed rate/held notes");
            media_quiet=1;recover_ready();frames(8);
            // A real owner6 fence timeout poisons the DSP until common reset.
            // Recovering only the clock transaction must never clear it.
            before_epoch=epoch;hold_fence=1;@(negedge control_clk);request44=!rate;request=1;tick();request=0;
            wait(dsp_fault);tick();
            if(!fault || ready || active_valid || !smute || pdn_n || dut.serial_reset_n || epoch!=before_epoch)
                $fatal(1,"DSP fence timeout did not quarantine stream");
            wait(dut.clock_fault);hold_fence=0;
            if(fault_code!=1)$fatal(1,"DSP fault quiesce timeout missing");
            @(negedge control_clk);recover=1;tick();recover=0;
            wait(!dut.clock_fault);wait(dut.clock_fault);
            if(fault_code!=5 || !dsp_fault || ready || active_valid || epoch!=before_epoch || !smute || pdn_n)
                $fatal(1,"clock recover falsely cleared sticky DSP fault");
        end
        if(first_slots<2 || config_acks<2 || max_config_clocks>=3072000 || bridge_drops!=0 || writes==0 || fences==0 || analysis_drops==0 || record_drops==0)
            $fatal(1,"integration coverage missing/budget");
        if(!startup_only && (wet48!=7 || wet44!=7 || fdn_seen!=3 || loader_overlap_slots==0 || pressure_events!=768 || pressure_noteoffs!=26))
            $fatal(1,"wet/loader/event coverage wet48=%b wet44=%b fdn=%b loader=%0d",wet48,wet44,fdn_seen,loader_overlap_slots);
        $display("PASS runtime_audio: checked=%0d good=%0d errors=%0d nonzero=%0d first_slots=%0d config_acks=%0d applies=%0d faults=%0d mid_frame_switches=%0d max_render_clocks=%0d max_slot_clocks=%0d max_config_clocks=%0d writes=%0d fences=%0d analysis_drops=%0d record_drops=%0d startup_frames=%0d epoch=%0d loader_overlap_slots=%0d pressure_events=%0d pressure_noteoffs=%0d wet48=%0d wet44=%0d fdn_seen=%0d",checked,good,error_frames,nonzero,first_slots,config_acks,applies,faults,mid_frame_switches,max_render_clocks,max_slot_clocks,max_config_clocks,writes,fences,analysis_drops,record_drops,STARTUP_FRAMES,epoch,loader_overlap_slots,pressure_events,pressure_noteoffs,wet48,wet44,fdn_seen);
        $finish;
    end
    initial begin #1000000000;$fatal(1,"runtime composition watchdog");end
endmodule
