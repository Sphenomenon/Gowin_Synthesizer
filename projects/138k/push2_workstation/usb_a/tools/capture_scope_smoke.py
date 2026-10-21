#!/usr/bin/env python3
"""CRC-checked startup, control, 32-voice and live vector core-output smoke tests.

No audio sample stream is saved. Optional performances are bounded, use MIDI
and PANIC, and restore neutral synth controls. This does not program the FPGA.
"""
import argparse
import binascii
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import struct
import sys
import time

import serial

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / 'ae350/scripts'))
from midi_serial import performance, expression

RECORD = re.compile(rb'(A138|C350|K138|E138|P138|U138) ((?:[0-9A-F]{8} ){8})([0-9A-F]{4})')
MUSIC = re.compile(rb'B138 ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})')


def wait_for_controls(pump, read_last, label, expected_performance=None,
                      expected_expression=None, timeout=5):
    initial = read_last()
    previous_performance = initial['K138']['sequence']
    previous_expression = initial['E138']['sequence']
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pump(0.25)
        latest = read_last()
        state, options = latest['K138'], latest['E138']
        performance_fresh = state['sequence'] != previous_performance
        expression_fresh = not expected_expression or options['sequence'] != previous_expression
        performance_matches = all(state[name] == value for name, value in (expected_performance or {}).items())
        expression_matches = all(options[name] == value for name, value in (expected_expression or {}).items())
        if performance_fresh and expression_fresh and performance_matches and expression_matches:
            return dict(check=label, performance=dict(state), expression=dict(options))
    raise RuntimeError(f'{label}: fresh matching telemetry timed out; '
                       f'performance={state!r}, expression={options!r}')


def wait_for_snapshot(pump, read_last, read_pair, initial, timeout=6):
    expected_token = (initial['snap_request'] + 1) & 63
    first_completed = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pump(0.25)
        state = read_last()['E138']
        fresh = state['sequence'] != initial['sequence']
        requested = state['snap_request'] == expected_token and state['snap_token'] == expected_token
        if fresh and requested:
            if state['snap_error']:
                raise RuntimeError('live core snapshot reported an error')
            complete = state['snap_completed'] != initial['snap_completed']
            captured = state['snap_sequence'] != initial['snap_sequence']
            if complete and captured and state['snap_done'] and state['snap_count']:
                if first_completed is None:
                    first_completed = (state['snap_completed'], state['sequence'])
                elif state['snap_completed'] == first_completed[0] and state['sequence'] != first_completed[1]:
                    return read_pair()
    raise RuntimeError('live core snapshot did not complete with fresh settled telemetry')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0')
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exercise-live', action='store_true')
    parser.add_argument('--exercise-controls', action='store_true', help='Exercise committed modes, gains, effects, routes, sustain and PANIC')
    parser.add_argument('--exercise-polyphony', action='store_true', help='Exercise 32 held mode-A voices, release and PANIC at reduced gain')
    args = parser.parse_args()
    if not 3 <= args.seconds <= 60:
        parser.error('--seconds must be 3..60')
    if args.output.exists():
        parser.error('preserve previous capture; choose a new output path')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(passed=False, started_at=datetime.now().astimezone().isoformat(timespec='seconds'),
                  exercise_live=args.exercise_live, sample_stream_saved=False, tests={}, last={},
                  limits=['UART smoke does not verify physical DAC waveform, HDMI reception, TF hotplug or CNN song-score correctness.'])
    result['exercise_controls'] = args.exercise_controls
    result['exercise_polyphony'] = args.exercise_polyphony
    counts = Counter()
    model_statuses = set()
    crc_bad = 0
    sample_counts = []
    screen_frames = []
    commands = []
    snapshot_pair=(0,0)
    try:
        port = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=2, exclusive=True)
        port.dtr=False; port.rts=False; port.port=args.port
        with port:
            # Purging the driver alone does not empty old FTDI hardware packets.
            # Drain two real seconds before interpreting fresh board records.
            port.reset_input_buffer()
            warmup=time.monotonic()+2
            while time.monotonic()<warmup: port.read_until(b'\n', size=1024)
            port.reset_input_buffer()

            def pump(seconds):
                nonlocal crc_bad, snapshot_pair
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    raw = port.readline()
                    for match in MUSIC.finditer(raw):
                        words = [int(match[i], 16) for i in range(1, 5)]
                        model_statuses.add((words[3] >> 2) & 15)
                        counts['B138'] += 1
                        result['last']['B138'] = [f'{v:08X}' for v in words]
                    for match in RECORD.finditer(raw):
                        kind = match[1].decode()
                        words = [int(v, 16) for v in match[2].split()]
                        if binascii.crc_hqx(struct.pack('<8I', *words), 0xffff) != int(match[3], 16):
                            crc_bad += 1
                            continue
                        counts[kind] += 1
                        if kind == 'K138':
                            result['last'][kind] = performance(words)
                        elif kind == 'E138':
                            state = expression(words)
                            # Snapshots may contain a single PCM pair. Do not
                            # persist it or reconstruct a sampled audio trace.
                            snapshot_pair=(state.pop('snap_left'),state.pop('snap_right'))
                            result['last'][kind] = state
                        else:
                            result['last'][kind] = [f'{v:08X}' for v in words]
                            if kind == 'A138': sample_counts.append((words[0],words[2]))
                            if kind == 'P138': screen_frames.append(words[5])

            def send(packet):
                port.write(packet); port.flush()
                commands.append(packet.hex(' '))

            def cc(number, value):
                send(bytes([0xb0, number, value]))

            def snapshot():
                initial=dict(result['last']['E138'])
                cc(83,127)
                return wait_for_snapshot(pump, lambda: result['last'], lambda: snapshot_pair, initial)

            pump(args.seconds)
            result['startup_panic_epoch']=result['last'].get('E138',{}).get('panic_epoch',0)
            for kind in ['A138', 'C350', 'K138', 'E138', 'P138', 'B138']:
                if counts[kind] < 2: raise RuntimeError('insufficient valid records: ' + kind)
            cpu = [int(v, 16) for v in result['last']['C350']]
            if cpu[4:6] != [0x43505531, 0x50415353] or cpu[7] != 0:
                raise RuntimeError('AE350 startup signature or trap failed')
            a = [int(v, 16) for v in result['last']['A138']]
            if a[1] & 3 != 3 or ((a[1] >> 8) & 0x43) != 0x43:
                raise RuntimeError('audio PLL or DDR readiness missing')
            if len(sample_counts) < 2 or sample_counts[-1][1] <= sample_counts[0][1]:
                raise RuntimeError('audio engine sample counter stopped')
            report_delta=(sample_counts[-1][0]-sample_counts[0][0]) & 0xffffffff
            sample_delta=(sample_counts[-1][1]-sample_counts[0][1]) & 0xffffffff
            if not report_delta or abs(sample_delta/report_delta-48000)>64:
                raise RuntimeError('audio cadence is not 48000 samples per runtime report')
            if result['last']['K138']['pc_input_errors']:
                raise RuntimeError('PC MIDI input reports errors')
            if model_statuses != {14}:
                raise RuntimeError(f'CNN model readiness changed: {model_statuses}')
            result['tests']['startup_cpu_audio_ddr_model'] = 'passed'
            usb=[int(v,16) for v in result['last']['P138']]
            if usb[1]&2 and len(screen_frames)>1 and screen_frames[-1]>screen_frames[0]:
                result['tests']['push_connected_screen_frames_advancing']='passed'
            else:
                result['tests']['push_connected_screen_frames_advancing']='not_observed'
            result['push_connected']=bool(usb[1]&2)
            if args.exercise_controls:
                control_checks = []

                def check_control(label, expected_performance=None, expected_expression=None):
                    control_checks.append(wait_for_controls(
                        pump, lambda: result['last'], label,
                        expected_performance, expected_expression))

                try:
                    cc(120, 0); cc(104, 0); cc(90, 0); cc(64, 0)
                    cc(81, 0); cc(82, 0); cc(7, 127); cc(11, 127)
                    cc(1, 0); cc(5, 0); send(bytes([0xe0, 0, 64])); send(bytes([0xc0, 73]))
                    for mode in range(3):
                        cc(80, mode)
                        check_control('committed_mode_' + 'ABC'[mode], {'mode': 'ABC'[mode], 'active_voices': 0})
                    cc(7, 64)
                    check_control('volume', {'gain_q15': 16384})
                    cc(11, 64)
                    check_control('expression', {'gain_q15': 8192})
                    cc(1, 37); cc(5, 51)
                    check_control('modulation_glide', expected_expression={'vibrato': 37, 'glide': 51})
                    cc(7, 127); cc(11, 127); cc(1, 0); cc(5, 0)
                    send(bytes([0x90, 60, 96])); cc(64, 127); send(bytes([0x80, 60, 0]))
                    check_control('sustain_without_held_key', {'active_voices': 1, 'held_notes': []}, {'sustain': True})
                    for route, name in enumerate(['stereo', 'left', 'right', 'mute']):
                        cc(82, route)
                        check_control('route_' + name, {'route': name})
                        if route:
                            pair = snapshot()
                            if (route == 1 and pair[1] != 0) or (route == 2 and pair[0] != 0) or (route == 3 and pair != (0, 0)):
                                raise RuntimeError('route does not match core PCM: ' + name)
                    cc(82, 0); cc(81, 0)
                    for effect, mask in [(0, 1), (0, 1), (1, 3), (2, 7)]:
                        cc(87, effect)
                        check_control('effect_queue_' + str(effect), {'effects': mask})
                    cc(88, 0)
                    check_control('effect_master_off', {'effects': 0})
                    cc(88, 0)
                    check_control('effect_master_restore', {'effects': 7})
                    cc(87, 0)
                    check_control('full_queue_next_press_clears', {'effects': 0})
                    cc(64, 0)
                    check_control('sustain_release', {'active_voices': 0}, {'sustain': False})
                    send(bytes([0x90, 64, 96])); check_control('note_before_panic', {'active_voices': 1, 'held_notes': [64]})
                    cc(120, 0)
                    check_control('panic_clears_voices', {'active_voices': 0, 'held_notes': []})
                    result['tests']['common_control_application'] = 'passed'
                finally:
                    cc(120, 0); cc(104, 0); cc(90, 0); cc(64, 0); cc(81, 0)
                    cc(82, 0); cc(7, 127); cc(11, 127); cc(1, 0); cc(5, 0); cc(80, 2)
                    send(bytes([0xe0, 0, 64])); send(bytes([0xc0, 73])); pump(2)
                    result['control_checks'] = control_checks
            if args.exercise_polyphony:
                polyphony_checks = []
                try:
                    cc(120, 0); cc(104, 0); cc(90, 0); cc(64, 0)
                    cc(81, 0); cc(82, 0); cc(7, 32); cc(11, 127); cc(80, 0)
                    cc(1, 0); cc(5, 0); send(bytes([0xe0, 0, 64])); send(bytes([0xc0, 73]))
                    polyphony_checks.append(wait_for_controls(
                        pump, lambda: result['last'], 'polyphony_mode_a_ready',
                        {'mode': 'A', 'active_voices': 0, 'held_notes': [], 'gain_q15': 8192}))
                    notes = list(range(60, 92))
                    send(b''.join(bytes([0x90, note, 72]) for note in notes))
                    polyphony_checks.append(wait_for_controls(
                        pump, lambda: result['last'], 'polyphony_32_held_voices',
                        {'mode': 'A', 'active_voices': 32, 'held_notes': notes}))
                    pump(2)
                    if snapshot() == (0, 0):
                        raise RuntimeError('32-voice core snapshot remained zero')
                    result['polyphony_core_nonzero'] = True
                    send(bytes([0x80, notes[0], 0]))
                    released = wait_for_controls(
                        pump, lambda: result['last'], 'polyphony_single_key_release',
                        {'held_notes': notes[1:]})
                    if released['performance']['active_voices'] not in (31, 32):
                        raise RuntimeError('single release affected other voices')
                    polyphony_checks.append(released)
                    cc(120, 0)
                    polyphony_checks.append(wait_for_controls(
                        pump, lambda: result['last'], 'polyphony_panic',
                        {'active_voices': 0, 'held_notes': []}))
                    result['tests']['polyphony_32_mode_a'] = 'passed'
                finally:
                    cc(120, 0); cc(90, 0); cc(7, 127); cc(11, 127); cc(80, 2); pump(2)
                    result['polyphony_checks'] = polyphony_checks
            if args.exercise_live:
                # Cancel any prior performance before selecting the live mode.
                # A hardware microphone/listener is not assumed by this check.
                try:
                    cc(120, 0); cc(104, 0); cc(90, 0); pump(2)
                    if result['last']['K138']['active_voices']:
                        raise RuntimeError('PANIC did not clear voices')
                    cc(90, 127); pump(1)
                    send(b''.join(bytes([0x90, note, 72]) for note in [60, 64, 67]))
                    pump(3)
                    state = result['last']['K138']
                    if state['active_voices'] != 3 or state['held_notes'] != [60, 64, 67]:
                        raise RuntimeError('three-voice live performance mismatch: ' + str(state))
                    result['live_note_state'] = dict(state)
                    result['tests']['live_three_voices'] = 'passed'
                    distinct=0;nonzero=0
                    for _ in range(3):
                        pair=snapshot()
                        distinct+=pair[0]!=pair[1];nonzero+=pair!=(0,0)
                    result['live_core_snapshot_metrics']={'snapshots':3,'distinct_axes':distinct,'nonzero':nonzero}
                    if not distinct or not nonzero:
                        raise RuntimeError('live geometry did not produce non-diagonal stereo at core output')
                    result['tests']['live_geometry_stereo_core_output']='passed'
                    cc(95, 127); pump(1)
                    if snapshot()!=(0,0):raise RuntimeError('scope mute left nonzero core output')
                    result['tests']['scope_mute_zero_core_output']='passed'
                    cc(95, 0)
                    send(b''.join(bytes([0x80, note, 0]) for note in [60, 64, 67]))
                    pump(2)
                    cc(120, 0); pump(2)
                    if result['last']['K138']['active_voices'] or result['last']['K138']['held_notes']:
                        raise RuntimeError('PANIC left active voices or held notes')
                    if snapshot()!=(0,0):raise RuntimeError('PANIC left nonzero core output')
                    result['tests']['live_note_release_and_panic'] = 'passed'
                finally:
                    cc(120, 0); cc(95, 0); cc(90, 0); pump(1)
            health=int(result['last']['A138'][3],16)
            result['audio_health_word']=f'{health:08X}'
            if health:raise RuntimeError('audio core/serializer health faults reported')
            result['tests']['audio_health_zero']='passed'
            if result['last']['K138']['pc_input_errors'] or crc_bad:
                raise RuntimeError('input/telemetry integrity fault observed')
            result['passed'] = True
    except (OSError, RuntimeError, ValueError) as exc:
        result['error'] = str(exc)
    finally:
        result['crc_valid_records'] = dict(counts)
        result['crc_bad'] = crc_bad
        result['model_statuses'] = sorted(model_statuses)
        result['sample_counter_delta'] = ((sample_counts[-1][1] - sample_counts[0][1]) & 0xffffffff) if len(sample_counts) > 1 else 0
        result['runtime_report_sequence_delta'] = ((sample_counts[-1][0] - sample_counts[0][0]) & 0xffffffff) if len(sample_counts) > 1 else 0
        if result['runtime_report_sequence_delta']:
            result['samples_per_runtime_report']=result['sample_counter_delta']/result['runtime_report_sequence_delta']
        result['push_screen_frame_delta']=(screen_frames[-1]-screen_frames[0]) & 0xffffffff if len(screen_frames)>1 else 0
        result['midi_control_commands'] = commands
        result['finished_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    if not result['passed']: raise SystemExit(1)


if __name__ == '__main__':
    main()
