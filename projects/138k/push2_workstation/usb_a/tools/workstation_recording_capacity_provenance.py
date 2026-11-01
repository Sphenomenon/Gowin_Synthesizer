"""Reverse only the reviewed single-object capacity extension for lineage.

Compilation always consumes the real current C/header bytes. The original
firmware manifest remains immutable; exact inverse/forward checks establish
its parent and do not update any historical source lock or accepted profile.
"""
from pathlib import Path
import hashlib
import json

MANIFEST='firmware/ae350/ble_business_owner.capacity_lineage.json'
MANIFEST_SHA256='6ad34f7c8443d66a1f3869b152dde4b0e6e1de1c5a3d4fd4bb22f7dcb487910d'
TOOL='tools/workstation_recording_capacity_provenance.py'


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def original_identity(root, name, payload):
    if name not in ('ble_business_owner.c','ble_business_owner.h'):
        return digest(payload), None
    manifest=(Path(root)/MANIFEST).read_bytes()
    if digest(manifest)!=MANIFEST_SHA256:
        raise ValueError('recording capacity lineage manifest drift')
    record=json.loads(manifest)
    if (record.get('schema')!=1 or record.get('policy')!='task3_single_recording_configurable_capacity_v1'
            or record.get('default_frames')!=16384 or set(record.get('files',{}))!={'ble_business_owner.c','ble_business_owner.h'}):
        raise ValueError('recording capacity lineage policy drift')
    row=record['files'][name]
    if digest(payload)==row['parent_sha256']:
        return digest(payload), None
    if digest(payload)!=row['current_sha256'] or not row['exact_changes']:
        raise ValueError('recording capacity source drift: '+name)
    current=payload.decode()
    for edit in reversed(row['exact_changes']):
        if edit['count']!=1 or not edit['before'] or not edit['after'] or current.count(edit['after'])!=1:
            raise ValueError('recording capacity inverse anchor drift: '+name)
        current=current.replace(edit['after'],edit['before'],1)
    if digest(current.encode())!=row['parent_sha256']:
        raise ValueError('recording capacity parent identity drift: '+name)
    for edit in row['exact_changes']:
        if current.count(edit['before'])!=1:
            raise ValueError('recording capacity forward anchor drift: '+name)
        current=current.replace(edit['before'],edit['after'],1)
    if current.encode()!=payload:
        raise ValueError('recording capacity lineage roundtrip drift: '+name)
    return row['parent_sha256'],dict(policy=record['policy'],manifest=MANIFEST,
        manifest_sha256=MANIFEST_SHA256,parent_sha256=row['parent_sha256'],
        current_source_sha256=row['current_sha256'],exact_inverse_round_trip_verified=True)
