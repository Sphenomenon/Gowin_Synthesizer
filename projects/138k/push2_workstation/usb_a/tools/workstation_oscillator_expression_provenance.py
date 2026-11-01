"""Identity-bound expression prefix adaptation over unchanged oscillator ancestry."""
import hashlib
import json
from pathlib import Path

if __package__:
    from .workstation_oscillator_release_provenance import normalize_source, PARENT_SHA256 as RELEASE_PARENT_SHA256
    from .workstation_dispatch_slot_provenance import source_evidence
else:
    from workstation_oscillator_release_provenance import normalize_source, PARENT_SHA256 as RELEASE_PARENT_SHA256
    from workstation_dispatch_slot_provenance import source_evidence

SOURCE = 'rtl/audio/workstation_runtime_oscillator_engine.sv'
PROVENANCE = 'rtl/audio/workstation_runtime_oscillator_engine.provenance.json'
ADAPTATION = 'rtl/audio/workstation_runtime_oscillator_engine.expression_selection.json'
POLICY = 'native_expression_balanced_prefix_v1'
PROVENANCE_SHA256 = '92d3657f9e16f576181f6894b174fae956ba5ee98b9622e3b485c5c141a1f3c9'
ADAPTATION_SHA256 = '58742728c967dc752fa3279dfb9cc13e74b94c6c1e865e7921cd25f26a814674'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def restore_native(source, provenance, adaptation):
    """Reverse only the checked local selection change to the exact old native."""
    if sha(provenance) != PROVENANCE_SHA256:
        raise ValueError('Original oscillator provenance bytes changed')
    if sha(adaptation) != ADAPTATION_SHA256:
        raise ValueError('Oscillator expression adaptation bytes changed')
    meta, bridge = json.loads(provenance), json.loads(adaptation)
    source = normalize_source(source)
    if (bridge['policy'] != POLICY or bridge['source'] != SOURCE or
            bridge['original_provenance'] != PROVENANCE or
            bridge['original_provenance_sha256'] != sha(provenance) or
            bridge['parent_source_sha256'] != meta['native_sha256'] or
            bridge['parent_source_sha256'] != meta['registered_runtime_arithmetic']['source_sha256'] or
            bridge['current_source_sha256'] != sha(source) or
            len(bridge['exact_changes']) != 1 or bridge['added_clock_latency'] != 0):
        raise ValueError('Oscillator expression source identity changed')
    current = source.decode()
    for edit in reversed(bridge['exact_changes']):
        if edit['count'] != 1 or not edit['after'] or current.count(edit['after']) != 1:
            raise ValueError('Oscillator expression reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
    restored = current
    if sha(restored.encode()) != meta['native_sha256']:
        raise ValueError('Oscillator expression parent identity changed')
    for edit in bridge['exact_changes']:
        if not edit['before'] or current.count(edit['before']) != edit['count']:
            raise ValueError('Oscillator expression forward anchor drift')
        current = current.replace(edit['before'], edit['after'])
    if current.encode() != source:
        raise ValueError('Oscillator expression round trip changed bytes')
    return restored.encode()


def verify(source, provenance, adaptation):
    current = restore_native(source, provenance, adaptation).decode()
    meta = json.loads(provenance)
    for edit in reversed(meta['forward_edits']):
        if not edit['after'] or current.count(edit['after']) != edit['count']:
            raise ValueError('Original oscillator reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
    if sha(current.encode()) != meta['prepared_sha256']:
        raise ValueError('Oscillator exact prepared identity changed')
    return dict(policy=POLICY, source=SOURCE, current_source_sha256=sha(source),
                dispatch_slot_source=(None if sha(source) == RELEASE_PARENT_SHA256 else source_evidence(SOURCE, source)),
                original_native_sha256=meta['native_sha256'],
                original_provenance_sha256=sha(provenance), adaptation_sha256=sha(adaptation),
                exact_prepared_sha256=sha(current.encode()), original_provenance_unchanged=True,
                arithmetic_provenance_unchanged=True, added_clock_latency=0,
                physical_timing_verified=False, hardware_acceptance_inherited=False)


def source_bundle(root):
    root = Path(root)
    return verify((root / SOURCE).read_bytes(), (root / PROVENANCE).read_bytes(),
                  (root / ADAPTATION).read_bytes())
