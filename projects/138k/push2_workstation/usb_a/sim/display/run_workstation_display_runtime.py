#!/usr/bin/env python3
"""Verify optional native HDMI composition, CDC and current-context publication."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_counter import NATIVE, selected_source, selection_evidence
from tools import workstation_hdmi_provenance as hdmi_provenance


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(text):
    return re.findall(r'\w+|\S', re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-counter', action='store_true',
                        help='Explicitly test the maintained native counter with validated prepared support')
    parser.add_argument('--hdmi-adaptation', choices=[hdmi_provenance.OWNER8_POLICY],
                        help='Explicit checked provenance bridge; default retains the original checksum gate')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    native_hdmi = ROOT / 'rtl/workstation/workstation_hdmi_display.sv'
    provenance_path = native_hdmi.with_suffix('.provenance.json')
    adaptation_path = ROOT / hdmi_provenance.ADAPTATION if args.hdmi_adaptation else None
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
    prepared_counter = selected_source(project)
    counter = ROOT / NATIVE if args.native_counter else prepared_counter
    common += [project / 'src/migration/gw138k_stream_cdc.sv', counter]
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
    owner8_sources = [project / name for name in hdmi_provenance.OWNER8_SOURCES]
    a07_path = ROOT / 'reports/workstation_task_20261030/display_metadata_v11_native.json'
    profile_path = project.parents[1] / 'workstation_profile.json'
    inputs = list(dict.fromkeys(runtime_sources + hdmi_sources +
        (owner8_sources + [ROOT / name for name in hdmi_provenance.OWNER8_SOURCES] +
         [adaptation_path, project / 'Prj1.gprj', project / hdmi_provenance.SOURCE] if args.hdmi_adaptation else []) +
        [prepared_counter, ROOT / 'tools/workstation_runtime_counter.py', ROOT / 'tools/workstation_hdmi_provenance.py', native_hdmi, provenance_path,
        ROOT / 'rtl/workstation/RUNTIME_DISPLAY.md', a07_path, Path(__file__).resolve(),
        project / 'src/memory/ddr_address_map.vh', profile_path, project.parents[1] / 'integration_inputs.json']))
    hashes = {str(path): digest(path) for path in inputs}
    source_identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
        counter_source=selection_evidence(project),
        counter_compilation=dict(source=str(counter), sha256=digest(counter), explicit_native_override=args.native_counter),
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
        prior_runtime, result['hdmi_provenance'] = hdmi_provenance.verify(
            native_hdmi.read_bytes(), provenance_path.read_bytes(),
            args.hdmi_adaptation or hdmi_provenance.STRICT_POLICY,
            adaptation_path.read_bytes() if adaptation_path else None)
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
        modes = [('default', False, False), ('runtime', True, False)]
        if args.hdmi_adaptation:
            profile = json.loads(profile_path.read_text())
            result['owner8_prepared_source_bindings'] = hdmi_provenance.prepared_owner8_sources(ROOT, project, profile)
            modes.append(('runtime_owner8', True, True))
        for mode, runtime, owner8 in modes:
            name = 'hdmi_' + mode + '_elaboration'
            run(name, ['iverilog', '-g2012', '-I' + str(ROOT), '-I' + str(project), '-s', 'tb_workstation_hdmi_elaboration',
                *(['-DWORKSTATION_RUNTIME_NATIVE'] if runtime else []),
                *(['-DWORKSTATION_RECORDING_DDR'] if owner8 else []), '-o', str(output / (name + '.vvp')),
                *map(str, hdmi_sources + (owner8_sources if owner8 else []))], cwd=ROOT)
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
                    r'\.param/l "(\w+)"[^\n]*\+?C4<([01]+)>', matching[0])}
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
            arbiters = [kind for scope, kind, _ in scopes if scope == 'u_arbiter']
            expected_arbiter = 'workstation_recording_ddr_client_queues' if owner8 else 'basic_pitch_ddr_client_queues'
            if arbiters != [expected_arbiter]:
                raise ValueError('Wrong HDMI DDR arbiter elaborated: ' + repr(arbiters))
            if owner8:
                if parameters('u_arbiter').get('RECORDING_ENABLE') != 1 or parameters('u_core').get('RECORDING_ENABLE') != 1:
                    raise ValueError('HDMI owner8 arbitration disabled')
                cores = [kind for scope, kind, _ in scopes if scope == 'u_core']
                slots = [scope for scope, kind, _ in scopes if kind == 'basic_pitch_ddr_client_slot']
                if cores != ['workstation_recording_ddr_arbiter_pipeline'] or len(slots) != 9:
                    raise ValueError('HDMI owner8 core or nine request slots missing')
                result['owner8_elaboration'] = dict(arbiter=expected_arbiter,
                    core=cores[0], recording_enabled=True, request_slots=len(slots),
                    actual_prepared_sources=True, behavioral_or_hardware_acceptance=False)
            result.setdefault('elaborated_analysis', {})[mode] = dict(
                renderer_parameters=expected_parameters, fft_owners=fft_owners,
                both_dashboard_analysis_enabled=True, reader_cache_banks=2 if runtime else 1,
                compile_working_directory=str(ROOT), live_provider_selected=True)
        result['full_hdmi_elaboration'] = dict(default=True, runtime=True,
            runtime_owner8=bool(args.hdmi_adaptation), official_gw5a=True)
        compile_log = run('runtime_compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
            '--top-module', 'tb_workstation_display_runtime', '--Mdir', str(output / 'obj'),
            '-I' + str(project), *map(str, runtime_sources)], 180)
        warnings = re.findall(r'^%Warning-([^:]+): ([^\n]+)', compile_log, re.M)
        owned = {pipeline.name, runtime_tb.name, 'display_data_writer.v', 'display_data_reader.v',
                 'display_data_analysis_source.sv', 'workstation_runtime_counter_cdc.sv'}
        owned_warnings = [dict(kind=kind, message=message) for kind, message in warnings
            if kind != 'TIMESCALEMOD' and any('/' + name + ':' in message for name in owned)]
        result['verilator_owned_warnings'] = owned_warnings
        result['verilator_warning_counts'] = {kind: sum(k == kind for k, _ in warnings) for kind, _ in warnings}
        if owned_warnings or any(kind == 'UNOPTFLAT' for kind, _ in warnings):
            raise ValueError('New runtime display warning or combinational loop')
        log = run('runtime_run', [str(output / 'obj/Vtb_workstation_display_runtime')])
        print(log, end='')
        match = re.search(r'PASS workstation_display_runtime: publications=(\d+) commits=(\d+) tuple_checks=(\d+) waveform=(\d+) xy=(\d+) fft_columns=(\d+) cdc_drops=(\d+) tail_cancel=1 reader_cancel=1 idle_cache_lease=1 gray_drop_cycle_checks=(\d+) drop_revocations=(\d+) drop_completion_races=(\d+)', log)
        if not match or int(match[1]) < 6 or int(match[3]) < 10000 or list(map(int, match.groups()[3:6])) != [1024, 131072, 1024] or int(match[7]) < 1 or int(match[8]) < 10000 or int(match[9]) < 1 or int(match[10]) != 1:
            raise ValueError('Incomplete runtime display context/CDC/raster coverage')
        if 'reset_local_release=1' not in log:
            raise ValueError('Stopped-clock local reset release was not checked')
        result['metrics'] = dict(zip(('publications', 'commits', 'atomic_tuples', 'waveform_samples', 'xy_pixels',
                                     'fft_columns', 'cdc_drops', 'gray_drop_cycle_checks', 'drop_revocations', 'drop_completion_races'), map(int, match.groups())))
        result['checks'] = ['initial_image_required', 'actual_48_and_44_fft_wave_xy', '204bit_tuple_atomicity',
            'raster_idle_cache_lease', 'pending_old_epoch_cancel', 'stalled_commit_tail_cancel',
            'partial_reader_cancel', 'same_epoch_final_cdc_drop_cancel', 'cycle_exact_gray_drop_revocation',
            'drop_coincident_with_reader_publication_cancel', 'error_frame_cancel',
            'epoch_zero_reject', 'source_reset_async_revoke_both_domains', 'stopped_clock_local_reset_release',
            'default_tokens_equal', 'reverse_exact_parent_bytes', 'full_hdmi_elaboration_both_modes',
            'live_hdmi_provider_not_shadowed', 'native_render_without_local_fft', 'single_fft_owner_both_modes',
            'both_analysis_dashboards_enabled', 'runtime_reader_two_cache_banks']
        if args.hdmi_adaptation:
            result['checks'] += ['explicit_owner8_adaptation_reverse_to_original_native',
                                 'actual_owner8_arbiter_core_nine_slots_elaboration']
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
