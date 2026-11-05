`timescale 1ns/1ps
// W logical transaction adapter. It binds the real deferred-seal task service,
// not a model of CNN. Physical LCD serialization/electrical policy is external.
module workstation_task3_cnn_stream_w #(
    parameter bit CNN_USE_DDR_SIGNAL=1'b1,
    parameter bit CNN_USE_DDR_CQT_COEFF=1'b1,
    parameter integer IO_TIMEOUT_CYCLES=50000000,
    parameter [31:0] TASK_TIMEOUT_CYCLES=32'd3600000000
)(
    input wire clk_i,reset_ni,memory_clk_i,memory_reset_ni,backend_ready_i,
    input wire link_ready_i,transport_fault_i,panic_i,
    input wire [31:0] peer_boot_i,session_i,
    input wire desc_valid_i,
    output wire desc_ready_o,
    input wire [199:0] desc_i,
    input wire frame_valid_i,
    output wire frame_ready_o,
    input wire [191:0] frame_i,
    input wire seal_valid_i,
    output wire seal_ready_o,
    input wire [191:0] seal_i,
    input wire cancel_valid_i,
    output wire cancel_ready_o,
    input wire [127:0] cancel_i,
    output wire score_valid_o,
    input wire score_ready_i,
    output wire [166:0] score_o,
    output wire terminal_valid_o,
    input wire terminal_ready_i,
    output wire [163:0] terminal_o,
    output wire fatal_o,
    output wire [3:0] model_status_o,
    input wire model_serial_i,flash_miso_i,
    output wire flash_cs_n_o,flash_clk_o,flash_mosi_o,
    output wire memory_valid_o,memory_write_o,
    output wire [28:0] memory_address_o,
    output wire [255:0] memory_data_o,
    output wire [31:0] memory_mask_o,
    input wire memory_slot_ready_i,memory_native_accept_i,memory_response_i,
    input wire [255:0] memory_read_data_i,
    output reg [31:0] rejected_descriptors_o,stale_transactions_o,
    output wire [31:0] accepted_frames_o,committed_frames_o,replayed_frames_o
);
    // The shared request asserts immediately; each clock releases only after
    // three local edges. Never use native DDR release as control-domain CE.
    wire reset_request_n=reset_ni && memory_reset_ni;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] control_release;
    always @(posedge clk_i or negedge reset_request_n)
        if(!reset_request_n)control_release<=0;
        else control_release<={control_release[1:0],1'b1};
    wire control_reset_n=control_release[2];
    localparam [2:0] IDLE=0,START=1,START_ACK=2,ACTIVE=3,REJECT=4;
    reg [2:0] state;
    reg [199:0] descriptor;
    reg [31:0] service_generation;
    reg aborted;
    // Native DDR quarantine is immediate in task_service.broker. Only its
    // sticky fault crosses here: cancellation and result publication belong
    // to clk_i and must not consume the native combinational fault cone.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] transport_fault_control;
    always @(posedge clk_i or negedge control_reset_n)
        if(!control_reset_n)transport_fault_control<=0;
        else transport_fault_control<={transport_fault_control[0],transport_fault_i};
    wire [127:0] identity=descriptor[199:72];
    wire peer_matches=identity[127:96]==peer_boot_i && identity[95:64]==session_i;
    wire live=control_reset_n && link_ready_i && !transport_fault_control[1] && !panic_i;
    wire desc_peer=desc_i[199:168]==peer_boot_i && desc_i[167:136]==session_i;
    wire desc_shape=desc_peer && desc_i[199:168]!=0 && desc_i[167:136]!=0 &&
        desc_i[135:104]!=0 && desc_i[103:72]!=0 && desc_i[71:40]!=0 && desc_i[71:40]<=96000 && desc_i[7:0]==1;
    wire start_ready,start_accepted,start_rejected;
    wire [3:0] rejection_code;
    wire service_frame_ready,service_seal_ready,service_score_valid,service_terminal_valid;
    wire [6:0] service_score_note;
    wire [31:0] service_score_index;
    wire [3:0] service_terminal_code;
    wire frame_match=frame_i[191:64]==identity;
    wire seal_match=seal_i[191:64]==identity;
    wire cancel_match=cancel_valid_i && cancel_i==identity;
    wire seal_eligible=seal_i[63:32]<=accepted_frames_o || seal_i[63:32]>descriptor[71:40];
    wire cancel_service=state==ACTIVE && (aborted || !live || !peer_matches || cancel_match);
    assign desc_ready_o=live && state==IDLE && service_generation!=32'hffffffff && !fatal_o;
    // Stale traffic is drained without entering the real task. Current-task
    // traffic retains ready/valid backpressure from native storage commitment.
    assign frame_ready_o=control_reset_n && (!frame_match || state==IDLE || state==REJECT || !live || aborted ||
        (state==ACTIVE && service_frame_ready));
    assign seal_ready_o=control_reset_n && (!seal_match || state==IDLE || state==REJECT || !live || aborted ||
        (state==ACTIVE && seal_eligible && service_seal_ready));
    assign cancel_ready_o=control_reset_n;
    assign score_valid_o=live && peer_matches && state==ACTIVE && !aborted && service_score_valid;
    assign score_o={identity,service_score_index,service_score_note};
    assign terminal_valid_o=live && peer_matches && !aborted &&
        ((state==ACTIVE && service_terminal_valid) || state==REJECT);
    assign terminal_o={identity,state==REJECT?32'd0:service_score_index,state==REJECT?4'd13:service_terminal_code};
    wire service_terminal_ready=state==ACTIVE && service_terminal_valid &&
        (aborted || !live || !peer_matches || terminal_ready_i);
    workstation_cnn_task_service #(.DOMAIN_RESET_RELEASE(1'b1),.CNN_USE_DDR_SIGNAL(CNN_USE_DDR_SIGNAL),
        .CNN_USE_DDR_CQT_COEFF(CNN_USE_DDR_CQT_COEFF),.DEFERRED_SEAL_ENABLE(1'b1),
        .CNN_WIN_LEN(44100),.CNN_FRAME_LIMIT(8),.CNN_OCTAVE_LIMIT(9),
        .CNN_CQT_HOP_NUMERATOR(22050),.CNN_CQT_HOP_DENOMINATOR(4),
        .CNN_FEATURE_TILE_COLS(16),.CNN_COARSE_GUIDANCE(1'b1),
        .IO_TIMEOUT_CYCLES(IO_TIMEOUT_CYCLES),.TASK_TIMEOUT_CYCLES(TASK_TIMEOUT_CYCLES)) task_service(
        .clk_i(clk_i),.reset_ni(control_reset_n),.memory_clk_i(memory_clk_i),.memory_reset_ni(memory_reset_ni),
        .backend_ready_i(backend_ready_i),.transport_fault_i(transport_fault_i),
        .start_valid_i(state==START && live && peer_matches && !cancel_match),.start_ready_o(start_ready),
        .start_task_id_i(identity[63:32]),.start_generation_i(service_generation),
        .start_frames_i(descriptor[71:40]),.start_crc_i(32'd0),.start_format_i(descriptor[7:0]),
        .start_accepted_o(start_accepted),.start_rejected_o(start_rejected),.rejection_code_o(rejection_code),
        .frame_valid_i(frame_valid_i && frame_match && live && state==ACTIVE && !aborted),
        .frame_ready_o(service_frame_ready),.frame_task_id_i(identity[63:32]),.frame_generation_i(service_generation),
        .frame_index_i(frame_i[63:32]),.frame_pcm_i(frame_i[31:0]),
        .ingress_fault_i(1'b0),.seal_valid_i(seal_valid_i && seal_match && seal_eligible && live && state==ACTIVE && !aborted),
        .seal_ready_o(service_seal_ready),.seal_task_id_i(identity[63:32]),.seal_generation_i(service_generation),
        .seal_frames_i(seal_i[63:32]),.seal_crc_i(seal_i[31:0]),
        .cancel_valid_i(cancel_service),.cancel_task_id_i(identity[63:32]),.cancel_generation_i(service_generation),
        .seal_valid_o(),.seal_crc_o(),.accepted_frames_o(accepted_frames_o),.committed_frames_o(committed_frames_o),
        .replayed_frames_o(replayed_frames_o),.score_valid_o(service_score_valid),
        .score_ready_i(score_ready_i && live && peer_matches && !aborted && state==ACTIVE ||
            state==ACTIVE && (aborted || !live || !peer_matches)),
        .score_note_o(service_score_note),.score_index_o(service_score_index),.task_id_o(),.generation_o(),
        .terminal_valid_o(service_terminal_valid),.terminal_ready_i(service_terminal_ready),.terminal_code_o(service_terminal_code),
        .first_result_valid_o(),.first_result_note_o(),.first_result_frame_o(),.fatal_o(fatal_o),.model_status_o(model_status_o),
        .model_serial_i(model_serial_i),.flash_miso_i(flash_miso_i),.flash_cs_n_o(flash_cs_n_o),.flash_clk_o(flash_clk_o),
        .flash_mosi_o(flash_mosi_o),.memory_valid_o(memory_valid_o),.memory_write_o(memory_write_o),
        .memory_address_o(memory_address_o),.memory_data_o(memory_data_o),.memory_mask_o(memory_mask_o),
        .memory_slot_ready_i(memory_slot_ready_i),.memory_native_accept_i(memory_native_accept_i),
        .memory_response_i(memory_response_i),.memory_read_data_i(memory_read_data_i));
    always @(posedge clk_i or negedge control_reset_n)begin
        if(!control_reset_n)begin state<=IDLE;descriptor<=0;service_generation<=0;aborted<=0;rejected_descriptors_o<=0;stale_transactions_o<=0;end
        else begin
            if((frame_valid_i && frame_ready_o && (!frame_match || state!=ACTIVE)) ||
                (seal_valid_i && seal_ready_o && (!seal_match || state!=ACTIVE)))stale_transactions_o<=stale_transactions_o+1'b1;
            if(state!=IDLE && (!live || !peer_matches || cancel_match))aborted<=1;
            case(state)
                IDLE:if(desc_valid_i && desc_ready_o)begin
                    descriptor<=desc_i;aborted<=0;
                    if(!desc_shape)begin rejected_descriptors_o<=rejected_descriptors_o+1'b1;state<=REJECT;end
                    else begin service_generation<=service_generation+1'b1;state<=START;end
                end
                START:if(!live || !peer_matches || cancel_match)state<=IDLE;
                    else if(start_ready)state<=START_ACK;
                START_ACK:if(start_accepted)state<=ACTIVE;
                    else if(start_rejected)begin rejected_descriptors_o<=rejected_descriptors_o+1'b1;state<=REJECT;end
                ACTIVE:if(service_terminal_valid && service_terminal_ready)state<=IDLE;
                REJECT:if(!live || !peer_matches || (terminal_valid_o && terminal_ready_i))state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
