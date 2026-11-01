#!/usr/bin/env python3
"""Exact inverse of the actual configuration-acceptance observer migration.

These views are proof references only. Production always consumes maintained
RTL. Original hashes and every byte outside the reviewed hunks stay locked.
"""
from pathlib import Path
import hashlib,re
ROOT=Path(__file__).resolve().parents[2]
ORIGINAL_SHA256={'rtl/audio/gw138k_event_workstation.sv': 'b689d16fc95be1b25627d1471345f572292ec72f465e6e1ff80753e558abc1a6', 'rtl/audio/workstation_audio_render_service.sv': '9c80e68049ec1a08b9d176bd1d7dcb22723e3058c7015166a051c45dcd9d2bd0', 'rtl/workstation/workstation_runtime_audio.sv': '3f2889e9616839aa4657416fa9164e5e4f79502560f8e9b0b9b32f9985a55987'}
HUNKS={'rtl/audio/gw138k_event_workstation.sv': [['    output wire rate_ready_o, applied_rate_44100_o,', '    output wire rate_ready_o, rate_accepted_o, applied_rate_44100_o,'], ['  wire engine_rate_commit;', '  wire engine_rate_commit;\n  // This is the actual same-edge broadcast acceptance, not a ready offer.\n  assign rate_accepted_o=engine_rate_commit;']], 'rtl/audio/workstation_audio_render_service.sv': [['    output wire config_ready_o,config_applied_o,history_ready_o,history_done_o,', '    output wire config_ready_o,config_accepted_o,config_applied_o,history_ready_o,history_done_o,'], ['    wire core_rate_ready,core_rate_applied,core_rate_busy,core_fault,core_rate;', '    wire core_rate_ready,core_rate_accepted,core_rate_applied,core_rate_busy,core_fault,core_rate;'], ['    assign config_ready_o=RUNTIME_EFFECTS_ENABLE && external_free && core_rate_ready;', '    assign config_ready_o=RUNTIME_EFFECTS_ENABLE && external_free && core_rate_ready;\n    // Only the external request may acknowledge its caller; an automatic\n    // rate transaction is a different owner of the same broadcast edge.\n    assign config_accepted_o=external_config && core_rate_accepted;'], ['        .rate_ready_o(core_rate_ready),.applied_rate_44100_o(core_rate),', '        .rate_ready_o(core_rate_ready),.rate_accepted_o(core_rate_accepted),.applied_rate_44100_o(core_rate),']], 'rtl/workstation/workstation_runtime_audio.sv': [['    wire config_ready,config_applied;', '    wire config_ready,config_accepted,config_applied;'], ['                CFG_ACCEPT:if(config_ready)begin', '                CFG_ACCEPT:if(config_accepted)begin'], ['        .config_ready_o(config_ready),.config_applied_o(config_applied),.history_ready_o(pcm_history_ready),.history_done_o(pcm_history_done),', '        .config_ready_o(config_ready),.config_accepted_o(config_accepted),.config_applied_o(config_applied),.history_ready_o(pcm_history_ready),.history_done_o(pcm_history_done),']]}

def reference_view(relative,text=None):
    relative=str(relative)
    if text is None:text=(ROOT/relative).read_text()
    for old,new in reversed(HUNKS[relative]):
        assert text.count(new)==1,'configuration receipt hunk drift: '+relative
        text=text.replace(new,old)
    assert hashlib.sha256(text.encode()).hexdigest()==ORIGINAL_SHA256[relative],'configuration receipt changes escape reviewed inverse: '+relative
    return text

def contract_inputs():return [Path(__file__).resolve(),*(ROOT/n for n in HUNKS)]

def source_contract():
    result={}
    for relative in HUNKS:
        current=(ROOT/relative).read_text();original=reference_view(relative,current)
        # The only changed temporal control is CFG_ACCEPT's acceptance guard.
        # Its existing NBA targets, values and order are preserved as well.
        nba=lambda t:re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',t)
        assert nba(current)==nba(original),'configuration receipt NBA drift: '+relative
        result[relative]={'original_sha256':ORIGINAL_SHA256[relative],
            'maintained_sha256':hashlib.sha256(current.encode()).hexdigest(),
            'exact_whole_source_inverse':True,'NBA_targets_values_and_order_unchanged':True}
    return result
