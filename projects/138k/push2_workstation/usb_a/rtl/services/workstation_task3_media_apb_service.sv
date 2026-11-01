`timescale 1ns/1ps
// One clk_i command at a time after gw138k_apb_cdc. Every action either fires
// on this handshake or returns an error immediately; APB never waits for a CNN
// result, a packet credit or DDR. No register enables the unverified LCD link.
module workstation_task3_media_apb_service(
    input wire clk_i,reset_ni,owner_reset_ni,
    input wire command_valid_i,command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output wire command_ready_o,
    output reg response_error_o,
    output reg [31:0] response_data_o,
    input wire backend_ready_i,lcd_link_ready_i,
    output wire start_valid_o,
    input wire start_ready_i,start_accepted_i,start_rejected_i,
    input wire [3:0] rejection_code_i,
    output reg [31:0] task_id_o,generation_o,frames_o,crc_o,
    output reg [7:0] format_o,
    output wire frame_valid_o,
    input wire frame_ready_i,
    output reg [31:0] frame_index_o,frame_pcm_o,
    output wire ingress_fault_o,cancel_valid_o,
    input wire score_valid_i,
    output wire score_ready_o,
    input wire [6:0] score_note_i,
    input wire [31:0] score_index_i,
    input wire terminal_valid_i,
    output wire terminal_ready_o,
    input wire [3:0] terminal_code_i,model_status_i,
    input wire fatal_i,seal_valid_i,
    input wire [31:0] seal_crc_i,accepted_frames_i,committed_frames_i,replayed_frames_i,
    input wire [31:0] active_task_id_i,active_generation_i,
    input wire first_result_valid_i,
    input wire [6:0] first_result_note_i,
    input wire [15:0] first_result_frame_i,
    // Explicit software transport aperture for M final-tap packets. It is
    // closed after reset; opening it does not assert lcd_link_ready_i or claim
    // a physically connected M source. The board shell never selects W's tap.
    output reg tap_open_o,
    output wire tap_arm_valid_o,
    input wire tap_arm_ready_i,tap_arm_accepted_i,tap_arm_rejected_i,
    output reg [31:0] tap_session_o,tap_generation_o,tap_epoch_o,tap_first_sequence_o,
    output reg [7:0] tap_format_o,
    output wire tap_frame_valid_o,
    input wire tap_frame_ready_i,
    output reg [31:0] tap_frame_session_o,tap_frame_generation_o,tap_frame_epoch_o,tap_frame_sequence_o,tap_frame_pcm_o,
    output reg tap_frame_44k1_o,tap_frame_error_o,
    output wire tap_cancel_valid_o,tap_panic_o,
    input wire tap_armed_i,tap_fault_i,
    input wire [3:0] tap_failure_i,
    input wire [8:0] tap_queued_i,
    input wire [31:0] tap_accepted_i,tap_delivered_i
);
    wire aligned=command_address_i[1:0]==0 && (!command_write_i || command_strobes_i==4'hf);
    wire access=reset_ni && owner_reset_ni && command_valid_i;
    wire write=access && command_write_i && !response_error_o;
    // Attempts must not depend on response_error/credit: an invalid packet
    // itself fences the ingress, whose ready drops combinationally.
    wire action=access && command_write_i && aligned && command_data_i==1;
    assign command_ready_o=1'b1;
    assign start_valid_o=action && command_address_i==12'h024 && start_ready_i;
    assign frame_valid_o=action && command_address_i==12'h030 && frame_ready_i;
    assign cancel_valid_o=action && command_address_i==12'h034;
    assign score_ready_o=action && command_address_i==12'h040;
    assign terminal_ready_o=action && command_address_i==12'h048;
    assign ingress_fault_o=!owner_reset_ni || tap_panic_o;
    assign tap_arm_valid_o=action && command_address_i==12'h114 && tap_open_o && tap_arm_ready_i;
    assign tap_frame_valid_o=action && command_address_i==12'h134;
    assign tap_cancel_valid_o=action && command_address_i==12'h138;
    assign tap_panic_o=action && command_address_i==12'h150;
    reg [31:0] start_accept_count,start_reject_count,last_rejection,seal_count;
    reg [31:0] tap_arm_accept_count,tap_arm_reject_count;
    always @*begin
        response_data_o=0;response_error_o=!aligned || !owner_reset_ni;
        case(command_address_i)
            12'h000:response_data_o=32'h574d3301;
            12'h004:response_data_o={20'd0,model_status_i,lcd_link_ready_i,tap_open_o,
                fatal_i,terminal_valid_i,score_valid_i,frame_ready_i,start_ready_i,backend_ready_i};
            12'h010:response_data_o=task_id_o;
            12'h014:response_data_o=generation_o;
            12'h018:response_data_o=frames_o;
            12'h01c:response_data_o=crc_o;
            12'h020:response_data_o={24'd0,format_o};
            12'h024:if(command_write_i && (!start_ready_i || command_data_i!=1))response_error_o=1;
            12'h028:response_data_o=frame_index_o;
            12'h02c:response_data_o=frame_pcm_o;
            12'h030:if(command_write_i && (!frame_ready_i || command_data_i!=1))response_error_o=1;
            12'h034:if(command_write_i && command_data_i!=1)response_error_o=1;
            12'h038:response_data_o={score_valid_i,24'd0,score_note_i};
            12'h03c:response_data_o=score_index_i;
            12'h040:if(command_write_i && (!score_valid_i || command_data_i!=1))response_error_o=1;
            12'h044:response_data_o={terminal_valid_i,fatal_i,26'd0,terminal_code_i};
            12'h048:if(command_write_i && (!terminal_valid_i || command_data_i!=1))response_error_o=1;
            12'h04c:response_data_o=accepted_frames_i;
            12'h050:response_data_o=committed_frames_i;
            12'h054:response_data_o=replayed_frames_i;
            12'h058:response_data_o=seal_crc_i;
            12'h05c:response_data_o={first_result_valid_i,8'd0,first_result_frame_i,first_result_note_i};
            12'h060:response_data_o=active_task_id_i;
            12'h064:response_data_o=active_generation_i;
            12'h068:response_data_o=start_accept_count;
            12'h06c:response_data_o=start_reject_count;
            12'h070:response_data_o=last_rejection;
            12'h074:response_data_o=seal_count;
            12'h100:response_data_o=tap_session_o;
            12'h104:response_data_o=tap_generation_o;
            12'h108:response_data_o=tap_epoch_o;
            12'h10c:response_data_o=tap_first_sequence_o;
            12'h110:response_data_o={24'd0,tap_format_o};
            12'h114:if(command_write_i && (!tap_open_o || !tap_arm_ready_i || command_data_i!=1))response_error_o=1;
            12'h118:begin response_data_o={31'd0,tap_open_o};if(command_write_i && command_data_i>1)response_error_o=1;end
            12'h11c:response_data_o=tap_frame_session_o;
            12'h120:response_data_o=tap_frame_generation_o;
            12'h124:response_data_o=tap_frame_epoch_o;
            12'h128:response_data_o=tap_frame_sequence_o;
            12'h12c:response_data_o=tap_frame_pcm_o;
            12'h130:begin response_data_o={30'd0,tap_frame_error_o,tap_frame_44k1_o};if(command_write_i && command_data_i>3)response_error_o=1;end
            12'h134:if(command_write_i && (!tap_frame_ready_i || command_data_i!=1))response_error_o=1;
            12'h138:if(command_write_i && command_data_i!=1)response_error_o=1;
            12'h13c:response_data_o={11'd0,tap_queued_i,tap_failure_i,tap_fault_i,tap_armed_i,tap_open_o,lcd_link_ready_i,tap_frame_ready_i,tap_arm_ready_i,2'd0};
            12'h140:response_data_o=tap_accepted_i;
            12'h144:response_data_o=tap_delivered_i;
            12'h148:response_data_o=tap_arm_accept_count;
            12'h14c:response_data_o=tap_arm_reject_count;
            12'h150:if(command_write_i && command_data_i!=1)response_error_o=1;
            default:response_error_o=1;
        endcase
        if(command_write_i)case(command_address_i)
            12'h010,12'h014,12'h018,12'h01c,12'h020,12'h024,12'h028,12'h02c,12'h030,12'h034,12'h040,12'h048,
            12'h100,12'h104,12'h108,12'h10c,12'h110,12'h114,12'h118,12'h11c,12'h120,12'h124,12'h128,12'h12c,
            12'h130,12'h134,12'h138,12'h150:begin end
            default:response_error_o=1;
        endcase
    end
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            task_id_o<=0;generation_o<=0;frames_o<=0;crc_o<=0;format_o<=1;frame_index_o<=0;frame_pcm_o<=0;
            start_accept_count<=0;start_reject_count<=0;last_rejection<=0;seal_count<=0;
            tap_open_o<=0;tap_session_o<=0;tap_generation_o<=0;tap_epoch_o<=0;tap_first_sequence_o<=0;tap_format_o<=1;
            tap_frame_session_o<=0;tap_frame_generation_o<=0;tap_frame_epoch_o<=0;tap_frame_sequence_o<=0;tap_frame_pcm_o<=0;
            tap_frame_44k1_o<=0;tap_frame_error_o<=0;tap_arm_accept_count<=0;tap_arm_reject_count<=0;
        end else begin
            if(!owner_reset_ni)tap_open_o<=0;
            if(start_accepted_i)start_accept_count<=start_accept_count+1'b1;
            if(start_rejected_i)begin start_reject_count<=start_reject_count+1'b1;last_rejection<={28'd0,rejection_code_i};end
            if(seal_valid_i)seal_count<=seal_count+1'b1;
            if(tap_arm_accepted_i)tap_arm_accept_count<=tap_arm_accept_count+1'b1;
            if(tap_arm_rejected_i)tap_arm_reject_count<=tap_arm_reject_count+1'b1;
            if(write)case(command_address_i)
                12'h010:task_id_o<=command_data_i;
                12'h014:generation_o<=command_data_i;
                12'h018:frames_o<=command_data_i;
                12'h01c:crc_o<=command_data_i;
                12'h020:format_o<=command_data_i[7:0];
                12'h028:frame_index_o<=command_data_i;
                12'h02c:frame_pcm_o<=command_data_i;
                12'h100:tap_session_o<=command_data_i;
                12'h104:tap_generation_o<=command_data_i;
                12'h108:tap_epoch_o<=command_data_i;
                12'h10c:tap_first_sequence_o<=command_data_i;
                12'h110:tap_format_o<=command_data_i[7:0];
                12'h118:tap_open_o<=command_data_i[0];
                12'h11c:tap_frame_session_o<=command_data_i;
                12'h120:tap_frame_generation_o<=command_data_i;
                12'h124:tap_frame_epoch_o<=command_data_i;
                12'h128:tap_frame_sequence_o<=command_data_i;
                12'h12c:tap_frame_pcm_o<=command_data_i;
                12'h130:begin tap_frame_44k1_o<=command_data_i[0];tap_frame_error_o<=command_data_i[1];end
                default:begin end
            endcase
        end
    end
endmodule
