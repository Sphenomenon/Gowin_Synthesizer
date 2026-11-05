"""Opt-in96-bit phone RPC guard; exact inverse to the sealed M v7 source."""
from pathlib import Path
import hashlib

POLICY='task3_m_phone_full96_identity_group8_v1'
ENDPOINT='rtl/workstation/workstation_task3_m_bus_endpoint.sv'
BOARD='rtl/workstation/workstation_task3_m_paired_board.svh'
REFERENCE_ENDPOINT_SHA256='474b6d2288d968f791a2111e17e8cd4d88844f5f006789719f83e504c1b92acf'
REFERENCE_BOARD_SHA256='8948765c295b5c26663f9e958b781678bb7930fecdc7d4d5611f2b99955e51ab'
COMPARATOR_SHA256='db4506b721f3051b8655e0659f0ef1f78896bdcc072071036bbbdb2bef7ed993'
PARAMETER='    parameter integer PHONE_IDENTITY_COMPARE_GROUP_BITS=96,\n'
BINDING='    defparam u_task3_m_endpoint.PHONE_IDENTITY_COMPARE_GROUP_BITS=8;\n'
BEGIN='    // TASK3 phone identity comparison begin.'
END='    // TASK3 phone identity comparison end.\n'
REFERENCE='    wire phone_matches=rx_payload_i[177:82]==common;\n'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text,str) else text).hexdigest()


def require(ok,message):
    if not ok:raise ValueError('M phone identity comparison: '+message)


def comparator_block(text):
    require(text.count(BEGIN)==text.count(END)==1,'comparison boundaries changed')
    return text[text.index(BEGIN):text.index(END)+len(END)]


def restore_endpoint(text):
    block=comparator_block(text)
    require(digest(block)==COMPARATOR_SHA256,'reviewed complete96-bit comparator changed')
    require(text.count(PARAMETER)==1,'direct96 default changed')
    restored=text.replace(PARAMETER,'',1).replace(block,REFERENCE,1)
    require(digest(restored)==REFERENCE_ENDPOINT_SHA256,'unrelated endpoint behavior changed')
    return restored


def restore_board(text):
    require(text.count(BINDING)==1,'phone group8 board binding changed')
    restored=text.replace(BINDING,'',1)
    require(digest(restored)==REFERENCE_BOARD_SHA256,'unrelated board composition changed')
    return restored


def selection(stage,configuration,selected_top,*,sync_selected):
    policy=configuration.get('m_phone_identity_compare_policy')
    require(policy in (None,POLICY),'unknown phone identity policy')
    if policy is None:
        require(BINDING.strip() not in selected_top,'unselected phone group8 binding')
        return None
    from tools.workstation_task3_identity_compare import POLICY as PAIR_POLICY
    require(sync_selected and configuration.get('m_identity_compare_policy')==PAIR_POLICY,
            'phone grouping requires the explicit paired sync/group8 composition')
    require(selected_top.count(BINDING.strip())==1,'actual phone group8 endpoint binding changed')
    stage=Path(stage)
    endpoint=(stage/ENDPOINT).read_text();board=(stage/BOARD).read_text()
    if configuration.get('m_phone_lease_source_policy') is not None:
        from tools.workstation_task3_m_phone_lease_source import configured,restore
        require(configured(configuration),'unselected source-clock lease')
        board=restore(board)
    restore_endpoint(endpoint);restore_board(board)
    return dict(policy=policy,compared_identity_bits=96,group_bits=8,groups=12,
        extra_cycles=0,new_state_bits=0,same_cycle_revocation=True,
        fields=['local_boot[31:0]','session[31:0]','generation[31:0]'],
        endpoint_source_sha256=digest(endpoint),board_source_sha256=digest(board),
        reference_endpoint_sha256=REFERENCE_ENDPOINT_SHA256,
        reference_board_sha256=REFERENCE_BOARD_SHA256,
        exact_other_endpoint_and_board_bytes_preserved=True,
        mapped_equivalence_verified=False,routed_timing_verified=False,hardware_tested=False)
