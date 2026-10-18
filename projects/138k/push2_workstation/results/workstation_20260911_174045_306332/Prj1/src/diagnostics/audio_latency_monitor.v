// Passive, same-clock timestamps for the latest accepted sound command.
// A trace describes digital state/PCM transport, never analog headphone onset.
module audio_latency_monitor #(
    parameter integer CLOCK_HZ = 50000000
) (
    input wire clk, input wire rst_n, input wire [31:0] time_cycles,
    input wire packet_valid, input wire [31:0] packet_header,
    input wire [31:0] packet_start, packet_end,
    input wire command_commit, input wire [31:0] command_header,
    input wire [23:0] command_revision,
    input wire frame_start, input wire sample_event,
    input wire [23:0] sample_revision,
    input wire [31:0] nonzero_voices,
    input wire dac_done, input wire [23:0] dac_revision,
    input wire [31:0] dac_nonzero_voices,
    input wire ack_ready, input wire [31:0] ack_header, ack_ready_time,
    input wire ack_done, input wire [31:0] ack_done_header, ack_done_time,
    output wire [511:0] diagnostics
);
    localparam [31:0] CLOCK_RATE = CLOCK_HZ;
    reg pending_valid;
    reg [31:0] pending_header, pending_start, pending_end;
    reg [7:0] flags, trace_sequence, trace_opcode, trace_voice;
    reg [23:0] trace_revision;
    reg [31:0] trace_id, start_time, commit_time;
    reg [31:0] receive_cycles, commit_wait_cycles;
    reg [31:0] state_sample_cycles, note_sample_cycles;
    reg [31:0] dac_state_cycles, dac_note_cycles;
    reg [31:0] ack_ready_cycles, ack_done_cycles;
    reg [31:0] compute_cycles, period_cycles, last_frame_time;
    reg frame_seen;
    reg [31:0] overwritten_pending;
    wire [31:0] age_cycles = time_cycles - start_time;
    wire trace_live = flags[0] && !flags[7];
    wire note_trace = trace_opcode == 8'h01 && trace_voice < 32;
    wire ack_matches = ack_header[31:24] == trace_sequence &&
                       ack_header[7:0] == trace_opcode && ack_header[23:16] == 0;
    wire ack_done_matches = ack_done_header[31:24] == trace_sequence &&
                            ack_done_header[7:0] == trace_opcode && ack_done_header[23:16] == 0;

    // 16 little-endian words; opcode 0E snapshots all 64 bytes in the engine.
    assign diagnostics = {
        overwritten_pending, (flags[0] ? age_cycles : 32'd0),
        period_cycles, compute_cycles, ack_done_cycles, ack_ready_cycles,
        dac_note_cycles, dac_state_cycles, note_sample_cycles, state_sample_cycles,
        commit_wait_cycles, receive_cycles, CLOCK_RATE, trace_id,
        24'd0, flags, trace_voice, trace_opcode, trace_sequence, 8'd1
    };

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending_valid <= 0; pending_header <= 0; pending_start <= 0; pending_end <= 0;
            flags <= 0; trace_sequence <= 0; trace_opcode <= 0; trace_voice <= 0;
            trace_revision <= 0; trace_id <= 0; start_time <= 0; commit_time <= 0;
            receive_cycles <= 0; commit_wait_cycles <= 0;
            state_sample_cycles <= 0; note_sample_cycles <= 0;
            dac_state_cycles <= 0; dac_note_cycles <= 0;
            ack_ready_cycles <= 0; ack_done_cycles <= 0;
            compute_cycles <= 0; period_cycles <= 0; last_frame_time <= 0; frame_seen <= 0;
            overwritten_pending <= 0;
        end else begin
            if (packet_valid) begin
                pending_valid <= 1; pending_header <= packet_header;
                pending_start <= packet_start; pending_end <= packet_end;
            end
            if (frame_start) begin
                if (frame_seen) period_cycles <= time_cycles - last_frame_time;
                last_frame_time <= time_cycles; frame_seen <= 1;
            end
            if (sample_event && frame_seen) compute_cycles <= time_cycles - last_frame_time;

            // The transport is stop-and-wait. Require full header association;
            // a CRC-valid diagnostic or rejected command cannot replace a trace.
            if (command_commit && pending_valid && command_header == pending_header &&
                ((command_header[23:16] >= 1 && command_header[23:16] <= 10) ||
                 command_header[23:16] == 8'h10 || command_header[23:16] == 8'h11)) begin
                if (trace_live && (!flags[3] || (note_trace && !flags[4])))
                    overwritten_pending <= overwritten_pending + 1'b1;
                pending_valid <= 0;
                flags <= 8'h01; trace_id <= trace_id + 1'b1;
                trace_sequence <= command_header[31:24]; trace_opcode <= command_header[23:16];
                trace_voice <= command_header[15:8]; trace_revision <= command_revision;
                start_time <= pending_start; commit_time <= time_cycles;
                receive_cycles <= pending_end - pending_start;
                commit_wait_cycles <= time_cycles - pending_end;
                state_sample_cycles <= 0; note_sample_cycles <= 0;
                dac_state_cycles <= 0; dac_note_cycles <= 0;
                ack_ready_cycles <= 0; ack_done_cycles <= 0;
            end else if (trace_live) begin
                // Modular subtraction is unambiguous for <2^31 clocks.
                // Latch expiry before counter wrap can make an old trace look new.
                if (age_cycles[31]) flags[7] <= 1;
                else begin
                    if (sample_event && sample_revision == trace_revision) begin
                        if (!flags[1]) begin
                            state_sample_cycles <= time_cycles - commit_time; flags[1] <= 1;
                        end
                        if (note_trace && nonzero_voices[trace_voice[4:0]] && !flags[2]) begin
                            note_sample_cycles <= time_cycles - commit_time; flags[2] <= 1;
                        end
                    end
                    if (dac_done && dac_revision == trace_revision) begin
                        if (!flags[3]) begin
                            dac_state_cycles <= time_cycles - commit_time; flags[3] <= 1;
                        end
                        if (note_trace && dac_nonzero_voices[trace_voice[4:0]] && !flags[4]) begin
                            dac_note_cycles <= time_cycles - commit_time; flags[4] <= 1;
                        end
                    end
                    if (ack_ready && ack_matches && !flags[5]) begin
                        ack_ready_cycles <= ack_ready_time - start_time; flags[5] <= 1;
                    end
                    if (ack_done && ack_done_matches && !flags[6]) begin
                        ack_done_cycles <= ack_done_time - start_time; flags[6] <= 1;
                    end
                end
            end
        end
    end
endmodule
