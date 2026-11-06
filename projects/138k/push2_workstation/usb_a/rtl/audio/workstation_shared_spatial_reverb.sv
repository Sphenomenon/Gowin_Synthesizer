`timescale 1ns/1ps
`default_nettype none
// One physical engine, two mutually exclusive clients. A lease requires the
// complete local effects owner's real history/DDR fence, never a mute bit.
module workstation_shared_spatial_reverb #(
    parameter integer DRAIN_TIMEOUT_CYCLES=4096,
    parameter integer RESTORE_TIMEOUT_CYCLES=512
)(
    input wire clk_i,rst_ni,clear_i,local_preempt_i,local_fault_i,
    input wire local_quiescent_i,
    output wire local_quiesce_o,local_away_o,
    output wire local_fence_valid_o,
    input wire local_fence_ready_i,local_fence_done_i,
    input wire valid_i,enabled_i,
    input wire signed [31:0] left_i,right_i,
    output wire ready_o,active_o,valid_o,clip_o,
    output wire signed [31:0] left_o,right_o,
    input wire config_valid_i,rate_44100_i,history_clear_i,
    output wire config_ready_o,config_applied_o,history_ready_o,history_done_o,
    output wire quiescent_o,applied_rate_44100_o,
    input wire remote_claim_i,
    output wire remote_grant_o,
    input wire remote_clear_i,remote_config_valid_i,remote_rate_44100_i,
    output wire remote_config_ready_o,remote_config_applied_o,
    input wire remote_valid_i,remote_enabled_i,
    input wire signed [31:0] remote_left_i,remote_right_i,
    output wire remote_ready_o,remote_valid_o,remote_clip_o,
    output wire signed [31:0] remote_left_o,remote_right_o,
    output reg fault_o,
    output reg [31:0] denied_count_o,restore_failure_count_o
);
    localparam [3:0] LOCAL=0,DRAIN=1,FENCE_SEND=2,FENCE_WAIT=3,
        REMOTE=4,RETURN_CLEAR=5,RESTORE_SEND=6,RESTORE_WAIT=7,FAILED=8;
    localparam integer T=$clog2(DRAIN_TIMEOUT_CYCLES>RESTORE_TIMEOUT_CYCLES ?
        DRAIN_TIMEOUT_CYCLES : RESTORE_TIMEOUT_CYCLES);
    reg [3:0] state;
    reg [T-1:0] timer;
    reg blocked,local_rate;
    wire local_path=state==LOCAL || state==DRAIN || state==FENCE_SEND || state==FENCE_WAIT;
    wire request=remote_claim_i && !blocked && !local_preempt_i && !local_fault_i;
    assign local_quiesce_o=!rst_ni || state!=LOCAL || request;
    assign local_away_o=!local_path;
    assign remote_grant_o=rst_ni && !clear_i && state==REMOTE &&
        remote_claim_i && !local_preempt_i && !local_fault_i && !fault_o;
    assign local_fence_valid_o=rst_ni && state==FENCE_SEND && request && !clear_i;
    wire restoring=state==RETURN_CLEAR || state==RESTORE_SEND || state==RESTORE_WAIT;
    wire drain_timeout=(state==DRAIN || state==FENCE_SEND || state==FENCE_WAIT) &&
        timer==T'(DRAIN_TIMEOUT_CYCLES-1);
    wire restore_timeout=restoring && timer==T'(RESTORE_TIMEOUT_CYCLES-1);
    wire engine_ready,engine_active,engine_valid,engine_clip,engine_config_ready,engine_config_applied;
    wire engine_history_ready,engine_history_done,engine_quiet,engine_rate;
    wire signed [31:0] engine_left,engine_right;
    wire revoke=state==REMOTE && !remote_grant_o;
    wire engine_clear=clear_i || state==RETURN_CLEAR || state==FAILED || revoke ||
        (remote_grant_o && remote_clear_i);
    wire engine_config=state==RESTORE_SEND || (local_path && config_valid_i) ||
        (remote_grant_o && remote_config_valid_i);
    wire config_rate=restoring ? local_rate : local_path ? rate_44100_i : remote_rate_44100_i;
    workstation_runtime_spatial_reverb engine(
        .clk_i(clk_i),.rst_ni(rst_ni),.clear_i(engine_clear),
        .valid_i(!clear_i && ((local_path && valid_i) || (remote_grant_o && remote_valid_i))),
        .enabled_i(local_path ? enabled_i : remote_enabled_i),
        .left_i(local_path ? left_i : remote_left_i),.right_i(local_path ? right_i : remote_right_i),
        .ready_o(engine_ready),.active_o(engine_active),.valid_o(engine_valid),
        .left_o(engine_left),.right_o(engine_right),.clip_o(engine_clip),
        .config_valid_i(engine_config && !engine_clear),.rate_44100_i(config_rate),
        .history_clear_i(local_path && history_clear_i),.config_ready_o(engine_config_ready),
        .config_applied_o(engine_config_applied),.history_ready_o(engine_history_ready),
        .history_done_o(engine_history_done),.quiescent_o(engine_quiet),.applied_rate_44100_o(engine_rate));
    assign ready_o=rst_ni && local_path && engine_ready && !clear_i;
    assign active_o=local_path && engine_active;
    assign valid_o=rst_ni && local_path && engine_valid && !clear_i;
    assign clip_o=valid_o && engine_clip;
    assign left_o=engine_left,right_o=engine_right;
    assign config_ready_o=rst_ni && local_path && engine_config_ready && !clear_i;
    assign config_applied_o=rst_ni && local_path && engine_config_applied && !clear_i;
    assign history_ready_o=rst_ni && local_path && engine_history_ready && !clear_i;
    assign history_done_o=rst_ni && local_path && engine_history_done && !clear_i;
    assign quiescent_o=rst_ni && local_path && engine_quiet;
    // This is actual physical engine state, including while leased away.
    assign applied_rate_44100_o=engine_rate;
    assign remote_ready_o=remote_grant_o && engine_ready;
    assign remote_valid_o=remote_grant_o && engine_valid;
    assign remote_clip_o=remote_valid_o && engine_clip;
    assign remote_left_o=engine_left,remote_right_o=engine_right;
    assign remote_config_ready_o=remote_grant_o && engine_config_ready;
    assign remote_config_applied_o=remote_grant_o && engine_config_applied;
    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value : value+1'b1;
    endfunction
    initial if(DRAIN_TIMEOUT_CYCLES<16 || RESTORE_TIMEOUT_CYCLES<16)
        $fatal(1,"invalid shared reverb timeout");
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            state<=LOCAL;timer<=0;blocked<=0;local_rate<=0;fault_o<=0;
            denied_count_o<=0;restore_failure_count_o<=0;
        end else begin
            if(!remote_claim_i)blocked<=0;
            if(fault_o)begin state<=FAILED;timer<=0;end
            else if(clear_i)begin
                if(local_path)local_rate<=engine_rate;
                state<=RETURN_CLEAR;timer<=0;
            end else if(restore_timeout)begin
                state<=FAILED;fault_o<=1;restore_failure_count_o<=increment(restore_failure_count_o);
            end else if(drain_timeout || (local_fault_i && state!=LOCAL && local_path))begin
                // No ownership transfer occurred. Let the real local fence
                // finish/fail under its original timeout; never forge an ACK.
                state<=LOCAL;timer<=0;blocked<=1;denied_count_o<=increment(denied_count_o);
            end else begin
                if(state==LOCAL || state==REMOTE || state==FAILED)timer<=0;
                else timer<=timer+1'b1;
                case(state)
                    LOCAL:if(request)begin state<=DRAIN;timer<=0;end
                    DRAIN:if(!request)begin state<=LOCAL;timer<=0;end
                        else if(local_quiescent_i && engine_quiet)begin
                            local_rate<=engine_rate;state<=FENCE_SEND;
                        end
                    FENCE_SEND:if(!request)begin state<=LOCAL;timer<=0;end
                        else if(local_fence_ready_i)state<=FENCE_WAIT;
                    FENCE_WAIT:if(local_fence_done_i && local_quiescent_i && engine_quiet)begin
                        state<=request ? REMOTE : LOCAL;timer<=0;
                    end
                    REMOTE:if(!remote_grant_o)begin
                        state<=RETURN_CLEAR;timer<=0;blocked<=remote_claim_i;
                    end
                    RETURN_CLEAR:state<=RESTORE_SEND;
                    RESTORE_SEND:if(engine_config_ready)state<=RESTORE_WAIT;
                    RESTORE_WAIT:if(engine_config_applied)begin
                        if(engine_rate==local_rate)begin state<=LOCAL;timer<=0;end
                        else begin state<=FAILED;fault_o<=1;
                            restore_failure_count_o<=increment(restore_failure_count_o);end
                    end
                    FAILED:begin end
                    default:begin state<=FAILED;fault_o<=1;end
                endcase
            end
        end
    end
endmodule
`default_nettype wire
