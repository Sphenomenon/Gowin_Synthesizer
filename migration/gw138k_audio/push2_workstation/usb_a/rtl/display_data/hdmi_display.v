`default_nettype none
// Audio observation -> DDR RGB565 back buffer -> tagged scan lines -> 1080p60.
// Audio never waits for video, calibration or memory.
module hdmi_display (
    input wire clk_50m, reset_n,
    input wire hdmi_hpd,
    output wire [127:0] video_diagnostics,
    input wire signed [31:0] sample_data,
    input wire sample_valid,
    input wire [31:0] output_pcm,
    input wire [31:0] trigger_reference,
    input wire [31:0] active_voices, status_data,
    input wire [2:0] effect_mask,
    input wire [5:0] effect_order,
    input wire memory_clk, memory_reset_n, memory_calibrated, memory_pll_locked,
    input wire ui_pending,ui_visible,ui_next_visible,
    input wire [28:0] ui_front_base,ui_next_base,
    output wire ui_frame_commit,
    input wire cpu_req,cpu_write,
    input wire [28:0] cpu_address,
    input wire [255:0] cpu_data,
    input wire [31:0] cpu_mask,
    output wire cpu_ready,cpu_response,
    output wire [2:0] app_cmd,
    output wire app_en,
    output wire [28:0] app_addr,
    input wire app_rdy,
    output wire [255:0] app_wdata,
    output wire [31:0] app_wmask,
    output wire app_wren,app_wend,
    input wire app_wrdy,
    input wire [255:0] app_rdata,
    input wire app_rvalid,
    output wire [7:0] memory_flags,
    output wire tmds_clk_p,tmds_clk_n,
    output wire [2:0] tmds_data_p,tmds_data_n
);
    wire pixel_clk,serial_clk,pixel_reset_n,video_source_reset_n,video_locked,serializer_reset_n,serializer_reset;
    video_clock_1080p u_clock (
        .clk_50m(clk_50m),.reset_n(reset_n),.pixel_clk(pixel_clk),.serial_clk(serial_clk),
        .pixel_reset_n(pixel_reset_n),.serializer_reset_n(serializer_reset_n),
        .serializer_reset(serializer_reset),
        .video_source_reset_n(video_source_reset_n),.pll_locked(video_locked)
    );
    wire [11:0] x;
    wire [10:0] y;
    wire de,hs,vs,frame_start,line_start,vblank_start;
    video_timing_1080p u_timing (
        .pixel_clk(pixel_clk),.reset_n(pixel_reset_n),.pixel_x(x),.pixel_y(y),
        .data_enable(de),.hsync(hs),.vsync(vs),.frame_start(frame_start),
        .line_start(line_start),.vblank_start(vblank_start)
    );
    // All cross-domain handshakes assert reset together on DDR/video lock loss.
    wire shared_release=reset_n && memory_reset_n && video_source_reset_n;
    reg [2:0] ui_reset_pipe,source_reset_pipe,pixel_reset_pipe;
    always @(posedge memory_clk or negedge shared_release)
        if(!shared_release) ui_reset_pipe<=0; else ui_reset_pipe<={ui_reset_pipe[1:0],1'b1};
    always @(posedge clk_50m or negedge shared_release)
        if(!shared_release) source_reset_pipe<=0; else source_reset_pipe<={source_reset_pipe[1:0],1'b1};
    always @(posedge pixel_clk or negedge shared_release)
        if(!shared_release) pixel_reset_pipe<=0; else pixel_reset_pipe<={pixel_reset_pipe[1:0],1'b1};
    wire ui_rst_n=ui_reset_pipe[2];
    wire bist_req,bist_ready,bist_write,bist_done,bist_failed;
    wire bist_response,scan_response,arbiter_fault;
    wire [28:0] bist_addr,bist_first_error;
    wire [255:0] bist_data;
    wire [31:0] bist_errors;
    ddr3_bist u_bist (
        .clk(memory_clk),.rst_n(ui_rst_n),.req_valid(bist_req),.req_ready(bist_ready),
        .req_write(bist_write),.req_addr(bist_addr),.req_wdata(bist_data),
        .rsp_valid(bist_response),.rsp_data(app_rdata),
        .done(bist_done),.failed(bist_failed),.error_count(bist_errors),.first_error_addr(bist_first_error)
    );
    wire fetch_fault,front_bank,front_valid,frame_pending,frame_swap;
    wire analysis_bank,analysis_commit,frame_available;
    wire [28:0] selected_base,selected_analysis_base;
    wire composite;
    gw138k_view_select u_view(.clk(memory_clk),.reset_n(ui_rst_n),.frame_swap(frame_swap),
        .analysis_pending(frame_pending),.ui_pending(ui_pending),.ui_visible(ui_visible),
        .ui_next_visible(ui_next_visible),.ui_front_base(ui_front_base),.ui_next_base(ui_next_base),
        .analysis_bank(analysis_bank),.analysis_commit(analysis_commit),.ui_commit(ui_frame_commit),
        .frame_available(frame_available),.selected_base(selected_base),
        .composite(composite),.selected_analysis_base(selected_analysis_base));
    wire display_enabled=bist_done && !bist_failed && !fetch_fault && !arbiter_fault;
    wire renderer_ready,renderer_busy,renderer_done,renderer_start,pixel_valid,pixel_ready;
    wire [63:0] pixel_data;
    wire [255:0] display_meta,shared_export_meta;
    wire [31:0] underruns,rendered_frames;
    wire shared_start,shared_write_done,shared_busy,shared_initialized,shared_read_enable;
    wire [1:0] shared_read_kind;
    wire [15:0] shared_read_addr;
    wire [31:0] shared_read_data,shared_analysis_sequence,shared_analysis_skipped,shared_stereo_peaks;
    wire shared_analysis_valid;
    wire [2:0] shared_image_gain;
    wire shared_req,shared_ready;
    wire [28:0] shared_addr;
    wire [255:0] shared_data;
    wire shared_load_req,shared_load_ready,shared_load_response;
    wire [28:0] shared_load_addr;
    wire shared_load_busy,shared_load_done,shared_load_valid,shared_load_fault;
    wire shared_render_read_enable,shared_render_image_hit,shared_render_analysis_valid;
    wire [8:0] shared_render_wave_addr,shared_render_spectrum_column;
    wire [15:0] shared_render_image_addr;
    wire [31:0] shared_render_wave_data,shared_render_analysis_sequence,shared_render_analysis_skipped;
    wire [31:0] shared_render_stereo_peaks,shared_render_frame_sequence;
    wire [7:0] shared_render_spectrum_left,shared_render_spectrum_right;
    wire [2:0] shared_render_image_gain;
    wire [255:0] shared_render_meta;
    video_runtime_diagnostics u_diagnostics (
        .clk_50m(clk_50m),.reset_n(reset_n),.pixel_clk(pixel_clk),
        .pixel_reset_n(pixel_reset_n),.ui_clk(memory_clk),.ui_reset_n(ui_rst_n),
        .hdmi_hpd(hdmi_hpd),.video_locked(video_locked),
        .scanout_reset_n(pixel_reset_pipe[2]),.serializer_reset(serializer_reset),
        .vblank_start(vblank_start),.rendered_frames(rendered_frames),
        .underruns(underruns),.diagnostics(video_diagnostics)
    );
    wire [31:0] memory_status={24'd0,video_locked,memory_pll_locked,(underruns!=0),(fetch_fault || arbiter_fault || shared_load_fault),
                              front_valid,bist_failed,bist_done,memory_calibrated};
    reg [7:0] flags_meta,flags_sync;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin flags_meta<=0;flags_sync<=0;end
        else begin flags_meta<=memory_status[7:0];flags_sync<=flags_meta;end
    end
    assign memory_flags=flags_sync;
    feedback_renderer #(.ENABLE_ANALYSIS(1),.SHARED_EXPORT(1),.SHARED_RENDER(1),.SHARED_WAVE_ZERO_BITS(15)) u_renderer (
        .clk(memory_clk),.rst_n(ui_rst_n),.start(renderer_start),.frame_ready(renderer_ready),
        .busy(renderer_busy),.frame_done(renderer_done),.pixel_valid(pixel_valid),
        .pixel_ready(pixel_ready),.pixel_data(pixel_data),.display_meta(display_meta),.shared_export_meta(shared_export_meta),.source_clk(clk_50m),
        .source_reset_n(source_reset_pipe[2]),.sample_data(sample_data),.sample_valid(sample_valid),
        .output_pcm(output_pcm),
        .trigger_reference(trigger_reference),
        .active_voices(active_voices),.status_data(status_data),.effect_mask(effect_mask),.effect_order(effect_order),.memory_status(memory_status),
        .underruns(underruns),.frame_count(rendered_frames),
        .shared_start(shared_start),.shared_done(shared_load_done),
        .shared_read_enable(shared_read_enable),.shared_read_kind(shared_read_kind),
        .shared_read_addr(shared_read_addr),.shared_read_data(shared_read_data),
        .shared_analysis_sequence(shared_analysis_sequence),.shared_analysis_skipped(shared_analysis_skipped),
        .shared_analysis_valid(shared_analysis_valid),.shared_image_gain(shared_image_gain),
        .shared_stereo_peaks(shared_stereo_peaks),
        .shared_render_read_enable(shared_render_read_enable),.shared_render_wave_addr(shared_render_wave_addr),
        .shared_render_image_addr(shared_render_image_addr),.shared_render_spectrum_column(shared_render_spectrum_column),
        .shared_render_wave_data(shared_render_wave_data),.shared_render_image_hit(shared_render_image_hit),
        .shared_render_spectrum_left(shared_render_spectrum_left),.shared_render_spectrum_right(shared_render_spectrum_right),
        .shared_render_meta(shared_render_meta),.shared_render_analysis_sequence(shared_render_analysis_sequence),
        .shared_render_analysis_skipped(shared_render_analysis_skipped),.shared_render_stereo_peaks(shared_render_stereo_peaks),
        .shared_render_image_gain(shared_render_image_gain),.shared_render_analysis_valid(shared_render_analysis_valid)
    );
    wire write_req,write_ready,read_req,read_ready;
    wire [28:0] write_addr,read_addr;
    wire [255:0] write_data;
    ddr_frame_writer u_writer (
        .clk(memory_clk),.rst_n(ui_rst_n),.enabled(display_enabled),
        // A ready waveform must not start a new raster while the previous
        // P5 commit is still waiting for DDR acceptance.
        .front_bank(analysis_bank),.frame_swap(analysis_commit),.renderer_ready(renderer_ready && shared_initialized && !write_req),
        .renderer_done(renderer_done),.renderer_start(renderer_start),.pixel_valid(pixel_valid),
        .pixel_ready(pixel_ready),.pixel_data(pixel_data),.display_meta(display_meta),.req_valid(write_req),
        .req_ready(write_ready),.req_addr(write_addr),.req_wdata(write_data),
        .frame_pending(frame_pending),.rendered_frames(rendered_frames)
    );
    display_data_writer u_data_writer(
        .clk(memory_clk),.rst_n(ui_rst_n),.enabled(display_enabled),.start(shared_start),
        .effect_meta(shared_export_meta),.analysis_sequence(shared_analysis_sequence),
        .analysis_skipped(shared_analysis_skipped),.analysis_valid(shared_analysis_valid),
        .image_gain(shared_image_gain),.stereo_peaks(shared_stereo_peaks),
        .busy(shared_busy),.done(shared_write_done),.initialized(shared_initialized),
        .req_valid(shared_req),.req_ready(shared_ready),.req_addr(shared_addr),.req_wdata(shared_data),
        .read_enable(shared_read_enable),.read_kind(shared_read_kind),.read_addr(shared_read_addr),.read_data(shared_read_data));
    display_data_reader u_data_reader(
        .clk(memory_clk),.rst_n(ui_rst_n),.enabled(display_enabled),.start(shared_write_done),
        .busy(shared_load_busy),.done(shared_load_done),.valid(shared_load_valid),.fault(shared_load_fault),
        .req_valid(shared_load_req),.req_ready(shared_load_ready),.req_addr(shared_load_addr),
        .rsp_valid(shared_load_response),.rsp_data(app_rdata),
        .render_read_enable(shared_render_read_enable),.render_wave_addr(shared_render_wave_addr),
        .render_image_addr(shared_render_image_addr),.render_spectrum_column(shared_render_spectrum_column),
        .render_wave_data(shared_render_wave_data),.render_image_hit(shared_render_image_hit),
        .render_spectrum_left(shared_render_spectrum_left),.render_spectrum_right(shared_render_spectrum_right),
        .render_meta(shared_render_meta),.render_analysis_sequence(shared_render_analysis_sequence),
        .render_analysis_skipped(shared_render_analysis_skipped),.render_stereo_peaks(shared_render_stereo_peaks),
        .render_image_gain(shared_render_image_gain),.render_analysis_valid(shared_render_analysis_valid),
        .render_frame_sequence(shared_render_frame_sequence));
    wire merged_req,merged_ready;
    wire [28:0] merged_addr;
    wire [255:0] merged_data;
    // Export and coherent reload finish before raster pixels issue. The scanout
    // remains first-priority and audio never enters this DDR clock domain.
    display_write_bridge u_write_bridge(
        .clk(memory_clk),.rst_n(ui_rst_n),
        .shared_valid(shared_req),.shared_addr(shared_addr),.shared_data(shared_data),.shared_ready(shared_ready),
        .frame_valid(write_req),.frame_addr(write_addr),.frame_data(write_data),.frame_ready(write_ready),
        .req_valid(merged_req),.req_addr(merged_addr),.req_data(merged_data),.req_ready(merged_ready));
    wire [23:0] rgb;
    wire scan_de,scan_hs,scan_vs;
    video_ddr_scanout #(.EXPLICIT_BASE(1)) u_scanout (
        .clk(memory_clk),.rst_n(ui_rst_n),.enabled(display_enabled),
        .new_frame_pending(frame_available),.new_frame_base(selected_base),
        .new_composite(composite),.new_analysis_base(selected_analysis_base),.frame_swap(frame_swap),.front_bank(front_bank),.front_valid(front_valid),
        .req_valid(read_req),.req_ready(read_ready),.req_addr(read_addr),
        .rsp_valid(scan_response),.rsp_data(app_rdata),.fetch_fault(fetch_fault),.underruns(underruns),
        .pixel_clk(pixel_clk),.pixel_rst_n(pixel_reset_pipe[2]),.pixel_x(x),.pixel_y(y),
        .data_enable(de),.hsync(hs),.vsync(vs),.vblank_start(vblank_start),
        .rgb(rgb),.out_de(scan_de),.out_hsync(scan_hs),.out_vsync(scan_vs)
    );
    gw138k_ddr_arbiter u_arbiter(.clk(memory_clk),.reset_n(ui_rst_n),.bist_done(bist_done),
        .bist_valid(bist_req),.bist_write(bist_write),.bist_address(bist_addr),.bist_data(bist_data),
        .bist_ready(bist_ready),.bist_response(bist_response),
        .scan_valid(read_req),.scan_address(read_addr),.scan_ready(read_ready),.scan_response(scan_response),
        .display_valid(shared_load_req),.display_address(shared_load_addr),
        .display_ready(shared_load_ready),.display_response(shared_load_response),
        .writer_valid(merged_req),.writer_address(merged_addr),
        .writer_data(merged_data),.writer_ready(merged_ready),
        .cpu_valid(cpu_req),.cpu_write(cpu_write),.cpu_address(cpu_address),.cpu_data(cpu_data),.cpu_mask(cpu_mask),
        .cpu_ready(cpu_ready),.cpu_response(cpu_response),
        .app_cmd(app_cmd),.app_en(app_en),.app_wren(app_wren),.app_wend(app_wend),
        .app_address(app_addr),.app_data(app_wdata),.app_mask(app_wmask),
        .app_ready(app_rdy),.app_write_ready(app_wrdy),.app_response(app_rvalid),.response_fault(arbiter_fault));
    // Preserve a valid black 1080p raster even while DDR is uncalibrated.
    // This delay matches scanout's two pixel-clock stages.
    reg [1:0] fallback_de,fallback_hs,fallback_vs;
    always @(posedge pixel_clk or negedge pixel_reset_n) begin
        if(!pixel_reset_n) begin fallback_de<=0;fallback_hs<=0;fallback_vs<=0;end
        else begin fallback_de<={fallback_de[0],de};fallback_hs<={fallback_hs[0],hs};fallback_vs<={fallback_vs[0],vs};end
    end
    wire scanning=pixel_reset_pipe[2];
    dvi_tx_top u_dvi (
        .pixel_clock(pixel_clk),.ddr_bit_clock(serial_clk),.reset(!pixel_reset_n),
        .serializer_reset(serializer_reset),
        .den(scanning ? scan_de : fallback_de[1]),
        .hsync(scanning ? scan_hs : fallback_hs[1]),
        .vsync(scanning ? scan_vs : fallback_vs[1]),.pixel_data(scanning ? rgb : 24'd0),
        .tmds_clk({tmds_clk_p,tmds_clk_n}),.tmds_d0({tmds_data_p[0],tmds_data_n[0]}),
        .tmds_d1({tmds_data_p[1],tmds_data_n[1]}),.tmds_d2({tmds_data_p[2],tmds_data_n[2]})
    );
endmodule
`default_nettype wire
