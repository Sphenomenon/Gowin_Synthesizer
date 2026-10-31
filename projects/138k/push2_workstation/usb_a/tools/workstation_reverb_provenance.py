"""Verify local Reverb scheduling against its unchanged prepared provenance."""
import hashlib
import json
from pathlib import Path

SOURCE = 'rtl/audio/workstation_runtime_spatial_reverb.sv'
PROVENANCE = 'rtl/audio/workstation_runtime_spatial_reverb.provenance.json'
ADAPTATION = 'rtl/audio/workstation_runtime_spatial_reverb.pipeline.json'
PROVENANCE_SHA256 = '3ca4cbf55bb0dea90f67f08388fee5fd2460532ed8a64cc7f64a9d3b8bf01a52'
ADAPTATION_SHA256 = 'fa5d015a145ba4b89ece7b8662eb3e2d7e7fc1c811131ec7a173fab19b415328'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def restore(source, provenance, adaptation, scratch=False):
    """Reverse only the recorded scheduling edits, without changing evidence."""
    if sha(provenance) != PROVENANCE_SHA256 or sha(adaptation) != ADAPTATION_SHA256:
        raise ValueError('Reverb original provenance or scheduling adaptation drifted')
    info, bridge = json.loads(provenance), json.loads(adaptation)
    steps = bridge['steps']
    if (bridge['policy'] != 'local_damping_pipeline_v1' or bridge['source'] != SOURCE or
            bridge['original_provenance'] != PROVENANCE or len(steps) != 2 or
            bridge['original_provenance_sha256'] != sha(provenance) or
            steps[0]['parent_source_sha256'] != info['native_sha256'] or
            steps[0]['current_source_sha256'] != steps[1]['parent_source_sha256']):
        raise ValueError('Reverb scheduling provenance chain changed')
    current = source.decode()
    for step in reversed(steps[1:] if scratch else steps):
        if sha(current.encode()) != step['current_source_sha256']:
            raise ValueError('Reverb scheduling source identity changed')
        original = current
        for edit in reversed(step['exact_changes']):
            if not edit['after'] or current.count(edit['after']) != edit['count']:
                raise ValueError('Reverb scheduling reverse anchor drift')
            current = current.replace(edit['after'], edit['before'])
        if sha(current.encode()) != step['parent_source_sha256']:
            raise ValueError('Reverb scheduling parent identity changed')
        forward = current
        for edit in step['exact_changes']:
            if not edit['before'] or forward.count(edit['before']) != edit['count']:
                raise ValueError('Reverb scheduling forward anchor drift')
            forward = forward.replace(edit['before'], edit['after'])
        if forward != original:
            raise ValueError('Reverb scheduling round trip changed bytes')
    return current.encode()


def verify(source, provenance, adaptation):
    current = restore(source, provenance, adaptation).decode()
    info = json.loads(provenance)
    for edit in reversed(info['forward_edits']):
        if not edit['after'] or current.count(edit['after']) != edit['count']:
            raise ValueError('Original Reverb reverse anchor drift')
        current = current.replace(edit['after'], edit['before'])
    if sha(current.encode()) != info['prepared_sha256']:
        raise ValueError('Reverb exact prepared source identity changed')
    return current, dict(source=SOURCE, current_source_sha256=sha(source),
        original_native_sha256=info['native_sha256'], original_provenance_sha256=sha(provenance),
        adaptation_sha256=sha(adaptation), exact_prepared_sha256=sha(current.encode()),
        original_provenance_unchanged=True, added_frame_latency=0,
        physical_timing_verified=False, hardware_acceptance_inherited=False)


def source_bundle(root):
    root = Path(root)
    return verify((root / SOURCE).read_bytes(), (root / PROVENANCE).read_bytes(),
                  (root / ADAPTATION).read_bytes())[1]
