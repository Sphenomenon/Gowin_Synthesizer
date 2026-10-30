#!/usr/bin/env python3
"""Real final-drop health CDC plus healthy complete dual-rate controlled runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_counter import selected_source, selection_evidence


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--controlled-evidence', type=Path,
                        help='Optional complete nonzero-epoch verification.json; all inputs must still match')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / name for name in (
        'rtl/workstation/workstation_runtime_controlled.sv', 'rtl/audio/workstation_pcm_observation_bridge.sv',
        'rtl/music/music_async_fifo.sv')]
    sources += [selected_source(project), project / 'src/migration/gw138k_stream_cdc.sv']
    sources += [Path(__file__).with_name('tb_workstation_display_observation_health.sv')]
    inputs = sources + [Path(__file__).resolve(), ROOT / 'tools/workstation_runtime_counter.py', ROOT / 'rtl/audio/DISPLAY_OBSERVATION_HEALTH.md',
                       project.parents[1] / 'workstation_profile.json', project.parents[1] / 'integration_inputs.json']
    initial_hashes = {str(path): digest(path) for path in inputs}
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False, bitstream_identity=None,
                  counter_source=selection_evidence(project),
                  source_policy='Maintained controlled-runtime source with actual physical observation FIFO and display mailbox; explicit prepared CDC and full-runtime support',
                  scope='50MHz display-only sticky loss fault; audio scheduling/stream owner unchanged',
                  policy='Either upstream loss disables new display publication until common runtime reset',
                  limits='Offline directed source-stop/transport tests and full I2S/functional-DDR runtime; no physical timing/CDC/resource or board/deployment acceptance', commands={})

    def run(name, command, timeout=60):
        result['commands'][name] = list(map(str, command))
        with (output / (name + '.log')).open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        return (output / (name + '.log')).read_text()

    try:
        run('tail_compile', ['iverilog', '-g2012', '-s', 'tb_workstation_display_observation_health',
                            '-o', str(output / 'tail.vvp'), *map(str, sources)])
        log = run('tail_run', ['vvp', str(output / 'tail.vvp')])
        print(log, end='')
        if 'PASS display_observation_health: physical_final_drop=1 display_final_drop=1 source_stops=2 resets=4 wrap_checks=1 no_following_frames=1' not in log:
            raise ValueError('Incomplete final-drop/source-stop/reset/wrap checks')
        result['directed'] = dict(physical_final_drop=1, display_final_drop=1, source_stops=2,
                                  common_resets=4, counter_wrap=True, no_following_frames=True)
        if args.controlled_evidence:
            controlled_path = args.controlled_evidence.resolve()
            result['reused_controlled_evidence'] = str(controlled_path)
        else:
            run('controlled_regression', [sys.executable, str(Path(__file__).with_name('run_runtime_controlled.py')),
                '--project', str(project), '--output', str(output / 'controlled'), '--nonzero-epoch'], 360)
            controlled_path = output / 'controlled/verification.json'
        controlled = json.loads(controlled_path.read_text())
        if not controlled['passed'] or not controlled['configuration']['reserve_zero_epoch'] or controlled['metrics'].get('display_observation_fault_checks') != 1:
            raise ValueError('Complete nonzero-epoch healthy display-loss regression missing')
        if controlled['metrics']['observed48'] < 256 or controlled['metrics']['observed44'] < 256 or controlled['metrics']['switches'] != 2:
            raise ValueError('Both physical rates were not verified')
        metrics = controlled['metrics']
        if metrics.get('display_effect_tuple_checks') != metrics['display_frames'] or metrics.get('display_effect_changes48', 0) < 3 or metrics.get('display_effect_changes44', 0) < 3:
            raise ValueError('Atomic display effect tuple was not verified at both physical rates')
        if controlled['new_composition_and_fixture_warning_count'] != 0 or 'UNOPTFLAT' in controlled['warning_counts']:
            raise ValueError('New controlled-runtime warning or combinational loop')
        hashes = dict(initial_hashes)
        for path, value in controlled['input_sha256'].items():
            if digest(Path(path)) != value or (path in hashes and hashes[path] != value):
                raise ValueError('Controlled-runtime evidence source drift: ' + path)
            hashes[path] = value
        if initial_hashes != {str(path): digest(path) for path in inputs}:
            raise ValueError('Directed test source changed during verification')
        source_identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        result.update(identity='native-display-observation-health-v1-' + source_identity[:16],
                      source_set_sha256=source_identity, input_sha256=hashes,
                      controlled_identity=controlled['identity'], controlled_evidence_sha256=digest(controlled_path),
                      controlled_metrics=controlled['metrics'], controlled_warning_count=0,
                      checks=['real_final_physical_fifo_drop_no_next_mclk', 'real_final_display_drop_no_next_compute',
                              'current_nonzero_before_source_sticky', 'source_counter_wrap', 'common_reset_recovery',
                              'normal_48_44100_fault_stays_clear', 'cpu_reset_does_not_rearm_or_fault', 'two_physical_rate_switches',
                              'atomic_203bit_display_effect_frame_tuple', 'effect_mask_order_changes_both_rates'],
                      passed=True)
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(identity=result['identity'], passed=True, source_set_sha256=result['source_set_sha256'])))


if __name__ == '__main__':
    main()
