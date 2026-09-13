// Independent C-revision migration candidate. Original Prj1 top is retained.
// G1 MIDI is on a separate expansion pin; BL616 V14 is not reused.
module gw138k_audio_display_top (
    input wire clk_50m,
    input wire button1_n,
    input wire midi_rx_i,
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
    wire [31:0] output_pcm,output_reference,active_voices,display_status;
    wire output_sample_valid;
    wire audio_sample_valid;
    gw138k_audio_adapter u_audio(
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(audio_reset_n),.midi_rx_i(midi_rx_i),
        .hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),
        .sample_ce_o(),.sample_valid_o(audio_sample_valid),.audio_left_o(),.audio_right_o(),
        .active_mask_o(),.deadline_miss_o(),.midi_overflow_o(),.note_drop_o(),
        .underrun_count_o(),.midi_cdc_drop_o(),.observation_drop_o(),.uart_error_o(),
        .record_enable_i(1'b0),.record_ready_i(1'b0),.record_valid_o(),.record_packet_o(),.record_drop_o(),
        .fft_valid_o(),.fft_bin_o(),.fft_real_o(),.fft_imag_o(),.fft_frame_o(),
        .score_write_i(1'b0),.score_address_i(8'd0),.score_data_i(64'd0),.score_length_i(9'd0),
        .score_start_i(1'b0),.score_stop_i(1'b0),.score_running_o(),.score_done_o(),.led_mask_o(),.score_frame_o(),
        .display_valid_o(output_sample_valid),.display_pcm_o(output_pcm),.display_reference_o(output_reference),
        .display_voices_o(active_voices),.display_status_o(display_status));
    wire signed [16:0] output_mid_pcm=$signed({output_pcm[31],output_pcm[31:16]})+
                                            $signed({output_pcm[15],output_pcm[15:0]});
    wire signed [31:0] output_mid={output_mid_pcm,15'd0};
    wire [7:0] memory_flags;
    wire [127:0] video_diagnostics;
    gw138k_runtime_uart u_runtime(
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .audio_locked(audio_locked),.sample_valid(audio_sample_valid),.memory_flags(memory_flags),
        .audio_status(display_status),.video_diagnostics(video_diagnostics),.serial_out(debug_uart_tx));
    assign hdmi_tx_en = 1'b1;
    wire memory_clk,memory_reset_n,memory_calibrated,memory_pll_locked;
    wire [2:0] app_cmd;
    wire app_en,app_rdy,app_wren,app_wend,app_wrdy,app_rvalid;
    wire [28:0] app_addr;
    wire [255:0] app_wdata,app_rdata;
    wire [31:0] app_wmask;
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
    hdmi_display u_video (
        .clk_50m(clk_50m), .reset_n(reset_n),
        .hdmi_hpd(hdmi_hpd),.video_diagnostics(video_diagnostics),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_calibrated(memory_calibrated),.memory_pll_locked(memory_pll_locked),
        .app_cmd(app_cmd),.app_en(app_en),.app_addr(app_addr),.app_rdy(app_rdy),
        .app_wdata(app_wdata),.app_wmask(app_wmask),.app_wren(app_wren),.app_wend(app_wend),
        .app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),
        .sample_data(output_mid), .sample_valid(output_sample_valid),.output_pcm(output_pcm),
        .trigger_reference(output_reference),
        .active_voices(active_voices), .status_data(display_status),
        .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
        .tmds_data_p(tmds_data_p), .tmds_data_n(tmds_data_n)
    );
endmodule
