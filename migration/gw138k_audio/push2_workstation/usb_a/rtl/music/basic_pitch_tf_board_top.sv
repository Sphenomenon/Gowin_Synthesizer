`timescale 1ns/1ps

// Physical link bring-up image: on-board micro-SD -> WAV PCM -> Basic Pitch.
module basic_pitch_tf_board_top (
    input  wire clk_50m,
    input  wire button1_n,
    input  wire sd_miso,
    output wire sd_cs_n,
    output wire sd_sck,
    output wire sd_mosi,
    output wire debug_uart_tx,
    input  wire debug_uart_rx,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs, ddr_ras, ddr_cas, ddr_we,
    output wire ddr_ck, ddr_ck_n, ddr_cke, ddr_odt, ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout  wire [31:0] ddr_dq,
    inout  wire [3:0] ddr_dqs, ddr_dqs_n
);
    reg [1:0] reset_sync = 2'b00;
    reg [11:0] reset_count = 12'd0;
    reg reset_n = 1'b0;
    always @(posedge clk_50m or negedge button1_n) begin
        if (!button1_n) begin
            reset_sync <= 2'b00;
            reset_count <= 12'd0;
            reset_n <= 1'b0;
        end else begin
            reset_sync <= {reset_sync[0], 1'b1};
            if (!reset_sync[1]) begin
                reset_count <= 12'd0;
                reset_n <= 1'b0;
            end else if (!reset_n) begin
                if (&reset_count) reset_n <= 1'b1;
                else reset_count <= reset_count + 1'b1;
            end
        end
    end

    wire [1:0] card_type, fs_type;
    wire [3:0] card_stat;
    wire [2:0] fs_stat;
    wire scan_done, card_ready, playing, eof;
    wire [4:0] track_count;
    wire format_ready, unsupported, stereo;
    wire [19:0] sample_rate;
    wire [5:0] bits_per_sample;
    wire pcm_valid, pcm_ready;
    wire signed [15:0] pcm_left, pcm_right;
    wire [15:0] frame_count, resync_count, skipped_frames, stuck_frames;
    wire [15:0] parity_errors;
    wire [7:0] debug_cmdrsp, debug_rwrsp;
    wire [3:0] debug_cardstate;
    wire debug_spidone, debug_rvalid_session;
    reg [7:0] last_cmdrsp, last_rwrsp;
    reg seen_spidone, miso_seen_low;

    tf_sd_audio_pcm_player #(
        .FILE_EXT("WAV"), .AUDIO_KIND(2),
        .SPI_CLK_DIV(100), .SPI_CLK_DIV_FAST(12)
    ) u_tf_audio (
        .clk(clk_50m), .rst_n(reset_n), .restart(1'b0), .track_index(4'd0),
        .sd_miso(sd_miso), .sd_cs_n(sd_cs_n), .sd_sck(sd_sck), .sd_mosi(sd_mosi),
        .card_type(card_type), .card_stat(card_stat),
        .filesystem_type(fs_type), .filesystem_stat(fs_stat),
        .scan_done(scan_done), .card_ready(card_ready), .playing(playing), .eof(eof),
        .track_count(track_count), .format_ready(format_ready), .unsupported(unsupported),
        .sample_rate_hz(sample_rate), .stereo(stereo), .bits_per_sample(bits_per_sample),
        .pcm_valid(pcm_valid), .pcm_ready(pcm_ready),
        .pcm_left(pcm_left), .pcm_right(pcm_right),
        .frame_count(frame_count), .resync_count(resync_count),
        .skipped_frames(skipped_frames), .stuck_frames(stuck_frames),
        .pcm_fifo_parity_errors(parity_errors), .debug_cmdrsp(debug_cmdrsp),
        .debug_rwrsp(debug_rwrsp), .debug_cardstate(debug_cardstate),
        .debug_spidone(debug_spidone), .debug_rvalid_session(debug_rvalid_session)
    );

    // Decoder and Basic Pitch stay in the already-routed 50-MHz domain.  Only
    // slow DP state crosses into the calibrated 100-MHz DDR domain below.
    wire memory_clk, memory_reset_n, memory_calibrated, memory_pll_locked;

    wire bp_result_valid, bp_busy, bp_done;
    wire [6:0] bp_result_note;
    wire [15:0] bp_result_conf, bp_result_frame, bp_debug_onset;
    wire [15:0] bp_debug_progress;
    wire [8:0] bp_stream_wave;
    wire [191:0] bp_layer_hashes;
    wire bp_report_tick;
    reg [2:0] hash_page;
    reg bp_done_q;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin hash_page <= 0; bp_done_q <= 0; end
        else begin
            bp_done_q <= bp_done;
            if (bp_done && !bp_done_q) hash_page <= 0;
            else if (bp_result_valid && bp_report_tick) begin
                hash_page <= (hash_page == 5) ? 0 : hash_page + 1'b1;
            end
        end
    end
    wire [3:0] bp_model_status;
    wire bp_mem_req, bp_mem_write, bp_mem_ready, bp_mem_rsp_valid;
    wire [31:0] bp_mem_byte_addr;
    wire [15:0] bp_mem_wdata, bp_mem_rdata;
    basic_pitch_pcm_pipeline #(
        .WIN_LEN(43844), .FRAME_LIMIT(172), .OCTAVE_LIMIT(9),
        .USE_EXTERNAL_STATE(1'b1), .USE_EXTERNAL_PLANE(1'b1),
        .USE_EXTERNAL_WEIGHTS(1'b0), .USE_EXTERNAL_FEATURES(1'b0),
        .USE_ALL_DDR(1'b1), .USE_DDR_FRONT_COEFF(1'b1),
        .USE_DDR_CQT_COEFF(1'b1)
    ) u_basic_pitch (
        .clk_i(clk_50m), .rst_ni(reset_n),
        .model_boot_ready_i(1'b1),.flash_miso_i(1'b1),
        .flash_cs_n_o(),.flash_clk_o(),.flash_mosi_o(),
        .debug_model_source_o(),.debug_model_flash_error_o(),
        .model_serial_i(debug_uart_rx), .model_status_o(bp_model_status),
        .pcm_valid_i(pcm_valid), .pcm_end_i(1'b0), .pcm_ready_o(pcm_ready),
        .pcm_left_i(pcm_left), .pcm_right_i(pcm_right),
        .result_valid_o(bp_result_valid), .result_note_o(bp_result_note),
        .result_conf_o(bp_result_conf), .result_frame_o(bp_result_frame),
        .debug_onset_o(bp_debug_onset), .debug_progress_o(bp_debug_progress),
        .debug_stream_wave_o(bp_stream_wave),
        .debug_layer_hashes_o(bp_layer_hashes),
        .busy_o(bp_busy), .done_o(bp_done),
        .mem_req_o(bp_mem_req), .mem_write_o(bp_mem_write),
        .mem_byte_addr_o(bp_mem_byte_addr), .mem_wdata_o(bp_mem_wdata),
        .mem_ready_i(bp_mem_ready), .mem_rsp_valid_i(bp_mem_rsp_valid),
        .mem_rdata_i(bp_mem_rdata)
    );

    wire ddr_cmd_valid, ddr_cmd_ready, ddr_cmd_write;
    wire [48:0] ddr_cmd_data;
    music_async_fifo #(.WIDTH(49), .ADDRESS_BITS(4)) u_ddr_req_cdc (
        .write_clk_i(clk_50m), .write_rst_ni(reset_n),
        .write_valid_i(bp_mem_req), .write_ready_o(bp_mem_ready),
        .write_data_i({bp_mem_write, bp_mem_byte_addr, bp_mem_wdata}),
        .read_clk_i(memory_clk), .read_rst_ni(memory_reset_n),
        .read_valid_o(ddr_cmd_valid), .read_ready_i(ddr_cmd_ready),
        .read_data_o(ddr_cmd_data)
    );
    assign ddr_cmd_write = ddr_cmd_data[48];

    wire ddr_rsp_fifo_valid, ddr_rsp_fifo_ready, ddr_rsp_valid;
    wire [15:0] ddr_rsp_fifo_data, ddr_rsp_data;
    music_async_fifo #(.WIDTH(16), .ADDRESS_BITS(2)) u_ddr_rsp_cdc (
        .write_clk_i(memory_clk), .write_rst_ni(memory_reset_n),
        .write_valid_i(ddr_rsp_valid), .write_ready_o(ddr_rsp_fifo_ready),
        .write_data_i(ddr_rsp_data),
        .read_clk_i(clk_50m), .read_rst_ni(reset_n),
        .read_valid_o(ddr_rsp_fifo_valid), .read_ready_i(1'b1),
        .read_data_o(ddr_rsp_fifo_data)
    );
    assign bp_mem_rsp_valid = ddr_rsp_fifo_valid;
    assign bp_mem_rdata = ddr_rsp_fifo_data;

    wire ddr_req, ddr_write, ddr_ready, ddr_response;
    wire [28:0] ddr_address;
    wire [255:0] ddr_wdata, ddr_rdata;
    wire [31:0] ddr_wmask;
    basic_pitch_ddr16_port u_dp_ddr (
        .clk_i(memory_clk), .rst_ni(memory_reset_n),
        .req_valid_i(ddr_cmd_valid), .req_write_i(ddr_cmd_write),
        .req_byte_addr_i(ddr_cmd_data[47:16]), .req_wdata_i(ddr_cmd_data[15:0]),
        .req_ready_o(ddr_cmd_ready), .rsp_valid_o(ddr_rsp_valid),
        .rsp_rdata_o(ddr_rsp_data), .ddr_req_o(ddr_req),
        .ddr_write_o(ddr_write), .ddr_address_o(ddr_address),
        .ddr_data_o(ddr_wdata), .ddr_mask_o(ddr_wmask),
        .ddr_ready_i(ddr_ready), .ddr_response_i(ddr_response),
        .ddr_read_data_i(ddr_rdata)
    );

    wire app_rdy, app_wrdy, app_rvalid, app_rend;
    ddr3_platform u_memory (
        .clk_50m(clk_50m), .rst_n(reset_n), .ui_clk(memory_clk),
        .ui_rst_n(memory_reset_n), .calib_done(memory_calibrated),
        .pll_locked(memory_pll_locked),
        .app_cmd(ddr_write ? 3'b000 : 3'b001), .app_en(ddr_req && ddr_ready),
        .app_addr(ddr_address), .app_rdy(app_rdy), .app_wdata(ddr_wdata),
        .app_wmask(ddr_wmask), .app_wren(ddr_req && ddr_ready && ddr_write),
        .app_wend(ddr_req && ddr_ready && ddr_write), .app_wrdy(app_wrdy),
        .app_rdata(ddr_rdata), .app_rvalid(app_rvalid), .app_rend(app_rend),
        .ddr_addr(ddr_addr), .ddr_bank(ddr_bank), .ddr_cs(ddr_cs),
        .ddr_ras(ddr_ras), .ddr_cas(ddr_cas), .ddr_we(ddr_we),
        .ddr_ck(ddr_ck), .ddr_ck_n(ddr_ck_n), .ddr_cke(ddr_cke),
        .ddr_odt(ddr_odt), .ddr_reset_n(ddr_reset_n), .ddr_dm(ddr_dm),
        .ddr_dq(ddr_dq), .ddr_dqs(ddr_dqs), .ddr_dqs_n(ddr_dqs_n)
    );
    assign ddr_ready = app_rdy && (!ddr_write || app_wrdy);
    assign ddr_response = app_rvalid;

    (* ASYNC_REG="TRUE" *) reg memory_calibrated_meta, memory_calibrated_sync;
    (* ASYNC_REG="TRUE" *) reg memory_pll_locked_meta, memory_pll_locked_sync;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            memory_calibrated_meta <= 1'b0;
            memory_calibrated_sync <= 1'b0;
            memory_pll_locked_meta <= 1'b0;
            memory_pll_locked_sync <= 1'b0;
        end else begin
            memory_calibrated_meta <= memory_calibrated;
            memory_calibrated_sync <= memory_calibrated_meta;
            memory_pll_locked_meta <= memory_pll_locked;
            memory_pll_locked_sync <= memory_pll_locked_meta;
        end
    end

    reg seen_playing, seen_format, seen_pcm, seen_busy, seen_done;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            seen_playing <= 1'b0;
            seen_format <= 1'b0;
            seen_pcm <= 1'b0;
            seen_busy <= 1'b0;
            seen_done <= 1'b0;
            last_cmdrsp <= 8'd0;
            last_rwrsp <= 8'd0;
            seen_spidone <= 1'b0;
            miso_seen_low <= 1'b0;
        end else begin
            seen_playing <= seen_playing | playing;
            seen_format <= seen_format | format_ready;
            seen_pcm <= seen_pcm | (pcm_valid && pcm_ready);
            seen_busy <= seen_busy | bp_busy;
            seen_done <= seen_done | bp_done;
            if (debug_spidone) begin
                last_cmdrsp <= debug_cmdrsp;
                last_rwrsp <= debug_rwrsp;
                seen_spidone <= 1'b1;
            end
            if (!sd_cs_n && !sd_miso) miso_seen_low <= 1'b1;
        end
    end

    wire [31:0] bp_report = {
        (bp_result_valid ? bp_result_frame[11:0] : {3'd0,bp_stream_wave}),
        bp_result_conf[7:0], bp_result_note,
        bp_result_valid, seen_done, seen_busy, seen_format, seen_playing
    };
    wire [31:0] tf_report = {
        frame_count[7:0], pcm_ready, seen_pcm, unsupported, format_ready,
        track_count, eof, playing, card_ready, scan_done,
        fs_stat, fs_type, card_stat, card_type
    };
    wire [31:0] sd_report = {
        last_cmdrsp, last_rwrsp, debug_cardstate,
        seen_spidone, debug_rvalid_session,
        miso_seen_low, sd_cs_n, sd_sck, sd_mosi, bp_model_status,
        memory_calibrated_sync, memory_pll_locked_sync
    };

    basic_pitch_link_uart u_report (
        .clk_i(clk_50m), .rst_ni(reset_n),
        .bp_report_i(bp_report), .tf_report_i(tf_report),
        .nn_report_i(bp_result_valid ?
            {bp_layer_hashes[hash_page*32+3 +: 29], hash_page} :
            {bp_debug_progress, sample_rate[15:0]}),
        .sd_report_i(sd_report),
        .tick_o(bp_report_tick),
        .serial_o(debug_uart_tx)
    );
endmodule

// Emits: B138 <bp_report> <tf_report> <onset|rate> <sd_debug>\r\n at 2 Hz.
module basic_pitch_link_uart (
    input  wire        clk_i,
    input  wire        rst_ni,
    input  wire [31:0] bp_report_i,
    input  wire [31:0] tf_report_i,
    input  wire [31:0] nn_report_i,
    input  wire [31:0] sd_report_i,
    output wire        tick_o,
    output wire        serial_o
);
    localparam integer INTERVAL_CYCLES = 25_000_000;
    reg [24:0] interval_count;
    reg sending;
    reg [5:0] character;
    reg [127:0] payload;
    wire tx_ready;
    reg [7:0] tx_byte;
    assign tick_o = !sending && interval_count == INTERVAL_CYCLES-1;

    function automatic [7:0] hex_digit(input [3:0] value);
        hex_digit = value < 10 ? 8'd48 + value : 8'd55 + value;
    endfunction

    always @* begin
        case (character)
            0: tx_byte = "B";
            1: tx_byte = "1";
            2: tx_byte = "3";
            3: tx_byte = "8";
            4, 13, 22, 31: tx_byte = " ";
            40: tx_byte = 8'd13;
            41: tx_byte = 8'd10;
            default: tx_byte = hex_digit(payload[127:124]);
        endcase
    end

    uart_tx #(.CLK_HZ(50_000_000), .BAUD(115200)) u_uart (
        .clk(clk_i), .rst_n(rst_ni), .data({24'd0, tx_byte}),
        .valid(sending), .ready(tx_ready), .serial_out(serial_o), .byte_done()
    );

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            interval_count <= 0;
            sending <= 1'b0;
            character <= 0;
            payload <= 0;
        end else if (!sending) begin
            if (interval_count == INTERVAL_CYCLES-1) begin
                interval_count <= 0;
                payload <= {bp_report_i, tf_report_i, nn_report_i, sd_report_i};
                character <= 0;
                sending <= 1'b1;
            end else interval_count <= interval_count + 1'b1;
        end else if (tx_ready) begin
            if ((character >= 5 && character <= 12) ||
                (character >= 14 && character <= 21) ||
                (character >= 23 && character <= 30) ||
                (character >= 32 && character <= 39))
                payload <= {payload[123:0], 4'd0};
            if (character == 41) sending <= 1'b0;
            else character <= character + 1'b1;
        end
    end
endmodule
