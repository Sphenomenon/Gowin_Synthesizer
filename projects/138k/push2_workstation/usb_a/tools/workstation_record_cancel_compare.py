"""Same-cycle W CANCEL comparator, exact inverse after ARM capture."""
from pathlib import Path
import hashlib,json
SOURCE='rtl/workstation/workstation_task3_w_bus_endpoint.sv'
MANIFEST='rtl/workstation/workstation_record_cancel_compare_v1.adaptation.json'
TOOL='tools/workstation_record_cancel_compare.py'
POLICY='task3_W_record_cancel_padding_and_active_key_byte_compare_v1'
PARENT_SHA256='cfabbd51941804aad088fb56ba099e7835038984fb77eb96d89fd3a77fb6250e'
NATIVE_SHA256='aabe49f5f797681f99b57f00145c4c5df28d654454f5c582b8f3588a102bc7e1'
MANIFEST_SHA256='4e21867c36b6fb0aca87f937d247c7a78e01d4ac9c480b24f6747efc0278db64'

def normalize(payload):
    from tools.workstation_phone_ack_compare import normalize as ack_parent
    payload=ack_parent(payload)
    digest=lambda b:hashlib.sha256(b).hexdigest()
    if digest(payload)==PARENT_SHA256:return payload
    # Older exact source identities remain the older comparator's concern.
    if b'record_cancel_zero_bytes' not in payload:return payload
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    if digest(raw)!=MANIFEST_SHA256:raise ValueError('record CANCEL manifest drift')
    d=json.loads(raw)
    if digest(payload)!=NATIVE_SHA256:raise ValueError('record CANCEL source drift')
    text=payload.decode()
    for e in reversed(d['edits']):
        if text.count(e['after'])!=1:raise ValueError('record CANCEL inverse anchor drift')
        text=text.replace(e['after'],e['before'],1)
    if digest(text.encode())!=PARENT_SHA256:raise ValueError('record CANCEL parent drift')
    return text.encode()
