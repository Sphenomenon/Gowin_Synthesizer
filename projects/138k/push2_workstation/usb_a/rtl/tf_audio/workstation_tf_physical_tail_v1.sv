`timescale 1ns/1ps

// Reusable TF endpoint, not an audio top or another source selector. Compute
// admission must wait for armed_o. Only actual TF fire binds an ordered LAST.
// The serializer and observation queue remain owned by the unique audio path.
module workstation_tf_physical_tail_v1 (
    input wire rst_ni,compute_clk_i,serial_clk_i,
    // Compute-domain lifecycle fence; one event per high edge. It invalidates
    // eligibility immediately but does not reset either mailbox endpoint.
    input wire fence_i,
    input wire arm_valid_i,
    output wire arm_ready_o,
    input wire arm_44k1_i,
    input wire [31:0] arm_generation_i,arm_session_i,arm_epoch_i,
    output reg armed_o,tail_pending_o,tail_closed_o,
    output wire tf_admit_o,quiescent_o,
    input wire tf_fire_i,tf_last_i,tf_error_i,tf_44k1_i,
    input wire [31:0] tf_generation_i,tf_session_i,
    // These are the SAME accepted final-router request's assigned identity.
    input wire [31:0] render_epoch_i,render_sequence_i,
    input wire router_valid_i,router_error_i,router_source_tf_i,router_44k1_i,
    input wire [31:0] router_epoch_i,router_sequence_i,
    input wire transport_fault_i,
    // Real completed-frame observation in compute domain, after its actual CDC.
    input wire observation_valid_i,observation_error_i,observation_44k1_i,
    input wire observation_gap_i,observation_drop_event_i,
    input wire [31:0] observation_epoch_i,observation_sequence_i,
    // Serial-domain raw serializer completion and the REAL observation queue's
    // source counter. No test acknowledgement substitutes for these endpoints.
    input wire physical_valid_i,physical_error_i,physical_44k1_i,
    input wire [31:0] physical_epoch_i,physical_sequence_i,
    input wire [31:0] observation_source_drops_i,
    output reg physical_eos_o,tail_cancelled_o,failed_o,
    output reg [3:0] failure_code_o,
    output reg [31:0] tail_epoch_o,tail_sequence_o,
    output reg [31:0] baseline_drops_o,tail_drops_o,
    output wire mailbox_busy_o
);
    // kind/rate/transport/session/epoch/sequence/cancellation-Gray.
    localparam integer TOKEN_WIDTH=162,REPLY_WIDTH=229;
    localparam [1:0] OK=0,CANCELLED=1,BAD_CONTEXT=2;
    localparam [3:0] BAD_FIRE=1,ROUTER_ERROR=2,TRANSPORT_ERROR=3,
        OBSERVATION_ERROR=4,RECEIPT_ERROR=5,OBSERVATION_LOSS=6;
    reg [31:0] fence_count,fence_gray;
    wire [31:0] next_fence=fence_count+1'b1;
    function automatic [31:0] gray(input [31:0] value);gray=value^(value>>1);endfunction
    reg request_toggle,reply_consumed,arm_pending,tail_sent,tail_observed,tail_receipted;
    (* syn_preserve=1 *) reg [TOKEN_WIDTH-1:0] held_request;
    (* syn_preserve=1 *) reg [REPLY_WIDTH-1:0] held_reply;
    reg reply_toggle;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] reply_sync,request_sync;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [31:0] fence_meta,fence_sync;
    reg context_rate,have_first;
    reg [31:0] context_generation,context_session,context_epoch,context_fence,first_sequence;
    wire busy=request_toggle!=reply_sync[1];
    assign mailbox_busy_o=busy;
    assign arm_ready_o=rst_ni && !fence_i && !busy && !arm_pending && !armed_o && !tail_pending_o && !tail_closed_o;
    assign tf_admit_o=armed_o && !tail_closed_o && !failed_o && !fence_i;
    assign quiescent_o=rst_ni && !armed_o && !tail_pending_o && !arm_pending && !busy;
    wire arm_fire=arm_valid_i && arm_ready_o;
    wire [TOKEN_WIDTH-1:0] reply_token=held_reply[REPLY_WIDTH-1:67];
    wire [1:0] reply_status=held_reply[66:65];
    wire [31:0] reply_baseline=held_reply[64:33],reply_prefix=held_reply[32:1];
    wire reply_error=held_reply[0];
    wire reply_kind=reply_token[161],reply_rate=reply_token[160];
    wire [31:0] reply_generation=reply_token[159:128],reply_session=reply_token[127:96];
    wire [31:0] reply_epoch=reply_token[95:64],reply_sequence=reply_token[63:32],reply_fence=reply_token[31:0];
    wire reply_current=reply_rate==context_rate && reply_generation==context_generation &&
        reply_session==context_session && reply_epoch==context_epoch && reply_fence==context_fence;
    wire observation_current=have_first && observation_44k1_i==context_rate &&
        observation_epoch_i==context_epoch && (observation_sequence_i-first_sequence)<32'h80000000;
    wire router_current=have_first && router_44k1_i==context_rate &&
        router_epoch_i==context_epoch && (router_sequence_i-first_sequence)<32'h80000000;
    wire observed_tail=observation_valid_i && observation_44k1_i==context_rate &&
        observation_epoch_i==tail_epoch_o && observation_sequence_i==tail_sequence_o;
    reg [3:0] failure_now;
    always @* begin
        failure_now=0;
        if(armed_o || tail_pending_o)begin
            if(tf_fire_i && (!tf_admit_o || tf_error_i || tf_44k1_i!=context_rate ||
                tf_generation_i!=context_generation || tf_session_i!=context_session || render_epoch_i!=context_epoch))failure_now=BAD_FIRE;
            else if(router_valid_i && router_source_tf_i && router_current && router_error_i)failure_now=ROUTER_ERROR;
            else if(transport_fault_i)failure_now=TRANSPORT_ERROR;
            else if((observation_valid_i && observation_current && (observation_error_i || observation_gap_i)) ||
                    observation_drop_event_i)failure_now=OBSERVATION_ERROR;
        end
    end
    always @(posedge compute_clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            fence_count<=0;fence_gray<=0;request_toggle<=0;reply_consumed<=0;reply_sync<=0;held_request<=0;
            armed_o<=0;arm_pending<=0;tail_pending_o<=0;tail_closed_o<=0;tail_sent<=0;tail_observed<=0;tail_receipted<=0;
            context_rate<=0;context_generation<=0;context_session<=0;context_epoch<=0;context_fence<=0;
            have_first<=0;first_sequence<=0;physical_eos_o<=0;tail_cancelled_o<=0;failed_o<=0;failure_code_o<=0;
            tail_epoch_o<=0;tail_sequence_o<=0;baseline_drops_o<=0;tail_drops_o<=0;
        end else begin
            reply_sync<={reply_sync[0],reply_toggle};physical_eos_o<=0;tail_cancelled_o<=0;
            if(reply_sync[1]!=reply_consumed)begin
                reply_consumed<=reply_sync[1];
                // Late retired replies free the transport slot but cannot arm
                // or finish a newer fenced session.
                if(reply_current && reply_status==OK && !fence_i && !failed_o)begin
                    if(!reply_kind && arm_pending)begin
                        arm_pending<=0;baseline_drops_o<=reply_baseline;
                        if(reply_baseline==32'hffffffff)begin failed_o<=1;failure_code_o<=OBSERVATION_LOSS;end
                        else armed_o<=1;
                    end else if(reply_kind && tail_pending_o && reply_sequence==tail_sequence_o)begin
                        tail_drops_o<=reply_prefix;
                        if(reply_error)begin failed_o<=1;failure_code_o<=RECEIPT_ERROR;end
                        else if(reply_baseline!=baseline_drops_o || reply_prefix!=reply_baseline ||
                                reply_prefix==32'hffffffff || reply_prefix<reply_baseline)begin
                            failed_o<=1;failure_code_o<=OBSERVATION_LOSS;
                        end else tail_receipted<=1;
                    end
                end else if(reply_current && !fence_i && (arm_pending || tail_pending_o))begin
                    arm_pending<=0;failed_o<=1;failure_code_o<=RECEIPT_ERROR;
                end
            end
            if(arm_fire)begin
                context_rate<=arm_44k1_i;context_generation<=arm_generation_i;context_session<=arm_session_i;
                context_epoch<=arm_epoch_i;context_fence<=fence_gray;have_first<=0;
                held_request<={1'b0,arm_44k1_i,arm_generation_i,arm_session_i,arm_epoch_i,32'd0,fence_gray};
                request_toggle<=!request_toggle;arm_pending<=1;failed_o<=0;failure_code_o<=0;
                baseline_drops_o<=0;tail_drops_o<=0;
            end
            if(tf_fire_i && tf_admit_o)begin
                if(!have_first)begin have_first<=1;first_sequence<=render_sequence_i;end
                if(tf_last_i)begin
                    tail_epoch_o<=render_epoch_i;tail_sequence_o<=render_sequence_i;
                    tail_pending_o<=1;tail_closed_o<=1;tail_sent<=0;tail_observed<=0;tail_receipted<=0;
                end
            end
            if(tail_pending_o && !tail_sent && !busy && !fence_i && !failed_o)begin
                held_request<={1'b1,context_rate,context_generation,context_session,tail_epoch_o,tail_sequence_o,context_fence};
                request_toggle<=!request_toggle;tail_sent<=1;
            end
            if(tail_pending_o && observed_tail && !observation_error_i && !observation_gap_i)tail_observed<=1;
            if(tail_pending_o && tail_observed && tail_receipted && !failed_o && failure_now==0 && !fence_i)begin
                physical_eos_o<=1;tail_pending_o<=0;armed_o<=0;
            end
            if(failure_now!=0)begin failed_o<=1;failure_code_o<=failure_now;armed_o<=0;end
            if(fence_i)begin
                fence_count<=next_fence;fence_gray<=gray(next_fence);
                if(armed_o || arm_pending || tail_pending_o)tail_cancelled_o<=1;
                armed_o<=0;arm_pending<=0;tail_pending_o<=0;tail_closed_o<=0;
                tail_sent<=0;tail_observed<=0;tail_receipted<=0;have_first<=0;
            end
        end
    end

    localparam [1:0] IDLE=0,VALIDATE=1,WAIT_FRAME=2,WATERMARK=3;
    reg [1:0] serial_state;
    reg [TOKEN_WIDTH-1:0] serial_token;
    reg serial_request_seen,serial_context_valid,serial_frame_error;
    reg [31:0] serial_generation,serial_session,serial_epoch,serial_fence,serial_baseline;
    reg serial_rate;
    wire token_kind=serial_token[161],token_rate=serial_token[160];
    wire [31:0] token_generation=serial_token[159:128],token_session=serial_token[127:96];
    wire [31:0] token_epoch=serial_token[95:64],token_sequence=serial_token[63:32],token_fence=serial_token[31:0];
    wire token_context=serial_context_valid && token_rate==serial_rate && token_generation==serial_generation &&
        token_session==serial_session && token_epoch==serial_epoch && token_fence==serial_fence;
    task retire(input [1:0] status,input [31:0] baseline,prefix,input bit error);
        begin held_reply<={serial_token,status,baseline,prefix,error};reply_toggle<=serial_request_seen;serial_state<=IDLE;end
    endtask
    always @(posedge serial_clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            request_sync<=0;fence_meta<=0;fence_sync<=0;serial_state<=IDLE;serial_token<=0;
            serial_request_seen<=0;serial_context_valid<=0;serial_frame_error<=0;
            serial_generation<=0;serial_session<=0;serial_epoch<=0;serial_fence<=0;serial_baseline<=0;serial_rate<=0;
            held_reply<=0;reply_toggle<=0;
        end else begin
            request_sync<={request_sync[0],request_toggle};fence_meta<=fence_gray;fence_sync<=fence_meta;
            if(serial_context_valid && serial_fence!=fence_sync)serial_context_valid<=0;
            case(serial_state)
                IDLE:if(request_sync[1]!=reply_toggle)begin
                    serial_token<=held_request;serial_request_seen<=request_sync[1];serial_state<=VALIDATE;
                end
                VALIDATE:if(token_fence!=fence_sync)retire(CANCELLED,0,0,1);
                    else if(!token_kind)begin
                        serial_rate<=token_rate;serial_generation<=token_generation;serial_session<=token_session;
                        serial_epoch<=token_epoch;serial_fence<=token_fence;serial_baseline<=observation_source_drops_i;
                        serial_context_valid<=1;retire(OK,observation_source_drops_i,observation_source_drops_i,0);
                    end else if(!token_context)retire(BAD_CONTEXT,0,0,1);
                    else serial_state<=WAIT_FRAME;
                WAIT_FRAME:if(token_fence!=fence_sync)retire(CANCELLED,serial_baseline,observation_source_drops_i,1);
                    else if(physical_valid_i && physical_44k1_i==token_rate && physical_epoch_i==token_epoch &&
                            physical_sequence_i==token_sequence)begin
                        serial_frame_error<=physical_error_i;serial_state<=WATERMARK;
                    end
                WATERMARK:begin
                    // The actual observation queue processes this same physical
                    // pulse on the preceding edge. Its registered source drop
                    // count now includes the matched tail's accept/drop action.
                    // Without this real source edge no success receipt exists.
                    if(token_fence!=fence_sync)retire(CANCELLED,serial_baseline,observation_source_drops_i,1);
                    else retire(OK,serial_baseline,observation_source_drops_i,serial_frame_error);
                end
                default:serial_state<=IDLE;
            endcase
        end
    end
endmodule
