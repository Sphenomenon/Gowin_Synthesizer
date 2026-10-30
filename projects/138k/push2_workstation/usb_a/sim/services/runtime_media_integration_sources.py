"""Explicit source/fixture support for enabled runtime plus real TF regression.

No product source, prepared project, baseline or vendor file is modified here.
Compile and run from a fresh output directory with include paths in this order:
output, maintained usb_a root, then the explicit prepared Prj1 support project.
The output contains only data/include fixtures; it never shadows maintained RTL.
"""

from collections import defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import sys
import wave


PCM_FRAMES = 4096
WAV_BYTES = 44 + PCM_FRAMES * 4
FIXTURE_SOURCE = 'sim/services/tf_sd_media_integration_fixture.sv'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified_project(root, project, evidence=None):
    """Read-only verification of every prepared input plus synthesis VG.

    The returned identity describes immutable support bytes, not a synthesis
    result for the changed maintained RTL selected by build_sources().
    """
    root, project = Path(root).resolve(), Path(project).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tools.workstation_runtime_clock_audit import verify_synthesis_identity
    if evidence is None:
        evidence = project.parents[1] / 'runtime_synthesis_evidence/process.json'
    identity = verify_synthesis_identity(project, Path(evidence).resolve())
    identity['purpose'] = 'Immutable legacy/support closure only; maintained runtime/TF inputs are separately hashed'
    identity['verifier_source_sha256'] = sha(root / 'tools/workstation_runtime_clock_audit.py')
    return identity


def _unique_owners(sources):
    owners = defaultdict(set)
    for path in sources:
        # Raw vendor conditional variants in one file are one owner. Distinct
        # files defining the same module/package fail before simulator selection.
        text = re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(), flags=re.S)
        for kind, name in re.findall(r'\b(module|package)\s+(?:automatic\s+)?([A-Za-z_][\w$]*)', text):
            owners[(kind, name)].add(path)
    duplicates = {kind + ':' + name: sorted(map(str, paths))
                  for (kind, name), paths in owners.items() if len(paths) != 1}
    if duplicates:
        raise ValueError('Multiple HDL owners in runtime/TF closure: ' + json.dumps(duplicates, sort_keys=True))


def build_sources(root, project):
    """Return ordered real runtime/TF sources, official DCS model and SD fixture.

    The list follows the frozen run_runtime_controlled.py support policy while
    adding the actual TF service/storage path and its one-entry DDR buffer.
    It deliberately includes no integration TB, fake rate core or fake TF done.
    Call verified_project() before compilation and again after the run.
    """
    from tools.workstation_runtime_counter import selected_source
    root, project = Path(root).resolve(), Path(project).resolve()
    simlib = Path(os.environ.get('GOWIN_GW5A_SIMLIB',
        '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v')).resolve()
    sources = sorted((project / 'legacy/rtl/audio').glob('*.sv'),
                     key=lambda p: (not p.name.endswith('_pkg.sv'), str(p)))
    # These original composition roots are not instantiated by the native
    # runtime. Keeping them would diagnose obsolete, unused module interfaces
    # against the selected native replacement owners before elaboration.
    sources = [p for p in sources if p.name not in (
        'audio_capture_fifo.sv', 'audio_workstation.sv', 'audio_visual_extensions.sv')]
    sources += [project / name for name in (
        'legacy/rtl/input/midi_stream_decoder.sv', 'src/ae350/gw138k_three_event_arbiter.sv',
        'rtl/music/music_async_fifo.sv', 'rtl/audio/serial_spatial_reverb.sv',
        'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv')]
    for folder in ('rtl/audio/scope_vec', 'rtl/control', 'rtl/audio/delay_ddr'):
        sources += [p for p in sorted((project / folder).glob('*.sv')) if not (
            folder == 'rtl/audio/delay_ddr' and p.name in (
                'workstation_runtime_delay_effect_ddr.sv', 'workstation_runtime_delay_ddr_dma.sv'))]
    sources += [root / ('rtl/audio/' + name) for name in (
        'gw138k_event_workstation.sv', 'workstation_audio_render_service.sv', 'workstation_frame_delivery.sv',
        'workstation_runtime_div147.sv',
        'workstation_rate_pitch_expression.sv', 'workstation_runtime_oscillator_engine.sv',
        'workstation_runtime_scope_vec.sv', 'workstation_runtime_render_engines.sv',
        'workstation_runtime_chorus_effect.sv', 'workstation_runtime_spatial_reverb.sv',
        'workstation_runtime_stereo_effects.sv', 'delay_ddr/workstation_runtime_delay_effect_ddr.sv',
        'delay_ddr/workstation_runtime_delay_ddr_dma.sv', 'workstation_audio_clock_monitor.sv',
        'workstation_sample_rate_switch.sv', 'workstation_audio_clock_domain.sv',
        'workstation_pcm_frame_bridge.sv', 'workstation_i2s_serializer.sv',
        'workstation_final_pcm_router.sv', 'workstation_pcm_frame_fanout.sv')]
    sources += [root / 'rtl/workstation/workstation_runtime_audio.sv', simlib]
    sources += [project / ('src/migration/' + name) for name in (
        'gw138k_apb_cdc.sv', 'gw138k_stream_cdc.sv')]
    sources += [selected_source(project)]
    sources += [project / 'legacy/rtl/input/uart_rx.sv']
    sources += [root / name for name in (
        'rtl/services/workstation_audio_clock_service.sv', 'rtl/services/workstation_controlled_services.sv',
        'rtl/audio/gw138k_usb_lifecycle_merge.sv', 'rtl/audio/workstation_pcm_observation_bridge.sv',
        'rtl/audio/workstation_observation_consumers.sv', 'rtl/audio/audio_capture_fifo.sv',
        'rtl/input/score_led_player.sv', 'rtl/workstation/workstation_runtime_controlled.sv',
        'rtl/tf_audio/workstation_tf_runtime_service.sv', 'rtl/tf_audio/workstation_tf_frame_bridge.sv',
        'rtl/tf_audio/workstation_tf_runtime_byte_fifo.sv', 'rtl/tf_audio/workstation_tf_runtime_dma.sv',
        'rtl/tf_audio/storage/tf_audio_ddr_path.v', 'rtl/tf_audio/storage/tf_audio_ddr_dma.v',
        'rtl/tf_audio/storage/tf_async_byte_fifo.v', 'rtl/tf_audio/storage/tf_audio_decoder_ip.v',
        'rtl/tf_audio/storage/tf_wav_chunk_parser.v', 'rtl/tf_audio/storage/tf_wav_pcm_decoder.v',
        'rtl/display_data/tf_audio_ddr_command_buffer.sv', FIXTURE_SOURCE)]
    missing = [str(p) for p in sources if not p.is_file()]
    if missing:
        raise ValueError('Explicit runtime/TF input missing: ' + ', '.join(missing))
    # Runtime support already supplies music_async_fifo. Require exact identity
    # with the maintained TF dependency rather than silently picking an owner.
    if sha(project / 'rtl/music/music_async_fifo.sv') != sha(root / 'rtl/music/music_async_fifo.sv'):
        raise ValueError('Prepared runtime and maintained TF music_async_fifo bytes differ')
    if not re.search(r'\bmodule\s+DCS\b', simlib.read_text()):
        raise ValueError('Official simulation library has no DCS primitive')
    if len(sources) != len(set(sources)):
        raise ValueError('Duplicate source path in runtime/TF closure')
    _unique_owners(sources)
    return sources


def _copy_exact(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(source.read_bytes())
    if sha(source) != sha(destination):
        raise ValueError('Fixture copy identity differs: ' + str(source))


def prepare_fixtures(root, project, output):
    """Populate fresh output data/includes and actual WAV byte fixtures.

    Returns every created file for the caller's input-hash seal. Existing files
    are never overwritten; no prepared/cache files are changed or symlinked.
    Data copied from Prj1 belongs to the separately verified support closure.
    """
    root, project, output = map(lambda p: Path(p).resolve(), (root, project, output))
    output.mkdir(parents=True, exist_ok=True)
    created = []
    support = []
    for folder in ('sim/data', 'sim/matlab/output', 'rtl/audio/scope_vec/data'):
        support += sorted((project / folder).rglob('*.mem'))
    support += [project / 'rtl/audio/spatial_room_preset.svh']
    for source in support:
        target = output / source.relative_to(project)
        _copy_exact(source, target)
        created.append(target)
    for source, relative in (
        (root / 'rtl/audio/runtime_spatial_room_preset.svh', 'rtl/audio/runtime_spatial_room_preset.svh'),
        (root / 'rtl/ddr_address_map.vh', 'src/memory/ddr_address_map.vh')):
        target = output / relative
        _copy_exact(source, target)
        created.append(target)
    files = []
    for track, rate in enumerate((48000, 44100, 32000, 48000)):
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(b''.join(struct.pack('<hh', 1000 + track * 100 + index,
                                                -2000 - track * 100 - index)
                                     for index in range(PCM_FRAMES)))
        payload = bytearray(stream.getvalue())
        if len(payload) != WAV_BYTES:
            raise ValueError('Generated WAV fixture length changed')
        if track == 3:
            payload[20] = 3  # Unsupported IEEE-float format; never fake PCM.
        wav_path, hex_path = output / f'file{track}.wav', output / f'file{track}.hex'
        with wav_path.open('xb') as target:
            target.write(payload)
        with hex_path.open('x') as target:
            target.write(''.join(f'{value:02x}\n' for value in payload))
        created += [wav_path, hex_path]
        files.append(dict(track=track, sample_rate_hz=rate, format_code=3 if track == 3 else 1,
                          frames=PCM_FRAMES, wav_bytes=WAV_BYTES, wav_sha256=sha(wav_path),
                          hex_sha256=sha(hex_path)))
    manifest = output / 'media_fixture_manifest.json'
    with manifest.open('x') as target:
        json.dump(dict(schema=1, boundary='SD/FAT byte endpoint only; actual DDR/WAV/transport remain RTL',
                       left='1000 + track*100 + frame', right='-2000 - track*100 - frame',
                       fixture_source=FIXTURE_SOURCE, fixture_source_sha256=sha(root / FIXTURE_SOURCE),
                       files=files), target, indent=2)
        target.write('\n')
    return created + [manifest]


def input_key(root, project, output, path):
    """Canonical hash key independent of cache/output directory spelling."""
    root, project, output, path = map(lambda p: Path(p).resolve(), (root, project, output, path))
    for prefix, base in (('fixture/', output), ('prepared/', project), ('maintained/', root)):
        if path.is_relative_to(base):
            return prefix + str(path.relative_to(base))
    return 'external/' + path.name
