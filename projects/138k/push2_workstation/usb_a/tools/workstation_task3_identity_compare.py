"""Exact opt-in M identity guard source binding; no state or wire changes."""
from pathlib import Path
import hashlib

POLICY='task3_m_full128_identity_group8_v1'
ENDPOINT='rtl/workstation/workstation_task3_m_bus_endpoint.sv'
BOARD='rtl/workstation/workstation_task3_m_paired_board.svh'
REFERENCE_ENDPOINT_SHA256='5d625039d428ab18d554a70ae9ef9ee9b241eba8421fdd301013baf8ad769908'
COMPARATOR_SHA256='85a9eaa467aed0720c3e026aafd3597c57c80011578970d12cc3a395073e9811'
PARAMETER='    parameter integer IDENTITY_COMPARE_GROUP_BITS=128,\n'
BINDING='defparam u_task3_m_endpoint.IDENTITY_COMPARE_GROUP_BITS=8;'
BEGIN='    // TASK3 identity comparison begin.'
END='    // TASK3 identity comparison end.\n'
REFERENCE='    wire new_identity=configured_identity!={local_boot_i,peer_boot_i,session_i,generation_i};\n'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('M identity comparison: '+message)


def comparator_block(text):
    require(text.count(BEGIN)==text.count(END)==1,'comparison boundaries changed')
    start=text.index(BEGIN);stop=text.index(END,start)+len(END)
    return text[start:stop]


def restore_endpoint(text):
    """All other endpoint bytes must equal the sealed terminal-pipeline source."""
    block=comparator_block(text)
    require(hashlib.sha256(block.encode()).hexdigest()==COMPARATOR_SHA256,
            'reviewed complete128-bit comparator changed')
    require(text.count(PARAMETER)==1,'direct128 default changed')
    result=text.replace(PARAMETER,'',1).replace(block,REFERENCE,1)
    require(hashlib.sha256(result.encode()).hexdigest()==REFERENCE_ENDPOINT_SHA256,
            'unrelated endpoint behavior changed')
    return result


def selection(stage,configuration,selected_top,*,sync_selected):
    policy=configuration.get('m_identity_compare_policy')
    require(policy in (None,POLICY),'unknown identity policy')
    if policy is None:
        require(BINDING not in selected_top,'unselected grouped identity binding')
        return None
    require(sync_selected and configuration.get('m_score_terminal_policy')==
            'task3_m_one_slot_terminal_validation_v1','grouping requires explicit sync/terminal policy')
    require(selected_top.count(BINDING)==1,'group8 actual endpoint binding changed')
    stage=Path(stage);text=(stage/ENDPOINT).read_text()
    if configuration.get('m_phone_identity_compare_policy') is not None:
        from tools.workstation_task3_phone_identity_compare import restore_endpoint as restore_phone
        text=restore_phone(text)
    restore_endpoint(text)
    return dict(policy=policy,compared_identity_bits=128,group_bits=8,groups=16,
        extra_cycles=0,new_state_bits=0,same_cycle_revocation=True,
        endpoint_source_sha256=sha(stage/ENDPOINT),board_source_sha256=sha(stage/BOARD),
        reference_endpoint_sha256=REFERENCE_ENDPOINT_SHA256,
        exact_other_endpoint_bytes_preserved=True,mapped_equivalence_verified=False,
        routed_timing_verified=False,hardware_tested=False)
