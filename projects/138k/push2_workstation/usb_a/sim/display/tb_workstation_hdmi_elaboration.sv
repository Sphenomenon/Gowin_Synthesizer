`timescale 1ns/1ps
// Elaboration only, with official GW5A primitives. Runtime behavior is checked
// by tb_workstation_display_runtime; this does not model HDMI clock operation.
module tb_workstation_hdmi_elaboration;
    GSR GSR(.GSRI(1'b1));
    hdmi_display dut(
        .clk_50m(1'b0),.reset_n(1'b0),.hdmi_hpd(1'b0),.video_diagnostics(),
        .sample_data(32'd0),.sample_valid(1'b0),.output_pcm(32'd0),.trigger_reference(32'd0),
        .active_voices(32'd0),.status_data(32'd0),.effect_mask(3'd0),.effect_order(6'b10_01_00),
`ifdef WORKSTATION_RUNTIME_NATIVE
        .frame_44k1_i(1'b0),.frame_error_i(1'b0),.observation_trusted_i(1'b0),
        .frame_epoch_i(32'd1),.frame_sequence_i(32'd0),.display_observation_drop_o(),
        .ddr_client_reset_no(),.ddr_client_ready_o(),
`endif
        .memory_clk(1'b0),.memory_reset_n(1'b0),.memory_calibrated(1'b0),.memory_pll_locked(1'b0),
        .ui_pending(1'b0),.ui_visible(1'b0),.ui_next_visible(1'b0),.ui_front_base(29'd0),.ui_next_base(29'd0),.ui_frame_commit(),
        .cpu_req(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),.cpu_mask(32'd0),.cpu_ready(),.cpu_response(),
        .audio_req(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),.audio_ready(),.audio_response(),
        .music_req(1'b0),.music_write(1'b0),.music_address(29'd0),.music_data(256'd0),.music_mask(32'd0),.music_ready(),.music_response(),
        .delay_req(1'b0),.delay_write(1'b0),.delay_address(29'd0),.delay_data(256'd0),.delay_ready(),.delay_response(),
        .app_cmd(),.app_en(),.app_addr(),.app_rdy(1'b0),.app_wdata(),.app_wmask(),.app_wren(),.app_wend(),.app_wrdy(1'b0),
        .app_rdata(256'd0),.client_rdata(),.app_rvalid(1'b0),.memory_flags(),.push_display_summary(),.push_display_summary_valid(),
        .tmds_clk_p(),.tmds_clk_n(),.tmds_data_p(),.tmds_data_n());
endmodule
