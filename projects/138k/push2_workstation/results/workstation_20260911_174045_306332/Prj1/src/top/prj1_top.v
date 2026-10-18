// Tang Mega 138K / NEO Dock 31005. Pin details: docs/hardware.md.
// Peripheral transport widths are confined to adapters; audio/control use 32-bit words.
module prj1_top (
    input wire clk_50m,
    input wire button1_n,
    input wire uart_rx,
    output wire uart_tx,
    output wire hp_bck,
    output wire hp_ws,
    output wire hp_din,
    output wire pa_en,
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
    reset_release u_reset (.clk(clk_50m), .ext_reset_n(button1_n), .reset_n(reset_n));

    // One 50MHz timebase spans UART, synth and physical audio serializer.
    reg [31:0] latency_cycles;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) latency_cycles <= 0;
        else latency_cycles <= latency_cycles + 1'b1;
    end
    wire [511:0] latency_diagnostics;
    wire onset_query_request, onset_query_done;
    wire [4:0] onset_query_voice;
    wire [255:0] onset_query_data;
    wire trace_packet_valid, trace_ack_ready, trace_ack_done;
    wire [31:0] trace_packet_header, trace_packet_start, trace_packet_end;
    wire [31:0] trace_ack_header, trace_ack_ready_time, trace_ack_done_header, trace_ack_done_time;
    wire trace_commit, trace_frame_start, trace_sample_event, trace_dac_done;
    wire [31:0] trace_header, trace_nonzero_voices, sample_nonzero_voices, trace_dac_nonzero_voices;
    wire [23:0] trace_revision, trace_sample_revision, trace_dac_revision;
    wire [31:0] cmd_data, rsp_data, uart_errors;
    wire cmd_valid, cmd_ready, cmd_first, cmd_last, rsp_valid, rsp_ready;
    uart_control u_uart (
        .clk(clk_50m), .rst_n(reset_n), .uart_rx(uart_rx), .uart_tx(uart_tx),
        .cmd_data(cmd_data), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .cmd_first(cmd_first), .cmd_last(cmd_last),
        .rsp_data(rsp_data), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .error_count(uart_errors),.time_cycles(latency_cycles),
        .trace_packet_valid(trace_packet_valid),.trace_packet_header(trace_packet_header),
        .trace_packet_start(trace_packet_start),.trace_packet_end(trace_packet_end),
        .trace_ack_ready(trace_ack_ready),.trace_ack_header(trace_ack_header),
        .trace_ack_ready_time(trace_ack_ready_time),.trace_ack_done(trace_ack_done),
        .trace_ack_done_header(trace_ack_done_header),.trace_ack_done_time(trace_ack_done_time)
    );

    wire sample_tick, sample_valid;
    wire signed [31:0] sample_data;
    wire [31:0] active_voices, underrun_count, frame_count;
    wire [31:0] trigger_reference;
    wire signed [39:0] mix_sum;
    wire voice_sample_event;
    wire signed [31:0] voice_sample_data;
    wire [4:0] voice_sample_index;
    wire [31:0] master_volume,lr_balance;
    wire [7:0] memory_flags;
    wire [127:0] video_diagnostics;
    synth_engine #(.VOICE_COUNT(32)) u_synth (
        .clk(clk_50m), .rst_n(reset_n), .sample_tick(sample_tick),
        .cmd_data(cmd_data), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready),
        .cmd_first(cmd_first), .cmd_last(cmd_last),
        .rsp_data(rsp_data), .rsp_valid(rsp_valid), .rsp_ready(rsp_ready),
        .sample_data(sample_data), .sample_valid(sample_valid), .active_voices(active_voices),
        .trigger_reference(trigger_reference),
        .memory_flags(memory_flags),.video_diagnostics(video_diagnostics),
        .latency_diagnostics(latency_diagnostics),.trace_commit(trace_commit),.trace_header(trace_header),
        .onset_query_request(onset_query_request),.onset_query_voice(onset_query_voice),
        .onset_query_done(onset_query_done),.onset_query_data(onset_query_data),
        .trace_revision(trace_revision),.trace_frame_start(trace_frame_start),
        .trace_sample_event(),.trace_sample_revision(),.trace_nonzero_voices(),.sample_nonzero_voices(),
        .mix_sum(mix_sum),.voice_sample_event(voice_sample_event),.voice_sample_data(voice_sample_data),
        .voice_sample_index(voice_sample_index),.master_volume(master_volume),.lr_balance(lr_balance)
    );

    wire signed [31:0] final_left,final_right;
    wire final_valid;
    wire [31:0] final_reference;
    audio_output_stage u_output_gain(
        .clk(clk_50m),.reset_n(reset_n),.frame_start(trace_frame_start),
        .master_target(master_volume),.balance_target(lr_balance),.mix_sum(mix_sum),
        .mix_valid(sample_valid),.mix_reference(trigger_reference),
        .voice_sample_event(voice_sample_event),.voice_sample_data(voice_sample_data),.voice_sample_index(voice_sample_index),
        .sample_left(final_left),.sample_right(final_right),.sample_valid(final_valid),
        .sample_reference(final_reference),.sample_nonzero_voices(sample_nonzero_voices),
        .trace_sample_event(trace_sample_event),.trace_sample_revision(trace_sample_revision),.trace_nonzero_voices(trace_nonzero_voices));

    wire [31:0] dac_frame_reference, output_pcm, output_reference;
    wire output_sample_valid;
    wire signed [16:0] output_mid_pcm=$signed({output_pcm[31],output_pcm[31:16]})+
                                            $signed({output_pcm[15],output_pcm[15:0]});
    wire signed [31:0] output_mid={output_mid_pcm,15'd0};
    pt8211_tx #(.STEREO_ENABLE(1)) u_audio (
        .clk(clk_50m), .reset_n(reset_n), .sample_data(final_left),.sample_right(final_right),.sample_valid(final_valid),
        .sample_tick(sample_tick), .hp_bck(hp_bck), .hp_ws(hp_ws), .hp_din(hp_din),
        .pa_en(pa_en), .underrun_count(underrun_count), .frame_count(frame_count),
        .sample_revision(final_reference[31:8]),.sample_nonzero_voices(sample_nonzero_voices),
        .trace_dac_done(trace_dac_done),.trace_dac_revision(trace_dac_revision),
        .trace_dac_nonzero_voices(trace_dac_nonzero_voices),
        .sample_trigger_reference(final_reference),.frame_trigger_reference(dac_frame_reference)
    );
    pt8211_observer u_output_observer(
        .clk(clk_50m),.reset_n(reset_n),.bck(hp_bck),.ws(hp_ws),.din(hp_din),
        .frame_reference(dac_frame_reference),.pcm_pair(output_pcm),
        .sample_valid(output_sample_valid),.trigger_reference(output_reference));

    audio_latency_monitor u_latency (
        .clk(clk_50m),.rst_n(reset_n),.time_cycles(latency_cycles),
        .packet_valid(trace_packet_valid),.packet_header(trace_packet_header),
        .packet_start(trace_packet_start),.packet_end(trace_packet_end),
        .command_commit(trace_commit),.command_header(trace_header),.command_revision(trace_revision),
        .frame_start(trace_frame_start),.sample_event(trace_sample_event),
        .sample_revision(trace_sample_revision),.nonzero_voices(trace_nonzero_voices),
        .dac_done(trace_dac_done),.dac_revision(trace_dac_revision),
        .dac_nonzero_voices(trace_dac_nonzero_voices),
        .ack_ready(trace_ack_ready),.ack_header(trace_ack_header),.ack_ready_time(trace_ack_ready_time),
        .ack_done(trace_ack_done),.ack_done_header(trace_ack_done_header),.ack_done_time(trace_ack_done_time),
        .diagnostics(latency_diagnostics));

    voice_onset_monitor u_voice_onset (
        .clk(clk_50m),.rst_n(reset_n),.time_cycles(latency_cycles),
        .command_commit(trace_commit),.command_header(trace_header),
        .command_revision(trace_revision),.command_active_voices(active_voices),
        .sample_event(trace_sample_event),.sample_revision(trace_sample_revision),
        .nonzero_voices(trace_nonzero_voices),.dac_done(trace_dac_done),
        .dac_revision(trace_dac_revision),.dac_nonzero_voices(trace_dac_nonzero_voices),
        .dac_muted(pa_en),.query_request(onset_query_request),.query_voice(onset_query_voice),
        .query_done(onset_query_done),.query_data(onset_query_data));

    // Diagnostics are latched by video CDC. Low half UART errors, high half underruns.
    wire [31:0] display_status = {underrun_count[15:0], uart_errors[15:0]};
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
