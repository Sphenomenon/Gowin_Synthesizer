module workstation_lcd (
    input wire clk_50m_i, audio_clk_i, rst_ni, audio_rst_ni,
    input wire feedback_valid_i,
    input wire [255:0] feedback_i,
    input wire [31:0] score_mask_i,
    input wire score_running_i, record_enabled_i,
    output wire [4:0] red_o,
    output wire [5:0] green_o,
    output wire [4:0] blue_o,
    output wire pclk_o,
    output reg hsync_o, vsync_o, de_o,
    output wire backlight_o,
    output wire [31:0] snapshot_drop_count_o
);
    wire pixel_clk, locked;
    gw138k_cpu_pll_cell #(
        .MULTIPLY_INTEGER(15), .MULTIPLY_EIGHTHS(6),
        .OUTPUT_DIV0(25), .OUTPUT1_ENABLE("FALSE")
    ) u_pll (
        .clkin(clk_50m_i), .init_clk(clk_50m_i), .reset(!rst_ni),
        .enable0(1'b1), .lock(locked), .clkout0(pixel_clk), .clkout1()
    );
    wire qualified_reset_n = rst_ni && locked;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [2:0] release_pipe = 0;
    always @(posedge pixel_clk or negedge qualified_reset_n)
        if (!qualified_reset_n) release_pipe <= 0;
        else release_pipe <= {release_pipe[1:0],1'b1};
    wire pixel_reset_n = release_pipe[2];
    wire [289:0] feedback;
    gw138k_stream_cdc #(.WIDTH(290)) u_feedback (
        .reset_n(qualified_reset_n && audio_rst_ni),
        .source_clk(audio_clk_i), .destination_clk(pixel_clk),
        .source_valid(feedback_valid_i),
        .source_data({score_mask_i,score_running_i,record_enabled_i,feedback_i}),
        .destination_valid(), .destination_data(feedback), .drop_count(snapshot_drop_count_o)
    );
    reg [9:0] horizontal, vertical;
    reg [1:0] startup_frames;
    reg active_q, hsync_q, vsync_q;
    reg [15:0] rgb;
    wire active = horizontal >= 136 && horizontal < 936 && vertical >= 35 && vertical < 515;
    wire frame_start = horizontal == 0 && vertical == 0;
    wire [9:0] position_x = active ? horizontal-10'd136 : 10'd0;
    wire [8:0] position_y = active ? vertical-10'd35 : 9'd0;
    wire [12:0] scaled_x = {3'd0,position_x}*13'd6;
    wire [9:0] surface_x = scaled_x/13'd5;
    wire [7:0] surface_y = position_y/9'd3;
    wire [15:0] pixel;
    push2_surface_pixels #(.PIPELINED(1),.SHOW_LAST_NOTE(0)) u_surface (
        .clk(pixel_clk), .rst(!pixel_reset_n), .frame_ready(frame_start), .frame_start(),
        .x(surface_x), .y(surface_y), .pixel_valid(), .pixel(pixel),
        .control(feedback[63:32]), .options(feedback[255:224]), .held(feedback[195:132]),
        .note(7'd0), .velocity(7'd0), .display_meta(64'd0), .display_meta_valid(1'b0),
        .score_mask(feedback[289:258]), .score_running(feedback[257]), .record_enabled(feedback[256]),
        .guide_mode(1'b0), .guide_chosen(1'b0), .guide_browse(4'd0), .guide_track(4'd0),
        .guide_track_count(5'd0), .guide_score_count(16'd0), .guide_cursor(16'd0),
        .guide_analysis_done(1'b0), .name_write_valid(1'b0), .name_write_addr(8'd0), .name_write_data(8'd0)
    );
    assign {red_o,green_o,blue_o} = rgb;
    assign pclk_o = !pixel_clk;
    assign backlight_o = qualified_reset_n && pixel_reset_n && startup_frames == 3;
    always @(posedge pixel_clk or negedge pixel_reset_n) begin
        if (!pixel_reset_n) begin
            horizontal <= 0;
            vertical <= 0;
            startup_frames <= 0;
            active_q <= 0;
            hsync_q <= 0;
            vsync_q <= 0;
            rgb <= 0;
            hsync_o <= 0;
            vsync_o <= 0;
            de_o <= 0;
        end else begin
            active_q <= active;
            hsync_q <= horizontal >= 48;
            vsync_q <= vertical >= 3;
            rgb <= active_q ? pixel : 16'd0;
            de_o <= active_q;
            hsync_o <= hsync_q;
            vsync_o <= vsync_q;
            if (horizontal == 975) begin
                horizontal <= 0;
                if (vertical == 527) begin
                    vertical <= 0;
                    if (startup_frames != 3) startup_frames <= startup_frames+1'b1;
                end else vertical <= vertical+1'b1;
            end else horizontal <= horizontal+1'b1;
        end
    end
endmodule
