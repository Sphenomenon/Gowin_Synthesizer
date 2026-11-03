// Independent C-revision migration candidate. Original Prj1 top is retained.
// G1 MIDI is on a separate expansion pin; BL616 V14 is not reused.
`ifdef WORKSTATION_BLE_RAW_DDR
`include "rtl/ddr_address_map.vh"
`endif
`ifdef WORKSTATION_CUSTOM_138K
module workstation_custom_138k_top #(
`ifdef WORKSTATION_CNN_DEMO
    parameter integer TF_AUDIO_KIND=1,
`else
    parameter integer TF_AUDIO_KIND=2,
`endif
    parameter integer USB2_DIAGNOSTIC_UART=0,
    parameter integer BLUETOOTH_DIAGNOSTIC_UART=0
) (
    input wire clk_50m,clk_12m288,pc_uart_rx_i,
`ifdef WORKSTATION_RUNTIME_NATIVE
    input wire clk_16m9344,
`endif
    input wire flash_miso,
    output wire flash_clk,flash_cs_n,flash_mosi,flash_wp_n,flash_hold_n,
    input wire usb2_ulpi_clk,usb2_ulpi_dir,usb2_ulpi_nxt,
    inout wire [7:0] usb2_ulpi_data,
    output wire usb2_ulpi_stp,
    input wire sd_miso,
    output wire sd_mosi,sd_sck,sd_cs_n,
    output wire hp_bck,hp_ws,hp_din,dac_mclk,dac_pdn_n,
    output wire dac_sslow,dac_smute,dac_sd,dac_slow,
    input wire amp_fpga_det,
    output wire [4:0] lcd_r,
    output wire [5:0] lcd_g,
    output wire [4:0] lcd_b,
    output wire lcd_pclk,lcd_hsync,lcd_vsync,lcd_de,lcd_bl,
    output wire debug_uart_tx,
    input wire hdmi_hpd,
    inout wire hdmi_cec,
    input wire ble_uart_rx_i,
    inout wire ble_uart_tx_o,ble_bt_dis_n,ble_wl_dis_n,
    output wire tmds_clk_p,tmds_clk_n,
    output wire [2:0] tmds_data_p,tmds_data_n,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs,ddr_ras,ddr_cas,ddr_we,ddr_ck,ddr_ck_n,ddr_cke,ddr_odt,ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs,ddr_dqs_n
);
    wire button1_n=1'b1;
    wire midi_rx_i=1'b1;
    wire pa_en,hdmi_tx_en;
    wire reference_bck,reference_ws,reference_din;
    assign hdmi_cec=1'bz;
`else
module gw138k_push_workstation_top #(
    parameter integer TF_AUDIO_KIND=2
) (
    inout wire usb1_dp,usb1_dn,
    input wire clk_50m,
    input wire button1_n,
    input wire midi_rx_i,
    input wire pc_uart_rx_i,
    input wire sd_miso,
    output wire sd_mosi,sd_sck,sd_cs_n,
    output wire hp_bck,
    output wire hp_ws,
    output wire hp_din,
    output wire pa_en,
    output wire debug_uart_tx,
    output wire hdmi_tx_en,
    input wire hdmi_hpd,
    output wire tmds_clk_p,
    output wire tmds_clk_n,
    output wire [2:0] tmds_data_p,
    output wire [2:0] tmds_data_n,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs,ddr_ras,ddr_cas,ddr_we,ddr_ck,ddr_ck_n,ddr_cke,ddr_odt,ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs,ddr_dqs_n
);
`endif
`ifdef WORKSTATION_RUNTIME_NATIVE
`ifdef WORKSTATION_NO_CNN
    localparam bit RECOGNITION_ENABLED=1'b0;
`else
    localparam bit RECOGNITION_ENABLED=1'b1;
`endif
`endif
`ifdef WORKSTATION_CNN_DEMO
    wire [31:0] fetch_count,last_fetch,signature,ram_result,heartbeat,trap_cause,trap_pc,ui_report;
`endif
`ifdef WORKSTATION_RUNTIME_NATIVE
    wire ble_debug_uart,song_cmd_valid,playlist_scan_done,tf_card_lost;
    wire [3:0] song_cmd_index;
    wire [4:0] tf_track_count;
    wire [31:0] fetch_count,last_fetch;
    reg [31:0] signature,ram_result,heartbeat,trap_cause,trap_pc,ui_report;
`ifdef WORKSTATION_CPU_BLE_DIAGNOSTICS
    reg [31:0] business_diagnostic_stage,business_diagnostic_meta,business_diagnostic_data;
`endif
`endif
    wire reset_n;
    reset_release u_reset(.clk(clk_50m),.ext_reset_n(button1_n),.reset_n(reset_n));
    wire audio_clk,audio_reset_n,audio_locked;
    gw138k_audio_clock u_audio_clock(.clk_50m(clk_50m),.reset_n(reset_n),
        .audio_clk(audio_clk),.audio_reset_n(audio_reset_n),.pll_locked(audio_locked));
    wire usb_clk,usb_locked;
    gw138k_cpu_pll_cell #(.OUTPUT_DIV0(25),.OUTPUT1_ENABLE("FALSE")) u_usb_pll(
        .clkin(clk_50m),.init_clk(clk_50m),.reset(!reset_n),.enable0(1'b1),
        .lock(usb_locked),.clkout0(usb_clk),.clkout1());
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [3:0] usb_release=0;
    wire usb_qualified=reset_n && usb_locked;
    always @(posedge usb_clk or negedge usb_qualified)
        if(!usb_qualified)usb_release<=0;else usb_release<={usb_release[2:0],1'b1};
    wire usb_reset_n=usb_release[3];
`ifndef WORKSTATION_CUSTOM_138K
    wire mmio_select,mmio_write,mmio_ready;
    wire [7:0] mmio_address;wire [31:0] mmio_wdata,mmio_rdata;
    wire host_mmio_select,host_mmio_write,host_mmio_ready;
    wire [7:0] host_mmio_address;
    wire [31:0] host_mmio_wdata,host_mmio_rdata;
    gw138k_mmio_pipeline u_usb_mmio_pipeline(
        .clk(usb_clk),.reset_n(usb_reset_n),
        .select_i(host_mmio_select),.write_i(host_mmio_write),.address_i(host_mmio_address),.wdata_i(host_mmio_wdata),
        .ready_o(host_mmio_ready),.rdata_o(host_mmio_rdata),
        .select_o(mmio_select),.write_o(mmio_write),.address_o(mmio_address),.wdata_o(mmio_wdata),
        .ready_i(mmio_ready),.rdata_i(mmio_rdata));
    wire [223:0] usb_words;
    iosys2 u_usb_host(.clk(usb_clk),.resetn(usb_reset_n),.uart_rx(1'b1),.uart_tx(),
        .usb_dp(usb1_dp),.usb_dm(usb1_dn),.mmio_select(host_mmio_select),.mmio_write(host_mmio_write),
        .mmio_address(host_mmio_address),.mmio_wdata(host_mmio_wdata),.mmio_ready(host_mmio_ready),.mmio_rdata(host_mmio_rdata));
`else
    wire [223:0] usb_words;
`endif
    wire [31:0] output_pcm,output_reference,active_voices,display_status;
    wire [127:0] display_parameters;
`ifndef WORKSTATION_RUNTIME_NATIVE
    assign display_parameters=128'd0;
`endif
    wire synth_hp_bck,synth_hp_ws,synth_hp_din,synth_pa_en,synth_sample_ce;
    wire [31:0] scope_status_audio,tf_scope_control_audio,tf_scope_control_50;
    wire tf_control_valid,tf_mode_50,tf_run_50,tf_scope_restart,tf_scope_cancel,tf_scope_error;
`ifdef WORKSTATION_RUNTIME_NATIVE
    wire tf_explicit_restart,tf_file_cancel;
`endif
    wire [3:0] tf_scope_track;
`ifdef WORKSTATION_DEMO_NO_TF
    assign tf_control_valid=0,tf_scope_control_50=0,tf_mode_50=0,tf_run_50=0;
    assign tf_scope_track=0,tf_scope_restart=0,tf_scope_cancel=0,tf_scope_error=0;
    assign tf_explicit_restart=0,tf_file_cancel=0;
    wire tf_run_audio=1'b0;
`else
    reg [4:0] tf_control_divider;
    always @(posedge audio_clk or negedge audio_reset_n)
        if(!audio_reset_n) tf_control_divider<=0;else tf_control_divider<=tf_control_divider+1'b1;
    gw138k_stream_cdc #(.WIDTH(32)) u_tf_control_cdc(
        .reset_n(reset_n && audio_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(&tf_control_divider),.source_data(tf_scope_control_audio),.drop_count(),
        .destination_valid(tf_control_valid),.destination_data(tf_scope_control_50));
    scope_tf_transport u_tf_scope_transport(
        .clk_i(clk_50m),.rst_ni(reset_n),.control_valid_i(tf_control_valid),.control_i(tf_scope_control_50),
        .song_valid_i(song_cmd_valid),.song_track_i(song_cmd_index),
        .playlist_ready_i(playlist_scan_done),.track_count_i(tf_track_count),.card_lost_i(tf_card_lost),
        .mode_o(tf_mode_50),.run_o(tf_run_50),.track_o(tf_scope_track),
`ifdef WORKSTATION_RUNTIME_NATIVE
        .explicit_restart_o(tf_explicit_restart),.file_cancel_o(tf_file_cancel),
`endif
        .restart_o(tf_scope_restart),.cancel_analysis_o(tf_scope_cancel),.error_o(tf_scope_error));
    reg tf_run_meta,tf_run_audio;
    always @(posedge audio_clk or negedge audio_reset_n)
        if(!audio_reset_n) begin tf_run_meta<=0;tf_run_audio<=0;end
        else begin tf_run_meta<=tf_run_50;tf_run_audio<=tf_run_meta;end
`endif
    wire final_sample_valid;
    wire [127:0] final_snapshot;
    wire [31:0] synth_dac_reference,synth_dac_voices,synth_dac_health;
    wire synth_display_valid;
    wire [31:0] synth_display_pcm,synth_display_reference,synth_display_voices,synth_display_status;
`ifndef WORKSTATION_RUNTIME_NATIVE
    gw138k_stream_cdc #(.WIDTH(128)) u_final_output_cdc(
        .reset_n(reset_n && audio_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(final_sample_valid),
        .source_data(final_snapshot),
        .drop_count(),.destination_valid(output_sample_valid),
        .destination_data({output_pcm,output_reference,active_voices,display_status}));
`endif
    wire [3:0] music_model_status;
    wire music_report_sending,music_report_serial,runtime_serial;
    wire music_pcm_ready;
    wire music_analysis_done;
    wire music_analysis_restart,music_analysis_enable,music_analysis_hold;
    wire playback_restart,score_accept;
    wire [3:0] playback_track;
`ifdef WORKSTATION_DEMO_NO_TF
    assign music_analysis_enable=0,music_analysis_restart=0,music_analysis_hold=0;
    assign playback_restart=0,playback_track=0,score_accept=0;
`else
    workstation_playback_service
`ifdef WORKSTATION_RUNTIME_NATIVE
        #(.RECOGNITION_ENABLE(RECOGNITION_ENABLED))
`endif
    u_playback_service (
        .clk_i(clk_50m),.rst_ni(reset_n),.model_status_i(music_model_status),
        .tf_mode_i(tf_mode_50),.tf_restart_i(tf_scope_restart),.tf_track_i(tf_scope_track),
        .cancel_i(tf_scope_cancel),.song_valid_i(song_cmd_valid),.song_track_i(song_cmd_index),
        .playlist_ready_i(playlist_scan_done),.track_count_i(tf_track_count),
        .card_lost_i(tf_card_lost),.analysis_done_i(music_analysis_done),
        .analysis_enable_o(music_analysis_enable),.analysis_restart_o(music_analysis_restart),
        .analysis_hold_o(music_analysis_hold),.reader_restart_o(playback_restart),
        .reader_track_o(playback_track),.score_accept_o(score_accept)
    );
`endif
`ifdef WORKSTATION_CUSTOM_138K
    wire native_usb_uart;
    assign debug_uart_tx=BLUETOOTH_DIAGNOSTIC_UART ? ble_debug_uart : USB2_DIAGNOSTIC_UART ? native_usb_uart :
        (music_report_sending ? music_report_serial : runtime_serial);
`else
    assign debug_uart_tx=music_report_sending ? music_report_serial : runtime_serial;
`endif
    wire [2:0] effect_mask;
    wire [5:0] effect_order;
    wire output_sample_valid;
    wire audio_sample_valid;
    wire memory_clk,memory_reset_n,memory_calibrated,memory_pll_locked;
    wire pclk,preset_n,psel,penable,pwrite;
    wire [31:0] paddr,pwdata,service_data;
    wire [3:0] pstrb;
    wire service_ready,service_error;
    wire ui_select=psel && paddr[31:12]==20'hf8020;
    wire ui_ready,ui_error;
    wire [31:0] ui_read_data;
    wire ui_command_reset_n,ui_command_valid,ui_command_ready,ui_command_write,ui_response_error;
    wire [11:0] ui_command_address;
    wire [31:0] ui_command_data,ui_response_data;
    wire [3:0] ui_command_strobes;
    wire ui_pending,ui_visible,ui_next_visible,ui_frame_commit;
    wire [28:0] ui_front_base,ui_next_base;
`ifdef WORKSTATION_CNN_DEMO
    assign ui_ready=1,ui_error=0,ui_read_data=0;
    assign ui_pending=0,ui_visible=0,ui_next_visible=0,ui_front_base=0,ui_next_base=0;
    assign ui_frame_commit=0;
`elsif WORKSTATION_WORKER_AUDIO_ONLY
    // Retired graphics APB page fails explicitly; no UI CDC or framebuffer owner.
    assign ui_ready=1'b1,ui_error=ui_select,ui_read_data=32'd0;
    assign ui_pending=0,ui_visible=0,ui_next_visible=0,ui_front_base=0,ui_next_base=0;
`else
    gw138k_apb_cdc u_ui_control(.reset_n(preset_n && memory_reset_n),.pclk(pclk),.audio_clk(memory_clk),
        .psel(ui_select),.penable(penable),.pwrite(pwrite),.paddr(paddr[11:0]),.pwdata(pwdata),.pstrb(pstrb),
        .pready(ui_ready),.pslverr(ui_error),.prdata(ui_read_data),.command_reset_n(ui_command_reset_n),
        .command_valid(ui_command_valid),.command_ready(ui_command_ready),.command_write(ui_command_write),
        .command_address(ui_command_address),.command_data(ui_command_data),.command_strobes(ui_command_strobes),
        .response_data(ui_response_data),.response_error(ui_response_error));
    gw138k_ui_services u_ui_services(.clk(memory_clk),.reset_n(ui_command_reset_n),
        // No touchscreen is attached. A future verified board input adapter
        // supplies logical 800x480 events in memory_clk, independently of audio.
        .input_attached(1'b0),.input_valid(1'b0),.input_down(1'b0),.input_x(16'd0),.input_y(16'd0),
        .command_valid(ui_command_valid),.command_ready(ui_command_ready),.command_write(ui_command_write),
        .command_address(ui_command_address),.command_data(ui_command_data),.command_strobes(ui_command_strobes),
        .response_data(ui_response_data),.response_error(ui_response_error),.frame_commit(ui_frame_commit),
        .pending(ui_pending),.visible(ui_visible),.next_visible(ui_next_visible),.front_base(ui_front_base),.next_base(ui_next_base));
`endif
    wire service_select=psel && paddr[31:12]==20'hf8010;
`ifdef WORKSTATION_RUNTIME_NATIVE
`ifdef WORKSTATION_AE350_PCM
    // New source requires a separately locked explicit candidate/profile.
    localparam AE350_PCM_ENABLED=1;
    wire pcm_select=psel && paddr[31:12]==20'hf8060;
    wire pcm_bus_ready,pcm_bus_error,hci_pcm_session_ready;
    wire [31:0] pcm_bus_data,hci_pcm_controller_epoch,hci_pcm_transport_generation;
`else
    localparam AE350_PCM_ENABLED=0;
    wire pcm_select=1'b0,pcm_bus_ready=1'b1,pcm_bus_error=1'b1,hci_pcm_session_ready=1'b0;
    wire [31:0] pcm_bus_data=0,hci_pcm_controller_epoch=0,hci_pcm_transport_generation=0;
`endif
    // This page is distinct from legacy audio F8010, UI F8020 and boot F8000.
    wire clock_service_select=psel && paddr[31:12]==20'hf8030;
    wire clock_service_ready,clock_service_error;
    wire [31:0] clock_service_data;
    wire clock_command_reset_n,clock_command_valid,clock_command_ready,clock_command_write;
    wire [11:0] clock_command_address;
    wire [31:0] clock_command_data,clock_response_data;
    wire [3:0] clock_command_strobes;
    wire clock_response_error;
    wire rate_request,rate_target44,rate_recover,rate_request_ready;
    wire rate_busy,rate_fault,rate_accepted,rate_applied,rate_rejected,rate_failed,rate_policy_rejected;
    wire rate44,rate_valid,rate_dsp_fault,rate_quiesce,rate_flush,rate_context_ready;
    wire [31:0] rate_epoch;
    wire [1:0] rate_qualified;
    wire [2:0] rate_reject_code;
    wire [3:0] rate_fault_code,rate_select,rate_block_reason;
    wire ddr_client_reset_n,ddr_client_ready;
    wire memory_guard_started,memory_guard_fault,memory_guard_ready,memory_guard_mute,runtime_channel_open;
    wire [1:0] memory_guard_code;
    wire runtime_reset_n=reset_n && memory_guard_started;
    wire runtime_delay_req;
    wire runtime_smute;
    wire [31:0] display_observation_drop;
    // Backend loss quarantines both directions until common reset. It never
    // clears held notes, committed parameters or the stream epoch in place.
    workstation_runtime_memory_guard u_runtime_memory_guard(
        .reset_ni(button1_n),.clk_50m_i(clk_50m),.memory_clk_i(memory_clk),
        .backend_reset_ni(ddr_client_reset_n),.backend_ready_i(ddr_client_ready && audio_reset_n),
        .started_o(memory_guard_started),.fault_o(memory_guard_fault),.start_ready_o(memory_guard_ready),
        .mute_o(memory_guard_mute),.channel_open_o(runtime_channel_open),.clock_alive_o(),.fault_code_o(memory_guard_code));
    wire compute_output_safe_n=reset_n && audio_reset_n && !memory_guard_mute;
    // Raw safety still asserts DAC SMUTE immediately. Compute-domain gain
    // policy consumes only the synchronized local permission, in both directions.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] output_safe_sync;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] output_safe_compute;
    always @(posedge audio_clk or negedge button1_n)
        if(!button1_n)output_safe_sync<=0;else output_safe_sync<={output_safe_sync[0],compute_output_safe_n};
    always @(posedge audio_clk or negedge button1_n)
        if(!button1_n)output_safe_compute<=0;
        else if(!output_safe_sync[1])output_safe_compute<=0;
        else output_safe_compute<={output_safe_compute[1:0],1'b1};
    wire tf_packet_active,tf_packet_busy,tf_packet_valid,tf_packet_error,tf_packet_ready;
    wire signed [15:0] tf_packet_left,tf_packet_right;
    wire [19:0] tf_packet_rate;
    wire [31:0] tf_packet_generation,tf_expected_generation;
    wire tf_media_quiet,tf_media_quiet50,tf_busy50,tf_runtime_failed;
    wire [3:0] tf_runtime_failure;
    wire runtime_media_request,runtime_media_hold,runtime_media_ready;
    wire runtime_media_done,runtime_media_failed,tf_stop_request,tf_stop_done,tf_stop_failed;
    wire [3:0] runtime_media_failure,tf_stop_failure;
    wire clock_media_request,clock_media_hold,clock_media_ready,clock_media_done,clock_media_failed;
    wire [3:0] clock_media_failure;
    wire ble_seal_request,ble_seal_hold,ble_seal_ready,ble_seal_done,ble_seal_failed,tf_stop_pending;
    wire [3:0] ble_seal_failure;
    wire delay_ddr_req,delay_ddr_write,delay_ddr_ready,delay_ddr_response;
    wire [28:0] delay_ddr_address;
    wire [255:0] delay_ddr_data,client_rdata;
    wire physical_frame_valid,physical_frame_error,physical_frame44;
    wire [31:0] physical_frame_epoch,physical_frame_sequence,physical_frame_pcm;
    wire display_frame44,display_frame_error;
    wire [31:0] display_frame_epoch,display_frame_sequence;
    wire [31:0] runtime_observation_drop;
    wire runtime_display_observation_fault;
`ifdef WORKSTATION_CPU_BLE_BUSINESS
    wire business_select=psel && paddr[31:12]==20'hf8050;
    wire business_bus_ready,business_bus_error,business_owner_reset;
    wire [31:0] business_bus_data;
    wire business_command_valid,business_command_ready,business_command_write,business_response_error;
    wire [11:0] business_command_address;
    wire [31:0] business_command_data,business_response_data;
    wire [3:0] business_command_strobes;
    gw138k_apb_cdc business_commands(
        .reset_n(preset_n && reset_n),.pclk(pclk),.audio_clk(clk_50m),
        .psel(business_select),.penable(penable),.pwrite(pwrite),.paddr(paddr[11:0]),
        .pwdata(pwdata),.pstrb(pstrb),.pready(business_bus_ready),.pslverr(business_bus_error),.prdata(business_bus_data),
        .command_reset_n(business_owner_reset),.command_valid(business_command_valid),.command_ready(business_command_ready),
        .command_write(business_command_write),.command_address(business_command_address),
        .command_data(business_command_data),.command_strobes(business_command_strobes),
        .response_data(business_response_data),.response_error(business_response_error));
`else
    wire business_select=1'b0,business_bus_ready=1'b1,business_bus_error=1'b0;
    wire [31:0] business_bus_data=0;
`endif

`ifdef WORKSTATION_RECORDING_DDR
    wire recording_select=psel && paddr[31:12]==20'hf8040;
    wire recording_bus_ready,recording_bus_error;
    wire [31:0] recording_bus_data;
    wire recording_req,recording_write,recording_ready,recording_response,recording_native_accept,recording_transport_fault;
    wire [28:0] recording_address;
    wire [255:0] recording_data;
    wire [31:0] recording_mask;
    wire recording_seal_request,recording_seal_hold,recording_seal_ready,recording_seal_done,recording_seal_failed;
    wire [3:0] recording_seal_failure;
`ifdef WORKSTATION_BLE_RAW_DDR
    wire recording_channel_ready,recording_authority_fault;
    wire [1:0] recording_subclient_valid,recording_subclient_write,recording_subclient_ready;
    wire [1:0] recording_subclient_native,recording_subclient_response,recording_bridge_protocol_fault;
    wire [28:0] recording_cpu_address,recording_ble_address;
    wire [255:0] recording_cpu_data,recording_ble_data;
    wire [31:0] recording_cpu_mask,recording_ble_mask;
    wire recording_mux_fault;
    wire raw_start_valid,raw_start_ready,raw_start_done,raw_clear_valid,raw_clear_ready,raw_clear_done;
    wire raw_capture_valid,raw_capture_ready,raw_close_valid,raw_close_ready,raw_drained;
    wire raw_fault,raw_object_fault,raw_channel_fault;
    wire [3:0] raw_failure;
    wire [31:0] raw_capture_index,raw_capture_pcm,raw_accepted,raw_committed;
    wire raw_fetch_valid,raw_fetch_ready,raw_fetch_done,raw_fetch_fault,raw_cache_valid;
    wire [31:0] raw_fetch_offset,raw_sample_addr,raw_sample_word;
    wire [13:0] raw_fetch_length;
    (* ASYNC_REG="TRUE" *) reg [1:0] recording_memory_release;
    always @(posedge memory_clk or negedge reset_n)
        if(!reset_n)recording_memory_release<=0;
        else recording_memory_release<={recording_memory_release[0],1'b1};
    wire recording_memory_reset_n=recording_memory_release[1];
    initial begin
        if(`PRJ1_DDR_RECORDING_BLE_BYTES!=65536 ||
           `PRJ1_DDR_RECORDING_BLE_BYTE_LAST-`PRJ1_DDR_RECORDING_BLE_BYTE_BASE+1!=65536 ||
           (32'(`PRJ1_DDR_RECORDING_BLE_APP_BASE)<<2)!=`PRJ1_DDR_RECORDING_BLE_BYTE_BASE ||
           (32'(`PRJ1_DDR_RECORDING_BLE_APP_LAST)<<2)+3!=`PRJ1_DDR_RECORDING_BLE_BYTE_LAST ||
           `PRJ1_DDR_RECORDING_BLE_APP_LAST-`PRJ1_DDR_RECORDING_BLE_APP_BASE+1!=16384 ||
           `PRJ1_DDR_RECORDING_BLE_APP_BASE%8!=0 || `PRJ1_DDR_RECORDING_BLE_APP_LAST%8!=7 ||
           `PRJ1_DDR_RECORDING_BLE_BYTE_BASE<`PRJ1_DDR_RECORDING_BYTE_BASE ||
           `PRJ1_DDR_RECORDING_BLE_BYTE_LAST>`PRJ1_DDR_RECORDING_BYTE_LAST ||
           !(`PRJ1_DDR_RECORDING_CPU_BYTE_LAST<`PRJ1_DDR_RECORDING_BLE_BYTE_BASE ||
             `PRJ1_DDR_RECORDING_BLE_BYTE_LAST<`PRJ1_DDR_RECORDING_CPU_BYTE_BASE) ||
           !(`PRJ1_DDR_RECORDING_CPU_APP_LAST<`PRJ1_DDR_RECORDING_BLE_APP_BASE ||
             `PRJ1_DDR_RECORDING_BLE_APP_LAST<`PRJ1_DDR_RECORDING_CPU_APP_BASE))
            $fatal(1,"invalid top BLE DDR byte/native allocation, capacity or complete BL8 window");
    end
    (* ASYNC_REG="TRUE" *) reg recording_channel_meta,recording_channel_ready50;
    always @(posedge clk_50m or negedge reset_n)
        if(!reset_n)begin recording_channel_meta<=0;recording_channel_ready50<=0;end
        else begin recording_channel_meta<=recording_channel_ready;recording_channel_ready50<=recording_channel_meta;end
    // Only a true root/controller reset can establish a fresh untagged epoch.
    // The real ledger reset is observed by authority; it never resets owners.
    workstation_recording_ddr_authority recording_authority(
        .root_reset_ni(reset_n),.control_clk_i(clk_50m),.memory_clk_i(memory_clk),
        .ledger_reset_ni(ddr_client_reset_n),.backend_ready_i(ddr_client_ready),
        .channel_ready_o(recording_channel_ready),.started_o(),.fault_o(recording_authority_fault),
        .epoch_lost_o(),.boot_seen_o(),.epoch_survived_o());
    workstation_recording_ddr_owner_mux #(
        .FIRST0(`PRJ1_DDR_RECORDING_CPU_APP_BASE),.LAST0(`PRJ1_DDR_RECORDING_CPU_APP_LAST),
        .FIRST1(`PRJ1_DDR_RECORDING_BLE_APP_BASE),.LAST1(`PRJ1_DDR_RECORDING_BLE_APP_LAST),
        .BUDGET_CYCLES(10000)) recording_owner8(
        .clk_i(memory_clk),.rst_ni(recording_memory_reset_n),.channel_ready_i(recording_channel_ready),
        .valid_i(recording_subclient_valid),.write_i(recording_subclient_write),
        .address0_i(recording_cpu_address),.address1_i(recording_ble_address),
        .data0_i(recording_cpu_data),.data1_i(recording_ble_data),
        .mask0_i(recording_cpu_mask),.mask1_i(recording_ble_mask),
        .ready_o(recording_subclient_ready),.native_accept_o(recording_subclient_native),.response_o(recording_subclient_response),
        .valid_o(recording_req),.write_o(recording_write),.address_o(recording_address),
        .data_o(recording_data),.mask_o(recording_mask),.ready_i(recording_ready),
        .native_accept_i(recording_native_accept),.response_i(recording_response),
        // The two bridge contributions are registered protocol faults. Feeding
        // their inclusive transport faults here would create a logic loop.
        .transport_fault_i(recording_transport_fault || recording_authority_fault || |recording_bridge_protocol_fault),
        .transport_fault_o(recording_mux_fault),.fault_o(),.busy_o());
    workstation_ble_raw_ddr_store #(.BASE_APP(`PRJ1_DDR_RECORDING_BLE_APP_BASE),.CAPACITY_FRAMES(16384),.FIFO_ADDRESS_BITS(8),
        .COMMAND_TIMEOUT_CYCLES(10000),.READ_TIMEOUT_CYCLES(10000)) recording_ble_store(
        .clk_i(clk_50m),.memory_clk_i(memory_clk),.rst_ni(reset_n),
        .start_valid_i(raw_start_valid && recording_channel_ready50),.start_ready_o(raw_start_ready),.start_done_o(raw_start_done),
        .clear_valid_i(raw_clear_valid),.clear_ready_o(raw_clear_ready),.clear_done_o(raw_clear_done),
        .capture_valid_i(raw_capture_valid),.capture_index_i(raw_capture_index),.capture_pcm_i(raw_capture_pcm),
        .capture_ready_o(raw_capture_ready),.close_valid_i(raw_close_valid),.close_ready_o(raw_close_ready),
        .drained_o(raw_drained),.fault_o(raw_fault),.object_fault_o(raw_object_fault),.channel_fault_o(raw_channel_fault),
        .failure_code_o(raw_failure),.accepted_frames_o(raw_accepted),.committed_frames_o(raw_committed),
        .fetch_valid_i(raw_fetch_valid),.fetch_ready_o(raw_fetch_ready),.fetch_offset_i(raw_fetch_offset),.fetch_length_i(raw_fetch_length),
        .fetch_done_o(raw_fetch_done),.fetch_fault_o(raw_fetch_fault),.cache_valid_o(raw_cache_valid),
        .sample_addr_i(raw_sample_addr),.sample_word_o(raw_sample_word),
        .slot_valid_o(recording_subclient_valid[1]),.slot_ready_i(recording_subclient_ready[1]),
        .native_accept_i(recording_subclient_native[1]),.ddr_write_o(recording_subclient_write[1]),
        .ddr_address_o(recording_ble_address),.ddr_data_o(recording_ble_data),.ddr_mask_o(recording_ble_mask),
        .read_response_i(recording_subclient_response[1]),.read_data_i(client_rdata),
        .transport_fault_i(recording_mux_fault),.native_protocol_fault_o(recording_bridge_protocol_fault[1]));
`endif
`ifdef WORKSTATION_SINGLE_BLE_RECORDING
    // The BLE business owner is the sole object owner. The retired R00 APB
    // window rejects access; CPU commands use its maintained C service.
    assign recording_bus_ready=1'b1,recording_bus_error=recording_select;
    assign recording_bus_data=32'h0;
    assign recording_seal_ready=1'b1,recording_seal_done=1'b0;
    assign recording_seal_failed=1'b0,recording_seal_failure=4'd0;
    assign recording_subclient_valid[0]=1'b0,recording_subclient_write[0]=1'b0;
    assign recording_cpu_address=29'd0,recording_cpu_data=256'd0,recording_cpu_mask=32'd0;
    assign recording_bridge_protocol_fault[0]=1'b0;
`else
    workstation_recording_runtime u_recording(
`ifdef WORKSTATION_BLE_RAW_DDR
        .reset_ni(recording_memory_reset_n),.source_clk_i(dac_mclk),.memory_clk_i(memory_clk),
        .control_clk_i(clk_50m),.backend_ready_i(recording_channel_ready),
`else
        .reset_ni(reset_n && ddr_client_reset_n),.source_clk_i(dac_mclk),.memory_clk_i(memory_clk),
        .control_clk_i(clk_50m),.backend_ready_i(ddr_client_ready),
`endif
        .frame_valid_i(physical_frame_valid),.frame_error_i(physical_frame_error),.frame_44k1_i(physical_frame44),
        .frame_epoch_i(physical_frame_epoch),.frame_sequence_i(physical_frame_sequence),.frame_pcm_i(physical_frame_pcm),
        .pclk(pclk),.preset_n(preset_n),.psel(recording_select),.penable(penable),.pwrite(pwrite),
        .paddr(paddr[11:0]),.pwdata(pwdata),.pstrb(pstrb),.pready(recording_bus_ready),
        .pslverr(recording_bus_error),.prdata(recording_bus_data),
        .seal_hold_i(recording_seal_hold),.seal_request_i(recording_seal_request),
        .seal_ready_o(recording_seal_ready),.seal_done_o(recording_seal_done),.seal_failed_o(recording_seal_failed),
        .seal_failure_code_o(recording_seal_failure),
`ifdef WORKSTATION_BLE_RAW_DDR
        .recording_valid_o(recording_subclient_valid[0]),.recording_write_o(recording_subclient_write[0]),
        .recording_address_o(recording_cpu_address),.recording_data_o(recording_cpu_data),.recording_mask_o(recording_cpu_mask),
        .recording_ready_i(recording_subclient_ready[0]),.recording_response_i(recording_subclient_response[0]),
        .recording_native_accept_i(recording_subclient_native[0]),.recording_read_data_i(client_rdata),
        .transport_fault_i(recording_mux_fault),.native_protocol_fault_o(recording_bridge_protocol_fault[0]),
`else
        .recording_valid_o(recording_req),.recording_write_o(recording_write),
        .recording_address_o(recording_address),.recording_data_o(recording_data),.recording_mask_o(recording_mask),
        .recording_ready_i(recording_ready),.recording_response_i(recording_response),
        .recording_native_accept_i(recording_native_accept),.recording_read_data_i(client_rdata),
        .transport_fault_i(recording_transport_fault),
`endif
        .object_state_o(),.object_failure_o(),
        .object_frames_o(),.committed_frames_o(),.capture_o());
`endif
`endif
    // CPU reset clears command bookkeeping. The independently latched backend
    // fault and runtime identity survive it and remain visible to the service.
    gw138k_apb_cdc u_clock_control(
        .reset_n(preset_n && runtime_reset_n),.pclk(pclk),.audio_clk(clk_50m),
        .psel(clock_service_select),.penable(penable),.pwrite(pwrite),.paddr(paddr[11:0]),
        .pwdata(pwdata),.pstrb(pstrb),.pready(clock_service_ready),.pslverr(clock_service_error),
        .prdata(clock_service_data),.command_reset_n(clock_command_reset_n),
        .command_valid(clock_command_valid),.command_ready(clock_command_ready),
        .command_write(clock_command_write),.command_address(clock_command_address),
        .command_data(clock_command_data),.command_strobes(clock_command_strobes),
        .response_data(clock_response_data),.response_error(clock_response_error));
`ifdef WORKSTATION_PUSH_RATE_CONTROL
    wire push_rate_usb_ready,push_rate_usb_toggle,push_rate_toggle,push_rate_ready;
    wire clock_service_busy,clock_service_fault;
    wire [31:0] push_rate_generation,push_rate_command_generation;
    workstation_push_rate_bridge u_push_rate_bridge(
        .reset_ni(clock_command_reset_n && usb_reset_n),.usb_clk_i(usb_clk),.control_clk_i(clk_50m),
        .service_ready_i(push_rate_ready),.service_generation_i(push_rate_generation),
        .usb_ready_o(push_rate_usb_ready),.usb_toggle_i(push_rate_usb_toggle),
        .service_toggle_o(push_rate_toggle),.service_generation_o(push_rate_command_generation));
`endif
    workstation_audio_clock_service #(.RESERVE_ZERO_EPOCH(1),.ENABLE_MEDIA_POLICY(1)
`ifdef WORKSTATION_PUSH_RATE_CONTROL
        ,.ENABLE_PUSH_RATE_CONTROL(1)
`endif
    ) u_clock_service(
`ifdef WORKSTATION_PUSH_RATE_CONTROL
        .push_toggle_i(push_rate_toggle),.push_generation_i(push_rate_command_generation),
        .push_ready_o(push_rate_ready),.push_generation_o(push_rate_generation),.push_rejected_o(),
        .service_busy_o(clock_service_busy),.service_fault_o(clock_service_fault),
`endif
        .clk_i(clk_50m),.reset_ni(clock_command_reset_n),
        .command_valid_i(clock_command_valid),.command_write_i(clock_command_write),
        .command_address_i(clock_command_address),.command_data_i(clock_command_data),
        .command_strobes_i(clock_command_strobes),.command_ready_o(clock_command_ready),
        .response_data_o(clock_response_data),.response_error_o(clock_response_error),
        .switch_permit_i(memory_guard_ready),.core_request_ready_i(rate_request_ready),
        .core_busy_i(rate_busy),.core_fault_i(rate_fault),.core_dsp_fault_i(rate_dsp_fault || memory_guard_fault),
        .core_accepted_i(rate_accepted),.core_applied_i(rate_applied),.core_rejected_i(rate_rejected),
        .core_policy_rejected_i(rate_policy_rejected),.core_failed_i(rate_failed),
        .core_reject_code_i(rate_reject_code),.core_fault_code_i(rate_fault_code),
        .core_active_44k1_i(rate44),.core_active_valid_i(rate_valid),.core_stream_epoch_i(rate_epoch),
        .core_source_qualified_i(rate_qualified),.request_o(rate_request),.request_44k1_o(rate_target44),
        .recover_o(rate_recover),.media_stop_request_o(clock_media_request),
        .media_stop_hold_o(clock_media_hold),.media_stop_ready_i(clock_media_ready),
        .media_stop_done_i(clock_media_done),.media_stop_failed_i(clock_media_failed),
        .media_stop_failure_code_i(clock_media_failure));
    workstation_media_preparation #(
`ifdef WORKSTATION_WORKER_AUDIO_ONLY
        .ENABLE_BLE(0)
`elsif WORKSTATION_NO_BLUETOOTH
        .ENABLE_BLE(0)
`else
        .ENABLE_BLE(1)
`endif
`ifdef WORKSTATION_RECORDING_DDR
`ifndef WORKSTATION_SINGLE_BLE_RECORDING
        ,.ENABLE_RECORDING(1)
`endif
`endif
    ) u_media_preparation(
        .clk_i(clk_50m),.reset_ni(runtime_reset_n),.request_i(clock_media_request),.hold_i(clock_media_hold),
        .ready_o(clock_media_ready),.done_o(clock_media_done),.failed_o(clock_media_failed),
        .failure_code_o(clock_media_failure),.runtime_request_o(runtime_media_request),.runtime_hold_o(runtime_media_hold),
        .runtime_ready_i(runtime_media_ready),.runtime_done_i(runtime_media_done),.runtime_failed_i(runtime_media_failed),
        .runtime_failure_code_i(runtime_media_failure),.ble_request_o(ble_seal_request),.ble_hold_o(ble_seal_hold),
        .ble_ready_i(ble_seal_ready),.ble_done_i(ble_seal_done),.ble_failed_i(ble_seal_failed),
        .ble_failure_code_i(ble_seal_failure),.ble_failure_code_o()
`ifdef WORKSTATION_RECORDING_DDR
        ,.recording_request_o(recording_seal_request),.recording_hold_o(recording_seal_hold),
        .recording_ready_i(recording_seal_ready),.recording_done_i(recording_seal_done),
        .recording_failed_i(recording_seal_failed),.recording_failure_code_i(recording_seal_failure),.recording_failure_code_o()
`else
        ,.recording_request_o(),.recording_hold_o(),.recording_ready_i(1'b1),
        .recording_done_i(1'b0),.recording_failed_i(1'b0),.recording_failure_code_i(4'd0),.recording_failure_code_o()
`endif
    );
`endif
    wire [447:0] performance_words;
    wire all_usb_valid,all_usb_ready;wire [17:0] all_usb_event;
    wire [447:0] push_snapshot;
    wire [31:0] score_led_mask;wire score_running,record_enabled;
    wire [33:0] service_state_usb;wire service_state_usb_valid;
    wire music_score_valid,music_score_ready,score_usb_valid,score_usb_ready;
`ifdef WORKSTATION_RUNTIME_NATIVE
    wire playlist_usb_valid,playlist_usb_ready;
`else
    wire playlist_scan_done,playlist_usb_valid,playlist_usb_ready;
`endif
    wire [7:0] playlist_name_addr,playlist_name_data;
    wire [15:0] playlist_usb_word;
    wire push_track_launch;
    wire [3:0] push_track_index;
`ifndef WORKSTATION_RUNTIME_NATIVE
    wire song_cmd_valid;
    wire [3:0] song_cmd_index;
    wire [4:0] tf_track_count;
`endif
`ifdef WORKSTATION_DEMO_NO_TF
    assign playlist_name_addr=0,playlist_usb_valid=0,playlist_usb_word=0;
`else
    tf_playlist_bridge u_playlist_bridge(
        .clk_50m(clk_50m),.reset_n(reset_n),.usb_clk(usb_clk),.usb_reset_n(usb_reset_n),
        .scan_done(playlist_scan_done),.track_count(tf_track_count),
        .name_addr(playlist_name_addr),.name_data(playlist_name_data),
        .playlist_valid(playlist_usb_valid),.playlist_ready(playlist_usb_ready),
        .playlist_word(playlist_usb_word));
`endif
`ifdef WORKSTATION_NO_CNN
    wire [6:0] music_score_note,score_usb_note;
    assign song_cmd_valid=1'b0;
    assign song_cmd_index=4'd0;
    assign music_score_ready=1'b1;
    assign score_usb_valid=1'b0;
    assign score_usb_note=7'd0;
`else
    gw138k_stream_cdc #(.WIDTH(4)) u_song_command_cdc(
        .reset_n(reset_n && usb_reset_n),.source_clk(usb_clk),.destination_clk(clk_50m),
        .source_valid(push_track_launch),.source_data(push_track_index),.drop_count(),
        .destination_valid(song_cmd_valid),.destination_data(song_cmd_index));
    wire [6:0] music_score_note,score_usb_note;
    music_async_fifo #(.WIDTH(7),.ADDRESS_BITS(2)) u_score_push_cdc(
        .write_clk_i(clk_50m),.write_rst_ni(reset_n),
        .write_valid_i(music_score_valid && score_accept),.write_ready_o(music_score_ready),
        .write_data_i(music_score_note),
        .read_clk_i(usb_clk),.read_rst_ni(usb_reset_n),
        .read_valid_o(score_usb_valid),.read_ready_i(score_usb_ready),
        .read_data_o(score_usb_note));
`endif
    wire [63:0] display_summary,display_summary_usb;wire display_summary_valid,display_summary_usb_valid;
`ifdef WORKSTATION_CNN_DEMO
    assign service_state_usb=0,service_state_usb_valid=0;
    // Coherent CNN-only status uses the existing Push metadata mailbox.
    // These levels report the real model/TF owners, never a progress timer.
    wire [1:0] cnn_error_sync;
    gw138k_level_cdc #(.WIDTH(2)) u_cnn_error_sync(
        .clk(clk_50m),.reset_n(reset_n),.data_i({tf_ddr_error,tf_unsupported}),.data_o(cnn_error_sync));
    gw138k_stream_cdc #(.WIDTH(64)) u_cnn_status_push_cdc(
        .reset_n(reset_n && usb_reset_n),.source_clk(clk_50m),.destination_clk(usb_clk),
        .source_valid(1'b1),.source_data({32'h434e4e31,8'd0,tf_hotplug_debug,tf_track_count,
            music_analysis_enable,tf_card_lost,cnn_error_sync[1],cnn_error_sync[0],
            music_model_status==4'd15,music_analysis_enable,
            music_model_status==4'd15 || tf_card_lost || (|cnn_error_sync),
            music_model_status==4'd14}),
        .destination_valid(display_summary_usb_valid),.destination_data(display_summary_usb),.drop_count());
`elsif WORKSTATION_WORKER_AUDIO_ONLY
    assign service_state_usb=0,service_state_usb_valid=0;
    assign display_summary_usb=0,display_summary_usb_valid=0;
`else
    gw138k_stream_cdc #(.WIDTH(34)) u_service_push_cdc(
        .reset_n(reset_n && audio_reset_n && usb_reset_n),.source_clk(audio_clk),.destination_clk(usb_clk),
        .source_valid(audio_sample_valid),.source_data({record_enabled,score_running,score_led_mask}),
        .destination_valid(service_state_usb_valid),.destination_data(service_state_usb));
    gw138k_stream_cdc #(.WIDTH(64)) u_display_push_cdc(
        .reset_n(reset_n && memory_reset_n && usb_reset_n),.source_clk(memory_clk),.destination_clk(usb_clk),
        .source_valid(display_summary_valid),.source_data(display_summary),
        .destination_valid(display_summary_usb_valid),.destination_data(display_summary_usb));
`endif
    wire usb_lifecycle,usb_cancel;
`ifdef WORKSTATION_CUSTOM_138K
    wire [7:0] native_usb_data;
    wire native_usb_oe;
`ifdef WORKSTATION_USB_STATUS_PANEL
    wire [2:0] usb_display_device;
    wire [3:0] usb_display_cpu_fault;
    wire usb_display_failed,usb_display_traffic,usb_display_ready,usb_display_high_speed;
    wire [7:0] usb_display_status;
    workstation_usb2_display_status u_usb_display_status(
        .cpu_clk(usb_clk),.ulpi_clk(usb2_ulpi_clk),.reset_n(usb_reset_n),
        .device_state(usb_display_device),.cpu_fault(usb_display_cpu_fault),
        .failed(usb_display_failed),.traffic_enable(usb_display_traffic),
        .transaction_ready(usb_display_ready),.high_speed(usb_display_high_speed),
        .status(usb_display_status));
`endif
    assign usb2_ulpi_data=native_usb_oe ? native_usb_data : 8'bz;
    workstation_usb2_input #(.FEEDBACK_AUDIO_DOMAIN(1)
`ifdef WORKSTATION_CNN_DEMO
        ,.CNN_DEMO_STATUS_ENABLE(1'b1)
`endif
`ifdef WORKSTATION_PUSH_RATE_CONTROL
        ,.PUSH_RATE_CONTROL_ENABLE(1'b1)
`endif
`ifdef WORKSTATION_DEMO_NO_TF
        ,.MEDIA_CONTROLS_ENABLE(1'b0)
`endif
`ifdef WORKSTATION_DEMO_D_ONLY
        ,.WORKER_DEMO(1'b1)
`endif
`ifdef WORKSTATION_RUNTIME_NATIVE
        ,.CNN_FOLLOW_ENABLE(RECOGNITION_ENABLED),.STOP_CLOCK_QUEUE_FENCE(1),.AUDIO_OWNER_RESET_SYNC(1)
`endif
    ) u_native_usb (
`ifdef WORKSTATION_PUSH_RATE_CONTROL
        .rate_control_ready_i(push_rate_usb_ready),.rate_toggle_o(push_rate_usb_toggle),.rate_rejected_o(),
`elsif WORKSTATION_CNN_DEMO
        .rate_control_ready_i(1'b0),.rate_toggle_o(),.rate_rejected_o(),
`endif
        .clk_cpu(usb_clk),.clk_ref(clk_50m),.clk_ulpi(usb2_ulpi_clk),.clk_audio(audio_clk),
`ifdef WORKSTATION_RUNTIME_NATIVE
        // Compute PLL recovery must not manufacture a second USB attach and
        // reapply defaults to a runtime whose notes/epoch were retained.
        .reset_n(usb_reset_n),.audio_reset_n(runtime_reset_n),.uart_rx_i(1'b1),.uart_tx_o(native_usb_uart),
`else
        .reset_n(usb_reset_n),.audio_reset_n(audio_reset_n),.uart_rx_i(1'b1),.uart_tx_o(native_usb_uart),
`endif
        .ulpi_data_i(usb2_ulpi_data),.ulpi_dir_i(usb2_ulpi_dir),.ulpi_nxt_i(usb2_ulpi_nxt),
        .ulpi_data_o(native_usb_data),.ulpi_data_oe_o(native_usb_oe),.ulpi_stp_o(usb2_ulpi_stp),
        .performance_words_i(performance_words),.display_meta_data_i(display_summary_usb),
        .display_meta_valid_i(display_summary_usb_valid),.service_state_data_i(service_state_usb),
        .service_state_valid_i(service_state_usb_valid),.score_valid_i(score_usb_valid),
        .analysis_done_i(music_analysis_done),.score_ready_o(score_usb_ready),.score_note_i(score_usb_note),
        .playlist_valid_i(playlist_usb_valid),.playlist_ready_o(playlist_usb_ready),.playlist_word_i(playlist_usb_word),
        .track_launch_o(push_track_launch),.track_index_o(push_track_index),
        .audio_valid_o(all_usb_valid),.audio_ready_i(all_usb_ready),.audio_event_o(all_usb_event),
        .audio_lifecycle_o(usb_lifecycle),.audio_cancel_o(usb_cancel),.telemetry_o(usb_words),
`ifdef WORKSTATION_USB_STATUS_PANEL
        .canceled_requests_o(),.cpu_fault_o(usb_display_cpu_fault),.cpu_fault_address_o(),
        .transaction_reset_n_o(usb_display_ready),.phy_ready_o(),.failed_o(usb_display_failed),
        .high_speed_o(usb_display_high_speed),.traffic_enable_o(usb_display_traffic),.sof_count_o(),
        .device_state_o(usb_display_device)
`else
        .canceled_requests_o(),.cpu_fault_o(),.cpu_fault_address_o(),.transaction_reset_n_o(),
        .phy_ready_o(),.failed_o(),.high_speed_o(),.traffic_enable_o(),.sof_count_o()
`endif
    );
`else
    push2_usb_a_control u_push(.clk(usb_clk),.reset_n(usb_reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .feedback_clk(clk_50m),.feedback_reset_n(reset_n),.performance_words(push_snapshot),
        .display_meta_data(display_summary_usb),.display_meta_valid(display_summary_usb_valid),
        .service_state_data(service_state_usb),.service_state_valid(service_state_usb_valid),
        .score_valid(score_usb_valid),.score_ready(score_usb_ready),.score_note(score_usb_note),
        .analysis_done(music_analysis_done),
        .playlist_valid(playlist_usb_valid),.playlist_ready(playlist_usb_ready),
        .playlist_word(playlist_usb_word),.track_launch(push_track_launch),
        .track_index(push_track_index),
        .select(mmio_select),.write(mmio_write),.address(mmio_address),.wdata(mmio_wdata),.ready(mmio_ready),.rdata(mmio_rdata),
        .audio_valid(all_usb_valid),.audio_ready(all_usb_ready),.audio_event(all_usb_event),.audio_lifecycle(usb_lifecycle),.audio_cancel(usb_cancel),.telemetry(usb_words));
`endif
`ifdef WORKSTATION_RUNTIME_NATIVE
    wire [15:0] master_volume;
    workstation_runtime_controlled #(.RESERVE_ZERO_EPOCH(1),.ENABLE_MEDIA_POLICY(1),.ENABLE_AE350_PCM(AE350_PCM_ENABLED),.SEPARATE_COMMON_RESET(1)
`ifdef WORKSTATION_DEMO_NO_TF
        ,.TF_CONTROL_ENABLE(0)
`endif
`ifdef WORKSTATION_DEMO_D_ONLY
        ,.SYNTH_ENGINES_ENABLE(0),.D_ONLY_ENABLE(1)
`endif
`ifdef WORKSTATION_DEMO_NO_LOCAL_RECORD
        ,.LOCAL_RECORD_ENABLE(0)
`endif
`ifdef WORKSTATION_DEMO_NO_LOCAL_SCORE
        ,.LOCAL_SCORE_ENABLE(0)
`endif
    ) u_managed(
        .rst_ni(runtime_reset_n),.common_reset_ni(button1_n),.clk_50m_i(clk_50m),.compute_clk_i(audio_clk),.memory_clk_i(memory_clk),
        .reference_48_i(clk_12m288),.reference_44_i(clk_16m9344),.midi_rx_i(midi_rx_i),
        .pc_uart_rx_i((!RECOGNITION_ENABLED || music_model_status==4'd14 || tf_mode_50) ? pc_uart_rx_i : 1'b1),
        .usb_event_valid(all_usb_valid),.usb_lifecycle(usb_lifecycle),.usb_cancel(usb_cancel),
        .usb_event_data(all_usb_event),.usb_event_ready(all_usb_ready),
        .pclk(pclk),.preset_n(preset_n),.psel(service_select),.penable(penable),.pwrite(pwrite),
        .paddr(paddr[11:0]),.pwdata(pwdata),.pstrb(pstrb),
        .pready(service_ready),.pslverr(service_error),.prdata(service_data),.performance_words_o(performance_words),
        .request_i(rate_request),.request_44k1_i(rate_target44),.switch_permit_i(memory_guard_ready),
        .recover_i(rate_recover),.media_quiescent_i(tf_media_quiet50),
        .request_ready_o(rate_request_ready),.busy_o(rate_busy),.fault_o(rate_fault),
        .accepted_o(rate_accepted),.applied_o(rate_applied),.rejected_o(rate_rejected),.failed_o(rate_failed),
        .policy_rejected_o(rate_policy_rejected),.reject_code_o(rate_reject_code),
        .fault_code_o(rate_fault_code),.clock_select_o(rate_select),.switch_block_reason_o(rate_block_reason),
        .active_44k1_o(rate44),.active_valid_o(rate_valid),.stream_epoch_o(rate_epoch),
        .source_qualified_o(rate_qualified),.quiesce_o(rate_quiesce),.stream_flush_o(rate_flush),
        .dsp_fault_o(rate_dsp_fault),.context_ready_o(rate_context_ready),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(!output_safe_compute[2]),
        .pcm_psel_i(pcm_select),.pcm_pready_o(pcm_bus_ready),.pcm_pslverr_o(pcm_bus_error),.pcm_prdata_o(pcm_bus_data),
        .hci_session_ready_i(hci_pcm_session_ready),.hci_controller_epoch_i(hci_pcm_controller_epoch),
        .hci_transport_generation_i(hci_pcm_transport_generation),
        .tf_active_i(tf_packet_active),.tf_busy_i(tf_packet_busy),.tf_valid_i(tf_packet_valid),
        .tf_error_i(tf_packet_error),.tf_left_i(tf_packet_left),.tf_right_i(tf_packet_right),
        .tf_sample_rate_i(tf_packet_rate),.tf_generation_i(tf_packet_generation),
        .expected_tf_generation_i(tf_expected_generation),.tf_ready_o(tf_packet_ready),
        .ddr_req_o(runtime_delay_req),.ddr_write_o(delay_ddr_write),.ddr_address_o(delay_ddr_address),
        .ddr_data_o(delay_ddr_data),.ddr_mask_o(),.ddr_ready_i(delay_ddr_ready && runtime_channel_open),
        .ddr_response_i(delay_ddr_response && runtime_channel_open),.ddr_read_data_i(client_rdata),
        .mclk_o(dac_mclk),.bck_o(hp_bck),.lrck_o(hp_ws),.data_o(hp_din),
        .pdn_no(dac_pdn_n),.smute_o(runtime_smute),
        .frame_valid_o(physical_frame_valid),.frame_error_o(physical_frame_error),.frame_44k1_o(physical_frame44),
        .frame_epoch_o(physical_frame_epoch),.frame_sequence_o(physical_frame_sequence),.frame_pcm_o(physical_frame_pcm),
        .held_notes_o(),.control_state_o(),.control_pitch_o(),.control_options_o(),.applied_events_o(),.pc_health_o(),
        .master_volume_o(master_volume),.active_mask_o(),.scope_status_o(scope_status_audio),
        .tf_scope_control_o(tf_scope_control_audio),.deadline_miss_o(),.midi_overflow_o(),.note_drop_o(),
        .underrun_count_o(),.midi_cdc_drop_o(),.observation_drop_o(runtime_observation_drop),.record_drop_o(),
        .uart_error_o(),.sample_valid_o(audio_sample_valid),.audio_left_o(),.audio_right_o(),
        .record_enabled_o(record_enabled),.record_failed_o(),.record_failure_code_o(),
        .score_running_o(score_running),.score_done_o(),.score_failed_o(),.led_mask_o(score_led_mask),.score_frame_o(),
        .fft_valid_o(),.fft_bin_o(),.fft_real_o(),.fft_imag_o(),.fft_frame_o(),.fft_discard_count_o(),
        .fft_44k1_o(),.fft_context_valid_o(),.fft_epoch_o(),
        .display_valid_o(output_sample_valid),.display_pcm_o(output_pcm),.display_reference_o(output_reference),
        .display_parameters_o(display_parameters),
        .display_voices_o(active_voices),.display_status_o(display_status),.display_44k1_o(display_frame44),
        .display_error_o(display_frame_error),.display_epoch_o(display_frame_epoch),.display_sequence_o(display_frame_sequence),
        .effect_mask_o(effect_mask),.effect_order_o(effect_order),
        .display_observation_fault_o(runtime_display_observation_fault),
        .media_stop_request_i(runtime_media_request),.media_stop_hold_i(runtime_media_hold),
        .media_stop_ready_o(runtime_media_ready),.media_stop_done_o(runtime_media_done),
        .media_stop_failed_o(runtime_media_failed),.media_stop_failure_code_o(runtime_media_failure),
        .tf_stop_request_o(tf_stop_request),.tf_stop_done_i(tf_stop_done),
        .tf_stop_failed_i(tf_stop_failed),.tf_stop_pending_i(tf_stop_pending),.tf_stop_failure_code_i(tf_stop_failure));
    assign dac_sslow=1'b0,dac_sd=1'b0,dac_slow=1'b0;
    assign dac_smute=runtime_smute || memory_guard_mute;
    assign synth_display_valid=output_sample_valid;
    assign synth_display_pcm=output_pcm,synth_display_reference=output_reference;
    assign synth_display_voices=active_voices,synth_display_status=display_status;
    assign delay_ddr_req=runtime_delay_req && runtime_channel_open;
`else
`ifdef WORKSTATION_CUSTOM_138K
    wire [15:0] master_volume;
`ifndef WORKSTATION_CNN_DEMO
    defparam u_managed.u_audio.u_workstation.effects.delay_stage.u_write_fifo.RAM_STYLE="block_ram";
    defparam u_managed.u_audio.u_workstation.effects.delay_stage.u_read_fifo.RAM_STYLE="block_ram";
`endif
`ifdef WORKSTATION_CNN_DEMO
    workstation_cnn_demo_audio #(.EXTERNAL_MASTER_VOLUME(1)) u_managed(
`else
    gw138k_usb_controlled_audio #(.EXTERNAL_MASTER_VOLUME(1)) u_managed(
`endif
        .master_volume_o(master_volume),
`else
    gw138k_usb_controlled_audio u_managed(
`endif
        .usb_event_valid(all_usb_valid),.usb_lifecycle(usb_lifecycle),.usb_cancel(usb_cancel),.usb_event_ready(all_usb_ready),.usb_event_data(all_usb_event),
        .pc_uart_rx_i((music_model_status==4'd14 || tf_scope_control_audio[12]) ? pc_uart_rx_i : 1'b1),.performance_words_o(performance_words),
        .led_mask_o(score_led_mask),.score_running_o(score_running),.record_enabled_o(record_enabled),
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(audio_reset_n),.midi_rx_i(midi_rx_i),
        .pclk(pclk),.preset_n(preset_n),.psel(service_select),.penable(penable),.pwrite(pwrite),
        .paddr(paddr[11:0]),.pwdata(pwdata),.pstrb(pstrb),
        .prdata(service_data),.pready(service_ready),.pslverr(service_error),
        .hp_bck(synth_hp_bck),.hp_ws(synth_hp_ws),.hp_din(synth_hp_din),.pa_en(synth_pa_en),
        .scope_status_o(scope_status_audio),.tf_scope_control_o(tf_scope_control_audio),
        .dac_reference_o(synth_dac_reference),.dac_voices_o(synth_dac_voices),.dac_health_o(synth_dac_health),
        .sample_ce_o(synth_sample_ce),.sample_valid_o(audio_sample_valid),
        .display_valid_o(synth_display_valid),.display_pcm_o(synth_display_pcm),.display_reference_o(synth_display_reference),
        .display_voices_o(synth_display_voices),.display_status_o(synth_display_status),.effect_mask_o(effect_mask),.effect_order_o(effect_order),
        .delay_mem_clk_i(memory_clk),.delay_mem_rst_ni(memory_reset_n),
        .delay_dwr_valid_o(delay_dwr_valid),.delay_dwr_data_o(delay_dwr_data),.delay_dwr_pop_i(delay_dwr_pop),
        .delay_drd_push_i(delay_drd_push),.delay_drd_data_i(delay_drd_data),.delay_drd_ready_o(delay_drd_ready));
`endif
    wire signed [16:0] output_mid_pcm=$signed({output_pcm[31],output_pcm[31:16]})+
                                            $signed({output_pcm[15],output_pcm[15:0]});
    wire signed [31:0] output_mid={output_mid_pcm,15'd0};
    wire [7:0] memory_flags;
    wire [127:0] video_diagnostics;
`ifdef WORKSTATION_CNN_DEMO
    assign runtime_serial=1,push_snapshot=performance_words;
`else
`ifdef WORKSTATION_RUNTIME_NATIVE
    gw138k_push_performance_uart #(.USB_CDC_SEPARATE_RESET(1)) u_runtime(
        .usb_cdc_assert_ni(button1_n),
`else
    gw138k_push_performance_uart u_runtime(
`endif
        .push_words(224'd0),.performance_feedback(push_snapshot),
        .usb_clk(usb_clk),.usb_reset_n(usb_reset_n),.usb_words(usb_words),
        .performance_words(performance_words),
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .audio_locked(audio_locked),.sample_valid(audio_sample_valid),.memory_flags(memory_flags),
        .audio_status(synth_display_status),.video_diagnostics(video_diagnostics),.serial_out(runtime_serial),
        .cpu_clk(pclk),.cpu_reset_n(preset_n),
`ifdef WORKSTATION_CPU_BLE_DIAGNOSTICS
        .cpu_words({trap_cause,heartbeat,ram_result,signature,business_diagnostic_data,business_diagnostic_meta,ui_report}));
`else
        .cpu_words({trap_cause,heartbeat,ram_result,signature,last_fetch,fetch_count,ui_report}));
`endif
`endif
`ifdef WORKSTATION_WORKER_AUDIO_ONLY
    assign hdmi_tx_en=1'b0;
`else
    assign hdmi_tx_en = 1'b1;
`endif
    wire [2:0] app_cmd;
    wire app_en,app_rdy,app_wren,app_wend,app_wrdy,app_rvalid;
    wire [28:0] app_addr;
`ifdef WORKSTATION_RUNTIME_NATIVE
    wire [255:0] app_wdata,app_rdata;
`else
    wire [255:0] app_wdata,app_rdata,client_rdata;
`endif
    wire [31:0] app_wmask;
    wire audio_ddr_req,audio_ddr_write,audio_ddr_ready,audio_ddr_response;
    wire audio_queued_req,audio_queued_write,audio_queued_ready;
    wire [28:0] audio_queued_address;
    wire [255:0] audio_queued_data;
    wire [28:0] audio_ddr_address;wire [255:0] audio_ddr_data;
`ifndef WORKSTATION_RUNTIME_NATIVE
    wire delay_ddr_req,delay_ddr_write,delay_ddr_ready,delay_ddr_response;
    wire [28:0] delay_ddr_address;
    wire [255:0] delay_ddr_data;
`endif
    wire delay_dwr_valid,delay_dwr_pop,delay_drd_push,delay_drd_ready;
    wire [64:0] delay_dwr_data,delay_drd_data;
    wire [7:0] delay_ddr_debug;
    // P10 delay ring DMA: arbiter owner 6, BULK_POOL first granule (128 KiB).
`ifndef WORKSTATION_RUNTIME_NATIVE
`ifdef WORKSTATION_CNN_DEMO
    assign delay_ddr_req=0,delay_ddr_write=0,delay_ddr_address=0,delay_ddr_data=0;
    assign delay_dwr_pop=0,delay_drd_push=0,delay_drd_data=0,delay_ddr_debug=0;
`else
    delay_ddr_dma #(.DELAY_BITS(14),.ECHO_SAMPLES(9600)) u_delay_ddr_dma(
        .clk_i(memory_clk),.rst_ni(memory_reset_n),
        .dwr_valid_i(delay_dwr_valid),.dwr_data_i(delay_dwr_data),.dwr_pop_o(delay_dwr_pop),
        .drd_push_o(delay_drd_push),.drd_data_o(delay_drd_data),.drd_ready_i(delay_drd_ready),
        .ddr_req_o(delay_ddr_req),.ddr_write_o(delay_ddr_write),.ddr_address_o(delay_ddr_address),
        .ddr_data_o(delay_ddr_data),.ddr_mask_o(),
        .ddr_ready_i(delay_ddr_ready),.ddr_response_i(delay_ddr_response),.ddr_read_data_i(client_rdata),
        .debug_status_o(delay_ddr_debug));
`endif
`endif
`ifdef WORKSTATION_DEMO_NO_TF
    assign audio_ddr_ready=0,audio_queued_req=0,audio_queued_write=0;
    assign audio_queued_address=0,audio_queued_data=0;
`else
    tf_audio_ddr_command_buffer u_audio_command_buffer(
        .clk(memory_clk),.rst_n(memory_reset_n),
`ifdef WORKSTATION_RUNTIME_NATIVE
        .in_valid(audio_ddr_req && runtime_channel_open),.in_write(audio_ddr_write),
`else
        .in_valid(audio_ddr_req),.in_write(audio_ddr_write),
`endif
        .in_address(audio_ddr_address),.in_data(audio_ddr_data),
        .in_ready(audio_ddr_ready),.out_valid(audio_queued_req),
        .out_write(audio_queued_write),.out_address(audio_queued_address),
`ifdef WORKSTATION_RUNTIME_NATIVE
        .out_data(audio_queued_data),.out_ready(audio_queued_ready && runtime_channel_open));
`else
        .out_data(audio_queued_data),.out_ready(audio_queued_ready));
`endif
`endif
    wire signed [31:0] tf_pcm_left,tf_pcm_right;
    wire analysis_pcm_valid,analysis_pcm_end;
    wire signed [15:0] analysis_pcm_left,analysis_pcm_right;
    wire [19:0] analysis_sample_rate;
    wire tf_pcm_valid,tf_source_active,tf_format_ready,tf_unsupported,tf_ddr_error;
`ifdef WORKSTATION_RUNTIME_NATIVE
    wire [19:0] tf_sample_rate;wire [31:0] tf_file_size;wire [10:0] tf_hotplug_debug;
`else
    wire [19:0] tf_sample_rate;wire [31:0] tf_file_size;wire tf_card_lost;wire [10:0] tf_hotplug_debug;
`endif
    wire tf_sample_ce,tf_hp_bck,tf_hp_ws,tf_hp_din,tf_pa_en;
`ifdef WORKSTATION_DEMO_NO_TF
    assign sd_cs_n=1'b1,sd_sck=1'b0,sd_mosi=1'b0;
    assign analysis_pcm_valid=0,analysis_pcm_end=0,analysis_pcm_left=0,analysis_pcm_right=0,analysis_sample_rate=0;
    assign tf_track_count=0,playlist_scan_done=0,tf_card_lost=0,tf_hotplug_debug=0,playlist_name_data=0;
    assign tf_format_ready=0,tf_unsupported=0,tf_ddr_error=0,tf_file_size=0,tf_sample_rate=0;
    assign audio_ddr_req=0,audio_ddr_write=0,audio_ddr_address=0,audio_ddr_data=0;
    assign tf_busy50=0,tf_runtime_failed=0,tf_runtime_failure=0,tf_media_quiet50=1;
    assign tf_packet_active=0,tf_packet_busy=0,tf_packet_valid=0,tf_packet_error=0;
    assign tf_packet_left=0,tf_packet_right=0,tf_packet_rate=0,tf_packet_generation=0,tf_expected_generation=0;
    assign tf_media_quiet=1,tf_stop_done=0,tf_stop_failed=0,tf_stop_failure=0,tf_stop_pending=0;
    assign tf_source_active=0;
`elsif WORKSTATION_RUNTIME_NATIVE
    workstation_tf_runtime_service #(.AUDIO_KIND(TF_AUDIO_KIND),.FILE_EXT("WAV"),.EXTERNAL_STOP_PROTOCOL(1),.SEPARATE_COMMON_RESET(1)) u_tf_audio(
        .rst_ni(runtime_reset_n),.common_reset_ni(button1_n),.clk_50m_i(clk_50m),.compute_clk_i(audio_clk),
        .memory_clk_i(memory_clk),.memory_reset_ni(memory_reset_n),
        .memory_ready_i(memory_calibrated && memory_reset_n),
        .mode_i(tf_mode_50),.run_i(tf_run_50),.restart_i(tf_explicit_restart),.cancel_i(tf_file_cancel),
        .reader_restart_i(playback_restart),.transport_error_i(tf_scope_error),.track_index_i(playback_track),
        .runtime_valid_i(rate_valid && memory_guard_ready),.runtime_44k1_i(rate44),
        .runtime_fault_i(rate_fault || rate_dsp_fault || memory_guard_fault),
        .runtime_busy_i(rate_busy),.runtime_epoch_i(rate_epoch),
        .analysis_enable_i(music_analysis_enable),.analysis_hold_i(music_analysis_hold),.analysis_pcm_ready_i(music_pcm_ready),
        .analysis_pcm_valid_o(analysis_pcm_valid),.analysis_pcm_end_o(analysis_pcm_end),
        .analysis_left_o(analysis_pcm_left),.analysis_right_o(analysis_pcm_right),.analysis_sample_rate_o(analysis_sample_rate),
        .sd_miso_i(sd_miso),.sd_cs_no(sd_cs_n),.sd_sck_o(sd_sck),.sd_mosi_o(sd_mosi),
        .track_count_o(tf_track_count),.playlist_ready_o(playlist_scan_done),.card_lost_o(tf_card_lost),
        .hotplug_debug_o(tf_hotplug_debug),.playlist_name_address_i(playlist_name_addr),.playlist_name_data_o(playlist_name_data),
        .format_ready_o(tf_format_ready),.unsupported_o(tf_unsupported),.ddr_error_o(tf_ddr_error),
        .file_size_o(tf_file_size),.file_sample_rate_o(tf_sample_rate),
        .ddr_valid_o(audio_ddr_req),.ddr_write_o(audio_ddr_write),.ddr_address_o(audio_ddr_address),
        .ddr_data_o(audio_ddr_data),.ddr_ready_i(audio_ddr_ready && runtime_channel_open),
        .ddr_response_i(audio_ddr_response && runtime_channel_open),.ddr_read_data_i(client_rdata),
        .busy_50_o(tf_busy50),.failed_o(tf_runtime_failed),.cancelled_o(),.eof_seen_o(),
        .failure_code_o(tf_runtime_failure),.paused_o(),.control_pending_o(),.media_quiescent_50_o(tf_media_quiet50),
        .source_generation_o(),.source_accepted_count_o(),.failure_count_o(),.invalidate_count_o(),
        .tf_active_o(tf_packet_active),.tf_busy_o(tf_packet_busy),.tf_valid_o(tf_packet_valid),.tf_error_o(tf_packet_error),
        .tf_left_o(tf_packet_left),.tf_right_o(tf_packet_right),.tf_sample_rate_o(tf_packet_rate),
        .tf_generation_o(tf_packet_generation),.expected_generation_o(tf_expected_generation),.tf_ready_i(tf_packet_ready),
        .media_quiescent_o(tf_media_quiet),.stale_discard_count_o(),.quiesce_discard_count_o(),
        .stop_request_i(tf_stop_request),.stop_done_o(tf_stop_done),.stop_failed_o(tf_stop_failed),
        .stop_failure_code_o(tf_stop_failure),.stop_pending_o(tf_stop_pending));
    assign tf_source_active=tf_busy50;
`else
    tf_workstation_audio_bridge #(
        .AUDIO_KIND(TF_AUDIO_KIND),
        .FILE_EXT(TF_AUDIO_KIND==1 ? "MP3" : (TF_AUDIO_KIND==3 ? "FLA" : "WAV")),.CAPTURE_ON_ANALYSIS(1)
    ) u_tf_audio(
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_ready(memory_calibrated && memory_reset_n),.restart(playback_restart),
        .track_index(playback_track),
        .sd_miso(sd_miso),.sd_cs_n(sd_cs_n),.sd_sck(sd_sck),.sd_mosi(sd_mosi),
        .sample_ce(tf_sample_ce),.pcm_left(tf_pcm_left),.pcm_right(tf_pcm_right),
        .analysis_pcm_valid(analysis_pcm_valid),.analysis_pcm_end(analysis_pcm_end),
        .playback_hold_i(!tf_mode_50 || !tf_run_50),
        .analysis_hold_i(music_analysis_hold),
        .analysis_enable_i(music_analysis_enable || (tf_mode_50 && tf_run_50)),
        .analysis_pcm_ready_i(music_pcm_ready),
        .analysis_pcm_left(analysis_pcm_left),.analysis_pcm_right(analysis_pcm_right),
        .analysis_sample_rate(analysis_sample_rate),
        .pcm_active(tf_pcm_valid),.source_active(tf_source_active),
        .sample_rate_hz(tf_sample_rate),.format_ready(tf_format_ready),.unsupported(tf_unsupported),
        .ddr_error(tf_ddr_error),.file_size(tf_file_size),.track_count(tf_track_count),
        .card_lost(tf_card_lost),
        .hotplug_debug(tf_hotplug_debug),
        .playlist_ready(playlist_scan_done),.playlist_name_addr(playlist_name_addr),
        .playlist_name_data(playlist_name_data),
        .ddr_valid(audio_ddr_req),.ddr_write(audio_ddr_write),.ddr_address(audio_ddr_address),
        .ddr_data(audio_ddr_data),.ddr_ready(audio_ddr_ready),.ddr_response(audio_ddr_response),
        .ddr_response_data(client_rdata));
`endif
    wire music_ddr_req,music_ddr_write,music_ddr_ready,music_ddr_response;
    wire [28:0] music_ddr_address;
    wire [255:0] music_ddr_data;
    wire [31:0] music_ddr_mask;
    wire music_result_valid;
    wire [6:0] music_result_note;
    wire [15:0] music_result_frame;
`ifdef WORKSTATION_DEMO_NO_TF
    wire tf_format_sync50=1'b0,tf_source_sync50=1'b0;
`else
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg tf_format_meta50,tf_format_sync50;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg tf_source_meta50,tf_source_sync50;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin
            tf_format_meta50<=0;tf_format_sync50<=0;tf_source_meta50<=0;tf_source_sync50<=0;
        end else begin
            tf_format_meta50<=tf_format_ready;tf_format_sync50<=tf_format_meta50;
            tf_source_meta50<=tf_source_active;tf_source_sync50<=tf_source_meta50;
        end
    end
`endif
`ifdef WORKSTATION_CUSTOM_138K
    wire model_flash_cs_n,model_flash_clk,model_flash_mosi;
    basic_pitch_flash_io_guard u_model_flash_guard(
        .spi_cs_n_i(model_flash_cs_n),.spi_clk_i(model_flash_clk),.spi_mosi_i(model_flash_mosi),
        .flash_cs_n_o(flash_cs_n),.flash_clk_o(flash_clk),.flash_mosi_o(flash_mosi),
        .flash_wp_n_o(flash_wp_n),.flash_hold_n_o(flash_hold_n),.owned_o());
`ifdef WORKSTATION_NO_CNN
    assign model_flash_cs_n=1'b1;
    assign model_flash_clk=1'b0;
    assign model_flash_mosi=1'b0;
`endif
`endif
`ifndef WORKSTATION_NO_CNN
`ifdef WORKSTATION_CUSTOM_138K
`ifdef WORKSTATION_CNN_DEMO
    assign model_flash_cs_n=1,model_flash_clk=0,model_flash_mosi=0;
    basic_pitch_workstation_link u_music (
`else
    basic_pitch_workstation_link #(.USE_FLASH_WEIGHTS(1'b1)) u_music (
        .flash_miso(flash_miso),.flash_cs_n(model_flash_cs_n),.flash_clk(model_flash_clk),.flash_mosi(model_flash_mosi),
`endif
`else
    basic_pitch_workstation_link u_music (
`endif
        .clk_50m(clk_50m),.reset_n(reset_n),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_calibrated(memory_calibrated),.model_serial(pc_uart_rx_i),
        .analysis_enable(music_analysis_enable),.analysis_restart(music_analysis_restart),
        .hotplug_debug(tf_hotplug_debug),
        .pcm_valid(analysis_pcm_valid && !tf_mode_50),.pcm_end(analysis_pcm_end && !tf_mode_50),
        .pcm_left(analysis_pcm_left),
        .pcm_right(analysis_pcm_right),.sample_rate(analysis_sample_rate),
        .format_ready(tf_format_sync50),.source_active(tf_source_sync50),
        .pcm_ready(music_pcm_ready),
        .model_status(music_model_status),.result_valid(music_result_valid),
        .result_note(music_result_note),.result_frame(music_result_frame),
        .score_valid(music_score_valid),.score_ready(music_score_ready),.score_note(music_score_note),
        .analysis_done(music_analysis_done),
        .report_sending(music_report_sending),.report_serial(music_report_serial),
        .ddr_req(music_ddr_req),.ddr_write(music_ddr_write),
        .ddr_address(music_ddr_address),.ddr_data(music_ddr_data),
        .ddr_mask(music_ddr_mask),.ddr_ready(music_ddr_ready),
        .ddr_response(music_ddr_response),.ddr_read_data(client_rdata));
`else
    assign music_pcm_ready=1'b1;
    assign music_model_status=4'd0;
    assign music_result_valid=1'b0;
    assign music_result_note=7'd0;
    assign music_result_frame=16'd0;
    assign music_score_valid=1'b0;
    assign music_score_note=7'd0;
    assign music_analysis_done=1'b0;
    assign music_report_sending=1'b0;
    assign music_report_serial=1'b1;
    assign music_ddr_req=1'b0;
    assign music_ddr_write=1'b0;
    assign music_ddr_address=29'd0;
    assign music_ddr_data=256'd0;
    assign music_ddr_mask=32'hffffffff;
`endif
`ifndef WORKSTATION_RUNTIME_NATIVE
    wire [19:0] tf_dac_rate=(tf_format_ready && !tf_unsupported &&
        tf_sample_rate>=20'd8000 && tf_sample_rate<=20'd96000) ? tf_sample_rate : 20'd0;
    tf_rate_pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1),.RATE_MUL(916260)) u_tf_dac(
        .clk(audio_clk),.reset_n(audio_reset_n), .sample_data(tf_run_audio ? tf_pcm_left : 32'sd0),.sample_right(tf_run_audio ? tf_pcm_right : 32'sd0),
        .sample_valid((tf_pcm_valid && tf_run_audio) || (tf_scope_control_audio[12] && !tf_run_audio)),.rate_hz(tf_dac_rate),.sample_tick(tf_sample_ce),
        .hp_bck(tf_hp_bck),.hp_ws(tf_hp_ws),.hp_din(tf_hp_din),.pa_en(tf_pa_en),
        .underrun_count(),.frame_count(),.sample_revision(24'd0),.sample_nonzero_voices(32'd0),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(32'd0),.frame_trigger_reference());
    workstation_output_router u_output_router (
        .clk_i(audio_clk),.rst_ni(audio_reset_n),.scope_enable_i(scope_status_audio[8]),
        .tf_active_i(tf_scope_control_audio[12]),.synth_tick_i(synth_sample_ce),.tf_tick_i(tf_sample_ce),
        .synth_bck_i(synth_hp_bck),.synth_ws_i(synth_hp_ws),.synth_data_i(synth_hp_din),.synth_pa_i(synth_pa_en),
        .tf_bck_i(tf_hp_bck),.tf_ws_i(tf_hp_ws),.tf_data_i(tf_hp_din),.tf_pa_i(tf_pa_en),
        .synth_reference_i(synth_dac_reference),.synth_voices_i(synth_dac_voices),.synth_health_i(synth_dac_health),
`ifdef WORKSTATION_CUSTOM_138K
        .bck_o(reference_bck),.ws_o(reference_ws),.data_o(reference_din),.pa_o(pa_en),
`else
        .bck_o(hp_bck),.ws_o(hp_ws),.data_o(hp_din),.pa_o(pa_en),
`endif
        .tap_valid_o(final_sample_valid),.tap_snapshot_o(final_snapshot)
    );
`endif
`ifdef WORKSTATION_CUSTOM_138K
    wire ble_frame_clock,ble_frame_valid,ble_pcm_valid,ble_active;
    wire [31:0] ble_frame_pcm,ble_pcm,ble_frame_sequence,ble_sequence;
`ifndef WORKSTATION_RUNTIME_NATIVE
    wire ble_debug_uart;
`endif
    wire ble_tx,ble_bt_enable,ble_wl_enable;
`ifdef WORKSTATION_NO_LOCAL_PANEL
    // The explicit no-local-panel profile retains the reviewed pin mapping.
    // No pixel clock, reset chain, raster or feedback mailbox is instantiated.
    assign lcd_r=5'd0,lcd_g=6'd0,lcd_b=5'd0;
    assign lcd_pclk=1'b0,lcd_hsync=1'b0,lcd_vsync=1'b0,lcd_de=1'b0,lcd_bl=1'b0;
`else
    workstation_lcd u_lcd (
        .clk_50m_i(clk_50m),.audio_clk_i(audio_clk),.rst_ni(reset_n),.audio_rst_ni(audio_reset_n),
        .feedback_valid_i(audio_sample_valid),.feedback_i(performance_words[255:0]),
        .score_mask_i(score_led_mask),.score_running_i(score_running),.record_enabled_i(record_enabled),
        .red_o(lcd_r),.green_o(lcd_g),.blue_o(lcd_b),.pclk_o(lcd_pclk),
        .hsync_o(lcd_hsync),.vsync_o(lcd_vsync),.de_o(lcd_de),.backlight_o(lcd_bl),.snapshot_drop_count_o()
    );
`endif
`ifndef WORKSTATION_RUNTIME_NATIVE
    workstation_fpc_audio u_fpc_audio (
        .clk_50m_i(clk_50m),.dac_reference_clk_i(clk_12m288),.audio_clk_i(audio_clk),
        .rst_ni(reset_n),.audio_rst_ni(audio_reset_n),.master_volume_i(master_volume),
        .sample_valid_i(final_sample_valid),.enable_i(!pa_en),.pcm_pair_i(final_snapshot[127:96]),
        .mclk_o(dac_mclk),.bck_o(hp_bck),.lrck_o(hp_ws),.data_o(hp_din),
        .pdn_no(dac_pdn_n),.smute_o(dac_smute),.sslow_o(dac_sslow),.sd_o(dac_sd),.slow_o(dac_slow),
        .frame_clock_o(ble_frame_clock),.frame_valid_o(ble_frame_valid),.frame_pcm_o(ble_frame_pcm),
        .frame_sequence_o(ble_frame_sequence),
        .mailbox_drop_count_o()
    );
`else
    assign ble_frame_clock=dac_mclk,ble_frame_valid=physical_frame_valid;
    assign ble_frame_pcm=physical_frame_pcm,ble_frame_sequence=physical_frame_sequence;
`endif
`ifdef WORKSTATION_NO_BLUETOOTH
    assign ble_uart_tx_o=1'bz,ble_bt_dis_n=1'b0,ble_wl_dis_n=1'b0;
    assign ble_debug_uart=1'b1;
    assign ble_seal_ready=1'b1,ble_seal_done=1'b0,ble_seal_failed=1'b0,ble_seal_failure=4'd0;
`else
`ifdef WORKSTATION_WORKER_AUDIO_ONLY
    // Capture/download is absent, so final audio is not crossed to the radio owner.
    assign ble_pcm_valid=0,ble_pcm=0,ble_sequence=0;
    wire ble_frame44=1'b0,ble_frame_error=1'b0;
    wire [31:0] ble_frame_epoch=0;
`elsif WORKSTATION_RUNTIME_NATIVE
    wire ble_frame44,ble_frame_error;
    wire [31:0] ble_frame_epoch;
    gw138k_stream_cdc #(.WIDTH(98)) u_ble_pcm_cdc (
        .reset_n(runtime_reset_n),.source_clk(ble_frame_clock),.destination_clk(clk_50m),
        .source_valid(ble_frame_valid),
        .source_data({physical_frame44,physical_frame_error,physical_frame_epoch,ble_frame_sequence,ble_frame_pcm}),
        .drop_count(),.destination_valid(ble_pcm_valid),
        .destination_data({ble_frame44,ble_frame_error,ble_frame_epoch,ble_sequence,ble_pcm})
    );
`else
    gw138k_stream_cdc #(.WIDTH(64)) u_ble_pcm_cdc (
        .reset_n(reset_n && audio_reset_n),.source_clk(ble_frame_clock),.destination_clk(clk_50m),
        .source_valid(ble_frame_valid),.source_data({ble_frame_sequence,ble_frame_pcm}),.drop_count(),
        .destination_valid(ble_pcm_valid),.destination_data({ble_sequence,ble_pcm})
    );
`endif
    wire [767:0] ble_status;
    wire ble_memory_req,ble_memory_write,ble_memory_ready,ble_memory_response;
    wire [28:0] ble_memory_address;
    wire [255:0] ble_memory_data;
    wire [31:0] ble_memory_mask;
`ifdef WORKSTATION_RUNTIME_NATIVE
`ifdef WORKSTATION_WORKER_AUDIO_ONLY
    workstation_bluetooth #(.SESSION_ONLY_PAIRING(1)) u_bluetooth (
`elsif WORKSTATION_BLE_RAW_DDR
    workstation_bluetooth #(.EXTERNAL_SEAL_PROTOCOL(1),.EXTERNAL_RAW_STORE(1),.RAW_DRAIN_TIMEOUT_CYCLES(5000000)
`ifdef WORKSTATION_SINGLE_BLE_RECORDING
        ,.SINGLE_BLE_RECORDING(1),.SESSION_ONLY_PAIRING(1)
`endif
    ) u_bluetooth (
`else
    workstation_bluetooth #(.EXTERNAL_SEAL_PROTOCOL(1)) u_bluetooth (
`endif
`else
    workstation_bluetooth #(.STORAGE_DDR(1)) u_bluetooth (
`endif
        .clk_i(clk_50m),.rst_ni(reset_n),.module_uart_tx_i(ble_uart_rx_i),
`ifdef WORKSTATION_CPU_BLE_BUSINESS
        .business_owner_reset_ni(business_owner_reset),.business_command_valid_i(business_command_valid),
        .business_command_write_i(business_command_write),.business_command_address_i(business_command_address),
        .business_command_data_i(business_command_data),.business_command_strobes_i(business_command_strobes),
        .business_command_ready_o(business_command_ready),.business_response_error_o(business_response_error),
        .business_response_data_o(business_response_data),
`ifdef WORKSTATION_AE350_PCM
        .hci_classic_ready_o(hci_pcm_session_ready),.hci_epoch_o(hci_pcm_controller_epoch),
        .hci_classic_generation_o(hci_pcm_transport_generation),
`endif
`endif
        .pcm_valid_i(ble_pcm_valid),.pcm_pair_i(ble_pcm),.pcm_sequence_i(ble_sequence),
        .memory_clk_i(memory_clk),.memory_rst_ni(memory_reset_n),.memory_ready_i(memory_calibrated),
        .memory_req_o(ble_memory_req),.memory_write_o(ble_memory_write),.memory_address_o(ble_memory_address),
        .memory_data_o(ble_memory_data),.memory_mask_o(ble_memory_mask),
        .memory_req_ready_i(ble_memory_ready),.memory_response_i(ble_memory_response),.memory_read_data_i(client_rdata),
`ifdef WORKSTATION_RUNTIME_NATIVE
        // Existing BLE format 1 remains 48 kHz. Never relabel 44.1-kHz PCM.
        .source_allowed_i(
`ifdef WORKSTATION_BLE_RAW_DDR
            recording_channel_ready50 &&
`endif
            memory_guard_ready && rate_valid && !rate44 && !rate_busy && !rate_fault && !rate_dsp_fault &&
            !ble_frame44 && !ble_frame_error && ble_frame_epoch==rate_epoch),
`else
        .source_allowed_i(1'b1),
`endif
        .module_uart_rx_o(ble_tx),.module_bt_dis_no(ble_bt_enable),
        .module_wl_dis_no(ble_wl_enable),.outputs_active_o(ble_active),
        .initialized_o(),.connected_o(),.subscribed_o(),.failed_o(),.status_o(ble_status)
`ifdef WORKSTATION_RUNTIME_NATIVE
        ,.seal_hold_i(ble_seal_hold),.seal_request_i(ble_seal_request),.seal_ready_o(ble_seal_ready),
        .seal_pending_o(),.seal_done_o(ble_seal_done),.seal_failed_o(ble_seal_failed),.seal_failure_code_o(ble_seal_failure),
        .seal_record_state_o(),.seal_recording_id_o(),.seal_frames_o(),.seal_crc_o()
`endif
`ifdef WORKSTATION_BLE_RAW_DDR
        ,.raw_start_valid_o(raw_start_valid),.raw_start_ready_i(raw_start_ready && recording_channel_ready50),.raw_start_done_i(raw_start_done),
        .raw_clear_valid_o(raw_clear_valid),.raw_clear_ready_i(raw_clear_ready),.raw_clear_done_i(raw_clear_done),
        .raw_capture_valid_o(raw_capture_valid),.raw_capture_index_o(raw_capture_index),.raw_capture_pcm_o(raw_capture_pcm),
        .raw_capture_ready_i(raw_capture_ready),.raw_close_valid_o(raw_close_valid),.raw_close_ready_i(raw_close_ready),
        .raw_drained_i(raw_drained),.raw_fault_i(raw_fault),.raw_object_fault_i(raw_object_fault),.raw_channel_fault_i(raw_channel_fault),
        .raw_failure_code_i(raw_failure),.raw_accepted_frames_i(raw_accepted),.raw_committed_frames_i(raw_committed),
        .raw_fetch_valid_o(raw_fetch_valid),.raw_fetch_ready_i(raw_fetch_ready),.raw_fetch_offset_o(raw_fetch_offset),.raw_fetch_length_o(raw_fetch_length),
        .raw_fetch_done_i(raw_fetch_done),.raw_fetch_fault_i(raw_fetch_fault),.raw_cache_valid_i(raw_cache_valid),
        .raw_sample_addr_o(raw_sample_addr),.raw_sample_word_i(raw_sample_word)
`endif
    );
    assign ble_uart_tx_o=ble_active ? ble_tx : 1'bz;
    assign ble_bt_dis_n=ble_active ? ble_bt_enable : 1'bz;
    assign ble_wl_dis_n=ble_active ? ble_wl_enable : 1'bz;
    generate if(BLUETOOTH_DIAGNOSTIC_UART) begin: bluetooth_diagnostics
        gw138k_ble_status_uart u_status (.clk(clk_50m),.resetn(reset_n),.debug(ble_status),.serial_out(ble_debug_uart));
    end else begin: no_bluetooth_diagnostics
        assign ble_debug_uart=1'b1;
    end endgenerate
`endif
`endif
    ddr_address_map_guard u_ddr_address_map_guard();
`ifdef WORKSTATION_CUSTOM_138K
`ifndef WORKSTATION_RUNTIME_NATIVE
    // Resource defaults apply only to the legacy native composition.
    // M/W retain their existing BIST, model and sampling policies.
    // Calibration remains mandatory; production skips destructive startup BIST.
    defparam u_video.u_bist.ENABLE_BIST=0;
    defparam u_native_usb.host.bus.RAM_BYTES=49152;
    defparam u_managed.u_audio.u_pc_cdc.COUNT_DROPS=0;
    defparam u_managed.u_audio.u_workstation.cue_player.VALIDATE_ROM=0;
    defparam u_music.u_basic_pitch.g_model_boot.g_flash.u_model_loader.VERIFY_DDR=0;
`endif
`endif
    ddr3_platform u_memory (
        .clk_50m(clk_50m),.rst_n(reset_n),.ui_clk(memory_clk),.ui_rst_n(memory_reset_n),
        .calib_done(memory_calibrated),.pll_locked(memory_pll_locked),
        .app_cmd(app_cmd),.app_en(app_en),.app_addr(app_addr),.app_rdy(app_rdy),
        .app_wdata(app_wdata),.app_wmask(app_wmask),.app_wren(app_wren),.app_wend(app_wend),
        .app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.app_rend(),
        .ddr_addr(ddr_addr),.ddr_bank(ddr_bank),.ddr_cs(ddr_cs),.ddr_ras(ddr_ras),
        .ddr_cas(ddr_cas),.ddr_we(ddr_we),.ddr_ck(ddr_ck),.ddr_ck_n(ddr_ck_n),
        .ddr_cke(ddr_cke),.ddr_odt(ddr_odt),.ddr_reset_n(ddr_reset_n),.ddr_dm(ddr_dm),
        .ddr_dq(ddr_dq),.ddr_dqs(ddr_dqs),.ddr_dqs_n(ddr_dqs_n)
    );
    wire cpu_mem_req,cpu_mem_write,cpu_mem_ready,cpu_mem_response;
    wire [28:0] cpu_mem_address;
    wire [255:0] cpu_mem_data;
    wire [31:0] cpu_mem_mask;
`ifndef WORKSTATION_RUNTIME_NATIVE
`ifdef WORKSTATION_CUSTOM_138K
    wire shared_music_req,shared_music_write,shared_music_ready,shared_music_response;
    wire [28:0] shared_music_address;
    wire [255:0] shared_music_data;
    wire [31:0] shared_music_mask;
    workstation_ddr_pair u_music_ble_memory (
        .clk_i(memory_clk),.rst_ni(memory_reset_n),
        .a_req_i(music_ddr_req),.a_write_i(music_ddr_write),.a_address_i(music_ddr_address),
        .a_data_i(music_ddr_data),.a_mask_i(music_ddr_mask),.a_ready_o(music_ddr_ready),.a_response_o(music_ddr_response),
        .b_req_i(ble_memory_req),.b_write_i(ble_memory_write),.b_address_i(ble_memory_address),
        .b_data_i(ble_memory_data),.b_mask_i(ble_memory_mask),.b_ready_o(ble_memory_ready),.b_response_o(ble_memory_response),
        .req_o(shared_music_req),.write_o(shared_music_write),.address_o(shared_music_address),
        .data_o(shared_music_data),.mask_o(shared_music_mask),.ready_i(shared_music_ready),.response_i(shared_music_response));
`endif
`endif
`ifdef WORKSTATION_CNN_DEMO
    workstation_cnn_demo_memory u_video(
        .reset_ni(reset_n),.clk_50m_i(clk_50m),.memory_clk_i(memory_clk),.memory_reset_ni(memory_reset_n),
        .memory_calibrated_i(memory_calibrated),.memory_pll_locked_i(memory_pll_locked),
        .audio_valid_i(audio_queued_req),.audio_write_i(audio_queued_write),.audio_address_i(audio_queued_address),.audio_data_i(audio_queued_data),
        .audio_ready_o(audio_queued_ready),.audio_response_o(audio_ddr_response),
        .music_valid_i(music_ddr_req),.music_write_i(music_ddr_write),.music_address_i(music_ddr_address),.music_data_i(music_ddr_data),
        .music_mask_i(music_ddr_mask),.music_ready_o(music_ddr_ready),.music_response_o(music_ddr_response),
        .app_cmd_o(app_cmd),.app_en_o(app_en),.app_wren_o(app_wren),.app_wend_o(app_wend),.app_address_o(app_addr),.app_data_o(app_wdata),.app_mask_o(app_wmask),
        .app_ready_i(app_rdy),.app_write_ready_i(app_wrdy),.app_response_i(app_rvalid),.app_response_data_i(app_rdata),.response_data_o(client_rdata),.memory_flags_o(memory_flags));
    assign tmds_clk_p=0,tmds_clk_n=0,tmds_data_p=0,tmds_data_n=0;
    assign display_summary=0,display_summary_valid=0,video_diagnostics=0;
    assign cpu_mem_ready=0,cpu_mem_response=0,delay_ddr_ready=0,delay_ddr_response=0;
`elsif WORKSTATION_WORKER_AUDIO_ONLY
    workstation_audio_memory u_audio_memory(
        .reset_ni(reset_n),.clk_50m_i(clk_50m),.memory_clk_i(memory_clk),
        .memory_reset_ni(memory_reset_n),.memory_calibrated_i(memory_calibrated),
        .memory_pll_locked_i(memory_pll_locked),.client_reset_no(ddr_client_reset_n),
        .client_ready_o(ddr_client_ready),.delay_valid_i(delay_ddr_req),
        .delay_write_i(delay_ddr_write),.delay_address_i(delay_ddr_address),.delay_data_i(delay_ddr_data),
        .delay_ready_o(delay_ddr_ready),.delay_response_o(delay_ddr_response),
        .app_cmd_o(app_cmd),.app_en_o(app_en),.app_address_o(app_addr),.app_ready_i(app_rdy),
        .app_data_o(app_wdata),.app_mask_o(app_wmask),.app_wren_o(app_wren),.app_wend_o(app_wend),
        .app_write_ready_i(app_wrdy),.app_response_data_i(app_rdata),.app_response_i(app_rvalid),
        .response_data_o(client_rdata),.memory_flags_o(memory_flags));
    assign video_diagnostics=0,display_observation_drop=0;
    assign display_summary=0,display_summary_valid=0,ui_frame_commit=0;
    assign audio_queued_ready=0,audio_ddr_response=0,music_ddr_ready=0,music_ddr_response=0;
    assign cpu_mem_ready=0,cpu_mem_response=0;
    assign tmds_clk_p=0,tmds_clk_n=0,tmds_data_p=0,tmds_data_n=0;
`else
    hdmi_display u_video (
`ifdef WORKSTATION_USB_STATUS_PANEL
        .usb_status_clk(usb_clk),.usb_status_reset_n(usb_reset_n),.usb_status(usb_display_status),
`endif
`ifdef WORKSTATION_PUSH_RATE_CONTROL
        // Independent of PCM observations: a stopped/muted audio stream must
        // not freeze switching/fault feedback. Bit0 is the committed rate.
        .audio_clock_status_i({rate_fault || rate_dsp_fault || memory_guard_fault || clock_service_fault,
            rate_busy || clock_service_busy,rate_valid,rate44}),
`endif
`ifdef WORKSTATION_RECORDING_DDR
        .recording_req(recording_req),.recording_write(recording_write),.recording_address(recording_address),
        .recording_data(recording_data),.recording_mask(recording_mask),.recording_ready(recording_ready),
        .recording_response(recording_response),.recording_native_accept(recording_native_accept),
        .recording_transport_fault(recording_transport_fault),
`endif
`ifdef WORKSTATION_RUNTIME_NATIVE
        .frame_44k1_i(display_frame44),.frame_error_i(display_frame_error),
        .frame_epoch_i(display_frame_epoch),.frame_sequence_i(display_frame_sequence),
        .observation_trusted_i(memory_guard_ready && rate_valid && !rate_busy && !rate_fault && !rate_dsp_fault &&
            !runtime_display_observation_fault),
        .display_observation_drop_o(display_observation_drop),
        .ddr_client_reset_no(ddr_client_reset_n),.ddr_client_ready_o(ddr_client_ready),
`endif
        .ui_pending(ui_pending),.ui_visible(ui_visible),.ui_next_visible(ui_next_visible),
        .ui_front_base(ui_front_base),.ui_next_base(ui_next_base),.ui_frame_commit(ui_frame_commit),
        .cpu_req(cpu_mem_req),.cpu_write(cpu_mem_write),.cpu_address(cpu_mem_address),
        .cpu_data(cpu_mem_data),.cpu_mask(cpu_mem_mask),.cpu_ready(cpu_mem_ready),.cpu_response(cpu_mem_response),
`ifdef WORKSTATION_RUNTIME_NATIVE
        .audio_req(audio_queued_req && runtime_channel_open),.audio_write(audio_queued_write),.audio_address(audio_queued_address),
`else
        .audio_req(audio_queued_req),.audio_write(audio_queued_write),.audio_address(audio_queued_address),
`endif
        .audio_data(audio_queued_data),.audio_ready(audio_queued_ready),.audio_response(audio_ddr_response),
`ifdef WORKSTATION_CUSTOM_138K
`ifndef WORKSTATION_RUNTIME_NATIVE
        .music_req(shared_music_req),.music_write(shared_music_write),.music_address(shared_music_address),
        .music_data(shared_music_data),.music_mask(shared_music_mask),
        .music_ready(shared_music_ready),.music_response(shared_music_response),
`else
        .music_req(music_ddr_req),.music_write(music_ddr_write),.music_address(music_ddr_address),
        .music_data(music_ddr_data),.music_mask(music_ddr_mask),
        .music_ready(music_ddr_ready),.music_response(music_ddr_response),
`endif
`else
        .music_req(music_ddr_req),.music_write(music_ddr_write),.music_address(music_ddr_address),
        .music_data(music_ddr_data),.music_mask(music_ddr_mask),
        .music_ready(music_ddr_ready),.music_response(music_ddr_response),
`endif
        .delay_req(delay_ddr_req),.delay_write(delay_ddr_write),.delay_address(delay_ddr_address),
        .delay_data(delay_ddr_data),
        .delay_ready(delay_ddr_ready),.delay_response(delay_ddr_response),
        .clk_50m(clk_50m), .reset_n(reset_n),
        .hdmi_hpd(hdmi_hpd),.video_diagnostics(video_diagnostics),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_calibrated(memory_calibrated),.memory_pll_locked(memory_pll_locked),
        .app_cmd(app_cmd),.app_en(app_en),.app_addr(app_addr),.app_rdy(app_rdy),
        .app_wdata(app_wdata),.app_wmask(app_wmask),.app_wren(app_wren),.app_wend(app_wend),
        .app_wrdy(app_wrdy),.app_rdata(app_rdata),.client_rdata(client_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),
        .push_display_summary(display_summary),.push_display_summary_valid(display_summary_valid),
        .sample_data(output_mid), .sample_valid(output_sample_valid),.output_pcm(output_pcm),
        .applied_parameters_i(display_parameters),
        .trigger_reference(output_reference),
        .active_voices(active_voices), .status_data(display_status), .effect_mask(effect_mask), .effect_order(effect_order),
        .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
        .tmds_data_p(tmds_data_p), .tmds_data_n(tmds_data_n)
    );
`endif
`ifdef WORKSTATION_CNN_DEMO
    assign pclk=clk_50m,preset_n=reset_n,psel=0,penable=0,pwrite=0,paddr=0,pwdata=0,pstrb=0;
    assign fetch_count=0,last_fetch=0,signature=0,ram_result=0,heartbeat=0,trap_cause=0,trap_pc=0,ui_report=0;
    assign cpu_mem_req=0,cpu_mem_write=0,cpu_mem_address=0,cpu_mem_data=0,cpu_mem_mask=0;
`else
    wire core_clk,bus_clk,pll_locked;
    wire system_reset_n=reset_n;
`ifdef WORKSTATION_CUSTOM_138K
    wire rtc_clk;
    workstation_ae350_rtc u_rtc(.clk_50m(clk_50m),.reset_n(system_reset_n),.rtc_clk(rtc_clk));
`endif
    gw138k_cpu_pll_cell u_cpu_pll(.clkin(clk_50m),.init_clk(clk_50m),.reset(!system_reset_n),
        .enable0(1'b1),.lock(pll_locked),.clkout0(bus_clk),.clkout1(core_clk));
    reg [16:0] lock_count=0;
    reg lock_qualified=0;
    // DDR loss restarts only the CPU/control path. Audio remains independent.
    wire cpu_memory_ready=memory_flags[1:0]==2'b11 && memory_flags[6] && !memory_flags[2];
    wire ready_async=system_reset_n && pll_locked && cpu_memory_ready;
    always @(posedge clk_50m or negedge ready_async)
        if(!ready_async) begin lock_count<=0;lock_qualified<=0;end
        else if(!lock_qualified) begin
            if(lock_count==17'd100000) lock_qualified<=1;
            else lock_count<=lock_count+1'b1;
        end
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [3:0] core_reset_pipe=0;
    always @(posedge core_clk or negedge lock_qualified)
        if(!lock_qualified) core_reset_pipe<=0;
        else core_reset_pipe<={core_reset_pipe[2:0],1'b1};
    wire cpu_reset_n=core_reset_pipe[3];
    wire rom_clk,rom_reset_n,rom_write;
`ifdef WORKSTATION_RUNTIME_NATIVE
    wire [31:0] rom_address,rom_read_data;
`else
    wire [31:0] rom_address,rom_read_data,fetch_count,last_fetch;
`endif
    wire [1:0] rom_transfer;
    wire ram_clk,ram_reset_n,ram_write;
    wire [31:0] ram_address;
    wire [63:0] ram_read_data,ram_write_data;
    wire [1:0] ram_transfer;
    wire [2:0] ram_size;
    wire [63:0] external_read_data;
    wire cpu_bus_ready,cpu_bus_error;
    wire local_address=ram_address[31:13]==0 && (ram_size==0 ||
        (ram_size==1 && !ram_address[0]) || (ram_size==2 && ram_address[1:0]==0) ||
        (ram_size==3 && ram_address[2:0]==0));
    reg local_data_phase;
    always @(posedge ram_clk or negedge ram_reset_n)
        if(!ram_reset_n) local_data_phase<=1;
        else if(cpu_bus_ready) local_data_phase<=local_address;
`ifdef WORKSTATION_WORKER_AUDIO_ONLY
    // Only the local scratch window is present. Retired external DDR accesses
    // terminate with AHB error instead of issuing an unowned memory request.
    reg external_rejected;
    always @(posedge ram_clk or negedge ram_reset_n)
        if(!ram_reset_n)external_rejected<=0;
        else external_rejected<=ram_transfer[1] && !local_address;
    assign cpu_bus_ready=1'b1,cpu_bus_error=external_rejected,external_read_data=64'd0;
    assign cpu_mem_req=0,cpu_mem_write=0,cpu_mem_address=0,cpu_mem_data=0,cpu_mem_mask=0;
`else
    gw138k_ahb_ddr u_cpu_ddr(.reset_n(ram_reset_n),.hclk(ram_clk),.memory_clk(memory_clk),
        .haddr(ram_address),.htrans(local_address?2'b00:ram_transfer),.hsize(ram_size),
        .hwrite(ram_write),.hwdata(ram_write_data),.hrdata(external_read_data),.hready(cpu_bus_ready),.hresp(cpu_bus_error),
        .req_valid(cpu_mem_req),.req_write(cpu_mem_write),.req_address(cpu_mem_address),
        .req_data(cpu_mem_data),.req_mask(cpu_mem_mask),.req_ready(cpu_mem_ready),
        .rsp_valid(cpu_mem_response),.rsp_data(client_rdata));
`endif
`ifndef WORKSTATION_RUNTIME_NATIVE
    reg [31:0] signature,ram_result,heartbeat,trap_cause,trap_pc,ui_report;
`endif
    wire valid_word=paddr[31:12]==20'hf8000 && paddr[1:0]==0 && pstrb==4'hf;
    always @(posedge pclk or negedge preset_n) begin
        if(!preset_n) begin signature<=0;ram_result<=0;heartbeat<=0;trap_cause<=0;trap_pc<=0;ui_report<=3;end
        else if(psel && penable && pwrite && valid_word) case(paddr[11:0])
            0:signature<=pwdata;
            4:ram_result<=pwdata;
            8:heartbeat<=pwdata;
            12:trap_cause<=pwdata;
            16:trap_pc<=pwdata;
            20:ui_report<=pwdata;
            default:begin end
        endcase
    end
`ifdef WORKSTATION_CPU_BLE_DIAGNOSTICS
    // Reuse the boot diagnostic page and existing C350 snapshot. A staged
    // value never appears with a preceding page/status word on the UART.
    always @(posedge pclk or negedge preset_n) begin
        if(!preset_n) begin
            business_diagnostic_stage<=0;business_diagnostic_meta<=0;business_diagnostic_data<=0;
        end else if(psel && penable && pwrite && valid_word) case(paddr[11:0])
            24:business_diagnostic_stage<=pwdata;
            28:begin business_diagnostic_meta<=pwdata;business_diagnostic_data<=business_diagnostic_stage;end
            default:begin end
        endcase
    end
`endif
`ifdef WORKSTATION_AE350_ROM96
    gw138k_boot_memory #(.ROM_BYTES(98304)) u_boot_memory(.rom_clk(rom_clk),.rom_reset_n(rom_reset_n),.rom_address(rom_address),
`elsif WORKSTATION_AE350_ROM128
    gw138k_boot_memory #(.ROM_BYTES(131072)) u_boot_memory(.rom_clk(rom_clk),.rom_reset_n(rom_reset_n),.rom_address(rom_address),
`else
    gw138k_boot_memory u_boot_memory(.rom_clk(rom_clk),.rom_reset_n(rom_reset_n),.rom_address(rom_address),
`endif
        .rom_transfer(rom_transfer),.rom_data(rom_read_data),.fetch_count(fetch_count),.last_fetch(last_fetch),
        .ram_clk(ram_clk),.ram_reset_n(ram_reset_n),.ram_address(ram_address),.ram_transfer((cpu_bus_ready && local_address)?ram_transfer:2'b00),
        .ram_size(ram_size),.ram_write(ram_write),.ram_write_data(ram_write_data),.ram_read_data(ram_read_data));
    RiscV_AE350_SOC_Top u_cpu (
        .ROM_HRDATA(rom_read_data),.ROM_HREADY(1'b1),.ROM_HRESP(1'b0),.ROM_HADDR(rom_address),
        .ROM_HTRANS(rom_transfer),.ROM_HWRITE(rom_write),.ROM_HCLK(rom_clk),.ROM_HRSTN(rom_reset_n),
        .DDR_HRDATA(local_data_phase?ram_read_data:external_read_data),.DDR_HREADY(cpu_bus_ready),.DDR_HRESP(cpu_bus_error),.DDR_HADDR(ram_address),
        .DDR_HBURST(),.DDR_HPROT(),.DDR_HSIZE(ram_size),.DDR_HTRANS(ram_transfer),
        .DDR_HWDATA(ram_write_data),.DDR_HWRITE(ram_write),.DDR_HCLK(ram_clk),.DDR_HRSTN(ram_reset_n),
`ifdef WORKSTATION_RECORDING_DDR
        .APB_PRDATA(pcm_select?pcm_bus_data:business_select?business_bus_data:recording_select?recording_bus_data:clock_service_select?clock_service_data:service_select?service_data:ui_select?ui_read_data:32'h41313338),
        .APB_PREADY(pcm_select?pcm_bus_ready:business_select?business_bus_ready:recording_select?recording_bus_ready:clock_service_select?clock_service_ready:service_select?service_ready:ui_select?ui_ready:1'b1),
        .APB_PSLVERR(pcm_select?pcm_bus_error:business_select?business_bus_error:recording_select?recording_bus_error:clock_service_select?clock_service_error:service_select?service_error:ui_select?ui_error:!valid_word),.APB_PADDR(paddr),
`elsif WORKSTATION_WORKER_AUDIO_ONLY
        .APB_PRDATA(pcm_select?pcm_bus_data:business_select?business_bus_data:clock_service_select?clock_service_data:service_select?service_data:ui_select?ui_read_data:32'h41313338),
        .APB_PREADY(pcm_select?pcm_bus_ready:business_select?business_bus_ready:clock_service_select?clock_service_ready:service_select?service_ready:ui_select?ui_ready:1'b1),
        .APB_PSLVERR(pcm_select?pcm_bus_error:business_select?business_bus_error:clock_service_select?clock_service_error:service_select?service_error:ui_select?ui_error:!valid_word),.APB_PADDR(paddr),
`elsif WORKSTATION_RUNTIME_NATIVE
        .APB_PRDATA(pcm_select?pcm_bus_data:clock_service_select?clock_service_data:service_select?service_data:ui_select?ui_read_data:32'h41313338),
        .APB_PREADY(pcm_select?pcm_bus_ready:clock_service_select?clock_service_ready:service_select?service_ready:ui_select?ui_ready:1'b1),
        .APB_PSLVERR(pcm_select?pcm_bus_error:clock_service_select?clock_service_error:service_select?service_error:ui_select?ui_error:!valid_word),.APB_PADDR(paddr),
`else
        .APB_PRDATA(service_select?service_data:ui_select?ui_read_data:32'h41313338),.APB_PREADY(service_select?service_ready:ui_select?ui_ready:1'b1),.APB_PSLVERR(service_select?service_error:ui_select?ui_error:!valid_word),.APB_PADDR(paddr),
`endif
        .APB_PENABLE(penable),.APB_PSEL(psel),.APB_PWDATA(pwdata),.APB_PWRITE(pwrite),
        .APB_PPROT(),.APB_PSTRB(pstrb),.APB_PCLK(pclk),.APB_PRSTN(preset_n),
        .TCK_IN(1'b0),.TMS_IN(1'b1),.TRST_IN(1'b1),.TDI_IN(1'b0),.TDO_OUT(),.TDO_OE(),
        .CORE0_WFI_MODE(),.RTC_WAKEUP(),
        .CORE_CLK(core_clk),.DDR_CLK(bus_clk),.AHB_CLK(bus_clk),.APB_CLK(bus_clk),
`ifdef WORKSTATION_CUSTOM_138K
        .RTC_CLK(rtc_clk),
`else
        .RTC_CLK(clk_50m),
`endif
        .POR_RSTN(cpu_reset_n),.HW_RSTN(cpu_reset_n));
`endif
endmodule
