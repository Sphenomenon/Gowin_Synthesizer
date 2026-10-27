`default_nettype none
`include "hdmi_isolation_config.vh"
module workstation_hdmi_isolation (
    input wire clk_50m,
    input wire reset_n,
    input wire hdmi_hpd,
    input wire signed [31:0] sample_data,
    input wire sample_valid,
    input wire [31:0] output_pcm,
    input wire [31:0] trigger_reference,
    input wire [31:0] active_voices,
    input wire [31:0] status_data,
    input wire [2:0] effect_mask,
    input wire [5:0] effect_order,
    input wire ui_pending, ui_visible, ui_next_visible,
    input wire [28:0] ui_front_base, ui_next_base,
    output wire ui_frame_commit,
    input wire cpu_req, cpu_write,
    input wire [28:0] cpu_address,
    input wire [255:0] cpu_data,
    input wire [31:0] cpu_mask,
    output wire cpu_ready, cpu_response,
    output wire [255:0] client_rdata,
    output wire ui_clk, ui_reset_n,
    output wire [7:0] memory_flags,
    output wire [127:0] video_diagnostics,
    output wire tmds_clk_p, tmds_clk_n,
    output wire [2:0] tmds_data_p, tmds_data_n,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs, ddr_ras, ddr_cas, ddr_we,
    output wire ddr_ck, ddr_ck_n, ddr_cke, ddr_odt, ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs, ddr_dqs_n
);
    wire memory_clk, memory_reset_n, memory_calibrated, memory_pll_locked;
    wire [2:0] app_cmd;
    wire app_en, app_rdy, app_wren, app_wend, app_wrdy, app_rvalid;
    wire [28:0] app_addr;
    wire [255:0] app_wdata, app_rdata;
    wire [31:0] app_wmask;
    assign ui_clk = memory_clk;
    assign ui_reset_n = memory_reset_n;
    ddr3_platform u_memory (
        .clk_50m(clk_50m), .rst_n(reset_n), .ui_clk(memory_clk), .ui_rst_n(memory_reset_n),
        .calib_done(memory_calibrated), .pll_locked(memory_pll_locked),
        .app_cmd(app_cmd), .app_en(app_en), .app_addr(app_addr), .app_rdy(app_rdy),
        .app_wdata(app_wdata), .app_wmask(app_wmask), .app_wren(app_wren), .app_wend(app_wend),
        .app_wrdy(app_wrdy), .app_rdata(app_rdata), .app_rvalid(app_rvalid), .app_rend(),
        .ddr_addr(ddr_addr), .ddr_bank(ddr_bank), .ddr_cs(ddr_cs), .ddr_ras(ddr_ras),
        .ddr_cas(ddr_cas), .ddr_we(ddr_we), .ddr_ck(ddr_ck), .ddr_ck_n(ddr_ck_n),
        .ddr_cke(ddr_cke), .ddr_odt(ddr_odt), .ddr_reset_n(ddr_reset_n),
        .ddr_dm(ddr_dm), .ddr_dq(ddr_dq), .ddr_dqs(ddr_dqs), .ddr_dqs_n(ddr_dqs_n)
    );
    hdmi_display u_video (
        .clk_50m(clk_50m), .reset_n(reset_n), .hdmi_hpd(hdmi_hpd),
        .video_diagnostics(video_diagnostics), .sample_data(sample_data), .sample_valid(sample_valid),
        .output_pcm(output_pcm), .trigger_reference(trigger_reference), .active_voices(active_voices),
        .status_data(status_data), .effect_mask(effect_mask), .effect_order(effect_order),
        .memory_clk(memory_clk), .memory_reset_n(memory_reset_n),
        .memory_calibrated(memory_calibrated), .memory_pll_locked(memory_pll_locked),
        .ui_pending(ui_pending), .ui_visible(ui_visible), .ui_next_visible(ui_next_visible),
        .ui_front_base(ui_front_base), .ui_next_base(ui_next_base), .ui_frame_commit(ui_frame_commit),
        .cpu_req(cpu_req), .cpu_write(cpu_write), .cpu_address(cpu_address), .cpu_data(cpu_data),
        .cpu_mask(cpu_mask), .cpu_ready(cpu_ready), .cpu_response(cpu_response), .client_rdata(client_rdata),
        .audio_req(1'b0), .audio_write(1'b0), .audio_address(29'd0), .audio_data(256'd0),
        .audio_ready(), .audio_response(), .music_req(1'b0), .music_write(1'b0),
        .music_address(29'd0), .music_data(256'd0), .music_mask(32'd0), .music_ready(), .music_response(),
        .delay_req(1'b0), .delay_write(1'b0), .delay_address(29'd0), .delay_data(256'd0),
        .delay_ready(), .delay_response(), .app_cmd(app_cmd), .app_en(app_en), .app_addr(app_addr),
        .app_rdy(app_rdy), .app_wdata(app_wdata), .app_wmask(app_wmask), .app_wren(app_wren),
        .app_wend(app_wend), .app_wrdy(app_wrdy), .app_rdata(app_rdata), .app_rvalid(app_rvalid),
        .memory_flags(memory_flags), .push_display_summary(), .push_display_summary_valid(),
        .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
        .tmds_data_p(tmds_data_p), .tmds_data_n(tmds_data_n)
    );
endmodule

module workstation_hdmi_probe_top #(
    parameter integer DYNAMIC = `HDMI_ISOLATION_DYNAMIC
) (
    input wire clk_50m,
    input wire hdmi_hpd,
    inout wire hdmi_cec,
    output wire tmds_clk_p, tmds_clk_n,
    output wire [2:0] tmds_data_p, tmds_data_n,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs, ddr_ras, ddr_cas, ddr_we,
    output wire ddr_ck, ddr_ck_n, ddr_cke, ddr_odt, ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs, ddr_dqs_n
);
    wire reset_n, sample_valid;
    wire signed [31:0] sample_data;
    wire [31:0] output_pcm, trigger_reference, active_voices, status_data;
    wire [2:0] effect_mask;
    wire [5:0] effect_order;
    wire [7:0] memory_flags;
    wire [127:0] video_diagnostics;
    (* syn_preserve = 1 *) reg [14:0] debug_status = 0;
    always @(posedge clk_50m)
        debug_status <= {memory_flags, video_diagnostics[13:8], video_diagnostics[64]};
    reset_release u_reset (.clk(clk_50m), .ext_reset_n(1'b1), .reset_n(reset_n));
    workstation_hdmi_demo #(.DYNAMIC(DYNAMIC)) u_input (
        .clk(clk_50m), .reset_n(reset_n), .sample_valid(sample_valid), .sample_data(sample_data),
        .output_pcm(output_pcm), .trigger_reference(trigger_reference), .active_voices(active_voices),
        .status_data(status_data), .effect_mask(effect_mask), .effect_order(effect_order)
    );
    assign hdmi_cec = 1'bz;
    workstation_hdmi_isolation u_display (
        .clk_50m(clk_50m), .reset_n(reset_n), .hdmi_hpd(hdmi_hpd),
        .sample_data(sample_data), .sample_valid(sample_valid), .output_pcm(output_pcm),
        .trigger_reference(trigger_reference), .active_voices(active_voices), .status_data(status_data),
        .effect_mask(effect_mask), .effect_order(effect_order),
        .ui_pending(1'b0), .ui_visible(1'b0), .ui_next_visible(1'b0),
        .ui_front_base(29'd0), .ui_next_base(29'd0), .ui_frame_commit(),
        .cpu_req(1'b0), .cpu_write(1'b0), .cpu_address(29'd0), .cpu_data(256'd0), .cpu_mask(32'd0),
        .cpu_ready(), .cpu_response(), .client_rdata(), .ui_clk(), .ui_reset_n(),
        .memory_flags(memory_flags), .video_diagnostics(video_diagnostics),
        .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
        .tmds_data_p(tmds_data_p), .tmds_data_n(tmds_data_n),
        .ddr_addr(ddr_addr), .ddr_bank(ddr_bank), .ddr_cs(ddr_cs), .ddr_ras(ddr_ras),
        .ddr_cas(ddr_cas), .ddr_we(ddr_we), .ddr_ck(ddr_ck), .ddr_ck_n(ddr_ck_n),
        .ddr_cke(ddr_cke), .ddr_odt(ddr_odt), .ddr_reset_n(ddr_reset_n),
        .ddr_dm(ddr_dm), .ddr_dq(ddr_dq), .ddr_dqs(ddr_dqs), .ddr_dqs_n(ddr_dqs_n)
    );
endmodule
`default_nettype wire
