`timescale 1ns/1ps
`default_nettype none
// One outstanding normal-seal transaction. Common reset asserts both domains
// asynchronously; each domain releases locally. A CPU observer reset is
// deliberately not a channel reset and cannot abandon an accepted seal.
module workstation_recording_seal_bridge(
    input wire reset_ni,source_clk_i,destination_clk_i,
    input wire request_i,hold_i,
    output wire ready_o,
    output reg done_o,failed_o,
    output reg [3:0] failure_code_o,
    output wire destination_hold_o,
    output reg destination_request_o,
    input wire destination_ready_i,destination_done_i,destination_failed_i,
    input wire [3:0] destination_failure_code_i
);
    (* ASYNC_REG="TRUE" *) reg source_release_meta,source_release_sync;
    (* ASYNC_REG="TRUE" *) reg destination_release_meta,destination_release_sync;
    wire source_reset_n=source_release_sync;
    wire destination_reset_n=destination_release_sync;
    always @(posedge source_clk_i or negedge reset_ni)begin
        if(!reset_ni)begin source_release_meta<=0;source_release_sync<=0;end
        else begin source_release_meta<=1;source_release_sync<=source_release_meta;end
    end
    always @(posedge destination_clk_i or negedge reset_ni)begin
        if(!reset_ni)begin destination_release_meta<=0;destination_release_sync<=0;end
        else begin destination_release_meta<=1;destination_release_sync<=destination_release_meta;end
    end
    reg request_toggle,source_pending,result_seen,source_hold;
    reg result_toggle,result_failed;
    reg [3:0] result_code;
    reg request_seen,destination_pending,destination_ready;
    (* ASYNC_REG="TRUE" *) reg request_meta,request_sync,hold_meta,hold_sync;
    (* ASYNC_REG="TRUE" *) reg result_meta,result_sync,ready_meta,ready_sync;
    assign ready_o=source_reset_n && !source_pending && !hold_i && ready_sync;
    assign destination_hold_o=hold_sync;
    always @(posedge source_clk_i or negedge source_reset_n)begin
        if(!source_reset_n)begin
            request_toggle<=0;source_pending<=0;result_seen<=0;
            source_hold<=0;
            result_meta<=0;result_sync<=0;ready_meta<=0;ready_sync<=0;
            done_o<=0;failed_o<=0;failure_code_o<=0;
        end else begin
            result_meta<=result_toggle;result_sync<=result_meta;
            // Cross one registered memory-domain status, never its raw reset
            // or a combinational mixture of ready/pending/hold inputs.
            ready_meta<=destination_ready;
            ready_sync<=ready_meta;done_o<=0;failed_o<=0;
            source_hold<=hold_i || source_pending;
            // The caller observes ready before registering request and hold
            // together. Do not use ready_o (which includes this new hold).
            if(request_i && !source_pending && ready_sync)begin
                request_toggle<=~request_toggle;source_pending<=1;source_hold<=1;
                failure_code_o<=0;
            end
            if(source_pending && result_sync!=result_seen)begin
                result_seen<=result_sync;source_pending<=0;
                done_o<=!result_failed;failed_o<=result_failed;failure_code_o<=result_code;
            end
        end
    end
    always @(posedge destination_clk_i or negedge destination_reset_n)begin
        if(!destination_reset_n)begin
            request_meta<=0;request_sync<=0;hold_meta<=0;hold_sync<=0;
            request_seen<=0;destination_pending<=0;destination_request_o<=0;destination_ready<=0;
            result_toggle<=0;result_failed<=0;result_code<=0;
        end else begin
            request_meta<=request_toggle;request_sync<=request_meta;
            hold_meta<=source_hold;hold_sync<=hold_meta;destination_request_o<=0;
            destination_ready<=destination_ready_i && !destination_pending && !hold_sync;
            if(request_sync!=request_seen && !destination_pending)begin
                request_seen<=request_sync;
                if(destination_ready_i)begin destination_request_o<=1;destination_pending<=1;end
                else begin result_failed<=1;result_code<=11;result_toggle<=~result_toggle;end
            end
            // Ignore an old terminal at the request delivery edge.
            if(destination_pending && !destination_request_o && (destination_done_i || destination_failed_i))begin
                destination_pending<=0;result_failed<=destination_failed_i;
                result_code<=destination_failed_i ? destination_failure_code_i:4'd0;result_toggle<=~result_toggle;
            end
        end
    end
endmodule
`default_nettype wire
