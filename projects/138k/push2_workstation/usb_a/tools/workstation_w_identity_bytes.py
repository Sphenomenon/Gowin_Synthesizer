"""Exact inverse for two W combinational identity comparisons."""
from pathlib import Path
import hashlib
import json

MANIFEST='rtl/workstation/workstation_w_identity_bytes_v1.adaptation.json'
MANIFEST_SHA256='f301adda1eff95d1c146803bee5b8f9662c062b544f2dfdf0a96be425cabc6b6'


def normalize(path, text):
    raw=(Path(__file__).resolve().parents[1]/MANIFEST).read_bytes()
    sha=lambda b:hashlib.sha256(b).hexdigest()
    if sha(raw)!=MANIFEST_SHA256:
        raise ValueError('W identity byte manifest drift')
    entries=[row for row in json.loads(raw)['sources'] if row['source']==path]
    if not entries:return text
    row,=entries
    if sha(text.encode())==row['parent_sha256']:return text
    if 'key_equal_bytes' not in text:return text
    if sha(text.encode())!=row['native_sha256']:
        raise ValueError('W identity byte source drift: '+path)
    for edit in reversed(row['edits']):
        if text.count(edit['after'])!=1:
            raise ValueError('W identity byte inverse anchor drift: '+path)
        text=text.replace(edit['after'],edit['before'],1)
    if sha(text.encode())!=row['parent_sha256']:
        raise ValueError('W identity byte parent drift: '+path)
    return text
