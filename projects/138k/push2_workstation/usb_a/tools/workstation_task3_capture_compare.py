"""Explicit full32 unsigned capture ordering, with an exact v20 inverse.

The staged default adapter is temporary. Retire it when a versioned composition
can bind this parameter directly; never change frozen providers or descriptors.
"""
from pathlib import Path
import hashlib

POLICY='task3_m_capture_unsigned32_group8_v1'
KEY='m_capture_compare_policy'
PROFILE='custom138k-workstation-task3-m-paired-checkpoint-v21'
SOURCE='rtl/workstation/workstation_task3_phone_batch_m.sv'
TOOL='tools/workstation_task3_capture_compare.py'
PARENT_SHA256='f5d823e777b203655fdd88e0b182df078a887732f343884eaa76b7703740ae2c'
NATIVE_SHA256='1f346864a46c085cbfb9f01332f441680797d18df67487749c7d894c1d37ab47'
SELECTED_SHA256='7cdd4e0092ec52149759d13744d08ff045867e784c8d376e0270a7063d753c47'
BLOCK_SHA256='463bedbb5ee63a5f2100283d1fd458d8a26b470594eacda55499ebbaa1e0341b'
PARAMETER='    parameter integer CAPTURE_COMPARE_GROUP_BITS=32\n'
SELECTED=PARAMETER.replace('=32','=8')
BEGIN='    // TASK3 capture ordering comparison begin.'
END='    // TASK3 capture ordering comparison end.\n'

def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text,str) else text).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('M capture ordering: '+message)

def native(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and PARAMETER not in text,'selected parameter changed')
        text=text.replace(SELECTED,PARAMETER,1)
    require(digest(text)==NATIVE_SHA256,'complete native batch source changed')
    return text

def restore(text):
    text=native(text)
    require(text.count(BEGIN)==text.count(END)==1,'comparison boundaries changed')
    block=text[text.index(BEGIN):text.index(END)+len(END)]
    require(digest(block)==BLOCK_SHA256,'unsigned32 comparison changed')
    old='    parameter integer TIMEOUT_CYCLES=50000,\n'+PARAMETER
    require(text.count(old)==1,'default parameter boundary changed')
    restored=text.replace(old,'    parameter integer TIMEOUT_CYCLES=50000\n',1).replace(block,'',1)
    anchor='FIRST_CAPTURE_ID:if(command_response_data_i==0 || capture_not_newer)'
    require(restored.count(anchor)==1,'comparison consumer changed')
    restored=restored.replace(anchor,'FIRST_CAPTURE_ID:if(command_response_data_i==0 || command_response_data_i<=last_capture_id)',1)
    require(digest(restored)==PARENT_SHA256,'unrelated batch behavior changed')
    return restored

def configured(configuration):
    policy=configuration.get(KEY)
    require(policy in (None,POLICY),'unknown policy')
    if policy is not None:
        require(configuration.get('demo_role')=='M' and
                configuration.get('phone_batch_policy')=='full_key_atomic_owner_snapshot_command_v1' and
                configuration.get('m_demand_identity_compare_policy')=='task3_m_demand_full96_identity_group8_v1',
                'requires explicit M full batch/demand composition')
    return policy is not None

def evidence(stage,configuration):
    path=Path(stage)/SOURCE
    if not configured(configuration):
        if path.is_file():require(SELECTED not in path.read_text(),'unselected grouping')
        return None
    text=path.read_text();restore(text)
    require(text.count(SELECTED)==1 and PARAMETER not in text,'group8 not selected')
    return dict(policy=POLICY,compared_bits=32,group_bits=8,groups=4,
        relation='unsigned command_response_data_i <= last_capture_id',
        source_sha256=digest(text),native_source_sha256=NATIVE_SHA256,
        reference_source_sha256=PARENT_SHA256,extra_cycles=0,new_state_bits=0,
        exact_other_batch_bytes_preserved=True,mapped_equivalence_verified=False,
        routed_timing_verified=False,hardware_tested=False)

def select(stage,configuration):
    if configured(configuration):
        path=Path(stage)/SOURCE;text=path.read_text();restore(text)
        require(text.count(PARAMETER)==1 and SELECTED not in text,'default selection changed')
        path.write_text(text.replace(PARAMETER,SELECTED,1))
    return evidence(stage,configuration)
