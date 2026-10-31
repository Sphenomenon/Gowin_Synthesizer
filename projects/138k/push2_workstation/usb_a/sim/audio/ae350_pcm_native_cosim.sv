`timescale 1ns/1ps
module ae350_pcm_cosim(
 input wire cpu_reset_n, bus_select,bus_enable,bus_write,bus_page,
 input wire [11:0] bus_address,input wire [31:0] bus_data,
 input wire session_ready,input wire [31:0] session_epoch,session_generation,
 input wire rate_request,rate_request44,input wire [31:0] expected_pcm_word,
 output wire bus_ready,bus_error,output wire [31:0] bus_result,
 output wire peripheral_clk,context_ready,context_rate,stream_selected,owner_failed,serial_held,command_pending,
 output wire [31:0] physical_count,direct_count,half_count,mono_count,history_count,effect_count,
 output wire [31:0] owner_commands,queue_count,cancel_epoch,complete_block_count,complete_word_count,control_debug,options_debug,output wire [127:0] held_snapshot
);
    reg control_clk=0,compute_clk=0,memory_clk=0,pclk=0,reference48=0,reference44=0,rst_n=0,compute_run=1;wire preset_n=cpu_reset_n;
    always #10 control_clk=!control_clk;
    always #6.510417 if(compute_run)compute_clk=!compute_clk;
    always #5 memory_clk=!memory_clk;
    always #17 pclk=!pclk;
    initial begin #3.7;forever #40.690104 reference48=!reference48;end
    initial begin #17.2;forever #29.525699 reference44=!reference44;end
    reg midi_rx=1,pc_rx=1,usb_valid=0,usb_lifecycle=0,usb_cancel=0;
    reg [17:0] usb_data=0;
    wire usb_ready;
    wire psel=bus_select,penable=bus_enable,pwrite=bus_write;
    wire [11:0] paddr=bus_address;
    wire [31:0] pwdata=bus_data;
    reg [3:0] pstrb=15;
    wire pready,pslverr,normal_ready,normal_error,pcm_ready,pcm_error;
    wire [31:0] prdata,normal_data,pcm_data;
    wire pcm_page=bus_page,hci_ready=session_ready;
    wire [31:0] hci_epoch=session_epoch,hci_generation=session_generation;
    assign pready=pcm_page ? pcm_ready:normal_ready;
    assign pslverr=pcm_page ? pcm_error:normal_error;
    assign prdata=pcm_page ? pcm_data:normal_data;
    wire [447:0] performance;
    wire request=rate_request,request44=rate_request44;reg permit=1,tf_active=0,tf_busy=0,tf_error=0;
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
        .RESERVE_ZERO_EPOCH(1),.ENABLE_AE350_PCM(1)) dut(
        .rst_ni(rst_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
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
    integer physical_frames=0,physical_good=0,physical_nonzero=0,physical_errors=0,matched_pcm=0,matched_half=0,matched_mono=0;
    integer position=0,serial_checks=0,history_clears=0,effect_results=0;
    reg [31:0] decoded=0,last_decoded=0;
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
        if(frame_pcm=={16'sd8000,16'sd8000}&&!frame_error)matched_mono=matched_mono+1;
    end
    always @(posedge compute_clk)begin
        if(dut.runtime.pcm_history_request && dut.runtime.pcm_history_ready && !dut.runtime.config_valid)history_clears=history_clears+1;
        if(dut.runtime.service.workstation.runtime_effects.effects.chorus_valid &&
            dut.runtime.service.workstation.runtime_effects.effects.chorus_stage.product_l!=0)effect_results=effect_results+1;
    end

    integer verified_blocks=0,verified_words=0;
    always @(posedge compute_clk)begin
        if(dut.pcm_command_valid && dut.pcm_command_ready && dut.pcm_command_write &&
            dut.pcm_command_address==12'h040 && dut.pcm_command_data==2 && !dut.pcm_response_error)begin
            for(integer j=0;j<128;j=j+1)if(j<dut.runtime.cpu_pcm.owner.staged_frames)begin
                if(dut.runtime.cpu_pcm.owner.memory[dut.runtime.cpu_pcm.owner.staged_slot*128+j]!==expected_pcm_word)
                    $fatal(1,"C complete block payload differs at %d",j);
                verified_words=verified_words+1;
            end
            verified_blocks=verified_blocks+1;
        end
    end
    assign complete_block_count=verified_blocks;assign complete_word_count=verified_words;
    assign control_debug=control_state;assign options_debug=options;
    assign bus_ready=pready;assign bus_error=pslverr;assign bus_result=prdata;
    assign peripheral_clk=pclk;assign context_ready=active_valid && !busy && ready;
    assign context_rate=rate;assign stream_selected=dut.runtime.cpu_pcm.owner.selected_o;
    assign owner_failed=dut.runtime.cpu_pcm.owner.failed_o;
    assign serial_held=dut.runtime.cpu_pcm.owner.serial_hold_o;assign command_pending=dut.pcm_command_valid;
    assign physical_count=physical_frames;assign direct_count=matched_pcm;assign half_count=matched_half;
    assign mono_count=matched_mono;assign history_count=history_clears;assign effect_count=effect_results;
    assign owner_commands=dut.runtime.cpu_pcm.owner.command_id;assign queue_count=dut.runtime.cpu_pcm.owner.queued;
    assign cancel_epoch={10'd0,dut.runtime.cpu_pcm.owner.cancel_epoch_o};assign held_snapshot=held;
    initial begin for(integer i=0;i<4096;i=i+1)memory[i]=0;#137;rst_n=1;end
    initial begin #200000000;$fatal(1,"PCM C runtime timeout");end
endmodule
