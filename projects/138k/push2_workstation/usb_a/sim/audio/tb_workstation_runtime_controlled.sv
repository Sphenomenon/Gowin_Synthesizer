`timescale 1ns/1ps
module tb_workstation_runtime_controlled #(parameter bit RESERVE_ZERO_EPOCH=0,INFLIGHT_SCORE_BOUNDARY=0,CHECK_SWITCH_ASYNC=1);
    reg control_clk=0,compute_clk=0,memory_clk=0,pclk=0,reference48=0,reference44=0,rst_n=0,preset_n=0,compute_run=1;
    always #10 control_clk=!control_clk;
    always #6.510417 if(compute_run)compute_clk=!compute_clk;
    always #5 memory_clk=!memory_clk;
    always #17 pclk=!pclk;
    initial begin #3.7;forever #40.690104 reference48=!reference48;end
    initial begin #17.2;forever #29.525699 reference44=!reference44;end
    reg midi_rx=1,pc_rx=1,usb_valid=0,usb_lifecycle=0,usb_cancel=0;
    reg [17:0] usb_data=0;
    wire usb_ready;
    reg psel=0,penable=0,pwrite=0;
    reg [11:0] paddr=0;
    reg [31:0] pwdata=0;
    reg [3:0] pstrb=15;
    wire pready,pslverr;
    wire [31:0] prdata;
    wire [447:0] performance;
    reg request=0,request44=0,permit=1,tf_active=0,tf_busy=0,tf_error=0;
    reg [19:0] tf_rate=48000;
    wire ready,busy,fault,accepted,applied,policy_rejected,rate,active_valid,rec_enabled,rec_failed;
    wire [2:0] rec_code;
    wire [3:0] block_reason;
    wire [31:0] epoch,active,control_state,control_pitch,options,applied_events,pc_health;
    wire [127:0] held;
    wire [15:0] volume;
    wire [31:0] underruns,midi_drops,observation_drops,record_drops;
    wire sample_valid,frame_valid,frame_error,frame_rate,mclk,bck,lrck,sd,pdn_n,smute,uart_error;
    wire signed [31:0] audio_left,audio_right;
    wire [31:0] frame_epoch,frame_sequence,frame_pcm;
    wire fft_valid,fft_context,fft_rate;
    wire [7:0] fft_bin;
    wire signed [23:0] fft_real,fft_imag;
    wire [31:0] fft_epoch,fft_discards;
    wire running,done,score_failed;
    wire [31:0] leds,score_frame;
    wire display_valid;
    wire display_rate,display_error,display_observation_fault;
    wire [31:0] display_pcm,display_epoch,display_sequence;
    wire [2:0] display_effect_mask;
    wire [5:0] display_effect_order;
    wire ddr_req,ddr_write;
    wire [28:0] ddr_address;
    wire [255:0] ddr_data,ddr_read_data;
    wire [31:0] ddr_mask;
    reg ddr_response=0;
    workstation_runtime_controlled #(.WINDOW_CYCLES(500),.STABLE_WINDOWS(3),.LOSS_TIMEOUT_CYCLES(25),
        .STOP_LOW_CYCLES(8),.STARTUP_MUTE_FRAMES(3),.PDN_HOLD_FRAMES(1),.RECORD_ADDRESS_BITS(4),
        .RESERVE_ZERO_EPOCH(RESERVE_ZERO_EPOCH)) dut(
        .rst_ni(rst_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .reference_48_i(reference48),.reference_44_i(reference44),.midi_rx_i(midi_rx),.pc_uart_rx_i(pc_rx),
        .usb_event_valid(usb_valid),.usb_lifecycle,.usb_cancel,.usb_event_data(usb_data),.usb_event_ready(usb_ready),
        .pclk,.preset_n,.psel,.penable,.pwrite,.paddr,.pwdata,.pstrb,.pready,.pslverr,.prdata,.performance_words_o(performance),
        .request_i(request),.request_44k1_i(request44),.switch_permit_i(permit),.recover_i(1'b0),.media_quiescent_i(1'b1),
        .request_ready_o(ready),.busy_o(busy),.fault_o(fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(),.failed_o(),.policy_rejected_o(policy_rejected),.reject_code_o(),.fault_code_o(),.clock_select_o(),
        .switch_block_reason_o(block_reason),.active_44k1_o(rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),
        .source_qualified_o(),.quiesce_o(),.stream_flush_o(),.dsp_fault_o(),.context_ready_o(),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(1'b0),
        .tf_active_i(tf_active),.tf_busy_i(tf_busy),.tf_valid_i(1'b1),.tf_error_i(tf_error),
        .tf_left_i(16'sd25000),.tf_right_i(-16'sd17000),.tf_sample_rate_i(tf_rate),
        .tf_generation_i(32'd1),.expected_tf_generation_i(32'd1),.tf_ready_o(),
        .ddr_req_o(ddr_req),.ddr_write_o(ddr_write),.ddr_address_o(ddr_address),.ddr_data_o(ddr_data),.ddr_mask_o(ddr_mask),
        .ddr_ready_i(1'b1),.ddr_response_i(ddr_response),.ddr_read_data_i(ddr_read_data),
        .mclk_o(mclk),.bck_o(bck),.lrck_o(lrck),.data_o(sd),.pdn_no(pdn_n),.smute_o(smute),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_44k1_o(frame_rate),
        .frame_epoch_o(frame_epoch),.frame_sequence_o(frame_sequence),.frame_pcm_o(frame_pcm),
        .held_notes_o(held),.control_state_o(control_state),.control_pitch_o(control_pitch),.control_options_o(options),
        .applied_events_o(applied_events),.pc_health_o(pc_health),.master_volume_o(volume),.active_mask_o(active),
        .scope_status_o(),.tf_scope_control_o(),.deadline_miss_o(),.midi_overflow_o(),.note_drop_o(),
        .underrun_count_o(underruns),.midi_cdc_drop_o(midi_drops),.observation_drop_o(observation_drops),.record_drop_o(record_drops),
        .uart_error_o(uart_error),.sample_valid_o(sample_valid),.audio_left_o(audio_left),.audio_right_o(audio_right),
        .record_enabled_o(rec_enabled),.record_failed_o(rec_failed),.record_failure_code_o(rec_code),
        .score_running_o(running),.score_done_o(done),.score_failed_o(score_failed),.led_mask_o(leds),.score_frame_o(score_frame),
        .fft_valid_o(fft_valid),.fft_bin_o(fft_bin),.fft_real_o(fft_real),.fft_imag_o(fft_imag),.fft_frame_o(),
        .fft_discard_count_o(fft_discards),.fft_44k1_o(fft_rate),.fft_context_valid_o(fft_context),.fft_epoch_o(fft_epoch),
        .display_valid_o(display_valid),.display_pcm_o(display_pcm),.display_reference_o(),.display_voices_o(),.display_status_o(),
        .display_44k1_o(display_rate),.display_error_o(display_error),.display_epoch_o(display_epoch),.display_sequence_o(display_sequence),
        .effect_mask_o(display_effect_mask),.effect_order_o(display_effect_order),.display_observation_fault_o(display_observation_fault));
    // Ordered owner-6 DDR model with real data, not synthetic DMA completion.
    reg [255:0] memory[0:4095],qdata[0:63],read_data=0;
    reg [28:0] qaddr[0:63];reg qwrite[0:63];
    integer head=0,tail=0,queued=0,memory_ticks=0,writes=0,reads=0;
    assign ddr_read_data=read_data;
    always @(posedge memory_clk)begin
        ddr_response<=0;
        if(rst_n)begin
            if(ddr_req)begin
                if(queued>=64 || ddr_address<29'h0c000000 || ddr_address>=29'h0c008000 || ddr_address[2:0]!=0 || ddr_mask!=0)
                    $fatal(1,"owner6 allocation/alignment/mask");
                qdata[tail]=ddr_data;qaddr[tail]=ddr_address;qwrite[tail]=ddr_write;
                tail=(tail+1)%64;queued=queued+1;
            end
            if(queued!=0)begin
                if(memory_ticks==3)begin
                    memory_ticks=0;
                    if(qwrite[head])begin memory[12'((qaddr[head]-29'h0c000000)>>3)]=qdata[head];writes=writes+1;end
                    else begin read_data<=memory[12'((qaddr[head]-29'h0c000000)>>3)];ddr_response<=1;reads=reads+1;end
                    head=(head+1)%64;queued=queued-1;
                end else memory_ticks=memory_ticks+1;
            end
        end
    end
    reg [31:0] physical_pcm[0:3][0:8191];
    reg physical_error[0:3][0:8191],physical_seen[0:3][0:8191],physical_rate[0:3][0:8191];
    reg [8:0] observed_effect_pair[0:3][0:8191];
    reg observed_effect_seen[0:3][0:8191];
    reg [31:0] decoded=0,last_decoded=0;
    integer physical_position=0,physical_frames=0,observed_frames=0,nonzero=0,display_frames=0;
    integer fft_bins=0,fft_nonzero=0,uart_errors=0,apb_transactions=0,usb_events=0,cpu_events=0,policies=0;
    integer observed48=0,observed44=0,fft48=0,fft44=0;
    integer display_effect_tuple_checks=0,display_effect_changes48=0,display_effect_changes44=0;
    integer source_50_checks=0,source_compute_checks=0,switch_source_changes=0,reason_source_changes=0;
    integer switch_launch_delay_checks=0,pc_drop_carry_checks=0,tf_reason_handoffs=0,score_switch_rejects=0;
    integer switch_async_assert_checks=0,switch_release_checks=0;
    reg expected_switch_source,expected_drop_source,check_50_source,check_compute_source;
    reg previous_switch_source=1;
    reg [2:0] expected_reason_source,previous_reason_source=0;
    realtime last_control_edge=0,last_compute_edge=0;
    realtime boundary_accept_time=0,boundary_start_time=0,boundary_inhibit_time=0;
    reg boundary_armed=0;
    always @(posedge compute_clk)if(INFLIGHT_SCORE_BOUNDARY && boundary_armed && dut.score_start)
        boundary_start_time=$realtime;
    always @(posedge dut.switch_busy_compute[1])if(INFLIGHT_SCORE_BOUNDARY && boundary_armed)
        boundary_inhibit_time=$realtime;
    // These checks prove source-flop timing, not analog glitch/CDC behavior.
    // The pre-edge decode must be retained after an owner changes this edge.
    always @(posedge control_clk)begin
        last_control_edge=$realtime;check_50_source=dut.reset_50_n;
        expected_switch_source=busy || dut.quiesce_o;expected_drop_source=dut.pc_drop!=0;
        #0.001;
        if(check_50_source)begin
            if(dut.switch_busy_50!==expected_switch_source || dut.pc_drop_seen_50!==expected_drop_source)
                $fatal(1,"control CDC aggregate lacks source register");
            source_50_checks=source_50_checks+1;
            if(dut.switch_busy_50!=previous_switch_source)switch_source_changes=switch_source_changes+1;
        end
        previous_switch_source=dut.switch_busy_50;
    end
    always @(posedge compute_clk)begin
        last_compute_edge=$realtime;check_compute_source=dut.reset_compute_n;
        expected_reason_source={tf_active || tf_busy,running,rec_enabled};
        #0.001;
        if(check_compute_source)begin
            if(dut.reasons_compute!==expected_reason_source)$fatal(1,"reason CDC aggregate lacks source register");
            source_compute_checks=source_compute_checks+1;
            if(dut.reasons_compute!=previous_reason_source)reason_source_changes=reason_source_changes+1;
        end
        previous_reason_source=dut.reasons_compute;
    end
    always @(dut.switch_busy_50 or dut.pc_drop_seen_50)
        if(dut.reset_50_n && $realtime!=last_control_edge)$fatal(1,"control CDC source changed between source edges");
    always @(dut.reasons_compute)
        if(dut.reset_compute_n && $realtime!=last_compute_edge)$fatal(1,"reason CDC source changed between source edges");
    always @(posedge dut.switch_busy_50)begin
        #0.001;
        if(CHECK_SWITCH_ASYNC && rst_n && dut.reset_compute_n)begin
            if(dut.switch_busy_compute!==2'b11)$fatal(1,"registered switch source did not assert compute inhibit asynchronously");
            switch_async_assert_checks=switch_async_assert_checks+1;
        end
    end
    reg [1:0] expected_switch_release;
    always @(posedge compute_clk)begin
        expected_switch_release={dut.switch_busy_compute[0],1'b0};
        #0.001;
        if(dut.reset_compute_n && !dut.switch_busy_50)begin
            if(dut.switch_busy_compute!==expected_switch_release)$fatal(1,"switch inhibit release skipped local compute stages");
            switch_release_checks=switch_release_checks+1;
        end
    end
    reg [8:0] last_effect48=9'h1ff,last_effect44=9'h1ff;
    always @(negedge dut.runtime.serial_reset_n)begin physical_position=0;decoded=0;last_decoded=0;end
    always @(posedge bck)begin
        #0.1;
        if(dut.runtime.serial_reset_n)begin
            if(lrck!==(physical_position>=32))$fatal(1,"I2S LRCK");
            if(physical_position>=1 && physical_position<=16)decoded[32-physical_position]=sd;
            else if(physical_position>=33 && physical_position<=48)decoded[48-physical_position]=sd;
            else if(sd!==0)$fatal(1,"I2S padding");
            if(physical_position==63)begin last_decoded=decoded;decoded=0;physical_position=0;end
            else physical_position=physical_position+1;
        end
    end
    always @(negedge mclk)if(rst_n && frame_valid)begin
        if(frame_epoch>=4 || frame_sequence>=8192 || frame_pcm!==last_decoded)$fatal(1,"physical serial tap");
        physical_seen[frame_epoch][frame_sequence]=1;physical_pcm[frame_epoch][frame_sequence]=last_decoded;
        physical_error[frame_epoch][frame_sequence]=frame_error;physical_rate[frame_epoch][frame_sequence]=frame_rate;
        physical_frames=physical_frames+1;
    end
    always @(negedge compute_clk)if(rst_n && dut.reset_compute_n)begin
        if(performance!=={32'h43545231,dut.snap_sequence,dut.snap_right,dut.snap_left,dut.snap_status,
            control_pitch,options,held,pc_health,control_state,applied_events})$fatal(1,"448-bit performance layout");
        if(sample_valid)begin
            if(!physical_seen[dut.observed_epoch][dut.observed_sequence] ||
               {audio_left[31:16],audio_right[31:16]}!==physical_pcm[dut.observed_epoch][dut.observed_sequence] ||
               audio_left[15:0]!=0 || audio_right[15:0]!=0 ||
               dut.observed_error!==physical_error[dut.observed_epoch][dut.observed_sequence] ||
               dut.observed_rate!==physical_rate[dut.observed_epoch][dut.observed_sequence])
                $fatal(1,"compute observer did not receive actual physical PCM/context");
            observed_frames=observed_frames+1;if(audio_left!=0 || audio_right!=0)nonzero=nonzero+1;
            if(dut.observed_rate)observed44=observed44+1;else observed48=observed48+1;
        end
        if(fft_valid)begin
            if(!fft_context || fft_epoch!=dut.observed_epoch || fft_rate!==dut.observed_rate)$fatal(1,"FFT context label");
            fft_bins=fft_bins+1;if(fft_real!=0 || fft_imag!=0)fft_nonzero=fft_nonzero+1;
            if(fft_rate)fft44=fft44+1;else fft48=fft48+1;
        end
    end
    always @(posedge compute_clk)if(rst_n)begin
        // Independent source-edge oracle keyed by the physical frame context.
        // Both this oracle and the held-word mailbox sample the old committed
        // controls on this edge, before any new parameter commit takes effect.
        if(dut.observed_valid)begin
            observed_effect_pair[dut.observed_epoch][dut.observed_sequence]={dut.effect_mask_compute,dut.effect_order_compute};
            observed_effect_seen[dut.observed_epoch][dut.observed_sequence]=1;
        end
        if(dut.events.g1_valid && dut.events.g1_ready)usb_events=usb_events+1;
        if(dut.events.pc_valid && dut.events.pc_ready)cpu_events=cpu_events+1;
    end
    always @(negedge control_clk)if(rst_n)begin
        if(display_valid)begin
            if(!physical_seen[display_epoch][display_sequence] ||
               display_pcm!==physical_pcm[display_epoch][display_sequence] ||
               display_error!==physical_error[display_epoch][display_sequence] || display_rate!==physical_rate[display_epoch][display_sequence])
                $fatal(1,"display lost physical PCM context");
            if(!observed_effect_seen[display_epoch][display_sequence] ||
               {display_effect_mask,display_effect_order}!==observed_effect_pair[display_epoch][display_sequence])
                $fatal(1,"display effect pair torn or detached from physical frame");
            display_effect_tuple_checks=display_effect_tuple_checks+1;
            if(display_rate)begin
                if({display_effect_mask,display_effect_order}!=last_effect44)display_effect_changes44=display_effect_changes44+1;
                last_effect44={display_effect_mask,display_effect_order};
            end else begin
                if({display_effect_mask,display_effect_order}!=last_effect48)display_effect_changes48=display_effect_changes48+1;
                last_effect48={display_effect_mask,display_effect_order};
            end
            display_frames=display_frames+1;
        end
        if(uart_error)uart_errors=uart_errors+1;
        if(policy_rejected)policies=policies+1;
        if(fault || display_observation_fault || underruns!=0 || observation_drops!=0 || midi_drops!=0)
            $fatal(1,"healthy integration fault/drop/underrun");
    end
    task frames(input integer n);integer target;begin target=observed_frames+n;wait(observed_frames>=target);@(negedge compute_clk);end endtask
    task apb(input bit wr,input integer address,input reg [31:0] data,output reg [31:0] value);
        integer n;
        begin
            @(negedge pclk);psel=1;penable=0;pwrite=wr;paddr=12'(address);pwdata=data;
            @(negedge pclk);penable=1;n=0;
            do begin @(posedge pclk);#0.1;n=n+1;end while(!pready && n<10000);
            if(!pready || pslverr)$fatal(1,"APB failure wr=%b address=%h error=%b",wr,address,pslverr);
            value=prdata;@(negedge pclk);psel=0;penable=0;apb_transactions=apb_transactions+1;
        end
    endtask
    reg [31:0] value;
    task write_reg(input integer addr,input reg [31:0] data);begin apb(1,addr,data,value);end endtask
    task read_reg(input integer addr);begin apb(0,addr,0,value);end endtask
    task event_cpu(input integer kind,address,data);begin write_reg('h180,{14'd0,4'(kind),7'(address),7'(data)});end endtask
    task event_usb(input integer kind,address,data,input bit life,input bit cancel);
        begin @(negedge compute_clk);usb_data={4'(kind),7'(address),7'(data)};usb_valid=1;usb_lifecycle=life;usb_cancel=cancel;
            do @(posedge compute_clk);while(!usb_ready);
            @(negedge compute_clk);usb_valid=0;usb_lifecycle=0;usb_cancel=0;end
    endtask
    task uart_byte(input bit pc,input reg [7:0] data,input bit bad_stop);
        integer period;
        begin
            period=pc ? 434:1600;
            @(negedge control_clk);if(pc)pc_rx=0;else midi_rx=0;
            repeat(period)@(negedge control_clk);
            for(integer bitno=0;bitno<8;bitno=bitno+1)begin
                if(pc)pc_rx=data[bitno];else midi_rx=data[bitno];repeat(period)@(negedge control_clk);
            end
            if(pc)pc_rx=!bad_stop;else midi_rx=!bad_stop;repeat(period)@(negedge control_clk);
            if(pc)pc_rx=1;else midi_rx=1;repeat(period)@(negedge control_clk);
        end
    endtask
    task reject_switch(input integer reason);
        integer saved;
        begin saved=epoch;repeat(6)@(negedge control_clk);
            if(ready || !block_reason[reason])$fatal(1,"busy source not blocking switch reason=%0d mask=%h",reason,block_reason);
            request44=!rate;request=1;@(negedge control_clk);request=0;
            if(!policy_rejected || accepted || busy || epoch!=32'(saved))$fatal(1,"policy rejection changed stream");end
    endtask
    task inflight_zero_cue_switch;
        integer attempts;
        begin
            frames(2);
            write_reg('h100,0);write_reg('h104,0);write_reg('h108,32'ha5);write_reg('h10c,1);write_reg('h110,1);
            attempts=0;
            while(!boundary_armed && attempts<96)begin
                attempts=attempts+1;
                fork
                    begin write_reg('h114,1);end
                    begin
                        // The real APB CDC has captured this command but has
                        // not yet asserted command_valid. Choose a phase in
                        // which the next 50-MHz request acceptance falls just
                        // before the compute edge consuming SCORE_START.
                        wait(dut.command_address==12'h114 &&
                             dut.control_cdc.req_settled!=dut.control_cdc.acknowledge_toggle &&
                             !dut.control_cdc.request_decoded);
                        if(last_control_edge+20.0-$realtime>19.1)begin
                            boundary_armed=1;
                            @(negedge control_clk);request44=1;request=1;
                            @(posedge control_clk);#0.001;
                            if(!accepted || dut.switch_busy_50)$fatal(1,"in-flight score request was not accepted from RUN");
                            boundary_accept_time=$realtime;
                            @(negedge control_clk);request=0;
                        end
                    end
                join
                if(!boundary_armed)begin
                    repeat(6)@(negedge compute_clk);
                    if(running)$fatal(1,"zero cue did not finish between phase attempts");
                end
            end
            if(!boundary_armed || boundary_start_time<=boundary_accept_time || boundary_start_time-boundary_accept_time>=6.95)
                $fatal(1,"in-flight score phase not covered accept=%0t start=%0t",boundary_accept_time,boundary_start_time);
            repeat(6)@(negedge compute_clk);
            if(running || !score_failed || done)
                $fatal(1,"in-flight zero-cue score lost explicit failure: failed=%b done=%b running=%b accept=%0t start=%0t inhibit=%0t",
                    score_failed,done,running,boundary_accept_time,boundary_start_time,boundary_inhibit_time);
            $display("PASS runtime_controlled_inflight_score: attempts=%0d explicit_failures=1 source_50_checks=%0d source_compute_checks=%0d switch_async_assert_checks=%0d switch_release_checks=%0d accept_ps=%0d start_ps=%0d inhibit_ps=%0d",attempts,source_50_checks,source_compute_checks,switch_async_assert_checks,switch_release_checks,longint'(boundary_accept_time*1000.0),longint'(boundary_start_time*1000.0),longint'(boundary_inhibit_time*1000.0));
            $finish;
        end
    endtask
    reg [127:0] before_held;
    reg [31:0] before_control,before_pitch,before_options;
    integer before_epoch,before_applied,before_observed;
    reg [31:0] captured_left,captured_right;
    initial begin
        for(integer e=0;e<4;e=e+1)for(integer s=0;s<8192;s=s+1)begin
            physical_seen[e][s]=0;observed_effect_seen[e][s]=0;
        end
        repeat(8)@(negedge control_clk);rst_n=1;preset_n=1;
        // A real stopped byte consumer produces counter transitions 0->1->2,
        // including a binary carry. Boot waits for DSP context; audio has not
        // started, so this exercises UART loss without dropping physical PCM.
        repeat(8)@(negedge control_clk);@(negedge compute_clk);compute_run=0;
        uart_byte(1,8'hf8,0);uart_byte(1,8'hf8,0);uart_byte(1,8'hf8,0);
        if(dut.pc_drop!=2 || !dut.pc_drop_seen_50)$fatal(1,"real PC byte drop carry not exercised");
        compute_run=1;wait(pc_health[1]);pc_drop_carry_checks=pc_drop_carry_checks+1;
        wait(ready && active_valid);read_reg(0);if(value!=32'h41313338)$fatal(1,"services identity");
        if(INFLIGHT_SCORE_BOUNDARY)inflight_zero_cue_switch();
        event_cpu(2,7,100);event_cpu(1,60,127);frames(192);
        if(!held[60] || active==0 || nonzero==0)$fatal(1,"APB event failed to reach single real owner");
        // Change multiple effect bits and order fields at each physical rate.
        // They must arrive with the same frame tuple, never through naked 2FFs.
        event_cpu(2,81,1);event_cpu(2,84,2);event_cpu(2,85,0);frames(4);
        event_cpu(2,81,0);event_cpu(2,86,1);frames(4);
        write_reg('h1a8,32'h10203040);write_reg('h1ac,32'h50607080);write_reg('h1b0,32'h12345678);write_reg('h1b4,32'h87654321);
        if(performance[415:384]!=32'h50607080 || performance[319:288]!=32'h10203040)$fatal(1,"snapshot performance field placement");
        before_held=held;before_applied=integer'(applied_events);
        before_control=control_state;before_pitch=control_pitch;before_options=options;
        preset_n=0;repeat(20)@(negedge pclk);preset_n=1;repeat(20)@(negedge pclk);
        if(held!==before_held || applied_events!=32'(before_applied) || control_state!=before_control ||
           control_pitch!=before_pitch || options!=before_options)$fatal(1,"preset reset leaked into DSP");
        read_reg('h1a8);if(value!=0)$fatal(1,"services not reset independently");
        // Both original UART baud rates carry real MIDI bytes into same owner.
        uart_byte(0,8'h90,0);uart_byte(0,8'd61,0);uart_byte(0,8'd100,0);frames(4);
        if(!held[61])$fatal(1,"31250 MIDI UART/byte CDC failed");
        uart_byte(1,8'h90,0);uart_byte(1,8'd62,0);uart_byte(1,8'd100,0);frames(4);
        if(!held[62])$fatal(1,"115200 PC UART/byte CDC failed");
        uart_byte(1,8'hf8,1);uart_byte(0,8'hf8,1);frames(2);
        if(!pc_health[0] || uart_errors==0)$fatal(1,"UART health behavior lost");
        // Concurrent normal producers both progress through fair merge.
        fork
            begin for(integer i=0;i<32;i=i+1)event_usb(2,11,80+i%32,0,0);end
            begin for(integer i=0;i<16;i=i+1)event_cpu(3,20+i%8,0);end
        join
        frames(4);if(usb_events<32 || cpu_events<18)$fatal(1,"normal source starvation");
        // All 256 downloaded cue slots remain usable through original services.
        for(integer i=0;i<256;i=i+1)begin
            write_reg('h100,32'(i));write_reg('h104,32'(1000+i));write_reg('h108,32'(i+1));write_reg('h10c,1);
        end
        write_reg('h110,256);read_reg('h12c);if(value!=256)$fatal(1,"score cue capacity");
        write_reg('h114,1);wait(running);reject_switch(2);write_reg('h118,1);wait(!running);
        // Old firmware sequence is start, capture, STOP, then POP/READ/RELEASE.
        write_reg('h080,1);frames(8);reject_switch(1);write_reg('h080,0);
        if(rec_failed)$fatal(1,"normal recording failed");
        read_reg('h084);if(!value[1])$fatal(1,"STOP hid capture queue");
        write_reg('h088,1);read_reg('h090);captured_left=value;read_reg('h094);captured_right=value;
        if(captured_left[15:0]!=0 || captured_right[15:0]!=0 || (captured_left==0 && captured_right==0))$fatal(1,"record packet did not carry physical Q31");
        write_reg('h098,1);
        // Overflow fails the whole recording object and does not recover alone.
        write_reg('h080,1);frames(24);
        if(!rec_failed || rec_code!=6 || record_drops==0 || dut.record_valid)$fatal(1,"capture overflow hidden");
        write_reg('h080,0);frames(2);
        @(negedge compute_clk);tf_busy=1;reject_switch(3);
        @(negedge compute_clk);tf_active=1;tf_busy=0;repeat(6)@(negedge control_clk);
        if(!block_reason[3] || ready)$fatal(1,"TF busy-to-active diagnostic handoff lost inhibit");
        tf_reason_handoffs=tf_reason_handoffs+1;
        @(negedge compute_clk);tf_active=0;wait(ready);
        // Mid-frame rate request plus a new recording command: race fails REC.
        before_held=held;before_epoch=integer'(epoch);before_observed=observed_frames;
        @(negedge control_clk);request44=1;request=1;
        @(posedge control_clk);#0.001;
        if(!accepted || dut.switch_busy_50)$fatal(1,"switch source did not retain previous RUN edge");
        switch_launch_delay_checks=switch_launch_delay_checks+1;
        @(negedge control_clk);request=0;
        if(!accepted)$fatal(1,"real 44.1 switch not accepted");
        write_reg('h080,1);wait(rec_failed);
        if(rec_code!=7)$fatal(1,"switch/REC race not explicit code=%0d",rec_code);
        write_reg('h114,1);repeat(3)@(negedge compute_clk);
        if(running || !score_failed || done)$fatal(1,"switch admitted score start/success");
        score_switch_rejects=score_switch_rejects+1;
        wait(!busy && active_valid);frames(8);
        if(!rate || epoch!=32'(before_epoch+1) || held!==before_held || observed_frames<=before_observed)$fatal(1,"switch lost live state/observations");
        write_reg('h080,0);frames(1);write_reg('h080,1);frames(1);
        if(!rec_failed || rec_code!=5 || dut.record_valid)$fatal(1,"44.1 legacy packet accepted without context");
        write_reg('h080,0);
        event_cpu(2,81,1);event_cpu(2,84,1);event_cpu(2,85,2);frames(4);
        event_cpu(2,81,0);event_cpu(2,86,0);frames(4);frames(692);
        // Actual physical source error terminates score and discards FFT context.
        write_reg('h114,1);wait(running);tf_active=1;tf_rate=44100;tf_error=1;frames(4);
        if(running || !score_failed || fft_discards==0 || done)$fatal(1,"physical error not propagated to consumers");
        tf_active=0;tf_error=0;frames(2);
        // Epoch-local counters really jump N->0; the held health snapshot
        // carries that new epoch and coherent zero, rather than a torn Gray word.
        if(dut.source_errors_compute==0)$fatal(1,"physical error health snapshot missing");
        before_epoch=integer'(epoch);wait(ready);
        @(negedge control_clk);request44=0;request=1;
        @(posedge control_clk);#0.001;
        if(!accepted || dut.switch_busy_50)$fatal(1,"return switch source did not retain previous RUN edge");
        switch_launch_delay_checks=switch_launch_delay_checks+1;
        @(negedge control_clk);request=0;
        if(!accepted)$fatal(1,"return switch not accepted");
        wait(!busy && active_valid);frames(8);
        if(rate || epoch!=32'(before_epoch+1) || dut.health_epoch!=epoch || dut.source_errors_compute!=0)
            $fatal(1,"epoch health reset snapshot was torn or stale");
        // Lifecycle cancellation is still the unbuffered priority path.
        event_usb(15,0,0,1,1);frames(4);if(held!=0 || active!=0)$fatal(1,"USB cancel did not clear real owner");
        if(physical_frames<1000 || observed_frames<1000 || observed48<256 || observed44<256 ||
           fft48<128 || fft44<128 || fft_nonzero==0 || display_frames<100 || writes==0 || reads==0 ||
           display_effect_tuple_checks!=display_frames || display_effect_changes48<3 || display_effect_changes44<3)
            $fatal(1,"missing integration coverage physical=%0d observed=%0d fft=%0d wet=%0d",physical_frames,observed_frames,fft_bins,fft_nonzero);
        if(source_50_checks==0 || source_compute_checks==0 || switch_source_changes<5 || reason_source_changes<8 ||
           switch_launch_delay_checks!=2 || pc_drop_carry_checks!=1 || tf_reason_handoffs!=1 || score_switch_rejects!=1)
            $fatal(1,"missing registered source/boundary checks");
        if(switch_async_assert_checks!=2 || switch_release_checks==0)$fatal(1,"missing switch asynchronous assert/local release checks");
        $display("PASS runtime_controlled: physical_frames=%0d observed_frames=%0d observed48=%0d observed44=%0d nonzero=%0d display_frames=%0d fft_bins=%0d fft48=%0d fft44=%0d fft_nonzero=%0d apb=%0d usb=%0d cpu=%0d policies=%0d writes=%0d reads=%0d fft_discards=%0d switches=2 health_reset_checks=1 display_observation_fault_checks=1 display_effect_tuple_checks=%0d display_effect_changes48=%0d display_effect_changes44=%0d source_50_checks=%0d source_compute_checks=%0d switch_source_changes=%0d reason_source_changes=%0d switch_launch_delay_checks=%0d pc_drop_carry_checks=%0d tf_reason_handoffs=%0d score_switch_rejects=%0d switch_async_assert_checks=%0d switch_release_checks=%0d",physical_frames,observed_frames,observed48,observed44,nonzero,display_frames,fft_bins,fft48,fft44,fft_nonzero,apb_transactions,usb_events,cpu_events,policies,writes,reads,fft_discards,display_effect_tuple_checks,display_effect_changes48,display_effect_changes44,source_50_checks,source_compute_checks,switch_source_changes,reason_source_changes,switch_launch_delay_checks,pc_drop_carry_checks,tf_reason_handoffs,score_switch_rejects,switch_async_assert_checks,switch_release_checks);
        $finish;
    end
    initial begin #200000000;$fatal(1,"controlled integration watchdog");end
endmodule
