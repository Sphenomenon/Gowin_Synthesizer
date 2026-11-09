"""Exact role-specific selection of the private combined sample/event admission."""
from pathlib import Path
import hashlib
import json

KEY = 'event_admission_policy'
POLICY = 'task3_M_combined_sample_event_admission_v1'
MANIFEST = 'rtl/audio/workstation_event_admission_v1.adaptation.json'
MANIFEST_SHA256 = 'a94829640e1500010b0ff9353a1f0da78a95bd87dd479aef0ac16a2c8e56b576'
TOOL = 'tools/workstation_event_admission.py'
W_POLICY = 'task3_W_combined_sample_event_admission_v1'
W_MANIFEST = 'rtl/audio/workstation_w_event_admission_v1.adaptation.json'
W_MANIFEST_SHA256 = 'a92a5f85fbcea76dad580e3f8a3b9b24d195dd23c6a5de3bba11defba548dc76'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('combined event admission: ' + message)


def manifest(role="M"):
    require(role in ("M", "W"), "unknown role")
    path, expected, policy = (W_MANIFEST,W_MANIFEST_SHA256,W_POLICY) if role=="W" else (MANIFEST,MANIFEST_SHA256,POLICY)
    raw = (Path(__file__).resolve().parents[1] / path).read_bytes()
    require(digest(raw) == expected, 'manifest drift')
    data = json.loads(raw)
    require(data['policy'] == policy, 'policy drift')
    return data


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY, W_POLICY), 'unknown policy')
    if value:
        role = 'W' if value == W_POLICY else 'M'
        require(configuration.get('demo_role') == role, 'requires matching explicit paired role')
        if role == 'W':
            require(configuration.get('inner_event_queue_policy') is None, 'W native queue must remain disabled')
    return bool(value)


def parent_source(root, source, role="M"):
    text = (Path(root) / source).read_text()
    if source == 'rtl/audio/gw138k_event_workstation.sv' and role == 'M':
        from tools import workstation_inner_event_queue as queue
        require(text.count(queue.DEFAULT) == 1, 'default inner queue drift')
        text = text.replace(queue.DEFAULT, queue.SELECTED, 1)
    require(digest(text) == manifest(role)['sources'][source]['parent_sha256'], 'composed parent drift')
    return text


def adapt(source, text, role="M"):
    data = manifest(role)['sources'][source]
    require(digest(text) == data['parent_sha256'], 'parent source drift: ' + source)
    for edit in data['edits']:
        require(text.count(edit['before']) == 1, 'forward anchor drift')
        text = text.replace(edit['before'], edit['after'], 1)
    require(digest(text) == data['selected_sha256'], 'selected identity drift')
    return text


def restore(source, text):
    if source == 'rtl/audio/gw138k_event_workstation.sv':
        from tools.workstation_cancel_fanout import restore as restore_fanout
        text = restore_fanout(text)
    data = manifest()['sources'][source]
    if digest(text) != data['selected_sha256']:
        data = manifest('W')['sources'][source]
    require(digest(text) == data['selected_sha256'], 'selected source drift: ' + source)
    for edit in reversed(data['edits']):
        require(text.count(edit['after']) == 1, 'inverse anchor drift')
        text = text.replace(edit['after'], edit['before'], 1)
    require(digest(text) == data['parent_sha256'], 'parent identity drift')
    return text


def select(stage, configuration):
    if not configured(configuration):
        return None
    role=configuration['demo_role']
    for source in manifest(role)['sources']:
        path = Path(stage) / manifest(role)['source_destinations'][source]
        path.write_text(adapt(source, path.read_text(),role))
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    role=configuration['demo_role']
    sources = {}
    for source in manifest(role)['sources']:
        text = (Path(stage) / manifest(role)['source_destinations'][source]).read_text()
        parent = restore(source, text)
        require(digest(parent)==manifest(role)['sources'][source]['parent_sha256'], 'configured role parent differs')
        sources[source] = dict(parent_sha256=digest(parent), selected_sha256=digest(text))
    return dict(policy=configuration[KEY], sources=sources, manifest_sha256=W_MANIFEST_SHA256 if role=="W" else MANIFEST_SHA256,
                added_state_bits=0, added_cycles=0, real_broadcasts_unchanged=True,
                sample_and_parameter_capture_edges_unchanged=True,
                routed_timing_verified=False, hardware_tested=False)
