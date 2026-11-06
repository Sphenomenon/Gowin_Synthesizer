"""Checked experiment on the exact v21 LAST_CAPTURE_ID equality consumer.

The first-party combinational RTL is versioned separately. This small adapter
is for explicitly prepared experiments; it changes no production profile.
Retire the adapter after full mapped/owner/route comparison and an explicit
versioned composition integrates the instance, or retain only the failed
experiment evidence. Never mutate the parent stage or refresh its hashes.
"""
import hashlib

SOURCE='rtl/workstation/workstation_task3_phone_batch_m.sv'
COMPARATOR='rtl/workstation/workstation_task3_capture_identity32.sv'
POLICY='task3_m_LAST_CAPTURE_ID_full32_group8_experiment_v1'
PARENT_SHA256='7cdd4e0092ec52149759d13744d08ff045867e784c8d376e0270a7063d753c47'
ANCHOR='    wire snapshot_fields_good='
BEFORE='LAST_CAPTURE_ID:if(command_response_data_i!=capture_id || !snapshot_fields_good)'
AFTER='LAST_CAPTURE_ID:if(!capture_identity_matches || !snapshot_fields_good)'
BLOCK='''    // Explicit offline capture identity experiment; no protocol or state change.
    (* syn_keep=1 *) wire capture_identity_matches;
    workstation_task3_capture_identity32 capture_identity(
        .response_i(command_response_data_i),.capture_i(capture_id),
        .matches_o(capture_identity_matches));
'''

def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text,str) else text).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('M capture identity experiment: '+message)

def apply(text):
    require(digest(text)==PARENT_SHA256,'exact selected v21 parent required')
    require(text.count(ANCHOR)==text.count(BEFORE)==1 and 'capture_identity_matches' not in text,
            'consumer or insertion boundary changed')
    return text.replace(ANCHOR,BLOCK+ANCHOR,1).replace(BEFORE,AFTER,1)

def restore(text):
    require(text.count(BLOCK)==text.count(AFTER)==1 and BEFORE not in text,
            'complete selected instance and consumer required')
    parent=text.replace(BLOCK,'',1).replace(AFTER,BEFORE,1)
    require(digest(parent)==PARENT_SHA256,'unrelated batch behavior changed')
    require(apply(parent)==text,'selected bytes changed')
    return parent

def evidence(text):
    restore(text)
    return dict(policy=POLICY,parent_source_sha256=PARENT_SHA256,
        selected_source_sha256=digest(text),compared_bits=32,groups=4,group_bits=8,
        relation='command_response_data_i == capture_id',consumer='LAST_CAPTURE_ID',
        extra_cycles=0,new_state_bits=0,other_source_bytes_preserved=True,
        production_profile_selected=False,mapped_equivalence_verified=False,
        routed_timing_verified=False,hardware_tested=False)
