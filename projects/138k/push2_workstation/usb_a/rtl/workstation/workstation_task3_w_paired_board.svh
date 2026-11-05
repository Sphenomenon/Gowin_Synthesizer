// Native W paired board composition. The HCI physical engine remains the only
// CPU/BLE recording object; this include replaces only its storage/source wiring.
    wire task3_media_select=psel && paddr[31:12]==20'hf8070;
    wire task3_media_bus_ready=1'b1,task3_media_bus_error=task3_media_select;
    wire [31:0] task3_media_bus_data=32'h57335031;
    wire task3_record_pcm_valid,task3_record_source_allowed,task3_record_object_idle,task3_record_source_needed;
    wire [31:0] task3_record_pcm,task3_record_sequence;
    wire task3_pcm_reset_n,task3_pcm_valid,task3_pcm_ready,task3_pcm_write,task3_pcm_error;
    wire [11:0] task3_pcm_address;
    wire [31:0] task3_pcm_data,task3_pcm_response;
    wire [3:0] task3_pcm_strobes;
    // The original PCM1 aperture now ends at the REMOTE proxy, not W DSP.
    gw138k_apb_cdc u_task3_pcm_control(
        .reset_n(preset_n && reset_n),.pclk(pclk),.audio_clk(clk_50m),
        .psel(pcm_select),.penable(penable),.pwrite(pwrite),.paddr(paddr[11:0]),.pwdata(pwdata),.pstrb(pstrb),
        .pready(pcm_bus_ready),.pslverr(pcm_bus_error),.prdata(pcm_bus_data),
        .command_reset_n(task3_pcm_reset_n),.command_valid(task3_pcm_valid),.command_ready(task3_pcm_ready),
        .command_write(task3_pcm_write),.command_address(task3_pcm_address),.command_data(task3_pcm_data),.command_strobes(task3_pcm_strobes),
        .response_error(task3_pcm_error),.response_data(task3_pcm_response));
    wire [1:0] task3_remote_ready,task3_remote_error;
    wire [63:0] task3_remote_response;
    assign task3_pcm_ready=task3_remote_ready[0],task3_pcm_error=task3_remote_error[0],task3_pcm_response=task3_remote_response[31:0];
    assign clock_command_ready=task3_remote_ready[1],clock_response_error=task3_remote_error[1],clock_response_data=task3_remote_response[63:32];
    wire task3_desc_valid,task3_desc_ready,task3_frame_valid,task3_frame_ready,task3_seal_valid,task3_seal_ready;
    wire task3_cancel_valid,task3_cancel_ready,task3_score_valid,task3_score_ready,task3_terminal_valid,task3_terminal_ready;
    wire [199:0] task3_desc;
    wire [191:0] task3_frame,task3_seal;
    wire [127:0] task3_cancel;
    wire [166:0] task3_score;
    wire [163:0] task3_terminal;
    wire [3:0] task3_actual_model_status;
    wire task3_memory_transport_fault;
`ifdef WORKSTATION_TASK3_PHONE_WINDOW_BLOCK
    localparam bit TASK3_PHONE_WINDOW_BLOCK=1'b1;
`else
    localparam bit TASK3_PHONE_WINDOW_BLOCK=1'b0;
`endif
`ifdef WORKSTATION_TASK3_PHONE_BATCH
    localparam bit TASK3_PHONE_BATCH=1'b1;
    workstation_task3_w_bus_endpoint #(.BLOCK_PCM(1'b1),.PHONE_WINDOW_BLOCK(TASK3_PHONE_WINDOW_BLOCK),.PHONE_BATCH(TASK3_PHONE_BATCH)) u_task3_bus_endpoint(
`else
    localparam bit TASK3_PHONE_BATCH=1'b0;
    workstation_task3_w_bus_endpoint #(.BLOCK_PCM(1'b1),.PHONE_WINDOW_BLOCK(TASK3_PHONE_WINDOW_BLOCK)) u_task3_bus_endpoint(
`endif
        .clk_i(clk_50m),.reset_ni(reset_n),.link_ready_i(task3_pair_link_ready),.panic_i(task3_pair_panic),
        .local_boot_i(task3_pair_local_boot),.peer_boot_i(task3_pair_peer_boot),.session_i(task3_pair_session),.generation_i(task3_pair_generation),
        .rx_valid_i(task3_pair_rx_valid),.rx_ready_o(task3_pair_rx_ready),.rx_channel_i(task3_pair_rx_channel),.rx_payload_i(task3_pair_rx_payload),.rx_length_i(task3_pair_rx_length),
        .tx_valid_o(task3_pair_tx_valid),.tx_ready_i(task3_pair_tx_ready),.tx_channel_o(task3_pair_tx_channel),.tx_payload_o(task3_pair_tx_payload),.tx_length_o(task3_pair_tx_length),
        .cnn_desc_valid_o(task3_desc_valid),.cnn_desc_ready_i(task3_desc_ready),.cnn_desc_o(task3_desc),
        .cnn_frame_valid_o(task3_frame_valid),.cnn_frame_ready_i(task3_frame_ready),.cnn_frame_o(task3_frame),
        .cnn_seal_valid_o(task3_seal_valid),.cnn_seal_ready_i(task3_seal_ready),.cnn_seal_o(task3_seal),
        .cnn_cancel_valid_o(task3_cancel_valid),.cnn_cancel_ready_i(task3_cancel_ready),.cnn_cancel_o(task3_cancel),
        .cnn_score_valid_i(task3_score_valid),.cnn_score_ready_o(task3_score_ready),.cnn_score_i(task3_score),
        .cnn_terminal_valid_i(task3_terminal_valid),.cnn_terminal_ready_o(task3_terminal_ready),.cnn_terminal_i(task3_terminal),
        .backend_ready_i(recording_channel_ready50),.model_status_i(task3_actual_model_status),
        .record_object_idle_i(task3_record_object_idle && raw_start_ready && !raw_fault),
        .record_source_needed_i(task3_record_source_needed),
        // Native DDR dispatch fences immediately in its own domain. Its sticky
        // fault withdraws client readiness through ready_control's two flops;
        // do not bypass them with the memory-domain combinational fault cone.
        .record_transport_fault_i(!recording_channel_ready50 || raw_channel_fault),
        .record_pcm_valid_o(task3_record_pcm_valid),.record_source_allowed_o(task3_record_source_allowed),
        .record_pcm_o(task3_record_pcm),.record_sequence_o(task3_record_sequence),.record_fault_o(),.record_failure_o(),
        .hci_classic_ready_i(hci_pcm_session_ready),.phone_owner_ready_i(task3_pcm_reset_n && clock_command_reset_n),
        .hci_epoch_i(hci_pcm_controller_epoch),.hci_generation_i(hci_pcm_transport_generation),
        .command_valid_i({clock_command_valid,task3_pcm_valid}),.command_write_i({clock_command_write,task3_pcm_write}),
        .command_address_i({clock_command_address,task3_pcm_address}),.command_data_i({clock_command_data,task3_pcm_data}),
        .command_strobes_i({clock_command_strobes,task3_pcm_strobes}),.command_ready_o(task3_remote_ready),
        .response_error_o(task3_remote_error),.response_data_o(task3_remote_response),.phone_fault_o(),.malformed_packets_o(),.stale_packets_o());
    workstation_task3_w_paired #(.CNN_USE_DDR_SIGNAL(1'b0),.CNN_USE_DDR_CQT_COEFF(1'b0)) u_task3_media(
        .clk_i(clk_50m),
        .reset_ni(reset_n),
        .memory_clk_i(memory_clk),
        .memory_reset_ni(memory_reset_n),
        .memory_calibrated_i(memory_calibrated),
        .memory_pll_locked_i(memory_pll_locked),
        .client_reset_no(ddr_client_reset_n),
        .client_ready_o(ddr_client_ready),
        .control_ready_o(recording_channel_ready50),
        .memory_flags_o(memory_flags),
        .slot_accept_o(),
        .core_accept_o(),
        .native_accept_o(),
        .transport_fault_o(task3_memory_transport_fault),
        .delay_valid_i(delay_ddr_req),
        .delay_write_i(delay_ddr_write),
        .delay_address_i(delay_ddr_address),
        .delay_data_i(delay_ddr_data),
        .delay_ready_o(delay_ddr_ready),
        .delay_response_o(delay_ddr_response),
        .response_data_o(client_rdata),
        .raw_start_valid_i(raw_start_valid),
        .raw_clear_valid_i(raw_clear_valid),
        .raw_capture_valid_i(raw_capture_valid),
        .raw_capture_index_i(raw_capture_index),
        .raw_capture_pcm_i(raw_capture_pcm),
        .raw_close_valid_i(raw_close_valid),
        .raw_fetch_valid_i(raw_fetch_valid),
        .raw_fetch_offset_i(raw_fetch_offset),
        .raw_fetch_length_i(raw_fetch_length),
        .raw_sample_addr_i(raw_sample_addr),
        .raw_start_ready_o(raw_start_ready),
        .raw_start_done_o(raw_start_done),
        .raw_clear_ready_o(raw_clear_ready),
        .raw_clear_done_o(raw_clear_done),
        .raw_capture_ready_o(raw_capture_ready),
        .raw_close_ready_o(raw_close_ready),
        .raw_drained_o(raw_drained),
        .raw_fault_o(raw_fault),
        .raw_object_fault_o(raw_object_fault),
        .raw_channel_fault_o(raw_channel_fault),
        .raw_fetch_ready_o(raw_fetch_ready),
        .raw_fetch_done_o(raw_fetch_done),
        .raw_fetch_fault_o(raw_fetch_fault),
        .raw_cache_valid_o(raw_cache_valid),
        .raw_sample_word_o(raw_sample_word),
        .raw_failure_code_o(raw_failure),
        .raw_accepted_frames_o(raw_accepted),
        .raw_committed_frames_o(raw_committed),
        .raw_native_protocol_fault_o(),
        .link_ready_i(task3_pair_link_ready),.panic_i(task3_pair_panic),.peer_boot_i(task3_pair_peer_boot),.session_i(task3_pair_session),
        .cnn_desc_valid_i(task3_desc_valid),.cnn_desc_ready_o(task3_desc_ready),.cnn_desc_i(task3_desc),
        .cnn_frame_valid_i(task3_frame_valid),.cnn_frame_ready_o(task3_frame_ready),.cnn_frame_i(task3_frame),
        .cnn_seal_valid_i(task3_seal_valid),.cnn_seal_ready_o(task3_seal_ready),.cnn_seal_i(task3_seal),
        .cnn_cancel_valid_i(task3_cancel_valid),.cnn_cancel_ready_o(task3_cancel_ready),.cnn_cancel_i(task3_cancel),
        .cnn_score_valid_o(task3_score_valid),.cnn_score_ready_i(task3_score_ready),.cnn_score_o(task3_score),
        .cnn_terminal_valid_o(task3_terminal_valid),.cnn_terminal_ready_i(task3_terminal_ready),.cnn_terminal_o(task3_terminal),
        .cnn_fatal_o(),.cnn_model_status_o(task3_actual_model_status),.cnn_accepted_frames_o(),.cnn_committed_frames_o(),.cnn_replayed_frames_o(),
        .model_serial_i(pc_uart_rx_i),
        .model_flash_miso_i(flash_miso),
        .model_flash_cs_no(model_flash_cs_n),
        .model_flash_clk_o(model_flash_clk),
        .model_flash_mosi_o(model_flash_mosi),
        .app_cmd_o(app_cmd),
        .app_en_o(app_en),
        .app_wren_o(app_wren),
        .app_wend_o(app_wend),
        .app_address_o(app_addr),
        .app_data_o(app_wdata),
        .app_mask_o(app_wmask),
        .app_ready_i(app_rdy),
        .app_write_ready_i(app_wrdy),
        .app_response_i(app_rvalid),
        .app_response_data_i(app_rdata));
    assign video_diagnostics=0,display_observation_drop=0;
    assign display_summary=0,display_summary_valid=0,ui_frame_commit=0;
    assign audio_queued_ready=0,audio_ddr_response=0,music_ddr_ready=0,music_ddr_response=0;
    assign cpu_mem_ready=0,cpu_mem_response=0;
    assign tmds_clk_p=0,tmds_clk_n=0,tmds_data_p=0,tmds_data_n=0;
