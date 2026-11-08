"""Same-edge full phone ACK identity comparison and exact parent inverse."""
from pathlib import Path
import hashlib,json
SOURCE='rtl/workstation/workstation_task3_w_bus_endpoint.sv'
MANIFEST='rtl/workstation/workstation_phone_ack_compare_v1.adaptation.json'
TOOL='tools/workstation_phone_ack_compare.py'
POLICY='task3_W_phone_ACK_full96_byte_compare_v1'
PARENT_SHA256='aabe49f5f797681f99b57f00145c4c5df28d654454f5c582b8f3588a102bc7e1'
NATIVE_SHA256='a3604a9470f1298c8f29eb2d128ef33d835e954d34ac9b44f347545c1cd24a67'
MANIFEST_SHA256='f71713f1482cbce48bb0f3dbad5da502d3dc4b21011b5a98f9fad794e97ac535'

def normalize(payload):
    digest=lambda b:hashlib.sha256(b).hexdigest()
    if b'phone_ack_equal_bytes' not in payload:return payload
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    if digest(raw)!=MANIFEST_SHA256:raise ValueError('phone ACK manifest drift')
    d=json.loads(raw)
    if digest(payload)!=NATIVE_SHA256:raise ValueError('phone ACK source drift')
    text=payload.decode()
    for e in reversed(d['edits']):
        if text.count(e['after'])!=1:raise ValueError('phone ACK inverse anchor drift')
        text=text.replace(e['after'],e['before'],1)
    if digest(text.encode())!=PARENT_SHA256:raise ValueError('phone ACK parent drift')
    return text.encode()
