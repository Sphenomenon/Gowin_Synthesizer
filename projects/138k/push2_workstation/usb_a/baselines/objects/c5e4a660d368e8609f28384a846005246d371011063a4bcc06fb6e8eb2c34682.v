// USB derivative; source origin hashes in integration/ORIGINS.json.
// Independent C-revision migration candidate. Original Prj1 top is retained.
// G1 MIDI is on a separate expansion pin; BL616 V14 is not reused.
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
    wire mmio_select,mmio_write,mmio_ready;
    wire [7:0] mmio_address;wire [31:0] mmio_wdata,mmio_rdata;
    wire [223:0] usb_words;
    iosys2 u_usb_host(.clk(usb_clk),.resetn(usb_reset_n),.uart_rx(1'b1),.uart_tx(),
        .usb_dp(usb1_dp),.usb_dm(usb1_dn),.mmio_select(mmio_select),.mmio_write(mmio_write),
        .mmio_address(mmio_address),.mmio_wdata(mmio_wdata),.mmio_ready(mmio_ready),.mmio_rdata(mmio_rdata));
    wire [31:0] output_pcm,output_reference,active_voices,display_status;
    wire synth_hp_bck,synth_hp_ws,synth_hp_din,synth_pa_en,synth_sample_ce;
    wire [31:0] scope_status_audio,tf_scope_control_audio,tf_scope_control_50;
    wire tf_control_valid,tf_mode_50,tf_run_50,tf_scope_restart,tf_scope_cancel,tf_scope_error;
    wire [3:0] tf_scope_track;
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
        .restart_o(tf_scope_restart),.cancel_analysis_o(tf_scope_cancel),.error_o(tf_scope_error));
    reg tf_run_meta,tf_run_audio;
    always @(posedge audio_clk or negedge audio_reset_n)
        if(!audio_reset_n) begin tf_run_meta<=0;tf_run_audio<=0;end
        else begin tf_run_meta<=tf_run_50;tf_run_audio<=tf_run_meta;end
    wire final_switching,final_sample_valid,final_tf_selected;
    wire [31:0] final_pcm,final_reference,synth_dac_reference,synth_dac_voices,synth_dac_health;
    wire synth_display_valid;
    wire [31:0] synth_display_pcm,synth_display_reference,synth_display_voices,synth_display_status;
    pt8211_observer u_final_output_observer(
        .clk(audio_clk),.reset_n(audio_reset_n && !final_switching),.bck(hp_bck),.ws(hp_ws),.din(hp_din),
        .frame_reference(final_tf_selected ? 32'd0 : synth_dac_reference),
        .pcm_pair(final_pcm),.sample_valid(final_sample_valid),.trigger_reference(final_reference));
    gw138k_stream_cdc #(.WIDTH(128)) u_final_output_cdc(
        .reset_n(reset_n && audio_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(final_sample_valid && !final_switching),
        .source_data({final_pcm,final_reference,final_tf_selected ? 32'd0 : synth_dac_voices,synth_dac_health}),
        .drop_count(),.destination_valid(output_sample_valid),
        .destination_data({output_pcm,output_reference,active_voices,display_status}));
    wire [3:0] music_model_status;
    wire music_report_sending,music_report_serial,runtime_serial;
    wire music_pcm_ready;
    wire music_analysis_done;
    reg music_model_ready_q;
    reg [21:0] music_restart_delay;
    reg [2:0] music_run_reset_count;
    reg music_song_started,tf_song_restart;
    reg tf_recover;
    reg [28:0] tf_recover_wait;
    reg [3:0] tf_selected_track,pending_track;
    wire music_model_ready=music_model_status==4'd14;
    wire tf_restart=music_model_ready && !music_model_ready_q;
    wire music_analysis_restart=music_run_reset_count!=0;
    wire music_analysis_enable=music_model_ready_q && music_song_started &&
        music_restart_delay==0 && !music_analysis_restart && !tf_mode_50;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin
            music_model_ready_q<=0;music_restart_delay<=0;music_run_reset_count<=0;
            music_song_started<=0;tf_song_restart<=0;song_pending<=0;
            tf_selected_track<=0;pending_track<=0;tf_recover<=0;tf_recover_wait<=0;
        end else begin
            music_model_ready_q<=music_model_ready;
            tf_song_restart<=0;
            if(music_run_reset_count!=0) music_run_reset_count<=music_run_reset_count-1'b1;
            if(tf_restart) music_restart_delay<=22'd2_500_000;
            else if(music_restart_delay!=0) music_restart_delay<=music_restart_delay-1'b1;
            if(tf_scope_cancel) begin
                // Fresh recognition on exit: no mixed tracks/windows. Keep the
                // model and staged CNN caches; a later menu launch rearms it.
                song_pending<=0;music_song_started<=0;tf_recover<=0;
                music_run_reset_count<=3'd4;music_restart_delay<=0;
            end else if(tf_card_lost) begin
                song_pending<=0;music_song_started<=0;
                music_run_reset_count<=3'd4;music_restart_delay<=0;
                // A TF transport fault resets the reader and rescans. If
                // the playlist returns, restart the same song in place;
                // a card that stays missing lets the recovery expire into
                // this teardown and the held playlist count drops to menu.
                tf_recover<=music_song_started;tf_recover_wait<=29'd480_000_000;
            end else if(tf_recover) begin
                if(playlist_scan_done && tf_track_count!=0) begin
                    tf_recover<=0;music_song_started<=1;
                    music_run_reset_count<=3'd4;
                    music_restart_delay<=22'd2_500_000;
                end else if(tf_recover_wait==0) tf_recover<=0;
                else tf_recover_wait<=tf_recover_wait-1'b1;
            end else if(song_cmd_valid && !tf_mode_50) begin song_pending<=1;pending_track<=song_cmd_index;end
            else if(song_pending && music_model_ready && !tf_mode_50) begin
                song_pending<=0;music_song_started<=1;
                tf_selected_track<=pending_track;tf_song_restart<=1;
                music_run_reset_count<=3'd4;
                music_restart_delay<=22'd2_500_000;
            end
        end
    end
    assign debug_uart_tx=music_report_sending ? music_report_serial : runtime_serial;
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
    wire service_select=psel && paddr[31:12]==20'hf8010;
    wire [447:0] performance_words;
    wire all_usb_valid,all_usb_ready;wire [17:0] all_usb_event;
    wire [447:0] push_snapshot;
    wire [31:0] score_led_mask;wire score_running,record_enabled;
    wire [33:0] service_state_usb;wire service_state_usb_valid;
    wire music_score_valid,music_score_ready,score_usb_valid,score_usb_ready;
    wire playlist_scan_done,playlist_usb_valid,playlist_usb_ready;
    wire [7:0] playlist_name_addr,playlist_name_data;
    wire [15:0] playlist_usb_word;
    wire push_track_launch;
    wire [3:0] push_track_index;
    wire song_cmd_valid;
    wire [3:0] song_cmd_index;
    wire [4:0] tf_track_count;
    reg song_pending;
    tf_playlist_bridge u_playlist_bridge(
        .clk_50m(clk_50m),.reset_n(reset_n),.usb_clk(usb_clk),.usb_reset_n(usb_reset_n),
        .scan_done(playlist_scan_done),.track_count(tf_track_count),
        .name_addr(playlist_name_addr),.name_data(playlist_name_data),
        .playlist_valid(playlist_usb_valid),.playlist_ready(playlist_usb_ready),
        .playlist_word(playlist_usb_word));
    gw138k_stream_cdc #(.WIDTH(4)) u_song_command_cdc(
        .reset_n(reset_n && usb_reset_n),.source_clk(usb_clk),.destination_clk(clk_50m),
        .source_valid(push_track_launch),.source_data(push_track_index),.drop_count(),
        .destination_valid(song_cmd_valid),.destination_data(song_cmd_index));
    wire [6:0] music_score_note,score_usb_note;
    music_async_fifo #(.WIDTH(7),.ADDRESS_BITS(2)) u_score_push_cdc(
        .write_clk_i(clk_50m),.write_rst_ni(reset_n),
        .write_valid_i(music_score_valid && !song_pending && !song_cmd_valid && !tf_card_lost),.write_ready_o(music_score_ready),
        .write_data_i(music_score_note),
        .read_clk_i(usb_clk),.read_rst_ni(usb_reset_n),
        .read_valid_o(score_usb_valid),.read_ready_i(score_usb_ready),
        .read_data_o(score_usb_note));
    gw138k_stream_cdc #(.WIDTH(34)) u_service_push_cdc(
        .reset_n(reset_n && audio_reset_n && usb_reset_n),.source_clk(audio_clk),.destination_clk(usb_clk),
        .source_valid(audio_sample_valid),.source_data({record_enabled,score_running,score_led_mask}),
        .destination_valid(service_state_usb_valid),.destination_data(service_state_usb));
    wire [63:0] display_summary,display_summary_usb;wire display_summary_valid,display_summary_usb_valid;
    gw138k_stream_cdc #(.WIDTH(64)) u_display_push_cdc(
        .reset_n(reset_n && memory_reset_n && usb_reset_n),.source_clk(memory_clk),.destination_clk(usb_clk),
        .source_valid(display_summary_valid),.source_data(display_summary),
        .destination_valid(display_summary_usb_valid),.destination_data(display_summary_usb));
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
        .audio_valid(all_usb_valid),.audio_ready(all_usb_ready),.audio_event(all_usb_event),.telemetry(usb_words));
    gw138k_usb_controlled_audio u_managed(
        .usb_event_valid(all_usb_valid),.usb_event_ready(all_usb_ready),.usb_event_data(all_usb_event),
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
    wire signed [16:0] output_mid_pcm=$signed({output_pcm[31],output_pcm[31:16]})+
                                            $signed({output_pcm[15],output_pcm[15:0]});
    wire signed [31:0] output_mid={output_mid_pcm,15'd0};
    wire [7:0] memory_flags;
    wire [127:0] video_diagnostics;
    gw138k_push_performance_uart u_runtime(
        .push_words(224'd0),.performance_feedback(push_snapshot),
        .usb_clk(usb_clk),.usb_reset_n(usb_reset_n),.usb_words(usb_words),
        .performance_words(performance_words),
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .audio_locked(audio_locked),.sample_valid(audio_sample_valid),.memory_flags(memory_flags),
        .audio_status(synth_display_status),.video_diagnostics(video_diagnostics),.serial_out(runtime_serial),
        .cpu_clk(pclk),.cpu_reset_n(preset_n),.cpu_words({trap_cause,heartbeat,ram_result,signature,last_fetch,fetch_count,ui_report}));
    assign hdmi_tx_en = 1'b1;
    wire [2:0] app_cmd;
    wire app_en,app_rdy,app_wren,app_wend,app_wrdy,app_rvalid;
    wire [28:0] app_addr;
    wire [255:0] app_wdata,app_rdata;
    wire [31:0] app_wmask;
    wire audio_ddr_req,audio_ddr_write,audio_ddr_ready,audio_ddr_response;
    wire audio_queued_req,audio_queued_write,audio_queued_ready;
    wire [28:0] audio_queued_address;
    wire [255:0] audio_queued_data;
    wire [28:0] audio_ddr_address;wire [255:0] audio_ddr_data;
    wire delay_ddr_req,delay_ddr_write,delay_ddr_ready,delay_ddr_response;
    wire [28:0] delay_ddr_address;
    wire [255:0] delay_ddr_data;
    wire delay_dwr_valid,delay_dwr_pop,delay_drd_push,delay_drd_ready;
    wire [64:0] delay_dwr_data,delay_drd_data;
    wire [7:0] delay_ddr_debug;
    // P10 delay ring DMA: arbiter owner 6, BULK_POOL first granule (128 KiB).
    delay_ddr_dma #(.DELAY_BITS(14),.ECHO_SAMPLES(9600)) u_delay_ddr_dma(
        .clk_i(memory_clk),.rst_ni(memory_reset_n),
        .dwr_valid_i(delay_dwr_valid),.dwr_data_i(delay_dwr_data),.dwr_pop_o(delay_dwr_pop),
        .drd_push_o(delay_drd_push),.drd_data_o(delay_drd_data),.drd_ready_i(delay_drd_ready),
        .ddr_req_o(delay_ddr_req),.ddr_write_o(delay_ddr_write),.ddr_address_o(delay_ddr_address),
        .ddr_data_o(delay_ddr_data),.ddr_mask_o(),
        .ddr_ready_i(delay_ddr_ready),.ddr_response_i(delay_ddr_response),.ddr_read_data_i(app_rdata),
        .debug_status_o(delay_ddr_debug));
    tf_audio_ddr_command_buffer u_audio_command_buffer(
        .clk(memory_clk),.rst_n(memory_reset_n),
        .in_valid(audio_ddr_req),.in_write(audio_ddr_write),
        .in_address(audio_ddr_address),.in_data(audio_ddr_data),
        .in_ready(audio_ddr_ready),.out_valid(audio_queued_req),
        .out_write(audio_queued_write),.out_address(audio_queued_address),
        .out_data(audio_queued_data),.out_ready(audio_queued_ready));
    wire signed [31:0] tf_pcm_left,tf_pcm_right;
    wire analysis_pcm_valid,analysis_pcm_end;
    wire signed [15:0] analysis_pcm_left,analysis_pcm_right;
    wire [19:0] analysis_sample_rate;
    wire tf_pcm_valid,tf_source_active,tf_format_ready,tf_unsupported,tf_ddr_error;
    wire [19:0] tf_sample_rate;wire [31:0] tf_file_size;wire tf_card_lost;wire [10:0] tf_hotplug_debug;
    wire tf_sample_ce,tf_hp_bck,tf_hp_ws,tf_hp_din,tf_pa_en;
    tf_workstation_audio_bridge #(
        .AUDIO_KIND(TF_AUDIO_KIND),
        .FILE_EXT(TF_AUDIO_KIND==1 ? "MP3" : (TF_AUDIO_KIND==3 ? "FLA" : "WAV")),.CAPTURE_ON_ANALYSIS(1)
    ) u_tf_audio(
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_ready(memory_calibrated && memory_reset_n),.restart(tf_scope_restart || (!tf_mode_50 && (tf_restart || tf_song_restart))),
        .track_index(tf_mode_50 ? tf_scope_track : tf_selected_track),
        .sd_miso(sd_miso),.sd_cs_n(sd_cs_n),.sd_sck(sd_sck),.sd_mosi(sd_mosi),
        .sample_ce(tf_sample_ce),.pcm_left(tf_pcm_left),.pcm_right(tf_pcm_right),
        .analysis_pcm_valid(analysis_pcm_valid),.analysis_pcm_end(analysis_pcm_end),
        .playback_hold_i(!tf_mode_50 || !tf_run_50),
        .analysis_hold_i(!tf_mode_50 && music_model_ready_q && music_song_started && !music_analysis_done),
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
        .ddr_response_data(app_rdata));
    wire music_ddr_req,music_ddr_write,music_ddr_ready,music_ddr_response;
    wire [28:0] music_ddr_address;
    wire [255:0] music_ddr_data;
    wire [31:0] music_ddr_mask;
    wire music_result_valid;
    wire [6:0] music_result_note;
    wire [15:0] music_result_frame;
    basic_pitch_workstation_link u_music (
        .clk_50m(clk_50m),.reset_n(reset_n),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_calibrated(memory_calibrated),.model_serial(pc_uart_rx_i),
        .analysis_enable(music_analysis_enable),.analysis_restart(music_analysis_restart),
        .hotplug_debug(tf_hotplug_debug),
        .pcm_valid(analysis_pcm_valid && !tf_mode_50),.pcm_end(analysis_pcm_end && !tf_mode_50),
        .pcm_left(analysis_pcm_left),
        .pcm_right(analysis_pcm_right),.sample_rate(analysis_sample_rate),
        .format_ready(tf_format_ready),.source_active(tf_source_active),
        .pcm_ready(music_pcm_ready),
        .model_status(music_model_status),.result_valid(music_result_valid),
        .result_note(music_result_note),.result_frame(music_result_frame),
        .score_valid(music_score_valid),.score_ready(music_score_ready),.score_note(music_score_note),
        .analysis_done(music_analysis_done),
        .report_sending(music_report_sending),.report_serial(music_report_serial),
        .ddr_req(music_ddr_req),.ddr_write(music_ddr_write),
        .ddr_address(music_ddr_address),.ddr_data(music_ddr_data),
        .ddr_mask(music_ddr_mask),.ddr_ready(music_ddr_ready),
        .ddr_response(music_ddr_response),.ddr_read_data(app_rdata));
    wire [19:0] tf_dac_rate=(tf_format_ready && !tf_unsupported &&
        tf_sample_rate>=20'd8000 && tf_sample_rate<=20'd96000) ? tf_sample_rate : 20'd0;
    tf_rate_pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1),.RATE_MUL(916260)) u_tf_dac(
        .clk(audio_clk),.reset_n(audio_reset_n), .sample_data(tf_run_audio ? tf_pcm_left : 32'sd0),.sample_right(tf_run_audio ? tf_pcm_right : 32'sd0),
        .sample_valid((tf_pcm_valid && tf_run_audio) || (tf_scope_control_audio[12] && !tf_run_audio)),.rate_hz(tf_dac_rate),.sample_tick(tf_sample_ce),
        .hp_bck(tf_hp_bck),.hp_ws(tf_hp_ws),.hp_din(tf_hp_din),.pa_en(tf_pa_en),
        .underrun_count(),.frame_count(),.sample_revision(24'd0),.sample_nonzero_voices(32'd0),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(32'd0),.frame_trigger_reference());
    scope_dac_select u_scope_output(
        .clk_i(audio_clk),.rst_ni(audio_reset_n),.scope_enable_i(scope_status_audio[8]),
        .tf_source_active_i(tf_scope_control_audio[12]),
        .synth_frame_tick_i(synth_sample_ce),.tf_frame_tick_i(tf_sample_ce),
        .synth_bck_i(synth_hp_bck),.synth_ws_i(synth_hp_ws),.synth_din_i(synth_hp_din),.synth_pa_i(synth_pa_en),
        .tf_bck_i(tf_hp_bck),.tf_ws_i(tf_hp_ws),.tf_din_i(tf_hp_din),.tf_pa_i(tf_pa_en),
        .hp_bck_o(hp_bck),.hp_ws_o(hp_ws),.hp_din_o(hp_din),.pa_en_o(pa_en),
        .tf_selected_o(final_tf_selected),.switching_o(final_switching));
    ddr_address_map_guard u_ddr_address_map_guard();
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
    hdmi_display u_video (
        .ui_pending(ui_pending),.ui_visible(ui_visible),.ui_next_visible(ui_next_visible),
        .ui_front_base(ui_front_base),.ui_next_base(ui_next_base),.ui_frame_commit(ui_frame_commit),
        .cpu_req(cpu_mem_req),.cpu_write(cpu_mem_write),.cpu_address(cpu_mem_address),
        .cpu_data(cpu_mem_data),.cpu_mask(cpu_mem_mask),.cpu_ready(cpu_mem_ready),.cpu_response(cpu_mem_response),
        .audio_req(audio_queued_req),.audio_write(audio_queued_write),.audio_address(audio_queued_address),
        .audio_data(audio_queued_data),.audio_ready(audio_queued_ready),.audio_response(audio_ddr_response),
        .music_req(music_ddr_req),.music_write(music_ddr_write),.music_address(music_ddr_address),
        .music_data(music_ddr_data),.music_mask(music_ddr_mask),
        .music_ready(music_ddr_ready),.music_response(music_ddr_response),
        .delay_req(delay_ddr_req),.delay_write(delay_ddr_write),.delay_address(delay_ddr_address),
        .delay_data(delay_ddr_data),
        .delay_ready(delay_ddr_ready),.delay_response(delay_ddr_response),
        .clk_50m(clk_50m), .reset_n(reset_n),
        .hdmi_hpd(hdmi_hpd),.video_diagnostics(video_diagnostics),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_calibrated(memory_calibrated),.memory_pll_locked(memory_pll_locked),
        .app_cmd(app_cmd),.app_en(app_en),.app_addr(app_addr),.app_rdy(app_rdy),
        .app_wdata(app_wdata),.app_wmask(app_wmask),.app_wren(app_wren),.app_wend(app_wend),
        .app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),
        .push_display_summary(display_summary),.push_display_summary_valid(display_summary_valid),
        .sample_data(output_mid), .sample_valid(output_sample_valid),.output_pcm(output_pcm),
        .trigger_reference(output_reference),
        .active_voices(active_voices), .status_data(display_status), .effect_mask(effect_mask), .effect_order(effect_order),
        .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
        .tmds_data_p(tmds_data_p), .tmds_data_n(tmds_data_n)
    );
    wire core_clk,bus_clk,pll_locked;
    wire system_reset_n=reset_n;
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
    wire [31:0] rom_address,rom_read_data,fetch_count,last_fetch;
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
    gw138k_ahb_ddr u_cpu_ddr(.reset_n(ram_reset_n),.hclk(ram_clk),.memory_clk(memory_clk),
        .haddr(ram_address),.htrans(local_address?2'b00:ram_transfer),.hsize(ram_size),
        .hwrite(ram_write),.hwdata(ram_write_data),.hrdata(external_read_data),.hready(cpu_bus_ready),.hresp(cpu_bus_error),
        .req_valid(cpu_mem_req),.req_write(cpu_mem_write),.req_address(cpu_mem_address),
        .req_data(cpu_mem_data),.req_mask(cpu_mem_mask),.req_ready(cpu_mem_ready),
        .rsp_valid(cpu_mem_response),.rsp_data(app_rdata));
    reg [31:0] signature,ram_result,heartbeat,trap_cause,trap_pc,ui_report;
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
    gw138k_boot_memory u_boot_memory(.rom_clk(rom_clk),.rom_reset_n(rom_reset_n),.rom_address(rom_address),
        .rom_transfer(rom_transfer),.rom_data(rom_read_data),.fetch_count(fetch_count),.last_fetch(last_fetch),
        .ram_clk(ram_clk),.ram_reset_n(ram_reset_n),.ram_address(ram_address),.ram_transfer((cpu_bus_ready && local_address)?ram_transfer:2'b00),
        .ram_size(ram_size),.ram_write(ram_write),.ram_write_data(ram_write_data),.ram_read_data(ram_read_data));
    RiscV_AE350_SOC_Top u_cpu (
        .ROM_HRDATA(rom_read_data),.ROM_HREADY(1'b1),.ROM_HRESP(1'b0),.ROM_HADDR(rom_address),
        .ROM_HTRANS(rom_transfer),.ROM_HWRITE(rom_write),.ROM_HCLK(rom_clk),.ROM_HRSTN(rom_reset_n),
        .DDR_HRDATA(local_data_phase?ram_read_data:external_read_data),.DDR_HREADY(cpu_bus_ready),.DDR_HRESP(cpu_bus_error),.DDR_HADDR(ram_address),
        .DDR_HBURST(),.DDR_HPROT(),.DDR_HSIZE(ram_size),.DDR_HTRANS(ram_transfer),
        .DDR_HWDATA(ram_write_data),.DDR_HWRITE(ram_write),.DDR_HCLK(ram_clk),.DDR_HRSTN(ram_reset_n),
        .APB_PRDATA(service_select?service_data:ui_select?ui_read_data:32'h41313338),.APB_PREADY(service_select?service_ready:ui_select?ui_ready:1'b1),.APB_PSLVERR(service_select?service_error:ui_select?ui_error:!valid_word),.APB_PADDR(paddr),
        .APB_PENABLE(penable),.APB_PSEL(psel),.APB_PWDATA(pwdata),.APB_PWRITE(pwrite),
        .APB_PPROT(),.APB_PSTRB(pstrb),.APB_PCLK(pclk),.APB_PRSTN(preset_n),
        .TCK_IN(1'b0),.TMS_IN(1'b1),.TRST_IN(1'b1),.TDI_IN(1'b0),.TDO_OUT(),.TDO_OE(),
        .CORE0_WFI_MODE(),.RTC_WAKEUP(),
        .CORE_CLK(core_clk),.DDR_CLK(bus_clk),.AHB_CLK(bus_clk),.APB_CLK(bus_clk),.RTC_CLK(clk_50m),
        .POR_RSTN(cpu_reset_n),.HW_RSTN(cpu_reset_n));
endmodule
