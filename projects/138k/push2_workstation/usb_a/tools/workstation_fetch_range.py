"""Select same-edge parallel fetch bounds only for explicit preboard W."""
from pathlib import Path
import hashlib
import json

KEY = 'raw_fetch_range_policy'
POLICY = 'task3_W_parallel_byte_fetch_range_v1'
SOURCE = 'rtl/memory/workstation_ble_raw_ddr_store.sv'
MANIFEST = 'rtl/memory/workstation_fetch_range_v1.adaptation.json'
MANIFEST_SHA256 = '8f7f2058b54c3d6b4db483cc5fada5244c6bdeaa801584e037c61d6fce8ad5b0'
TOOL = 'tools/workstation_fetch_range.py'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('raw fetch range: ' + message)


def manifest():
    raw = (Path(__file__).resolve().parents[1] / MANIFEST).read_bytes()
    require(digest(raw) == MANIFEST_SHA256, 'manifest drift')
    data = json.loads(raw)
    require(data['policy'] == POLICY and data['source'] == SOURCE, 'contract drift')
    return data


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    if value:
        require(configuration.get('demo_role') == 'W' and
                configuration.get('raw_pack_policy') == 'task3_W_raw_pack_fetch_final_fault_selector_v1',
                'requires explicit paired W pack policy')
    return bool(value)


def parent_source(root):
    text = (Path(root) / SOURCE).read_text()
    for stem in ('PIPELINED_COMPLETION_ENABLE', 'TERMINAL_COFACTOR_ENABLE',
                 'TUPLE_COFACTOR_ENABLE', 'PACK_COFACTOR_ENABLE', 'NATIVE_FAULT_COFACTOR_ENABLE'):
        old, new = 'parameter bit '+stem+'=0', 'parameter bit '+stem+'=1'
        require(text.count(old) == 1, 'parent selection drift: '+stem)
        text = text.replace(old, new, 1)
    require(digest(text) == manifest()['parent_sha256'], 'composed parent drift')
    return text


def restore_if_selected(text):
    return restore(text) if 'wire [34:0] fetch_range_left=' in text else text


def adapt(text):
    data = manifest()
    require(digest(text) == data['parent_sha256'], 'parent source drift')
    for edit in data['edits']:
        require(text.count(edit['before']) == edit['count'], 'forward anchor drift')
        text = text.replace(edit['before'], edit['after'])
    require(digest(text) == data['selected_sha256'], 'selected identity drift')
    return text


def restore(text):
    data = manifest()
    require(digest(text) == data['selected_sha256'], 'selected source drift')
    for edit in reversed(data['edits']):
        require(text.count(edit['after']) == edit['count'], 'inverse anchor drift')
        text = text.replace(edit['after'], edit['before'])
    require(digest(text) == data['parent_sha256'], 'parent identity drift')
    return text


def select(stage, configuration):
    if not configured(configuration):
        return None
    path = Path(stage) / SOURCE
    path.write_text(adapt(path.read_text()))
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    text = (Path(stage) / SOURCE).read_text()
    parent = restore(text)
    return dict(policy=POLICY, source=SOURCE, parent_sha256=digest(parent),
                selected_sha256=digest(text), manifest_sha256=MANIFEST_SHA256,
                extra_cycles=0, added_state_bits=0,
                fetch_acceptance_edge_unchanged=True, four_state_fallback=True,
                routed_timing_verified=False, hardware_tested=False)
