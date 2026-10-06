`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"

// Dual-config equivalence probe for the 0x82 staged-cache fix.
//
// The SAME PCM stream runs through
//   dut_a: USE_ALL_DDR=1            (the proven 0x80/0x81 datapath)
//   dut_b: USE_ALL_DDR=0 + staged   (the 0x82 datapath)
// over one behavioural DDR preloaded with the model blob.  The UART loaders
// are hierarchy-forced DONE (a real BPN1 upload does not fit in sim time).
// Per-frame layer hashes and emitted score notes must match bit-exactly;
// any mismatch is a logic bug in the staged-cache path rather than silicon.
module tb_bp_config_ab #(
    parameter integer FRAMES = 3,
    parameter integer WIN_LEN = 2048,
    parameter integer DDR_READ_CYCLES = 1,
    parameter integer MAX_CYCLES = 400000000
);
    localparam integer TOTAL_SAMPLES = WIN_LEN + FRAMES*255 + 4096;

    reg clk = 0, rstn = 0;
    always #10 clk = ~clk;   // 50 MHz

    // ------------------------------------------------------------------
    // Behavioural 16-bit DDR.  Requests are serialized by the pipeline
    // (single outstanding read), so: writes accept immediately, reads
    // respond after DDR_READ_CYCLES cycles. Index = {granule, addr[19:1]} with the 13
    // 1 MiB granules the BP map actually uses; unwritten space reads 0.
    // ------------------------------------------------------------------
    function automatic [3:0] gmap(input [11:0] g);
        case (g)
            12'h100: gmap = 4'd0;   // CQT plane
            12'h101: gmap = 4'd1;   // model
            12'h102: gmap = 4'd2;   // notes
            12'h103: gmap = 4'd3;   // onset
            12'h104: gmap = 4'd4;   // contour
            12'h105: gmap = 4'd5;   // reduce
            12'h106: gmap = 4'd6;   // note post
            12'h107: gmap = 4'd7;   // onset post
            12'h108: gmap = 4'd8;   // CQT signal
            12'h300: gmap = 4'd9;   // DP backpointers
            12'h301: gmap = 4'd10;  // DP notes
            12'h302: gmap = 4'd11;  // DP onsets
            12'h303: gmap = 4'd12;  // analysis
            default: gmap = 4'd13;
        endcase
    endfunction

    reg [15:0] mem [0:14*524288-1];
    reg [15:0] rsp_data = 0;
    reg rsp_valid = 0;
    integer rsp_timer = 0;

    wire a_req, a_wr, b_req, b_wr;
    wire [31:0] a_addr, b_addr;
    wire [15:0] a_wdata, b_wdata;
    reg run_a = 1;
    wire mem_req = run_a ? a_req : b_req;
    wire mem_wr = run_a ? a_wr : b_wr;
    wire [31:0] mem_addr = run_a ? a_addr : b_addr;
    wire [15:0] mem_wdata = run_a ? a_wdata : b_wdata;
    wire [22:0] mem_idx = {gmap(mem_addr[31:20]), mem_addr[19:1]};
    wire mem_ready = rstn && rsp_timer == 0 && !rsp_valid;

    always @(posedge clk or negedge rstn) begin
        if (!rstn) begin
            rsp_valid <= 0; rsp_timer <= 0;
        end else begin
            rsp_valid <= 0;
            if (mem_req && mem_ready) begin
                if (gmap(mem_addr[31:20]) == 13 || mem_addr[0])
                    $fatal(1, "invalid DDR address %08h", mem_addr);
                if ($isunknown(mem_addr) || (mem_wr && $isunknown(mem_wdata)))
                    $fatal(1, "unknown DDR transaction addr=%08h data=%04h", mem_addr, mem_wdata);
                if (mem_wr) mem[mem_idx] <= mem_wdata;
                else begin
                    rsp_data <= mem[mem_idx];
                    rsp_timer <= DDR_READ_CYCLES;
                end
            end else if (rsp_timer != 0) begin
                rsp_timer <= rsp_timer - 1;
                if (rsp_timer == 1) rsp_valid <= 1;
            end
        end
    end

    // ------------------------------------------------------------------
    // Stimulus: one LFSR PCM stream, reseeded at every reset so both runs
    // see identical samples.
    // ------------------------------------------------------------------
    reg [15:0] lfsr;
    reg pcm_valid = 0, pcm_end = 0;
    reg signed [15:0] pcm_l = 0, pcm_r = 0;
    integer sent = 0;
    wire a_ready, b_ready;
    wire pcm_ready = run_a ? a_ready : b_ready;

    always @(negedge clk or negedge rstn) begin
        if (!rstn) begin
            pcm_valid <= 0; pcm_end <= 0; sent <= 0; lfsr = 16'hBEEF;
        end else begin
            pcm_valid <= 0;
            if (sent >= TOTAL_SAMPLES) pcm_end <= 1;
            else if (!pcm_end && pcm_ready) begin
                pcm_valid <= 1;
                lfsr = {lfsr[14:0], lfsr[15] ^ lfsr[12] ^ lfsr[10] ^ lfsr[8]};
                pcm_l <= $signed(lfsr);
                lfsr = {lfsr[14:0], lfsr[15] ^ lfsr[12] ^ lfsr[10] ^ lfsr[8]};
                pcm_r <= $signed(lfsr);
                sent = sent + 1;
            end
        end
    end

    // ------------------------------------------------------------------
    // Pipelines under test.
    // ------------------------------------------------------------------
    wire [191:0] a_hashes, b_hashes;
    wire a_done, b_done, a_busy, b_busy;
    wire a_score_valid, b_score_valid;
    wire [6:0] a_score_note, b_score_note;
    wire [15:0] a_prog, b_prog;
    wire [8:0] a_wave, b_wave;

    basic_pitch_pcm_pipeline #(
        .WIN_LEN(WIN_LEN), .FRAME_LIMIT(FRAMES), .OCTAVE_LIMIT(9),
        .USE_EXTERNAL_STATE(1'b1), .USE_EXTERNAL_PLANE(1'b1),
        .USE_ALL_DDR(1'b1), .USE_DDR_FRONT_COEFF(1'b1), .USE_DDR_CQT_COEFF(1'b1)
    ) dut_a (
        .clk_i(clk), .rst_ni(rstn && run_a), .analysis_restart_i(1'b0),
        .model_serial_i(1'b1), .model_status_o(), .debug_model_expected_crc_o(),
        .debug_model_actual_crc_o(), .debug_model_error_stage_o(),
        .pcm_valid_i(pcm_valid && run_a), .pcm_end_i(pcm_end && run_a),
        .pcm_ready_o(a_ready),
        .pcm_left_i(pcm_l), .pcm_right_i(pcm_r),
        .result_valid_o(), .result_note_o(), .result_conf_o(), .result_frame_o(),
        .score_valid_o(a_score_valid), .score_ready_i(1'b1), .score_note_o(a_score_note),
        .debug_onset_o(), .debug_progress_o(a_prog), .debug_dwell_o(),
        .debug_stream_wave_o(a_wave), .debug_layer_hashes_o(a_hashes),
        .busy_o(a_busy), .done_o(a_done), .song_done_o(),
        .mem_req_o(a_req), .mem_write_o(a_wr), .mem_byte_addr_o(a_addr),
        .mem_wdata_o(a_wdata), .mem_ready_i(mem_ready && run_a),
        .mem_rsp_valid_i(rsp_valid && run_a), .mem_rdata_i(rsp_data)
    );

    basic_pitch_pcm_pipeline #(
        .WIN_LEN(WIN_LEN), .FRAME_LIMIT(FRAMES), .OCTAVE_LIMIT(9),
        .USE_EXTERNAL_STATE(1'b1), .USE_EXTERNAL_PLANE(1'b1),
        .USE_EXTERNAL_WEIGHTS(1'b1), .USE_EXTERNAL_FEATURES(1'b1),
        .USE_ALL_DDR(1'b0), .USE_DDR_SIGNAL(1'b1),
        .USE_DDR_FRONT_COEFF(1'b1), .USE_DDR_CQT_COEFF(1'b1)
    ) dut_b (
        .clk_i(clk), .rst_ni(rstn && !run_a), .analysis_restart_i(1'b0),
        .model_serial_i(1'b1), .model_status_o(), .debug_model_expected_crc_o(),
        .debug_model_actual_crc_o(), .debug_model_error_stage_o(),
        .pcm_valid_i(pcm_valid && !run_a), .pcm_end_i(pcm_end && !run_a),
        .pcm_ready_o(b_ready),
        .pcm_left_i(pcm_l), .pcm_right_i(pcm_r),
        .result_valid_o(), .result_note_o(), .result_conf_o(), .result_frame_o(),
        .score_valid_o(b_score_valid), .score_ready_i(1'b1), .score_note_o(b_score_note),
        .debug_onset_o(), .debug_progress_o(b_prog), .debug_dwell_o(),
        .debug_stream_wave_o(b_wave), .debug_layer_hashes_o(b_hashes),
        .busy_o(b_busy), .done_o(b_done), .song_done_o(),
        .mem_req_o(b_req), .mem_write_o(b_wr), .mem_byte_addr_o(b_addr),
        .mem_wdata_o(b_wdata), .mem_ready_i(mem_ready && !run_a),
        .mem_rsp_valid_i(rsp_valid && !run_a), .mem_rdata_i(rsp_data)
    );

    // The (multi-second, real-UART) model upload cannot run in sim: the DDR
    // image is preloaded below, so hold both loaders in DONE from the start.
    reg model_loaded = 0;
    always @(posedge clk) begin
        if (rstn && model_loaded) begin
            if (run_a) dut_a.g_all_ddr_weights.u_model_loader.state = 4'd14;
            else dut_b.g_ddr_weights.u_model_loader.state = 4'd14;
        end
    end

    integer a_notes = 0, b_notes = 0, errors = 0, i;
    reg [6:0] a_seq [0:4095];
    reg [6:0] b_seq [0:4095];
    always @(posedge clk) begin
        if (run_a && a_score_valid) begin a_seq[a_notes] <= a_score_note; a_notes = a_notes + 1; end
        if (!run_a && b_score_valid) begin b_seq[b_notes] <= b_score_note; b_notes = b_notes + 1; end
    end

    reg [31:0] a_hash_snap [0:5];
    reg [31:0] b_hash_snap [0:5];

    // Store every completed streaming wave, including pipeline flush waves.
    reg [191:0] wave_hash_a [0:FRAMES+9];
    reg [8:0] previous_wave = 0;
    integer first_bad_wave = -1;
    integer a_writes [0:5];
    integer b_writes [0:5];
    always @(negedge clk) begin
        if (!rstn) previous_wave = 0;
        else if ((run_a ? a_wave : b_wave) != previous_wave) begin
            if (run_a) wave_hash_a[previous_wave] = a_hashes;
            else if (wave_hash_a[previous_wave] !== b_hashes) begin
                if (first_bad_wave < 0) first_bad_wave = previous_wave;
                $display("WAVE_MISMATCH wave=%0d A=%048h B=%048h", previous_wave,
                         wave_hash_a[previous_wave], b_hashes);
            end
            $display("WAVE_%s completed=%0d hashes=%048h", run_a ? "A" : "B",
                     previous_wave, run_a ? a_hashes : b_hashes);
            $fflush();
            previous_wave = run_a ? a_wave : b_wave;
        end
        if (rstn && run_a) begin
            if (dut_a.contour_act_valid) a_writes[0] = a_writes[0] + 1;
            if (dut_a.reduce_act_valid) a_writes[1] = a_writes[1] + 1;
            if (dut_a.notes_act_valid) a_writes[2] = a_writes[2] + 1;
            if (dut_a.note_out_act_valid) a_writes[3] = a_writes[3] + 1;
            if (dut_a.onset_act_valid) a_writes[4] = a_writes[4] + 1;
            if (dut_a.onset_out_act_valid) a_writes[5] = a_writes[5] + 1;
        end else if (rstn) begin
            if (dut_b.contour_act_valid) b_writes[0] = b_writes[0] + 1;
            if (dut_b.reduce_act_valid) b_writes[1] = b_writes[1] + 1;
            if (dut_b.notes_act_valid) b_writes[2] = b_writes[2] + 1;
            if (dut_b.note_out_act_valid) b_writes[3] = b_writes[3] + 1;
            if (dut_b.onset_act_valid) b_writes[4] = b_writes[4] + 1;
            if (dut_b.onset_out_act_valid) b_writes[5] = b_writes[5] + 1;
        end
    end

    reg [15:0] blob [0:52238];
    task preload_ddr;
        integer j;
        begin
            for (j = 0; j < 14*524288; j = j + 1) mem[j] = 16'h0;
            for (j = 0; j < 52239; j = j + 1)
                mem[524288 + j] = blob[j];
        end
    endtask
    initial begin
        $readmemh("rtl/music/weights/cnn_ddr_blob.mem", blob);
        preload_ddr();
        for (i = 0; i < 6; i = i + 1) begin a_writes[i] = 0; b_writes[i] = 0; end
        model_loaded = 1;
    end

    task step(input integer n);
        integer k;
        begin
            for (k = 0; k < n; k = k + 1) @(posedge clk);
        end
    endtask

    initial begin
        wait (model_loaded);
        repeat (8) @(negedge clk);
        rstn = 1;
        // ---- run A: proven all-DDR datapath ----
        run_a = 1;
        wait (a_done);
        step(20000);   // let the score drain finish
        for (i = 0; i < 6; i = i + 1) a_hash_snap[i] = a_hashes[i*32 +: 32];
        $display("RUN_A notes=%0d hashes=%08h_%08h_%08h_%08h_%08h_%08h",
                 a_notes, a_hash_snap[0], a_hash_snap[1], a_hash_snap[2],
                 a_hash_snap[3], a_hash_snap[4], a_hash_snap[5]);
        $writememh("sim/music/gen/run_a_hashes.mem", a_hash_snap);
        // ---- run B: staged-cache datapath ----
        @(negedge clk);
        rstn = 0;
        run_a = 0;
        preload_ddr();
        repeat (8) @(negedge clk);
        rstn = 1;
        wait (b_done);
        step(20000);
        for (i = 0; i < 6; i = i + 1) b_hash_snap[i] = b_hashes[i*32 +: 32];
        $display("RUN_B notes=%0d hashes=%08h_%08h_%08h_%08h_%08h_%08h",
                 b_notes, b_hash_snap[0], b_hash_snap[1], b_hash_snap[2],
                 b_hash_snap[3], b_hash_snap[4], b_hash_snap[5]);
        $writememh("sim/music/gen/run_b_hashes.mem", b_hash_snap);
        if (a_notes != b_notes) begin
            errors = errors + 1;
            $display("FAIL score note count %0d vs %0d", a_notes, b_notes);
        end
        for (i = 0; i < a_notes && i < b_notes; i = i + 1)
            if (a_seq[i] !== b_seq[i]) begin
                errors = errors + 1;
                $display("FAIL note[%0d] %0d vs %0d", i, a_seq[i], b_seq[i]);
            end
        if (first_bad_wave >= 0) begin
            errors = errors + 1;
            $display("FAIL first divergent wave=%0d", first_bad_wave);
        end
        for (i = 0; i < 6; i = i + 1) begin
            $display("COVERAGE layer=%0d writes_A=%0d writes_B=%0d", i, a_writes[i], b_writes[i]);
            if (a_writes[i] == 0 || a_writes[i] != b_writes[i]) begin
                errors = errors + 1;
                $display("FAIL layer %0d coverage", i);
            end
        end
        for (i = 0; i < 6; i = i + 1)
            if (a_hash_snap[i] !== b_hash_snap[i]) begin
                errors = errors + 1;
                $display("FAIL layer %0d hash %08h vs %08h", i, a_hash_snap[i], b_hash_snap[i]);
            end
        if (errors == 0) $display("PASS dual-config equivalence (%0d notes)", a_notes);
        else $fatal(1, "FAIL %0d mismatches", errors);
        $finish;
    end

    initial begin
        repeat (MAX_CYCLES) @(posedge clk);
        $display("TIMEOUT: run_a done=%0b busy=%0b run_b done=%0b busy=%0b",
                 a_done, a_busy, b_done, b_busy);
        $fatal(1, "cycle limit exceeded");
    end

    // heartbeat: one line per 10 ms of sim time (500k cycles)
    initial begin
        forever begin
            #10_000_000;
            $display("HB %0d ms  a_busy=%0b a_prog=%h  b_busy=%0b b_prog=%h",
                     $time / 1_000_000, a_busy, a_prog, b_busy, b_prog);
            $fflush();
        end
    end
endmodule
