`timescale 1ns/1ps
// Enabled real native runtime + true TF stop/DDR/WAV/transport. Only SD/FAT
// bytes and an ordered DDR endpoint are fixtures. No fake core/TF done pulse.
module tb_workstation_media_runtime_integration #(parameter bit BUSY_FENCE_ONLY=0);
    reg control_clk=0,compute_clk=0,memory_clk=0,pclk=0,reference48=0,reference44=0,rst_n=0,preset_n=0;
    reg reference44_run=1,reference48_run=1,compute_run=1;
    always #10 control_clk=~control_clk;
    always #6.510417 if(compute_run)compute_clk=~compute_clk;
    always #5 memory_clk=~memory_clk;
    always #17 pclk=~pclk;
    initial begin #3.7;forever #40.690104 if(reference48_run)reference48=~reference48;end
    initial begin #17.2;forever #29.525699 if(reference44_run)reference44=~reference44;end
    wire midi_rx=1,pc_rx=1,usb_valid=0,usb_lifecycle=0,usb_cancel=0;
    wire [17:0] usb_data=0;wire usb_ready;
    reg psel=0,penable=0,pwrite=0;reg [12:0] paddr=0;reg [31:0] pwdata=0;reg [3:0] pstrb=15;
    wire [1:0] bus_ready,bus_error;wire [31:0] bus_data[0:1];
    wire pready=bus_ready[paddr[12]],pslverr=bus_error[paddr[12]];wire [31:0] prdata=bus_data[paddr[12]];
    wire [447:0] performance;
    wire request,request44,recover;reg permit=1;
    reg direct_request=0,direct_target=0,direct_recover=0;
    wire tf_active,tf_busy,tf_error,tf_valid,tf_ready,tf_quiet50,tf_quiet,tf_busy50;
    wire signed [15:0] tf_left,tf_right;wire [19:0] tf_rate;
    wire [31:0] tf_generation,tf_expected,tf_source_generation,tf_source_accepted;
    wire ready,busy,fault,accepted,applied,policy_rejected,rate,active_valid,rec_enabled,rec_failed;
    wire core_rejected,core_failed,quiesce,dsp_fault;wire [2:0] reject_code;wire [3:0] fault_code;wire [1:0] qualified;
    wire [2:0] rec_code;wire [3:0] block_reason;
    wire [31:0] epoch,active,control_state,control_pitch,options,applied_events,pc_health;wire [127:0] held;wire [15:0] volume;
    wire [31:0] underruns,midi_drops,observation_drops,record_drops;
    wire sample_valid,frame_valid,frame_error,frame_rate,mclk,bck,lrck,sd,pdn_n,smute,uart_error;
    wire signed [31:0] audio_left,audio_right;wire [31:0] frame_epoch,frame_sequence,frame_pcm;
    wire fft_valid,fft_context,fft_rate;wire [7:0] fft_bin;wire signed [23:0] fft_real,fft_imag;wire [31:0] fft_epoch,fft_discards;
    wire running,done,score_failed;wire [31:0] leds,score_frame;
    wire display_valid,display_rate,display_error,display_observation_fault;wire [31:0] display_pcm,display_epoch,display_sequence;
    wire [2:0] display_effect_mask;wire [5:0] display_effect_order;
    wire ddr_req,ddr_write,audio_ddr_ready;wire [28:0] ddr_address;wire [255:0] ddr_data,ddr_read_data;wire [31:0] ddr_mask;
    reg ddr_response=0;reg [255:0] audio_read_data=0;assign ddr_read_data=audio_read_data;
    wire media_request,media_hold,media_ready,media_done,media_failed;wire [3:0] media_failure;
    wire tf_stop_request,tf_stop_pending,tf_stop_done,tf_stop_failed;wire [3:0] tf_stop_failure;
    workstation_runtime_controlled #(.WINDOW_CYCLES(500),.STABLE_WINDOWS(3),.LOSS_TIMEOUT_CYCLES(25),
        .STOP_LOW_CYCLES(8),.STARTUP_MUTE_FRAMES(3),.PDN_HOLD_FRAMES(1),.RECORD_ADDRESS_BITS(6),
        .RESERVE_ZERO_EPOCH(1),.ENABLE_MEDIA_POLICY(1)) dut(
        .common_reset_ni(1'b1),.rst_ni(rst_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .reference_48_i(reference48),.reference_44_i(reference44),.midi_rx_i(midi_rx),.pc_uart_rx_i(pc_rx),
        .usb_event_valid(usb_valid),.usb_lifecycle,.usb_cancel,.usb_event_data(usb_data),.usb_event_ready(usb_ready),
        .pclk,.preset_n,.psel(psel && !paddr[12]),.penable,.pwrite,.paddr(paddr[11:0]),.pwdata,.pstrb,.pready(bus_ready[0]),.pslverr(bus_error[0]),.prdata(bus_data[0]),.performance_words_o(performance),
        .request_i(request || direct_request),.request_44k1_i(direct_request ? direct_target:request44),
        .switch_permit_i(permit),.recover_i(recover || direct_recover),.media_quiescent_i(tf_quiet50),
        .request_ready_o(ready),.busy_o(busy),.fault_o(fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(core_rejected),.failed_o(core_failed),.policy_rejected_o(policy_rejected),.reject_code_o(reject_code),.fault_code_o(fault_code),.clock_select_o(),
        .switch_block_reason_o(block_reason),.active_44k1_o(rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),
        .source_qualified_o(qualified),.quiesce_o(quiesce),.stream_flush_o(),.dsp_fault_o(dsp_fault),.context_ready_o(),
        .pcm_psel_i(1'b0),.pcm_pready_o(),.pcm_pslverr_o(),.pcm_prdata_o(),
        .hci_session_ready_i(1'b0),.hci_controller_epoch_i(32'd0),.hci_transport_generation_i(32'd0),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(1'b0),
        .tf_active_i(tf_active),.tf_busy_i(tf_busy),.tf_valid_i(tf_valid),.tf_error_i(tf_error),
        .tf_left_i(tf_left),.tf_right_i(tf_right),.tf_sample_rate_i(tf_rate),
        .tf_generation_i(tf_generation),.expected_tf_generation_i(tf_expected),.tf_ready_o(tf_ready),
        .ddr_req_o(ddr_req),.ddr_write_o(ddr_write),.ddr_address_o(ddr_address),.ddr_data_o(ddr_data),.ddr_mask_o(ddr_mask),
        .ddr_ready_i(audio_ddr_ready),.ddr_response_i(ddr_response),.ddr_read_data_i(ddr_read_data),
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
        .media_stop_request_i(media_request),.media_stop_hold_i(media_hold),.media_stop_ready_o(media_ready),.media_stop_done_o(media_done),.media_stop_failed_o(media_failed),
        .media_stop_failure_code_o(media_failure),.tf_stop_request_o(tf_stop_request),.tf_stop_pending_i(tf_stop_pending),.tf_stop_done_i(tf_stop_done),.tf_stop_failed_i(tf_stop_failed),.tf_stop_failure_code_i(tf_stop_failure));

    wire clock_reset,clock_valid,clock_ready,clock_write,clock_error;
    wire [11:0] clock_address;wire [31:0] clock_data,clock_response;wire [3:0] clock_strobes;
    gw138k_apb_cdc clock_apb(.reset_n(rst_n&&preset_n),.pclk,.audio_clk(control_clk),
        .psel(psel&&paddr[12]),.penable,.pwrite,.paddr(paddr[11:0]),.pwdata,.pstrb,
        .pready(bus_ready[1]),.pslverr(bus_error[1]),.prdata(bus_data[1]),
        .command_reset_n(clock_reset),.command_valid(clock_valid),.command_ready(clock_ready),.command_write(clock_write),
        .command_address(clock_address),.command_data(clock_data),.command_strobes(clock_strobes),
        .response_data(clock_response),.response_error(clock_error));
    workstation_audio_clock_service #(.ENABLE_MEDIA_POLICY(1),.RESERVE_ZERO_EPOCH(1),
        .ACCEPT_TIMEOUT_CYCLES(32),.RESULT_TIMEOUT_CYCLES(100000),.MEDIA_TIMEOUT_CYCLES(8000)) commands(
        .clk_i(control_clk),.reset_ni(clock_reset),.command_valid_i(clock_valid),.command_write_i(clock_write),
        .command_address_i(clock_address),.command_data_i(clock_data),.command_strobes_i(clock_strobes),
        .command_ready_o(clock_ready),.response_data_o(clock_response),.response_error_o(clock_error),
        .switch_permit_i(permit),.core_request_ready_i(ready),.core_busy_i(busy),.core_fault_i(fault),.core_dsp_fault_i(dsp_fault),
        .core_accepted_i(accepted),.core_applied_i(applied),.core_rejected_i(core_rejected),.core_policy_rejected_i(policy_rejected),
        .core_failed_i(core_failed),.core_reject_code_i(reject_code),.core_fault_code_i(fault_code),
        .core_active_44k1_i(rate),.core_active_valid_i(active_valid),.core_stream_epoch_i(epoch),.core_source_qualified_i(qualified),
        .request_o(request),.request_44k1_o(request44),.recover_o(recover),
        .media_stop_request_o(media_request),.media_stop_hold_o(media_hold),.media_stop_ready_i(media_ready),
        .media_stop_done_i(media_done),.media_stop_failed_i(media_failed),.media_stop_failure_code_i(media_failure));
    reg tf_restart=0,tf_run=1,transport_error=0;reg [3:0] track=0;
    wire tf_req,tf_write,tf_ddr_ready,tf_ddr_response;wire [28:0] tf_addr;wire [255:0] tf_data,tf_read_data;
    wire tf_failed;wire [3:0] tf_failure;
    workstation_tf_runtime_service #(.FIFO_ADDRESS_BITS(3),.QUIET_TIMEOUT_CYCLES(12000),.EXTERNAL_STOP_PROTOCOL(1),
        .HOTPLUG_TIMEOUT_CYCLES(28'd200000),.HOTPLUG_STALL_TIMEOUT_CYCLES(28'd300000)) tf(
        .common_reset_ni(1'b1),.rst_ni(rst_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .memory_reset_ni(rst_n),.memory_ready_i(rst_n),.mode_i(1'b1),.run_i(tf_run),.restart_i(tf_restart),
        .cancel_i(1'b0),.reader_restart_i(1'b0),.transport_error_i(transport_error),.track_index_i(track),
        .runtime_valid_i(active_valid),.runtime_44k1_i(rate),.runtime_fault_i(fault||dsp_fault),.runtime_busy_i(busy),.runtime_epoch_i(epoch),
        .analysis_enable_i(1'b0),.analysis_hold_i(1'b1),.analysis_pcm_ready_i(1'b0),.analysis_pcm_valid_o(),.analysis_pcm_end_o(),
        .analysis_left_o(),.analysis_right_o(),.analysis_sample_rate_o(),.sd_miso_i(1'b1),.sd_cs_no(),.sd_sck_o(),.sd_mosi_o(),
        .track_count_o(),.playlist_ready_o(),.card_lost_o(),.hotplug_debug_o(),.playlist_name_address_i(8'd0),.playlist_name_data_o(),
        .format_ready_o(),.unsupported_o(),.ddr_error_o(),.file_size_o(),.file_sample_rate_o(),
        .ddr_valid_o(tf_req),.ddr_write_o(tf_write),.ddr_address_o(tf_addr),.ddr_data_o(tf_data),
        .ddr_ready_i(tf_ddr_ready),.ddr_response_i(tf_ddr_response),.ddr_read_data_i(tf_read_data),
        .busy_50_o(tf_busy50),.failed_o(tf_failed),.cancelled_o(),.eof_seen_o(),.failure_code_o(tf_failure),.paused_o(),
        .control_pending_o(),.media_quiescent_50_o(tf_quiet50),.source_generation_o(tf_source_generation),.source_accepted_count_o(tf_source_accepted),
        .failure_count_o(),.invalidate_count_o(),.tf_active_o(tf_active),.tf_busy_o(tf_busy),.tf_valid_o(tf_valid),.tf_error_o(tf_error),
        .tf_left_o(tf_left),.tf_right_o(tf_right),.tf_sample_rate_o(tf_rate),.tf_generation_o(tf_generation),.expected_generation_o(tf_expected),
        .tf_ready_i(tf_ready),.media_quiescent_o(tf_quiet),.stale_discard_count_o(),.quiesce_discard_count_o(),
        .stop_request_i(tf_stop_request),.stop_pending_o(tf_stop_pending),.stop_done_o(tf_stop_done),.stop_failed_o(tf_stop_failed),.stop_failure_code_o(tf_stop_failure));
    wire tf_down_req,tf_down_write,tf_down_ready;wire [28:0] tf_down_addr;wire [255:0] tf_down_data;
    tf_audio_ddr_command_buffer tf_queue(.clk(memory_clk),.rst_n(rst_n),.in_valid(tf_req),.in_write(tf_write),
        .in_address(tf_addr),.in_data(tf_data),.in_ready(tf_ddr_ready),.out_valid(tf_down_req),.out_write(tf_down_write),
        .out_address(tf_down_addr),.out_data(tf_down_data),.out_ready(tf_down_ready));
    // Shared ordered two-client DDR endpoint. One physical acceptance/edge;
    // writes/read returns preserve global order and address allocations.
    localparam [28:0] TF_BASE=29'h0600000,AUDIO_BASE=29'h0c000000;
    reg [255:0] tf_memory[0:2047],audio_memory[0:4095];
    reg [28:0] qaddr[0:63];reg [255:0] qdata[0:63];reg qowner[0:63],qwrite[0:63];
    integer head=0,tail=0,queued=0,delay_count=0,mem_cycle=0,tf_reads=0,audio_reads=0,mem_writes=0;
    reg round_robin=0,tf_response=0;reg [255:0] tf_response_data=0;reg hold_tf_response=0;
    wire select_tf=tf_down_req&&(!ddr_req||round_robin);
    wire backend_ready=rst_n&&queued<60&&mem_cycle%11!=0;
    assign tf_down_ready=backend_ready&&select_tf;
    assign audio_ddr_ready=backend_ready&&!select_tf;
    assign tf_ddr_response=tf_response;assign tf_read_data=tf_response_data;
    always @(posedge memory_clk)begin
        mem_cycle=mem_cycle+1;ddr_response<=0;tf_response<=0;
        if(rst_n)begin
            if((select_tf?tf_down_req:ddr_req)&&backend_ready)begin
                qaddr[tail]=select_tf?tf_down_addr:ddr_address;
                qdata[tail]=select_tf?tf_down_data:ddr_data;
                qowner[tail]=select_tf;qwrite[tail]=select_tf?tf_down_write:ddr_write;
                if(qaddr[tail][2:0]!=0 || (!select_tf && ddr_mask!=0))$fatal(1,"DDR address/mask alignment");
                if(select_tf ? (qaddr[tail]<TF_BASE||qaddr[tail]>=TF_BASE+16384):
                               (qaddr[tail]<AUDIO_BASE||qaddr[tail]>=AUDIO_BASE+32768))$fatal(1,"DDR allocation overlap/escape");
                tail=(tail+1)%64;queued=queued+1;round_robin=~round_robin;
            end
            if(queued!=0)begin
                if(delay_count>=3 && !(qowner[head]&&!qwrite[head]&&hold_tf_response))begin
                    if(qwrite[head])begin
                        if(qowner[head])tf_memory[11'((qaddr[head]-TF_BASE)>>3)]=qdata[head];
                        else audio_memory[12'((qaddr[head]-AUDIO_BASE)>>3)]=qdata[head];
                        mem_writes=mem_writes+1;
                    end else if(qowner[head])begin
                        tf_response_data<=tf_memory[11'((qaddr[head]-TF_BASE)>>3)];tf_response<=1;tf_reads=tf_reads+1;
                    end else begin audio_read_data<=audio_memory[12'((qaddr[head]-AUDIO_BASE)>>3)];ddr_response<=1;audio_reads=audio_reads+1;end
                    head=(head+1)%64;queued=queued-1;delay_count=0;
                end else if(delay_count<3)delay_count=delay_count+1;
            end
        end
    end
    reg [31:0] physical_pcm[0:7][0:2047];reg physical_seen[0:7][0:2047];
    reg [31:0] router_pcm[0:7][0:2047];reg router_tf[0:7][0:2047],router_seen[0:7][0:2047];
    integer physical_frames=0,observed_frames=0,tf_physical_frames=0,tf_packets=0,packet_index=0;
    reg [31:0] last_generation=0;reg [31:0] decoded=0,last_decoded=0;integer serial_position=0;
    always @(negedge dut.runtime.serial_reset_n)begin serial_position=0;decoded=0;last_decoded=0;end
    always @(posedge bck)begin #0.1;if(dut.runtime.serial_reset_n)begin
        if(lrck!==(serial_position>=32))$fatal(1,"I2S LRCK mismatch");
        if(serial_position>=1&&serial_position<=16)decoded[32-serial_position]=sd;
        else if(serial_position>=33&&serial_position<=48)decoded[48-serial_position]=sd;
        else if(sd!==0)$fatal(1,"I2S padding changed");
        if(serial_position==63)begin last_decoded=decoded;decoded=0;serial_position=0;end
        else serial_position=serial_position+1;
    end end
    always @(posedge compute_clk)if(rst_n)begin
        if(dut.runtime.router_done)begin
            router_pcm[dut.runtime.final_pcm.frame_epoch_o][dut.runtime.final_pcm.frame_sequence_o]=dut.runtime.final_pcm.frame_pcm_o;
            router_tf[dut.runtime.final_pcm.frame_epoch_o][dut.runtime.final_pcm.frame_sequence_o]=dut.runtime.final_pcm.frame_source_tf_o;
            router_seen[dut.runtime.final_pcm.frame_epoch_o][dut.runtime.final_pcm.frame_sequence_o]=1;
        end
        if(tf_active&&tf_valid&&tf_ready&&tf.compute_control[1])begin
            if(tf_generation!=last_generation)begin last_generation=tf_generation;packet_index=0;end
            if(tf_error || tf_left!==16'(1000+integer'(track)*100+packet_index) ||
                tf_right!==16'(-2000-integer'(track)*100-packet_index) || tf_rate!==(track==1?20'd44100:20'd48000))
                $fatal(1,"actual TF packet sequence/context mismatch index=%0d left=%0d right=%0d",packet_index,tf_left,tf_right);
            packet_index=packet_index+1;tf_packets=tf_packets+1;
        end
    end
    always @(negedge mclk)if(rst_n&&frame_valid)begin
        if(frame_epoch>=8||frame_sequence>=2048||frame_pcm!==last_decoded)$fatal(1,"physical serialized PCM tap mismatch");
        physical_seen[frame_epoch][frame_sequence]=1;physical_pcm[frame_epoch][frame_sequence]=frame_pcm;
        if(!frame_error&&router_seen[frame_epoch][frame_sequence])begin
            if(frame_pcm!==router_pcm[frame_epoch][frame_sequence])$fatal(1,"router result changed before physical output");
            if(router_tf[frame_epoch][frame_sequence]&&frame_pcm!=0)tf_physical_frames=tf_physical_frames+1;
        end
        physical_frames=physical_frames+1;
    end
    always @(negedge compute_clk)if(rst_n&&sample_valid)begin
        if(!physical_seen[dut.observed_epoch][dut.observed_sequence] ||
            {audio_left[31:16],audio_right[31:16]}!==physical_pcm[dut.observed_epoch][dut.observed_sequence])
            $fatal(1,"physical-to-compute observation mismatch");
        observed_frames=observed_frames+1;
    end
    integer requests=0,stops=0,tf_done_count=0,tf_failed_count=0,checks=0,mailbox_checks=0,drain_checks=0;
    reg ack_stall=0;reg [1:0] held_ack=0;
    always @(posedge control_clk)if(rst_n)begin
        if(request)begin
            requests=requests+1;
            if(ack_stall || tf.control_pending_o)$fatal(1,"clock request preceded final TF mailbox ACK");
            if(tf_stop_pending||rec_enabled||running||tf_active||tf_busy)$fatal(1,"clock request preceded actual media stop");
        end
        if(tf_stop_request)stops=stops+1;
        if(tf_stop_done)tf_done_count=tf_done_count+1;
        if(tf_stop_failed)tf_failed_count=tf_failed_count+1;
        if((fault&&!BUSY_FENCE_ONLY)||dsp_fault||display_observation_fault||observation_drops!=0)$fatal(1,"native runtime health failure fault=%b dsp=%b",fault,dsp_fault);
    end
    task clocks(input integer n);begin repeat(n)@(negedge control_clk);end endtask
    task frames(input integer n);integer target;begin target=observed_frames+n;wait(observed_frames>=target);@(negedge compute_clk);end endtask
    task bus(input bit wr,input [12:0] addr,input [31:0] data,input bit err,output [31:0] value);
        integer n;begin
            @(negedge pclk);psel=1;penable=0;pwrite=wr;paddr=addr;pwdata=data;
            @(negedge pclk);penable=1;n=0;
            do begin @(posedge pclk);#0.1;n=n+1;end while(!pready&&n<10000);
            if(!pready||pslverr!==err)$fatal(1,"joint APB failure addr=%h expected_error=%b actual=%b reason=%0d",addr,err,pslverr,clock_response);
            value=prdata;@(negedge pclk);psel=0;penable=0;
        end
    endtask
    reg [31:0] value,ticket;
    task wr(input [12:0] addr,input [31:0] data,input bit err);begin bus(1,addr,data,err,value);end endtask
    task rd(input [12:0] addr,input [31:0] expected);begin bus(0,addr,0,0,value);if(value!==expected)$fatal(1,"joint read %h got=%h expected=%h",addr,value,expected);end endtask
    task event_cpu(input integer kind,a,b);begin wr(13'h180,{14'd0,4'(kind),7'(a),7'(b)},0);end endtask
    task begin_file(input [3:0] next_track);integer n;reg [31:0] target_gen;begin
        @(negedge control_clk);track=next_track;tf_run=1;tf_restart=1;
        @(negedge control_clk);tf_restart=0;clocks(3);target_gen=tf_source_generation;n=0;
        while(!tf_active||tf_expected!=target_gen)begin clocks(1);n=n+1;if(n>100000)$fatal(1,"joint TF start failed state=%0d reason=%0d gen=%0d/%0d format=%b rate=%0d bytes=%0d reader=%b/%0d quiet=%b/%b dmaW=%0d dmaR=%0d capture=%b/%b eof=%b playback=%b bytecount=%0d fifo=%0d/%0d pcm=%b ddr=%0d/%0d/%0d",tf.state,tf_failure,tf_expected,target_gen,tf.format_ready_o,tf.file_sample_rate_o,tf.path.captured_bytes,tf.path.u_file_reader.active,tf.path.u_file_reader.index,tf.source_quiet,tf.memory_quiet_50,tf.path.g_runtime_dma.u_dma.write_total_bytes,tf.path.g_runtime_dma.u_dma.read_total_bytes,tf.path.capture_done_toggle,tf.path.g_runtime_dma.u_dma.capture_seen,tf.path.g_runtime_dma.u_dma.eof_finalized,tf.path.playback_active,tf.path.decoder_byte_count,tf.path.in_wr_count,tf.path.out_rd_count,tf.path_pcm_valid,mem_writes,tf_reads,queued);end
        tf_run=1;frames(5);
    end endtask
    task result_code(input integer expected);integer n;begin
        n=0;while(commands.phase!=0)begin clocks(1);n=n+1;if(n>200000)$fatal(1,"joint rate result timeout");end
        rd(13'h1018,ticket);rd(13'h101c,32'(expected));
    end endtask
    reg [127:0] held_before;reg [31:0] state_before,pitch_before,options_before,epoch_before,pop_left,pop_right,pop_seq,object_id,object_frames;
    task live_state;begin
        if(held!==held_before||control_state!==state_before||control_pitch!==pitch_before||options!==options_before)
            $fatal(1,"planned rate change/CPU reset lost held notes or committed parameters");
    end endtask
    task stall_final_ack(input integer cycles);begin
        wait(tf.state==4&&tf.path_clear_done&&!tf.memory_gate);
        @(negedge control_clk);held_ack=tf.ack_sync;force tf.ack_sync=held_ack;ack_stall=1;
        clocks(20);if(tf.state!=0||tf_busy50||!tf.control_pending_o||!tf_stop_pending)$fatal(1,"actual final mailbox boundary not reached");
        repeat(cycles)begin clocks(1);if(request||busy)$fatal(1,"clock advanced during final TF ACK hold");mailbox_checks=mailbox_checks+1;end
        release tf.ack_sync;ack_stall=0;
    end endtask
    integer busy_fence_checks=0,busy_sync_checks=0;
    reg [1:0] expected_switch_status;
    reg [2:0] expected_media_status;
    always @(posedge compute_clk)begin
        expected_switch_status={dut.switch_busy_compute[0],dut.switch_busy_50};
        #0.001;
        if(BUSY_FENCE_ONLY && dut.reset_compute_n)begin
            if(dut.switch_busy_compute!==expected_switch_status)$fatal(1,"prepared switch status skipped data synchronizer");
            busy_sync_checks=busy_sync_checks+1;
        end
    end
    always @(posedge control_clk)begin
        expected_media_status={dut.media_busy_50[1:0],dut.media_busy_compute};
        #0.001;
        if(BUSY_FENCE_ONLY && dut.reset_50_n)begin
            if(dut.media_busy_50!==expected_media_status)$fatal(1,"prepared media status skipped data synchronizer");
            busy_sync_checks=busy_sync_checks+1;
        end
    end
    task check_unprepared_request;reg [31:0] saved_epoch;begin
        saved_epoch=epoch;@(negedge control_clk);direct_request=1;direct_target=!rate;
        @(posedge control_clk);#0.001;
        if(!policy_rejected||accepted||busy||epoch!=saved_epoch)$fatal(1,"unprepared clock request escaped media fence");
        @(negedge control_clk);direct_request=0;clocks(2);busy_fence_checks=busy_fence_checks+1;
    end endtask
    task busy_fence_regression;reg [31:0] saved_epoch;integer saved_requests;begin
        // Idle readiness is usable before preparation, but it is never a
        // substitute for the actual stop ACK on a changing request.
        if(!ready||dut.media_prepared)$fatal(1,"unprepared idle readiness changed");
        check_unprepared_request();
        // Same-rate no-op keeps its old epoch and does not start media stop.
        saved_epoch=epoch;saved_requests=requests;wr(13'h1008,0,0);ticket=value;result_code(1);
        if(epoch!=saved_epoch||requests!=saved_requests+1||stops!=0)$fatal(1,"same-rate no-op required media preparation");
        busy_fence_checks=busy_fence_checks+1;
        // A real active REC seals normally and a real active score cancels.
        wr(13'h0100,0,0);wr(13'h0104,1000000,0);wr(13'h0108,32'ha5,0);wr(13'h010c,1,0);wr(13'h0110,1,0);wr(13'h0114,1,0);
        wr(13'h0080,1,0);frames(3);saved_epoch=epoch;
        fork
            begin wr(13'h1008,1,0);ticket=value;end
            begin
                wait(dut.local_stop_hold);wait(busy);
                wr(13'h0114,1,1);wr(13'h0080,1,1);
            end
        join
        result_code(1);frames(3);
        if(!rate||epoch!=saved_epoch+1||rec_enabled||running||rec_failed||!dut.consumers.score_cancelled_o||
            !dut.consumers.record_object_status_o[1])$fatal(1,"prepared switch lost normal seal/cancellation");
        wait(media_ready);if(dut.media_prepared)$fatal(1,"released hold retained old preparation");
        busy_fence_checks=busy_fence_checks+1;
        bus(0,13'h00ac,0,0,object_frames);
        for(integer i=0;i<integer'(object_frames);i=i+1)begin wr(13'h0088,1,0);wr(13'h0098,1,0);end
        check_unprepared_request();
        // A stopped compute owner cannot ACK a new stop or issue its clock
        // request. Resume before the unchanged real-time DSP deadline.
        saved_epoch=epoch;saved_requests=requests;
        fork
            begin wr(13'h1008,0,0);ticket=value;end
            begin wait(media_request);@(negedge compute_clk);compute_run=0;
                repeat(30)begin clocks(1);if(media_done||request||busy||dut.media_prepared)$fatal(1,"stopped compute authorized switch");end
                compute_run=1;
            end
        join
        result_code(1);frames(3);wait(media_ready);
        if(rate||epoch!=saved_epoch+1||requests!=saved_requests+1)$fatal(1,"resumed compute lost prepared switch");
        busy_fence_checks=busy_fence_checks+1;
        // Recovery is subject to the same proof even though the original
        // clock owner's recover input bypasses ordinary switch_permit.
        reference48_run=0;wait(fault&&!busy);saved_epoch=epoch;
        @(negedge control_clk);direct_recover=1;
        @(posedge control_clk);#0.001;
        if(!policy_rejected||dut.prepared_recover||busy||epoch!=saved_epoch)$fatal(1,"unprepared recovery escaped media fence");
        @(negedge control_clk);direct_recover=0;reference48_run=1;wait(qualified[0]);
        wr(13'h1008,2,0);ticket=value;result_code(1);frames(3);wait(media_ready);
        if(fault||epoch!=saved_epoch+1||dut.media_prepared)$fatal(1,"prepared recovery failed or retained proof");
        busy_fence_checks=busy_fence_checks+1;
        $display("PASS media_runtime_busy_fence: checks=%0d data_sync_checks=%0d core_requests=%0d physical=%0d observed=%0d",busy_fence_checks,busy_sync_checks,requests,physical_frames,observed_frames);$finish;
    end endtask
    initial begin
        for(integer e=0;e<8;e=e+1)for(integer s=0;s<2048;s=s+1)begin physical_seen[e][s]=0;router_seen[e][s]=0;end
        clocks(5);rst_n=1;preset_n=1;wait(ready);frames(8);
        if(BUSY_FENCE_ONLY)busy_fence_regression();
        event_cpu(2,7,100);event_cpu(1,60,127);frames(8);
        if(!held[60]||active==0)$fatal(1,"single native owner did not receive APB note");
        held_before=held;state_before=control_state;pitch_before=control_pitch;options_before=options;
        begin_file(0);if(tf_packets<2||tf_physical_frames<1)$fatal(1,"TF did not reach real serialized output");
        // Same-rate and unqualified-target admissions remain strict even when
        // the media policy may prepare an actual change despite gated ready.
        wr(13'h1008,0,1);rd(13'h104c,11);
        checks=checks+1;
        wr(13'h0100,0,0);wr(13'h0104,1000000,0);wr(13'h0108,32'ha5,0);wr(13'h010c,1,0);wr(13'h0110,1,0);wr(13'h0114,1,0);
        wr(13'h0080,1,0);frames(5);wr(13'h0088,1,0);
        bus(0,13'h0090,0,0,pop_left);bus(0,13'h0094,0,0,pop_right);bus(0,13'h008c,0,0,pop_seq);
        epoch_before=epoch;hold_tf_response=1;wait(tf.memory_read_pending);clocks(2);
        fork
            begin wr(13'h1008,1,0);ticket=value;end
            begin
                wait(tf_stop_request);wait(tf.memory_gate);
                repeat(30)begin @(negedge memory_clk);if(!tf.memory_read_pending||request||busy)$fatal(1,"joint accepted TF read did not fence clock");drain_checks=drain_checks+1;end
                hold_tf_response=0;stall_final_ack(200);
            end
        join
        result_code(1);frames(4);live_state();
        if(!rate||epoch!=epoch_before+1||requests!=1||running||!dut.consumers.score_cancelled_o||rec_failed)$fatal(1,"first real joint switch failed");
        bus(0,13'h00a0,0,0,object_id);bus(0,13'h00ac,0,0,object_frames);
        if(object_frames<5||object_frames>64)$fatal(1,"sealed object accepted count invalid");
        rd(13'h00a4,48000);rd(13'h00a8,epoch_before);rd(13'h0090,pop_left);rd(13'h0094,pop_right);rd(13'h008c,pop_seq);
        wr(13'h0098,1,0);for(integer i=1;i<integer'(object_frames);i=i+1)begin wr(13'h0088,1,0);wr(13'h0098,1,0);end
        rd(13'h0084,0);rd(13'h00a0,object_id);checks=checks+1;
        begin_file(1);epoch_before=epoch;wr(13'h1008,0,0);ticket=value;result_code(1);frames(4);live_state();
        if(rate||epoch!=epoch_before+1||requests!=2)$fatal(1,"real reverse switch failed");checks=checks+1;
        begin_file(0);
        reference44_run=0;wait(!qualified[1]);wr(13'h1008,1,1);rd(13'h104c,13);
        reference44_run=1;wait(qualified==3);checks=checks+1;
        wr(13'h0080,1,0);frames(2);epoch_before=epoch;
        // Abort an in-flight clock APB transaction by resetting its CPU owner;
        // real media still stops, no abandoned request reaches the rate core.
        @(negedge pclk);paddr=13'h1008;pwdata=1;pwrite=1;psel=1;penable=0;
        @(negedge pclk);penable=1;wait(dut.local_stop_request);@(negedge compute_clk);preset_n=0;psel=0;penable=0;
        clocks(8);preset_n=1;wait(media_ready);frames(3);live_state();
        if(dut.media_prepared_50)$fatal(1,"abandoned media stop retained preparation");
        if(requests!=2||epoch!=epoch_before||rate||rec_enabled||!dut.consumers.record_object_status_o[1])$fatal(1,"CPUreset revived joint command");
        bus(0,13'h00ac,0,0,object_frames);for(integer i=0;i<integer'(object_frames);i=i+1)begin wr(13'h0088,1,0);wr(13'h0098,1,0);end
        checks=checks+1;
        begin_file(0);epoch_before=epoch;
        fork
            begin wr(13'h1008,1,0);ticket=value;end
            begin wait(tf_stop_request);@(negedge control_clk);transport_error=1;end
        join
        result_code(8);rd(13'h1068,7);wait(media_ready);transport_error=0;frames(3);live_state();
        if(requests!=2||epoch!=epoch_before)$fatal(1,"TF failure switched actual core");checks=checks+1;
        begin_file(0);epoch_before=epoch;
        fork
            begin wr(13'h1008,1,0);ticket=value;end
            begin wait(tf_stop_request);stall_final_ack(12500);end
        join
        result_code(9);rd(13'h1068,0);wait(media_ready);frames(4);live_state();
        if(dut.media_prepared_50)$fatal(1,"abandoned media stop retained preparation");
        check_unprepared_request();
        if(requests!=2||epoch!=epoch_before||tf_stop_failure!=8)$fatal(1,"timeout/late cleanup switched core or lost TF failure");checks=checks+1;
        wr(13'h1008,0,0);ticket=value;result_code(1);live_state();
        if(requests!=3||tf_packets<10||tf_physical_frames<5||mailbox_checks<12700||drain_checks!=30)$fatal(1,"joint coverage incomplete");
        $display("PASS media_runtime_integration: checks=%0d core_requests=%0d stop_requests=%0d tf_done=%0d tf_failed=%0d physical=%0d observed=%0d tf_packets=%0d tf_physical=%0d mailbox_wait=%0d drain_wait=%0d tf_reads=%0d audio_reads=%0d writes=%0d",checks,requests,stops,tf_done_count,tf_failed_count,physical_frames,observed_frames,tf_packets,tf_physical_frames,mailbox_checks,drain_checks,tf_reads,audio_reads,mem_writes);$finish;
    end
    initial begin #30000000;$fatal(1,"joint integration watchdog state=%0d tfstate=%0d physical=%0d tfpackets=%0d",commands.phase,tf.state,physical_frames,tf_packets);end
endmodule
