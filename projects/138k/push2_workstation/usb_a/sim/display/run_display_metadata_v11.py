#!/usr/bin/env python3
"""Opt-in minor1 display context, real analysis, and exact minor0 compatibility."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PINNED_REFERENCE = {
    'src/memory/display_data_writer.v': 'd04be5254fa9ee07e497ff9c92a26a959eb394f3c68366faf71de16543e9d8b8',
    'src/memory/display_data_reader.v': '3079ea0aa9108ec476fbb52ae0814faa41a039c98fba5a486c1ad136c617dd20',
    'src/video/feedback_wave_align.v': '4cc6e5bb6c065266185236ee6dcb6acf9403872096d912cf096ce07b66848d4a',
    'src/video/output_audio_capture.v': '855292cf2db770b21ff690920deee65aeb44a32a786b7a6069403ccbd9ea3a60',
    'src/video/audio_analysis_rom.v': '439ff9f00ff4d29740b296f2e264eabc19e6cb2ff2195dfb2bd815c9d1286946',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='Explicit prepared Prj1 reference')
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    package = ROOT / 'rtl/display_data_layout_pkg.svh'
    writer = ROOT / 'rtl/display_data/display_data_writer.v'
    reader = ROOT / 'rtl/display_data/display_data_reader.v'
    source = ROOT / 'rtl/display_data/display_data_analysis_source.sv'
    fixtures = [Path(__file__).with_name(name) for name in (
        'tb_display_metadata_v11.sv', 'tb_display_metadata_v10_compat.sv',
        'tb_display_analysis_context.sv')]
    legacy_tb = ROOT / 'sim/p11/tb_display_data_reader.sv'
    analysis_sources = [package, writer, reader, source,
                        ROOT / 'rtl/display_data/feedback_capture.v',
                        ROOT / 'rtl/display_data/output_audio_analysis.v']
    analysis_sources += [project / ('src/video/' + name) for name in (
        'output_audio_capture.v', 'audio_analysis_rom.v', 'feedback_wave_align.v')]
    analysis_sources += [fixtures[2]]
    reference_inputs = [project / name for name in PINNED_REFERENCE]
    profile_path = project.parents[1] / 'workstation_profile.json'
    inputs = list(dict.fromkeys(analysis_sources + fixtures + [legacy_tb,
        Path(__file__).resolve(),
        ROOT / 'rtl/display_data/DISPLAY_METADATA_CONTEXT.md', profile_path,
        project.parents[1] / 'integration_inputs.json'] + reference_inputs))
    hashes = {str(path): digest(path) for path in inputs}
    source_identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                  identity='native-display-metadata-v11-offline-v1-' + source_identity[:16],
                  source_set_sha256=source_identity, input_sha256=hashes,
                  prepared_reference_candidate=json.loads(profile_path.read_text())['candidate_identity'],
                  source_policy='Maintained native display writer/reader/optional producer; explicit prepared original capture/alignment/ROM and byte-pinned minor0 writer reference; no top/profile selection',
                  configuration=dict(default_minor=0, explicit_test_minor=1,
                                     supported_hz=[48000, 44100], stream_epoch_zero_allowed=False,
                                     display_local_cache_banks_minor0=1, display_local_cache_banks_minor1=2,
                                     extra_logical_cache_bits_minor1=90112,
                                     real_analysis_input_strobe_every_ui_clocks=16),
                  validation_scope='RTL offline DDR, 512-point unfiltered waveform, actual 2048-point stereo Hann FFT/XY, cancellation and exact legacy cycle/bytes',
                  limitations='Accelerated functional PCM source and ordered functional DDR; no live I2S, DCS, P&R, physical BSRAM count, HDMI pixels, board or deployment acceptance',
                  bitstream_identity=None, commands={})

    def run(name, command, timeout):
        result['commands'][name] = list(map(str, command))
        with (output / (name + '.log')).open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout)
        return (output / (name + '.log')).read_text()

    def icarus(name, sources, marker):
        binary = output / (name + '.vvp')
        run(name + '_compile', ['iverilog', '-g2012', '-I' + str(project), '-s', name,
                              '-o', str(binary), *map(str, sources)], 60)
        log = run(name + '_run', ['vvp', str(binary)], 180)
        if marker not in log:
            raise ValueError('Missing proof marker: ' + marker)
        print(log, end='')
        return log

    try:
        for name, expected in PINNED_REFERENCE.items():
            if hashes[str(project / name)] != expected:
                raise ValueError('Prepared reference identity drift: ' + name)
        result['pinned_reference_sha256'] = PINNED_REFERENCE
        # Only module identifiers change, in a temporary output copy. The
        # original bytes and the locked prepared project remain untouched.
        reference_text = (project / 'src/memory/display_data_writer.v').read_text()
        reference_text = re.sub(r'\bdisplay_data_writer\b', 'reference_display_data_writer', reference_text)
        reference_text = re.sub(r'\bdisplay_write_bridge\b', 'reference_display_write_bridge', reference_text)
        reference = output / 'reference_display_data_writer.v'
        reference.write_text(reference_text)
        result['temporary_renamed_reference_sha256'] = digest(reference)
        compat_log = icarus('tb_display_metadata_v10_compat',
                            [package, writer, reader, reference, fixtures[1]],
                            'PASS display_metadata_v10_compat:')
        match = re.search(r'compared_cycles=(\d+) default_beats=(\d+) context44_rejected=1 reader_unselected_minor1_rejected=1', compat_log)
        if not match or int(match[2]) != 1098:
            raise ValueError('Incomplete minor0 compatibility checks')
        result['minor0_compatibility'] = dict(compared_cycles=int(match[1]), default_beats=int(match[2]),
                                             context44_rejected=True, reader_minor1_rejected=True)
        legacy_log = icarus('tb_display_data_reader', [package, reader, legacy_tb],
                             'PASS display reader:')
        result['legacy_reader_regression_passed'] = True
        v11_log = icarus('tb_display_metadata_v11', [package, writer, reader, fixtures[0]],
                          'PASS display_metadata_v11:')
        match = re.search(r'checks=(\d+) writes=(\d+) commits=(\d+) reads=(\d+) rejected=(\d+) aborted=(\d+) first_reads=(\d+) local_banks=2', v11_log)
        if not match or int(match[1]) < 14 or int(match[5]) != 5 or int(match[6]) != 3 or int(match[7]) < 6 or 'final_payload_aborts=2' not in v11_log:
            raise ValueError('Incomplete minor1 snapshot/cache coverage')
        result['minor1_transport'] = dict(zip(
            ('full_cache_checks', 'writes', 'commits', 'reads', 'rejected', 'aborted', 'first_publish_reads'),
            map(int, match.groups())))
        # Removing the final comparison drain must be detected specifically by
        # the accepted-last-WRITE boundary, rather than a generic watchdog.
        anchor = 'state<=CONTEXT_ENABLED ? VERIFY_CONTEXT : META;'
        if writer.read_text().count(anchor) != 1:
            raise ValueError('Final context-drain negative-control anchor drift')
        mutant = output / 'display_data_writer_without_final_context_drain.v'
        mutant.write_text(writer.read_text().replace(anchor, 'state<=META;'))
        mutant_binary = output / 'without_final_context_drain.vvp'
        run('final_context_negative_compile', ['iverilog', '-g2012', '-s', 'tb_display_metadata_v11',
            '-o', str(mutant_binary), str(package), str(mutant), str(reader), str(fixtures[0])], 60)
        negative = subprocess.run(['vvp', str(mutant_binary)], cwd=project,
            capture_output=True, text=True, timeout=180)
        (output / 'final_context_negative_run.log').write_text(negative.stdout + negative.stderr)
        if negative.returncode == 0 or 'final payload context change published during_write=1' not in negative.stdout:
            raise ValueError('Final context-drain negative control did not reject last-WRITE publication')
        result['final_context_drain_negative_control_passed'] = True
        compile_log = run('analysis_compile', ['verilator', '--binary', '--timing', '-j', '4',
            '-Wno-fatal', '--top-module', 'tb_display_analysis_context', '--Mdir', str(output / 'obj'),
            '-I' + str(project), *map(str, analysis_sources)], 180)
        owned_names = {writer.name, reader.name, source.name, fixtures[2].name}
        warnings = re.findall(r'^%Warning-([^:]+): ([^\n]+)', compile_log, re.M)
        owned_warnings = [dict(kind=kind, message=message) for kind, message in warnings
                          if kind != 'TIMESCALEMOD' and any('/' + name + ':' in message for name in owned_names)]
        result['verilator_owned_warnings'] = owned_warnings
        result['verilator_warning_counts'] = {kind: sum(k == kind for k, _ in warnings) for kind, _ in warnings}
        if owned_warnings or any(kind == 'UNOPTFLAT' for kind, _ in warnings):
            raise ValueError('New display implementation/fixture warning or combinational loop')
        analysis_log = run('analysis_run', [str(output / 'obj/Vtb_display_analysis_context')], 90)
        print(analysis_log, end='')
        match = re.search(r'PASS display_analysis_context: published=(\d+) physical_wave_samples=(\d+) xy_pixels=(\d+) fft_columns=(\d+) discarded=(\d+) early_rejected=(\d+)', analysis_log)
        rates = re.findall(r'RATE_CHECK rate=(\d+) epoch=(\d+) left_bin=(\d+) right_bin=(\d+) left_hz_q16=(\d+) right_hz_q16=(\d+) generation=(\d+)', analysis_log)
        if not match or list(map(int, match.groups()[:4])) != [3, 1536, 196608, 1536] or len(rates) != 3:
            raise ValueError('Incomplete real analysis result coverage')
        if [int(row[0]) for row in rates] != [48000, 44100, 44100] or any(row[2:4] != ('32', '64') for row in rates):
            raise ValueError('Actual-rate FFT frequency identity failure')
        result['real_analysis'] = dict(zip(('published', 'wave_samples', 'xy_pixels', 'fft_columns',
                                            'discarded_contexts', 'early_rejected'), map(int, match.groups())))
        result['rate_results'] = [dict(zip(('rate_hz', 'epoch', 'left_bin', 'right_bin', 'left_hz_q16',
                                           'right_hz_q16', 'commit_generation'), map(int, row))) for row in rates]
        result['checks'] = ['48_to_44_to_48', 'same_epoch_observation_loss', 'epoch_zero_rejection',
            'mixed_wave_analysis_generation_rejection', 'all_descriptor_versions_epochs',
            'late_metadata_corruption_last_image', 'final_seqlock_corruption_last_image',
            'slow_reader_bank_reuse', 'stalled_writer_context_abort_stability',
            'final_capture_and_accepted_write_context_abort', 'final_context_drain_negative_control',
            'sealed_snapshot_keeps_old_tags', 'first_synchronous_publish_read', 'reset',
            'default_writer_exact_cycle_bytes', 'default_reader_unselected_minor1',
            'context_aware_minor0_refuses_44100', 'untrusted_source_rejected', 'actual_fft_and_xy']
        if {str(path): digest(path) for path in inputs} != hashes:
            raise ValueError('Source inputs changed during verification')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(identity=result['identity'], passed=result['passed'], source_set_sha256=source_identity)))


if __name__ == '__main__':
    main()
