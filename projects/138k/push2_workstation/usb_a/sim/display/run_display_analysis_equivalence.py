#!/usr/bin/env python3
"""Compare all producer outputs against byte-pinned pre-M8 real FFT/XY RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from run_display_metadata_v11 import PINNED_REFERENCE, ROOT, digest

FIXTURES = Path(__file__).resolve().parent
REFERENCE_SHA256 = 'a8f1a948370a464d6ed609d275075e2ff936a01e62bc915074914a1193d9736c'


def require_reference(path):
    if digest(path) != REFERENCE_SHA256:
        raise ValueError('Pre-M8 analysis reference identity drift')


def output_names(path):
    header = path.read_text().split('\n);', 1)[0]
    declarations = re.findall(r'\boutput\s+(?:wire|reg)\s*(?:\[[^]]+\])?\s*([^\n]+)', header)
    return [name.strip() for declaration in declarations
            for name in declaration.rstrip(',').split(',')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='Explicit pinned prepared Prj1')
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
    parser.add_argument('--reference-source', type=Path,
                        default=FIXTURES / 'fixtures/display_data_analysis_source_pre_m8.sv',
                        help='Still must match the fixed pre-M8 SHA256; cannot replace the oracle')
    args = parser.parse_args()
    project, output, frozen = args.project.resolve(), args.output.resolve(), args.reference_source.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/display_data/display_data_analysis_source.sv'
    checker = FIXTURES / 'display_analysis_equivalence_checker.sv'
    bench = FIXTURES / 'tb_display_analysis_context.sv'
    metadata_runner = FIXTURES / 'run_display_metadata_v11.py'
    sources = [ROOT / name for name in (
        'rtl/display_data_layout_pkg.svh', 'rtl/display_data/display_data_writer.v',
        'rtl/display_data/display_data_reader.v', 'rtl/display_data/feedback_capture.v',
        'rtl/display_data/output_audio_analysis.v')]
    sources += [project / ('src/video/' + name) for name in (
        'output_audio_capture.v', 'audio_analysis_rom.v', 'feedback_wave_align.v')]
    inputs = list(dict.fromkeys([*sources, source, checker, bench, frozen, metadata_runner,
        Path(__file__).resolve(), *[project / name for name in PINNED_REFERENCE],
        project.parents[1] / 'workstation_profile.json', project.parents[1] / 'integration_inputs.json']))
    hashes = {str(path): digest(path) for path in inputs}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, identity='display-analysis-equivalence-v1-' + identity[:16],
        source_set_sha256=identity, input_sha256=hashes, hardware_tested=False,
        synthesis_tested=False, place_and_route_tested=False, sram_deployed=False, flash_deployed=False,
        reference_sha256=REFERENCE_SHA256,
        reference_origin='ec223df:projects/138k/push2_workstation/usb_a/rtl/display_data/display_data_analysis_source.sv',
        source_policy='Maintained production producer versus exact pre-M8 bytes; temporary module-identifier rename only; actual 2048 FFT, XY, waveform and pinned prepared capture/alignment/ROM',
        comparison='All 21 external outputs on both clock edges and asynchronous reset assertion, after delta settling; includes unqualified read data and metadata',
        scope='Original metadata minor0/minor1 and real-analysis scenarios plus producer cycle equivalence, all epoch bits, sequence wrap/skip/repeat, trust/loss/error and FFT reset',
        limitations='Accelerated functional PCM and DDR; no physical audio/video, CDC/PLL, timing, resource or board acceptance',
        commands={})

    def run(name, command, timeout=180, check=True):
        result['commands'][name] = list(map(str, command))
        with (output / (name + '.log')).open('w') as stream:
            process = subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                                     check=check, timeout=timeout)
        return process.returncode, (output / (name + '.log')).read_text()

    def compile_case(name, implementation, reference):
        directory = output / name
        directory.mkdir()
        _, log = run(name + '_compile', ['verilator', '--binary', '--timing', '-j', '4',
            '-Wno-fatal', '-DDISPLAY_ANALYSIS_EQUIVALENCE', '--top-module', 'tb_display_analysis_context',
            '--Mdir', str(directory / 'obj'), '-I' + str(project),
            *map(str, [*sources, implementation, reference, checker, bench])])
        warnings = re.findall(r'^%Warning-([^:]+): ([^\n]+)', log, re.M)
        owned = {source.name, implementation.name, checker.name, bench.name}
        own = [dict(kind=kind, message=message) for kind, message in warnings
               if kind != 'TIMESCALEMOD' and any('/' + item + ':' in message for item in owned)]
        if own or any(kind == 'UNOPTFLAT' for kind, _ in warnings):
            raise ValueError('Owned equivalence fixture warning or combinational loop: ' + str(own))
        return directory / 'obj/Vtb_display_analysis_context'

    try:
        require_reference(frozen)
        for name, expected in PINNED_REFERENCE.items():
            if hashes[str(project / name)] != expected:
                raise ValueError('Prepared reference identity drift: ' + name)
        result['pinned_prepared_reference_sha256'] = PINNED_REFERENCE
        ports = output_names(source)
        if len(ports) != 21 or ports != output_names(frozen):
            raise ValueError('Producer external output contract changed')
        if any(checker.read_text().count('if(' + name + '!==reference_' + name + ')') != 1 for name in ports):
            raise ValueError('Checker does not compare every producer output exactly once')
        result['compared_output_ports'] = ports
        original = frozen.read_text()
        anchor = 'module display_data_analysis_source ('
        if original.count(anchor) != 1:
            raise ValueError('Pinned reference module rename anchor drift')
        reference = output / 'reference_display_data_analysis_source.sv'
        reference.write_text(original.replace(anchor, 'module reference_display_data_analysis_source ('))
        result['temporary_reference_sha256'] = digest(reference)
        # Keep the existing transport/legacy/real-result gates in the chain.
        run('metadata', [sys.executable, str(metadata_runner), '--project', str(project),
                         '--output', str(output / 'metadata')], 300)
        metadata = output / 'metadata/verification.json'
        metadata_result = json.loads(metadata.read_text())
        if not metadata_result['passed']:
            raise ValueError('Original metadata regression failed')
        result['original_metadata_regression'] = dict(identity=metadata_result['identity'],
            verification_sha256=digest(metadata), real_analysis=metadata_result['real_analysis'],
            minor0_compatibility=metadata_result['minor0_compatibility'],
            minor1_transport=metadata_result['minor1_transport'])
        binary = compile_case('equivalence', source, reference)
        _, log = run('equivalence_run', [str(binary), '+IDENTITY_EDGES'], 180)
        print(log, end='')
        marker = re.search(r'PASS display_analysis_equivalence: compared_edges=(\d+) output_ports=(\d+) published=(\d+) identity_cases=(\d+)', log)
        edges = re.search(r'IDENTITY_EDGE_CHECK cases=(\d+) wrap_frames=(\d+) epoch_bits=(\d+) sequence_faults=(\d+) trust=(\d+) loss=(\d+) error=(\d+) resets=(\d+) fft_resets=(\d+)', log)
        if not marker or not edges or int(marker[1]) < 1000000 or list(map(int, marker.groups()[1:])) != [21, 4, 79]:
            raise ValueError('Incomplete external-output equivalence coverage')
        if list(map(int, edges.groups())) != [79, 4, 32, 2, 1, 1, 1, 2, 1]:
            raise ValueError('Missing directed identity/revocation cases')
        result['equivalence'] = dict(compared_edges=int(marker[1]), output_ports=21, publications=4,
            physical_wave_samples=2048, xy_pixels=262144, fft_columns=2048,
            identity_cases=79, wrap_frames=4, epoch_bits=32, sequence_faults=2,
            trust=1, loss=1, frame_error=1, resets=2, fft_resets=1)
        # A wrong prediction must fail at the public interface before any real
        # analysis publication; a passing pair cannot be a disconnected oracle.
        mutation = 'expected_sequence<=frame_sequence_i+1\'b1;'
        current = source.read_text()
        if current.count(mutation) != 1:
            raise ValueError('Sequence-prediction negative-control anchor drift')
        mutant = output / 'display_data_analysis_source_wrong_prediction.sv'
        mutant.write_text(current.replace(mutation, 'expected_sequence<=frame_sequence_i+32\'d2;'))
        mutant_binary = compile_case('negative_sequence', mutant, reference)
        code, negative = run('negative_sequence_run', [str(mutant_binary), '+IDENTITY_EDGES'], 180, False)
        if code == 0 or 'display analysis output mismatch:' not in negative:
            raise ValueError('Wrong sequence prediction escaped the public-output oracle')
        result['sequence_prediction_negative_control'] = dict(passed=True, exit_code=code,
            log_sha256=digest(output / 'negative_sequence_run.log'))
        altered = output / 'rejected_reference_identity.sv'
        altered.write_bytes(frozen.read_bytes() + b'\n// hash-gate negative control\n')
        try:
            require_reference(altered)
        except ValueError:
            result['changed_reference_rejected'] = True
        else:
            raise ValueError('Changed reference passed immutable identity gate')
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('Equivalence inputs changed during verification')
        result['equivalence_log_sha256'] = digest(output / 'equivalence_run.log')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(identity=result['identity'], passed=result['passed'], source_set_sha256=identity)))


if __name__ == '__main__':
    main()
