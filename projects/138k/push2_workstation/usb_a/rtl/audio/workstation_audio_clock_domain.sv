`timescale 1ns/1ps

// Explicit GW5A clock-domain composition. No product command or PCM policy.
module workstation_audio_clock_domain #(
    parameter integer WINDOW_CYCLES=50000,
    parameter integer STABLE_WINDOWS=4,
    parameter integer TOLERANCE_PPM=2000,
    parameter integer LOSS_TIMEOUT_CYCLES=500,
    parameter integer STOP_LOW_CYCLES=16,
    parameter integer COUNTER_BITS=32,
    parameter integer SWITCH_TIMEOUT_CYCLES=2000000
) (
    input wire clk_50m_i, rst_ni, reference_48_i, reference_44_i,
    input wire request_i, request_44k1_i, recover_i,
    // All completion inputs are already synchronized into clk_50m_i.
    input wire frame_quiescent_i, prefill_ready_i, output_running_i,
    output wire selected_clock_o, audio_reset_no,
    output wire request_ready_o,busy_o,fault_o,accepted_o,applied_o,rejected_o,failed_o,
    output wire [2:0] reject_code_o,
    output wire [3:0] fault_code_o,clock_select_o,
    output wire quiesce_o,dac_mute_o,stream_flush_o,
    output wire active_44k1_o,active_valid_o,staged_44k1_o,
    output wire [31:0] stream_epoch_o,staged_epoch_o,
    output wire [1:0] source_qualified_o,source_present_o,
    output wire selected_qualified_o,selected_stopped_low_o,
    output wire [COUNTER_BITS-1:0] measured_48_o,measured_44_o,measured_selected_o
);
    // The public reset may assert asynchronously. All 50 MHz control consumers
    // release together after three always-on edges; source monitors additionally
    // release their own measurement counters in each raw source domain.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] control_reset_pre;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg control_reset_n;
    always @(posedge clk_50m_i or negedge rst_ni)
        if (!rst_ni) begin control_reset_pre<=0; control_reset_n<=0; end
        else begin control_reset_pre<={control_reset_pre[0],1'b1}; control_reset_n<=control_reset_pre[1]; end
    wire monitor_restart,requested_audio_reset_n;
    workstation_audio_clock_monitor #(
        .WINDOW_CYCLES(WINDOW_CYCLES),.STABLE_WINDOWS(STABLE_WINDOWS),
        .TOLERANCE_PPM(TOLERANCE_PPM),.LOSS_TIMEOUT_CYCLES(LOSS_TIMEOUT_CYCLES),
        .STOP_LOW_CYCLES(STOP_LOW_CYCLES),.COUNTER_BITS(COUNTER_BITS)
    ) reference_48_monitor (
        .clk_i(clk_50m_i),.rst_ni(control_reset_n),.source_clk_i(reference_48_i),
        .restart_i(1'b0),.expect_44k1_i(1'b0),.qualified_o(source_qualified_o[0]),
        .clock_present_o(source_present_o[0]),.stopped_low_o(),
        .window_valid_o(),.window_good_o(),.window_edges_o(measured_48_o)
    );
    workstation_audio_clock_monitor #(
        .WINDOW_CYCLES(WINDOW_CYCLES),.STABLE_WINDOWS(STABLE_WINDOWS),
        .TOLERANCE_PPM(TOLERANCE_PPM),.LOSS_TIMEOUT_CYCLES(LOSS_TIMEOUT_CYCLES),
        .STOP_LOW_CYCLES(STOP_LOW_CYCLES),.COUNTER_BITS(COUNTER_BITS)
    ) reference_44_monitor (
        .clk_i(clk_50m_i),.rst_ni(control_reset_n),.source_clk_i(reference_44_i),
        .restart_i(1'b0),.expect_44k1_i(1'b1),.qualified_o(source_qualified_o[1]),
        .clock_present_o(source_present_o[1]),.stopped_low_o(),
        .window_valid_o(),.window_good_o(),.window_edges_o(measured_44_o)
    );
    DCS #(.DCS_MODE("FALLING")) selector (
        .CLKIN0(reference_48_i),.CLKIN1(reference_44_i),.CLKIN2(1'b0),.CLKIN3(1'b0),
        .CLKSEL(clock_select_o),.SELFORCE(1'b0),.CLKOUT(selected_clock_o)
    );
    workstation_audio_clock_monitor #(
        .WINDOW_CYCLES(WINDOW_CYCLES),.STABLE_WINDOWS(STABLE_WINDOWS),
        .TOLERANCE_PPM(TOLERANCE_PPM),.LOSS_TIMEOUT_CYCLES(LOSS_TIMEOUT_CYCLES),
        .STOP_LOW_CYCLES(STOP_LOW_CYCLES),.COUNTER_BITS(COUNTER_BITS)
    ) selected_monitor (
        .clk_i(clk_50m_i),.rst_ni(control_reset_n),.source_clk_i(selected_clock_o),
        .restart_i(monitor_restart),.expect_44k1_i(clock_select_o[1]),
        .qualified_o(selected_qualified_o),.clock_present_o(),.stopped_low_o(selected_stopped_low_o),
        .window_valid_o(),.window_good_o(),.window_edges_o(measured_selected_o)
    );
    workstation_sample_rate_switch #(.TIMEOUT_CYCLES(SWITCH_TIMEOUT_CYCLES)) transaction (
        .clk_i(clk_50m_i),.rst_ni(control_reset_n),.request_i(request_i),.request_44k1_i(request_44k1_i),.recover_i(recover_i),
        .source_qualified_i(source_qualified_o),.frame_quiescent_i(frame_quiescent_i),
        .selected_clock_stopped_low_i(selected_stopped_low_o),.selected_clock_qualified_i(selected_qualified_o),
        .prefill_ready_i(prefill_ready_i),.output_running_i(output_running_i),
        .request_ready_o(request_ready_o),.busy_o(busy_o),.fault_o(fault_o),
        .accepted_o(accepted_o),.applied_o(applied_o),.rejected_o(rejected_o),.failed_o(failed_o),
        .reject_code_o(reject_code_o),.fault_code_o(fault_code_o),.quiesce_o(quiesce_o),.dac_mute_o(dac_mute_o),
        .audio_reset_no(requested_audio_reset_n),.stream_flush_o(stream_flush_o),
        .clock_monitor_restart_o(monitor_restart),.clock_select_o(clock_select_o),
        .active_44k1_o(active_44k1_o),.active_valid_o(active_valid_o),.stream_epoch_o(stream_epoch_o),
        .staged_44k1_o(staged_44k1_o),.staged_epoch_o(staged_epoch_o)
    );
    // Assertion is independent of the stopped clock; release requires three
    // genuine selected-clock edges after monitor and transaction qualification.
    wire audio_safe_n=rst_ni && requested_audio_reset_n && selected_qualified_o;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] reset_release;
    always @(posedge selected_clock_o or negedge audio_safe_n)
        if (!audio_safe_n) reset_release<=0;
        else reset_release<={reset_release[1:0],1'b1};
    assign audio_reset_no=reset_release[2];
endmodule
