"""Proof-only bridge to pre-panel composition; never produces build RTL."""
import hashlib
import json
from pathlib import Path

MANIFEST = 'rtl/workstation/workstation_usb_status_integration.json'
MANIFEST_SHA256 = '5191c5dc915ac594dcaa1c239928aab5b7fea84a2c3acf0058ebf1eaaa1c0657'


def restore_parent(source, relative):
    digest = lambda data: hashlib.sha256(data).hexdigest()
    payload = (Path(__file__).resolve().parents[1] / MANIFEST).read_bytes()
    if digest(payload) != MANIFEST_SHA256:
        raise ValueError('USB status provenance manifest changed')
    info = json.loads(payload)
    record = info['records'].get(relative)
    if record is None or digest(source) != record['current_sha256']:
        return source, None  # The unchanged downstream verifier rejects unknown bytes.
    text = source.decode('utf-8')
    for edit in reversed(record['edits']):
        if not edit['after'] or text.count(edit['after']) != 1:
            raise ValueError('USB status reverse anchor drift: ' + relative)
        text = text.replace(edit['after'], edit['before'])
    parent = text.encode('utf-8')
    if digest(parent) != record['parent_sha256']:
        raise ValueError('USB status parent identity changed: ' + relative)
    for edit in record['edits']:
        if not edit['before'] or text.count(edit['before']) != 1:
            raise ValueError('USB status forward anchor drift: ' + relative)
        text = text.replace(edit['before'], edit['after'])
    if text.encode('utf-8') != source:
        raise ValueError('USB status round trip changed: ' + relative)
    return parent, dict(policy=info['policy'], source=relative,
        current_source_sha256=digest(source), parent_source_sha256=digest(parent),
        manifest_sha256=digest(payload), exact_inverse_edits=len(record['edits']),
        exact_round_trip_verified=True, input_source_rewritten=False,
        hardware_acceptance_inherited=False)
