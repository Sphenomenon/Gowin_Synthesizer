"""Strict local NoteOff prefix inverse over the immutable expression parent."""
import hashlib
import json
from pathlib import Path

SOURCE = 'rtl/audio/workstation_runtime_oscillator_engine.sv'
ADAPTATION = 'rtl/audio/workstation_runtime_oscillator_engine.release_selection.json'
POLICY = 'native_release_balanced_prefix_v1'
PARENT_SHA256 = '99cdad64b9ed09773f5fb93c43e2303fd58c780a32b6bb6b051386511bec74e9'
ADAPTATION_SHA256 = '5791de08ba19b2a4b0069fb72e92645d6ff428689090bb0884b6d7d110580c16'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def restore_parent(source, adaptation):
    if sha(adaptation) != ADAPTATION_SHA256:
        raise ValueError('Oscillator release adaptation bytes changed')
    bridge = json.loads(adaptation)
    if (bridge['schema'] != 1 or bridge['policy'] != POLICY or bridge['source'] != SOURCE or
            bridge['parent_source_sha256'] != PARENT_SHA256 or
            bridge['current_source_sha256'] != sha(source) or
            bridge['added_clock_latency'] != 0 or len(bridge['exact_changes']) != 2):
        raise ValueError('Oscillator release source identity changed')
    current = source.decode()
    for edit in reversed(bridge['exact_changes']):
        if edit['count'] != 1 or not edit['after'] or current.count(edit['after']) != 1:
            raise ValueError('Oscillator release reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
    parent = current.encode()
    if sha(parent) != PARENT_SHA256:
        raise ValueError('Oscillator release parent identity changed')
    for edit in bridge['exact_changes']:
        if not edit['before'] or current.count(edit['before']) != 1:
            raise ValueError('Oscillator release forward anchor drift')
        current = current.replace(edit['before'], edit['after'])
    if current.encode() != source:
        raise ValueError('Oscillator release round trip changed bytes')
    return parent


def normalize_source(source):
    # Old callers and immutable historical fixtures retain their exact input.
    # Every other source must reverse through the complete checked bridge.
    if sha(source) == PARENT_SHA256:
        return source
    return restore_parent(source, (Path(__file__).resolve().parents[1] / ADAPTATION).read_bytes())


def source_bundle(root):
    root = Path(root)
    source, adaptation = (root / SOURCE).read_bytes(), (root / ADAPTATION).read_bytes()
    parent = restore_parent(source, adaptation)
    return dict(policy=POLICY, source=SOURCE, current_source_sha256=sha(source),
                parent_source_sha256=sha(parent), adaptation_sha256=sha(adaptation),
                exact_inverse_and_roundtrip=True, all_clocked_source_bytes_unchanged=True,
                added_clock_latency=0, physical_timing_verified=False,
                hardware_acceptance_inherited=False)
