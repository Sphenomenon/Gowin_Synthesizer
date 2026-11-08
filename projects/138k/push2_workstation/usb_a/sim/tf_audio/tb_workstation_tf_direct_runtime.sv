`timescale 1ns/1ps
// The real maintained runtime/DSP/DMA/router/DCS/serializer/observation owner.
// Only the external SD card and ordered DDR memory are behavioral models.
module tb_workstation_tf_direct_runtime #(
    parameter bit LOCAL_COMPUTE_RESET_ENABLE=0
);
    // Picosecond simulation precision quantizes these external references.
    // Check the actual supplied clocks, including that quantization.
    localparam realtime REF48_HALF=40.690,REF44_HALF=29.526;
    reg clk50=0,compute_clk=0,memory_clk=0,pclk=0,reference48=0,reference44=0,manual_rn=0,manual_common_rn=0,backend_available=0;
    integer cold_start=0,common_rises=0,common_falls=0,startup_grants=0;
    wire root_common_rn,common_rn=cold_start!=0 ? root_common_rn:manual_common_rn;
    wire guard_started,guard_ready,guard_fault;
    wire rn=cold_start!=0 ? common_rn && guard_started:manual_rn;
    realtime common_release_time=0,startup_grant_delay=0;
    // Actual selected-board root owner, with the external reset permanently
    // deasserted. Initial register values produce its only cold-start pulse.
    reset_release #(.HOLD_CYCLES(1024)) cold_root(
        .clk(clk50),.ext_reset_n(1'b1),.reset_n(root_common_rn));
    workstation_runtime_memory_guard cold_memory_guard(
        .reset_ni(common_rn),.clk_50m_i(clk50),.memory_clk_i(memory_clk),
        .backend_reset_ni(backend_available),.backend_ready_i(backend_available),
        .started_o(guard_started),.fault_o(guard_fault),.start_ready_o(guard_ready),
        .mute_o(),.channel_open_o(),.clock_alive_o(),.fault_code_o());
    always @(posedge common_rn)begin
        common_rises++;common_release_time=$realtime;
        if(cold_start!=0 && $realtime<20480)$fatal(1,"real root reset skipped HOLD_CYCLES=1024");
    end
    always @(negedge common_rn)if($time>0)common_falls++;
    always @(posedge rn)begin
        startup_grants++;startup_grant_delay=$realtime-common_release_time;
        if(cold_start!=0 && (!backend_available || !guard_started || guard_fault || startup_grant_delay<160))
            $fatal(1,"actual memory guard granted before backend qualification");
    end
    always #10 clk50=!clk50;
    always #6.510417 compute_clk=!compute_clk;
    always #5 memory_clk=!memory_clk;
    always #17 pclk=!pclk;
    initial begin #3.7;forever #(REF48_HALF) reference48=!reference48;end
    initial begin #17.2;forever #(REF44_HALF) reference44=!reference44;end
    reg psel=0,penable=0,pwrite=0;reg [11:0] paddr=0;reg [31:0] pwdata=0;
    wire pready,pslverr;wire [31:0] prdata;
    reg rate_request=0,requested_rate=0;
    wire ready,busy,fault,active_valid,active_rate,context_ready,dsp_fault,applied;
    wire [31:0] epoch,tf_control,active,applied_events,control_pitch;
    wire [127:0] held;wire [15:0] master;
    wire mclk,bck,lrck,sd,pdn,smute,frame_valid,frame_error,frame_rate,sample_valid;
    wire [31:0] frame_epoch,frame_sequence,frame_pcm,underruns,observation_drops,deadline_misses;
    wire signed [31:0] observed_left,observed_right;
    wire tf_active,tf_busy,tf_valid,tf_error,tf_last,tf_pause,tf_ready;
    wire signed [15:0] tf_left,tf_right;
    wire [19:0] tf_rate;wire [31:0] tf_generation,tf_session,tf_expected;
    wire physical_eos,physical_quiet,physical_failed,physical_abort;
    wire service_busy,service_failed,service_eof,service_quiet,service_quiet50;
    wire [3:0] service_failure;
    wire tf_stop_request,stop_pending,stop_done,stop_failed;
    wire [3:0] stop_failure;
    reg explicit_stop=0;
    wire ddr_req,ddr_write;wire [28:0] ddr_address;wire [255:0] ddr_data,ddr_read_data;wire [31:0] ddr_mask;
    reg ddr_response=0;
    workstation_runtime_controlled #(.WINDOW_CYCLES(500),.STABLE_WINDOWS(3),.LOSS_TIMEOUT_CYCLES(25),
        .STOP_LOW_CYCLES(8),.STARTUP_MUTE_FRAMES(3),.PDN_HOLD_FRAMES(1),.RECORD_ADDRESS_BITS(4),
        .SEPARATE_COMMON_RESET(1),.TF_DIRECT_ENABLE(1)) dut(
        .rst_ni(rn),.common_reset_ni(common_rn),.clk_50m_i(clk50),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .reference_48_i(reference48),.reference_44_i(reference44),.midi_rx_i(1'b1),.pc_uart_rx_i(1'b1),
        .usb_event_valid(1'b0),.usb_lifecycle(1'b0),.usb_cancel(1'b0),.usb_event_data(18'd0),.usb_event_ready(),
        .pclk(pclk),.preset_n(rn),.psel(psel),.penable(penable),.pwrite(pwrite),.paddr(paddr),.pwdata(pwdata),.pstrb(4'hf),
        .pready(pready),.pslverr(pslverr),.prdata(prdata),.performance_words_o(),
        .request_i(rate_request),.request_44k1_i(requested_rate),.switch_permit_i(1'b1),.recover_i(1'b0),
        .media_quiescent_i(service_quiet50),.request_ready_o(ready),.busy_o(busy),.fault_o(fault),
        .accepted_o(),.applied_o(applied),.rejected_o(),.failed_o(),.policy_rejected_o(),.reject_code_o(),.fault_code_o(),
        .clock_select_o(),.switch_block_reason_o(),.active_44k1_o(active_rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),
        .source_qualified_o(),.quiesce_o(),.stream_flush_o(),.dsp_fault_o(dsp_fault),.context_ready_o(context_ready),
        .pcm_psel_i(1'b0),.pcm_pready_o(),.pcm_pslverr_o(),.pcm_prdata_o(),
        .hci_session_ready_i(1'b0),.hci_controller_epoch_i(32'd0),.hci_transport_generation_i(32'd0),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(1'b0),
        .tf_active_i(tf_active),.tf_busy_i(tf_busy),.tf_valid_i(tf_valid),.tf_error_i(tf_error),
        .tf_left_i(tf_left),.tf_right_i(tf_right),.tf_sample_rate_i(tf_rate),
        .tf_generation_i(tf_generation),.expected_tf_generation_i(tf_expected),.tf_ready_o(tf_ready),
        .tf_last_i(tf_last),.tf_session_i(tf_session),.tf_pause_i(tf_pause),
        .tf_physical_eos_o(physical_eos),.tf_physical_quiescent_o(physical_quiet),
        .tf_physical_failed_o(physical_failed),.tf_physical_abort_o(physical_abort),
        .ddr_req_o(ddr_req),.ddr_write_o(ddr_write),.ddr_address_o(ddr_address),.ddr_data_o(ddr_data),.ddr_mask_o(ddr_mask),
        .ddr_ready_i(1'b1),.ddr_response_i(ddr_response),.ddr_read_data_i(ddr_read_data),
        .mclk_o(mclk),.bck_o(bck),.lrck_o(lrck),.data_o(sd),.pdn_no(pdn),.smute_o(smute),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_44k1_o(frame_rate),
        .frame_epoch_o(frame_epoch),.frame_sequence_o(frame_sequence),.frame_pcm_o(frame_pcm),
        .held_notes_o(held),.control_state_o(),.control_pitch_o(control_pitch),.control_options_o(),.applied_events_o(applied_events),
        .pc_health_o(),.master_volume_o(master),.active_mask_o(active),.scope_status_o(),.tf_scope_control_o(tf_control),
        .deadline_miss_o(deadline_misses),.midi_overflow_o(),.note_drop_o(),.underrun_count_o(underruns),
        .midi_cdc_drop_o(),.observation_drop_o(observation_drops),.record_drop_o(),.uart_error_o(),
        .sample_valid_o(sample_valid),.audio_left_o(observed_left),.audio_right_o(observed_right),
        .record_enabled_o(),.record_failed_o(),.record_failure_code_o(),.score_running_o(),.score_done_o(),.score_failed_o(),
        .led_mask_o(),.score_frame_o(),.fft_valid_o(),.fft_bin_o(),.fft_real_o(),.fft_imag_o(),.fft_frame_o(),
        .fft_discard_count_o(),.fft_44k1_o(),.fft_context_valid_o(),.fft_epoch_o(),
        .display_valid_o(),.display_pcm_o(),.display_reference_o(),.display_voices_o(),.display_status_o(),.display_parameters_o(),
        .display_44k1_o(),.display_error_o(),.display_epoch_o(),.display_sequence_o(),.effect_mask_o(),.effect_order_o(),
        .display_observation_fault_o(),.media_stop_request_i(1'b0),.media_stop_hold_i(1'b0),.media_stop_ready_o(),
        .media_stop_done_o(),.media_stop_failed_o(),.media_stop_failure_code_o(),
        .tf_stop_request_o(tf_stop_request),.tf_stop_pending_i(stop_pending),.tf_stop_done_i(stop_done),
        .tf_stop_failed_i(stop_failed),.tf_stop_failure_code_i(stop_failure));

    wire control_valid;wire [31:0] control50;
    wire scope_mode,scope_run,scope_restart,scope_cancel,scope_error,explicit_restart,file_cancel;
    wire [3:0] scope_track,reader_track;wire reader_restart;
    wire playlist_ready,card_lost;wire [4:0] track_count;
    gw138k_stream_cdc #(.WIDTH(32)) accepted_tf_control(
        .reset_n(rn),.source_clk(compute_clk),.destination_clk(clk50),.source_valid(1'b1),.source_data(tf_control),
        .drop_count(),.destination_valid(control_valid),.destination_data(control50));
    scope_tf_transport transport(.clk_i(clk50),.rst_ni(rn),.control_valid_i(control_valid),.control_i(control50),
        .song_valid_i(1'b0),.song_track_i(4'd0),.playlist_ready_i(playlist_ready),.card_lost_i(card_lost),.track_count_i(track_count),
        .mode_o(scope_mode),.run_o(scope_run),.track_o(scope_track),.restart_o(scope_restart),.cancel_analysis_o(scope_cancel),
        .error_o(scope_error),.explicit_restart_o(explicit_restart),.file_cancel_o(file_cancel));
    workstation_playback_service #(.RECOGNITION_ENABLE(0)) playback(
        .clk_i(clk50),.rst_ni(rn),.model_status_i(4'd0),.tf_mode_i(scope_mode),.tf_restart_i(scope_restart),.cancel_i(scope_cancel),
        .tf_track_i(scope_track),.song_valid_i(1'b0),.song_track_i(4'd0),.playlist_ready_i(playlist_ready),.track_count_i(track_count[3:0]),
        .card_lost_i(card_lost),.analysis_done_i(1'b0),.analysis_enable_o(),.analysis_restart_o(),.analysis_hold_o(),
        .reader_restart_o(reader_restart),.reader_track_o(reader_track),.score_accept_o());
    wire ssn,sck,mosi,miso;
    workstation_tf_direct_runtime_service #(.SPI_CLK_DIV(2),.SPI_CLK_DIV_FAST(2),
        .LOCAL_COMPUTE_RESET_ENABLE(LOCAL_COMPUTE_RESET_ENABLE),
        .TOKEN_WAIT_CLOCKS(1000),.WATCHDOG_CLOCKS(500000),.QUIET_TIMEOUT_CYCLES(2000000),.SEPARATE_COMMON_RESET(1)) source(
        .rst_ni(rn),.common_reset_ni(common_rn),.clk_50m_i(clk50),.compute_clk_i(compute_clk),
        .mode_i(scope_mode),.run_i(scope_run),.restart_i(explicit_restart),.cancel_i(file_cancel),.transport_error_i(scope_error),
        .track_index_i(reader_track),.runtime_valid_i(active_valid),.runtime_44k1_i(active_rate),
        .runtime_fault_i(fault || dsp_fault),.runtime_busy_i(busy),.runtime_epoch_i(epoch),
        .sd_miso_i(miso),.sd_cs_no(ssn),.sd_sck_o(sck),.sd_mosi_o(mosi),
        .track_count_o(track_count),.playlist_ready_o(playlist_ready),.card_lost_o(card_lost),
        .playlist_name_address_i(8'd0),.playlist_name_data_o(),.format_ready_o(),.unsupported_o(),.file_sample_rate_o(),
        .busy_50_o(service_busy),.failed_o(service_failed),.failure_code_o(service_failure),.eof_seen_o(service_eof),
        .media_quiescent_50_o(service_quiet50),.tf_active_o(tf_active),.tf_busy_o(tf_busy),.tf_valid_o(tf_valid),.tf_error_o(tf_error),
        .tf_last_o(tf_last),.tf_pause_o(tf_pause),.tf_left_o(tf_left),.tf_right_o(tf_right),.tf_sample_rate_o(tf_rate),
        .tf_generation_o(tf_generation),.tf_session_o(tf_session),.expected_generation_o(tf_expected),.tf_ready_i(tf_ready),
        .media_quiescent_o(service_quiet),.physical_eos_i(physical_eos),.physical_quiescent_i(physical_quiet),
        .physical_failed_i(physical_failed),.physical_abort_i(physical_abort),.stop_request_i(tf_stop_request || explicit_stop),
        .stop_pending_o(stop_pending),.stop_done_o(stop_done),.stop_failed_o(stop_failed),.stop_failure_code_o(stop_failure));
    wire integer card_commands,card_bytes,card_crc,card_post,card_cs,card_high;
    workstation_tf_file_wire_card card(.ssn(ssn),.sck(sck),.mosi(mosi),.miso(miso),.token_delay_bytes(2),
        .hold_init(1'b0),.fault_lba(32'hffffffff),.fault_kind(0),.suppress_token(1'b0),.command_error(1'b0),.suppress_r1(1'b0),
        .cmd17_count(card_commands),.payload_bytes(card_bytes),.crc_bytes(card_crc),.post_crc_bytes(card_post),.cs_releases(card_cs),.high_clocks(card_high));

    // Real ordered owner6 memory traffic and BL8 data. TF has no memory port.
    reg [255:0] memory[0:4095],qdata[0:63],read_data=0;
    reg [28:0] qaddr[0:63];reg qwrite[0:63];
    integer head=0,tail=0,queued=0,memory_ticks=0,writes=0,reads=0;
    assign ddr_read_data=read_data;
    always @(posedge memory_clk)begin
        ddr_response<=0;
        if(rn)begin
            if(ddr_req)begin
                if(queued>=64 || ddr_address<29'h0c000000 || ddr_address>=29'h0c008000 || ddr_address[2:0]!=0 || ddr_mask!=0)
                    $fatal(1,"real owner6 DDR allocation/alignment/mask");
                qdata[tail]=ddr_data;qaddr[tail]=ddr_address;qwrite[tail]=ddr_write;tail=(tail+1)%64;queued++;
            end
            if(queued!=0)begin
                if(memory_ticks==3)begin
                    memory_ticks=0;
                    if(qwrite[head])begin memory[12'((qaddr[head]-29'h0c000000)>>3)]=qdata[head];writes++;end
                    else begin read_data<=memory[12'((qaddr[head]-29'h0c000000)>>3)];ddr_response<=1;reads++;end
                    head=(head+1)%64;queued--;
                end else memory_ticks++;
            end
        end
    end
    reg [31:0] oracle0[0:12000],oracle1[0:12000];
    reg [2047:0] oracle_path0,oracle_path1;
    integer target_rate=48000,first_file_frames=97,file_frames=97,mode=0,current_track=0,delivered0=0,delivered1=0;
    integer tf_fires=0,physical_tf=0,physical_tf0=0,physical_tf1=0,eos_count=0,observed_count=0,physical_count=0,synth_nonzero=0,synth_after=0;
    integer render_service_requests=0,serial_requests=0,bit_checks=0,period_checks=0;
    integer pause_checks=0,boundary_checks=0,abort_count=0,stop_count=0,expected_failure=0;
    reg inflight_watch=0,inflight_invalidate_seen=0,inflight_native_ack=0;
    integer inflight_base_payload,inflight_base_crc,inflight_base_post,inflight_base_cs,inflight_base_high,inflight_commands;
    integer inflight_payload_at_cancel=0,inflight_quiet_ns=0,inflight_ack_after_cs_ns=0,inflight_release_clocks=0;
    realtime inflight_start_time=0,inflight_cs_time=0,inflight_spi_done_time=0,inflight_sector_done_time=0,inflight_reader_cancel_time=0;
    reg after_tf=0;
    reg expected_tf[0:7][0:32767],physical_seen[0:7][0:32767];
    reg expected_track[0:7][0:32767];
    reg [31:0] expected_tf_pcm[0:7][0:32767],physical_values[0:7][0:32767];
    reg [31:0] decoded=0,last_decoded=0;
    integer physical_position=0;
    realtime previous_bck=0,previous_frame=0;
    reg [31:0] gold;
    always @(posedge compute_clk)if(rn)begin
        if(dut.runtime.render_request && dut.runtime.service_ready)render_service_requests++;
        if(tf_valid && tf_ready)begin
            if(tf_error || tf_rate!=20'(target_rate))$fatal(1,"direct packet error/rate");
            if(current_track==0)begin
                if(delivered0>=first_file_frames)$fatal(1,"duplicate first file PCM");gold=oracle0[delivered0];delivered0++;
                if(tf_last!==(delivered0==first_file_frames))$fatal(1,"first file atomic LAST");
            end else begin
                if(delivered1>=file_frames)$fatal(1,"duplicate second file PCM");gold=oracle1[delivered1];delivered1++;
                if(tf_last!==(delivered1==file_frames))$fatal(1,"second file atomic LAST");
            end
            if({tf_right,tf_left}!==gold)$fatal(1,"SPI/FAT/WAV actual PCM differs from independent Python oracle");
            if(dut.runtime.final_pcm.next_gain!=16'h8000)$fatal(1,"pause/arming changed final master gain");
            if(dut.runtime.bridge_epoch>=8 || dut.runtime.bridge_sequence>=32768)$fatal(1,"expected queue capacity");
            expected_tf[dut.runtime.bridge_epoch][dut.runtime.bridge_sequence]=1;
            expected_track[dut.runtime.bridge_epoch][dut.runtime.bridge_sequence]=(current_track!=0);
            expected_tf_pcm[dut.runtime.bridge_epoch][dut.runtime.bridge_sequence]={gold[15:0],gold[31:16]};tf_fires++;
        end
        if(physical_eos)begin
            if(physical_failed || frame_error)$fatal(1,"false physical EOF");eos_count++;
        end
        if(physical_abort)abort_count++;
        if(sample_valid)begin
            if(!physical_seen[dut.observed_epoch][dut.observed_sequence] ||
               {observed_left[31:16],observed_right[31:16]}!==physical_values[dut.observed_epoch][dut.observed_sequence])
                $fatal(1,"real completed-frame observation detached from serial PCM");
            observed_count++;
        end
    end
    always @(negedge dut.runtime.serial_reset_n)begin physical_position=0;decoded=0;last_decoded=0;previous_bck=0;previous_frame=0;end
    always @(bck)if(dut.runtime.serial_reset_n && dut.runtime.serializer.configured)begin
        if(previous_bck>0 && ($realtime-previous_bck<(dut.runtime.serializer.mode_44k1 ? 6*REF44_HALF:4*REF48_HALF)-0.1 ||
           $realtime-previous_bck>(dut.runtime.serializer.mode_44k1 ? 6*REF44_HALF:4*REF48_HALF)+0.1))
            $fatal(1,"real BCK period changed delta=%f serializer_rate=%b serial_rate=%b active_rate=%b",$realtime-previous_bck,
                dut.runtime.serializer.mode_44k1,dut.runtime.serial_rate,active_rate);
        previous_bck=$realtime;bit_checks++;
    end
    always @(posedge bck)begin
        #0.1;
        if(dut.runtime.serial_reset_n)begin
            if(lrck!==(physical_position>=32))$fatal(1,"I2S LRCK identity");
            if(physical_position>=1 && physical_position<=16)decoded[32-physical_position]=sd;
            else if(physical_position>=33 && physical_position<=48)decoded[48-physical_position]=sd;
            else if(sd!==0)$fatal(1,"I2S padding");
            if(physical_position==63)begin last_decoded=decoded;decoded=0;physical_position=0;end
            else physical_position++;
        end
    end
    always @(negedge mclk)if(rn && dut.runtime.serial_reset_n)begin
        if(dut.runtime.serial_request)serial_requests++;
        if(frame_valid)begin
            if(frame_epoch>=8 || frame_sequence>=32768 || frame_pcm!==last_decoded)$fatal(1,"physical serial PCM/context");
            if(frame_error)$fatal(1,"healthy real runtime error frame epoch=%0d seq=%0d",frame_epoch,frame_sequence);
            if(previous_frame>0 && ($realtime-previous_frame<(frame_rate ? 768*REF44_HALF:512*REF48_HALF)-0.2 ||
               $realtime-previous_frame>(frame_rate ? 768*REF44_HALF:512*REF48_HALF)+0.2))
                $fatal(1,"serial sample schedule paused delta=%f physical_rate=%b",$realtime-previous_frame,frame_rate);
            previous_frame=$realtime;period_checks++;
            physical_seen[frame_epoch][frame_sequence]=1;physical_values[frame_epoch][frame_sequence]=frame_pcm;
            physical_count++;
            if(expected_tf[frame_epoch][frame_sequence])begin
                if(frame_pcm!==expected_tf_pcm[frame_epoch][frame_sequence])$fatal(1,"physical TF PCM differs from source oracle");physical_tf++;
                if(expected_track[frame_epoch][frame_sequence])physical_tf1++;else physical_tf0++;
            end else if(frame_pcm!=0 && !scope_mode && !tf_busy)begin
                if(after_tf)synth_after++;else synth_nonzero++;
            end
        end
    end
    always @(posedge clk50)if(rn && stop_done)stop_count++;
    // Observe the public card wire's actual payload/CRC and chip-select
    // release. Native ACK and source quiet must follow that wire completion.
    always @(posedge ssn)if(inflight_watch && inflight_cs_time==0 &&
        card_bytes>=inflight_base_payload+512 && card_crc>=inflight_base_crc+2)
            inflight_cs_time=$realtime;
    always @(posedge clk50)if(rn && inflight_watch)begin
        if(source.invalidate && !inflight_invalidate_seen)begin
            inflight_payload_at_cancel=card_bytes-inflight_base_payload;
            if(inflight_payload_at_cancel<32 || inflight_payload_at_cancel>=512 || ssn || card.phase!=2)
                $fatal(1,"long-file cancel was not actually accepted within SPI payload");
            inflight_invalidate_seen=1;
            $display("TRACE inflight invalidate_ns=%0d session=%0d generation=%0d payload_offset=%0d",integer'($realtime),source.session,tf_generation,inflight_payload_at_cancel);
        end
        if(source.native.file_owner.u_sector_reader.spidone && inflight_spi_done_time==0)begin
            if(inflight_cs_time==0 || card_high<inflight_base_high+8 || !ssn)
                $fatal(1,"actual SPI session done preceded CS-high release clocks");
            inflight_spi_done_time=$realtime;
            $display("TRACE inflight SPI_done_ns=%0d session=%0d generation=%0d",integer'($realtime),source.session,tf_generation);
        end
        if(source.native.file_owner.read_done && inflight_sector_done_time==0)begin
            if(inflight_spi_done_time==0 || $realtime<inflight_spi_done_time)$fatal(1,"sector done preceded SPI session done");
            inflight_sector_done_time=$realtime;
            $display("TRACE inflight sector_done_ns=%0d session=%0d generation=%0d",integer'($realtime),source.session,tf_generation);
        end
        if(source.native.reader_cancelled && inflight_reader_cancel_time==0)begin
            if(inflight_sector_done_time==0 || $realtime<=inflight_sector_done_time)$fatal(1,"file cancellation ACK preceded sector done");
            inflight_reader_cancel_time=$realtime;
            $display("TRACE inflight reader_cancelled_ns=%0d session=%0d generation=%0d",integer'($realtime),source.session,tf_generation);
        end
        if(source.native_stop_done)begin
            if(!inflight_invalidate_seen || inflight_cs_time==0 || $realtime<=inflight_cs_time ||
               card_bytes!=inflight_base_payload+512 || card_crc!=inflight_base_crc+2 ||
               card_post!=inflight_base_post || card_cs<=inflight_base_cs || card_high<inflight_base_high+8 ||
               !ssn || source.native.sector_busy_o || inflight_reader_cancel_time==0 || $realtime<=inflight_reader_cancel_time)
                $fatal(1,"native stop ACK preceded full SPI payload/CRC/CS drain inv=%b cs_time=%f now=%f payload=%0d/%0d CRC=%0d/%0d post=%0d/%0d CS=%0d/%0d ssn=%b busy=%b phase=%0d",
                    inflight_invalidate_seen,inflight_cs_time,$realtime,card_bytes,inflight_base_payload+512,
                    card_crc,inflight_base_crc+2,card_post,inflight_base_post,card_cs,inflight_base_cs,
                    ssn,source.native.sector_busy_o,card.phase);
            inflight_native_ack=1;inflight_ack_after_cs_ns=integer'($realtime-inflight_cs_time);
            inflight_release_clocks=card_high-inflight_base_high;
            $display("TRACE inflight native_stop_ACK_ns=%0d session=%0d generation=%0d CS_release_ns=%0d high_clocks=%0d",integer'($realtime),source.session,tf_generation,integer'(inflight_cs_time),inflight_release_clocks);
        end
        if(service_quiet50 && !inflight_native_ack)$fatal(1,"long-file source quiet preceded native drain ACK");
    end
    always @(negedge clk50)if(rn)begin
        if(fault || dsp_fault || (service_failed && (expected_failure==0 || service_failure!=expected_failure)) ||
           physical_failed || underruns || observation_drops || deadline_misses)
            $fatal(1,"healthy real direct integration failed runtime=%b dsp=%b source=%b code=%0d physical=%b underrun=%0d obs=%0d deadlines=%0d state=%0d",
                fault,dsp_fault,service_failed,service_failure,physical_failed,underruns,observation_drops,deadline_misses,source.state);
    end
    always @(negedge clk50)if(cold_start!=0 && !rn)begin
        if(tf_ready || tf_valid || dut.runtime.g_direct_tf.tail.armed_o ||
           dut.runtime.g_direct_tf.tail.arm_pending || dut.runtime.serial_reset_n)
            $fatal(1,"actual root cold start bypassed runtime startup grant");
    end
    task frames(input integer n);integer goal;begin goal=observed_count+n;wait(observed_count>=goal);@(negedge compute_clk);end endtask
    task apb_write(input [11:0] address,input [31:0] data);
        integer n;
        begin
            @(negedge pclk);psel=1;penable=0;pwrite=1;paddr=address;pwdata=data;
            @(negedge pclk);penable=1;n=0;
            do begin @(posedge pclk);#0.1;n++;end while(!pready && n<10000);
            if(!pready || pslverr)$fatal(1,"real APB command failure %h",address);
            @(negedge pclk);psel=0;penable=0;
        end
    endtask
    task event_cpu(input [3:0] kind,input [6:0] address,value);
        begin apb_write(12'h180,{14'd0,kind,address,value});end
    endtask
    task await_idle_voices;
        integer cycles;
        begin
            cycles=0;
            while(active!=0 && cycles<25000000)begin @(negedge compute_clk);cycles++;end
            if(active!=0 || held!=0)$fatal(1,"real release did not retire voice");
        end
    endtask
    task begin_inflight_boundary;
        begin
            @(posedge clk50);
            while(!source.native.data_sector_start_o)@(posedge clk50);
            inflight_base_payload=card_bytes;inflight_base_crc=card_crc;
            inflight_base_post=card_post;inflight_base_cs=card_cs;inflight_base_high=card_high;
            if(inflight_base_payload%512!=0)$fatal(1,"sector start was not at a complete payload boundary");
            if(!tf_active || source.state!=4 || source.PREFILL_FRAMES!=3072 ||
               source.PCM_DEPTH!=4096 || source.BYTE_DEPTH!=4096 || first_file_frames<=4096)
                $fatal(1,"long case bypassed production PLAY/prefill/queue depth");
            $display("TRACE inflight data_sector_start_ns=%0d session=%0d generation=%0d LBA=%0d completed_sectors=%0d first_file_frames=%0d prefill=%0d PCM_depth=%0d BYTE_depth=%0d",integer'($realtime),source.session,tf_generation,source.native.file_owner.read_sector_no,inflight_base_payload/512,first_file_frames,source.PREFILL_FRAMES,source.PCM_DEPTH,source.BYTE_DEPTH);
            wait(card_bytes>=inflight_base_payload+32);@(negedge clk50);
            if(ssn || card.phase!=2 || card_crc!=inflight_base_crc || !source.native.sector_busy_o)
                $fatal(1,"long-file boundary failed to reach actual SPI payload");
            inflight_commands=card_commands;inflight_start_time=$realtime;inflight_watch=1;
        end
    endtask
    reg [32:0] paused_head;
    reg [31:0] paused_generation,paused_session;
    integer paused_fires,paused_serial,boundary_fires,boundary_physical,boundary_serial,wanted_eos=2;
    initial begin
        if(!$value$plusargs("ORACLE0=%s",oracle_path0) || !$value$plusargs("ORACLE1=%s",oracle_path1))$fatal(1,"missing oracle paths");
        if(!$value$plusargs("RATE=%d",target_rate))target_rate=48000;
        if(!$value$plusargs("FIRST_FRAMES=%d",first_file_frames))first_file_frames=97;
        if(!$value$plusargs("FRAMES=%d",file_frames))file_frames=97;
        if(!$value$plusargs("MODE=%d",mode))mode=0;
        if(!$value$plusargs("COLD_START=%d",cold_start))cold_start=0;
        $readmemh(oracle_path0,oracle0);$readmemh(oracle_path1,oracle1);
        for(integer e=0;e<8;e++)for(integer s=0;s<32768;s++)begin expected_tf[e][s]=0;physical_seen[e][s]=0;end
        for(integer i=0;i<4096;i++)memory[i]=0;
        repeat(4)@(negedge clk50);
        if(cold_start!=0)begin
            if(common_rn!==0 || cold_root.HOLD_CYCLES!=1024)$fatal(1,"root reset did not start asserted with production hold");
            wait(common_rn);@(negedge clk50);
        end else manual_common_rn=1;
        repeat(8)begin
            @(negedge clk50);
            if(tf_ready || tf_valid || dut.runtime.g_direct_tf.tail.armed_o ||
               dut.runtime.g_direct_tf.tail.arm_pending || dut.runtime.serial_reset_n)
                $fatal(1,"separate common reset bypassed startup grant");
        end
        if(cold_start!=0)begin backend_available=1;wait(rn);end
        else manual_rn=1;
        wait(ready && active_valid && context_ready && playlist_ready);
        if(track_count!=2)$fatal(1,"real FAT scan missing two tracks");
        if(target_rate==44100)begin
            @(negedge clk50);requested_rate=1;rate_request=1;
            @(negedge clk50);rate_request=0;wait(busy);wait(!busy && ready && active_rate);frames(4);
        end
        event_cpu(2,7,127);event_cpu(1,60,127);frames(192);
        if(!held[60] || active==0 || synth_nonzero==0 || render_service_requests<100)$fatal(1,"real synth before TF was silent");
        event_cpu(0,60,0);await_idle_voices();frames(4);
        event_cpu(2,104,127);wait(scope_mode && scope_run);
        if(mode==1)begin
            wait(delivered0>=17);event_cpu(2,105,0);wait(tf_pause);frames(4);
            paused_head={tf_last,tf_right,tf_left};paused_generation=tf_generation;paused_session=tf_session;
            paused_fires=tf_fires;paused_serial=serial_requests;frames(8);
            if(tf_ready || tf_fires!=paused_fires || serial_requests<=paused_serial ||
               !tf_valid || {tf_last,tf_right,tf_left}!==paused_head ||
               tf_generation!=paused_generation || tf_session!=paused_session)$fatal(1,"pause consumed/replaced TF head or stopped serial schedule");
            pause_checks++;event_cpu(2,105,64);wait(!tf_pause);
        end
        if(mode<2)begin
            wait(eos_count==1);wait(service_eof);frames(2);
            if(delivered0!=first_file_frames || physical_tf0!=first_file_frames || tf_fires!=first_file_frames || !service_eof)
                $fatal(1,"first real TF file did not physically complete frames=%0d physical=%0d eos=%0d",delivered0,physical_tf0,eos_count);
            current_track=1;event_cpu(2,106,1);
        end else begin
            wait(delivered0>=17);
            if(mode>=6)begin_inflight_boundary();
            if(mode==2 || mode==6)event_cpu(2,104,0);
            else if(mode==3 || mode==7)begin
                @(negedge clk50);explicit_stop=1;
                @(negedge clk50);explicit_stop=0;
                wait(stop_count==1);
            end else if(mode==4)begin
                expected_failure=6;event_cpu(2,120,0);
                wait(abort_count!=0);wait(service_failed);
                if(service_failure!=6)$fatal(1,"PANIC did not return physical abort to source");
            end else if(mode==5)begin
                expected_failure=5;event_cpu(2,106,15);
                wait(scope_error && service_failed);
                if(service_failure!=5 || source.native_file_error)$fatal(1,"invalid track bypassed transport bounds");
            end else $fatal(1,"unsupported runtime test mode");
            wait(!tf_busy && service_quiet50);
            if(mode>=6)inflight_quiet_ns=integer'($realtime-inflight_start_time);
            frames(4);
            if(mode>=6)begin
                if(!inflight_invalidate_seen || !inflight_native_ack || card_commands!=inflight_commands)
                    $fatal(1,"in-flight cancel lost ACK or issued a later old-session SPI command");
                inflight_watch=0;
            end
            if(eos_count!=0 || service_eof || delivered0>=first_file_frames || physical_tf0!=delivered0 || stop_failed)
                $fatal(1,"cancel/stop/PANIC/error produced false EOF/quiet source=%0d physical=%0d eos=%0d",delivered0,physical_tf0,eos_count);
            boundary_fires=tf_fires;boundary_physical=physical_tf;boundary_serial=serial_requests;frames(8);
            if(tf_fires!=boundary_fires || physical_tf!=boundary_physical || serial_requests<=boundary_serial)
                $fatal(1,"retired TF session leaked or serial cadence stopped");
            boundary_checks++;
            if(scope_mode)event_cpu(2,104,0);
            wait(!scope_mode && service_quiet50);
            if(mode==4)begin
                // Only a real accepted NoteOn clears the existing PANIC
                // mute. No hierarchical force/reset bypasses that policy.
                boundary_physical=synth_nonzero;
                event_cpu(1,67,127);frames(96);
                if(!held[67] || active==0 || synth_nonzero<=boundary_physical)
                    $fatal(1,"real NoteOn did not restore base synth after PANIC");
                event_cpu(0,67,0);await_idle_voices();frames(4);
            end
            wanted_eos=1;current_track=1;event_cpu(2,106,1);event_cpu(2,104,127);
            wait(scope_mode && scope_run && !service_failed);expected_failure=0;
        end
        wait(eos_count==wanted_eos);wait(service_eof);frames(2);
        if(delivered1!=file_frames || physical_tf1!=file_frames || tf_fires!=delivered0+file_frames)
            $fatal(1,"second TF track identity/tail failed");
        event_cpu(2,104,0);wait(!scope_mode && !tf_busy && service_quiet50);
        after_tf=1;event_cpu(1,64,127);frames(192);
        if(!held[64] || active==0 || synth_after==0)$fatal(1,"real synth did not resume after TF");
        event_cpu(0,64,0);frames(4);
        if(card_commands==0 || card_bytes==0 || card_crc==0 || writes==0 || serial_requests<physical_count || observed_count==0 || bit_checks==0)
            $fatal(1,"required actual SPI/DMA/serial traffic absent");
        if(cold_start!=0 && (common_rises!=1 || common_falls!=0 || manual_common_rn!=0 || !root_common_rn ||
            startup_grants!=1 || !guard_started || !guard_ready || guard_fault || manual_rn!=0))
            $fatal(1,"actual root common reset was manually pulsed or released more than once");
        $display("PASS tf_direct_runtime rate=%0d mode=%0d stereo_bits=16 tracks=2 source_frames=%0d physical_tf=%0d physical_eos=%0d synth_before=%0d synth_after=%0d real_DSP_requests=%0d serial_requests=%0d physical_frames=%0d observations=%0d BCK_checks=%0d schedule_checks=%0d pause_checks=%0d boundary_checks=%0d physical_aborts=%0d stop_completions=%0d DDR_owner6_writes=%0d DDR_owner6_reads=%0d SPI_commands=%0d SPI_bytes=%0d SPI_CRC_bytes=%0d",target_rate,mode,tf_fires,physical_tf,eos_count,synth_nonzero,synth_after,render_service_requests,serial_requests,physical_count,observed_count,bit_checks,period_checks,pause_checks,boundary_checks,abort_count,stop_count,writes,reads,card_commands,card_bytes,card_crc);
        if(mode>=6)$display("inflight_payload_at_cancel=%0d inflight_quiet_ns=%0d native_ACK_after_CS_ns=%0d CS_high_release_clocks=%0d",inflight_payload_at_cancel,inflight_quiet_ns,inflight_ack_after_cs_ns,inflight_release_clocks);
        if(cold_start!=0)$display("actual_root_cold_start=1 reset_HOLD_CYCLES=1024 common_rises=%0d common_falls=%0d actual_memory_guard=1 startup_grants=%0d startup_grant_delay_ns=%0d",common_rises,common_falls,startup_grants,integer'(startup_grant_delay));
        $finish;
    end
    initial begin #1000000000;$fatal(1,"real direct runtime watchdog source_state=%0d delivered=%0d/%0d EOS=%0d source_busy=%b active=%h",source.state,delivered0,delivered1,eos_count,service_busy,active);end
endmodule
