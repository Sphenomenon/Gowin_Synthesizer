"""Explicit preboard delay watchdog retiming; preserve the original inverse."""
from pathlib import Path
import hashlib,json

KEY='delay_watchdog_policy'
POLICY='task3_delay_watchdog_lagged_counter_same_fault_edge_v1'
SOURCE='rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv'
MANIFEST='rtl/audio/delay_ddr/workstation_delay_watchdog_retime_v1.adaptation.json'
TOOL='tools/workstation_delay_watchdog_retime.py'
MANIFEST_SHA256='6c5333b442e860036d4b7d8d9ade66195367d8b5043cffb60b84cc55f68da7c6'
DEFAULT='parameter bit PIPELINED_WATCHDOG_ENABLE=0'
SELECTED='parameter bit PIPELINED_WATCHDOG_ENABLE=1'

def digest(raw):return hashlib.sha256(raw.encode()if isinstance(raw,str)else raw).hexdigest()

def require(ok,message):
    if not ok:raise ValueError('delay watchdog retime: '+message)

def unselect(text):
    if SELECTED in text:
        require(text.count(SELECTED)==1 and DEFAULT not in text,'duplicate selection')
        text=text.replace(SELECTED,DEFAULT,1)
    return text

def restore(text):
    from tools.workstation_w_watchdog_width import restore as restore_width
    text=restore_width(text)
    text=unselect(text)
    if DEFAULT not in text:return text
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
        require(configuration.get('demo_role')in ('M','W') and
                configuration.get('effects_dispatch_policy')in (
                    'task3_M_reserved_effects_configuration_v1',
                    'task3_W_reserved_effects_configuration_v1'),
                'requires explicit paired preboard effects composition')
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
    require(text.count(SELECTED)==1 and DEFAULT not in text,'selected retiming absent')
    return dict(policy=POLICY,source_sha256=digest(text),manifest_sha256=MANIFEST_SHA256,
                counter_lag_memory_clocks=1,fault_edge_unchanged=True,
                stream_and_native_schedule_unchanged=True,
                timing_exception_added=False,routed_timing_verified=False,hardware_tested=False)
