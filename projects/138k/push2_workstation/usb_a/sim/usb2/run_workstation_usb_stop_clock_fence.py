#!/usr/bin/env python3
"""Opt-in real USB FIFO reset fencing and unchanged-default regression."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from run_workstation_usb_runtime_reset import ROOT, compact, digest, instance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-native-opt-in', action='store_true',
                        help='Require the actual preprocessed runtime top to select the new parameter')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    bench = Path(__file__).with_name('tb_workstation_usb_stop_clock_fence.sv')
    old_runner = Path(__file__).with_name('run_workstation_usb_runtime_reset.py')
    old_bench = Path(__file__).with_name('tb_workstation_usb_runtime_reset.sv')
    contract = ROOT / 'rtl/workstation/USB_INPUT_QUEUE_FENCE.md'
    frozen = ROOT / 'reports/workstation_task_20261030/usb_runtime_reset_isolation.json'
    top = ROOT / 'rtl/workstation/gw138k_push_workstation_top.v'
    wrapper = ROOT / 'rtl/workstation/workstation_usb2_input.sv'
    owner = ROOT / 'rtl/push2_usb_a_control.sv'
    sources = [ROOT / name for name in ('rtl/push2_usb_a_control.sv', 'rtl/audio/push2_controls.sv',
        'rtl/workstation/workstation_usb2_service_adapter.sv', 'rtl/display_data/push2_surface_pixels.sv',
        'rtl/control/workstation_session.sv')]
    sources += [ROOT / 'rtl/push2' / name for name in ('push2_playlist_hold.sv', 'push2_song_menu.sv',
        'push2_score_guide.sv', 'push2_lights.sv', 'push2_led_tx.sv', 'push2_song_screen.sv')]
    sources += [project / name for name in ('src/migration/gw138k_stream_cdc.sv',
        'src/usb_host/gw138k_usb_event_fifo.v', 'src/push2/push2_midi_rx.sv', 'src/video/video_font_5x7.v')]
    sources += [bench]
    inputs = sources + [top, wrapper, old_runner, old_bench, contract, frozen, Path(__file__).resolve(),
        project.parents[1] / 'workstation_profile.json', project.parents[1] / 'integration_inputs.json']
    hashes = {str(path): digest(path) for path in inputs}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, identity='native-usb-stop-clock-fence-offline-v1-' + identity[:16],
        source_set_sha256=identity, input_sha256=hashes, hardware_tested=False, synthesis_tested=False,
        profile_changed=False, sram_deployed=False, flash_deployed=False, bitstream_identity=None,
        source_policy='Maintained default-zero opt-in owner/wrapper with unchanged source-hashed generated FIFO and explicit prepared support',
        scope='Real adapter/queue/session stop-clock boundary fencing, with modeled held/volume and legacy replay negative control',
        limits='Continuous 48MHz USB; compute at most 76.8MHz; no ULPI/USB enumeration, DSP, physical audio/PLL/CDC/timing/resource or board acceptance',
        configuration=dict(default_enabled=False, reset_hold_compute_edges=6, post_reset_drain_compute_edges=6,
            write_ready_usb_edges=2, require_native_opt_in=args.require_native_opt_in), commands={})

    def run(name, command, timeout=90):
        result['commands'][name] = list(map(str, command))
        with (output / (name + '.log')).open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        return (output / (name + '.log')).read_text()

    try:
        prior = json.loads(frozen.read_text())
        fifo = project / 'src/usb_host/gw138k_usb_event_fifo.v'
        expected_fifo = [value for path, value in prior['input_sha256'].items() if path.endswith('/src/usb_host/gw138k_usb_event_fifo.v')]
        if len(expected_fifo) != 1 or digest(fifo) != expected_fifo[0]:
            raise ValueError('Original generated FIFO bytes changed')
        for source in (owner, wrapper):
            if not re.search(r'parameter\s+integer\s+STOP_CLOCK_QUEUE_FENCE\s*=\s*0\b', source.read_text()):
                raise ValueError('Fence must remain default zero: ' + str(source))
        prefix = wrapper.read_text().split('input_owner', 1)[0]
        binding = re.search(r'push2_usb_a_control\s*#\((.*?)\)\s*$', prefix, re.S)
        forwarded = [] if binding is None else re.findall(
            r'\.STOP_CLOCK_QUEUE_FENCE\(([^()]+)\)', binding.group(1))
        if [value.strip() for value in forwarded] != ['STOP_CLOCK_QUEUE_FENCE']:
            raise ValueError('Wrapper does not forward the explicit fence parameter')
        run('default_regression', [sys.executable, str(old_runner), '--project', str(project),
            '--output', str(output / 'default')], 240)
        default_path = output / 'default/verification.json'
        default = json.loads(default_path.read_text())
        if not default['passed'] or default['metrics'] != prior['metrics']:
            raise ValueError('Default-zero adapter behavior differs from frozen reset regression')
        if args.require_native_opt_in and default['actual_top_binding']['stop_clock_queue_fence'] != 1:
            raise ValueError('Actual native top has not explicitly enabled the queue fence')
        for path, value in default['input_sha256'].items():
            if hashes.get(path) != value:
                raise ValueError('Default regression support/source closure differs: ' + path)
        result['actual_top_binding'] = default['actual_top_binding']
        result['native_profile_opt_in_verified'] = default['actual_top_binding']['stop_clock_queue_fence'] == 1
        result['default_compatibility'] = dict(passed=True, identity=default['identity'],
            verification_sha256=digest(default_path), original_metrics_equal=True, metrics=default['metrics'])
        log = run('compile', ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps',
            '-j', '4', '-Wno-fatal', '--top-module', 'tb_workstation_usb_stop_clock_fence',
            '--Mdir', str(output / 'obj'), *map(str, sources)], 180)
        warnings = re.findall(r'^%Warning-([^:]+): ([^\n]+)', log, re.M)
        owned = {bench.name, owner.name, wrapper.name}
        own = [dict(kind=kind, message=message) for kind, message in warnings
            if kind != 'TIMESCALEMOD' and any('/' + name + ':' in message for name in owned)]
        result['owned_warnings'] = own
        result['warning_counts'] = {kind: sum(k == kind for k, _ in warnings) for kind, _ in warnings}
        if own or any(kind == 'UNOPTFLAT' for kind, _ in warnings):
            raise ValueError('New owner/fixture warning or combinational loop')
        log = run('run', [str(output / 'obj/Vtb_workstation_usb_stop_clock_fence')], 60)
        print(log, end='')
        rows = re.findall(r'USB_STOP_CLOCK_FENCE (enabled=\d+[^\n]*)', log)
        cases = {values['enabled']: values for values in (
            {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', row)} for row in rows)}
        if set(cases) != {0, 1}:
            raise ValueError('Missing opt-in/legacy comparison')
        current, legacy = cases[1], cases[0]
        expected = dict(attaches=3, barriers=4, detaches=2, panics=1, defaults=39, stale=0, fresh=3,
                        blocked=3, hold_stops=3, drain_stops=3, pointer_checks=3, stores=18)
        if any(current[name] != value for name, value in expected.items()) or legacy['stale'] == 0:
            raise ValueError('Incomplete boundary/fence/pointer/legacy replay checks')
        if 'PASS usb_stop_clock_fence:' not in log:
            raise ValueError('Missing final stopped-clock fence oracle')
        result['metrics'] = dict(opt_in=current, legacy=legacy)
        result['generated_fifo_unchanged'] = True
        result['protocol_clock_budget'] = dict(usb_hz=48000000, compute_max_hz=76800000,
            effective_producer_to_read_edges=3, generated_read_reset_release_edges=2,
            zero_pointer_to_read_ready_min_compute_edges=9, zero_pointer_to_read_ready_min_ns=117.1875,
            usb_pointer_return_and_application_edges=3, usb_pointer_return_and_application_ns=62.5,
            buffered_consume_return_usb_edges=4, buffered_consume_return_ns=83.333333,
            additional_write_ready_usb_edges=2,
            first_fresh_write_actual_pointers_buffer_and_reset_checked=True)
        result['checks'] = ['default_zero_metrics_equal_frozen_regression', 'generated_fifo_bytes_unchanged',
            'wrapper_parameter_forwarding', 'actual_native_top_selection_recorded', 'stopped_compute_short_hotplug',
            'stopped_compute_panic', 'repeated_connection_boundaries_coalesce_and_refence',
            'stop_again_during_six_edge_hold', 'stop_again_during_six_edge_post_reset_drain',
            'normal_store_backpressure_until_compute_ack', 'first_fresh_write_real_pointer_roundtrip',
            'zero_stale_notes_or_parameters_after_opt_in_fence', 'legacy_zero_parameter_reproduces_old_ram_replay']
        if {str(path): digest(path) for path in inputs} != hashes:
            raise ValueError('Source drift during queue-fence verification')
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(identity=result['identity'], passed=True, source_set_sha256=identity)))


if __name__ == '__main__':
    main()
