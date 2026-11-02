`timescale 1ns/1ps
// Complete SAME-CLOCK logical paired composition. This explicitly connects
// final-tap recording and remote phone PCM1/clock transactions to their real
// subsystem boundaries. Board integration replaces the typed direct wires with
// the validated bounded hub/transport; this module is not a physical CDC design.
module workstation_task3_audio_exchange #(
    parameter integer RECORD_FIFO_ADDRESS_BITS=8,
    parameter integer RECORD_SOURCE_LEASE_CYCLES=200000,
    parameter integer OWNER_TIMEOUT_CYCLES=10000,
    parameter integer ROUND_TRIP_TIMEOUT_CYCLES=50000
) (
    input wire clk_i,reset_ni,link_validated_i,panic_i,
    input wire [31:0] boot_i,session_i,generation_i,
    input wire record_arm_valid_i,
    output wire record_arm_ready_o,record_arm_accepted_o,record_arm_rejected_o,
    input wire [31:0] record_epoch_i,record_first_sequence_i,
    input wire record_cancel_i,record_object_idle_i,
    input wire m_final_frame_valid_i,m_final_frame44_i,m_final_frame_error_i,
    input wire [31:0] m_final_frame_epoch_i,m_final_frame_sequence_i,m_final_frame_pcm_i,
    output wire w_record_pcm_valid_o,w_record_source_allowed_o,
    output wire [31:0] w_record_pcm_o,w_record_observer_sequence_o,w_record_physical_sequence_o,
    output wire record_fault_o,
    output wire [3:0] record_export_failure_o,record_ingress_failure_o,
    output wire [31:0] record_captured_frames_o,record_delivered_frames_o,
    input wire phone_arm_valid_i,
    output wire phone_arm_ready_o,phone_arm_accepted_o,phone_arm_rejected_o,
    input wire phone_cancel_i,m_phone_owner_idle_i,
    // Existing W PCM1 and clock APB command CDCs; lane0=PCM1, lane1=clock.
    // Responses complete the ORIGINAL caller, never a local substitute owner.
    input wire [1:0] w_command_valid_i,w_command_write_i,
    input wire [23:0] w_command_address_i,
    input wire [63:0] w_command_data_i,
    input wire [7:0] w_command_strobes_i,
    output wire [1:0] w_command_ready_o,w_response_error_o,
    output wire [63:0] w_response_data_o,
    // Gate the EXISTING M PCM1 owner's session_live with this output.
    output wire m_phone_owner_live_o,
    output wire m_pcm_command_valid_o,m_clock_command_valid_o,m_command_write_o,
    output wire [11:0] m_command_address_o,
    output wire [31:0] m_command_data_o,
    output wire [3:0] m_command_strobes_o,
    input wire m_pcm_command_ready_i,m_pcm_response_error_i,
    input wire [31:0] m_pcm_response_data_i,
    input wire m_clock_command_ready_i,m_clock_response_error_i,
    input wire [31:0] m_clock_response_data_i,
    output wire phone_fault_o,
    output wire [3:0] phone_proxy_failure_o,phone_ingress_failure_o
);
    wire record_arm_tx,record_arm_ready,record_remote_accepted,record_remote_rejected,record_local_rejected;
    wire record_frame_tx,record_frame_ready,record_cancel_tx;
    wire [31:0] record_boot,record_session,record_generation,record_epoch,record_first;
    wire [31:0] record_tx_epoch,record_tx_sequence,record_tx_pcm;
    wire record_tx44,record_tx_error,record_export_fault,record_ingress_fault;
    wire record_ingress_ready;
    reg record_delivery_valid;
    reg [97:0] record_delivery;
    // Convert held transport valid to the pulse/credit ingress contract with a
    // registered one-frame reservation. No combinational valid/ready loop is
    // allowed through ingress's immediate error gate. No other producer can
    // spend this reserved credit before the following delivery edge.
    assign record_frame_ready=!record_delivery_valid && record_ingress_ready;
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin record_delivery_valid<=0;record_delivery<=0;end
        else begin
            record_delivery_valid<=0;
            if(record_frame_tx && record_frame_ready)begin
                record_delivery_valid<=1;
                record_delivery<={record_tx44,record_tx_error,record_tx_epoch,record_tx_sequence,record_tx_pcm};
            end
        end
    end
    wire record_export_armed,record_ingress_armed;
    workstation_task3_final_tap_export #(.FIFO_ADDRESS_BITS(RECORD_FIFO_ADDRESS_BITS)) final_tap(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(link_validated_i),.panic_i(panic_i),
        .arm_valid_i(record_arm_valid_i),.arm_ready_o(record_arm_ready_o),
        .arm_boot_i(boot_i),.arm_session_i(session_i),.arm_generation_i(generation_i),
        .arm_physical_epoch_i(record_epoch_i),.arm_first_sequence_i(record_first_sequence_i),
        .arm_accepted_o(),.arm_rejected_o(record_local_rejected),
        .arm_tx_valid_o(record_arm_tx),.arm_tx_ready_i(record_arm_ready),
        .arm_result_accepted_i(record_remote_accepted),.arm_result_rejected_i(record_remote_rejected),
        .boot_o(record_boot),.session_o(record_session),.generation_o(record_generation),
        .physical_epoch_o(record_epoch),.first_sequence_o(record_first),
        .cancel_valid_i(record_cancel_i),.cancel_session_i(session_i),.cancel_generation_i(generation_i),
        .frame_valid_i(m_final_frame_valid_i),.frame_44k1_i(m_final_frame44_i),.frame_error_i(m_final_frame_error_i),
        .frame_epoch_i(m_final_frame_epoch_i),.frame_sequence_i(m_final_frame_sequence_i),.frame_pcm_i(m_final_frame_pcm_i),
        .frame_tx_valid_o(record_frame_tx),.frame_tx_ready_i(record_frame_ready),
        .frame_tx_epoch_o(record_tx_epoch),.frame_tx_sequence_o(record_tx_sequence),.frame_tx_pcm_o(record_tx_pcm),
        .frame_tx_44k1_o(record_tx44),.frame_tx_error_o(record_tx_error),
        .cancel_tx_valid_o(record_cancel_tx),.cancel_tx_ready_i(1'b1),
        .armed_o(record_export_armed),.fault_o(record_export_fault),.failure_code_o(record_export_failure_o),
        .queued_frames_o(),.captured_frames_o(record_captured_frames_o),.exported_frames_o());
    assign record_arm_accepted_o=record_remote_accepted;
    assign record_arm_rejected_o=record_local_rejected || record_remote_rejected;
    workstation_task3_record_ingress #(.FIFO_ADDRESS_BITS(RECORD_FIFO_ADDRESS_BITS),
        .SOURCE_LEASE_CYCLES(RECORD_SOURCE_LEASE_CYCLES)) recording_ingress(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(link_validated_i),.panic_i(panic_i),.transport_fault_i(1'b0),
        .object_idle_i(record_object_idle_i),.cancel_valid_i(record_cancel_tx),
        .cancel_session_i(record_session),.cancel_generation_i(record_generation),
        .arm_valid_i(record_arm_tx),.arm_ready_o(record_arm_ready),
        .arm_session_i(record_session),.arm_generation_i(record_generation),
        .arm_physical_epoch_i(record_epoch),.arm_first_sequence_i(record_first),.arm_format_i(8'd1),
        .arm_accepted_o(record_remote_accepted),.arm_rejected_o(record_remote_rejected),
        .frame_valid_i(record_delivery_valid),.frame_ready_o(record_ingress_ready),
        .frame_session_i(record_session),.frame_generation_i(record_generation),.frame_physical_epoch_i(record_delivery[95:64]),
        .frame_sequence_i(record_delivery[63:32]),.frame_pcm_i(record_delivery[31:0]),
        .frame_44k1_i(record_delivery[97]),.frame_error_i(record_delivery[96]),
        .pcm_valid_o(w_record_pcm_valid_o),.source_allowed_o(w_record_source_allowed_o),.pcm_pair_o(w_record_pcm_o),
        .pcm_sequence_o(w_record_observer_sequence_o),.physical_sequence_o(w_record_physical_sequence_o),
        .session_o(),.generation_o(),.physical_epoch_o(),.armed_o(record_ingress_armed),.fault_o(record_ingress_fault),
        .failure_code_o(record_ingress_failure_o),.queued_frames_o(),.accepted_frames_o(),.delivered_frames_o(record_delivered_frames_o));
    assign record_fault_o=record_export_fault || record_ingress_fault;
    wire phone_arm_tx,phone_arm_ready,phone_arm_accepted,phone_arm_rejected,phone_cancel_tx;
    wire [31:0] phone_boot,phone_session,phone_generation;
    wire request_valid,request_ready,request_target,request_write;
    wire [31:0] request_sequence,request_data;
    wire [11:0] request_address;
    wire [3:0] request_strobes;
    wire response_valid,response_ready,response_error;
    wire [31:0] response_boot,response_session,response_generation,response_sequence,response_data;
    wire phone_proxy_armed,phone_proxy_fault,phone_ingress_armed,phone_ingress_fault;
    wire w_mux_valid,w_mux_target,w_mux_write,w_mux_ready,w_mux_error;
    wire [11:0] w_mux_address;
    wire [31:0] w_mux_data,w_mux_response;
    wire [3:0] w_mux_strobes;
    workstation_task3_phone_command_mux phone_mux(
        .clk_i(clk_i),.reset_ni(reset_ni),.valid_i(w_command_valid_i),.write_i(w_command_write_i),
        .address_i(w_command_address_i),.data_i(w_command_data_i),.strobes_i(w_command_strobes_i),
        .ready_o(w_command_ready_o),.response_error_o(w_response_error_o),.response_data_o(w_response_data_o),
        .valid_o(w_mux_valid),.target_o(w_mux_target),.write_o(w_mux_write),.address_o(w_mux_address),.data_o(w_mux_data),
        .strobes_o(w_mux_strobes),.ready_i(w_mux_ready),.response_error_i(w_mux_error),.response_data_i(w_mux_response));
    workstation_task3_phone_command_proxy #(.ROUND_TRIP_TIMEOUT_CYCLES(ROUND_TRIP_TIMEOUT_CYCLES)) phone_proxy(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(link_validated_i),.panic_i(panic_i),
        .arm_valid_i(phone_arm_valid_i),.arm_ready_o(phone_arm_ready_o),
        .arm_boot_i(boot_i),.arm_session_i(session_i),.arm_generation_i(generation_i),
        .arm_accepted_o(phone_arm_accepted_o),.arm_rejected_o(phone_arm_rejected_o),
        .arm_tx_valid_o(phone_arm_tx),.arm_tx_ready_i(phone_arm_ready),
        .arm_result_accepted_i(phone_arm_accepted),.arm_result_rejected_i(phone_arm_rejected),
        .boot_o(phone_boot),.session_o(phone_session),.generation_o(phone_generation),
        .cancel_tx_valid_o(phone_cancel_tx),.cancel_tx_ready_i(1'b1),
        .cancel_valid_i(phone_cancel_i),.cancel_session_i(session_i),.cancel_generation_i(generation_i),
        .cpu_command_valid_i(w_mux_valid),.cpu_command_target_i(w_mux_target),.cpu_command_write_i(w_mux_write),
        .cpu_command_address_i(w_mux_address),.cpu_command_data_i(w_mux_data),.cpu_command_strobes_i(w_mux_strobes),
        .cpu_command_ready_o(w_mux_ready),.cpu_response_data_o(w_mux_response),.cpu_response_error_o(w_mux_error),
        .request_valid_o(request_valid),.request_ready_i(request_ready),.request_sequence_o(request_sequence),
        .request_target_o(request_target),.request_write_o(request_write),.request_address_o(request_address),
        .request_data_o(request_data),.request_strobes_o(request_strobes),
        .response_valid_i(response_valid),.response_ready_o(response_ready),
        .response_boot_i(response_boot),.response_session_i(response_session),.response_generation_i(response_generation),
        .response_sequence_i(response_sequence),.response_data_i(response_data),.response_error_i(response_error),
        .armed_o(phone_proxy_armed),.fault_o(phone_proxy_fault),.failure_code_o(phone_proxy_failure_o),.completed_commands_o());
    wire command_valid,command_target;
    workstation_task3_phone_command_ingress #(.OWNER_TIMEOUT_CYCLES(OWNER_TIMEOUT_CYCLES)) phone_ingress(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(link_validated_i),.panic_i(panic_i),.owner_idle_i(m_phone_owner_idle_i),
        .arm_valid_i(phone_arm_tx),.arm_ready_o(phone_arm_ready),
        .arm_boot_i(phone_boot),.arm_session_i(phone_session),.arm_generation_i(phone_generation),
        .arm_accepted_o(phone_arm_accepted),.arm_rejected_o(phone_arm_rejected),
        .cancel_valid_i(phone_cancel_tx),.cancel_session_i(phone_session),.cancel_generation_i(phone_generation),
        .request_valid_i(request_valid),.request_ready_o(request_ready),
        .request_boot_i(phone_boot),.request_session_i(phone_session),.request_generation_i(phone_generation),
        .request_sequence_i(request_sequence),.request_target_i(request_target),.request_write_i(request_write),
        .request_address_i(request_address),.request_data_i(request_data),.request_strobes_i(request_strobes),
        .response_valid_o(response_valid),.response_ready_i(response_ready),
        .response_boot_o(response_boot),.response_session_o(response_session),.response_generation_o(response_generation),
        .response_sequence_o(response_sequence),.response_data_o(response_data),.response_error_o(response_error),
        .owner_live_o(m_phone_owner_live_o),.command_valid_o(command_valid),.command_target_o(command_target),
        .command_ready_i(command_target?m_clock_command_ready_i:m_pcm_command_ready_i),
        .command_write_o(m_command_write_o),.command_address_o(m_command_address_o),.command_data_o(m_command_data_o),.command_strobes_o(m_command_strobes_o),
        .command_response_data_i(command_target?m_clock_response_data_i:m_pcm_response_data_i),
        .command_response_error_i(command_target?m_clock_response_error_i:m_pcm_response_error_i),
        .armed_o(phone_ingress_armed),.fault_o(phone_ingress_fault),.failure_code_o(phone_ingress_failure_o),
        .accepted_commands_o(),.applied_commands_o());
    assign m_pcm_command_valid_o=command_valid && !command_target;
    assign m_clock_command_valid_o=command_valid && command_target;
    assign phone_fault_o=phone_proxy_fault || phone_ingress_fault;
endmodule
