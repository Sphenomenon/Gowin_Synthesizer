#!/usr/bin/env python3
"""Measure scan admission against actual prepared scanout and DDR queue RTL."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(log, prefix):
    lines = [line for line in log.splitlines() if line.startswith(prefix)]
    if not lines:
        return None
    return {name: int(value) for name, value in re.findall(r'(\w+)=(-?\d+)', lines[-1])}


def run_case(project, output, sources, name, parameters, mode=0, expect_success=True):
    directory = output / name
    directory.mkdir()
    binary = directory / 'simulation'
    command = ['iverilog', '-g2012', '-s', 'tb_video_scanout', '-I', str(project),
               *[f'-Ptb_video_scanout.{key}={value}' for key, value in parameters.items()],
               '-o', str(binary), *map(str, sources)]
    compiled = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=60)
    (directory / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    result = dict(name=name, parameters=parameters, mode=mode, compile_argv=command,
                  compile_exit_code=compiled.returncode, expect_functional_success=expect_success)
    if compiled.returncode:
        result.update(functional_success=False, observation_matches_expectation=False)
        print(f'{name}: COMPILE FAILURE', flush=True)
        return result
    command = ['vvp', str(binary), f'+MODE={mode}']
    simulation = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=600)
    log = simulation.stdout + simulation.stderr
    path = directory / 'simulation.log'
    path.write_text(log)
    success = simulation.returncode == 0 and f'PASS mode={mode} ' in log
    expected_failure = simulation.returncode != 0 and 'unexpected black line' in log
    result.update(run_argv=command, run_exit_code=simulation.returncode,
                  functional_success=success,
                  observation_matches_expectation=success if expect_success else expected_failure,
                  log_sha256=digest(path), log=log,
                  pixels=metrics(log, 'PASS '), competition=metrics(log, 'COMPETITION '),
                  latency_ui_cycles=metrics(log, 'LATENCY '),
                  deadline_violation=metrics(log, 'DIAGNOSTIC '))
    print(f'{name}: {"PASS" if success else "DEADLINE VIOLATION" if expected_failure else "FAIL"}', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='Actual prepared Prj1 directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--active-lines', type=int, default=8)
    parser.add_argument('--case', action='append', help='Run only a named case; repeat for multiple cases')
    args = parser.parse_args()
    if not 8 <= args.active_lines <= 1080:
        parser.error('--active-lines must be between 8 and 1080')
    project = args.project.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    gate = project / 'rtl/display_data/workstation_ddr_scan_window.sv'
    native_hdmi = project / 'rtl/workstation/workstation_hdmi_display.sv'
    provenance_path = project / 'rtl/workstation/workstation_hdmi_display.provenance.json'
    provenance = json.loads(provenance_path.read_text())
    original = native_hdmi.read_text()
    for change in reversed(provenance['exact_changes']):
        if original.count(change['after']) != 1:
            raise ValueError('Native HDMI migration region drifted')
        original = original.replace(change['after'], change['before'])
    if hashlib.sha256(original.encode()).hexdigest() != provenance['parent_sha256']:
        raise ValueError('Native HDMI contains changes outside the declared migration')
    sources = [gate, project / 'rtl/memory/workstation_sdp.sv',
               project / 'src/video/video_ddr_scanout.v',
               project / 'rtl/timing/basic_pitch_ddr_client_queues.sv',
               project / 'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv',
               Path(__file__).with_name('tb_video_scanout.sv')]
    unit = Path(__file__).with_name('tb_workstation_ddr_scan_window.sv')
    inputs = [*sources, unit, native_hdmi, provenance_path,
              project / 'src/memory/ddr_address_map.vh', Path(__file__).resolve()]
    hashes = {str(path): digest(path) for path in inputs}
    profile_path = project.parents[1] / 'workstation_profile.json'
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
    for relative, entry in profile.get('enabled_inputs', {}).items():
        path = project / relative
        if str(path) in hashes and hashes[str(path)] != entry['sha256']:
            raise ValueError('Prepared input drifted from the profile: ' + relative)
    binary = output / 'unit'
    unit_compile = ['iverilog', '-g2012', '-s', 'tb_workstation_ddr_scan_window',
                    '-o', str(binary), str(gate), str(unit)]
    result = subprocess.run(unit_compile, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    unit_result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=30)
    unit_passed = unit_result.returncode == 0 and 'PASS scan-window admission:' in unit_result.stdout
    (output / 'unit.log').write_text(unit_result.stdout + unit_result.stderr)
    common = dict(USE_QUEUES=1, ACTIVE_LINES=args.active_lines, READ_LATENCY_CYCLES=64)
    cases = [
        ('legacy_default', dict(common, USE_SCAN_ADMISSION_MODULE=0), 0, True),
        ('native_default', dict(common, USE_SCAN_ADMISSION_MODULE=1), 0, True),
        ('d5_writer_only_turn100', dict(common, USE_SCAN_ADMISSION_MODULE=1, SCAN_WRITE_WINDOW=1,
                                       WRITE_TURNAROUND_CYCLES=100), 0, True),
        ('mixed_disabled_turn100', dict(common, USE_SCAN_ADMISSION_MODULE=1, COMPETING_CLIENTS=1,
                                        WRITE_TURNAROUND_CYCLES=100), 0, False),
        ('mixed_enabled_turn100', dict(common, USE_SCAN_ADMISSION_MODULE=1, COMPETING_CLIENTS=1,
                                       SCAN_WRITE_WINDOW=1, WRITE_TURNAROUND_CYCLES=100), 0, False),
        ('mixed_48000_turn40', dict(common, USE_SCAN_ADMISSION_MODULE=1, COMPETING_CLIENTS=1,
                                   SCAN_WRITE_WINDOW=1, WRITE_TURNAROUND_CYCLES=40, SAMPLE_RATE_HZ=48000), 0, True),
        ('mixed_44100_turn40', dict(common, USE_SCAN_ADMISSION_MODULE=1, COMPETING_CLIENTS=1,
                                   SCAN_WRITE_WINDOW=1, WRITE_TURNAROUND_CYCLES=40, SAMPLE_RATE_HZ=44100), 0, True),
        ('late_line_48000_turn40', dict(common, USE_SCAN_ADMISSION_MODULE=1, COMPETING_CLIENTS=1,
                                       SCAN_WRITE_WINDOW=1, WRITE_TURNAROUND_CYCLES=40, SAMPLE_RATE_HZ=48000), 1, True),
        ('late_epoch_44100_turn40', dict(common, USE_SCAN_ADMISSION_MODULE=1, COMPETING_CLIENTS=1,
                                        SCAN_WRITE_WINDOW=1, WRITE_TURNAROUND_CYCLES=40, SAMPLE_RATE_HZ=44100), 2, True),
    ]
    known = {case[0] for case in cases}
    if args.case:
        if set(args.case) - known:
            parser.error('Unknown cases: ' + ', '.join(sorted(set(args.case) - known)))
        cases = [case for case in cases if case[0] in args.case]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_case, project, output, sources, *case) for case in cases]
        results = [future.result() for future in futures]
    by_name = {case['name']: case for case in results}
    defaults_equal = None
    if 'legacy_default' in by_name and 'native_default' in by_name:
        legacy, native = by_name['legacy_default'], by_name['native_default']
        defaults_equal = legacy.get('pixels') == native.get('pixels') and legacy['functional_success']
    unchanged = all(digest(Path(path)) == value for path, value in hashes.items())
    evidence = dict(schema=1, scope='Source admission integration and bounded-model diagnostics, not D01/D04 acceptance',
                    d01_complete=False, d04_complete=False, hardware_tested=False, board_accessed=False,
                    candidate_identity=profile.get('candidate_identity'), profile_revision=profile.get('revision'),
                    project=str(project), active_lines=args.active_lines, horizontal_active_pixels=1920,
                    input_sha256=hashes, inputs_unchanged_during_run=unchanged,
                    native_hdmi_reverse_migration_matches_parent=True,
                    default_admission_matches_legacy_pixels_and_command_counts=defaults_equal,
                    unit=dict(compile_argv=unit_compile, passed=unit_passed, log=unit_result.stdout + unit_result.stderr),
                    model_assumptions=dict(ordered_read_latency_ui_cycles=64, native_ready_every='all cycles except cycle%11==0 and direction-turnaround wait',
                        direction_turnaround_ui_cycles=[40, 100], startup_vblank_lines=45,
                        tf_total_request_period='400000000/sample_rate UI cycles, alternate full-beat write/read',
                        delay_total_request_period='200000000/sample_rate UI cycles, alternate full-beat write/read',
                        cnn_request_period_ui_cycles=5000, display_read_period_ui_cycles=5000,
                        background_writers='continuous raster/shared-model writer and masked CPU writer',
                        client_models='Real scanout/queues/core; other producers are bounded test traffic, not real media DMA RTL'),
                    cases=results)
    evidence['diagnostic_checks_passed'] = unit_passed and unchanged and defaults_equal is not False and all(
        case['observation_matches_expectation'] for case in results)
    (output / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('PASS scan-window diagnostic checks' if evidence['diagnostic_checks_passed'] else 'FAIL scan-window diagnostic checks', flush=True)
    if not evidence['diagnostic_checks_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
