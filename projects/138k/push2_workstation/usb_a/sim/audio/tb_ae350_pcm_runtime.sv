`timescale 1ns/1ps
module tb_ae350_pcm_runtime #(parameter bit D_ONLY_MODE=0);
`include "sim/audio/fixtures/d_process_before_exact_mask.svh"
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
    wire pready,pslverr,normal_ready,normal_error,pcm_ready,pcm_error;
    wire [31:0] prdata,normal_data,pcm_data;
    reg pcm_page=0,hci_ready=1;
    reg [31:0] hci_epoch=11,hci_generation=22;
    assign pready=pcm_page ? pcm_ready:normal_ready;
    assign pslverr=pcm_page ? pcm_error:normal_error;
    assign prdata=pcm_page ? pcm_data:normal_data;
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
        .RESERVE_ZERO_EPOCH(1),.ENABLE_AE350_PCM(1),
        .SYNTH_ENGINES_ENABLE(!D_ONLY_MODE),.D_ONLY_ENABLE(D_ONLY_MODE),
        .LOCAL_RECORD_ENABLE(!D_ONLY_MODE),.LOCAL_SCORE_ENABLE(!D_ONLY_MODE)) dut(
        .common_reset_ni(1'b1),.rst_ni(rst_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .reference_48_i(reference48),.reference_44_i(reference44),.midi_rx_i(midi_rx),.pc_uart_rx_i(pc_rx),
        .usb_event_valid(usb_valid),.usb_lifecycle,.usb_cancel,.usb_event_data(usb_data),.usb_event_ready(usb_ready),
        .pclk,.preset_n,.psel(psel && !pcm_page),.penable,.pwrite,.paddr,.pwdata,.pstrb,
        .pready(normal_ready),.pslverr(normal_error),.prdata(normal_data),.performance_words_o(performance),
        .request_i(request),.request_44k1_i(request44),.switch_permit_i(permit),.recover_i(1'b0),.media_quiescent_i(1'b1),
        .request_ready_o(ready),.busy_o(busy),.fault_o(fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(),.failed_o(),.policy_rejected_o(policy_rejected),.reject_code_o(),.fault_code_o(),.clock_select_o(),
        .switch_block_reason_o(block_reason),.active_44k1_o(rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),
        .source_qualified_o(),.quiesce_o(),.stream_flush_o(),.dsp_fault_o(),.context_ready_o(),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(1'b0),
        .pcm_psel_i(psel && pcm_page),.pcm_pready_o(pcm_ready),.pcm_pslverr_o(pcm_error),.pcm_prdata_o(pcm_data),
        .hci_session_ready_i(hci_ready),.hci_controller_epoch_i(hci_epoch),.hci_transport_generation_i(hci_generation),
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
        .effect_mask_o(display_effect_mask),.effect_order_o(display_effect_order),.display_observation_fault_o(display_observation_fault),
        .media_stop_request_i(1'b0),.media_stop_hold_i(1'b0),.media_stop_ready_o(),.media_stop_done_o(),.media_stop_failed_o(),
        .media_stop_failure_code_o(),.tf_stop_request_o(),.tf_stop_pending_i(1'b0),.tf_stop_done_i(1'b0),.tf_stop_failed_i(1'b0),.tf_stop_failure_code_i(4'd0));
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
    integer physical_frames=0,physical_good=0,physical_nonzero=0,physical_errors=0,matched_pcm=0,matched_half=0;
    integer position=0,serial_checks=0,history_clears=0,effect_results=0;
    integer d_snapshots=0,d_panic_cases=0,d_inflight_panics=0,d_display_checks=0;
    integer d_dry[0:1],d_driven[0:1],d_crushed[0:1],d_wet[0:1],d_panics[0:1];
    reg signed [31:0] expected_capture_l,expected_capture_r,target_crush_l,target_crush_r;
    reg [31:0] target_crushed;
    reg [31:0] completed_pcm[0:4095],completed_epoch[0:4095];
    reg completed_rate[0:4095],completed_error[0:4095],completed_valid[0:4095];
    reg [31:0] decoded=0,last_decoded=0;
    reg [31:0] d_previous_underruns=0;
    always @(negedge mclk)if(rst_n && D_ONLY_MODE)begin
        if(underruns!=d_previous_underruns)
            $display("D_SERIAL_UNDERRUN t=%0t rate=%0d old=%0d new=%0d owner=%0d history=%0d hold=%0d guard=%0d playing=%0d have_next=%0d requested=%0d seq=%0d resume=%0d quiesce=%0d",$time,rate,d_previous_underruns,underruns,dut.runtime.cpu_pcm.owner.selected_o,dut.runtime.cpu_pcm.owner.history_state,dut.runtime.serializer.source_hold,dut.runtime.serializer.source_guard,dut.runtime.serializer.playing,dut.runtime.serializer.have_next,dut.runtime.serializer.requested,dut.runtime.serializer.wanted_sequence,dut.runtime.serial_resume[1],dut.runtime.serial_quiesce[1]);
        d_previous_underruns=underruns;
    end
    always @(negedge dut.runtime.serial_reset_n)begin position=0;decoded=0;last_decoded=0;end
    always @(posedge bck)begin #0.1;if(dut.runtime.serial_reset_n)begin
        if(lrck!==(position>=32))$fatal(1,"I2S LRCK");
        if(position>=1 && position<=16)decoded[32-position]=sd;
        else if(position>=33 && position<=48)decoded[48-position]=sd;
        else if(sd!==0)$fatal(1,"I2S padding");
        if(position==63)begin last_decoded=decoded;decoded=0;position=0;end else position=position+1;
    end end
    always @(negedge mclk)if(frame_valid)begin
        if(frame_pcm!==last_decoded)$fatal(1,"physical completed tap differs from pins");
        physical_frames=physical_frames+1;serial_checks=serial_checks+1;
        if(frame_error)physical_errors=physical_errors+1;
        else begin physical_good=physical_good+1;if(frame_pcm!=0)physical_nonzero=physical_nonzero+1;end
        if(frame_pcm=={16'sd8000,-16'sd6000}&&!frame_error)matched_pcm=matched_pcm+1;
        if(frame_pcm=={16'sd4000,-16'sd3000}&&!frame_error)matched_half=matched_half+1;
        if(D_ONLY_MODE && !frame_error)begin
            if(frame_pcm=={16'sd8000,-16'sd6000})d_dry[frame_rate]=d_dry[frame_rate]+1;
            if(frame_pcm=={16'sd16000,-16'sd12000})d_driven[frame_rate]=d_driven[frame_rate]+1;
            if(frame_pcm==target_crushed)d_crushed[frame_rate]=d_crushed[frame_rate]+1;
            if(display_effect_mask==7 && frame_pcm!=0)d_wet[frame_rate]=d_wet[frame_rate]+1;
        end
        if(D_ONLY_MODE)begin
            completed_pcm[frame_sequence[11:0]]=frame_pcm;completed_epoch[frame_sequence[11:0]]=frame_epoch;
            completed_rate[frame_sequence[11:0]]=frame_rate;completed_error[frame_sequence[11:0]]=frame_error;
            completed_valid[frame_sequence[11:0]]=1;
        end
    end
    always @(posedge control_clk)if(rst_n && D_ONLY_MODE && display_valid)begin
        if(!completed_valid[display_sequence[11:0]] || completed_pcm[display_sequence[11:0]]!==display_pcm ||
           completed_epoch[display_sequence[11:0]]!==display_epoch || completed_rate[display_sequence[11:0]]!==display_rate ||
           completed_error[display_sequence[11:0]]!==display_error)
            $fatal(1,"D display context/PCM snapshot disagrees with completed I2S frame");
        d_display_checks=d_display_checks+1;
    end
    always @(posedge compute_clk)begin
        if(dut.runtime.pcm_history_request && dut.runtime.pcm_history_ready && !dut.runtime.config_valid)history_clears=history_clears+1;
        if(dut.runtime.service.workstation.runtime_effects.effects.chorus_valid &&
            dut.runtime.service.workstation.runtime_effects.effects.chorus_stage.product_l!=0)effect_results=effect_results+1;
    end
    // Compare the real accepted-slot PCM and real committed controls on the
    // original core_ce edge, then inspect the actual held samples after NBA.
    // This catches moving either parameter or PCM sampling to another cycle.
    always @(posedge compute_clk)if(rst_n && D_ONLY_MODE)begin
        if(dut.runtime.service.workstation.panic_accept)begin
            d_panics[rate]=d_panics[rate]+1;
            if(dut.runtime.service.workstation.frame_inflight)d_inflight_panics=d_inflight_panics+1;
        end
        if(dut.runtime.service.workstation.core_ce)begin
            expected_capture_l=d_process_old_reference(dut.runtime.service.workstation.pcm_left_i,
                dut.runtime.service.workstation.d_crush,dut.runtime.service.workstation.d_drive);
            expected_capture_r=d_process_old_reference(dut.runtime.service.workstation.pcm_right_i,
                dut.runtime.service.workstation.d_crush,dut.runtime.service.workstation.d_drive);
            #0.1;
            if(dut.runtime.service.workstation.held_pcm_l!==expected_capture_l ||
               dut.runtime.service.workstation.held_pcm_r!==expected_capture_r)
                $fatal(1,"D core_ce PCM/parameter snapshot differs from actual old function");
            d_snapshots=d_snapshots+1;
        end
    end
    reg [31:0] value;
    task apb(input bit page,wr,input integer addr,input [31:0] data,input bit expected_error);
        integer n;begin
        @(negedge pclk);pcm_page=page;psel=1;penable=0;pwrite=wr;paddr=12'(addr);pwdata=data;
        @(negedge pclk);penable=1;n=0;
        do begin @(posedge pclk);#0.1;n=n+1;end while(!pready&&n<10000);
        if(!pready||pslverr!==expected_error)$fatal(1,"APB page=%b write=%b addr=%h err=%b expected=%b",page,wr,addr,pslverr,expected_error);
        value=prdata;@(negedge pclk);psel=0;penable=0;
    end endtask
    task cw(input integer addr,input [31:0] data);apb(1,1,addr,data,0);endtask
    task event_cpu(input integer kind,addr,data);apb(0,1,'h180,{14'd0,4'(kind),7'(addr),7'(data)},0);endtask
    task key(input integer stream);begin
        cw('h020,hci_epoch);cw('h024,hci_generation);cw('h028,stream);cw('h02c,rate ? 44100:48000);cw('h030,epoch);
    end endtask
    integer block_sequence=0;
    task block;
        integer slot;begin
        slot=block_sequence%4;
        wait(!dut.runtime.cpu_pcm.owner.owned[slot]);
        for(integer i=0;i<128;i=i+1)cw('h800+slot*512+i*4,{-16'sd6000,16'sd8000});
        cw('h034,slot);cw('h038,128);cw('h03c,block_sequence);cw('h040,2);block_sequence=block_sequence+1;
    end endtask
    task begin_stream(input integer stream);begin
        key(stream);cw('h040,1);block_sequence=0;block();block();block();cw('h040,3);
        wait(dut.runtime.cpu_pcm.owner.history_state==0 && dut.runtime.cpu_pcm.owner.selected_o);
    end endtask
    task frames(input integer n);integer target;begin target=physical_frames+n;wait(physical_frames>=target);@(negedge compute_clk);end endtask
    task d_panic(input integer phase);integer previous,previous_underruns;begin
        previous=d_panics[rate];
        previous_underruns=underruns;
        wait(dut.runtime.render_request && dut.runtime.service_ready);
        repeat(phase)@(negedge compute_clk);
        @(negedge compute_clk);usb_data={4'd15,7'd0,7'd0};usb_valid=1;usb_lifecycle=1;usb_cancel=1;
        @(posedge compute_clk);if(!usb_ready)$fatal(1,"D USB lifecycle fixture missed valid/ready");
        @(negedge compute_clk);usb_valid=0;usb_lifecycle=0;usb_cancel=0;
        frames(8);
        if(underruns!=previous_underruns)
            $display("D_CANCEL_UNDERRUN rate=%0d phase=%0d before=%0d after=%0d",rate,phase,previous_underruns,underruns);
        if(d_panics[rate]!=previous+1 || options[20:0]!=0 || fault)
            $fatal(1,"D public lifecycle/PANIC did not cancel and restore D controls phase=%0d rate=%0d before=%0d after=%0d options=%h fault=%0d",phase,rate,previous,d_panics[rate],options,fault);
        d_panic_cases=d_panic_cases+1;
    end endtask
    integer old_nonzero,old_history,old_frames;
    reg [127:0] saved_held;
    reg [31:0] saved_control,saved_options;
    initial begin
        for(integer i=0;i<2;i=i+1)begin d_dry[i]=0;d_driven[i]=0;d_crushed[i]=0;d_wet[i]=0;d_panics[i]=0;end
        target_crush_l=d_process_old_reference(32'sd8000<<<16,7'd64,7'd16);
        target_crush_r=d_process_old_reference(-32'sd6000<<<16,7'd64,7'd16);
        target_crushed={target_crush_l[31:16],target_crush_r[31:16]};
        for(integer i=0;i<4096;i=i+1)begin memory[i]=0;completed_valid[i]=0;end
        #137;rst_n=1;preset_n=1;wait(active_valid && !busy && ready);frames(3);
        apb(1,0,'h008,0,0);if(value!==(D_ONLY_MODE ? 32'h6f:32'h67))$fatal(1,"PCM owner capabilities");
        apb(1,0,'h06c,0,0);if(value!==0)$fatal(1,"unknown delay marked valid");
        if(D_ONLY_MODE)begin
            frames(280);
            for(integer rate_index=0;rate_index<2;rate_index=rate_index+1)begin
                if(rate_index==1)begin
                    request44=1;@(negedge control_clk);request=1;@(negedge control_clk);request=0;
                    wait(active_valid && !busy && rate);frames(8);
                end
                // History/rate changes intentionally retain effect controls
                // and wet gains. Set the dry baseline through real commands
                // and allow the unchanged wet slew to settle before comparing
                // an exact dry drive/crush target on the next owner stream.
                event_cpu(2,81,0);frames(80);
                begin_stream(rate_index+1);frames(100);
                if(d_dry[rate_index]<32)$fatal(1,"D dry PCM failed actual owner/effects/I2S");
                event_cpu(2,21,16);frames(32);
                if(options[13:7]!=16 || d_driven[rate_index]<16)$fatal(1,"D real committed drive vs I2S mismatch");
                event_cpu(2,20,64);frames(32);
                if(options[6:0]!=64 || d_crushed[rate_index]<16)$fatal(1,"D real committed crush vs I2S mismatch rate=%0d count=%0d options=%h",rate_index,d_crushed[rate_index],options);
                event_cpu(2,20,0);event_cpu(2,21,0);event_cpu(2,81,7);
                // The unchanged production chorus needs up to576 prior
                // frames after the actual owner history clear. Keep feeding
                // real APB blocks until a nonzero wet product can be observed.
                for(integer chunk=0;chunk<5;chunk=chunk+1)begin block();frames(100);end
                if(display_effect_mask!=7 || d_wet[rate_index]<16 || effect_results==0)
                    $fatal(1,"D complete real effects chain or I2S lost mask=%0d wet=%0d products=%0d",display_effect_mask,d_wet[rate_index],effect_results);
                for(integer phase=0;phase<6;phase=phase+1)d_panic(phase);
                key(rate_index+1);cw('h040,5);wait(!dut.runtime.cpu_pcm.owner.serial_hold_o);frames(8);
            end
            if(fault || observation_drops!=0 || record_drops!=0 || midi_drops!=0 || active!=0 ||
               underruns!=0 || display_observation_fault || dut.runtime.service.workstation.deadline_miss_o!=0 ||
               d_snapshots<512 || d_display_checks<512 || d_panic_cases!=12 || d_inflight_panics<2 || d_panics[0]<6 || d_panics[1]<6)
                $fatal(1,"D physical snapshot/PANIC coverage or health failure snapshots=%0d display=%0d cases=%0d inflight=%0d panics48=%0d panics44=%0d fault=%0d observe_drop=%0d record_drop=%0d midi_drop=%0d voices=%0d underruns=%0d display_fault=%0d deadline=%0d",d_snapshots,d_display_checks,d_panic_cases,d_inflight_panics,d_panics[0],d_panics[1],fault,observation_drops,record_drops,midi_drops,active,underruns,display_observation_fault,dut.runtime.service.workstation.deadline_miss_o);
            $display("PASS D real APB/CDC owner, exact old core_ce snapshots, complete effects, I2S both rates/PANIC: physical=%0d snapshots=%0d display_snapshots=%0d panic_cases=%0d inflight_panics=%0d dry48=%0d dry44=%0d drive48=%0d drive44=%0d crush48=%0d crush44=%0d wet48=%0d wet44=%0d",physical_frames,d_snapshots,d_display_checks,d_panic_cases,d_inflight_panics,d_dry[0],d_dry[1],d_driven[0],d_driven[1],d_crushed[0],d_crushed[1],d_wet[0],d_wet[1]);
            $finish;
        end
        event_cpu(2,16,127);event_cpu(2,81,0);frames(280);begin_stream(1);frames(100);
        if(matched_pcm<32)$fatal(1,"actual block PCM did not reach existing effects/final volume/I2S: %d",matched_pcm);
        // Half master gain must yield half PCM, detecting accidental double volume.
        event_cpu(2,7,64);frames(100);if(matched_half<32)$fatal(1,"PCM master volume applied more than once");
        event_cpu(2,7,127);frames(70);
        event_cpu(1,60,100);wait(held[60]);event_cpu(2,81,2);
        for(integer i=0;i<8;i=i+1)block();frames(32);
        if(effect_results==0)$fatal(1,"BT input bypassed actual chorus");
        saved_held=held;saved_control=control_state;saved_options=options;old_history=history_clears;old_nonzero=physical_nonzero;
        key(1);cw('h040,5);wait(!dut.runtime.cpu_pcm.owner.serial_hold_o);frames(12);
        if(dut.runtime.cpu_pcm.owner.selected_o||held!==saved_held||control_state!==saved_control||options!==saved_options)
            $fatal(1,"source cancel changed held notes or common parameters");
        if(history_clears<=old_history||physical_nonzero<=old_nonzero)$fatal(1,"cancel failed to clear BT history or resume MIDI");
        begin_stream(2);frames(16);saved_held=held;saved_control=control_state;old_frames=physical_frames;
        // Reset the actual CPU interface while a held APB command is in flight.
        @(negedge pclk);pcm_page=1;psel=1;penable=0;pwrite=1;paddr='h820;pwdata=32'hdeadbeef;
        @(negedge pclk);penable=1;wait(dut.pcm_command_valid);#0.1;preset_n=0;
        @(negedge pclk);psel=0;penable=0;repeat(8)@(negedge pclk);preset_n=1;
        wait(!dut.runtime.cpu_pcm.owner.serial_hold_o);frames(12);
        if(!dut.runtime.cpu_pcm.owner.failed_o||dut.runtime.cpu_pcm.owner.selected_o||held!==saved_held||control_state!==saved_control)
            $fatal(1,"CPU reset revived BT or reset audio owner");
        key(2);apb(1,1,'h040,1,1);
        begin_stream(3);frames(16);hci_ready=0;frames(12);
        if(!dut.runtime.cpu_pcm.owner.failed_o||dut.runtime.cpu_pcm.owner.selected_o)$fatal(1,"controller fence waited on CPU");
        hci_generation=23;hci_ready=1;repeat(12)@(negedge compute_clk);
        begin_stream(1);frames(16);key(3);cw('h024,22);apb(1,1,'h040,5,1); // Old PL generation cannot cancel new owner.
        key(1);cw('h040,5);wait(!dut.runtime.cpu_pcm.owner.serial_hold_o);frames(8);
        event_cpu(0,60,0);frames(32);tf_active=1;tf_rate=48000;frames(16);tf_active=0;frames(8);
        request44=1;@(negedge control_clk);request=1;@(negedge control_clk);request=0;
        wait(active_valid && !busy && rate);frames(8);
        begin_stream(2);frames(48);
        if(fault||observation_drops!=0||record_drops!=0||midi_drops!=0)$fatal(1,"runtime fault or observer loss");
        if(history_clears<8||serial_checks<1000)$fatal(1,"insufficient real source switch coverage");
        $display("PASS AE350 PCM real APB/CDC owner, DSP/chorus, one-volume final PCM, I2S, MIDI retention, CPU/session fence, TF and both rates: physical=%d good=%d errors=%d direct_pcm=%d half_pcm=%d history=%d wet=%d",physical_frames,physical_good,physical_errors,matched_pcm,matched_half,history_clears,effect_results);
        $finish;
    end
    initial begin #200000000;$fatal(1,"PCM runtime timeout");end
endmodule
