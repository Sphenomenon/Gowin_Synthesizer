// M native board binding. Shared pair config + physical LCD adapter are owned
// by the paired common include. No block here grants or guesses link readiness.
    wire task3_m_analysis_start,task3_m_analysis_ready,task3_m_analysis_cancel;
    wire task3_m_analysis_pcm_valid,task3_m_analysis_pcm_ready,task3_m_analysis_pcm_last;
    wire [31:0] task3_m_analysis_pcm;
    wire task3_m_analysis_failed,task3_m_analysis_busy,task3_m_analysis_done;
    wire task3_m_score_valid,task3_m_score_ready;
    wire [6:0] task3_m_score_note;
    wire [3:0] task3_m_model_status;
    wire task3_m_phone_live,task3_m_phone_valid,task3_m_phone_ready,task3_m_phone_target,task3_m_phone_write;
    wire [11:0] task3_m_phone_address;
    wire [31:0] task3_m_phone_data,task3_m_phone_response;
    wire [3:0] task3_m_phone_strobes;
    wire task3_m_phone_error,task3_m_hci_ready;
    wire [31:0] task3_m_hci_epoch,task3_m_hci_generation;
    wire task3_m_pcm_valid,task3_m_pcm_ready,task3_m_pcm_write,task3_m_pcm_error,task3_m_pcm_reset;
    wire [11:0] task3_m_pcm_address;
    wire [31:0] task3_m_pcm_data,task3_m_pcm_response;
    wire [3:0] task3_m_pcm_strobes;
    wire task3_m_pcm_bus_ready,task3_m_pcm_bus_error;
    wire [31:0] task3_m_pcm_bus_data;
    wire task3_m_pcm_idle_compute;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] task3_m_idle_sync;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] task3_m_owner_live_sync;
    always @(posedge clk_50m or negedge runtime_common_reset_n)
        if(!runtime_common_reset_n)task3_m_idle_sync<=0;
        else task3_m_idle_sync<={task3_m_idle_sync[0],task3_m_pcm_idle_compute};
    always @(posedge audio_clk or negedge runtime_common_reset_n)
        if(!runtime_common_reset_n)task3_m_owner_live_sync<=0;
        else task3_m_owner_live_sync<={task3_m_owner_live_sync[1:0],task3_m_phone_live};
    // One held transaction crosses into the existing compute-domain PCM1 owner.
    // Even a link-fenced transaction receives an explicit error to drain CDC.
    gw138k_apb_cdc u_task3_m_pcm_commands(
        .reset_n(runtime_common_reset_n),.pclk(clk_50m),.audio_clk(audio_clk),
        .psel(task3_m_phone_valid && !task3_m_phone_target),.penable(task3_m_phone_valid && !task3_m_phone_target),
        .pwrite(task3_m_phone_write),.paddr(task3_m_phone_address),.pwdata(task3_m_phone_data),.pstrb(task3_m_phone_strobes),
        .pready(task3_m_pcm_bus_ready),.pslverr(task3_m_pcm_bus_error),.prdata(task3_m_pcm_bus_data),
        .command_reset_n(task3_m_pcm_reset),.command_valid(task3_m_pcm_valid),.command_ready(task3_m_pcm_ready),
        .command_write(task3_m_pcm_write),.command_address(task3_m_pcm_address),.command_data(task3_m_pcm_data),.command_strobes(task3_m_pcm_strobes),
        .response_data(task3_m_pcm_response),.response_error(task3_m_pcm_error));
    wire task3_m_clock_valid,task3_m_clock_ready,task3_m_clock_write,task3_m_clock_error;
    wire [11:0] task3_m_clock_address;
    wire [31:0] task3_m_clock_data,task3_m_clock_response;
    wire [3:0] task3_m_clock_strobes;
    wire [1:0] task3_m_clock_caller_ready,task3_m_clock_caller_error;
    wire [63:0] task3_m_clock_caller_data;
    workstation_task3_phone_command_mux u_task3_m_clock_mux(
        .clk_i(clk_50m),.reset_ni(clock_command_reset_n),
        .valid_i({task3_m_phone_valid && task3_m_phone_target,clock_command_valid}),
        .write_i({task3_m_phone_write,clock_command_write}),.address_i({task3_m_phone_address,clock_command_address}),
        .data_i({task3_m_phone_data,clock_command_data}),.strobes_i({task3_m_phone_strobes,clock_command_strobes}),
        .ready_o(task3_m_clock_caller_ready),.response_error_o(task3_m_clock_caller_error),.response_data_o(task3_m_clock_caller_data),
        .valid_o(task3_m_clock_valid),.target_o(),.write_o(task3_m_clock_write),.address_o(task3_m_clock_address),.data_o(task3_m_clock_data),.strobes_o(task3_m_clock_strobes),
        .ready_i(task3_m_clock_ready),.response_error_i(task3_m_clock_error),.response_data_i(task3_m_clock_response));
    assign clock_command_ready=task3_m_clock_caller_ready[0];
    assign clock_response_error=task3_m_clock_caller_error[0],clock_response_data=task3_m_clock_caller_data[31:0];
    assign task3_m_phone_ready=task3_m_phone_target?task3_m_clock_caller_ready[1]:task3_m_pcm_bus_ready;
    assign task3_m_phone_error=task3_m_phone_target?task3_m_clock_caller_error[1]:task3_m_pcm_bus_error;
    assign task3_m_phone_response=task3_m_phone_target?task3_m_clock_caller_data[63:32]:task3_m_pcm_bus_data;
    wire task3_m_frame_valid;wire [97:0] task3_m_frame;
    wire [31:0] task3_m_frame_drops;
    gw138k_stream_cdc #(.WIDTH(98)) u_task3_m_final_tap(
        .reset_n(runtime_common_reset_n),.source_clk(dac_mclk),.destination_clk(clk_50m),
        .source_valid(physical_frame_valid),.source_data({physical_frame44,physical_frame_error,physical_frame_epoch,physical_frame_sequence,physical_frame_pcm}),
        .drop_count(task3_m_frame_drops),.destination_valid(task3_m_frame_valid),.destination_data(task3_m_frame));
    wire [31:0] task3_m_control_pitch;
    wire task3_m_panic_valid;wire [9:0] task3_m_panic_epoch;
    reg [9:0] task3_m_previous_panic;
    reg task3_m_panic;
    gw138k_stream_cdc #(.WIDTH(10)) u_task3_m_panic_epoch(
        .reset_n(runtime_common_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(audio_sample_valid),.source_data(task3_m_control_pitch[31:22]),
        .drop_count(),.destination_valid(task3_m_panic_valid),.destination_data(task3_m_panic_epoch));
    always @(posedge clk_50m or negedge runtime_common_reset_n)
        if(!runtime_common_reset_n)begin task3_m_previous_panic<=0;task3_m_panic<=0;end
        else begin
            task3_m_panic<=task3_m_panic_valid && task3_m_panic_epoch!=task3_m_previous_panic;
            if(task3_m_panic_valid)task3_m_previous_panic<=task3_m_panic_epoch;
        end
    // A changed CDC drop count revokes just the recording branch. The next
    // physical sequence gap is independently checked by the export queue.
    reg [31:0] task3_m_previous_drop;
    always @(posedge clk_50m or negedge runtime_common_reset_n)
        if(!runtime_common_reset_n)task3_m_previous_drop<=0;else task3_m_previous_drop<=task3_m_frame_drops;
    wire task3_m_record_fault,task3_m_record_armed;
`ifdef WORKSTATION_TASK3_PHONE_WINDOW_BLOCK
    localparam bit TASK3_PHONE_WINDOW_BLOCK=1'b1;
`else
    localparam bit TASK3_PHONE_WINDOW_BLOCK=1'b0;
`endif
    workstation_task3_m_bus_endpoint #(.BLOCK_PCM(1'b1),.PHONE_WINDOW_BLOCK(TASK3_PHONE_WINDOW_BLOCK)) u_task3_m_endpoint(
        .clk_i(clk_50m),.reset_ni(runtime_common_reset_n),.link_ready_i(task3_pair_link_ready),
        .panic_i(task3_pair_panic || task3_m_panic),.local_boot_i(task3_pair_local_boot),.peer_boot_i(task3_pair_peer_boot),
        .session_i(task3_pair_session),.generation_i(task3_pair_generation),
        .rx_valid_i(task3_pair_rx_valid),.rx_ready_o(task3_pair_rx_ready),.rx_channel_i(task3_pair_rx_channel),.rx_payload_i(task3_pair_rx_payload),.rx_length_i(task3_pair_rx_length),
        .tx_valid_o(task3_pair_tx_valid),.tx_ready_i(task3_pair_tx_ready),.tx_channel_o(task3_pair_tx_channel),.tx_payload_o(task3_pair_tx_payload),.tx_length_o(task3_pair_tx_length),
        .analysis_start_i(task3_m_analysis_start),.analysis_ready_o(task3_m_analysis_ready),.analysis_cancel_i(task3_m_analysis_cancel),
        .analysis_pcm_valid_i(task3_m_analysis_pcm_valid),.analysis_pcm_ready_o(task3_m_analysis_pcm_ready),.analysis_pcm_last_i(task3_m_analysis_pcm_last),.analysis_pcm_i(task3_m_analysis_pcm),
        .analysis_failed_o(task3_m_analysis_failed),.analysis_busy_o(task3_m_analysis_busy),.analysis_done_o(task3_m_analysis_done),
        .push_score_valid_o(task3_m_score_valid),.push_score_ready_i(task3_m_score_ready),.push_score_note_o(task3_m_score_note),
        .record_arm_i(task3_pair_record_arm),.record_cancel_i(task3_pair_record_cancel || task3_m_frame_drops!=task3_m_previous_drop),
        .frame_valid_i(task3_m_frame_valid),.frame_44k1_i(task3_m_frame[97]),.frame_error_i(task3_m_frame[96]),
        .frame_epoch_i(task3_m_frame[95:64]),.frame_sequence_i(task3_m_frame[63:32]),.frame_pcm_i(task3_m_frame[31:0]),
        .record_armed_o(task3_m_record_armed),.record_fault_o(task3_m_record_fault),
        .phone_owner_idle_i(task3_m_idle_sync[1]),.phone_owner_live_o(task3_m_phone_live),.phone_command_valid_o(task3_m_phone_valid),.phone_command_ready_i(task3_m_phone_ready),
        .phone_command_target_o(task3_m_phone_target),.phone_command_write_o(task3_m_phone_write),.phone_command_address_o(task3_m_phone_address),
        .phone_command_data_o(task3_m_phone_data),.phone_command_strobes_o(task3_m_phone_strobes),.phone_response_data_i(task3_m_phone_response),.phone_response_error_i(task3_m_phone_error),
        .hci_ready_o(task3_m_hci_ready),.hci_epoch_o(task3_m_hci_epoch),.hci_generation_o(task3_m_hci_generation),.model_status_o(task3_m_model_status),
        .malformed_packets_o(),.stale_packets_o());
