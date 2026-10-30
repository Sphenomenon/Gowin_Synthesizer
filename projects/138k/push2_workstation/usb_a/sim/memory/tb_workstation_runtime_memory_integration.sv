`timescale 1ns/1ps
// Actual controlled runtime and owner-6 queue, with the explicit top's reset,
// permanent transaction gates and asynchronous mute assertion composition.
module tb_workstation_runtime_memory_integration;
    reg control_clk=0,compute_clk=0,memory_clk=0,pclk=0,reference48=0,reference44=0;
    reg common_reset_n=0,preset_n=0,memory_run=1;
    reg backend_reset_n=1,backend_ready=0,compute_qualified=1;
    always #10 control_clk=!control_clk;
    always #6.510417 compute_clk=!compute_clk;
    initial begin #2; forever begin #5; if(memory_run)memory_clk=!memory_clk;end end
    always #17 pclk=!pclk;
    initial begin #3.7;forever #40.690104 reference48=!reference48;end
    initial begin #17.2;forever #29.525699 reference44=!reference44;end
    wire guard_started,guard_fault,guard_ready,guard_mute,channel_open;
    wire [1:0] guard_code;
    wire runtime_reset_n=common_reset_n && guard_started;
    workstation_runtime_memory_guard #(.HEARTBEAT_TIMEOUT_CYCLES(25)) guard(
        .reset_ni(common_reset_n),.clk_50m_i(control_clk),.memory_clk_i(memory_clk),
        .backend_reset_ni(backend_reset_n),.backend_ready_i(backend_ready && compute_qualified),
        .started_o(guard_started),.fault_o(guard_fault),.start_ready_o(guard_ready),
        .mute_o(guard_mute),.channel_open_o(channel_open),.clock_alive_o(),.fault_code_o(guard_code));
    wire compute_output_safe_n=common_reset_n && compute_qualified && !guard_mute;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] output_safe_compute;
    always @(posedge compute_clk or negedge compute_output_safe_n)
        if(!compute_output_safe_n)output_safe_compute<=0;
        else output_safe_compute<={output_safe_compute[1:0],1'b1};
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
    reg request=0,request44=0,recover=0,tf_active=0,tf_busy=0,tf_error=0;
    reg [19:0] tf_rate=48000;
    wire ready,busy,fault,accepted,applied,policy_rejected,rate,active_valid,rec_enabled,rec_failed;
    wire [2:0] rec_code;
    wire [3:0] block_reason;
    wire [31:0] epoch,active,control_state,control_pitch,options,applied_events,pc_health;
    wire [127:0] held;
    wire [15:0] volume;
    wire [31:0] underruns,midi_drops,observation_drops,record_drops;
    wire sample_valid,frame_valid,frame_error,frame_rate,mclk,bck,lrck,sd,pdn_n,smute,uart_error;
    wire hardware_smute=smute || guard_mute;
    wire signed [31:0] audio_left,audio_right;
    wire [31:0] frame_epoch,frame_sequence,frame_pcm;
    wire fft_valid,fft_context,fft_rate;
    wire [7:0] fft_bin;
    wire signed [23:0] fft_real,fft_imag;
    wire [31:0] fft_epoch,fft_discards;
    wire running,done,score_failed;
    wire [31:0] leds,score_frame;
    wire display_valid;
    wire display_rate,display_error;
    wire [31:0] display_pcm,display_epoch,display_sequence;
    wire [2:0] display_effect_mask;
    wire [5:0] display_effect_order;
    wire display_observation_fault;
    wire ddr_req,ddr_write;
    wire [28:0] ddr_address;
    wire [255:0] ddr_data,ddr_read_data;
    wire [31:0] ddr_mask;
    reg ddr_response=0;
    wire backend_request_ready;
    workstation_runtime_controlled #(.WINDOW_CYCLES(500),.STABLE_WINDOWS(3),.LOSS_TIMEOUT_CYCLES(25),
        .STOP_LOW_CYCLES(8),.STARTUP_MUTE_FRAMES(3),.PDN_HOLD_FRAMES(1),.RECORD_ADDRESS_BITS(4),
        .RESERVE_ZERO_EPOCH(1)) dut(
        .rst_ni(runtime_reset_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .reference_48_i(reference48),.reference_44_i(reference44),.midi_rx_i(midi_rx),.pc_uart_rx_i(pc_rx),
        .usb_event_valid(usb_valid),.usb_lifecycle,.usb_cancel,.usb_event_data(usb_data),.usb_event_ready(usb_ready),
        .pclk,.preset_n,.psel,.penable,.pwrite,.paddr,.pwdata,.pstrb,.pready,.pslverr,.prdata,.performance_words_o(performance),
        .request_i(request),.request_44k1_i(request44),.switch_permit_i(guard_ready),.recover_i(recover),.media_quiescent_i(1'b1),
        .request_ready_o(ready),.busy_o(busy),.fault_o(fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(),.failed_o(),.policy_rejected_o(policy_rejected),.reject_code_o(),.fault_code_o(),.clock_select_o(),
        .switch_block_reason_o(block_reason),.active_44k1_o(rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),
        .source_qualified_o(),.quiesce_o(),.stream_flush_o(),.dsp_fault_o(),.context_ready_o(),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(!output_safe_compute[2]),
        .tf_active_i(tf_active),.tf_busy_i(tf_busy),.tf_valid_i(1'b1),.tf_error_i(tf_error),
        .tf_left_i(16'sd25000),.tf_right_i(-16'sd17000),.tf_sample_rate_i(tf_rate),
        .tf_generation_i(32'd1),.expected_tf_generation_i(32'd1),.tf_ready_o(),
        .ddr_req_o(ddr_req),.ddr_write_o(ddr_write),.ddr_address_o(ddr_address),.ddr_data_o(ddr_data),.ddr_mask_o(ddr_mask),
        .ddr_ready_i(backend_request_ready && channel_open),.ddr_response_i(ddr_response && channel_open),.ddr_read_data_i(ddr_read_data),
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
        .effect_mask_o(display_effect_mask),.effect_order_o(display_effect_order),.display_observation_fault_o(display_observation_fault),
        .media_stop_request_i(1'b0),.media_stop_hold_i(1'b0),.media_stop_ready_o(),.media_stop_done_o(),.media_stop_failed_o(),
        .media_stop_failure_code_o(),.tf_stop_request_o(),.tf_stop_pending_i(1'b0),.tf_stop_done_i(1'b0),.tf_stop_failed_i(1'b0),.tf_stop_failure_code_i(4'd0));
    // Memory array and ordered queue survive backend readiness/reset loss.
    // Only the explicit complete-system reset resets queue identity. Reads are
    // held by the backend until release_reads, never invented completions.
    reg [255:0] memory[0:4095],qdata[0:63],read_data=0;
    reg [28:0] qaddr[0:63];reg qwrite[0:63];
    integer head=0,tail=0,queued=0,memory_ticks=0;
    integer accepted_commands=0,accepted_reads=0,completed_reads=0;
    integer stale_returns=0,escaped_returns=0,closed_request_attempts=0;
    integer writes=0,checks=0,phases=0,apb_transactions=0;
    reg release_reads=1;
    wire gated_request=ddr_req && channel_open;
    wire gated_ready=backend_request_ready && channel_open;
    wire gated_response=ddr_response && channel_open;
    assign backend_request_ready=queued<60;
    assign ddr_read_data=read_data;
    always @(posedge memory_clk)begin
        ddr_response<=0;
        if(!common_reset_n)begin head=0;tail=0;queued=0;memory_ticks=0;end
        else begin
            if(ddr_response && guard_fault)stale_returns=stale_returns+1;
            if(gated_response && guard_fault)escaped_returns=escaped_returns+1;
            if(ddr_req && !channel_open)closed_request_attempts=closed_request_attempts+1;
            if(gated_request && backend_request_ready)begin
                if(queued>=64 || ddr_address<29'h0c000000 || ddr_address>=29'h0c008000 || ddr_address[2:0]!=0 || ddr_mask!=0)
                    $fatal(1,"memory integration owner6 allocation/alignment/mask");
                qdata[tail]=ddr_data;qaddr[tail]=ddr_address;qwrite[tail]=ddr_write;
                tail=(tail+1)%64;queued=queued+1;accepted_commands=accepted_commands+1;
                if(!ddr_write)accepted_reads=accepted_reads+1;
            end
            if(queued!=0 && (qwrite[head] || release_reads))begin
                if(memory_ticks==3)begin
                    memory_ticks=0;
                    if(qwrite[head])begin memory[12'((qaddr[head]-29'h0c000000)>>3)]=qdata[head];writes=writes+1;end
                    else begin read_data<=memory[12'((qaddr[head]-29'h0c000000)>>3)];ddr_response<=1;completed_reads=completed_reads+1;end
                    head=(head+1)%64;queued=queued-1;
                end else memory_ticks=memory_ticks+1;
            end
        end
    end
    task automatic check(input bit value,input string description);
        begin checks=checks+1;if(!value)$fatal(1,"runtime memory integration: %s",description);end
    endtask
    integer physical_position=0,physical_frames=0,nonzero_frames=0,silent_fault_frames=0;
    integer fault_frame_base=0;
    reg inspect_fault_frames=0;
    reg [31:0] decoded=0,last_decoded=0;
    always @(negedge dut.runtime.serial_reset_n)begin physical_position=0;decoded=0;last_decoded=0;end
    always @(posedge bck)begin
        #0.1;
        if(dut.runtime.serial_reset_n)begin
            check(lrck===(physical_position>=32),"physical I2S LRCK");
            if(physical_position>=1 && physical_position<=16)decoded[32-physical_position]=sd;
            else if(physical_position>=33 && physical_position<=48)decoded[48-physical_position]=sd;
            else check(sd===0,"physical I2S zero padding");
            if(physical_position==63)begin last_decoded=decoded;decoded=0;physical_position=0;end
            else physical_position=physical_position+1;
        end
    end
    always @(negedge mclk)if(runtime_reset_n && frame_valid)begin
        check(frame_pcm===last_decoded,"actual serialized PCM agrees with physical frame tap");
        physical_frames=physical_frames+1;
        if(frame_pcm!=0)nonzero_frames=nonzero_frames+1;
        if(inspect_fault_frames && physical_frames>fault_frame_base+4)begin
            check(frame_pcm==0 && hardware_smute,"fault produces zero physical I2S frames with hardware SMUTE");
            silent_fault_frames=silent_fault_frames+1;
        end
    end
    task automatic control_cycles(input integer count);
        begin repeat(count)@(posedge control_clk);#2;end
    endtask
    task automatic frames(input integer count);
        integer target;
        begin target=physical_frames+count;wait(physical_frames>=target);@(negedge compute_clk);end
    endtask
    task automatic apb(input bit wr,input integer address,input [31:0] data,output reg [31:0] value);
        integer age;
        begin
            @(negedge pclk);psel=1;penable=0;pwrite=wr;paddr=12'(address);pwdata=data;
            @(negedge pclk);penable=1;age=0;
            do begin @(posedge pclk);#0.1;age=age+1;end while(!pready && age<10000);
            check(pready && !pslverr,"real APB command completes");
            value=prdata;@(negedge pclk);psel=0;penable=0;apb_transactions=apb_transactions+1;
        end
    endtask
    reg [31:0] apb_value;
    task automatic event_cpu(input integer kind,address,data);
        begin apb(1,'h180,{14'd0,4'(kind),7'(address),7'(data)},apb_value);end
    endtask
    reg [127:0] saved_held;
    reg [31:0] saved_control,saved_pitch,saved_options,saved_epoch,saved_applied;
    integer saved_accepted,saved_stale;
    task automatic snapshot;
        begin
            saved_held=held;saved_control=control_state;saved_pitch=control_pitch;
            saved_options=options;saved_epoch=epoch;saved_applied=applied_events;
            check(held[60] && volume!=16'd32768 && epoch==1,"note and nondefault parameter authority exist before failure");
        end
    endtask
    task automatic preserved;
        begin
            check(runtime_reset_n && guard_started,"guard failure does not reset actual runtime");
            check(held===saved_held && control_state===saved_control && control_pitch===saved_pitch &&
                options===saved_options && epoch===saved_epoch && applied_events===saved_applied,
                "actual held notes, committed controls, panic identity and stream epoch survive failure/recovery/CPU reset");
        end
    endtask
    task automatic boot;
        begin
            inspect_fault_frames=0;common_reset_n=0;preset_n=0;backend_reset_n=1;
            backend_ready=0;compute_qualified=1;memory_run=1;release_reads=1;request=0;recover=0;
            control_cycles(10);common_reset_n=1;control_cycles(40);
            check(!guard_started && !runtime_reset_n && !guard_fault,"actual runtime waits for first backend qualification");
            backend_ready=1;preset_n=1;
            wait(guard_ready && ready && active_valid);frames(8);
            check(held==0 && epoch==1,"complete common reset establishes fresh nonzero stream identity");
            event_cpu(2,7,91);event_cpu(2,11,73);event_cpu(1,60,127);frames(192);
            check(held[60] && active!=0 && nonzero_frames!=0,
                $sformatf("real owner rendered the APB note held=%b active=%h nonzero=%0d volume=%0d safe=%b",
                    held[60],active,nonzero_frames,volume,output_safe_compute));
            snapshot();saved_accepted=accepted_commands;saved_stale=stale_returns;
        end
    endtask
    task automatic after_fault(input [1:0] code);
        begin
            wait(guard_fault);control_cycles(4);
            check(guard_code==code && !channel_open && !gated_ready && !gated_request && !gated_response && hardware_smute,
                "permanent fault closes all three actual owner6 directions and asserts hardware mute");
            preserved();saved_accepted=accepted_commands;
            backend_ready=1;backend_reset_n=1;compute_qualified=1;memory_run=1;release_reads=1;
            fault_frame_base=physical_frames;inspect_fault_frames=1;
            frames(20);preserved();
            check(accepted_commands==saved_accepted && escaped_returns==0 && !channel_open && hardware_smute,
                "restored backend cannot accept or deliver a transaction");
            preset_n=0;repeat(8)@(negedge pclk);preset_n=1;repeat(12)@(negedge pclk);
            preserved();
            request44=1;request=1;@(negedge control_clk);request=0;recover=1;
            @(negedge control_clk);recover=0;control_cycles(20);preserved();
            check(!channel_open && guard_fault && guard_code==code && !accepted,"new switch/recover cannot hide a memory fault or change epoch");
            inspect_fault_frames=0;phases=phases+1;
        end
    endtask
    integer prior_reads,wait_frames;
    initial begin
        for(integer index=0;index<4096;index=index+1)memory[index]=0;
        boot();
        // Warm the actual audited 9600-sample delay rather than overriding its
        // state or narrowing its allocation. Keep its first ordinary ring read
        // accepted in the real backend queue when the fault arrives.
        prior_reads=accepted_reads;release_reads=0;wait_frames=physical_frames;
        wait(accepted_reads>prior_reads);
        check(physical_frames-wait_frames>8000 && queued!=0,"real delay ring read is pending after audited warmup");
        snapshot();
        @(negedge control_clk);#3;backend_ready=0;
        #0.1;check(!channel_open && hardware_smute,"short ready pulse closes/mutes before reference or memory edge");
        #0.9;backend_ready=1;after_fault(1);
        check(stale_returns>saved_stale && escaped_returns==0,"real queued pre-loss read returns after failure but never reaches delay DMA");
        $display("memory integration phase=ready-pulse physical_frames=%0d stale_returns=%0d",physical_frames,stale_returns);

        boot();@(negedge control_clk);#3;compute_qualified=0;
        #0.1;check(!channel_open && hardware_smute && runtime_reset_n,"short compute PLL qualification loss mutes without resetting DSP");
        #0.9;compute_qualified=1;after_fault(1);
        $display("memory integration phase=compute-qualification physical_frames=%0d",physical_frames);

        boot();@(posedge memory_clk);#1;memory_run=0;after_fault(2);
        $display("memory integration phase=memory-stopped-high physical_frames=%0d",physical_frames);

        boot();@(negedge memory_clk);#1;memory_run=0;after_fault(2);
        $display("memory integration phase=memory-stopped-low physical_frames=%0d",physical_frames);

        boot();check(!guard_fault && channel_open && held[60] && epoch==1,"only complete common reset permits a fresh functional runtime");
        check(silent_fault_frames>=64 && stale_returns>0 && escaped_returns==0 && closed_request_attempts>0,
            "fault fixture exercised actual mute, withheld response and blocked DMA continuation");
        $display("PASS runtime_memory_integration: phases=%0d checks=%0d physical_frames=%0d nonzero_frames=%0d silent_fault_frames=%0d apb=%0d accepted_reads=%0d completed_reads=%0d stale_returns=%0d escaped_returns=%0d blocked_request_cycles=%0d writes=%0d",
            phases,checks,physical_frames,nonzero_frames,silent_fault_frames,apb_transactions,
            accepted_reads,completed_reads,stale_returns,escaped_returns,closed_request_attempts,writes);
        $finish;
    end
    initial begin #400000000;$fatal(1,"runtime memory integration watchdog");end
endmodule
