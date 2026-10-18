// Time-multiplexed voice bank; all slots share oscillator and gain hardware.
// Commands are two 32-bit words and commit only on sample_tick.
module synth_engine #(parameter integer VOICE_COUNT = 32) (
    input wire clk, input wire rst_n, input wire sample_tick,
    input wire [31:0] cmd_data, input wire cmd_valid, output wire cmd_ready,
    input wire cmd_first, input wire cmd_last,
    output reg [31:0] rsp_data, output reg rsp_valid, input wire rsp_ready,
    output reg signed [31:0] sample_data, output reg sample_valid,
    output wire [31:0] active_voices,
    // Sample-aligned display tag: bit0 reference valid, bit1 cycle start,
    // bits7:2 reference voice, bits31:8 sound-parameter revision.
    // This observation never changes audio phase.
    output reg [31:0] trigger_reference,
    input wire [7:0] memory_flags,
    input wire [127:0] video_diagnostics,
    input wire [511:0] latency_diagnostics,
    // Per-voice onset records live in a shared observer RAM. Byte zero waits
    // for its atomic read; audio frames continue while that read is pending.
    output wire onset_query_request, output wire [4:0] onset_query_voice,
    input wire onset_query_done, input wire [255:0] onset_query_data,
    output wire trace_commit, output wire [31:0] trace_header,
    output wire [23:0] trace_revision,
    output wire trace_frame_start, output wire trace_sample_event,
    output wire [23:0] trace_sample_revision,
    output wire [31:0] trace_nonzero_voices,
    output reg [31:0] sample_nonzero_voices,
    output reg signed [39:0] mix_sum,
    output wire voice_sample_event,
    output wire signed [31:0] voice_sample_data,
    output wire [4:0] voice_sample_index,
    output reg [31:0] master_volume, lr_balance
);
    wire bank_sample_valid, bank_busy, bank_ready;
    reg have_header, command_pending, response_pending, response_wait_frame;
    reg [31:0] command_header, command_value;
    reg [7:0] response_status;
    reg [127:0] video_snapshot;
    reg video_snapshot_valid;
    reg [31:0] voice_snapshot;
    reg voice_snapshot_valid;
    reg [511:0] latency_snapshot;
    reg latency_snapshot_valid;
    reg [255:0] onset_snapshot;
    reg onset_snapshot_valid, response_wait_onset;
    reg [4:0] onset_snapshot_voice;
    wire [7:0] opcode = command_header[23:16];
    wire [7:0] voice_id = command_header[15:8];
    reg [7:0] validation_status;
    assign cmd_ready = bank_ready && !command_pending && !response_pending && !rsp_valid;
    // The DAC may request its first sample while the state RAM initializes.
    // Retain that request and finish it well before the next 1024-clock frame.
    reg sample_request;
    wire frame_accept = bank_ready && (sample_tick || sample_request);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) sample_request <= 0;
        else if (frame_accept) sample_request <= 0;
        else if (sample_tick) sample_request <= 1;
    end
    always @* begin
        validation_status = 0;
        if (command_header[7:0] != 0) validation_status = 3;
        else if (opcode == 0 || opcode == 8'h0a || opcode == 8'h0b) begin
            if (voice_id != 8'hff) validation_status = 2;
            else if (command_value != 0) validation_status = 3;
        end else if (opcode == 8'h0c) begin
            if (voice_id != 8'hff) validation_status = 2;
            else if (command_value > 15) validation_status = 3;
            else if (command_value != 0 && !video_snapshot_valid) validation_status = 3;
        end else if (opcode == 8'h0d) begin
            if (voice_id != 8'hff) validation_status = 2;
            else if (command_value > 3) validation_status = 3;
            else if (command_value != 0 && !voice_snapshot_valid) validation_status = 3;
        end else if (opcode == 8'h0e) begin
            if (voice_id != 8'hff) validation_status = 2;
            else if (command_value > 63) validation_status = 3;
            else if (command_value != 0 && !latency_snapshot_valid) validation_status = 3;
        end else if (opcode == 8'h0f) begin
            if (voice_id >= VOICE_COUNT) validation_status = 2;
            else if (command_value > 31) validation_status = 3;
            else if (command_value != 0 && (!onset_snapshot_valid ||
                     onset_snapshot_voice != voice_id[4:0])) validation_status = 3;
        end else if (opcode == 8'h10 || opcode == 8'h11) begin
            if (voice_id != 8'hff) validation_status = 2;
            else if (command_value > 32'h80000000) validation_status = 3;
        end else if (opcode > 8'h09) validation_status = 1;
        else if (voice_id >= VOICE_COUNT) validation_status = 2;
        else case (opcode)
            8'h01,8'h03: if (command_value[31]) validation_status = 3;
            8'h02: if (command_value != 0) validation_status = 3;
            8'h05: if (command_value > 2) validation_status = 3;
            default: if (command_value > 32'h80000000) validation_status = 3;
        endcase
    end
    wire command_apply = frame_accept && command_pending && validation_status == 0;
    assign onset_query_request = command_apply && opcode == 8'h0f && command_value == 0;
    assign onset_query_voice = voice_id[4:0];
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            have_header <= 0; command_pending <= 0; response_pending <= 0; response_wait_frame <= 0;
            command_header <= 0; command_value <= 0; rsp_data <= 0; rsp_valid <= 0; response_status <= 0;
            video_snapshot <= 0; video_snapshot_valid <= 0;
            voice_snapshot <= 0; voice_snapshot_valid <= 0;
            latency_snapshot <= 0; latency_snapshot_valid <= 0;
            onset_snapshot <= 0; onset_snapshot_valid <= 0;
            onset_snapshot_voice <= 0; response_wait_onset <= 0;
            master_volume <= 32'h80000000; lr_balance <= 32'h40000000;
        end else begin
            if (rsp_valid && rsp_ready) rsp_valid <= 0;
            if (cmd_valid && cmd_ready) begin
                if (!have_header && cmd_first && !cmd_last) begin command_header <= cmd_data; have_header <= 1; end
                else if (have_header && !cmd_first && cmd_last) begin
                    command_value <= cmd_data; command_pending <= 1; have_header <= 0;
                end else begin
                    have_header <= 0; response_status <= 4; response_pending <= 1; response_wait_frame <= 0;
                    if (!have_header) command_header <= cmd_data;
                end
            end
            if (frame_accept && command_pending) begin
                command_pending <= 0; response_pending <= 1; response_status <= validation_status;
                response_wait_frame <= 1;
                if (validation_status == 0 && opcode == 8'h10) master_volume <= command_value;
                if (validation_status == 0 && opcode == 8'h11) lr_balance <= command_value;
                // Byte zero starts one atomic host-visible snapshot. Later byte
                // requests read this same copy even as the live counters advance.
                if (validation_status == 0 && opcode == 8'h0d && command_value == 0) begin
                    voice_snapshot <= active_voices; voice_snapshot_valid <= 1;
                end
                if (validation_status == 0 && opcode == 8'h0c && command_value == 0) begin
                    video_snapshot <= video_diagnostics;
                    video_snapshot_valid <= 1;
                end
                if (validation_status == 0 && opcode == 8'h0e && command_value == 0) begin
                    latency_snapshot <= latency_diagnostics; latency_snapshot_valid <= 1;
                end
                if (onset_query_request) response_wait_onset <= 1;
            end
            if (response_pending && response_wait_frame && bank_sample_valid)
                response_wait_frame <= 0;
            if (response_wait_onset && onset_query_done) begin
                onset_snapshot <= onset_query_data; onset_snapshot_valid <= 1;
                onset_snapshot_voice <= voice_id[4:0]; response_wait_onset <= 0;
            end
            // Wait for every slot write before acknowledging a frame commit.
            if (response_pending && (!response_wait_frame || bank_sample_valid) && !response_wait_onset) begin
                rsp_data <= {command_header[31:24],response_status,
                             (opcode==8'h0b ? memory_flags :
                              opcode==8'h0c ? (response_status == 0 ?
                                  video_snapshot[command_value[3:0]*8 +: 8] : 8'd0) :
                              opcode==8'h0d ? (response_status == 0 ?
                                  voice_snapshot[command_value[1:0]*8 +: 8] : 8'd0) :
                              opcode==8'h0e ? (response_status == 0 ?
                                  latency_snapshot[command_value[5:0]*8 +: 8] : 8'd0) :
                              opcode==8'h0f ? (response_status == 0 ?
                                  onset_snapshot[command_value[4:0]*8 +: 8] : 8'd0) :
                              active_voices[7:0]),opcode};
                rsp_valid <= 1; response_pending <= 0; response_wait_frame <= 0;
            end
        end
    end
    // One state RAM, oscillator/ADSR datapath and gain multiplier serve all slots.
    wire signed [31:0] bank_sample;
    wire signed [39:0] bank_mix_sum;
    wire bank_reference_valid;
    wire [5:0] bank_reference_voice;
    wire [31:0] bank_reference_phase;
    wire [31:0] bank_nonzero_voices;
    synth_voice_bank #(.VOICE_COUNT(VOICE_COUNT)) bank (
        .clk(clk),.rst_n(rst_n),.sample_tick(frame_accept),
        .command_header(command_header),.command_value(command_value),.command_apply(command_apply),
        .sample_data(bank_sample),.sample_valid(bank_sample_valid),.active_voices(active_voices),
        .nonzero_voices(bank_nonzero_voices),
        .mix_sum(bank_mix_sum),.voice_sample_event(voice_sample_event),
        .voice_sample_data(voice_sample_data),.voice_sample_index(voice_sample_index),
        .reference_valid(bank_reference_valid),.reference_voice(bank_reference_voice),
        .reference_phase(bank_reference_phase),.busy(bank_busy),.ready(bank_ready));

    // The tag describes the same pre-update states as the mixed sample.
    // Minimum-pitch selection is accumulated during the sequential voice scan.
    reg previous_reference_valid;
    reg [5:0] previous_reference_voice;
    reg [31:0] previous_reference_phase;
    reg [23:0] sound_revision, frame_revision;
    wire sound_change=command_apply && ((opcode>=8'h01 && opcode<=8'h0a) || opcode==8'h10 || opcode==8'h11);
    assign trace_commit = sound_change;
    assign trace_header = command_header;
    assign trace_revision = sound_revision + 1'b1;
    assign trace_frame_start = frame_accept;
    // Pre-edge event/data describe the values registered to the engine's
    // sample outputs on that same edge, avoiding a monitor's extra cycle.
    assign trace_sample_event = bank_sample_valid;
    assign trace_sample_revision = frame_revision;
    assign trace_nonzero_voices = bank_nonzero_voices;
    wire reference_wrap = bank_reference_valid && previous_reference_valid &&
                          bank_reference_voice == previous_reference_voice &&
                          bank_reference_phase < previous_reference_phase;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            previous_reference_valid <= 0; previous_reference_voice <= 0;
            previous_reference_phase <= 0; trigger_reference <= 0;
            sound_revision <= 0; frame_revision <= 0;
            sample_data <= 0; sample_valid <= 0; sample_nonzero_voices <= 0; mix_sum <= 0;
        end else begin
            sample_valid <= bank_sample_valid;
            trigger_reference <= 0;
            if (frame_accept) frame_revision <= sound_revision;
            if (sound_change)
                sound_revision <= sound_revision + 1'b1;
            if (bank_sample_valid) begin
                sample_data <= bank_sample;
                mix_sum <= bank_mix_sum;
                sample_nonzero_voices <= bank_nonzero_voices;
                trigger_reference <= {frame_revision,bank_reference_voice,reference_wrap,bank_reference_valid};
                previous_reference_valid <= bank_reference_valid;
                previous_reference_voice <= bank_reference_voice;
                previous_reference_phase <= bank_reference_phase;
            end
        end
    end
endmodule
