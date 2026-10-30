"""Exact Chorus verification chain and explicit native source identity gate."""
from pathlib import Path
import hashlib
import json

STRICT_POLICY = 'locked_native_v1'
NARROW_POLICY = 'narrow_exact_rate_delay_v1'
SOURCE = 'rtl/audio/workstation_runtime_chorus_effect.sv'
PROVENANCE = 'rtl/audio/workstation_runtime_chorus_effect.provenance.json'
ADAPTATION = 'rtl/audio/workstation_runtime_chorus_effect.rate_delay_narrowing.json'
PROVENANCE_SHA256 = '41babc5ece0ec3ca5cae68e2f7d5c5069e93d1acb63224771d7483c138f32b48'
ADAPTATION_SHA256 = '0f2811bdfa33f04111cc036cace4b986eecf25306cdb13fd297b56d0bcfbadf4'


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def restore_native(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Return exact previous native bytes without altering historical evidence."""
    if policy not in (STRICT_POLICY, NARROW_POLICY):
        raise ValueError('Unknown Chorus provenance policy')
    if sha(provenance) != PROVENANCE_SHA256:
        raise ValueError('Original Chorus provenance bytes changed')
    original = json.loads(provenance)
    current = source.decode()
    if policy == NARROW_POLICY:
        if adaptation is None or sha(adaptation) != ADAPTATION_SHA256:
            raise ValueError('Chorus narrowing adaptation changed or missing')
        bridge = json.loads(adaptation)
        if (bridge['policy'] != policy or bridge['source'] != SOURCE or
                bridge['original_provenance'] != PROVENANCE or
                bridge['original_provenance_sha256'] != sha(provenance) or
                bridge['parent_source_sha256'] != original['native_sha256'] or
                bridge['current_source_sha256'] != sha(source) or
                len(bridge['exact_changes']) != 1):
            raise ValueError('Chorus narrowing source identity changed')
        edit = bridge['exact_changes'][0]
        if (edit['count'] != 1 or not edit['after'] or current.count(edit['after']) != 1):
            raise ValueError('Chorus narrowing reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
        if not edit['before'] or current.count(edit['before']) != 1 or current.replace(edit['before'], edit['after']) != source.decode():
            raise ValueError('Chorus narrowing round trip changed bytes')
    elif adaptation is not None:
        raise ValueError('Chorus adaptation needs explicit policy')
    if sha(current.encode()) != original['native_sha256']:
        raise ValueError('Native Chorus provenance checksum changed')
    return current


def verify(source, provenance, policy=STRICT_POLICY, adaptation=None):
    """Reverse the explicit adaptation and unchanged original prepared chain."""
    current = restore_native(source, provenance, policy, adaptation)
    info = json.loads(provenance)
    for edit in reversed(info['forward_edits']):
        if not edit['after'] or current.count(edit['after']) != edit['count']:
            raise ValueError('Original Chorus reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
    if sha(current.encode()) != info['prepared_sha256']:
        raise ValueError('Chorus exact prepared source identity changed')
    return current, dict(policy=policy, source=SOURCE, current_source_sha256=sha(source),
        original_native_sha256=info['native_sha256'], original_provenance_sha256=sha(provenance),
        adaptation_sha256=sha(adaptation) if adaptation is not None else None,
        exact_prepared_sha256=sha(current.encode()), original_provenance_unchanged=True,
        added_clock_latency=0, physical_timing_verified=False, hardware_acceptance_inherited=False)


def source_bundle(root):
    """Bind only explicit native runtime production profiles to these bytes."""
    root = Path(root)
    _, evidence = verify((root / SOURCE).read_bytes(), (root / PROVENANCE).read_bytes(),
                         NARROW_POLICY, (root / ADAPTATION).read_bytes())
    return evidence
