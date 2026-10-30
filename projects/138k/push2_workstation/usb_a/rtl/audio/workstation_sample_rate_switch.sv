`timescale 1ns/1ps

// Always-on control transaction only. The board owns DCS, frequency monitors,
// complete-frame quiescence, local reset distribution and tagged PCM delivery.
module workstation_sample_rate_switch #(
    parameter integer TIMEOUT_CYCLES = 1000000,
    parameter bit DEFAULT_44K1 = 0,
    parameter bit RESERVE_ZERO_EPOCH = 0,
    parameter [31:0] INITIAL_STREAM_EPOCH = RESERVE_ZERO_EPOCH ? 32'd1 : 32'd0
) (
    input wire clk_i, rst_ni,
    // Single-cycle request strobes; busy requests are rejected, never queued.
    input wire request_i, request_44k1_i, recover_i,
    input wire [1:0] source_qualified_i,
    input wire frame_quiescent_i,
    input wire selected_clock_stopped_low_i, selected_clock_qualified_i,
    input wire prefill_ready_i, output_running_i,
    output wire request_ready_o, busy_o, fault_o,
    output reg accepted_o, applied_o, rejected_o, failed_o,
    output reg [2:0] reject_code_o,
    output reg [3:0] fault_code_o,
    output reg quiesce_o, dac_mute_o, stream_flush_o,
    output reg audio_reset_no,
    output wire clock_monitor_restart_o,
    // Connect to GW5A DCS CLKSEL, DCS_MODE="FALLING", SELFORCE=0.
    output reg [3:0] clock_select_o,
    output reg active_44k1_o, active_valid_o,
    output reg [31:0] stream_epoch_o,
    output wire staged_44k1_o,
    output wire [31:0] staged_epoch_o
);
    localparam [3:0] BOOT_SELECT=0, RUN=1, QUIESCE=2, STOP_START=3,
        STOP_WAIT=4, SELECT_TARGET=5, QUALIFY=6, PREFILL=7, FAULT=8, RESUME=9;
    localparam [2:0] REJECT_NONE=0, REJECT_BUSY=1, REJECT_UNQUALIFIED=2,
        REJECT_FAULT=3;
    localparam [3:0] FAULT_NONE=0, FAULT_QUIESCE_TIMEOUT=1,
        FAULT_STOP_TIMEOUT=2, FAULT_QUALIFY_TIMEOUT=3,
        FAULT_TARGET_LOST=4, FAULT_PREFILL_TIMEOUT=5, FAULT_RUNNING_LOST=6,
        FAULT_RESUME_TIMEOUT=7;
    localparam integer TIMER_BITS = $clog2(TIMEOUT_CYCLES+1);
    reg [3:0] state;
    reg [TIMER_BITS-1:0] timer;
    reg pending_44k1;
    reg [31:0] pending_epoch;
    reg booting;
    wire target_qualified = source_qualified_i[pending_44k1];
    wire running_qualified = source_qualified_i[active_44k1_o] && selected_clock_qualified_i;
    wire timed_out = timer == TIMER_BITS'(TIMEOUT_CYCLES-1);

    // Explicit v1.1 metadata policy. The clock transaction remains the only
    // stream epoch owner; display and command observers never remap its value.
    wire [31:0] following_epoch=RESERVE_ZERO_EPOCH && stream_epoch_o==32'hffffffff
        ? 32'd1 : stream_epoch_o+1'b1;
    initial begin
        if (TIMEOUT_CYCLES < 4) $fatal(1, "TIMEOUT_CYCLES must be >= 4");
        if (RESERVE_ZERO_EPOCH && INITIAL_STREAM_EPOCH==0)
            $fatal(1, "Reserved-zero epoch requires a nonzero initial identity");
    end

    assign request_ready_o = state == RUN && running_qualified;
    assign busy_o = state != RUN && state != FAULT;
    assign fault_o = state == FAULT;
    assign clock_monitor_restart_o = state == BOOT_SELECT || state == STOP_START || state == SELECT_TARGET;
    assign staged_44k1_o = pending_44k1;
    assign staged_epoch_o = pending_epoch;

    // Publish crossing control levels from the same target state as the FSM.
    // Multi-bit state decode must not become an asynchronous CDC source: e.g.
    // PREFILL 7 -> RESUME 9 may transiently decode STOP/QUALIFY while bits settle.
    // One transition owner keeps all three outputs aligned without another
    // state register or a one-control-cycle lag.
    // During QUIESCE the serializer finishes its whole frame and acknowledges
    // its own boundary mute. Direct DAC mute/reset starts only after that ack.
    task automatic transition_to(input [3:0] target_state);
        begin
            state <= target_state;
            quiesce_o <= target_state != RUN && target_state != PREFILL && target_state != RESUME;
            dac_mute_o <= target_state != RUN && target_state != QUIESCE && target_state != RESUME;
            stream_flush_o <= target_state != RUN && target_state != QUIESCE && target_state != PREFILL && target_state != RESUME;
        end
    endtask

    task automatic enter_fault(input [3:0] code);
        begin
            transition_to(FAULT);
            timer <= 0;
            fault_code_o <= code;
            active_valid_o <= 0;
            failed_o <= 1;
            booting <= 0;
            audio_reset_no <= 0;
            clock_select_o <= 0;
        end
    endtask

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            transition_to(BOOT_SELECT);
            timer <= 0;
            pending_44k1 <= DEFAULT_44K1;
            pending_epoch <= INITIAL_STREAM_EPOCH;
            booting <= 1;
            active_44k1_o <= DEFAULT_44K1;
            active_valid_o <= 0;
            stream_epoch_o <= INITIAL_STREAM_EPOCH;
            accepted_o <= 0; applied_o <= 0; rejected_o <= 0; failed_o <= 0;
            reject_code_o <= REJECT_NONE;
            fault_code_o <= FAULT_NONE;
            audio_reset_no <= 0;
            clock_select_o <= DEFAULT_44K1 ? 4'b0010 : 4'b0001;
        end else begin
            accepted_o <= 0; applied_o <= 0; rejected_o <= 0; failed_o <= 0;
            reject_code_o <= REJECT_NONE;
            if (request_i && state != RUN) begin
                rejected_o <= 1;
                reject_code_o <= state == FAULT ? REJECT_FAULT : REJECT_BUSY;
            end
            case (state)
                BOOT_SELECT: begin transition_to(QUALIFY); timer <= 0; end
                RUN: begin
                    timer <= 0;
                    if (!running_qualified) begin
                        if (request_i) begin rejected_o <= 1; reject_code_o <= REJECT_UNQUALIFIED; end
                        enter_fault(FAULT_RUNNING_LOST);
                    end else if (request_i) begin
                        if (!source_qualified_i[request_44k1_i]) begin
                            rejected_o <= 1; reject_code_o <= REJECT_UNQUALIFIED;
                        end else begin
                            accepted_o <= 1;
                            if (request_44k1_i == active_44k1_o) applied_o <= 1;
                            else begin
                                pending_44k1 <= request_44k1_i;
                                pending_epoch <= following_epoch;
                                booting <= 0;
                                transition_to(QUIESCE);
                            end
                        end
                    end
                end
                QUIESCE: begin
                    // Losing an unselected target does not justify cutting an
                    // otherwise healthy current serial frame in half.
                    if (!running_qualified) enter_fault(FAULT_RUNNING_LOST);
                    else if (frame_quiescent_i) begin
                        if (!target_qualified) enter_fault(FAULT_TARGET_LOST);
                        else begin
                            transition_to(STOP_START); timer <= 0; active_valid_o <= 0;
                            audio_reset_no <= 0; clock_select_o <= 0;
                        end
                    end else if (timed_out) enter_fault(FAULT_QUIESCE_TIMEOUT);
                    else timer <= timer + 1'b1;
                end
                STOP_START: begin transition_to(STOP_WAIT); timer <= 0; end
                STOP_WAIT: begin
                    if (!target_qualified) enter_fault(FAULT_TARGET_LOST);
                    else if (selected_clock_stopped_low_i) begin
                        transition_to(SELECT_TARGET); timer <= 0;
                        clock_select_o <= pending_44k1 ? 4'b0010 : 4'b0001;
                    end
                    else if (timed_out) enter_fault(FAULT_STOP_TIMEOUT);
                    else timer <= timer + 1'b1;
                end
                SELECT_TARGET: begin transition_to(QUALIFY); timer <= 0; end
                QUALIFY: begin
                    if (!booting && !target_qualified) enter_fault(FAULT_TARGET_LOST);
                    else if (target_qualified && selected_clock_qualified_i) begin
                        transition_to(PREFILL); timer <= 0; audio_reset_no <= 1;
                    end
                    else if (timed_out) enter_fault(FAULT_QUALIFY_TIMEOUT);
                    else timer <= timer + 1'b1;
                end
                PREFILL: begin
                    if (!target_qualified || !selected_clock_qualified_i) enter_fault(FAULT_TARGET_LOST);
                    else if (prefill_ready_i) begin
                        transition_to(RESUME);
                        timer <= 0;
                    end else if (timed_out) enter_fault(FAULT_PREFILL_TIMEOUT);
                    else timer <= timer + 1'b1;
                end
                RESUME: begin
                    if (!target_qualified || !selected_clock_qualified_i) enter_fault(FAULT_TARGET_LOST);
                    else if (output_running_i) begin
                        active_44k1_o <= pending_44k1;
                        stream_epoch_o <= pending_epoch;
                        active_valid_o <= 1;
                        applied_o <= !booting;
                        booting <= 0;
                        fault_code_o <= FAULT_NONE;
                        transition_to(RUN);
                        timer <= 0;
                    end else if (timed_out) enter_fault(FAULT_RESUME_TIMEOUT);
                    else timer <= timer + 1'b1;
                end
                FAULT: begin
                    timer <= 0;
                    // Retry the last committed rate. A stopped-high old input
                    // must resume before DCS can acknowledge a safe low stop.
                    if (recover_i && source_qualified_i[active_44k1_o]) begin
                        pending_44k1 <= active_44k1_o;
                        pending_epoch <= following_epoch;
                        booting <= 0;
                        transition_to(STOP_START);
                    end
                end
                default: enter_fault(FAULT_RUNNING_LOST);
            endcase
        end
    end
endmodule
