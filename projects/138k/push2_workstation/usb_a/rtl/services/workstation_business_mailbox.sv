`timescale 1ns/1ps
`default_nettype none
// Unselected S1a transport for already validated business commands. No parser,
// business task owner, PCM path, APB page decode or production hook lives here.
module workstation_business_mailbox #(
    parameter integer TIMEOUT_CYCLES=5000000
)(
    input wire clk_i,rst_ni,owner_reset_ni,boot_valid_i,control_open_i,
    input wire [63:0] boot_id_i,
    input wire [31:0] session_generation_i,
    input wire fence_i,cancel_i,
    input wire request_offer_i,
    input wire [7:0] request_opcode_i,request_reserved_i,
    input wire [15:0] request_length_i,
    input wire [31:0] request_id_i,
    input wire [63:0] request_nonce_i,
    input wire [127:0] request_payload_i,
    output wire request_ready_o,
    output reg request_admitted_o,request_rejected_o,
    output reg [7:0] request_reject_reason_o,
    input wire command_valid_i,command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output wire command_ready_o,
    output reg response_error_o,
    output reg [31:0] response_data_o,
    output wire completion_valid_o,
    input wire completion_consume_i,
    output wire [31:0] completion_ticket_o,completion_owner_o,completion_session_o,
    output wire [63:0] completion_boot_o,
    output wire [7:0] completion_phase_o,completion_status_o,completion_reason_o,
    output wire [6:0] completion_length_o,
    output wire [31:0] completion_operation_o,
    output wire [511:0] completion_payload_o
);
    localparam [1:0] EMPTY=0,QUEUED=1,CLAIMED=2,RESULT=3;
    localparam [7:0] PENDING=1,APPLIED=2,FAILED=3,REJECTED=4,UNCERTAIN=5;
    localparam [7:0] LOCAL_CANCEL=1,OWNER_RESET=2,SESSION_LOST=3,TIMEOUT=4,
        OWNER_CLOSE=5,BOOT_CHANGED=6,BUSY=8,BAD_LENGTH=9,BAD_CONTEXT=10,
        BAD_RESERVED=11,OWNER_NOT_OPEN=12,EXHAUSTED=13;
    localparam [11:0] ID=12'h000,CAPS=12'h004,STATE=12'h008,OWNER=12'h00c,
        BOOT_LOW=12'h010,BOOT_HIGH=12'h014,SESSION=12'h018,TICKET=12'h01c,
        SLOT_OWNER=12'h020,SLOT_SESSION=12'h024,SLOT_BOOT_LOW=12'h028,SLOT_BOOT_HIGH=12'h02c,
        REQUEST_ID=12'h030,NONCE_LOW=12'h034,NONCE_HIGH=12'h038,REQUEST_META=12'h03c,
        REQUEST_DATA0=12'h040,REQUEST_DATA3=12'h04c,AGE=12'h050,ADMITTED=12'h054,
        REJECT_COUNT=12'h058,TIMEOUT_COUNT=12'h05c,STALE_COUNT=12'h060,ABANDONED=12'h064,
        LAST_REASON=12'h068,KEY_TICKET=12'h080,KEY_OWNER=12'h084,KEY_SESSION=12'h088,
        KEY_BOOT_LOW=12'h08c,KEY_BOOT_HIGH=12'h090,RESULT_META=12'h094,
        RESULT_OPERATION=12'h098,RESULT_DATA0=12'h09c,RESULT_DATA15=12'h0d8,COMMAND=12'h0dc,
        LAST_TICKET=12'h0e0,LAST_OWNER=12'h0e4,LAST_SESSION=12'h0e8,
        LAST_BOOT_LOW=12'h0ec,LAST_BOOT_HIGH=12'h0f0,LAST_META=12'h0f4,LAST_OPERATION=12'h0f8;
    localparam [31:0] OPEN=1,CLAIM=2,COMPLETE=3,ABANDON=4,CLOSE=5;
    initial begin
        if(TIMEOUT_CYCLES<1)$fatal(1,"business mailbox timeout must be positive");
    end
    reg [1:0] state;
    reg owner_open,previous_owner_reset,ticket_exhausted,owner_exhausted;
    reg [31:0] owner_generation,next_ticket,slot_ticket,slot_owner,slot_session;
    reg [63:0] tracked_boot,slot_boot,slot_nonce;
    reg [31:0] slot_request_id,age,admitted_count,rejected_count,timeout_count,stale_count,abandoned_count;
    reg [7:0] slot_opcode,last_reason;
    reg [15:0] slot_length;
    reg [127:0] slot_payload;
    reg [31:0] key_ticket,key_owner,key_session;
    reg [63:0] key_boot;
    reg [31:0] staged_meta,staged_operation;
    reg [511:0] staged_payload,result_payload;
    reg [7:0] result_phase,result_status,result_reason;
    reg [6:0] result_length;
    reg [31:0] result_operation,last_ticket,last_owner,last_session,last_meta,last_operation;
    reg [63:0] last_boot;
    wire good_boot=boot_valid_i && boot_id_i!=0;
    wire boot_change=boot_id_i!=tracked_boot;
    wire owner_reset_edge=previous_owner_reset && !owner_reset_ni;
    wire owner_event=boot_change || owner_reset_edge;
    wire session_lost=!control_open_i || session_generation_i==0 || slot_session!=session_generation_i;
    wire expired=(state==QUEUED || state==CLAIMED) && age>=TIMEOUT_CYCLES-1;
    wire slot_fence=!owner_reset_ni || !good_boot || boot_change || fence_i || session_lost || cancel_i || expired;
    wire slot_key=key_ticket==slot_ticket && key_owner==slot_owner && key_session==slot_session && key_boot==slot_boot;
    wire open_key=key_ticket==0 && key_owner==owner_generation && key_session==session_generation_i && key_boot==boot_id_i;
    wire staged_valid=staged_meta[31:24]==0 && staged_meta[23:16]<=64 &&
        staged_meta[7:0]>=PENDING && staged_meta[7:0]<=FAILED &&
        (staged_meta[7:0]!=PENDING || staged_operation!=0);
    wire bus_write=command_valid_i && command_write_i && !response_error_o;
    wire owner_available=owner_reset_ni && good_boot && !owner_event && !owner_exhausted;
    wire local_fence_pending=state!=EMPTY && !(state==RESULT && result_reason!=0) && slot_fence;
    wire closing=command_valid_i && command_write_i && command_address_i==COMMAND && command_data_i==CLOSE;
    assign command_ready_o=1'b1;
    assign request_ready_o=rst_ni && owner_available && owner_open && !ticket_exhausted &&
        control_open_i && session_generation_i!=0 && !fence_i && !cancel_i && !closing && state==EMPTY;
    // A changing session cannot consume a previous business result. The next
    // edge replaces it with an explicitly local observation-loss descriptor.
    assign completion_valid_o=state==RESULT && (result_reason!=0 || !slot_fence);
    assign completion_ticket_o=slot_ticket,completion_owner_o=slot_owner,completion_session_o=slot_session;
    assign completion_boot_o=slot_boot,completion_phase_o=result_phase,completion_status_o=result_status;
    assign completion_reason_o=result_reason,completion_length_o=result_length;
    assign completion_operation_o=result_operation,completion_payload_o=result_payload;
    function automatic [31:0] sat(input [31:0] value);
        sat=&value ? value : value+1'b1;
    endfunction
    task automatic local_result(input [7:0] reason);
        begin
            state<=RESULT;result_phase<=state==QUEUED ? REJECTED : UNCERTAIN;
            result_status<=0;result_length<=0;result_reason<=reason;result_payload<=0;
            result_operation<=state==RESULT ? result_operation : 0;
            last_ticket<=slot_ticket;last_owner<=slot_owner;last_session<=slot_session;last_boot<=slot_boot;
            last_meta<={reason,8'd0,8'd0,(state==QUEUED ? REJECTED : UNCERTAIN)};
            last_operation<=state==RESULT ? result_operation : 0;
            last_reason<=reason;
            if(state!=QUEUED)abandoned_count<=sat(abandoned_count);
            if(reason==TIMEOUT)timeout_count<=sat(timeout_count);
        end
    endtask
    always @* begin
        response_error_o=0;response_data_o=0;
        if(command_write_i)begin
            if(command_strobes_i!=4'hf || command_address_i[1:0]!=0 || !owner_available || local_fence_pending ||
                (state==RESULT && completion_consume_i))
                response_error_o=1;
            else case(command_address_i)
                KEY_TICKET,KEY_OWNER,KEY_SESSION,KEY_BOOT_LOW,KEY_BOOT_HIGH,
                RESULT_META,RESULT_OPERATION:begin end
                COMMAND:case(command_data_i)
                    OPEN:response_error_o=!open_key;
                    CLAIM:response_error_o=!owner_open || state!=QUEUED || !slot_key || slot_fence;
                    COMPLETE:response_error_o=!owner_open || state!=CLAIMED || !slot_key || slot_fence || !staged_valid;
                    ABANDON:response_error_o=!slot_key || (state!=QUEUED && state!=CLAIMED) || slot_fence;
                    CLOSE:response_error_o=!open_key;
                    default:response_error_o=1;
                endcase
                default:if(command_address_i<RESULT_DATA0 || command_address_i>RESULT_DATA15)
                    response_error_o=1;
            endcase
        end else case(command_address_i)
            ID:response_data_o=32'h424d4201;
            CAPS:response_data_o=32'h00401001; // 64-byte result, 16-byte request, one slot; ABI in ID.
            STATE:response_data_o={20'd0,good_boot,owner_exhausted,ticket_exhausted,owner_open,6'd0,state};
            OWNER:response_data_o=owner_generation;
            BOOT_LOW:response_data_o=boot_id_i[31:0];BOOT_HIGH:response_data_o=boot_id_i[63:32];
            SESSION:response_data_o=session_generation_i;TICKET:response_data_o=slot_ticket;
            SLOT_OWNER:response_data_o=slot_owner;SLOT_SESSION:response_data_o=slot_session;
            SLOT_BOOT_LOW:response_data_o=slot_boot[31:0];SLOT_BOOT_HIGH:response_data_o=slot_boot[63:32];
            REQUEST_ID:response_data_o=slot_request_id;NONCE_LOW:response_data_o=slot_nonce[31:0];
            NONCE_HIGH:response_data_o=slot_nonce[63:32];REQUEST_META:response_data_o={8'd0,slot_opcode,slot_length};
            AGE:response_data_o=age;ADMITTED:response_data_o=admitted_count;REJECT_COUNT:response_data_o=rejected_count;
            TIMEOUT_COUNT:response_data_o=timeout_count;STALE_COUNT:response_data_o=stale_count;
            ABANDONED:response_data_o=abandoned_count;LAST_REASON:response_data_o={24'd0,last_reason};
            RESULT_META:response_data_o={result_reason,1'b0,result_length,result_status,result_phase};
            RESULT_OPERATION:response_data_o=result_operation;
            LAST_TICKET:response_data_o=last_ticket;LAST_OWNER:response_data_o=last_owner;
            LAST_SESSION:response_data_o=last_session;LAST_BOOT_LOW:response_data_o=last_boot[31:0];
            LAST_BOOT_HIGH:response_data_o=last_boot[63:32];LAST_META:response_data_o=last_meta;
            LAST_OPERATION:response_data_o=last_operation;
            default:begin
                if(command_address_i[1:0]!=0)response_error_o=1;
                else if(command_address_i>=REQUEST_DATA0 && command_address_i<=REQUEST_DATA3)
                    response_data_o=slot_payload[(command_address_i-REQUEST_DATA0)*8+:32];
                else if(command_address_i>=RESULT_DATA0 && command_address_i<=RESULT_DATA15)
                    response_data_o=result_payload[(command_address_i-RESULT_DATA0)*8+:32];
                else response_error_o=1;
            end
        endcase
    end
    integer i;
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            state<=EMPTY;owner_open<=0;previous_owner_reset<=0;owner_generation<=1;tracked_boot<=0;
            next_ticket<=1;ticket_exhausted<=0;owner_exhausted<=0;
            slot_ticket<=0;slot_owner<=0;slot_session<=0;slot_boot<=0;slot_nonce<=0;
            slot_request_id<=0;slot_opcode<=0;slot_length<=0;slot_payload<=0;age<=0;
            admitted_count<=0;rejected_count<=0;timeout_count<=0;stale_count<=0;abandoned_count<=0;last_reason<=0;
            key_ticket<=0;key_owner<=0;key_session<=0;key_boot<=0;staged_meta<=0;staged_operation<=0;staged_payload<=0;
            result_phase<=0;result_status<=0;result_reason<=0;result_length<=0;result_operation<=0;result_payload<=0;
            last_ticket<=0;last_owner<=0;last_session<=0;last_boot<=0;last_meta<=0;last_operation<=0;
            request_admitted_o<=0;request_rejected_o<=0;request_reject_reason_o<=0;
        end else begin
            request_admitted_o<=0;request_rejected_o<=0;request_reject_reason_o<=0;
            previous_owner_reset<=owner_reset_ni;tracked_boot<=boot_id_i;
            if(state==QUEUED || state==CLAIMED)age<=sat(age);
            if(request_offer_i)begin
                if(!request_ready_o || request_length_i>16 || request_reserved_i!=0 || request_id_i==0 || request_nonce_i==0)begin
                    request_rejected_o<=1;rejected_count<=sat(rejected_count);
                    if(request_reserved_i!=0)request_reject_reason_o<=BAD_RESERVED;
                    else if(request_length_i>16)request_reject_reason_o<=BAD_LENGTH;
                    else if(request_id_i==0 || request_nonce_i==0 || !good_boot || !control_open_i || session_generation_i==0)
                        request_reject_reason_o<=BAD_CONTEXT;
                    else if(ticket_exhausted || owner_exhausted)request_reject_reason_o<=EXHAUSTED;
                    else if(!owner_open || !owner_reset_ni)request_reject_reason_o<=OWNER_NOT_OPEN;
                    else request_reject_reason_o<=BUSY;
                end else begin
                    state<=QUEUED;slot_ticket<=next_ticket;slot_owner<=owner_generation;
                    slot_session<=session_generation_i;slot_boot<=boot_id_i;slot_nonce<=request_nonce_i;
                    slot_request_id<=request_id_i;slot_opcode<=request_opcode_i;slot_length<=request_length_i;
                    for(i=0;i<16;i=i+1)slot_payload[i*8+:8]<=i<request_length_i ? request_payload_i[i*8+:8] : 8'd0;
                    age<=0;admitted_count<=sat(admitted_count);request_admitted_o<=1;
                    if(&next_ticket)ticket_exhausted<=1;else next_ticket<=next_ticket+1'b1;
                end
            end
            if(owner_event || !owner_reset_ni || !good_boot)begin
                owner_open<=0;key_ticket<=0;key_owner<=0;key_session<=0;key_boot<=0;
                staged_meta<=0;staged_operation<=0;staged_payload<=0;
                if(owner_event)begin
                    if(&owner_generation)owner_exhausted<=1;else owner_generation<=owner_generation+1'b1;
                end
                if(state!=EMPTY && !(state==RESULT && result_reason!=0))
                    local_result(boot_change || !good_boot ? BOOT_CHANGED : OWNER_RESET);
                else if(state==RESULT && completion_consume_i)state<=EMPTY;
            end else if(state!=EMPTY && !(state==RESULT && result_reason!=0) && slot_fence)
                local_result(cancel_i ? LOCAL_CANCEL : expired ? TIMEOUT : SESSION_LOST);
            else if(state==RESULT && completion_consume_i)state<=EMPTY;
            else if(bus_write)begin
                case(command_address_i)
                    KEY_TICKET:key_ticket<=command_data_i;KEY_OWNER:key_owner<=command_data_i;
                    KEY_SESSION:key_session<=command_data_i;KEY_BOOT_LOW:key_boot[31:0]<=command_data_i;
                    KEY_BOOT_HIGH:key_boot[63:32]<=command_data_i;RESULT_META:staged_meta<=command_data_i;
                    RESULT_OPERATION:staged_operation<=command_data_i;
                    COMMAND:case(command_data_i)
                        OPEN:owner_open<=1;
                        CLAIM:state<=CLAIMED;
                        COMPLETE:begin
                            state<=RESULT;result_phase<=staged_meta[7:0];result_status<=staged_meta[15:8];
                            result_length<=staged_meta[22:16];result_reason<=0;result_operation<=staged_operation;
                            for(i=0;i<64;i=i+1)result_payload[i*8+:8]<=i<staged_meta[23:16] ? staged_payload[i*8+:8] : 8'd0;
                            last_ticket<=slot_ticket;last_owner<=slot_owner;last_session<=slot_session;last_boot<=slot_boot;
                            last_meta<={8'd0,staged_meta[23:0]};last_operation<=staged_operation;
                        end
                        ABANDON:local_result(LOCAL_CANCEL);
                        CLOSE:begin
                            owner_open<=0;
                            if(state!=EMPTY && !(state==RESULT && result_reason!=0))local_result(OWNER_CLOSE);
                        end
                        default:begin end
                    endcase
                    default:if(command_address_i>=RESULT_DATA0 && command_address_i<=RESULT_DATA15)
                        staged_payload[(command_address_i-RESULT_DATA0)*8+:32]<=command_data_i;
                endcase
            end
            if(command_valid_i && command_write_i && command_address_i==COMMAND && response_error_o &&
                (command_data_i==CLAIM || command_data_i==COMPLETE || command_data_i==ABANDON))
                stale_count<=sat(stale_count);
        end
    end
endmodule
`default_nettype wire
