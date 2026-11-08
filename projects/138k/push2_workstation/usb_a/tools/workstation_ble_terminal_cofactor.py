"""Select the W terminal fault cofactor, retaining its exact historical inverse."""
from pathlib import Path
import hashlib,json

KEY='raw_terminal_policy'
POLICY='task3_W_raw_terminal_fault_final_selector_v1'
SOURCE='rtl/memory/workstation_ble_raw_ddr_store.sv'
MANIFEST='rtl/memory/workstation_ble_terminal_cofactor_v1.adaptation.json'
TOOL='tools/workstation_ble_terminal_cofactor.py'
MANIFEST_SHA256='769d1db0d3642f018b46069287781bbebfe7a14e9cdb442a6a53c81403e77c57'
DEFAULT='parameter bit TERMINAL_COFACTOR_ENABLE=0'
SELECTED='parameter bit TERMINAL_COFACTOR_ENABLE=1'

def digest(raw):return hashlib.sha256(raw.encode()if isinstance(raw,str)else raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('raw terminal cofactor: '+message)

def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate selection')
        text=text.replace(SELECTED,DEFAULT,1)
    return text

def restore(text):
    text=unselect(text)
    if DEFAULT not in text:return text
    # Completion publication is an older independently checked adaptation.
    # Normalize its parameter before checking this complete-source identity.
    from tools.workstation_ble_completion_publication import unselect as publication_native
    text=publication_native(text)
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
                configuration.get('raw_completion_policy')=='task3_W_raw_completion_publication_one_memory_edge_v1' and
                configuration.get('preboard_cdc_policy')=='task3_W_proven_release_and_CNN_drain_CDC_v1',
                'requires explicit paired preboard W with completion publication')
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
    require(text.count(SELECTED)==1 and DEFAULT not in text,'selected cofactor absent')
    return dict(policy=POLICY,source_sha256=digest(text),manifest_sha256=MANIFEST_SHA256,
                added_state_bits=0,completion_edge_unchanged=True,index_edge_unchanged=True,
                procedural_unknown_fallback=True,timing_exception_added=False,
                routed_timing_verified=False,hardware_tested=False)
