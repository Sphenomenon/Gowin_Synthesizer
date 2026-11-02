`timescale 1ns/1ps

// One Basic Pitch client of the workstation DDR arbiter.  Decoded PCM is
// observed in the TF decoder clock domain; the audio playback path is never
// stalled by model upload or analysis.
module basic_pitch_workstation_link #(
    parameter bit USE_FLASH_WEIGHTS = 1'b0,
    // Placement only: the default preserves the existing DDR arithmetic path.
    parameter bit USE_DDR_SIGNAL = 1'b1,
    parameter bit USE_DDR_CQT_COEFF = 1'b1,
    parameter integer WIN_LEN=43844,FRAME_LIMIT=172,OCTAVE_LIMIT=9,
    parameter integer CQT_HOP_NUMERATOR=256,CQT_HOP_DENOMINATOR=1,
    parameter integer FEATURE_TILE_COLS=0,
    parameter bit COARSE_GUIDANCE=1'b0,
    // Opt in only for a task owner which waits for restart_done_o. The
    // default retains the accepted single-board restart contract.
    parameter bit DRAIN_RESTART_ENABLE = 1'b0,
    parameter bit BOUNDED_EOF_PADDING = 1'b0,
    parameter integer RESTART_TIMEOUT_CYCLES = 50000000
) (
    input wire clk_50m, reset_n,
    input wire memory_clk, memory_reset_n, memory_calibrated,
    input wire model_serial,
    input wire flash_miso,
    output wire flash_cs_n, flash_clk, flash_mosi,
    input wire analysis_enable,
    input wire analysis_restart,
    input wire pcm_valid,
    input wire pcm_end,
    input wire signed [15:0] pcm_left, pcm_right,
    input wire [19:0] sample_rate,
    input wire format_ready, source_active,
    input wire [10:0] hotplug_debug,
    output wire pcm_ready,
    output wire [3:0] model_status,
    output wire result_valid,
    output wire [6:0] result_note,
    output wire [15:0] result_frame,
    output wire score_valid,
    input wire score_ready,
    output wire [6:0] score_note,
    output wire analysis_done,
    output wire report_sending, report_serial,
    output wire ddr_req, ddr_write,
    output wire [28:0] ddr_address,
    output wire [255:0] ddr_data,
    output wire [31:0] ddr_mask,
    input wire ddr_ready, ddr_response,
    input wire [255:0] ddr_read_data,
    output wire restart_ready_o, restart_busy_o, restart_done_o,
    output wire restart_fault_o,
    // 1: drain timeout; 2: memory reset/calibration lost after readiness.
    // Recovery from either fault requires a coherent global reset_n.
    output wire [1:0] restart_failure_code_o
);
    wire bp_busy,bp_done,bp_song_done;
    wire pipeline_restart,task_io_enable,request_admit;
    wire raw_result_valid,raw_score_valid;
    assign analysis_done=bp_song_done && task_io_enable;
    assign result_valid=raw_result_valid && task_io_enable;
    assign score_valid=raw_score_valid && task_io_enable;
    wire bp_pcm_ready,converted_valid,converted_ready;
    wire signed [15:0] converted_left,converted_right;
    wire rate_48000=sample_rate==20'd48000;
    wire rate_44100=sample_rate==20'd44100;
    assign pcm_ready=task_io_enable && (rate_48000 ? bp_pcm_ready :
                     rate_44100 ? converted_ready : 1'b1);
    basic_pitch_44100_to_48000 u_44100_to_48000(
        .clk_i(clk_50m),.rst_ni(reset_n && !pipeline_restart),
        .valid_i(pcm_valid && analysis_enable && rate_44100 && task_io_enable),
        .ready_o(converted_ready),.left_i(pcm_left),.right_i(pcm_right),
        .valid_o(converted_valid),.ready_i(bp_pcm_ready && task_io_enable),
        .left_o(converted_left),.right_o(converted_right));
    wire [15:0] result_conf,debug_onset,debug_progress,debug_dwell;
    wire [8:0] debug_stream_wave;
    wire [191:0] layer_hashes;
    wire [31:0] model_expected_crc,model_actual_crc;
    wire [1:0] model_error_stage,model_source,model_flash_error;
    (* ASYNC_REG="TRUE" *) reg model_memory_meta,model_memory_ready;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin model_memory_meta<=0; model_memory_ready<=0; end
        else begin
            model_memory_meta<=memory_calibrated && memory_reset_n;
            model_memory_ready<=model_memory_meta;
        end
    end
    wire bp_mem_req,bp_mem_write,bp_mem_ready,bp_mem_rsp_valid;
    wire [31:0] bp_mem_byte_addr;
    wire [15:0] bp_mem_wdata,bp_mem_rdata;
    basic_pitch_pcm_pipeline #(
        .WIN_LEN(WIN_LEN),.FRAME_LIMIT(FRAME_LIMIT),.OCTAVE_LIMIT(OCTAVE_LIMIT),
        .CQT_HOP_NUMERATOR(CQT_HOP_NUMERATOR),.CQT_HOP_DENOMINATOR(CQT_HOP_DENOMINATOR),
        .FEATURE_TILE_COLS(FEATURE_TILE_COLS),.COARSE_GUIDANCE(COARSE_GUIDANCE),
        .USE_EXTERNAL_STATE(1'b1),.USE_EXTERNAL_PLANE(1'b1),
        .USE_EXTERNAL_WEIGHTS(1'b1),.USE_FLASH_WEIGHTS(USE_FLASH_WEIGHTS),.USE_EXTERNAL_FEATURES(1'b1),
        .BOUNDED_EOF_PADDING(BOUNDED_EOF_PADDING),
        .USE_ALL_DDR(1'b0),.USE_DDR_SIGNAL(USE_DDR_SIGNAL),
        .USE_DDR_FRONT_COEFF(1'b1),.USE_DDR_CQT_COEFF(USE_DDR_CQT_COEFF)
    ) u_basic_pitch (
        .clk_i(clk_50m),.rst_ni(reset_n),.analysis_restart_i(pipeline_restart),
        .model_serial_i(model_serial),.model_boot_ready_i(model_memory_ready),
        .flash_miso_i(flash_miso),
        .flash_cs_n_o(flash_cs_n),.flash_clk_o(flash_clk),.flash_mosi_o(flash_mosi),
        .model_status_o(model_status),
        .debug_model_source_o(model_source),.debug_model_flash_error_o(model_flash_error),
        .debug_model_expected_crc_o(model_expected_crc),
        .debug_model_actual_crc_o(model_actual_crc),
        .debug_model_error_stage_o(model_error_stage),
        .pcm_valid_i(task_io_enable && (rate_48000 ? (pcm_valid && analysis_enable) :
                     (rate_44100 && converted_valid && analysis_enable))),
        .pcm_end_i(task_io_enable && analysis_enable && pcm_end &&
                   (!rate_44100 || !converted_valid)),
        .pcm_ready_o(bp_pcm_ready),
        .pcm_left_i(rate_48000 ? pcm_left : converted_left),
        .pcm_right_i(rate_48000 ? pcm_right : converted_right),
        .result_valid_o(raw_result_valid),.result_note_o(result_note),
        .result_conf_o(result_conf),.result_frame_o(result_frame),
        .score_valid_o(raw_score_valid),.score_ready_i(score_ready && task_io_enable),.score_note_o(score_note),
        .debug_onset_o(debug_onset),.debug_progress_o(debug_progress),
        .debug_dwell_o(debug_dwell),
        .debug_stream_wave_o(debug_stream_wave),
        .debug_layer_hashes_o(layer_hashes),
        .busy_o(bp_busy),.done_o(bp_done),.song_done_o(bp_song_done),
        .mem_req_o(bp_mem_req),.mem_write_o(bp_mem_write),
        .mem_byte_addr_o(bp_mem_byte_addr),.mem_wdata_o(bp_mem_wdata),
        .mem_ready_i(bp_mem_ready),.mem_rsp_valid_i(bp_mem_rsp_valid),
        .mem_rdata_i(bp_mem_rdata)
    );

    wire ddr_fifo_valid,ddr_fifo_ready;
    wire [48:0] ddr_fifo_data;
    wire ddr_cmd_valid,ddr_cmd_ready;
    wire [48:0] ddr_cmd_data;
    wire request_fifo_ready;
    assign bp_mem_ready = request_fifo_ready && request_admit;
    music_async_fifo #(.WIDTH(49),.ADDRESS_BITS(4)) u_ddr_req_cdc (
        .write_clk_i(clk_50m),.write_rst_ni(reset_n),
        .write_valid_i(bp_mem_req && request_admit),.write_ready_o(request_fifo_ready),
        .write_data_i({bp_mem_write,bp_mem_byte_addr,bp_mem_wdata}),
        .read_clk_i(memory_clk),.read_rst_ni(memory_reset_n),
        .read_valid_o(ddr_fifo_valid),.read_ready_i(ddr_fifo_ready),
        .read_data_o(ddr_fifo_data)
    );
    basic_pitch_ddr_command_buffer u_ddr_command_buffer (
        .clk_i(memory_clk),.rst_ni(memory_reset_n),
        .in_valid_i(ddr_fifo_valid),.in_data_i(ddr_fifo_data),
        .in_ready_o(ddr_fifo_ready),.out_valid_o(ddr_cmd_valid),
        .out_data_o(ddr_cmd_data),.out_ready_i(ddr_cmd_ready)
    );
    wire ddr_rsp_valid,ddr_rsp_fifo_valid,ddr_rsp_fifo_ready;
    wire [15:0] ddr_rsp_data,ddr_rsp_fifo_data;
    music_async_fifo #(.WIDTH(16),.ADDRESS_BITS(2)) u_ddr_rsp_cdc (
        .write_clk_i(memory_clk),.write_rst_ni(memory_reset_n),
        .write_valid_i(ddr_rsp_valid),.write_ready_o(ddr_rsp_fifo_ready),
        .write_data_i(ddr_rsp_data),
        .read_clk_i(clk_50m),.read_rst_ni(reset_n),
        .read_valid_o(ddr_rsp_fifo_valid),.read_ready_i(1'b1),
        .read_data_o(ddr_rsp_fifo_data)
    );
    assign bp_mem_rsp_valid = ddr_rsp_fifo_valid;
    assign bp_mem_rdata = ddr_rsp_fifo_data;
    basic_pitch_ddr16_port u_ddr16 (
        .clk_i(memory_clk),.rst_ni(memory_reset_n),
        .req_valid_i(ddr_cmd_valid && memory_calibrated &&
                     (ddr_cmd_data[48] || ddr_rsp_fifo_ready)),
        .req_write_i(ddr_cmd_data[48]),
        .req_byte_addr_i(ddr_cmd_data[47:16]),.req_wdata_i(ddr_cmd_data[15:0]),
        .req_ready_o(ddr_cmd_ready),.rsp_valid_o(ddr_rsp_valid),
        .rsp_rdata_o(ddr_rsp_data),.ddr_req_o(ddr_req),
        .ddr_write_o(ddr_write),.ddr_address_o(ddr_address),
        .ddr_data_o(ddr_data),.ddr_mask_o(ddr_mask),
        .ddr_ready_i(ddr_ready),.ddr_response_i(ddr_response),
        .ddr_read_data_i(ddr_read_data)
    );

    generate if (!DRAIN_RESTART_ENABLE) begin:g_legacy_restart
        assign pipeline_restart=analysis_restart;
        assign task_io_enable=1'b1;
        assign request_admit=1'b1;
        assign restart_ready_o=1'b1;
        assign restart_busy_o=1'b0;
        assign restart_done_o=analysis_restart;
        assign restart_fault_o=1'b0;
        assign restart_failure_code_o=2'd0;
    end else begin:g_drain_restart
        localparam integer TIMER_BITS=(RESTART_TIMEOUT_CYCLES<2) ? 1 :
                                      $clog2(RESTART_TIMEOUT_CYCLES);
        localparam [1:0] RUN=0,DRAIN=1,RESET_PIPELINE=2,RELEASE_PIPELINE=3;
        reg [1:0] state;
        reg armed,done,fault;
        reg [1:0] failure_code;
        reg [TIMER_BITS-1:0] timer;
        // The FIFO has only 16 slots and the pipeline permits one read in
        // flight. Monotonic 16-bit ledgers wrap safely; they are never reset
        // by a task restart or by a memory-domain-only reset.
        reg [15:0] reads_accepted,reads_consumed,writes_accepted;
        reg [15:0] writes_committed,writes_committed_gray;
        (* ASYNC_REG="TRUE" *) reg [15:0] writes_gray_meta,writes_gray_sync;
        reg memory_was_ready,memory_failed,transport_was_ready;
        (* ASYNC_REG="TRUE" *) reg memory_failed_meta,memory_failed_sync;
        wire restart_request=analysis_restart && armed;
        wire request_fire=bp_mem_req && bp_mem_ready;
        wire response_fire=ddr_rsp_fifo_valid;
        wire write_commit=memory_reset_n && memory_calibrated &&
                          ddr_cmd_valid && ddr_cmd_ready && ddr_cmd_data[48];
        wire [15:0] writes_committed_next=writes_committed+16'd1;
        function automatic [15:0] gray_to_binary(input [15:0] gray);
            integer bit_index;
            begin
                gray_to_binary[15]=gray[15];
                for(bit_index=14;bit_index>=0;bit_index=bit_index-1)
                    gray_to_binary[bit_index]=gray_to_binary[bit_index+1]^gray[bit_index];
            end
        endfunction
        wire [15:0] committed_sync=gray_to_binary(writes_gray_sync);
        wire drained=(reads_accepted==reads_consumed) &&
                     (writes_accepted==committed_sync);
        wire transport_ready=model_memory_ready && !memory_failed_sync;
        assign task_io_enable=state==RUN && !restart_request && !fault && transport_ready;
        assign request_admit=task_io_enable;
        assign pipeline_restart=state==RESET_PIPELINE && !fault && transport_ready;
        assign restart_ready_o=state==RUN && armed && !fault && transport_ready;
        assign restart_busy_o=state!=RUN && !fault;
        assign restart_done_o=done && !fault && transport_ready;
        assign restart_fault_o=fault;
        assign restart_failure_code_o=failure_code;

        // Register Gray from the very same single native-write acceptance.
        // It changes by at most one bit per memory clock, even while source
        // request admission is frozen for drain. Do not reset this counter
        // with memory_reset_n: lost transport state must fault, not look empty.
        always @(posedge memory_clk or negedge reset_n) begin
            if(!reset_n)begin
                writes_committed<=0;writes_committed_gray<=0;
                memory_was_ready<=0;memory_failed<=0;
            end else begin
                if(memory_reset_n && memory_calibrated)memory_was_ready<=1;
                if(memory_was_ready && (!memory_reset_n || !memory_calibrated))memory_failed<=1;
                if(write_commit && !memory_failed)begin
                    writes_committed<=writes_committed_next;
                    writes_committed_gray<=(writes_committed_next>>1)^writes_committed_next;
                end
            end
        end
        always @(posedge clk_50m or negedge reset_n)begin
            if(!reset_n)begin
                writes_gray_meta<=0;writes_gray_sync<=0;
                memory_failed_meta<=0;memory_failed_sync<=0;
                reads_accepted<=0;reads_consumed<=0;writes_accepted<=0;
                state<=RUN;armed<=1;done<=0;fault<=0;failure_code<=0;timer<=0;
                transport_was_ready<=0;
            end else begin
                writes_gray_meta<=writes_committed_gray;
                writes_gray_sync<=writes_gray_meta;
                memory_failed_meta<=memory_failed;
                memory_failed_sync<=memory_failed_meta;
                if(model_memory_ready)transport_was_ready<=1;
                done<=0;
                if(!analysis_restart)armed<=1;
                if(request_fire)begin
                    if(bp_mem_write)writes_accepted<=writes_accepted+16'd1;
                    else reads_accepted<=reads_accepted+16'd1;
                end
                if(response_fire)reads_consumed<=reads_consumed+16'd1;
                // Source-side readiness loss also quarantines the client
                // if the memory clock itself has stopped.
                if(memory_failed_sync || (transport_was_ready && !model_memory_ready))begin
                    fault<=1;failure_code<=2'd2;
                end else if(!fault)begin
                    case(state)
                        RUN:if(restart_request)begin state<=DRAIN;armed<=0;timer<=0;end
                        DRAIN:begin
                            if(drained && transport_ready)state<=RESET_PIPELINE;
                            else if(timer>=RESTART_TIMEOUT_CYCLES-1)begin
                                fault<=1;failure_code<=2'd1;
                            end else timer<=timer+1'b1;
                        end
                        RESET_PIPELINE:if(transport_ready)state<=RELEASE_PIPELINE;
                        RELEASE_PIPELINE:if(transport_ready)begin state<=RUN;done<=1;end
                    endcase
                end
            end
        end
    end endgenerate

    // These two diagnostic levels originate in the audio clock domain. Only
    // the first sampling stage is asynchronous; all sticky/UART consumers use
    // the second stage in clk_50m, rather than a raw level driving CE or data.
    (* ASYNC_REG="TRUE" *) reg format_meta,format_sync,source_meta,source_sync;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            format_meta <= 0; format_sync <= 0;
            source_meta <= 0; source_sync <= 0;
        end else begin
            format_meta <= format_ready; format_sync <= format_meta;
            source_meta <= source_active; source_sync <= source_meta;
        end
    end
    reg seen_pcm,seen_busy,seen_done,seen_format,seen_source;
    reg [2:0] hash_page;
    reg bp_done_q;
    reg [7:0] score_count;
    reg [6:0] score_first,score_last;
    wire report_tick;
    always @(posedge clk_50m or negedge reset_n) begin
        if (!reset_n) begin
            seen_pcm <= 0;seen_busy <= 0;seen_done <= 0;
            seen_format <= 0;seen_source <= 0;
            hash_page <= 0;bp_done_q <= 0;
            score_count <= 0;score_first <= 0;score_last <= 0;
        end else if (pipeline_restart) begin
            seen_pcm <= 0;seen_busy <= 0;seen_done <= 0;
            seen_format <= 0;seen_source <= 0;
            hash_page <= 0;bp_done_q <= 0;
            score_count <= 0;score_first <= 0;score_last <= 0;
        end else begin
            if (score_valid && score_ready) begin
                if (score_count == 0) score_first <= score_note;
                score_last <= score_note;
                score_count <= score_count + 1'b1;
            end
            seen_pcm <= seen_pcm | pcm_valid;
            seen_busy <= seen_busy | bp_busy;
            seen_done <= seen_done | bp_done;
            seen_format <= seen_format | format_sync;
            seen_source <= seen_source | source_sync;
            bp_done_q <= bp_done;
            if (bp_done && !bp_done_q) hash_page <= 0;
            else if ((result_valid || model_status==4'd15) && report_tick)
                hash_page <= (hash_page == 5) ? 0 : hash_page + 1'b1;
        end
    end
    wire [31:0] bp_report = {
        (result_valid ? result_frame[11:0] : {3'd0,debug_stream_wave}),
        result_conf[7:0],result_note,result_valid,
        seen_done,seen_busy,seen_format,seen_source
    };
    // Bits [15:6] trace the model request across the two clocks and DDR
    // arbiter when the UART loader waits in its WRITE state.
    wire [9:0] model_path_trace = {bp_mem_req,bp_mem_ready,
        ddr_cmd_valid,ddr_cmd_ready,ddr_req,ddr_ready,
        ddr_rsp_valid,ddr_rsp_fifo_valid,memory_reset_n,memory_calibrated};
    wire [10:0] tf_trace = hotplug_debug;
    wire [31:0] tf_report = model_status==4'd5 ?
        {sample_rate[15:0],model_path_trace,6'd0} :
        {sample_rate[15:0],tf_trace,
         seen_pcm,source_sync,format_sync,pcm_ready,pcm_valid};
    // Analysis-mode NN word: {debug_progress, per-state dwell page}.  The
    // former sample_rate half is redundant (the TF word carries it) and now
    // carries the CNN per-state dwell telemetry: {page[1:0], cycles[24:11]}.
    wire [31:0] nn_report = (model_status==4'd12 || model_status==4'd15) ?
        (hash_page[0] ? model_actual_crc : model_expected_crc) :
        result_valid ? {layer_hashes[hash_page*32+3 +: 29],hash_page} :
        {debug_progress,debug_dwell};
    // The model status remains in bits [5:2]. Upper bits make a completed
    // score observable on the board without altering the six CNN hash pages.
    wire [31:0] sd_report = {score_count,score_first,score_last,model_source,
                             (model_source==2'd2 && model_status==0 ? model_flash_error : model_error_stage),
                             model_status,memory_calibrated,1'b1};
    basic_pitch_link_uart u_report (
        .clk_i(clk_50m),.rst_ni(reset_n),
        .bp_report_i(bp_report),.tf_report_i(tf_report),
        .nn_report_i(nn_report),.sd_report_i(sd_report),
        .tick_o(report_tick),.sending_o(report_sending),
        .serial_o(report_serial)
    );
endmodule
