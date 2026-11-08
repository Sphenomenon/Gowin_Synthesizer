"""Select M's local empty-slot refill; preserve historical TF source identity.

The RTL owns the implementation. Retire the default-selection adapter when
the maintained parent composition passes NO_SAME_EDGE_REFILL explicitly.
"""
from pathlib import Path
import hashlib,json

KEY='tf_refill_policy'
POLICY='task3_M_TF_empty_slot_refill_v1'
SOURCE='rtl/tf_audio/workstation_tf_frame_bridge_v2.sv'
TOOL='tools/workstation_tf_empty_slot_refill.py'
MANIFEST='rtl/tf_audio/workstation_tf_empty_slot_refill_v1.adaptation.json'
MANIFEST_SHA256='9878690822182fade0533aa492317be018175acb10d491c724d96b8bcc128fcd'
DEFAULT='parameter bit NO_SAME_EDGE_REFILL=0'
SELECTED='parameter bit NO_SAME_EDGE_REFILL=1'

def digest(raw):return hashlib.sha256(raw.encode()if isinstance(raw,str)else raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('TF empty-slot refill: '+message)

def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate selection')
        text=text.replace(SELECTED,DEFAULT,1)
    return text

def restore(text):
    if 'NO_SAME_EDGE_REFILL'not in text:return text
    text=unselect(text)
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'manifest drift');data=json.loads(raw)
    require(data['source']==SOURCE and data['policy']==POLICY,'manifest policy drift')
    require(digest(text)==data['native_sha256'],'native source drift')
    for before,after in reversed(data['edits']):
        require(text.count(after)==1,'inverse anchor drift')
        text=text.replace(after,before,1)
    require(digest(text)==data['parent_sha256'],'parent source drift')
    return text

def configured(configuration):
    value=configuration.get(KEY)
    require(value in(None,POLICY),'unknown policy')
    if value:require(configuration.get('demo_role')=='M'and
        configuration.get('tf_compute_reset_policy')=='task3_M_TF_compute_functional_local_release_v1',
        'requires complete M local TF compute release')
    return bool(value)

def select(stage,configuration):
    if not configured(configuration):return None
    path=Path(stage)/SOURCE;text=path.read_text();restore(text)
    require(text.count(DEFAULT)==1 and SELECTED not in text,'default absent')
    path.write_text(text.replace(DEFAULT,SELECTED,1))
    return evidence(stage,configuration)

def evidence(stage,configuration):
    if not configured(configuration):return None
    text=(Path(stage)/SOURCE).read_text();restore(text)
    require(text.count(SELECTED)==1,'selected option absent')
    return dict(policy=POLICY,source_sha256=digest(text),manifest_sha256=MANIFEST_SHA256,
        same_edge_refill=False,consumer_ready_drives_payload_CE=False,
        cancellation_guard_unchanged=True,extra_state=0,sample_schedule_changed=False,
        routed_timing_verified=False,hardware_tested=False)
