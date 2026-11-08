"""Exact inverse for the native boot-only arithmetic schedule.

Maintained RTL is the build input. Reconstruction only lets the unchanged
CRC/cache and original GPL provenance verifiers check their historical bytes.
"""
from pathlib import Path
import hashlib,json
SOURCE='rtl/tf_audio/storage/workstation_tf_file_reader.sv'
MANIFEST='rtl/tf_audio/storage/workstation_tf_boot_geometry_v1.adaptation.json'
MANIFEST_SHA256='767d31b9b3cb10839678ddddb28d2ec7b9b00c3faac2fefc5600baaab749f11d'
POLICY='native_TF_boot_geometry_eight_stage_v1'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def restore(root,raw):
    payload=(Path(root)/MANIFEST).read_bytes()
    if digest(payload)!=MANIFEST_SHA256:raise ValueError('TF boot geometry manifest drift')
    d=json.loads(payload)
    if d['schema']!=1 or d['policy']!=POLICY or d['source']!=SOURCE or not d['reconstruction_used_only_for_verification']:
        raise ValueError('TF boot geometry contract drift')
    if digest(raw)!=d['native_sha256']:raise ValueError('TF boot geometry source drift')
    text=raw.decode()
    for e in reversed(d['edits']):
        if text.count(e['after'])!=1:raise ValueError('TF boot geometry reverse anchor drift')
        text=text.replace(e['after'],e['before'],1)
    prior=text.encode()
    if digest(prior)!=d['parent_sha256']:raise ValueError('TF boot geometry parent drift')
    for e in d['edits']:
        if text.count(e['before'])!=1:raise ValueError('TF boot geometry forward anchor drift')
        text=text.replace(e['before'],e['after'],1)
    if text.encode()!=raw:raise ValueError('TF boot geometry round trip drift')
    return prior,dict(policy=POLICY,source=SOURCE,parent_sha256=d['parent_sha256'],
        native_sha256=d['native_sha256'],manifest_sha256=MANIFEST_SHA256,
        exact_forward_reverse=True,boot_stages=8,transport_reservation_held=True,
        reconstruction_used_only_for_verification=True,hardware_tested=False)
