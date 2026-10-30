`timescale 1ns/1ps
`default_nettype none
// Production R00 composition: physical completed frame -> bounded CDC ->
// CPU object service -> native-accept bridge -> the real owner8 DDR slot.
module workstation_recording_runtime #(
    parameter integer CAPACITY_FRAMES=16384,FIFO_ADDRESS_BITS=9,
    parameter integer DDR_BUDGET_CYCLES=10000,SOURCE_GAP_CYCLES=400000
)(
    input wire reset_ni,source_clk_i,memory_clk_i,control_clk_i,backend_ready_i,
    input wire frame_valid_i,frame_error_i,frame_44k1_i,
    input wire [31:0] frame_epoch_i,frame_sequence_i,frame_pcm_i,
    input wire pclk,preset_n,psel,penable,pwrite,
    input wire [11:0] paddr,
    input wire [31:0] pwdata,
    input wire [3:0] pstrb,
    output wire pready,pslverr,
    output wire [31:0] prdata,
    input wire seal_hold_i,seal_request_i,
    output wire seal_ready_o,seal_done_o,seal_failed_o,
    output wire [3:0] seal_failure_code_o,
    output wire recording_valid_o,recording_write_o,
    output wire [28:0] recording_address_o,
    output wire [255:0] recording_data_o,
    output wire [31:0] recording_mask_o,
    input wire recording_ready_i,recording_response_i,recording_native_accept_i,
    input wire [255:0] recording_read_data_i,
    input wire transport_fault_i,
    output wire native_protocol_fault_o,
    output wire [3:0] object_state_o,object_failure_o,
    output wire [31:0] object_frames_o,committed_frames_o,
    output wire capture_o
);
    wire pcm_valid,pcm44,pcm_error,pcm_gap,pcm_loss;
    wire [31:0] pcm_epoch,pcm_sequence,pcm,drop_count;
    workstation_pcm_observation_bridge #(.FIFO_ADDRESS_BITS(4)) pcm_cdc(
        .reset_ni(reset_ni),.source_clk_i(source_clk_i),.destination_clk_i(memory_clk_i),
        .frame_valid_i(frame_valid_i),.frame_44k1_i(frame_44k1_i),.frame_error_i(frame_error_i),
        .frame_epoch_i(frame_epoch_i),.frame_sequence_i(frame_sequence_i),.frame_pcm_i(frame_pcm_i),
        .source_drop_count_o(),.destination_drop_count_o(drop_count),.destination_drop_event_o(),
        .destination_loss_seen_o(pcm_loss),.frame_valid_o(pcm_valid),.frame_ready_i(1'b1),
        .frame_44k1_o(pcm44),.frame_error_o(pcm_error),.frame_epoch_o(pcm_epoch),
        .frame_sequence_o(pcm_sequence),.frame_pcm_o(pcm),.left_q31_o(),.right_q31_o(),
        .stream_change_o(),.sequence_gap_o(pcm_gap));
    wire command_reset,command_valid,command_ready,command_write,response_error;
    wire [11:0] command_address;
    wire [31:0] command_data,response_data;
    wire [3:0] command_strobes;
    gw138k_apb_cdc commands(
        .reset_n(preset_n && reset_ni),.pclk(pclk),.audio_clk(memory_clk_i),
        .psel(psel),.penable(penable),.pwrite(pwrite),.paddr(paddr),.pwdata(pwdata),.pstrb(pstrb),
        .pready(pready),.pslverr(pslverr),.prdata(prdata),.command_reset_n(command_reset),
        .command_valid(command_valid),.command_ready(command_ready),.command_write(command_write),
        .command_address(command_address),.command_data(command_data),.command_strobes(command_strobes),
        .response_data(response_data),.response_error(response_error));
    wire seal_hold,seal_request,seal_ready,seal_done,seal_failed;
    wire [3:0] seal_failure;
    workstation_recording_seal_bridge seal_cdc(
        .reset_ni(reset_ni),.source_clk_i(control_clk_i),.destination_clk_i(memory_clk_i),
        .request_i(seal_request_i),.hold_i(seal_hold_i),.ready_o(seal_ready_o),
        .done_o(seal_done_o),.failed_o(seal_failed_o),.failure_code_o(seal_failure_code_o),
        .destination_hold_o(seal_hold),.destination_request_o(seal_request),
        .destination_ready_i(seal_ready),.destination_done_i(seal_done),.destination_failed_i(seal_failed),
        .destination_failure_code_i(seal_failure));
    wire ddr_valid,ddr_write,ddr_ready,bridge_fault;
    wire [28:0] ddr_address;
    wire [255:0] ddr_data;
    wire [31:0] ddr_mask;
    assign recording_write_o=ddr_write,recording_address_o=ddr_address;
    assign recording_data_o=ddr_data,recording_mask_o=ddr_mask;
    workstation_recording_ddr_native_bridge native_commit(
        .clk_i(memory_clk_i),.rst_ni(reset_ni),.published_valid_i(ddr_valid),
        .slot_ready_i(recording_ready_i),.native_accept_i(recording_native_accept_i),
        .transport_fault_i(transport_fault_i),.slot_valid_o(recording_valid_o),
        .native_ready_o(ddr_ready),.transport_fault_o(bridge_fault),.submitted_o(),.protocol_fault_o(native_protocol_fault_o));
    workstation_recording_ddr_service #(.CAPACITY_FRAMES(CAPACITY_FRAMES),.FIFO_ADDRESS_BITS(FIFO_ADDRESS_BITS),
        .DDR_BUDGET_CYCLES(DDR_BUDGET_CYCLES),.SOURCE_GAP_CYCLES(SOURCE_GAP_CYCLES)) service(
        .clk_i(memory_clk_i),.reset_ni(reset_ni),.command_reset_ni(command_reset),.backend_ready_i(backend_ready_i),
        .command_valid_i(command_valid),.command_write_i(command_write),.command_address_i(command_address),
        .command_data_i(command_data),.command_strobes_i(command_strobes),.command_ready_o(command_ready),
        .response_error_o(response_error),.response_data_o(response_data),
        .pcm_valid_i(pcm_valid),.pcm_44k1_i(pcm44),.pcm_error_i(pcm_error || pcm_gap),.pcm_loss_i(pcm_loss),
        .pcm_epoch_i(pcm_epoch),.pcm_sequence_i(pcm_sequence),.pcm_pair_i({pcm[15:0],pcm[31:16]}),.pcm_drop_count_i(drop_count),
        .seal_hold_i(seal_hold),.seal_request_i(seal_request),.seal_ready_o(seal_ready),
        .seal_done_o(seal_done),.seal_failed_o(seal_failed),.seal_failure_code_o(seal_failure),
        .ddr_valid_o(ddr_valid),.ddr_write_o(ddr_write),.ddr_address_o(ddr_address),.ddr_data_o(ddr_data),.ddr_mask_o(ddr_mask),
        .ddr_ready_i(ddr_ready),.ddr_response_i(recording_response_i),.ddr_read_data_i(recording_read_data_i),
        .transport_fault_i(transport_fault_i || bridge_fault),.object_state_o(object_state_o),
        .object_failure_o(object_failure_o),.object_frames_o(object_frames_o),.committed_frames_o(committed_frames_o),
        .capture_o(capture_o));
endmodule
`default_nettype wire
