`timescale 1ns/1ps
module tb_workstation_push_rate_runtime;
    localparam bit RESERVE_ZERO_EPOCH=1;
    reg control_clk=0,compute_clk=0,memory_clk=0,pclk=0,reference48=0,reference44=0,run48=1,run44=1,rst_n=0,preset_n=0,compute_run=1;
    always #10 control_clk=!control_clk;
    always #6.510417 if(compute_run)compute_clk=!compute_clk;
    always #5 memory_clk=!memory_clk;
    always #17 pclk=!pclk;
    initial begin #3.7;forever #40.690104 if(run48)reference48=!reference48;end
    initial begin #17.2;forever #29.525699 if(run44)reference44=!reference44;end
    reg midi_rx=1,pc_rx=1;
    wire usb_valid,usb_lifecycle,usb_cancel;
    wire [17:0] usb_data;
    wire usb_ready;
    reg psel=0,penable=0,pwrite=0;
    reg [11:0] paddr=0;
    reg [31:0] pwdata=0;
    reg [3:0] pstrb=15;
    wire pready,pslverr;
    wire [31:0] prdata;
    wire [447:0] performance;
    wire request,request44,recover;
    reg permit=1,tf_active=0,tf_busy=0,tf_error=0;
    reg [19:0] tf_rate=48000;
    wire ready,busy,fault,accepted,applied,rejected,failed,dsp_fault,policy_rejected,rate,active_valid,rec_enabled,rec_failed;
    wire [1:0] qualified; wire [2:0] reject_code; wire [3:0] fault_code;
    wire media_req,media_hold,media_ready,media_done,media_failed; wire [3:0]media_code;
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
    wire [127:0] display_parameters;
    wire [2:0] display_effect_mask;
    wire [5:0] display_effect_order;
    wire ddr_req,ddr_write;
    wire [28:0] ddr_address;
    wire [255:0] ddr_data,ddr_read_data;
    wire [31:0] ddr_mask;
    reg ddr_response=0;
    workstation_runtime_controlled #(.WINDOW_CYCLES(500),.STABLE_WINDOWS(3),.LOSS_TIMEOUT_CYCLES(25),
        .STOP_LOW_CYCLES(8),.STARTUP_MUTE_FRAMES(512),.PDN_HOLD_FRAMES(1),.RECORD_ADDRESS_BITS(4),
        .RESERVE_ZERO_EPOCH(RESERVE_ZERO_EPOCH),.ENABLE_MEDIA_POLICY(1),
        .TF_CONTROL_ENABLE(0),.LOCAL_RECORD_ENABLE(0),.LOCAL_SCORE_ENABLE(0)) dut(
        .common_reset_ni(1'b1),.rst_ni(rst_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .reference_48_i(reference48),.reference_44_i(reference44),.midi_rx_i(midi_rx),.pc_uart_rx_i(pc_rx),
        .usb_event_valid(usb_valid && consume),.usb_lifecycle,.usb_cancel,.usb_event_data(usb_data),.usb_event_ready(usb_ready),
        .pclk,.preset_n,.psel,.penable,.pwrite,.paddr,.pwdata,.pstrb,.pready,.pslverr,.prdata,.performance_words_o(performance),
        .request_i(request),.request_44k1_i(request44),.switch_permit_i(permit),.recover_i(recover),.media_quiescent_i(1'b1),
        .request_ready_o(ready),.busy_o(busy),.fault_o(fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(rejected),.failed_o(failed),.policy_rejected_o(policy_rejected),.reject_code_o(reject_code),.fault_code_o(fault_code),.clock_select_o(),
        .switch_block_reason_o(block_reason),.active_44k1_o(rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),
        .source_qualified_o(qualified),.quiesce_o(),.stream_flush_o(),.dsp_fault_o(dsp_fault),.context_ready_o(),
        .pcm_psel_i(1'b0),.pcm_pready_o(),.pcm_pslverr_o(),.pcm_prdata_o(),
        .hci_session_ready_i(1'b0),.hci_controller_epoch_i(32'd0),.hci_transport_generation_i(32'd0),
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
        .display_parameters_o(display_parameters),
        .display_44k1_o(display_rate),.display_error_o(display_error),.display_epoch_o(display_epoch),.display_sequence_o(display_sequence),
        .effect_mask_o(display_effect_mask),.effect_order_o(display_effect_order),.display_observation_fault_o(display_observation_fault),
        .media_stop_request_i(media_req),.media_stop_hold_i(media_hold),.media_stop_ready_o(media_ready),.media_stop_done_o(media_done),.media_stop_failed_o(media_failed),
        .media_stop_failure_code_o(media_code),.tf_stop_request_o(),.tf_stop_pending_i(1'b0),.tf_stop_done_i(1'b0),.tf_stop_failed_i(1'b0),.tf_stop_failure_code_i(4'd0));
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
    reg usb_clk=0,sel=0,wr=0,consume=1;
    always #10.416667 usb_clk=!usb_clk;
    reg [7:0] addr=0;reg [31:0] wd=0;
    wire mmio_ready,usb_pulse,usb_reject,source_ready,service_ready,service_reject,service_busy,service_fault;
    wire transported_pulse;wire [31:0] generation,transported_generation;
    wire [223:0] telemetry;
    wire [447:0] feedback=performance;
    push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0),.MEDIA_CONTROLS_ENABLE(0),.PUSH_RATE_CONTROL_ENABLE(1)) usb(
        .clk(usb_clk),.reset_n(rst_n),.audio_clk(compute_clk),.audio_reset_n(dut.reset_compute_n),
        .feedback_clk(control_clk),.feedback_reset_n(rst_n),.performance_words(feedback),
        .display_meta_data(64'd0),.display_meta_valid(1'b0),.service_state_data(34'd0),.service_state_valid(1'b0),
        .score_valid(1'b0),.analysis_done(1'b0),.score_ready(),.score_note(7'd0),
        .playlist_valid(1'b0),.playlist_ready(),.playlist_word(16'd0),.track_launch(),.track_index(),
        .select(sel),.write(wr),.address(addr),.wdata(wd),.ready(mmio_ready),.rdata(),
        .audio_valid(usb_valid),.audio_ready(usb_ready && consume),.audio_event(usb_data),
        .audio_lifecycle(usb_lifecycle),.audio_cancel(usb_cancel),.telemetry(telemetry),
        .rate_control_ready_i(source_ready),.rate_toggle_o(usb_pulse),.rate_rejected_o(usb_reject));
    // Runtime sees exactly the valid/ready transfer of the real USB owner.
    // The optional consumer gate creates genuine queue backpressure, without
    // changing any clock ACK, DSP, frame or serializer signal.
    workstation_push_rate_bridge bridge(.reset_ni(clock_reset_n && rst_n),
        .usb_clk_i(usb_clk),.control_clk_i(control_clk),.service_ready_i(service_ready),
        .service_generation_i(generation),.usb_ready_o(source_ready),.usb_toggle_i(usb_pulse),
        .service_toggle_o(transported_pulse),.service_generation_o(transported_generation));
    reg cpsel=0,cpenable=0,cpwrite=0;reg[11:0]cpaddr=0;reg[31:0]cpdata=0;
    wire cpready,cperror;wire[31:0]cpread;
    wire clock_reset_n,cv,cw,cr,ce;wire[11:0]ca;wire[31:0]cd,rd;wire[3:0]cs;
    gw138k_apb_cdc clock_cdc(.reset_n(rst_n && preset_n),.pclk(pclk),.audio_clk(control_clk),
        .psel(cpsel),.penable(cpenable),.pwrite(cpwrite),.paddr(cpaddr),.pwdata(cpdata),.pstrb(4'hf),
        .pready(cpready),.pslverr(cperror),.prdata(cpread),.command_reset_n(clock_reset_n),
        .command_valid(cv),.command_ready(cr),.command_write(cw),.command_address(ca),
        .command_data(cd),.command_strobes(cs),.response_data(rd),.response_error(ce));
    workstation_audio_clock_service #(.ENABLE_PUSH_RATE_CONTROL(1),.ENABLE_MEDIA_POLICY(1),
        .RESERVE_ZERO_EPOCH(1),.RESULT_TIMEOUT_CYCLES(4000000)) service(
        .clk_i(control_clk),.reset_ni(clock_reset_n),.command_valid_i(cv),.command_write_i(cw),
        .command_address_i(ca),.command_data_i(cd),.command_strobes_i(cs),.command_ready_o(cr),
        .response_data_o(rd),.response_error_o(ce),.push_toggle_i(transported_pulse),
        .push_generation_i(transported_generation),.push_ready_o(service_ready),.push_generation_o(generation),
        .push_rejected_o(service_reject),.service_busy_o(service_busy),.service_fault_o(service_fault),
        .switch_permit_i(permit),.core_request_ready_i(ready),.core_busy_i(busy),.core_fault_i(fault),
        .core_dsp_fault_i(dsp_fault),.core_accepted_i(accepted),.core_applied_i(applied),
        .core_rejected_i(rejected),.core_policy_rejected_i(policy_rejected),.core_failed_i(failed),
        .core_reject_code_i(reject_code),.core_fault_code_i(fault_code),.core_active_44k1_i(rate),
        .core_active_valid_i(active_valid),.core_stream_epoch_i(epoch),.core_source_qualified_i(qualified),
        .request_o(request),.request_44k1_o(request44),.recover_o(recover),
        .media_stop_request_o(media_req),.media_stop_hold_o(media_hold),.media_stop_ready_i(media_ready),
        .media_stop_done_i(media_done),.media_stop_failed_i(media_failed),.media_stop_failure_code_i(media_code));
    reg [31:0] physical_pcm[0:15][0:8191];
    reg physical_seen[0:15][0:8191],physical_error[0:15][0:8191],physical_rate[0:15][0:8191];
    reg [31:0] decoded=0,last_decoded=0;
    integer position=0,physical_frames=0,observed_frames=0,display_frames=0,nonzero=0,nonzero48=0,nonzero44=0,seen48=0,seen44=0;
    integer requests=0,recovers=0,accepts=0,applies=0,failures=0,pulses=0,rejects=0,transport_rejects=0;
    integer fifo_writes=0,usb_events=0,clock_apb=0,held_checks=0,tail_checks=0,panic_checks=0,busy_checks=0;
    integer mute_edges=0,prefill_edges=0,dcs_off_edges=0;
    reg expected_fault=0;
    always @(negedge dut.runtime.serial_reset_n)begin position=0;decoded=0;last_decoded=0;end
    always @(posedge bck)begin
        #0.1;
        if(dut.runtime.serial_reset_n)begin
            if(lrck!==(position>=32))$fatal(1,"I2S LRCK disagrees with decoded stereo slot");
            if(position>=1 && position<=16)decoded[32-position]=sd;
            else if(position>=33 && position<=48)decoded[48-position]=sd;
            else if(sd!==0)$fatal(1,"I2S nonzero padding");
            if(position==63)begin last_decoded=decoded;decoded=0;position=0;end
            else position++;
        end
    end
    always @(negedge mclk)if(rst_n && frame_valid)begin
        if(frame_epoch>=16 || frame_sequence>=8192 || frame_pcm!==last_decoded)$fatal(1,"physical serial PCM/context mismatch");
        physical_seen[frame_epoch][frame_sequence]=1;physical_pcm[frame_epoch][frame_sequence]=last_decoded;
        physical_error[frame_epoch][frame_sequence]=frame_error;physical_rate[frame_epoch][frame_sequence]=frame_rate;
        physical_frames++;
    end
    always @(negedge compute_clk)if(rst_n && sample_valid)begin
        if(!physical_seen[dut.observed_epoch][dut.observed_sequence] ||
            {audio_left[31:16],audio_right[31:16]}!==physical_pcm[dut.observed_epoch][dut.observed_sequence] ||
            audio_left[15:0]!=0 || audio_right[15:0]!=0 ||
            dut.observed_rate!==physical_rate[dut.observed_epoch][dut.observed_sequence])
            $fatal(1,"observer does not carry physically decoded PCM");
        observed_frames++;
        if(audio_left!=0 || audio_right!=0)begin
            nonzero++;if(dut.observed_rate)nonzero44++;else nonzero48++;
        end
        if(dut.observed_rate)seen44++;else seen48++;
    end
    always @(negedge control_clk)if(rst_n)begin
        if(display_valid)begin
            if(!physical_seen[display_epoch][display_sequence] ||
               display_pcm!==physical_pcm[display_epoch][display_sequence] ||
               display_rate!==physical_rate[display_epoch][display_sequence] ||
               display_error!==physical_error[display_epoch][display_sequence])$fatal(1,"display differs from physical PCM/context");
            display_frames++;
        end
        if(!expected_fault && (fault || dsp_fault || display_observation_fault || underruns!=0 || observation_drops!=0))
            $fatal(1,"unexpected runtime fault/drop fault=%b dsp=%b display=%b under=%d drop=%d",fault,dsp_fault,display_observation_fault,underruns,observation_drops);
        if(request)begin
            if(request44!==!rate)$fatal(1,"Push request did not toggle actual committed rate");
            requests++;
        end
        if(recover)recovers++;if(accepted)accepts++;if(applied)applies++;if(failed)failures++;
        if(service_reject)transport_rejects++;
        if(smute)mute_edges++;
        if(dut.runtime.clock_select_o==0)dcs_off_edges++;
        if(dut.runtime.serial_prefill)prefill_edges++;
    end
    always @(posedge usb_clk)if(rst_n)begin
        if(usb_pulse)pulses++;if(usb_reject)rejects++;if(usb.events.w_en)fifo_writes++;
        if(sel && wr && addr==4 && wd[15:0]==16'hb00b && wd[23:16]==51 &&
           (usb.midi.usb_valid || usb.events.w_en))$fatal(1,"rate control entered normal audio FIFO");
    end
    always @(posedge compute_clk)if(rst_n && usb_valid && usb_ready && consume)usb_events++;
    task ticks(input integer n);repeat(n)@(negedge control_clk);endtask
    task frames(input integer n);integer goal;begin goal=observed_frames+n;wait(observed_frames>=goal);@(negedge compute_clk);end endtask
    task put(input[7:0]a,input[31:0]d,input integer limit);
        integer n;
        begin
            @(negedge usb_clk);sel=1;wr=1;addr=a;wd=d;n=0;
            do begin @(posedge usb_clk);n++;if(n>limit)$fatal(1,"real USB MMIO backpressure addr=%h",a);end while(!mmio_ready);
            @(negedge usb_clk);sel=0;wr=0;
        end
    endtask
    task cc(input[6:0]a,input[6:0]v);
        begin
            put(4,{1'b0,v,1'b0,a,16'hb00b},2000);
            // Production 48-MHz release qualification: keep the real 5-ms
            // interval. Startup mute is 512 frames so a qualified second
            // press still occurs inside an actual hardware transaction.
            if(a==51 && v==0)repeat(240002)@(negedge usb_clk);
        end
    endtask
    task note(input bit onoff,input[6:0]n,input[6:0]v);put(4,{1'b0,v,1'b0,n,onoff ? 16'h9009:16'h8008},2000);endtask
    task ready_wait;
        integer n;
        begin n=0;while(!service_ready || !source_ready)begin ticks(1);n++;if(n>4000000)$fatal(1,"clock service never ready phase=%d busy=%b fault=%b dsp=%b",service.phase,busy,fault,dsp_fault);end end
    endtask
    task applied_rate(input bit want,input integer count);
        integer start_epoch;
        begin
            start_epoch=0;
            while(!active_valid || rate!==want || requests!=count || !service_ready || service_busy)begin
                ticks(1);start_epoch++;
                if(start_epoch>4000000 || requests>count)$fatal(1,"rate completion timeout/extra request actual=%b want=%b count=%d expected=%d",rate,want,requests,count);
            end
            ticks(20);
            if(!active_valid || rate!==want || requests!=count || service.result_code!=1)
                $fatal(1,"transaction actual rate=%b want=%b requests=%d expected=%d result=%d",rate,want,requests,count,service.result_code);
            frames(8);
        end
    endtask
    task clock_command(input[31:0]op);
        integer n;
        begin
            @(negedge pclk);cpsel=1;cpenable=0;cpwrite=1;cpaddr=12'h008;cpdata=op;
            @(negedge pclk);cpenable=1;n=0;
            do begin @(posedge pclk);#0.1;n++;if(n>10000)$fatal(1,"APB clock timeout");end while(!cpready);
            if(cperror)$fatal(1,"APB clock command rejected op=%d response=%h",op,cpread);
            @(negedge pclk);cpsel=0;cpenable=0;clock_apb++;
        end
    endtask
    integer q0,p0,r0,e0,n,w0,fill;reg full_seen;reg[127:0]held_before;reg[31:0]state_before,pitch_before,options_before;
    initial begin
        for(integer e=0;e<16;e++)for(integer s=0;s<8192;s++)physical_seen[e][s]=0;
        repeat(8)@(negedge control_clk);rst_n=1;preset_n=1;
        ready_wait();put(0,1,10);repeat(13000)@(negedge usb_clk);frames(8);
        if(usb.push_warmup!=0 || !usb.queue_write_ready)$fatal(1,"real USB owner did not finish warmup");
        cc(20,127);cc(21,127);cc(22,127);frames(8);
        if(display_effect_mask!=7)$fatal(1,"real Push effect chain did not reach owner");
        note(1,60,100);frames(192);
        if(!held[60] || active==0 || nonzero==0)$fatal(1,"real Push note failed to reach DSP/I2S");
        held_before=held;state_before=control_state;pitch_before=control_pitch;options_before=options;
        q0=requests;p0=pulses;e0=int'(epoch);cc(51,127);wait(service_busy);wait(busy);
        cc(51,127);cc(51,1);cc(51,0);r0=rejects;cc(51,127);ticks(20);
        if(rejects!=r0+1)$fatal(1,"busy physical press was not consumed/rejected");
        applied_rate(1,q0+1);frames(4);
        if(epoch!=32'(e0+1) || held!==held_before || control_state!=state_before || control_pitch!=pitch_before || options!=options_before)
            $fatal(1,"48->44.1 switch lost committed musical state");held_checks++;
        cc(51,127);frames(4);if(requests!=q0+1 || pulses!=p0+1)$fatal(1,"held/busy press replayed after completion");busy_checks++;
        cc(51,0);frames(2);if(requests!=q0+1)$fatal(1,"release triggered transaction");
        cc(51,127);applied_rate(0,q0+2);if(!held[60])$fatal(1,"44.1->48 lost held note");held_checks++;
        // Release keeps a genuine ADSR/effect tail. A clock transaction must
        // complete without treating that non-idle DSP as a blocked command.
        note(0,60,0);frames(1);if(held[60] || active==0)$fatal(1,"real release tail not present");
        cc(51,0);cc(51,127);applied_rate(1,q0+3);tail_checks++;
        // PANIC remains the actual USB priority path and clears held/voices.
        cc(27,127);frames(6);if(held!=0 || active!=0)$fatal(1,"real Push PANIC did not clear owner");panic_checks++;
        // Select retains vector entry, independent of the new Session action.
        cc(48,127);frames(6);if(!dut.runtime.scope_status_o[8])$fatal(1,"Select no longer enters vector source");
        cc(48,0);cc(48,127);frames(6);if(dut.runtime.scope_status_o[8])$fatal(1,"Select no longer leaves vector source");
        // Fill the actual generated async queue by withholding only its
        // ordinary consumer handshake; clock switching remains independent.
        consume=0;full_seen=0;fill=0;
        begin:fill_queue
            for(integer k=0;k<160;k++)begin
                @(negedge usb_clk);sel=1;wr=1;addr=4;wd={1'b0,7'd1,1'b0,7'd71,16'hb00b};n=0;
                begin:wait_normal
                    forever begin
                        @(posedge usb_clk);n++;
                        if(mmio_ready)begin fill++;disable wait_normal;end
                        if(n==30)begin full_seen=1;disable wait_normal;end
                    end
                end
                @(negedge usb_clk);sel=0;wr=0;if(full_seen)disable fill_queue;
            end
        end
        if(!full_seen || usb.fifo_ready || fill<32)$fatal(1,"real queue did not fill fill=%d",fill);
        q0=requests;w0=fifo_writes;cc(51,0);cc(51,127);wait(busy);cc(51,0);r0=rejects;cc(51,127);
        applied_rate(0,q0+1);if(usb.fifo_ready || fifo_writes!=w0 || rejects!=r0+1)$fatal(1,"rate depended on full audio queue");
        frames(4);if(requests!=q0+1)$fatal(1,"backpressured busy press replayed");busy_checks++;
        consume=1;frames(12);ready_wait();cc(51,0);
        // Lose the target crystal after genuine hardware acceptance. The
        // failure uses monitor/DCS/DSP state, never a synthetic ACK/status.
        q0=requests;e0=int'(epoch);expected_fault=1;cc(51,127);wait(accepted);
        @(negedge reference44);run44=0;wait(fault);ticks(12);
        if(!service_fault || active_valid || !smute || failures==0 || rate || epoch!=32'(e0))
            $fatal(1,"target crystal loss did not fail/mute without fake commit");
        r0=rejects;cc(51,0);cc(51,127);ticks(20);
        if(rejects!=r0+1 || requests!=q0+1)$fatal(1,"fault press admitted recovery");
        run44=1;wait(qualified==3);ticks(20);clock_command(2);wait(!fault && !busy && active_valid);
        ready_wait();frames(16);if(recovers!=1 || rate || epoch!=32'(e0+1) || service.result_code!=1)$fatal(1,"existing APB recovery did not restore physical stream");
        expected_fault=0;cc(51,0);cc(51,127);applied_rate(1,q0+2);
        if(physical_frames<300 || observed_frames<300 || seen48<128 || seen44<32 || display_frames<100 ||
           nonzero48<16 || nonzero44<8 || writes==0 || reads==0 || mute_edges==0 || dcs_off_edges==0 || prefill_edges==0 ||
           busy_checks!=2 || held_checks!=2 || tail_checks!=1 || panic_checks!=1 || clock_apb!=1)
            $fatal(1,"missing real runtime coverage");
        if(physical_period48_checks<128 || physical_period44_checks<32 || mute_policy_checks==0 ||
           prefill_commit_checks!=applies || committed_context_checks!=applies)
            $fatal(1,"missing independent physical period/mute/prefill/commit checks");
        $display("PASS independent_physical_clock period48_checks=%0d period44_checks=%0d tolerance_ns=1 mute_policy_checks=%0d prefill_commit_checks=%0d committed_context_checks=%0d",physical_period48_checks,physical_period44_checks,mute_policy_checks,prefill_commit_checks,committed_context_checks);
        $display("PASS push_rate_runtime physical_frames=%0d observed_frames=%0d observed48=%0d observed44=%0d display_frames=%0d nonzero=%0d nonzero48=%0d nonzero44=%0d USB_events=%0d USB_pulses=%0d source_rejects=%0d transport_rejects=%0d requests=%0d recovers=%0d accepts=%0d applies=%0d failures=%0d full_FIFO_fill=%0d held_checks=%0d tail_checks=%0d panic_checks=%0d busy_checks=%0d DDR_writes=%0d DDR_reads=%0d mute_edges=%0d prefill_edges=%0d DCS_off_edges=%0d",physical_frames,observed_frames,seen48,seen44,display_frames,nonzero,nonzero48,nonzero44,usb_events,pulses,rejects,transport_rejects,requests,recovers,accepts,applies,failures,fill,held_checks,tail_checks,panic_checks,busy_checks,writes,reads,mute_edges,prefill_edges,dcs_off_edges);
        $finish;
    end
    realtime previous_physical_time=0,physical_period=0,expected_period=0;
    reg [31:0] previous_physical_epoch=32'hffffffff,previous_physical_sequence=0;
    integer physical_period48_checks=0,physical_period44_checks=0;
    integer mute_policy_checks=0,prefill_commit_checks=0,committed_context_checks=0;
    reg committed_seen=0,previous_committed_rate=0,transaction_prefill_seen=0;
    reg [31:0] previous_committed_epoch=0;
    // This oracle measures elapsed physical serial-frame time, independently
    // of the serializer's frame-rate label and compute/display observations.
    // A new epoch or nonconsecutive frame starts a fresh measurement window.
    always @(negedge mclk)if(rst_n && frame_valid)begin
        if(frame_epoch==previous_physical_epoch && frame_sequence==previous_physical_sequence+1)begin
            physical_period=$realtime-previous_physical_time;
            expected_period=frame_rate ? 22675.73696 : 20833.333248;
            if(physical_period<expected_period-1.0 || physical_period>expected_period+1.0)
                $fatal(1,"independent physical frame period disagrees with rate period=%f expected=%f rate=%b",physical_period,expected_period,frame_rate);
            if(frame_rate)physical_period44_checks++;else physical_period48_checks++;
        end
        previous_physical_time=$realtime;
        previous_physical_epoch=frame_epoch;previous_physical_sequence=frame_sequence;
    end
    always @(negedge control_clk)if(rst_n && dut.reset_50_n)begin
        // QUIESCE finishes the whole in-flight frame before its own mute ACK;
        // RESUME unmutes to prove physical running before committing RUN.
        // Stop/select/qualify/prefill and FAULT must keep actual DAC mute set.
        if(fault || (busy && dut.runtime.clocks.transaction.state!=4'd2 &&
                            dut.runtime.clocks.transaction.state!=4'd9))begin
            if(!smute)$fatal(1,"actual DAC SMUTE released during stopped/qualifying/prefill or fault");
            mute_policy_checks++;
        end
        if(request || recover)transaction_prefill_seen=0;
        if(dut.runtime.clocks.transaction.state==4'd7 &&
           dut.runtime.prefill_sync[1] && dut.runtime.context_ready_o)transaction_prefill_seen=1;
        if(applied)begin
            if(!dut.runtime.context_ready_o || !dut.runtime.running_sync[1] ||
               !transaction_prefill_seen || !active_valid || busy || fault)
                $fatal(1,"committed clock transaction bypassed actual DSP context/prefill/serial running");
            prefill_commit_checks++;
        end
        if(committed_seen && (rate!=previous_committed_rate || epoch!=previous_committed_epoch))begin
            if(!applied)$fatal(1,"public committed clock identity changed without hardware applied");
            committed_context_checks++;
        end
        previous_committed_rate=rate;previous_committed_epoch=epoch;committed_seen=1;
    end
    initial begin #250000000;$fatal(1,"push rate runtime watchdog");end
endmodule
