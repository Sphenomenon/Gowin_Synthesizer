`timescale 1ns / 1ps

// UART/LED/PWM use the 50 MHz clock; HDMI derives its video clocks from it.
module sd_boot_top (
    input  wire clk,
    output wire led1,
    output wire led2,
    input  wire uart_rx_pin,
    output wire uart_tx_pin,
    input  wire button_n,
    output wire toggle_out,
    output wire ws2812_data,
    inout wire touch_scl,
    inout wire touch_sda,
    input wire touch_change_n,
    inout wire keypad_scl,
    inout wire keypad_sda,
    output wire [2:0] hdmi_data_p,
    output wire [2:0] hdmi_data_n,
    output wire hdmi_clock_p,
    output wire hdmi_clock_n,
    input wire [7:0] camera_data,
    input wire camera_pclk,
    input wire camera_href,
    input wire camera_vsync,
    inout wire camera_scl,
    inout wire camera_sda,
    output wire camera_pwdn,
    output wire camera_reset_n,
    inout wire [14:0] DDR_addr,
    inout wire [2:0] DDR_ba,
    inout wire DDR_cas_n,
    inout wire DDR_ck_n,
    inout wire DDR_ck_p,
    inout wire DDR_cke,
    inout wire DDR_cs_n,
    // PS7's fixed pin interface remains 32 bits; its controller uses 16 bits.
    inout wire [3:0] DDR_dm,
    inout wire [31:0] DDR_dq,
    inout wire [3:0] DDR_dqs_n,
    inout wire [3:0] DDR_dqs_p,
    inout wire DDR_odt,
    inout wire DDR_ras_n,
    inout wire DDR_reset_n,
    inout wire DDR_we_n,
    inout wire FIXED_IO_ddr_vrn,
    inout wire FIXED_IO_ddr_vrp,
    inout wire [53:0] FIXED_IO_mio,
    inout wire FIXED_IO_ps_clk,
    inout wire FIXED_IO_ps_porb,
    inout wire FIXED_IO_ps_srstb
);
    wire slider_report, slider_touch, slider_valid;
    wire [7:0] slider_value;
    (* MARK_DEBUG = "TRUE" *) wire slider_done, uart_byte_sent;
    (* MARK_DEBUG = "TRUE" *) wire [63:0] slider_result, uart_byte_result;
    wire key_tx_valid, key_tx_last, key_tx_ready;
    wire [7:0] key_tx_data;
    uart_led_controller #(.ENABLE_SLIDER_REPORT(0), .ENABLE_KEY_REPORT(1)) u_uart_led (
        .clk(clk), .uart_rx_pin(uart_rx_pin), .uart_tx_pin(uart_tx_pin),
        .led1(led1), .led2(led2), .slider_report(slider_report), .slider_value(slider_value),
        .slider_touch(slider_touch), .slider_valid(slider_valid),
        .key_tx_valid(key_tx_valid), .key_tx_data(key_tx_data),
        .key_tx_last(key_tx_last), .key_tx_ready(key_tx_ready),
        .uart_byte_sent(uart_byte_sent), .uart_byte_result(uart_byte_result));

    button_toggle u_button_toggle (
        .clk(clk), .button_n(button_n), .toggle_out(toggle_out));

    (* MARK_DEBUG = "TRUE" *) wire ws2812_frame_start;
    ws2812_chain u_ws2812 (
        .clk(clk), .data_out(ws2812_data), .frame_start(ws2812_frame_start));

    wire touch_scl_i, touch_sda_i, touch_scl_low, touch_sda_low;
    (* MARK_DEBUG = "TRUE" *) wire touch_done;
    (* MARK_DEBUG = "TRUE" *) wire [63:0] touch_result;
    IOBUF touch_scl_buffer (.I(1'b0), .T(!touch_scl_low), .O(touch_scl_i), .IO(touch_scl));
    IOBUF touch_sda_buffer (.I(1'b0), .T(!touch_sda_low), .O(touch_sda_i), .IO(touch_sda));
    qt2160_slider_reader u_touch (.clk(clk), .scl_in(touch_scl_i), .sda_in(touch_sda_i),
        .change_n(touch_change_n), .scl_low(touch_scl_low), .sda_low(touch_sda_low),
        .id_done(touch_done), .id_result(touch_result), .sample_done(slider_done), .slider_result(slider_result),
        .report(slider_report), .slider_value(slider_value), .touched(slider_touch), .sample_valid(slider_valid));

    wire keypad_scl_i, keypad_sda_i, keypad_scl_low, keypad_sda_low;
    wire key_event_valid, key_event_ready;
    wire [3:0] key_index;
    wire [15:0] key_signal, key_reference;
    (* MARK_DEBUG = "TRUE" *) wire keypad_done, keypad_event;
    (* MARK_DEBUG = "TRUE" *) wire [63:0] keypad_result, keypad_event_result;
    (* MARK_DEBUG = "TRUE" *) wire keypad_scan_done;
    (* MARK_DEBUG = "TRUE" *) wire [63:0] keypad_scan_result;
    assign keypad_event = key_event_valid && key_event_ready;
    assign keypad_event_result = {28'b0, key_index, key_reference, key_signal};
    IOBUF keypad_scl_buffer (.I(1'b0), .T(!keypad_scl_low), .O(keypad_scl_i), .IO(keypad_scl));
    IOBUF keypad_sda_buffer (.I(1'b0), .T(!keypad_sda_low), .O(keypad_sda_i), .IO(keypad_sda));
    qt2160_keypad_reader u_keypad (
        .clk(clk), .scl_in(keypad_scl_i), .sda_in(keypad_sda_i),
        .scl_low(keypad_scl_low), .sda_low(keypad_sda_low),
        .event_valid(key_event_valid), .event_ready(key_event_ready),
        .key_index(key_index), .key_signal(key_signal), .key_reference(key_reference),
        .sample_done(keypad_done), .result(keypad_result),
        .scan_done(keypad_scan_done), .scan_result(keypad_scan_result));
    qt2160_keypad_uart u_keypad_uart (
        .clk(clk), .event_valid(key_event_valid), .event_ready(key_event_ready),
        .key_index(key_index), .key_signal(key_signal), .key_reference(key_reference),
        .tx_valid(key_tx_valid), .tx_ready(key_tx_ready), .tx_data(key_tx_data), .tx_last(key_tx_last));

    wire camera_clk, axi_clk, axi_resetn, video_clk, video_fsync;
    // RGB565 DVP at 84 MHz, two bytes per pixel; sample on the rising edge after falling-edge launch.
    BUFG camera_pclk_buffer (.I(camera_pclk), .O(camera_clk));
    wire [31:0] camera_gain_rb;
    wire [15:0] camera_gain_g;
    wire [31:0] camera_gpio_i, camera_gpio_o, camera_gpio_t;
    assign camera_pwdn = camera_gpio_o[2];
    assign camera_reset_n = camera_gpio_o[3];
    assign camera_gpio_i[5:2] = camera_gpio_o[5:2];
    IOBUF camera_scl_buffer (.I(camera_gpio_o[0]), .T(camera_gpio_t[0]),
        .O(camera_gpio_i[0]), .IO(camera_scl));
    IOBUF camera_sda_buffer (.I(camera_gpio_o[1]), .T(camera_gpio_t[1]),
        .O(camera_gpio_i[1]), .IO(camera_sda));
    wire [15:0] capture_data, display_data;
    wire capture_valid, capture_last, capture_user, capture_ready;
    wire display_valid, display_last, display_user, display_ready;
    wire [1:0] display_keep;
    wire [15:0] camera_frame_gray;
    wire [11:0] camera_drop_gray;
    wire camera_activity, camera_stream_error;
    wire [25:0] frame_debug;
    wire debug_toggle;
    reg debug_ack = 0;
    (* ASYNC_REG = "TRUE" *) reg debug_req_meta = 0, debug_req_sync = 0;
    reg [25:0] frame_debug_axi = 0;
    // Bundled-data handshake: camera holds the snapshot until acknowledged.
    always @(posedge axi_clk) begin
        debug_req_meta <= debug_toggle; debug_req_sync <= debug_req_meta;
        if (debug_req_sync != debug_ack) begin
            frame_debug_axi <= frame_debug;
            debug_ack <= debug_req_sync;
        end
    end
    assign camera_gpio_i[31:6] = frame_debug_axi;
    reg capture_enable_axi = 0;
    always @(posedge axi_clk) capture_enable_axi <= camera_gpio_o[4] && axi_resetn;
    ov2640_capture #(.WIDTH(1280), .HEIGHT(720)) u_capture (.pclk(camera_clk), .enable(capture_enable_axi),
        .data(camera_data), .href(camera_href), .vsync(camera_vsync),
        .axis_data(capture_data), .axis_valid(capture_valid), .axis_ready(capture_ready),
        .axis_last(capture_last), .axis_user(capture_user), .frame_gray(camera_frame_gray),
        .drop_gray(camera_drop_gray), .activity(camera_activity),
        .frame_debug(frame_debug), .debug_toggle(debug_toggle), .debug_ack(debug_ack));
    wire [17:0] camera_fifo_data;
    wire camera_fifo_full, camera_fifo_empty, camera_fifo_wr_busy, camera_fifo_rd_busy;
    wire capture_dma_ready;
    (* ASYNC_REG = "TRUE" *) reg [7:0] camera_fifo_reset_pipe = 8'hff;
    always @(posedge camera_clk or negedge axi_resetn) begin
        if (!axi_resetn) camera_fifo_reset_pipe <= 8'hff;
        else camera_fifo_reset_pipe <= {camera_fifo_reset_pipe[6:0],1'b0};
    end
    assign capture_ready = !camera_fifo_full && !camera_fifo_wr_busy;
    xpm_fifo_sync #(.FIFO_MEMORY_TYPE("block"), .FIFO_WRITE_DEPTH(1024),
        .WRITE_DATA_WIDTH(18), .READ_DATA_WIDTH(18), .READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0), .USE_ADV_FEATURES("0000")) camera_pixel_fifo (
        .wr_clk(camera_clk), .rst(camera_fifo_reset_pipe[7]),
        .din({capture_user,capture_last,capture_data}),
        .wr_en(capture_valid && capture_ready), .full(camera_fifo_full),
        .wr_rst_busy(camera_fifo_wr_busy), .dout(camera_fifo_data),
        .rd_en(capture_dma_ready && !camera_fifo_empty && !camera_fifo_rd_busy),
        .empty(camera_fifo_empty), .rd_rst_busy(camera_fifo_rd_busy),
        .sleep(1'b0), .injectsbiterr(1'b0), .injectdbiterr(1'b0));
    hdmi_tx u_hdmi (.camera_fps_bcd({camera_gain_rb[31:28],camera_gain_rb[15:12]}),
        .camera_fps_epoch(camera_gain_g[15]), .clk_50(clk), .camera_display_enable(camera_gpio_o[5]),
        .camera_axis_data(display_data), .camera_axis_valid(display_valid),
        .camera_axis_last(display_last), .camera_axis_user(display_user),
        .camera_axis_ready(display_ready), .video_pixel_clock(video_clk), .video_fsync(video_fsync),
        .camera_stream_error(camera_stream_error), .data_p(hdmi_data_p), .data_n(hdmi_data_n),
        .clock_p(hdmi_clock_p), .clock_n(hdmi_clock_n));

    // Registered Gray counters cross into the PS GPIO status clock safely.
    (* ASYNC_REG = "TRUE" *) reg [15:0] frame_meta = 0, frame_sync = 0;
    (* ASYNC_REG = "TRUE" *) reg [11:0] drop_meta = 0, drop_sync = 0;
    (* ASYNC_REG = "TRUE" *) reg [3:0] status_meta = 0, status_sync = 0;
    always @(posedge axi_clk) begin
        frame_meta <= camera_frame_gray; frame_sync <= frame_meta;
        drop_meta <= camera_drop_gray; drop_sync <= drop_meta;
        status_meta <= {camera_activity, camera_stream_error, camera_href, camera_vsync};
        status_sync <= status_meta;
    end
    wire [15:0] frame_binary;
    wire [11:0] drop_binary;
    genvar bit_index;
    generate
        for (bit_index = 0; bit_index < 16; bit_index = bit_index + 1) begin: frame_decode
            assign frame_binary[bit_index] = ^(frame_sync >> bit_index);
        end
        for (bit_index = 0; bit_index < 12; bit_index = bit_index + 1) begin: drop_decode
            assign drop_binary[bit_index] = ^(drop_sync >> bit_index);
        end
    endgenerate
    wire [31:0] camera_status = {status_sync, drop_binary, frame_binary};

    // Use the BD itself so SCCB IOBUFs remain at the board-level top.
    ps_system u_ps (
        .camera_gain_rb(camera_gain_rb), .camera_gain_g(camera_gain_g),
        .camera_axi_clk(axi_clk), .camera_axi_resetn(axi_resetn),
        .camera_pclk(camera_clk), .video_pclk(video_clk), .video_fsync(video_fsync),
        .camera_control_tri_i(camera_gpio_i), .camera_control_tri_o(camera_gpio_o),
        .camera_control_tri_t(camera_gpio_t), .camera_status_tri_i(camera_status),
        .camera_in_tdata(camera_fifo_data[15:0]), .camera_in_tkeep(2'b11), .camera_in_tlast(camera_fifo_data[16]),
        .camera_in_tuser(camera_fifo_data[17]), .camera_in_tvalid(!camera_fifo_empty && !camera_fifo_rd_busy),
        .camera_in_tready(capture_dma_ready),
        .video_out_tdata(display_data), .video_out_tkeep(display_keep), .video_out_tlast(display_last),
        .video_out_tuser(display_user), .video_out_tvalid(display_valid), .video_out_tready(display_ready),
        .DDR_addr(DDR_addr), .DDR_ba(DDR_ba), .DDR_cas_n(DDR_cas_n),
        .DDR_ck_n(DDR_ck_n), .DDR_ck_p(DDR_ck_p), .DDR_cke(DDR_cke),
        .DDR_cs_n(DDR_cs_n), .DDR_dm(DDR_dm), .DDR_dq(DDR_dq),
        .DDR_dqs_n(DDR_dqs_n), .DDR_dqs_p(DDR_dqs_p), .DDR_odt(DDR_odt),
        .DDR_ras_n(DDR_ras_n), .DDR_reset_n(DDR_reset_n), .DDR_we_n(DDR_we_n),
        .FIXED_IO_ddr_vrn(FIXED_IO_ddr_vrn), .FIXED_IO_ddr_vrp(FIXED_IO_ddr_vrp),
        .FIXED_IO_mio(FIXED_IO_mio), .FIXED_IO_ps_clk(FIXED_IO_ps_clk),
        .FIXED_IO_ps_porb(FIXED_IO_ps_porb), .FIXED_IO_ps_srstb(FIXED_IO_ps_srstb)
    );
endmodule
