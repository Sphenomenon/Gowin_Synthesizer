"""Explicit native demand guard selection, with exact v19 source inverse.

Only the parameter is selected in staging. Retire that adapter after a versioned
provider can bind it without changing frozen provider/source identities.
"""
from pathlib import Path
import hashlib

POLICY='task3_m_demand_full96_identity_group8_v1'
KEY='m_demand_identity_compare_policy'
PROFILE='custom138k-workstation-task3-m-paired-checkpoint-v20'
ENDPOINT='rtl/workstation/workstation_task3_m_bus_endpoint.sv'
TOOL='tools/workstation_task3_demand_identity_compare.py'
PARENT_SHA256='cd60fb213960963cfd15343660796006ae5f70782ddc681e2f3cc30a4f2ab77d'
NATIVE_SHA256='3d3dd4ac360db2ec01b848ee9f45c04cb24fe8e73242590e309f3ba808759553'
SELECTED_SHA256='a8acf38a88900352bff99e1fb934039779cf3c24ea7ac105d166f9cb1d32405d'
COMPARATOR_SHA256='0f5c453bd3701590d34dc29b180895209d11276989a44a874be53aec30fc4126'
PARAMETER='    parameter integer DEMAND_IDENTITY_COMPARE_GROUP_BITS=96,\n'
SELECTED=PARAMETER.replace('=96','=8')
BEGIN='    // TASK3 demand identity comparison begin.'
END='    // TASK3 demand identity comparison end.\n'
REFERENCE='    wire demand_matches=rx_payload_i[95:0]==common;\n'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text,str) else text).hexdigest()


def require(ok,message):
    if not ok:raise ValueError('M demand identity comparison: '+message)


def comparator_block(text):
    require(text.count(BEGIN)==text.count(END)==1,'comparison boundaries changed')
    return text[text.index(BEGIN):text.index(END)+len(END)]


def native(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and PARAMETER not in text,'selected parameter changed')
        text=text.replace(SELECTED,PARAMETER,1)
    require(digest(text)==NATIVE_SHA256,'complete native endpoint changed')
    return text


def restore_endpoint(text):
    text=native(text)
    block=comparator_block(text)
    require(digest(block)==COMPARATOR_SHA256,'complete96-bit comparison changed')
    require(text.count(PARAMETER)==1,'direct96 default changed')
    restored=text.replace(PARAMETER,'',1).replace(block,REFERENCE,1)
    require(digest(restored)==PARENT_SHA256,'unrelated endpoint behavior changed')
    return restored


def configured(configuration):
    value=configuration.get(KEY)
    require(value in (None,POLICY),'unknown demand identity policy')
    if value is not None:
        require(configuration.get('demo_role')=='M' and
                configuration.get('phone_batch_policy')=='full_key_atomic_owner_snapshot_command_v1' and
                configuration.get('m_phone_identity_compare_policy')=='task3_m_phone_full96_identity_group8_v1',
                'requires explicit paired M batch/full96 composition')
    return value is not None


def evidence(stage,configuration):
    selected=configured(configuration)
    path=Path(stage)/ENDPOINT
    if not selected:
        if path.is_file():require(SELECTED not in path.read_text(),'unselected grouped demand guard')
        return None
    text=path.read_text()
    restore_endpoint(text)
    require(text.count(SELECTED)==1 and PARAMETER not in text,'group8 option not selected')
    return dict(policy=POLICY,compared_identity_bits=96,group_bits=8,groups=12,
        fields=['local_boot[31:0]','session[31:0]','generation[31:0]'],
        endpoint_source_sha256=digest(text),native_endpoint_sha256=NATIVE_SHA256,
        reference_endpoint_sha256=PARENT_SHA256,extra_cycles=0,new_state_bits=0,
        same_cycle_revocation=True,exact_other_endpoint_bytes_preserved=True,
        mapped_equivalence_verified=False,routed_timing_verified=False,hardware_tested=False)


def select(stage,configuration):
    if configured(configuration):
        path=Path(stage)/ENDPOINT;text=path.read_text();restore_endpoint(text)
        require(text.count(PARAMETER)==1 and SELECTED not in text,'default selection changed')
        path.write_text(text.replace(PARAMETER,SELECTED,1))
    return evidence(stage,configuration)
