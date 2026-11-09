"""Select the proven private response lifetime only for preboard M."""
from pathlib import Path
import hashlib
import json

KEY = 'display_reader_storage_policy'
POLICY = 'task3_M_display_reader_held_response_reuse_v1'
SOURCE = 'rtl/display_data/display_data_reader.v'
MANIFEST = 'rtl/display_data/workstation_reader_response_reuse_v1.adaptation.json'
MANIFEST_SHA256 = '74898efe45003f79a7dcb2c35168eeeb488be521e46c48c6324827d19d158150'
TOOL = 'tools/workstation_reader_response_reuse.py'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('display reader response reuse: ' + message)


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
        require(configuration.get('demo_role') == 'M' and
                configuration.get('display_metadata_minor') == 1,
                'requires explicit paired M minor1 display')
    return bool(value)


def adapt(text):
    data = manifest()
    require(digest(text) == data['parent_sha256'], 'parent source drift')
    for edit in data['edits']:
        require(text.count(edit['before']) == 1, 'forward anchor drift')
        text = text.replace(edit['before'], edit['after'], 1)
    require(digest(text) == data['selected_sha256'], 'selected identity drift')
    return text


def restore(text):
    from tools.workstation_reader_validated_metadata import restore as restore_validated
    text = restore_validated(text)
    data = manifest()
    require(digest(text) == data['selected_sha256'], 'selected source drift')
    for edit in reversed(data['edits']):
        require(text.count(edit['after']) == 1, 'inverse anchor drift')
        text = text.replace(edit['after'], edit['before'], 1)
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
                removed_private_payload_bits=256, extra_cycles=0,
                request_response_schedule_unchanged=True,
                cancellation_and_seqlock_unchanged=True,
                routed_timing_verified=False, hardware_tested=False)
