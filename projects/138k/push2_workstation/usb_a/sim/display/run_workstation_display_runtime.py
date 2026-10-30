#!/usr/bin/env python3
"""Verify optional native HDMI composition, CDC and current-context publication."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(text):
    return re.findall(r'\w+|\S', re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    native_hdmi = ROOT / 'rtl/workstation/workstation_hdmi_display.sv'
    provenance_path = native_hdmi.with_suffix('.provenance.json')
    provider = ROOT / 'rtl/workstation/workstation_profile_hdmi.sv'
    package = ROOT / 'rtl/display_data_layout_pkg.svh'
    display = ROOT / 'rtl/display_data'
    pipeline = display / 'workstation_display_runtime.sv'
    runtime_tb = Path(__file__).with_name('tb_workstation_display_runtime.sv')
    elaboration_tb = Path(__file__).with_name('tb_workstation_hdmi_elaboration.sv')
    common = [package] + [display / name for name in (
        'display_data_writer.v', 'display_data_reader.v', 'display_data_analysis_source.sv',
        'workstation_display_runtime.sv', 'feedback_capture.v', 'output_audio_analysis.v')]
    common += [project / ('src/video/' + name) for name in (
        'output_audio_capture.v', 'audio_analysis_rom.v', 'feedback_wave_align.v')]
    common += [project / ('src/migration/' + name) for name in ('gw138k_stream_cdc.sv', 'gw138k_counter_cdc.sv')]
    runtime_sources = common + [runtime_tb]
    simlib = Path(os.environ.get('GOWIN_GW5A_SIMLIB', '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v'))
    excluded = {'hdmi_display.v', 'feedback_capture.v', 'output_audio_analysis.v', 'feedback_renderer.v',
                'output_audio_capture.v', 'audio_analysis_rom.v', 'feedback_wave_align.v'}
    hdmi_sources = common + [provider, display / 'workstation_ddr_scan_window.sv', display / 'feedback_renderer.v']
    hdmi_sources += [path for path in sorted((project / 'src/video').glob('*.v')) if path.name not in excluded]
    hdmi_sources += [project / name for name in (
        'src/platform/video_clock_1080p.v', 'src/memory/ddr3_bist.v', 'src/memory/ddr_frame_writer.v',
        'src/ae350/gw138k_view_select.sv', 'rtl/timing/basic_pitch_ddr_client_queues.sv',
        'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv', 'rtl/memory/workstation_sdp.sv')]
    hdmi_sources += sorted((project / 'vendor/sipeed_dvi').glob('*.v'))
    hdmi_sources += [simlib, elaboration_tb]
    a07_path = ROOT / 'reports/workstation_task_20261030/display_metadata_v11_native.json'
    profile_path = project.parents[1] / 'workstation_profile.json'
    inputs = list(dict.fromkeys(runtime_sources + hdmi_sources + [native_hdmi, provenance_path,
        ROOT / 'rtl/workstation/RUNTIME_DISPLAY.md', a07_path, Path(__file__).resolve(),
        project / 'src/memory/ddr_address_map.vh', profile_path, project.parents[1] / 'integration_inputs.json']))
    hashes = {str(path): digest(path) for path in inputs}
    source_identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
        identity='native-runtime-display-offline-v1-' + source_identity[:16], source_set_sha256=source_identity,
        input_sha256=hashes, configuration=dict(explicit_macro='WORKSTATION_RUNTIME_NATIVE', default_enabled=False,
            metadata_minor=1, frame_tuple_bits=204, source_hz=50000000, memory_hz=100000000,
            fixture_strobe_source_cycles=16), source_policy='Maintained optional display/HDMI composition with explicit prepared support and official GW5A elaboration primitives',
        prepared_reference_candidate=json.loads(profile_path.read_text())['candidate_identity'],
        validation_scope='Offline real waveform/2048 FFT/XY to DDR/cache, atomic CDC, current-context raster/summary admission and full HDMI elaboration',
        limits='Functional ordered DDR and accelerated PCM fixture; no live I2S/HDMI pixels, synthesis, P&R, physical CDC/timing/resource or board/deployment acceptance',
        ddr_video_reset_separated=False, bitstream_identity=None, commands={})

    def run(name, command, timeout=90, cwd=None):
        result['commands'][name] = list(map(str, command))
        with (output / (name + '.log')).open('w') as stream:
            subprocess.run(command, cwd=project if cwd is None else cwd,
                           stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        return (output / (name + '.log')).read_text()

    try:
        a07 = json.loads(a07_path.read_text())
        if not a07['passed']:
            raise ValueError('A07 prerequisite is not verified')
        for path, value in a07['input_sha256'].items():
            if path in hashes and hashes[path] != value:
                raise ValueError('Frozen A07 prerequisite changed: ' + path)
        result['a07_prerequisite_identity'] = a07['identity']
        info = json.loads(provenance_path.read_text())
        current = native_hdmi.read_text()
        if digest(native_hdmi) != info['native_sha256']:
            raise ValueError('Native HDMI provenance checksum changed')
        restored = current
        prior_runtime = None
        for edit in reversed(info['exact_changes']):
            if restored.count(edit['after']) != 1:
                raise ValueError('Reverse HDMI provenance anchor drift')
            restored = restored.replace(edit['after'], edit['before'])
            if hashlib.sha256(restored.encode()).hexdigest() == info['pre_runtime_native_sha256']:
                prior_runtime = restored
        if prior_runtime is None or hashlib.sha256(restored.encode()).hexdigest() != info['parent_sha256']:
            raise ValueError('Reverse HDMI provenance did not reproduce exact inputs')
        result['reverse_provenance_passed'] = True
        before = output / 'pre_runtime_hdmi.sv'
        before.write_text(prior_runtime)
        for name, source in [('before', before), ('after', native_hdmi)]:
            run('preprocess_' + name, ['iverilog', '-g2012', '-E', '-o', str(output / (name + '.pre.sv')), str(source)])
        before_tokens, after_tokens = [tokens((output / (name + '.pre.sv')).read_text()) for name in ('before', 'after')]
        if before_tokens != after_tokens or '`define WORKSTATION_RUNTIME_NATIVE' in provider.read_text():
            raise ValueError('Default HDMI selection/tokens changed')
        result['default_tokens_equal'] = True
        result['default_token_count'] = len(after_tokens)
        for runtime in (False, True):
            name = 'hdmi_native_elaboration' if runtime else 'hdmi_default_elaboration'
            run(name, ['iverilog', '-g2012', '-I' + str(ROOT), '-I' + str(project), '-s', 'tb_workstation_hdmi_elaboration',
                *(['-DWORKSTATION_RUNTIME_NATIVE'] if runtime else []), '-o', str(output / (name + '.vvp')),
                *map(str, hdmi_sources)], cwd=ROOT)
            # Icarus searches its working directory before -I paths. Running
            # in the frozen support tree would silently include its old HDMI
            # composition instead of the live source whose hash we record.
            elaborated = (output / (name + '.vvp')).read_text()
            scopes = re.findall(r'^\S+ \.scope module, "([^"]+)" "([^"]+)"[^\n]*\n(.*?)(?=^\S+ \.scope |\Z)',
                                elaborated, re.M | re.S)
            def parameters(label):
                matching = [body for scope, _, body in scopes if scope == label]
                if len(matching) != 1:
                    raise ValueError('Ambiguous elaborated scope: ' + label)
                return {key: int(bits, 2) for key, bits in re.findall(
                    r'\.param/l "(\w+)"[^\n]*\+C4<([01]+)>', matching[0])}
            renderer_parameters = parameters('u_renderer')
            expected_parameters = dict(ENABLE_ANALYSIS=0 if runtime else 1, RENDER_ANALYSIS=1,
                                       SHARED_EXPORT=0 if runtime else 1, SHARED_RENDER=1)
            if any(renderer_parameters.get(key) != value for key, value in expected_parameters.items()):
                raise ValueError('Wrong HDMI composition or renderer parameters elaborated')
            fft_owners = [scope for scope, kind, _ in scopes if kind == 'output_audio_analysis']
            if fft_owners != (['analysis'] if runtime else ['u_analysis']):
                raise ValueError('HDMI FFT owner missing or duplicated: ' + repr(fft_owners))
            if any(parameters(label).get('ENABLE_ANALYSIS') != 1 for label in ('u_even', 'u_odd')):
                raise ValueError('HDMI analysis dashboard disabled')
            if runtime and parameters('reader').get('CACHE_BANKS') != 2:
                raise ValueError('Runtime reader did not elaborate both local cache banks')
            result.setdefault('elaborated_analysis', {})['runtime' if runtime else 'default'] = dict(
                renderer_parameters=expected_parameters, fft_owners=fft_owners,
                both_dashboard_analysis_enabled=True, reader_cache_banks=2 if runtime else 1,
                compile_working_directory=str(ROOT), live_provider_selected=True)
        result['full_hdmi_elaboration'] = dict(default=True, runtime=True, official_gw5a=True)
        compile_log = run('runtime_compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
            '--top-module', 'tb_workstation_display_runtime', '--Mdir', str(output / 'obj'),
            '-I' + str(project), *map(str, runtime_sources)], 180)
        warnings = re.findall(r'^%Warning-([^:]+): ([^\n]+)', compile_log, re.M)
        owned = {pipeline.name, runtime_tb.name, 'display_data_writer.v', 'display_data_reader.v', 'display_data_analysis_source.sv'}
        owned_warnings = [dict(kind=kind, message=message) for kind, message in warnings
            if kind != 'TIMESCALEMOD' and any('/' + name + ':' in message for name in owned)]
        result['verilator_owned_warnings'] = owned_warnings
        result['verilator_warning_counts'] = {kind: sum(k == kind for k, _ in warnings) for kind, _ in warnings}
        if owned_warnings or any(kind == 'UNOPTFLAT' for kind, _ in warnings):
            raise ValueError('New runtime display warning or combinational loop')
        log = run('runtime_run', [str(output / 'obj/Vtb_workstation_display_runtime')])
        print(log, end='')
        match = re.search(r'PASS workstation_display_runtime: publications=(\d+) commits=(\d+) tuple_checks=(\d+) waveform=(\d+) xy=(\d+) fft_columns=(\d+) cdc_drops=(\d+) tail_cancel=1 reader_cancel=1 idle_cache_lease=1', log)
        if not match or int(match[1]) < 6 or int(match[3]) < 10000 or list(map(int, match.groups()[3:6])) != [1024, 131072, 1024] or int(match[7]) < 1:
            raise ValueError('Incomplete runtime display context/CDC/raster coverage')
        result['metrics'] = dict(zip(('publications', 'commits', 'atomic_tuples', 'waveform_samples', 'xy_pixels',
                                     'fft_columns', 'cdc_drops'), map(int, match.groups())))
        result['checks'] = ['initial_image_required', 'actual_48_and_44_fft_wave_xy', '204bit_tuple_atomicity',
            'raster_idle_cache_lease', 'pending_old_epoch_cancel', 'stalled_commit_tail_cancel',
            'partial_reader_cancel', 'same_epoch_final_cdc_drop_cancel', 'error_frame_cancel',
            'epoch_zero_reject', 'default_tokens_equal', 'reverse_exact_parent_bytes', 'full_hdmi_elaboration_both_modes',
            'live_hdmi_provider_not_shadowed', 'native_render_without_local_fft', 'single_fft_owner_both_modes',
            'both_analysis_dashboards_enabled', 'runtime_reader_two_cache_banks']
        if {str(path): digest(path) for path in inputs} != hashes:
            raise ValueError('Verification source inputs changed during run')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(identity=result['identity'], passed=True, source_set_sha256=source_identity)))


if __name__ == '__main__':
    main()
