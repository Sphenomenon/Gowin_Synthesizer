`timescale 1ns/1ps

// Optional, page-local command observer in the always-on 50-MHz domain.
// reset_ni belongs to the APB/CPU owner; it NEVER resets the audio hardware.
// The existing predecoded gw138k_apb_cdc supplies one stable local edge before
// command_valid_i. This service must be the sole requester of its clock core.
module workstation_audio_clock_service #(
    parameter integer ACCEPT_TIMEOUT_CYCLES = 32,
    parameter integer RESULT_TIMEOUT_CYCLES = 20000000,
    parameter integer REARM_QUIET_CYCLES = 4,
    parameter bit RESERVE_ZERO_EPOCH = 0
) (
    input wire clk_i, reset_ni,
    input wire command_valid_i, command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output wire command_ready_o,
    output reg [31:0] response_data_o,
    output reg response_error_o,
    input wire switch_permit_i,
    input wire core_request_ready_i, core_busy_i, core_fault_i, core_dsp_fault_i,
    input wire core_accepted_i, core_applied_i, core_rejected_i,
    input wire core_policy_rejected_i, core_failed_i,
    input wire [2:0] core_reject_code_i,
    input wire [3:0] core_fault_code_i,
    input wire core_active_44k1_i, core_active_valid_i,
    input wire [31:0] core_stream_epoch_i,
    input wire [1:0] core_source_qualified_i,
    output reg request_o, request_44k1_o, recover_o
);
    localparam [1:0] IDLE=0, ISSUE=1, WAIT_ACCEPT=2, WAIT_APPLY=3;
    localparam [3:0] RESULT_NONE=0, RESULT_APPLIED=1, RESULT_CORE_REJECT=2,
        RESULT_POLICY_REJECT=3, RESULT_FAILED=4, RESULT_ACCEPT_TIMEOUT=5,
        RESULT_APPLY_TIMEOUT=6, RESULT_CONTEXT_MISMATCH=7;
    localparam [3:0] BUS_OK=0, BUS_ADDRESS=1, BUS_READ_ONLY=2, BUS_STROBES=3,
        BUS_VALUE=4, BUS_PENDING=5, BUS_UNARMED=6, BUS_DESYNCHRONIZED=7,
        BUS_NO_PERMIT=8, BUS_BUSY=9, BUS_DSP_FAULT=10, BUS_NOT_READY=11,
        BUS_RECOVER_STATE=12, BUS_SOURCE_UNQUALIFIED=13;
    localparam integer TIMER_BITS=$clog2(RESULT_TIMEOUT_CYCLES+1) > $clog2(ACCEPT_TIMEOUT_CYCLES+1)
        ? $clog2(RESULT_TIMEOUT_CYCLES+1) : $clog2(ACCEPT_TIMEOUT_CYCLES+1);
    localparam integer QUIET_BITS=$clog2(REARM_QUIET_CYCLES+1);
    reg [1:0] phase;
    reg command_seen, armed, correlation_fault;
    reg [QUIET_BITS-1:0] quiet_count;
    reg [TIMER_BITS-1:0] timer;
    reg [5:0] word_address;
    reg address_aligned;
    reg [31:0] command_id, result_id, accepted_id;
    reg [1:0] operation;
    reg expected_rate;
    reg [31:0] base_epoch, expected_epoch;
    reg [3:0] result_code, last_bus_reject;
    reg [15:0] result_detail;
    reg [31:0] submitted_count, accepted_count, applied_count, failed_count;
    reg [31:0] bus_reject_count, unowned_event_count;
    reg [31:0] snapshot_epoch;
    reg snapshot_valid;
    wire any_core_event=core_accepted_i || core_applied_i || core_rejected_i ||
        core_policy_rejected_i || core_failed_i;
    wire [31:0] next_id=command_id==32'hffffffff ? 32'd1 : command_id+1'b1;
    wire recovering=operation==2;
    wire [31:0] following_epoch=RESERVE_ZERO_EPOCH && core_stream_epoch_i==32'hffffffff
        ? 32'd1 : core_stream_epoch_i+1'b1;
    wire context_matches=core_active_valid_i && !core_fault_i && !core_dsp_fault_i &&
        core_active_44k1_i==expected_rate && core_stream_epoch_i==expected_epoch;
    wire [31:0] actual_status={23'b0,core_source_qualified_i,switch_permit_i,
        core_dsp_fault_i,core_fault_i,core_request_ready_i,core_busy_i,
        core_active_valid_i,core_active_44k1_i};
    reg known_address;
    reg [3:0] admission_error;
    wire bus_fire=command_valid_i && command_ready_o;
    wire submit=bus_fire && command_write_i && !response_error_o;
    assign command_ready_o=reset_ni && !command_seen;

    initial begin
        if(ACCEPT_TIMEOUT_CYCLES<4 || RESULT_TIMEOUT_CYCLES<4 || REARM_QUIET_CYCLES<3)
            $fatal(1,"Clock service timeout/rearm configuration invalid");
    end
    function automatic [31:0] increment_saturated(input [31:0] value);
        increment_saturated=&value ? value : value+1'b1;
    endfunction
    task automatic finish(input [3:0] code, input bit lose_correlation);
        begin
            phase<=IDLE;
            timer<=0;
            result_id<=command_id;
            result_code<=code;
            result_detail<={2'b0,core_dsp_fault_i,core_fault_i,core_failed_i,
                core_policy_rejected_i,core_rejected_i,core_applied_i,
                core_accepted_i,core_fault_code_i,core_reject_code_i};
            if(code==RESULT_APPLIED)applied_count<=increment_saturated(applied_count);
            else failed_count<=increment_saturated(failed_count);
            if(lose_correlation)correlation_fault<=1;
        end
    endtask

    // Decode only the local held request, never the asynchronous source word.
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin word_address<=0;address_aligned<=0;end
        else begin
            word_address<=command_address_i[7:2];
            address_aligned<=command_address_i[11:8]==0 && command_address_i[1:0]==0;
        end
    end
    always @* begin
        known_address=word_address<=6'h17;
        admission_error=BUS_OK;
        if(!address_aligned || !known_address)admission_error=BUS_ADDRESS;
        else if(command_write_i && word_address!=6'h02)admission_error=BUS_READ_ONLY;
        else if(!command_write_i && word_address==6'h02)admission_error=BUS_ADDRESS;
        else if(command_write_i)begin
            if(command_strobes_i!=4'hf)admission_error=BUS_STROBES;
            else if(command_data_i>2)admission_error=BUS_VALUE;
            else if(phase!=IDLE)admission_error=BUS_PENDING;
            else if(correlation_fault)admission_error=BUS_DESYNCHRONIZED;
            else if(!armed)admission_error=BUS_UNARMED;
            else if(!switch_permit_i)admission_error=BUS_NO_PERMIT;
            else if(core_dsp_fault_i)admission_error=BUS_DSP_FAULT;
            else if(core_busy_i)admission_error=BUS_BUSY;
            else if(command_data_i==2)begin
                if(!core_fault_i)admission_error=BUS_RECOVER_STATE;
                else if(!core_source_qualified_i[core_active_44k1_i])admission_error=BUS_SOURCE_UNQUALIFIED;
            end else if(core_fault_i || !core_request_ready_i || !core_active_valid_i)
                admission_error=BUS_NOT_READY;
            else if(!core_source_qualified_i[command_data_i[0]])admission_error=BUS_SOURCE_UNQUALIFIED;
        end
        response_error_o=admission_error!=BUS_OK;
        response_data_o=0;
        case(word_address)
            6'h00:response_data_o=32'h434c4b01;
            6'h01:response_data_o=32'h00010007 | (32'(RESERVE_ZERO_EPOCH)<<3);
            6'h02:response_data_o=response_error_o ? {28'b0,admission_error} : next_id;
            6'h03:response_data_o={26'b0,snapshot_valid,correlation_fault,armed,1'b0,phase};
            6'h04:response_data_o=command_id;
            6'h05:response_data_o={30'b0,operation};
            6'h06:response_data_o=result_id;
            6'h07:response_data_o={28'b0,result_code};
            6'h08:response_data_o={16'b0,result_detail};
            6'h09:response_data_o=base_epoch;
            6'h0a:response_data_o=expected_epoch;
            6'h0b:response_data_o=actual_status;
            6'h0c:response_data_o=snapshot_epoch;
            6'h0d:response_data_o=submitted_count;
            6'h0e:response_data_o=accepted_count;
            6'h0f:response_data_o=applied_count;
            6'h10:response_data_o=failed_count;
            6'h11:response_data_o=bus_reject_count;
            6'h12:response_data_o=unowned_event_count;
            6'h13:response_data_o={28'b0,last_bus_reject};
            6'h14:response_data_o=32'(ACCEPT_TIMEOUT_CYCLES);
            6'h15:response_data_o=32'(RESULT_TIMEOUT_CYCLES);
            6'h16:response_data_o={30'b0,recovering,expected_rate};
            6'h17:response_data_o=accepted_id;
            default:response_data_o=0;
        endcase
    end
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            phase<=IDLE;command_seen<=0;armed<=0;correlation_fault<=0;quiet_count<=0;timer<=0;
            command_id<=0;result_id<=0;accepted_id<=0;operation<=0;expected_rate<=0;
            base_epoch<=0;expected_epoch<=0;result_code<=RESULT_NONE;result_detail<=0;
            last_bus_reject<=BUS_OK;submitted_count<=0;accepted_count<=0;applied_count<=0;
            failed_count<=0;bus_reject_count<=0;unowned_event_count<=0;
            snapshot_epoch<=0;snapshot_valid<=0;request_o<=0;request_44k1_o<=0;recover_o<=0;
        end else begin
            request_o<=0;recover_o<=0;
            if(!command_valid_i)command_seen<=0;
            else if(bus_fire)command_seen<=1;
            if(!armed)begin
                if(core_busy_i || any_core_event)quiet_count<=0;
                else if(quiet_count==QUIET_BITS'(REARM_QUIET_CYCLES-1))armed<=1;
                else quiet_count<=quiet_count+1'b1;
            end
            if(any_core_event && (phase==IDLE || phase==ISSUE ||
                (phase==WAIT_ACCEPT && core_applied_i && !core_accepted_i && !(recovering && core_busy_i))))
                unowned_event_count<=increment_saturated(unowned_event_count);
            if(bus_fire && response_error_o)begin
                bus_reject_count<=increment_saturated(bus_reject_count);
                last_bus_reject<=admission_error;
            end
            if(bus_fire && !command_write_i && !response_error_o && word_address==6'h0b)begin
                snapshot_epoch<=core_stream_epoch_i;snapshot_valid<=1;
            end
            if(submit)begin
                command_id<=next_id;operation<=command_data_i[1:0];
                expected_rate<=command_data_i==2 ? core_active_44k1_i : command_data_i[0];
                base_epoch<=core_stream_epoch_i;
                expected_epoch<=command_data_i==2 || command_data_i[0]!=core_active_44k1_i
                    ? following_epoch : core_stream_epoch_i;
                submitted_count<=increment_saturated(submitted_count);
                request_44k1_o<=command_data_i[0];
                request_o<=command_data_i!=2;recover_o<=command_data_i==2;
                phase<=ISSUE;timer<=0;
            end
            case(phase)
                ISSUE:begin phase<=WAIT_ACCEPT;timer<=0;end
                WAIT_ACCEPT:begin
                    if(core_policy_rejected_i)finish(RESULT_POLICY_REJECT,0);
                    else if(core_rejected_i)finish(RESULT_CORE_REJECT,0);
                    else if(core_failed_i || core_dsp_fault_i || (!recovering && core_fault_i))finish(RESULT_FAILED,0);
                    else if(core_accepted_i || (recovering && core_busy_i && !core_fault_i))begin
                        accepted_count<=increment_saturated(accepted_count);accepted_id<=command_id;
                        if(core_applied_i)begin
                            if(context_matches)finish(RESULT_APPLIED,0);
                            else finish(RESULT_CONTEXT_MISMATCH,1);
                        end else begin phase<=WAIT_APPLY;timer<=0;end
                    end else if(timer==TIMER_BITS'(ACCEPT_TIMEOUT_CYCLES-1))finish(RESULT_ACCEPT_TIMEOUT,1);
                    else timer<=timer+1'b1;
                end
                WAIT_APPLY:begin
                    if(core_policy_rejected_i)finish(RESULT_POLICY_REJECT,0);
                    else if(core_rejected_i)finish(RESULT_CORE_REJECT,0);
                    else if(core_failed_i || core_fault_i || core_dsp_fault_i)finish(RESULT_FAILED,0);
                    else if(core_applied_i)begin
                        if(context_matches)finish(RESULT_APPLIED,0);
                        else finish(RESULT_CONTEXT_MISMATCH,1);
                    end else if(timer==TIMER_BITS'(RESULT_TIMEOUT_CYCLES-1))finish(RESULT_APPLY_TIMEOUT,1);
                    else timer<=timer+1'b1;
                end
                default:begin end
            endcase
        end
    end
endmodule
