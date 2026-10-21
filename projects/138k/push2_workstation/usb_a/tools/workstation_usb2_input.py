"""Explicit existing-owner inputs for the native USB2 input component."""

from pathlib import Path
import hashlib

from tools.workstation_baselines import load_baseline


NATIVE_INPUT_SOURCES = (
    'rtl/workstation/workstation_usb2_input.sv',
    'rtl/workstation/workstation_usb2_service_adapter.sv',
    'rtl/push2_usb_a_control.sv', 'rtl/audio/push2_controls.sv',
    'rtl/push2/push2_lights.sv', 'rtl/push2/push2_led_tx.sv',
    'rtl/push2/push2_playlist_hold.sv', 'rtl/push2/push2_song_menu.sv',
    'rtl/push2/push2_score_guide.sv', 'rtl/push2/push2_song_screen.sv',
    'rtl/display_data/push2_surface_pixels.sv',
)
LOCKED_INPUT_SOURCES = (
    'src/migration/gw138k_stream_cdc.sv', 'src/usb_host/gw138k_usb_event_fifo.v',
    'src/push2/push2_midi_rx.sv', 'src/video/video_font_5x7.v',
)


def input_bundle(root):
    root = Path(root).resolve()
    baseline = load_baseline(root, 'resource_rework_route0')
    inputs = (*NATIVE_INPUT_SOURCES, 'tools/workstation_usb2_input.py',
              'tools/workstation_baselines.py', 'baselines/index.json',
              str(baseline.manifest.relative_to(root)))
    identities = {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest() for relative in inputs}
    support = {}
    records = {}
    for relative in LOCKED_INPUT_SOURCES:
        destination = 'support/workstation/' + relative
        payload = baseline.read_bytes(relative)
        support[destination] = payload
        records[destination] = dict(target=relative, **baseline.descriptor['files'][relative])
    return dict(native_paths=NATIVE_INPUT_SOURCES, input_sha256=identities, payloads=support,
                provenance=dict(policy='explicit_current_input_owner_and_four_locked_support_sources',
                                baseline=baseline.evidence(), locked_sources=records))
