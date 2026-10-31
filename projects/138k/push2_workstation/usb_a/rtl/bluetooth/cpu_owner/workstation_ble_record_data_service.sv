`timescale 1ns/1ps
`default_nettype none
// One immutable descriptor. This transport never allocates business identities.
// Observer loss fences future submissions; accepted physical work still drains.
module workstation_ble_record_data_service (
    input wire clk_i,rst_ni,owner_reset_ni,
    input wire command_valid_i,command_write_i,
    input wire [7:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output wire command_ready_o,
    output reg response_error_o,
    output reg [31:0] response_data_o,
    input wire [7:0] record_state_i,
    input wire [31:0] object_id_i,frames_i,committed_i,crc_i,stop_reason_i,first_frame_ms_i,terminal_ms_i,
    input wire source_good_i,mutation_hold_i,transfer_valid_i,
    input wire request_admitted_i,request_replay_i,
    input wire [31:0] request_object_i,request_ticket_i,request_owner_i,request_session_i,
    input wire [63:0] request_boot_i,
    input wire enabled_i,subscribed_i,engine_idle_i,
    input wire [8:0] att_value_limit_i,
    input wire [31:0] elapsed_ms_i,engine_time_ms_i,engine_block_crc_i,
    input wire engine_block_crc_valid_i,engine_read_accepted_i,
    output reg engine_start_o,
    output wire [7:0] engine_opcode_o,
    output wire [4:0] engine_flags_o,
    output wire [15:0] engine_length_o,
    output wire [31:0] engine_request_o,engine_object_o,engine_transfer_o,
    output wire [63:0] engine_nonce_o,
    output wire [127:0] engine_payload_o,
    input wire engine_done_i,
    input wire [7:0] engine_status_i,
    input wire [6:0] engine_length_i,
    input wire [383:0] engine_result_i,
    output wire observer_fault_o
);
    reg owner_seen,fenced,busy;
    reg request_replay;reg [31:0] request_object;
    reg [4:0] staged_flags,active_flags;
    reg result_crc_valid,result_read_accepted;reg [31:0] result_crc,result_time;
    reg [31:0] staged_seq,staged_object,staged_transfer,staged_request;
    reg [7:0] staged_opcode;
    reg [15:0] staged_length;
    reg [63:0] staged_nonce;
    reg [127:0] staged_payload;
    reg [31:0] active_seq,active_object,active_transfer,active_request;
    reg [7:0] active_opcode;
    reg [15:0] active_length;
    reg [63:0] active_nonce;
    reg [127:0] active_payload;
    reg [31:0] accepted_seq,applied_seq;
    reg [7:0] result_status;
    reg [6:0] result_length;
    reg [383:0] result_payload;
    assign engine_opcode_o=active_opcode,engine_length_o=active_length;
    assign engine_flags_o=active_flags;
    assign engine_request_o=active_request,engine_nonce_o=active_nonce;
    assign engine_object_o=active_object,engine_transfer_o=active_transfer;
    assign engine_payload_o=active_payload;
    assign observer_fault_o=fenced;
    assign command_ready_o=1'b1;
    wire submit=command_valid_i && command_write_i && command_address_i==8'h08 && !response_error_o;
    always @* begin
        response_error_o=0;response_data_o=0;
        if(command_address_i[1:0]!=0)response_error_o=1;
        else if(command_write_i)begin
            if(command_strobes_i!=4'hf)response_error_o=1;
            else case(command_address_i)
                8'h08:response_error_o=command_data_i!=1 || fenced || !owner_reset_ni || busy ||
                    !engine_idle_i || staged_seq==0 || staged_seq<=accepted_seq ||
                    staged_length>16 || staged_request==0 || staged_nonce==0;
                8'h14:response_error_o=fenced || !owner_reset_ni || command_data_i[31:5]!=0;
                8'h60:response_error_o=fenced || !owner_reset_ni || command_data_i[31:8]!=0;
                8'h64:response_error_o=fenced || !owner_reset_ni || command_data_i>16;
                8'h10,8'h58,8'h5c,8'h68,8'h6c,8'h70,
                8'h74,8'h78,8'h7c,8'h80:response_error_o=fenced || !owner_reset_ni;
                default:response_error_o=1;
            endcase
        end else case(command_address_i)
            8'h00:response_data_o=32'h52434403;
            8'h04:response_data_o=32'h00301002; // 48-byte result, 16-byte command, one descriptor.
            8'h0c:response_data_o={16'd0,subscribed_i,enabled_i,1'b0,transfer_valid_i,
                mutation_hold_i,source_good_i,fenced,busy,record_state_i};
            8'h1c:response_data_o=object_id_i;
            8'h20:response_data_o=0; // BLE32 tag, distinct from R00's independent object64.
            8'h24:response_data_o=32'd48000; // Existing BLE format 1 only.
            8'h28:response_data_o=0;
            8'h2c:response_data_o=frames_i;
            8'h30:response_data_o=committed_i;
            8'h34:response_data_o=crc_i;
            8'h38:response_data_o=stop_reason_i;
            8'h40:response_data_o={23'd0,att_value_limit_i};
            8'h44:response_data_o=engine_time_ms_i;
            8'h48:response_data_o=elapsed_ms_i;
            8'h4c:response_data_o=accepted_seq;
            8'h50:response_data_o=applied_seq;
            8'h54:response_data_o=32'd1; // Common-reset lifetime; observer reset cannot rearm.
            8'hc0:response_data_o=first_frame_ms_i;
            8'hc4:response_data_o=terminal_ms_i;
            8'h84:response_data_o={15'd0,result_read_accepted,result_crc_valid,result_length,result_status};
            8'h88:response_data_o=result_crc;
            8'h8c:response_data_o=result_time;
            8'hc8:response_data_o={31'd0,request_replay};
            8'hcc:response_data_o=request_object;
            8'hd0:response_data_o=request_ticket_i;
            8'hd4:response_data_o=request_owner_i;
            8'hd8:response_data_o=request_session_i;
            8'hdc:response_data_o=request_boot_i[31:0];
            8'he0:response_data_o=request_boot_i[63:32];
            // The MMIO ABI only selects aligned whole words. Keep the shared
            // address decode explicit instead of a wide variable bit slice.
            8'h90:response_data_o=result_payload[0+:32];
            8'h94:response_data_o=result_payload[32+:32];
            8'h98:response_data_o=result_payload[64+:32];
            8'h9c:response_data_o=result_payload[96+:32];
            8'ha0:response_data_o=result_payload[128+:32];
            8'ha4:response_data_o=result_payload[160+:32];
            8'ha8:response_data_o=result_payload[192+:32];
            8'hac:response_data_o=result_payload[224+:32];
            8'hb0:response_data_o=result_payload[256+:32];
            8'hb4:response_data_o=result_payload[288+:32];
            8'hb8:response_data_o=result_payload[320+:32];
            8'hbc:response_data_o=result_payload[352+:32];
            default:response_error_o=1;
        endcase
    end
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            owner_seen<=0;fenced<=0;busy<=0;engine_start_o<=0;
            request_replay<=0;request_object<=0;staged_flags<=0;active_flags<=0;
            result_crc_valid<=0;result_read_accepted<=0;result_crc<=0;result_time<=0;
            staged_seq<=0;staged_object<=0;staged_transfer<=0;staged_request<=0;
            staged_opcode<=0;staged_length<=0;staged_nonce<=0;staged_payload<=0;
            active_seq<=0;active_object<=0;active_transfer<=0;active_request<=0;
            active_opcode<=0;active_length<=0;active_nonce<=0;active_payload<=0;
            accepted_seq<=0;applied_seq<=0;result_status<=0;result_length<=0;result_payload<=0;
        end else begin
            engine_start_o<=0;
            if(request_admitted_i)begin request_replay<=request_replay_i;request_object<=request_object_i;end
            if(owner_reset_ni)owner_seen<=1;
            else if(owner_seen)fenced<=1;
            if(command_valid_i && command_write_i && !response_error_o)case(command_address_i)
                8'h10:staged_object<=command_data_i;
                8'h14:staged_flags<=command_data_i[4:0];
                8'h58:staged_seq<=command_data_i;
                8'h5c:staged_transfer<=command_data_i;
                8'h60:staged_opcode<=command_data_i[7:0];
                8'h64:staged_length<=command_data_i[15:0];
                8'h68:staged_request<=command_data_i;
                8'h6c:staged_nonce[31:0]<=command_data_i;
                8'h70:staged_nonce[63:32]<=command_data_i;
                8'h74:staged_payload[0+:32]<=command_data_i;
                8'h78:staged_payload[32+:32]<=command_data_i;
                8'h7c:staged_payload[64+:32]<=command_data_i;
                8'h80:staged_payload[96+:32]<=command_data_i;
                default:begin end
            endcase
            if(submit)begin
                active_seq<=staged_seq;active_object<=staged_object;active_transfer<=staged_transfer;
                active_request<=staged_request;active_opcode<=staged_opcode;active_length<=staged_length;
                active_nonce<=staged_nonce;active_payload<=staged_payload;active_flags<=staged_flags;
                accepted_seq<=staged_seq;busy<=1;engine_start_o<=1;
            end
            if(busy && engine_done_i)begin
                applied_seq<=active_seq;result_status<=engine_status_i;
                result_length<=engine_length_i;result_payload<=engine_result_i;busy<=0;
                result_crc_valid<=engine_block_crc_valid_i;result_read_accepted<=engine_read_accepted_i;result_crc<=engine_block_crc_i;result_time<=engine_time_ms_i;
            end
        end
    end
endmodule
`default_nettype wire
