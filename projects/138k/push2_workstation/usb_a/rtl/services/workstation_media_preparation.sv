`timescale 1ns/1ps

// Always-on readiness composition. The recording and runtime owners seal and
// drain their own state; this module only correlates their terminal results.
// CPU command reset is deliberately absent. A lost caller cannot release a
// still-running backend, and an old completion cannot satisfy a new request.
module workstation_media_preparation #(
    parameter bit ENABLE_BLE=0,ENABLE_RECORDING=0
) (
    input wire clk_i,reset_ni,
    input wire request_i,hold_i,
    output wire ready_o,
    output wire done_o,failed_o,
    output wire [3:0] failure_code_o,
    output wire runtime_request_o,runtime_hold_o,
    input wire runtime_ready_i,runtime_done_i,runtime_failed_i,
    input wire [3:0] runtime_failure_code_i,
    output wire ble_request_o,ble_hold_o,
    input wire ble_ready_i,ble_done_i,ble_failed_i,
    input wire [3:0] ble_failure_code_i,
    output wire [3:0] ble_failure_code_o,
    output wire recording_request_o,recording_hold_o,
    input wire recording_ready_i,recording_done_i,recording_failed_i,
    input wire [3:0] recording_failure_code_i,
    output wire [3:0] recording_failure_code_o
);
    generate if(!ENABLE_BLE && !ENABLE_RECORDING)begin: g_legacy
        assign ready_o=runtime_ready_i,done_o=runtime_done_i,failed_o=runtime_failed_i;
        assign failure_code_o=runtime_failure_code_i;
        assign runtime_request_o=request_i,runtime_hold_o=hold_i;
        assign ble_request_o=0,ble_hold_o=0,ble_failure_code_o=0;
        assign recording_request_o=0,recording_hold_o=0,recording_failure_code_o=0;
    end else begin: g_combined
        localparam [1:0] IDLE=0,WAIT_RESULT=1,RELEASE=2;
        reg [1:0] state;
        reg held,runtime_request,ble_request,recording_request,done,failed;
        reg runtime_terminal,ble_terminal,recording_terminal,runtime_failure,ble_failure,recording_failure;
        reg [3:0] failure_code,ble_code,recording_code;
        wire both_ready=runtime_ready_i && (!ENABLE_BLE || ble_ready_i) && (!ENABLE_RECORDING || recording_ready_i);
        // Requests are registered. Ignore a terminal already present at their
        // delivery edge; a registered owner can first answer on the next edge.
        wire runtime_finishes=!runtime_request && (runtime_done_i || runtime_failed_i);
        wire ble_finishes=ENABLE_BLE && !ble_request && (ble_done_i || ble_failed_i);
        wire recording_finishes=ENABLE_RECORDING && !recording_request && (recording_done_i || recording_failed_i);
        assign ready_o=state==IDLE && !held && both_ready;
        assign done_o=done,failed_o=failed,failure_code_o=failure_code;
        assign runtime_request_o=runtime_request,ble_request_o=ble_request;
        assign recording_request_o=recording_request,recording_hold_o=held,recording_failure_code_o=recording_code;
        assign runtime_hold_o=held,ble_hold_o=held,ble_failure_code_o=ble_code;
        always @(posedge clk_i or negedge reset_ni)begin
            if(!reset_ni)begin
                state<=IDLE;held<=0;runtime_request<=0;ble_request<=0;recording_request<=0;done<=0;failed<=0;
                runtime_terminal<=0;ble_terminal<=!ENABLE_BLE;recording_terminal<=!ENABLE_RECORDING;runtime_failure<=0;ble_failure<=0;recording_failure<=0;
                failure_code<=0;ble_code<=0;recording_code<=0;
            end else begin
                runtime_request<=0;ble_request<=0;recording_request<=0;done<=0;failed<=0;
                case(state)
                    IDLE:if(request_i)begin
                        if(!both_ready)begin
                            // Admission normally observes ready_o first.
                            failed<=1;failure_code<=11;
                        end else begin
                            held<=1;runtime_request<=1;ble_request<=ENABLE_BLE;recording_request<=ENABLE_RECORDING;state<=WAIT_RESULT;
                            runtime_terminal<=0;ble_terminal<=!ENABLE_BLE;recording_terminal<=!ENABLE_RECORDING;runtime_failure<=0;ble_failure<=0;recording_failure<=0;
                            failure_code<=0;ble_code<=0;recording_code<=0;
                        end
                    end
                    WAIT_RESULT:begin
                        if(!runtime_terminal && runtime_finishes)begin
                            runtime_terminal<=1;runtime_failure<=runtime_failed_i;
                            if(runtime_failed_i)failure_code<=runtime_failure_code_i;
                        end
                        if(!ble_terminal && ble_finishes)begin
                            ble_terminal<=1;ble_failure<=ble_failed_i;
                            if(ble_failed_i)ble_code<=ble_failure_code_i;
                        end
                        if(!recording_terminal && recording_finishes)begin
                            recording_terminal<=1;recording_failure<=recording_failed_i;
                            if(recording_failed_i)recording_code<=recording_failure_code_i;
                        end
                        if((runtime_terminal || runtime_finishes) && (ble_terminal || ble_finishes) &&
                            (recording_terminal || recording_finishes))begin
                            if(runtime_failure || (!runtime_terminal && runtime_failed_i))begin
                                failed<=1;
                            end else if(ble_failure || (!ble_terminal && ble_failed_i))begin
                                failed<=1;failure_code<=10;
                            end else if(recording_failure || (!recording_terminal && recording_failed_i))begin
                                failed<=1;failure_code<=12;
                            end else done<=1;
                            state<=RELEASE;
                        end
                    end
                    RELEASE:if(!hold_i)begin
                        held<=0;
                        // Backends keep their own failure/drain fences until
                        // actually ready; no new request reuses their old ACK.
                        if(!held && both_ready)state<=IDLE;
                    end
                    default:state<=IDLE;
                endcase
            end
        end
    end endgenerate
endmodule
