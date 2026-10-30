`default_nettype none

// Raster producer for a DDR back buffer: even-x pixel in bits31:0, following
// pixel in bits63:32, RGB888 in each low24. One beat per cycle after startup.
// All metadata and the audio RAM bank remain fixed until the last accepted
// beat. WIDTH must be even; WIDTH/HEIGHT can be reduced for protocol tests.
module feedback_renderer #(
    parameter integer WIDTH = 1920,
    parameter integer HEIGHT = 1080,
    parameter integer ENABLE_ANALYSIS = 0,
    parameter integer SHARED_EXPORT = 0,
    parameter integer SHARED_RENDER = 0,
    parameter integer SHARED_WAVE_ZERO_BITS = 0,
    parameter integer SCALE_THREE_HALVES = 0,
    // Shared snapshots can render analysis without instantiating a local FFT.
    // Inherit the historical selection unless a composition opts in explicitly.
    parameter integer RENDER_ANALYSIS = ENABLE_ANALYSIS
) (
    input wire clk,
    input wire rst_n,
    input wire start,
    output wire frame_ready,
    output reg busy,
    output reg frame_done,
    output wire pixel_valid,
    input wire pixel_ready,
    output wire [63:0] pixel_data,
    output wire [255:0] display_meta,
    output wire [255:0] shared_export_meta,
    input wire source_clk,
    input wire source_reset_n,
    input wire [31:0] sample_data,
    input wire sample_valid,
    input wire [31:0] output_pcm,
    input wire [31:0] trigger_reference,
    input wire [31:0] active_voices,
    input wire [31:0] status_data,
    input wire [2:0] effect_mask,
    input wire [5:0] effect_order,
    input wire [31:0] memory_status,
    input wire [31:0] underruns,
    input wire [31:0] frame_count,
    input wire shared_done,
    input wire shared_read_enable,
    input wire [1:0] shared_read_kind,
    input wire [15:0] shared_read_addr,
    output wire [31:0] shared_read_data,
    output wire shared_start,
    output wire [31:0] shared_analysis_sequence, shared_analysis_skipped,
    output wire shared_analysis_valid,
    output wire [2:0] shared_image_gain,
    output wire [31:0] shared_stereo_peaks,
    output wire shared_render_read_enable,
    output wire [8:0] shared_render_wave_addr,
    output wire [15:0] shared_render_image_addr,
    output wire [8:0] shared_render_spectrum_column,
    input wire [31:0] shared_render_wave_data,
    input wire shared_render_image_hit,
    input wire [7:0] shared_render_spectrum_left,shared_render_spectrum_right,
    input wire [255:0] shared_render_meta,
    input wire [31:0] shared_render_analysis_sequence,shared_render_analysis_skipped,
    input wire [31:0] shared_render_stereo_peaks,
    input wire [2:0] shared_render_image_gain,
    input wire shared_render_analysis_valid
);
    wire snapshot_ready;
    wire [31:0] snapshot_peak, snapshot_voices, snapshot_status;
    wire [31:0] snapshot_sequence, snapshot_skipped, wave_data;
    wire [31:0] snapshot_revision, capture_data;
    wire alignment_busy, alignment_done, waveform_held, capture_read_enable;
    wire [8:0] capture_read_addr;
    reg aligned_ready;
    reg [10:0] issue_x, issue_y, read_x, read_y;
    reg [10:0] a_x, a_y, b_x, b_y, c_x, c_y, output_x, output_y;
    reg [4:0] valid_pipe, last_pipe;
    reg all_issued;
    reg exporting;
    assign shared_start=SHARED_EXPORT && start && frame_ready;
    reg [31:0] frame_memory_status, frame_underruns, frame_framecount;
    reg [2:0] frame_effect_mask;
    reg [5:0] frame_effect_order;
    reg [31:0] previous_wave_data;
    wire use_shared_render=(SHARED_RENDER!=0);
    wire pipeline_enable = !pixel_valid || pixel_ready;
    wire advance = busy && !exporting && !all_issued && pipeline_enable;
    wire final_accept = pixel_valid && pixel_ready && last_pipe[4];
    assign pixel_valid = valid_pipe[4];
    // Eight-word DDR record shared by HDMI, Push and future display adapters.
    // The raster remains the compatibility view; consumers can use this compact
    // packet without decoding the full framebuffer.
    wire [255:0] local_display_meta={32'h44495350, {23'd0,frame_effect_order,frame_effect_mask}, snapshot_peak, snapshot_voices, snapshot_status, snapshot_sequence, snapshot_skipped, frame_memory_status};
    assign shared_export_meta=local_display_meta;
    assign display_meta=use_shared_render ? shared_render_meta : local_display_meta;
    wire [10:0] canvas_x = SCALE_THREE_HALVES ? issue_x + (issue_x >> 1) : issue_x;
    wire [10:0] canvas_y = SCALE_THREE_HALVES ? issue_y + (issue_y >> 1) : issue_y;
    wire [10:0] wave_offset = canvas_x-11'd64;
    wire [8:0] wave_addr = canvas_x >= 64 && canvas_x < 1088 ? wave_offset[9:1] : 9'b0;
    wire analysis_ready,image_hit;
    wire [7:0] spectrum_left,spectrum_right;
    wire [15:0] peak_left,peak_right;
    wire [2:0] image_gain;
    wire [31:0] analysis_sequence,analysis_skipped;
    wire [10:0] next_x=advance ? (issue_x==WIDTH-2 ? 11'd0 : issue_x+11'd2) : issue_x;
    wire [10:0] next_canvas_x=SCALE_THREE_HALVES ? next_x + (next_x >> 1) : next_x;
    wire [10:0] spectrum_offset=next_canvas_x-11'd64;
    wire [8:0] spectrum_column=next_canvas_x>=64 && next_canvas_x<1088 ? spectrum_offset[9:1] : 9'd0;
    wire [10:0] image_x=canvas_x-11'd1248, image_y=canvas_y-11'd224;
    wire export_read=SHARED_EXPORT && exporting && shared_read_enable;
    wire local_render_read=(SHARED_RENDER==0) && advance;
    wire [8:0] read_column=exporting ? shared_read_addr[8:0] : spectrum_column;
    wire [15:0] read_image=exporting ? shared_read_addr : {image_y[8:1],image_x[8:1]};
    assign shared_analysis_sequence=analysis_sequence;
    assign shared_analysis_skipped=analysis_skipped;
    assign shared_image_gain=image_gain;
    assign shared_stereo_peaks={peak_left,peak_right};
    assign shared_render_read_enable=use_shared_render && advance;
    assign shared_render_wave_addr=wave_addr;
    assign shared_render_image_addr={image_y[8:1],image_x[8:1]};
    assign shared_render_spectrum_column=spectrum_column;
    // The HDMI source is (DAC left16 + right16) << 15. Preserve its exact
    // Q1.31 value without making constant-zero RAM bits observable to synthesis.
    wire [31:0] shared_wave_data=(wave_data >> SHARED_WAVE_ZERO_BITS) << SHARED_WAVE_ZERO_BITS;
    assign shared_read_data=shared_read_kind==0 ? shared_wave_data :
        shared_read_kind==1 ? {31'd0,image_hit} : {16'd0,spectrum_right,spectrum_left};
    generate if(ENABLE_ANALYSIS) begin : g_analysis
        output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1)) u_analysis(.clk(clk),.reset_n(rst_n),
            .source_clk(source_clk),.source_reset_n(source_reset_n),.pcm_pair(output_pcm),.sample_valid(sample_valid),
            .release_frame(start && frame_ready && analysis_ready),.ready(analysis_ready),.peak_left(peak_left),.peak_right(peak_right),
            .image_gain(image_gain),.sequence_data(analysis_sequence),.skipped_data(analysis_skipped),
            .display_read_enable(local_render_read || export_read),.spectrum_column(read_column),.image_addr(read_image),
            .spectrum_left(spectrum_left),.spectrum_right(spectrum_right),.image_hit(image_hit),.display_valid(shared_analysis_valid));
    end else begin : g_no_analysis
        assign shared_analysis_valid=1'b0;
        assign analysis_ready=1'b1; assign peak_left=0; assign peak_right=0;
        assign image_gain=0; assign analysis_sequence=0; assign analysis_skipped=0;
        assign spectrum_left=0; assign spectrum_right=0; assign image_hit=0;
    end endgenerate
    assign frame_ready = snapshot_ready && aligned_ready && !busy;
    feedback_capture #(.INPUT_REGISTERED(1),.CAPTURE_SAMPLES(512),.TRIGGER_TIMEOUT_SAMPLES(8192),.SMOOTH_TRIGGER(1)) u_capture (
        .source_clk(source_clk), .source_reset_n(source_reset_n),
        .sample_data(sample_data), .sample_valid(sample_valid),
        .trigger_reference(trigger_reference),
        .active_voices(active_voices), .status_data(status_data),
        .render_clk(clk), .render_reset_n(rst_n),
        .snapshot_ready(snapshot_ready), .snapshot_release(final_accept),
        .snapshot_peak(snapshot_peak), .snapshot_voices(snapshot_voices),
        .snapshot_status(snapshot_status), .snapshot_sequence(snapshot_sequence),
        .snapshot_skipped(snapshot_skipped), .snapshot_revision(snapshot_revision),
        .wave_read_enable(capture_read_enable),
        .wave_read_addr(capture_read_addr), .wave_read_data(capture_data)
    );
    feedback_wave_align u_align (
        .clk(clk), .reset_n(rst_n),
        .start(snapshot_ready && !busy && !aligned_ready && !alignment_busy && !alignment_done),
        .snapshot_revision(snapshot_revision), .snapshot_peak(snapshot_peak),
        .busy(alignment_busy), .done(alignment_done), .waveform_held(waveform_held),
        .capture_read_enable(capture_read_enable), .capture_read_addr(capture_read_addr),
        .capture_read_data(capture_data), .wave_read_enable(local_render_read || export_read),
        .wave_read_addr(exporting ? shared_read_addr[8:0] : wave_addr), .wave_read_data(wave_data)
    );
    wire [31:0] render_wave_data=use_shared_render ? shared_render_wave_data : wave_data;
    wire render_image_hit=use_shared_render ? shared_render_analysis_valid && shared_render_image_hit : image_hit;
    wire [7:0] render_spectrum_left=use_shared_render ? (shared_render_analysis_valid ? shared_render_spectrum_left : 8'd0) : spectrum_left;
    wire [7:0] render_spectrum_right=use_shared_render ? (shared_render_analysis_valid ? shared_render_spectrum_right : 8'd0) : spectrum_right;
    wire [15:0] render_peak_left=use_shared_render ? shared_render_stereo_peaks[31:16] : peak_left;
    wire [15:0] render_peak_right=use_shared_render ? shared_render_stereo_peaks[15:0] : peak_right;
    wire [2:0] render_image_gain=use_shared_render ? shared_render_image_gain : image_gain;
    wire [31:0] render_analysis_sequence=use_shared_render ? shared_render_analysis_sequence : analysis_sequence;
    wire [31:0] render_analysis_skipped=use_shared_render ? shared_render_analysis_skipped : analysis_skipped;
    wire [31:0] render_memory_status=use_shared_render ? shared_render_meta[31:0] : frame_memory_status;
    wire [31:0] render_sequence=use_shared_render ? shared_render_meta[95:64] : snapshot_sequence;
    wire [31:0] render_skipped=use_shared_render ? shared_render_meta[63:32] : snapshot_skipped;
    wire [31:0] render_status=use_shared_render ? shared_render_meta[127:96] : snapshot_status;
    wire [31:0] render_voices=use_shared_render ? shared_render_meta[159:128] : snapshot_voices;
    wire [31:0] render_peak=use_shared_render ? shared_render_meta[191:160] : snapshot_peak;
    wire [2:0] render_effect_mask=use_shared_render ? shared_render_meta[194:192] : frame_effect_mask;
    wire [5:0] render_effect_order=use_shared_render ? shared_render_meta[200:195] : frame_effect_order;
    wire render_waveform_held=use_shared_render ? 1'b0 : waveform_held;
    feedback_dashboard #(.ENABLE_ANALYSIS(RENDER_ANALYSIS)) u_even (
        .clk(clk), .reset_n(rst_n), .enable(pipeline_enable),
        .frame_start(advance && issue_x==0 && issue_y==0),
        .pixel_x(read_x), .pixel_y(read_y), .wave_sample(render_wave_data), .wave_previous(previous_wave_data),
        .peak_data(render_peak), .active_voices(render_voices), .status_data(render_status), .effect_mask(render_effect_mask), .effect_order(render_effect_order),
        .waveform_held(render_waveform_held),
        .spectrum_left(render_spectrum_left),.spectrum_right(render_spectrum_right),.image_hit(render_image_hit),
        .peak_left(render_peak_left),.peak_right(render_peak_right),.image_gain(render_image_gain),
        .analysis_sequence(render_analysis_sequence),.analysis_skipped(render_analysis_skipped),
        .sequence_data(render_sequence), .skipped_data(render_skipped),
        .memory_status(render_memory_status), .underruns(frame_underruns),
        .framecount(frame_framecount), .pixel_data(pixel_data[31:0])
    );
    feedback_dashboard #(.ENABLE_ANALYSIS(RENDER_ANALYSIS)) u_odd (
        .clk(clk), .reset_n(rst_n), .enable(pipeline_enable),
        .frame_start(advance && issue_x==0 && issue_y==0),
        .pixel_x(read_x+11'd1), .pixel_y(read_y), .wave_sample(render_wave_data), .wave_previous(previous_wave_data),
        .peak_data(render_peak), .active_voices(render_voices), .status_data(render_status), .effect_mask(render_effect_mask), .effect_order(render_effect_order),
        .waveform_held(render_waveform_held),
        .spectrum_left(render_spectrum_left),.spectrum_right(render_spectrum_right),.image_hit(render_image_hit),
        .peak_left(render_peak_left),.peak_right(render_peak_right),.image_gain(render_image_gain),
        .analysis_sequence(render_analysis_sequence),.analysis_skipped(render_analysis_skipped),
        .sequence_data(render_sequence), .skipped_data(render_skipped),
        .memory_status(render_memory_status), .underruns(frame_underruns),
        .framecount(frame_framecount), .pixel_data(pixel_data[63:32])
    );
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            exporting <= 0; busy <= 0; frame_done <= 0; valid_pipe <= 0; last_pipe <= 0; all_issued <= 0;
            issue_x <= 0; issue_y <= 0; read_x <= 0; read_y <= 0;
            a_x <= 0; a_y <= 0; b_x <= 0; b_y <= 0; c_x <= 0; c_y <= 0; output_x <= 0; output_y <= 0;
            frame_memory_status <= 0; frame_underruns <= 0; frame_framecount <= 0; frame_effect_mask <= 0; frame_effect_order <= 6'b10_01_00;
            previous_wave_data <= 0;
            aligned_ready <= 0;
        end else begin
            frame_done <= 0;
            if (shared_done) exporting <= 0;
            if (alignment_done) aligned_ready <= 1;
            if (final_accept) aligned_ready <= 0;
            if (start && frame_ready) begin
                exporting <= SHARED_EXPORT!=0;
                busy <= 1; valid_pipe <= 0; last_pipe <= 0; all_issued <= 0;
                issue_x <= 0; issue_y <= 0;
                frame_memory_status <= memory_status;
                frame_underruns <= underruns;
                frame_framecount <= frame_count;
                frame_effect_mask <= effect_mask; frame_effect_order <= effect_order;
            end
            // RAM read plus dashboard stages A/B/C/D move as a single stopped
            // pipeline. No beat can overtake a stalled output, including last.
            if (pipeline_enable) begin
                valid_pipe <= {valid_pipe[3:0],advance};
                last_pipe <= {last_pipe[3:0],advance && issue_x == WIDTH-2 && issue_y == HEIGHT-1};
                a_x <= read_x; a_y <= read_y;
                b_x <= a_x; b_y <= a_y;
                c_x <= b_x; c_y <= b_y;
                output_x <= c_x; output_y <= c_y;
            end
            if (advance) begin
                previous_wave_data <= render_wave_data;
                read_x <= canvas_x; read_y <= canvas_y;
                if (issue_x == WIDTH-2) begin
                    issue_x <= 0;
                    if (issue_y == HEIGHT-1) all_issued <= 1;
                    else issue_y <= issue_y + 1'b1;
                end else issue_x <= issue_x + 11'd2;
            end
            if (final_accept) begin busy <= 0; frame_done <= 1; end
        end
    end
endmodule

`default_nettype wire
