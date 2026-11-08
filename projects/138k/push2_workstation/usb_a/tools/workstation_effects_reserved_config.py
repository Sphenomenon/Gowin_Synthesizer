"""Explicit paired M held effects configuration; exact historical inverse.

Only the parameter default is selected in staging. Retire this selection
adapter when the versioned parent provider can pass the option explicitly.
The normal audio datapath and sample edges are unchanged.
"""
from pathlib import Path
import hashlib
SOURCE='rtl/audio/workstation_runtime_stereo_effects.sv'
TOOL='tools/workstation_effects_reserved_config.py'
DISPATCH='rtl/audio/workstation_effects_config_dispatch.sv'
KEY='effects_dispatch_policy'
POLICY='task3_M_reserved_effects_configuration_v1'
W_POLICY='task3_W_reserved_effects_configuration_v1'
DEFAULT='parameter bit RESERVED_CONFIG_DISPATCH_ENABLE=0'
SELECTED='parameter bit RESERVED_CONFIG_DISPATCH_ENABLE=1'
PARENT_SHA256='9583b6a9f4d4359018da4fdbbe08b5d8ed4eb34d9a126b1643314d5a21838036'
NATIVE_SHA256='67bb421dd9f60bcbdaad2c6c22a40d15519620f7d4aab7ecfea69a608a1e3085'
EDITS=[('    parameter integer VECTOR_ENABLE=0,\n', '    parameter integer VECTOR_ENABLE=0,\n    parameter bit RESERVED_CONFIG_DISPATCH_ENABLE=0,\n'), ('  wire clear_start=clear_i && !barrier_busy;', "  wire dispatch_pending,dispatch_config,dispatch_history,dispatch_rate;\n  generate if(RESERVED_CONFIG_DISPATCH_ENABLE)begin:g_reserved_config\n    // Reserve in the existing barrier; children see held data on a later edge.\n    workstation_effects_config_dispatch config_dispatch(\n        .clk_i,.rst_ni,.reserve_config_i(config_accept),.reserve_history_i(history_accept),\n        .rate_44100_i,.clear_i,.fault_i(fault_o),\n        .all_config_ready_i(&stage_config_ready),.all_history_ready_i(&stage_history_ready),\n        .all_quiet_i(&stage_quiet),.pending_o(dispatch_pending),\n        .config_valid_o(dispatch_config),.history_valid_o(dispatch_history),\n        .rate_44100_o(dispatch_rate));\n  end else begin:g_direct_config\n    assign dispatch_pending=1'b0;\n    assign dispatch_config=config_accept;\n    assign dispatch_history=history_accept;\n    assign dispatch_rate=rate_44100_i;\n  end endgenerate\n  wire clear_start=clear_i && !barrier_busy;"), ('wire complete_barrier=barrier_busy && !clear_i && (&next_seen) && (&stage_quiet);', 'wire complete_barrier=barrier_busy && !dispatch_pending && !clear_i && (&next_seen) && (&stage_quiet);'), ('        barrier_seen<=next_seen;', "        barrier_seen<=dispatch_pending ? 3'b000 : next_seen;"), ('.config_valid_i(config_accept),.rate_44100_i(rate_44100_i)', '.config_valid_i(dispatch_config),.rate_44100_i(dispatch_rate)'), ('.history_clear_i(history_accept),.config_ready_o(stage_config_ready[0])', '.history_clear_i(dispatch_history),.config_ready_o(stage_config_ready[0])'), ('.history_clear_i(history_accept),\n      .config_ready_o(stage_config_ready[1])', '.history_clear_i(dispatch_history),\n      .config_ready_o(stage_config_ready[1])'), ('.history_clear_i(history_accept),\n      .config_ready_o(stage_config_ready[2])', '.history_clear_i(dispatch_history),\n      .config_ready_o(stage_config_ready[2])')]

def digest(b):return hashlib.sha256(b.encode() if isinstance(b,str)else b).hexdigest()

def normalize(source):
    text=source.decode() if isinstance(source,bytes)else source
    if SELECTED in text:
        if text.count(SELECTED)!=1:raise ValueError('duplicate reserved effects selection')
        text=text.replace(SELECTED,DEFAULT,1)
    if digest(text)!=NATIVE_SHA256:return source
    for before,after in reversed(EDITS):
        if after not in text:raise ValueError('reserved effects inverse anchor changed')
        text=text.replace(after,before)
    if digest(text)!=PARENT_SHA256:raise ValueError('reserved effects parent changed')
    return text.encode() if isinstance(source,bytes)else text

def configured(configuration):
    value=configuration.get(KEY)
    if value not in (None,POLICY,W_POLICY):raise ValueError('unknown effects dispatch policy')
    if value and configuration.get('demo_role')!=('M' if value==POLICY else 'W'):
        raise ValueError('reserved effects role/policy mismatch')
    return value is not None

def select(stage,configuration):
    if not configured(configuration):return None
    p=Path(stage)/SOURCE;text=p.read_text()
    if digest(text)!=NATIVE_SHA256 or text.count(DEFAULT)!=1:raise ValueError('reserved effects source drift')
    normalize(text);selected=text.replace(DEFAULT,SELECTED,1);p.write_text(selected)
    return dict(policy=configuration[KEY],parent_sha256=digest(text),selected_sha256=digest(selected),
        configuration_minimum_added_cycles=1,sample_schedule_changed=False,hardware_tested=False)

def evidence(stage,configuration):
    if not configured(configuration):return None
    text=(Path(stage)/SOURCE).read_text()
    if text.count(SELECTED)!=1:raise ValueError('reserved effects option absent')
    native=text.replace(SELECTED,DEFAULT,1)
    if digest(native)!=NATIVE_SHA256:raise ValueError('reserved effects selected source drift')
    normalize(text)
    return dict(policy=configuration[KEY],parent_sha256=digest(native),selected_sha256=digest(text),
        configuration_minimum_added_cycles=1,sample_schedule_changed=False,hardware_tested=False)
