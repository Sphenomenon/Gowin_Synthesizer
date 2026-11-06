`timescale 1ns/1ps
`default_nettype none
// Source-only composition: existing full private effects, one leased reverb,
// and the bounded remote worker. The checked seam is prepared by the named
// experiment helper. No build profile silently selects this composition.
module workstation_worker_effects_shared #(
    parameter integer DRAIN_TIMEOUT_CYCLES=4096,
    parameter integer RESTORE_TIMEOUT_CYCLES=512,
    parameter integer TRANSACTION_TIMEOUT_CYCLES=1048576,
    parameter integer PEER_TIMEOUT_CYCLES=1048576
)(
    input wire clk_i,rst_ni,clear_i,local_preempt_i,
    input wire valid_i,
    input wire signed [31:0] synth_i,pcm_left_i,pcm_right_i,vector_left_i,vector_right_i,
    input wire [15:0] synth_gain_i,pcm_gain_i,
    input wire [2:0] effect_mask_i,input wire [5:0] effect_order_i,input wire [6:0] delay_send_i,
    output wire ready_o,sample_slot_ready_o,valid_o,clip_o,
    output wire signed [31:0] left_o,right_o,
    input wire mem_clk_i,mem_rst_ni,
    output wire dwr_valid_o,output wire [64:0] dwr_data_o,input wire dwr_pop_i,drd_push_i,
    input wire [64:0] drd_data_i,output wire drd_ready_o,
    input wire config_valid_i,rate_44100_i,history_clear_i,
    output wire config_ready_o,config_applied_o,history_ready_o,history_done_o,
    output wire quiescent_o,fault_o,applied_rate_44100_o,
    output wire [31:0] applied_transaction_o,
    input wire peer_heartbeat_i,delay_dma_fault_i,output wire heartbeat_o,
    input wire admitted_i,remote_rate_44100_i,input wire [191:0] key_i,
    input wire req_valid_i,output wire req_ready_o,
    input wire [191:0] req_key_i,input wire req_rate_44100_i,req_enabled_i,
    input wire [31:0] req_sequence_i,input wire signed [31:0] req_left_i,req_right_i,
    output wire rsp_valid_o,input wire rsp_ready_i,
    output wire [191:0] rsp_key_o,output wire rsp_rate_44100_o,rsp_error_o,rsp_clip_o,
    output wire [31:0] rsp_sequence_o,output wire signed [31:0] rsp_left_o,rsp_right_o,
    output wire lease_granted_o,local_quiesce_o,
    output wire [31:0] lease_denied_count_o,restore_failure_count_o,rejected_count_o,timeout_count_o
);
    wire quiet,local_fault,lease_fault,away,fence,fence_ready,fence_done,history_done;
    wire chain_ready,chain_slot,chain_config_ready,chain_history_ready,chain_config_applied;
    reg internal_fence;
    wire open_local=!local_quiesce_o && !local_fault && !lease_fault && !clear_i;
    wire internal_request=fence && !local_fault && !clear_i;
    assign ready_o=open_local && chain_ready;
    assign sample_slot_ready_o=open_local && chain_slot;
    assign config_ready_o=open_local && chain_config_ready;
    assign history_ready_o=open_local && chain_history_ready;
    assign config_applied_o=chain_config_applied && !internal_fence;
    assign history_done_o=history_done && !internal_fence;
    assign fence_ready=chain_history_ready && !clear_i && !local_fault;
    assign fence_done=history_done && internal_fence;
    assign quiescent_o=quiet && !away;
    assign fault_o=local_fault || lease_fault;
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)internal_fence<=0;
        else if(internal_request && fence_ready)internal_fence<=1;
        else if(history_done)internal_fence<=0;
    end
    wire lv,le,lr,la,lo,lc,lcvalid,lcrate,lhclear,lcready,lhready,lhdone,lquiet,lrate;
    wire signed [31:0] ll,lrpcm,lol,lor;
    workstation_runtime_stereo_effects_reverb_port #(.VECTOR_ENABLE(1),
        .TRANSACTION_TIMEOUT_CYCLES(TRANSACTION_TIMEOUT_CYCLES),.PEER_TIMEOUT_CYCLES(PEER_TIMEOUT_CYCLES)) local_effects(
        .clk_i(clk_i),.rst_ni(rst_ni),.clear_i(clear_i),.valid_i(valid_i && open_local),
        .synth_i(synth_i),.pcm_left_i(pcm_left_i),.pcm_right_i(pcm_right_i),
        .vector_left_i(vector_left_i),.vector_right_i(vector_right_i),
        .synth_gain_i(synth_gain_i),.pcm_gain_i(pcm_gain_i),.effect_mask_i(effect_mask_i),
        .effect_order_i(effect_order_i),.delay_send_i(delay_send_i),
        .ready_o(chain_ready),.sample_slot_ready_o(chain_slot),.valid_o(valid_o),
        .left_o(left_o),.right_o(right_o),.clip_o(clip_o),
        .mem_clk_i(mem_clk_i),.mem_rst_ni(mem_rst_ni),.dwr_valid_o(dwr_valid_o),
        .dwr_data_o(dwr_data_o),.dwr_pop_i(dwr_pop_i),.drd_push_i(drd_push_i),
        .drd_data_i(drd_data_i),.drd_ready_o(drd_ready_o),
        .config_valid_i(config_valid_i && open_local),.rate_44100_i(rate_44100_i),
        .history_clear_i((history_clear_i && open_local) || internal_request),
        .config_ready_o(chain_config_ready),.config_applied_o(chain_config_applied),
        .history_ready_o(chain_history_ready),.history_done_o(history_done),
        .quiescent_o(quiet),.fault_o(local_fault),.applied_rate_44100_o(applied_rate_44100_o),
        .applied_transaction_o(applied_transaction_o),.peer_heartbeat_i(peer_heartbeat_i),
        .delay_dma_fault_i(delay_dma_fault_i),.heartbeat_o(heartbeat_o),
        .rv_away_i(away),.rv_valid_o(lv),.rv_enabled_o(le),.rv_left_o(ll),.rv_right_o(lrpcm),
        .rv_ready_i(lr),.rv_active_i(la),.rv_valid_i(lo),.rv_clip_i(lc),.rv_left_i(lol),.rv_right_i(lor),
        .rv_config_valid_o(lcvalid),.rv_history_clear_o(lhclear),.rv_rate_o(lcrate),
        .rv_config_ready_i(lcready),.rv_history_ready_i(lhready),
        .rv_history_done_i(lhdone),.rv_quiescent_i(lquiet),.rv_applied_rate_i(lrate));
    wire claim,rclear,rcfg,rrate,rcfgready,rcfgdone,rv,re,rr,ro,rc;
    wire signed [31:0] rl,rrpcm,rol,ror;
    workstation_shared_spatial_reverb #(.DRAIN_TIMEOUT_CYCLES(DRAIN_TIMEOUT_CYCLES),
        .RESTORE_TIMEOUT_CYCLES(RESTORE_TIMEOUT_CYCLES)) shared_engine(
        .clk_i(clk_i),.rst_ni(rst_ni),.clear_i(clear_i),.local_preempt_i(local_preempt_i),
        .local_fault_i(local_fault),.local_quiescent_i(quiet),.local_quiesce_o(local_quiesce_o),
        .local_away_o(away),.local_fence_valid_o(fence),.local_fence_ready_i(fence_ready),.local_fence_done_i(fence_done),
        .valid_i(lv),.enabled_i(le),.left_i(ll),.right_i(lrpcm),.ready_o(lr),.active_o(la),
        .valid_o(lo),.clip_o(lc),.left_o(lol),.right_o(lor),.config_valid_i(lcvalid),
        .rate_44100_i(lcrate),.history_clear_i(lhclear),.config_ready_o(lcready),.config_applied_o(),
        .history_ready_o(lhready),.history_done_o(lhdone),.quiescent_o(lquiet),.applied_rate_44100_o(lrate),
        .remote_claim_i(claim),.remote_grant_o(lease_granted_o),.remote_clear_i(rclear),
        .remote_config_valid_i(rcfg),.remote_rate_44100_i(rrate),.remote_config_ready_o(rcfgready),
        .remote_config_applied_o(rcfgdone),.remote_valid_i(rv),.remote_enabled_i(re),.remote_left_i(rl),.remote_right_i(rrpcm),
        .remote_ready_o(rr),.remote_valid_o(ro),.remote_clip_o(rc),.remote_left_o(rol),.remote_right_o(ror),
        .fault_o(lease_fault),.denied_count_o(lease_denied_count_o),.restore_failure_count_o(restore_failure_count_o));
    workstation_remote_effect_stream_w worker(
        .clk_i(clk_i),.reset_ni(rst_ni),.clear_i(clear_i || fault_o),.admitted_i(admitted_i),
        .engine_lease_i(lease_granted_o),.rate_44100_i(remote_rate_44100_i),.key_i(key_i),
        .req_valid_i(req_valid_i),.req_ready_o(req_ready_o),.req_key_i(req_key_i),.req_rate_44100_i(req_rate_44100_i),
        .req_enabled_i(req_enabled_i),.req_sequence_i(req_sequence_i),.req_left_i(req_left_i),.req_right_i(req_right_i),
        .rsp_valid_o(rsp_valid_o),.rsp_ready_i(rsp_ready_i),.rsp_key_o(rsp_key_o),.rsp_rate_44100_o(rsp_rate_44100_o),
        .rsp_error_o(rsp_error_o),.rsp_clip_o(rsp_clip_o),.rsp_sequence_o(rsp_sequence_o),
        .rsp_left_o(rsp_left_o),.rsp_right_o(rsp_right_o),.engine_claim_o(claim),.engine_clear_o(rclear),
        .engine_config_valid_o(rcfg),.engine_rate_44100_o(rrate),.engine_config_ready_i(rcfgready),.engine_config_applied_i(rcfgdone),
        .engine_valid_o(rv),.engine_enabled_o(re),.engine_left_o(rl),.engine_right_o(rrpcm),
        .engine_ready_i(rr),.engine_result_valid_i(ro),.engine_clip_i(rc),.engine_left_i(rol),.engine_right_i(ror),
        .rejected_count_o(rejected_count_o),.timeout_count_o(timeout_count_o));
endmodule
`default_nettype wire
