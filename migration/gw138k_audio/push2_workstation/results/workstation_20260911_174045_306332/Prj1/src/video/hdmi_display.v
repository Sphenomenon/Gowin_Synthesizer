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
    wire [31:0] underruns,rendered_frames;
    video_runtime_diagnostics u_diagnostics (
        .clk_50m(clk_50m),.reset_n(reset_n),.pixel_clk(pixel_clk),
        .pixel_reset_n(pixel_reset_n),.ui_clk(memory_clk),.ui_reset_n(ui_rst_n),
        .hdmi_hpd(hdmi_hpd),.video_locked(video_locked),
        .scanout_reset_n(pixel_reset_pipe[2]),.serializer_reset(serializer_reset),
        .vblank_start(vblank_start),.rendered_frames(rendered_frames),
        .underruns(underruns),.diagnostics(video_diagnostics)
    );
    wire [31:0] memory_status={24'd0,video_locked,memory_pll_locked,(underruns!=0),(fetch_fault || arbiter_fault),
                              front_valid,bist_failed,bist_done,memory_calibrated};
    reg [7:0] flags_meta,flags_sync;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin flags_meta<=0;flags_sync<=0;end
        else begin flags_meta<=memory_status[7:0];flags_sync<=flags_meta;end
    end
    assign memory_flags=flags_sync;
    feedback_renderer #(.ENABLE_ANALYSIS(1)) u_renderer (
        .clk(memory_clk),.rst_n(ui_rst_n),.start(renderer_start),.frame_ready(renderer_ready),
        .busy(renderer_busy),.frame_done(renderer_done),.pixel_valid(pixel_valid),
        .pixel_ready(pixel_ready),.pixel_data(pixel_data),.source_clk(clk_50m),
        .source_reset_n(source_reset_pipe[2]),.sample_data(sample_data),.sample_valid(sample_valid),
        .output_pcm(output_pcm),
        .trigger_reference(trigger_reference),
        .active_voices(active_voices),.status_data(status_data),.effect_mask(effect_mask),.memory_status(memory_status),
        .underruns(underruns),.frame_count(rendered_frames)
    );
    wire write_req,write_ready,read_req,read_ready;
    wire [28:0] write_addr,read_addr;
    wire [255:0] write_data;
    ddr_frame_writer u_writer (
        .clk(memory_clk),.rst_n(ui_rst_n),.enabled(display_enabled),
        .front_bank(analysis_bank),.frame_swap(analysis_commit),.renderer_ready(renderer_ready),
        .renderer_done(renderer_done),.renderer_start(renderer_start),.pixel_valid(pixel_valid),
        .pixel_ready(pixel_ready),.pixel_data(pixel_data),.req_valid(write_req),
        .req_ready(write_ready),.req_addr(write_addr),.req_wdata(write_data),
        .frame_pending(frame_pending),.rendered_frames(rendered_frames)
    );
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
        .writer_valid(write_req),.writer_address(write_addr),.writer_data(write_data),.writer_ready(write_ready),
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
