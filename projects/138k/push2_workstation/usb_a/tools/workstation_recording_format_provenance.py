"""Trace dual-rate recording sources through their unchanged reviewed parents.

These exact inverse edits are used only for provenance comparison. The compiler
always consumes the current maintained files. Historical firmware, capacity and
phone-batch review manifests remain immutable; neither source drift nor a missing
lineage record is permitted to fall back to another source tree.
"""
from pathlib import Path
import json

from tools.workstation_recording_capacity_provenance import (
    digest, original_identity as capacity_identity)

MANIFEST = 'firmware/ae350/recording_formats.lineage.json'
MANIFEST_SHA256 = '5d074a96c3f4d77a12a6e469a3389f9aea5f8c4d0f11a13ace306c2757d5da55'
TOOL = 'tools/workstation_recording_format_provenance.py'
NAMES = ('ble_business_owner.c', 'ble_business_owner.h', 'recording_service.c', 'recording_service.h')


def parent_source(root, name, payload):
    if name not in NAMES:
        return payload, None
    encoded = (Path(root) / MANIFEST).read_bytes()
    if digest(encoded) != MANIFEST_SHA256:
        raise ValueError('recording format lineage manifest drift')
    manifest = json.loads(encoded)
    if (manifest.get('schema') != 1 or
            manifest.get('policy') != 'task3_single_recording_dual_rate_backend_v1' or
            manifest.get('default_dual_rate_enabled') is not False or
            set(manifest.get('files', {})) != set(NAMES)):
        raise ValueError('recording format lineage policy drift')
    row = manifest['files'][name]
    if digest(payload) == row['parent_sha256']:
        return payload, None
    if digest(payload) != row['current_sha256'] or not row['exact_changes']:
        raise ValueError('recording format source drift: ' + name)
    parent = payload.decode()
    for edit in reversed(row['exact_changes']):
        if edit['count'] != 1 or not edit['before'] or not edit['after'] or parent.count(edit['after']) != 1:
            raise ValueError('recording format inverse anchor drift: ' + name)
        parent = parent.replace(edit['after'], edit['before'], 1)
    if digest(parent.encode()) != row['parent_sha256']:
        raise ValueError('recording format parent identity drift: ' + name)
    forward = parent
    for edit in row['exact_changes']:
        if forward.count(edit['before']) != 1:
            raise ValueError('recording format forward anchor drift: ' + name)
        forward = forward.replace(edit['before'], edit['after'], 1)
    if forward.encode() != payload:
        raise ValueError('recording format lineage roundtrip drift: ' + name)
    return parent.encode(), dict(policy=manifest['policy'], manifest=MANIFEST,
                                manifest_sha256=MANIFEST_SHA256,
                                parent_sha256=row['parent_sha256'],
                                current_source_sha256=row['current_sha256'],
                                exact_inverse_round_trip_verified=True,
                                actual_source_compiled=True)


def original_identity(root, name, payload):
    parent, evidence = parent_source(root, name, payload)
    original, inherited = capacity_identity(root, name, parent)
    if evidence is None:
        return original, inherited
    return original, dict(evidence, original_source_sha256=original,
                          inherited_capacity_lineage=inherited)
