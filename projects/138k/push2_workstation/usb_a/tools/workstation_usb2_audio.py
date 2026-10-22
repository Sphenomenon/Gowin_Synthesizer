"""Native USB2 to the existing resource-candidate session, parameters and DSP."""

from pathlib import Path
import hashlib

from tools.workstation_baselines import load_baseline
from tools.workstation_usb2_input import input_bundle
from tools import workstation_resource_timing as timing


NATIVE_AUDIO_SOURCES = (
    'rtl/workstation/workstation_usb2_audio.sv',
    'rtl/workstation/gw138k_usb_controlled_audio.sv',
    'rtl/workstation/gw138k_controlled_adapter.sv',
    'rtl/audio/gw138k_event_workstation.sv', 'rtl/audio/workstation_frame_delivery.sv',
    'rtl/control/workstation_session.sv', 'rtl/control/workstation_parameters.sv',
    'rtl/audio/stereo_effects.sv', 'rtl/audio/serial_spatial_reverb.sv',
    'rtl/audio/scope_vec/scope_vec_engine.sv', 'rtl/audio/scope_vec/scope_control_player.sv',
    'rtl/audio/scope_vec/scope_tf_control.sv', 'rtl/music/music_async_fifo.sv',
    'rtl/audio/audio_capture_fifo.sv', 'rtl/input/score_led_player.sv',
    'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv',
    'rtl/resource_timing/delay_ddr_dma.sv',
)
LOCKED_AUDIO_SOURCES = (
    'legacy/rtl/audio/audio_math_pkg.sv', 'legacy/rtl/audio/sine_interp.sv',
    'legacy/rtl/audio/midi_step_rom.sv', 'legacy/rtl/audio/partial_step_generator_variable.sv',
    'legacy/rtl/audio/mode_timbre_rom.sv', 'legacy/rtl/audio/unified_oscillator_engine.sv',
    'legacy/rtl/audio/pitch_expression.sv', 'legacy/rtl/audio/spectrum_fft256.sv',
    'legacy/rtl/audio/audio_visual_extensions.sv', 'legacy/rtl/input/uart_rx.sv',
    'legacy/rtl/input/midi_stream_decoder.sv', 'src/ae350/gw138k_three_event_arbiter.sv',
    'src/ae350/gw138k_controlled_services.sv', 'src/migration/gw138k_apb_cdc.sv',
    'src/migration/gw138k_counter_cdc.sv', 'src/usb_a/gw138k_usb_lifecycle_merge.sv',
    'src/audio/pt8211_tx.v', 'src/audio/pt8211_observer.v',
    'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv',
)
LOCKED_AUDIO_DATA = (
    'sim/data/audio_chain/pitch_bend_q20.mem', 'sim/data/audio_chain/fft_hann.mem',
    'sim/data/audio_chain/fft_tw_re.mem', 'sim/data/audio_chain/fft_tw_im.mem',
    'sim/matlab/output/stage3_sine2048x24.mem',
    'sim/matlab/output/stage13_note_voice/stage13_midi_step.mem',
    'sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem',
    'sim/matlab/output/stage13_note_voice/stage13_ratio_q18.mem',
    'sim/matlab/output/stage15_unified_modes/stage15_mode_gain_q15.mem',
)
NATIVE_AUDIO_DATA = (
    'rtl/ddr_address_map.vh', 'rtl/audio/spatial_room_preset.svh',
    'rtl/audio/scope_vec/data/paths.mem', 'rtl/audio/scope_vec/data/note_steps.mem',
    'rtl/audio/scope_vec/data/rotation.mem', 'rtl/audio/scope_vec/data/scene_controls.mem',
    'rtl/audio/scope_vec/data/manifest.json', 'rtl/audio/scope_vec/data/scene.json',
)
TRANSFORMS = {
    'legacy/rtl/audio/unified_oscillator_engine.sv': timing.voice_count,
    'src/ae350/gw138k_controlled_services.sv': timing.services,
    'src/migration/gw138k_apb_cdc.sv': timing.apb,
    'src/usb_a/gw138k_usb_lifecycle_merge.sv': timing.lifecycle,
}


def audio_bundle(root):
    root = Path(root).resolve()
    bundle = input_bundle(root)
    baseline = load_baseline(root, 'resource_rework_route0')
    bundle['native_paths'] += NATIVE_AUDIO_SOURCES
    inputs = (*NATIVE_AUDIO_SOURCES, *NATIVE_AUDIO_DATA, 'tools/workstation_usb2_audio.py',
              'tools/workstation_resource_timing.py', 'tools/cnn_ddr_pipeline_patch.py')
    bundle['input_sha256'].update({relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
                                   for relative in inputs})
    records = {}
    for relative in (*LOCKED_AUDIO_SOURCES, *LOCKED_AUDIO_DATA):
        payload = baseline.read_bytes(relative)
        transformed = TRANSFORMS[relative](payload.decode()).encode() if relative in TRANSFORMS else payload
        destination = 'support/audio/' + relative if relative in LOCKED_AUDIO_SOURCES else relative
        bundle['payloads'][destination] = transformed
        records[destination] = dict(target=relative, before_sha256=hashlib.sha256(payload).hexdigest(),
                                    sha256=hashlib.sha256(transformed).hexdigest(),
                                    transform=TRANSFORMS[relative].__name__ if relative in TRANSFORMS else None,
                                    baseline_source=baseline.descriptor['files'][relative])
    for relative in NATIVE_AUDIO_DATA:
        bundle['payloads'][relative] = (root / relative).read_bytes()
    bundle['provenance']['policy'] = 'native_audio_with_selected_locked_resource_dependencies'
    bundle['provenance']['audio_sources'] = records
    bundle['provenance']['transform_exit_plan'] = (
        'Reuse only the existing checked resource timing transforms until their implementations move to versioned native sources; '
        'do not add a second session, parameter, frame-delivery or playback implementation.')
    return bundle
