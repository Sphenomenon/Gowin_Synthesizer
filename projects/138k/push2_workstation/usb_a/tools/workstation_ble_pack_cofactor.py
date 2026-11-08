"""W same-edge pack/fetch fault selector with checked historical inverse."""
from pathlib import Path
import hashlib,json
KEY='raw_pack_policy'
POLICY='task3_W_raw_pack_fetch_final_fault_selector_v1'
SOURCE='rtl/memory/workstation_ble_raw_ddr_store.sv'
MANIFEST='rtl/memory/workstation_ble_pack_cofactor_v1.adaptation.json'
TOOL='tools/workstation_ble_pack_cofactor.py'
MANIFEST_SHA256='9f6adcf4158668baa88aae5442095556226e9b2b8ed71ceec8d17d5a610aac0a'
DEFAULT='parameter bit PACK_COFACTOR_ENABLE=0'
SELECTED='parameter bit PACK_COFACTOR_ENABLE=1'
def digest(raw):return hashlib.sha256(raw.encode()if isinstance(raw,str)else raw).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('raw pack cofactor: '+message)
def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate selection')
        text=text.replace(SELECTED,DEFAULT,1)
    return text
def restore(text):
    from tools.workstation_native_fault_cofactor import restore_raw
    text=restore_raw(text)
    text=unselect(text)
    if DEFAULT not in text:return text
    # Normalize the two older independent selections only for lineage checks.
    for stem in ('PIPELINED_COMPLETION_ENABLE','TERMINAL_COFACTOR_ENABLE','TUPLE_COFACTOR_ENABLE'):
        selected='parameter bit '+stem+'=1';default='parameter bit '+stem+'=0'
        require(text.count(selected)+text.count(default)==1,'older selection inventory changed')
        text=text.replace(selected,default,1)
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'manifest drift')
    data=json.loads(raw)
    require(data['policy']==POLICY and data['source']==SOURCE,'manifest policy/source changed')
    require(digest(text)==data['native_sha256'],'native source drift')
    for edit in reversed(data['edits']):
        require(text.count(edit['after'])==1,'inverse anchor drift')
        text=text.replace(edit['after'],edit['before'],1)
    require(digest(text)==data['parent_sha256'],'parent identity drift')
    return text
def configured(configuration):
    value=configuration.get(KEY)
    require(value in (None,POLICY),'unknown policy')
    if value:
        require(configuration.get('demo_role')=='W' and
            configuration.get('raw_terminal_tuple_policy')=='task3_W_raw_terminal_tuple_final_fault_selector_v1' and
            configuration.get('raw_terminal_policy')=='task3_W_raw_terminal_fault_final_selector_v1' and
            configuration.get('raw_completion_policy')=='task3_W_raw_completion_publication_one_memory_edge_v1',
            'requires explicit W pipelined tuple policy')
    return bool(value)
def select(stage,configuration):
    if not configured(configuration):return None
    path=Path(stage)/SOURCE;text=path.read_text();restore(text)
    require(text.count(DEFAULT)==1 and SELECTED not in text,'default missing')
    path.write_text(text.replace(DEFAULT,SELECTED,1))
    return evidence(stage,configuration)
def evidence(stage,configuration):
    if not configured(configuration):return None
    text=(Path(stage)/SOURCE).read_text();restore(text)
    require(text.count(SELECTED)==1 and DEFAULT not in text,'selected pack cofactor absent')
    return dict(policy=POLICY,source_sha256=digest(text),manifest_sha256=MANIFEST_SHA256,
        added_state_bits=0,pack_edge_unchanged=True,fetch_address_edge_unchanged=True,
        immediate_native_fault_preserved=True,
        procedural_unknown_fallback=True,timing_exception_added=False,
        routed_timing_verified=False,hardware_tested=False)
