"""Exact M-only selection of the private combined sample/event admission."""
from pathlib import Path
import hashlib
import json

KEY = 'event_admission_policy'
POLICY = 'task3_M_combined_sample_event_admission_v1'
MANIFEST = 'rtl/audio/workstation_event_admission_v1.adaptation.json'
MANIFEST_SHA256 = 'a94829640e1500010b0ff9353a1f0da78a95bd87dd479aef0ac16a2c8e56b576'
TOOL = 'tools/workstation_event_admission.py'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('combined event admission: ' + message)


def manifest():
    raw = (Path(__file__).resolve().parents[1] / MANIFEST).read_bytes()
    require(digest(raw) == MANIFEST_SHA256, 'manifest drift')
    data = json.loads(raw)
    require(data['policy'] == POLICY, 'policy drift')
    return data


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'M', 'requires explicit paired M')
    return bool(value)


def parent_source(root, source):
    text = (Path(root) / source).read_text()
    if source == 'rtl/audio/gw138k_event_workstation.sv':
        from tools import workstation_inner_event_queue as queue
        require(text.count(queue.DEFAULT) == 1, 'default inner queue drift')
        text = text.replace(queue.DEFAULT, queue.SELECTED, 1)
    require(digest(text) == manifest()['sources'][source]['parent_sha256'], 'composed parent drift')
    return text


def adapt(source, text):
    data = manifest()['sources'][source]
    require(digest(text) == data['parent_sha256'], 'parent source drift: ' + source)
    for edit in data['edits']:
        require(text.count(edit['before']) == 1, 'forward anchor drift')
        text = text.replace(edit['before'], edit['after'], 1)
    require(digest(text) == data['selected_sha256'], 'selected identity drift')
    return text


def restore(source, text):
    data = manifest()['sources'][source]
    require(digest(text) == data['selected_sha256'], 'selected source drift: ' + source)
    for edit in reversed(data['edits']):
        require(text.count(edit['after']) == 1, 'inverse anchor drift')
        text = text.replace(edit['after'], edit['before'], 1)
    require(digest(text) == data['parent_sha256'], 'parent identity drift')
    return text


def select(stage, configuration):
    if not configured(configuration):
        return None
    for source in manifest()['sources']:
        path = Path(stage) / manifest()['source_destinations'][source]
        path.write_text(adapt(source, path.read_text()))
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    sources = {}
    for source in manifest()['sources']:
        text = (Path(stage) / manifest()['source_destinations'][source]).read_text()
        parent = restore(source, text)
        sources[source] = dict(parent_sha256=digest(parent), selected_sha256=digest(text))
    return dict(policy=POLICY, sources=sources, manifest_sha256=MANIFEST_SHA256,
                added_state_bits=0, added_cycles=0, real_broadcasts_unchanged=True,
                sample_and_parameter_capture_edges_unchanged=True,
                routed_timing_verified=False, hardware_tested=False)
