"""Source boundary for workstation builds based on the accepted full83 tree."""
import hashlib
from workstation_baselines import load_baseline


MUSIC = 'rtl/music/'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def music_files(project):
    return {path.relative_to(project).as_posix(): sha(path)
            for path in sorted((project / 'rtl/music').rglob('*')) if path.is_file()}


def verify_cnn_inputs(project, selected):
    """Reject missing, modified or unlisted CNN files in the tree being built."""
    actual = music_files(project)
    missing = sorted(selected.keys() - actual.keys())
    added = sorted(actual.keys() - selected.keys())
    changed = sorted(name for name in selected.keys() & actual.keys()
                     if selected[name] != actual[name])
    if missing or added or changed:
        raise ValueError('accepted CNN input mismatch: ' +
                         repr(dict(missing=missing, added=added, changed=changed)))


def accepted_cnn_inputs(project, inputs):
    """Select from the accepted manifest, never from the live source directory."""
    selected = {name: digest for name, digest in inputs.items() if name.startswith(MUSIC)}
    if not selected:
        raise ValueError('accepted input manifest has no CNN files')
    for name, digest in inputs.items():
        path = project / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError('accepted input tree drifted: ' + name)
    verify_cnn_inputs(project, selected)
    return selected


def cnn_source_audit(root, selected):
    """Record live differences without overlaying unaccepted CNN changes."""
    live = music_files(root)
    return dict(schema_version=1, policy='accepted_full83',
                selected_sha256=selected, live_sha256=live,
                changed=sorted(name for name in selected.keys() & live.keys()
                               if selected[name] != live[name]),
                added=sorted(live.keys() - selected.keys()),
                missing=sorted(selected.keys() - live.keys()),
                live_cnn_overlay=False)


TIMING85_BUILD = 'results/song_guide_full85_clk50_20261007_084539_884006_route1'
TIMING85_MANIFEST_SHA256 = 'c5aef03165e18b7f71119e6b563516feb00c88de86a156a2715f32a183ddef2c'
TIMING85_OVERLAYS = tuple(MUSIC + name + '.sv' for name in (
    'basic_pitch_viterbi', 'basic_pitch_cqt_engine', 'basic_pitch_cqt_frontend',
    'basic_pitch_workstation_link', 'basic_pitch_pcm_pipeline', 'basic_pitch_conv2d'))

ACCEPTED_DDR_INPUTS = {
    'rtl/display_data/gw138k_ddr_arbiter.sv': (
        'src/ae350/gw138k_ddr_arbiter.sv',
        '61b0353f72419f0a719f693e121b1aa9ff8b07ed0dbfbdd33ec39f72172ef178'),
    'rtl/display_data/hdmi_display.v': (
        'src/video/hdmi_display.v',
        '7421e472c9289b1cca0eefe1c428bc03d7f6ea1081e7f8f86a785d6d7ac42dcc'),
    'rtl/ddr_address_map.vh': (
        'src/memory/ddr_address_map.vh',
        '0ec949e54acecac04b71fceca2cf725d56d2691c850fbd83951fdc6441fc8ddb'),
    'rtl/audio/delay_ddr/delay_ddr_dma.sv': (
        'rtl/audio/delay_ddr/delay_ddr_dma.sv',
        'e39fc2672874fad520f1dfab8d945e23600499e7147f9057ed52fdd2561b7301'),
    'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv': (
        'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv',
        'e5764ef18a0c8a1918369121b1b27124eb9e5c0b6cfe4922a65cfd14d2d6eff6'),
}


def timing85_cnn_inputs(root, accepted):
    """Select six proven timing patches from a pinned snapshot, never live CNN."""
    snapshot = load_baseline(root, 'timing85')
    if snapshot.descriptor['origin']['input_manifest_sha256'] != TIMING85_MANIFEST_SHA256:
        raise ValueError('timing85 input manifest is missing or changed')
    selected = snapshot.music
    changed = {name for name in accepted.keys() | selected.keys()
               if accepted.get(name) != selected.get(name)}
    if changed != set(TIMING85_OVERLAYS):
        raise ValueError('timing85 CNN changes exceed the six fixed overlays: ' + repr(sorted(changed)))
    return selected
