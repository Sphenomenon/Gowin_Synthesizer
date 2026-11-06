"""Exact, reversible effects broadcast experiment; no profile selects it.

Retire this adapter after full effects, composed-workstation and physical
validation allow explicit versioned composition integration, or retain only
failed experiment evidence. Never rewrite the maintained parent or its locks.
"""
import hashlib

SOURCE='rtl/audio/workstation_runtime_stereo_effects.sv'
DISPATCH='rtl/audio/workstation_effects_config_dispatch.sv'
POLICY='effects_reserved_config_broadcast_experiment_v1'
# Filled from the inspected maintained source, not from a historical staging.
PARENT_SHA256='50d18332d820f8bc11f272726b6ed51190cd3ec4acde666c9ef4d0c511ab4e13'
ANCHOR='  wire clear_start=clear_i && !barrier_busy;'
BLOCK='''  wire dispatch_pending,dispatch_config,dispatch_history,dispatch_rate;
  workstation_effects_config_dispatch config_dispatch(
      .clk_i,.rst_ni,.reserve_config_i(config_accept),.reserve_history_i(history_accept),
      .rate_44100_i,.clear_i,.fault_i(fault_o),
      .all_config_ready_i(&stage_config_ready),.all_history_ready_i(&stage_history_ready),
      .all_quiet_i(&stage_quiet),.pending_o(dispatch_pending),
      .config_valid_o(dispatch_config),.history_valid_o(dispatch_history),
      .rate_44100_o(dispatch_rate));
'''
EDITS=(
    ('wire complete_barrier=barrier_busy && !clear_i && (&next_seen) && (&stage_quiet);',
     'wire complete_barrier=barrier_busy && !dispatch_pending && !clear_i && (&next_seen) && (&stage_quiet);',1),
    ('        barrier_seen<=next_seen;',
     '        barrier_seen<=dispatch_pending ? 3\'b000 : next_seen;',1),
    ('.config_valid_i(config_accept),.rate_44100_i(rate_44100_i)',
     '.config_valid_i(dispatch_config),.rate_44100_i(dispatch_rate)',4),
    ('.history_clear_i(history_accept),.config_ready_o(stage_config_ready[0])',
     '.history_clear_i(dispatch_history),.config_ready_o(stage_config_ready[0])',1),
    ('.history_clear_i(history_accept),\n      .config_ready_o(stage_config_ready[1])',
     '.history_clear_i(dispatch_history),\n      .config_ready_o(stage_config_ready[1])',1),
    ('.history_clear_i(history_accept),\n      .config_ready_o(stage_config_ready[2])',
     '.history_clear_i(dispatch_history),\n      .config_ready_o(stage_config_ready[2])',2),
)

def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text,str) else text).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('effects dispatch experiment: '+message)

def apply(text):
    require(digest(text)==PARENT_SHA256,'exact maintained parent required')
    require(text.count(ANCHOR)==1 and 'dispatch_pending' not in text,'insertion boundary changed')
    selected=text.replace(ANCHOR,BLOCK+ANCHOR,1)
    for before,after,count in EDITS:
        require(selected.count(before)==count and after not in selected,'child/barrier anchor changed')
        selected=selected.replace(before,after)
    return selected

def restore(text):
    require(text.count(BLOCK)==1,'complete dispatch instance required')
    parent=text.replace(BLOCK,'',1)
    for before,after,count in EDITS:
        require(parent.count(after)==count and before not in parent,'barrier/child adaptation changed')
        parent=parent.replace(after,before)
    require(digest(parent)==PARENT_SHA256,'unrelated effects behavior changed')
    require(apply(parent)==text,'selected bytes changed')
    return parent

def evidence(text):
    restore(text)
    return dict(policy=POLICY,parent_sha256=PARENT_SHA256,selected_sha256=digest(text),
        normal_sample_datapath_unchanged=True,minimum_added_configuration_cycles=1,
        PANIC_retains_reserved_configuration=True,child_ACKs_ignored_until_dispatch=True,
        production_profile_selected=False,full_system_synthesis_verified=False,
        routed_timing_verified=False,hardware_tested=False)
