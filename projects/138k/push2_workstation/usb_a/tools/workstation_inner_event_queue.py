"""Explicit M event buffering; preserve session ownership and historical source."""
from pathlib import Path
import hashlib,json
KEY='inner_event_queue_policy'
POLICY='task3_M_two_slot_inner_event_queue_v1'
SOURCE='rtl/audio/gw138k_event_workstation.sv'
DESTINATION='src/ae350/gw138k_event_workstation.sv'
QUEUE='rtl/control/workstation_event_queue.sv'
MANIFEST='rtl/control/workstation_inner_event_queue_v1.adaptation.json'
TOOL='tools/workstation_inner_event_queue.py'
MANIFEST_SHA256='7c1de06d8fb3b0a95e9f6cf92ff6b3dcc244f586b274114e7cf746e9df514253'
DEFAULT='parameter bit INNER_EVENT_QUEUE_ENABLE=0'
SELECTED='parameter bit INNER_EVENT_QUEUE_ENABLE=1'

def digest(raw):return hashlib.sha256(raw.encode()if isinstance(raw,str)else raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('inner event queue: '+message)

def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate selection')
        text=text.replace(SELECTED,DEFAULT,1)
    return text

def restore(relative,source):
    if str(relative)!=SOURCE:return source
    text=unselect(source.decode())
    if DEFAULT not in text:return source
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    require(digest(raw)==MANIFEST_SHA256,'manifest drift')
    data=json.loads(raw)
    require(data['policy']==POLICY and data['source']==SOURCE,'manifest policy/source changed')
    require(digest(text)==data['native_sha256'],'native source drift')
    for edit in reversed(data['edits']):
        require(text.count(edit['after'])==1,'inverse anchor drift')
        text=text.replace(edit['after'],edit['before'],1)
    require(digest(text)==data['parent_sha256'],'parent identity drift')
    return text.encode()

def configured(configuration):
    value=configuration.get(KEY)
    require(value in (None,POLICY),'unknown policy')
    if value:
        require(configuration.get('demo_role')=='M' and
                configuration.get('effects_dispatch_policy')=='task3_M_reserved_effects_configuration_v1',
                'requires explicit paired preboard M')
    return bool(value)

def select(stage,configuration):
    if not configured(configuration):return None
    path=Path(stage)/DESTINATION;text=path.read_text();restore(SOURCE,text.encode())
    require(text.count(DEFAULT)==1 and SELECTED not in text,'default missing')
    path.write_text(text.replace(DEFAULT,SELECTED,1))
    return evidence(stage,configuration)

def evidence(stage,configuration,*,source_text=None):
    if not configured(configuration):return None
    stage=Path(stage);text=(stage/DESTINATION).read_text() if source_text is None else source_text;restore(SOURCE,text.encode())
    require(text.count(SELECTED)==1 and DEFAULT not in text,'selected queue absent')
    root=Path(__file__).resolve().parents[1]
    require((stage/QUEUE).read_bytes()==(root/QUEUE).read_bytes(),'queue source drift')
    return dict(policy=POLICY,source_sha256=digest(text),queue_sha256=digest((stage/QUEUE).read_bytes()),
                manifest_sha256=MANIFEST_SHA256,capacity_events=2,event_bits=18,
                readiness_independent_of_consumer=True,lifecycle_purge=True,
                sample_schedule_unchanged=True,timing_exception_added=False,
                routed_timing_verified=False,hardware_tested=False)
