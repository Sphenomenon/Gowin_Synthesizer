"""Select constant-gain plot arithmetic only for explicit preboard M."""
from pathlib import Path
import hashlib
import json

KEY = 'display_plot_coordinate_policy'
POLICY = 'task3_M_constant_gain_plot_coordinates_v1'
SOURCE = 'rtl/display_data/output_audio_analysis.v'
MANIFEST = 'rtl/display_data/workstation_plot_coordinates_v1.adaptation.json'
MANIFEST_SHA256 = '1ad470410244a8b946326b229aa696848cafdcdf1a2468e4ab69431b1dc29184'
TOOL = 'tools/workstation_plot_coordinates.py'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('display plot coordinates: ' + message)


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
                extra_cycles=0, added_state_bits=0,
                image_write_schedule_unchanged=True, four_state_fallback=True,
                routed_timing_verified=False, hardware_tested=False)
