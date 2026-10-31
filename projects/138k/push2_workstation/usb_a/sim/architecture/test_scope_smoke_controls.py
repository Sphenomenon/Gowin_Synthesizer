import binascii
from contextlib import ExitStack
import itertools
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
try:
    import serial
except ModuleNotFoundError:
    sys.modules['serial'] = types.ModuleType('serial')
import capture_scope_smoke as smoke


class ControlTelemetry(unittest.TestCase):
    def wait(self, frames, performance=None, expression=None):
        current = frames[0]
        pending = iter(frames[1:])

        def pump(_seconds):
            nonlocal current
            current = next(pending, current)

        ticks = itertools.count()
        with patch.object(smoke.time, 'monotonic', side_effect=lambda: next(ticks) * 0.1):
            return smoke.wait_for_controls(pump, lambda: current, 'test',
                                           performance, expression, timeout=0.6)

    def frame(self, sequence, mode='C', sustain=False, expression_sequence=None):
        return {'K138': {'sequence': sequence, 'mode': mode},
                'E138': {'sequence': sequence if expression_sequence is None else expression_sequence,
                         'sustain': sustain}}

    def test_waits_past_stale_matching_data(self):
        result = self.wait([self.frame(1), self.frame(1), self.frame(2)], {'mode': 'C'})
        self.assertEqual(result['performance']['sequence'], 2)

    def test_waits_for_committed_state_after_fresh_old_snapshot(self):
        result = self.wait([self.frame(1), self.frame(2), self.frame(3, 'A')], {'mode': 'A'})
        self.assertEqual(result['performance']['sequence'], 3)

    def test_wrong_state_still_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'fresh matching telemetry timed out'):
            self.wait([self.frame(1), self.frame(2)], {'mode': 'A'})

    def test_expression_requires_its_own_fresh_record(self):
        result = self.wait([self.frame(1, sustain=True),
                            self.frame(2, sustain=True, expression_sequence=1),
                            self.frame(3, sustain=True)], expression={'sustain': True})
        self.assertEqual(result['expression']['sequence'], 3)

    def test_exact_held_note_list_requires_fresh_matching_state(self):
        initial, wrong, matching = self.frame(1), self.frame(2), self.frame(3)
        initial['K138']['held_notes'] = []
        wrong['K138']['held_notes'] = [60]
        matching['K138']['held_notes'] = list(range(60, 92))
        result = self.wait([initial, wrong, matching], {'held_notes': list(range(60, 92))})
        self.assertEqual(result['performance']['sequence'], 3)


class SnapshotTelemetry(unittest.TestCase):
    def state(self, sequence, request, completed, pair=(0, 0), error=False):
        return {'E138': dict(sequence=sequence, snap_request=request, snap_token=request,
                             snap_completed=completed, snap_sequence=completed + 100,
                             snap_done=True, snap_error=error, snap_count=1), 'pair': pair}

    def wait(self, frames):
        current = frames[0]
        pending = iter(frames[1:])

        def pump(_seconds):
            nonlocal current
            current = next(pending, current)

        ticks = itertools.count()
        with patch.object(smoke.time, 'monotonic', side_effect=lambda: next(ticks) * 0.1):
            return smoke.wait_for_snapshot(pump, lambda: current, lambda: current['pair'],
                                           frames[0]['E138'], timeout=0.8)

    def test_waits_for_settled_fresh_record_after_completion(self):
        first = self.state(2, 13, 13, (99, 99))
        pair = self.wait([self.state(1, 12, 12), first, first, self.state(3, 13, 13)])
        self.assertEqual(pair, (0, 0))

    def test_rejects_wrong_token(self):
        with self.assertRaisesRegex(RuntimeError, 'did not complete'):
            self.wait([self.state(1, 12, 12), self.state(2, 14, 13), self.state(3, 14, 13)])

    def test_does_not_hide_snapshot_error(self):
        with self.assertRaisesRegex(RuntimeError, 'reported an error'):
            self.wait([self.state(1, 12, 12), self.state(2, 13, 13, error=True)])

    def test_token_wrap_is_distinct_from_completion_count(self):
        pair = self.wait([self.state(1, 63, 63), self.state(2, 0, 64), self.state(3, 0, 64)])
        self.assertEqual(pair, (0, 0))


class RecognitionMode(unittest.TestCase):
    def capture(self, disabled=False, model=None, fault=None, exercises=(),
                late_model=False, exercise_failure=None):
        class Port:
            def __init__(self):
                self.sequence = 0
                self.writes = []

            def __enter__(self): return self
            def __exit__(self, *args): pass
            def reset_input_buffer(self): pass
            def read_until(self, *args, **kwargs): return b''
            def write(self, packet): self.writes.append(packet)
            def flush(self): pass

            def readline(self):
                self.sequence += 1
                n = self.sequence
                rows = {
                    'A138': [n, 0x4303, n * 48000, 0, 0, 0, 0, 0],
                    'C350': [n, 0x55490473, 0, 0, 0x43505531, 0x50415353, n, 0],
                    'K138': [n, 0, (32767 << 16) | (2 << 3), 0, 0, 0, 0, 0],
                    'E138': [n, 128 << 18, 1 << 20, 0, 0, 0, n, 0x43545231],
                    'P138': [n, 0, 0, 0, 0, n, 0, 0],
                }
                if fault == 'cpu': rows['C350'][7] = 1
                if fault == 'ddr': rows['A138'][1] = 3
                if fault == 'cadence': rows['A138'][2] = n * 44100
                if fault == 'stopped': rows['A138'][2] = 42
                if fault == 'input': rows['K138'][3] = 1
                if fault == 'health': rows['A138'][3] = 1
                if fault in rows: del rows[fault]
                raw = bytearray()
                for kind, words in rows.items():
                    crc = binascii.crc_hqx(struct.pack('<8I', *words), 0xffff)
                    if fault == 'crc' and kind == 'A138' and n == 1: crc ^= 1
                    raw.extend((kind + ' ' + ''.join(f'{word:08X} ' for word in words) + f'{crc:04X}\r\n').encode())
                if model is not None and (not late_model or self.writes):
                    raw.extend(f'B138 00000000 00000000 00000000 {model << 2:08X}\r\n'.encode())
                return bytes(raw)

        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            output = Path(directory) / 'capture.json'
            argv = ['capture_scope_smoke.py', '--seconds', '3', '--output', str(output), *exercises]
            if disabled: argv.append('--recognition-disabled')
            port = Port()
            ticks = itertools.count()
            stack.enter_context(patch.object(smoke.serial, 'Serial', return_value=port, create=True))
            stack.enter_context(patch.object(smoke.time, 'monotonic', side_effect=lambda: next(ticks) * 0.1))
            stack.enter_context(patch.object(sys, 'argv', argv))
            stack.enter_context(patch('builtins.print'))
            if exercise_failure:
                stack.enter_context(patch.object(smoke, 'wait_for_controls', side_effect=RuntimeError(exercise_failure)))
            elif exercises:
                stack.enter_context(patch.object(smoke, 'wait_for_controls', return_value={}))
                def snapshot(pump, *_args, **_kwargs):
                    pump(0.3)
                    return (0, 0)
                stack.enter_context(patch.object(smoke, 'wait_for_snapshot', side_effect=snapshot))
            try:
                smoke.main()
            except SystemExit as exc:
                self.assertEqual(exc.code, 1)
            return json.loads(output.read_text())

    def test_default_still_requires_ready_model_reports(self):
        ready = self.capture(model=14)
        self.assertTrue(ready['passed'])
        self.assertEqual(ready['tests']['startup_cpu_audio_ddr_model'], 'passed')
        for model, error in [(None, 'insufficient valid records: B138'),
                             (0, 'CNN model readiness changed')]:
            with self.subTest(model=model):
                result = self.capture(model=model)
                self.assertFalse(result['passed'])
                self.assertIn(error, result['error'])

    def test_explicit_disabled_requires_no_model_reports(self):
        result = self.capture(disabled=True)
        self.assertTrue(result['passed'])
        self.assertTrue(result['recognition_disabled'])
        self.assertEqual(result['tests']['recognition'], 'disabled')
        self.assertEqual(result['tests']['startup_cpu_audio_ddr'], 'passed')
        self.assertNotIn('startup_cpu_audio_ddr_model', result['tests'])
        self.assertEqual(result['model_statuses'], [])
        self.assertEqual(result['crc_valid_records']['B138'], 0)
        unexpected = self.capture(disabled=True, model=14)
        self.assertFalse(unexpected['passed'])
        self.assertIn('recognition disabled but B138/model reports observed', unexpected['error'])

    def test_disabled_retains_all_other_startup_integrity_and_health_gates(self):
        for fault in ['A138', 'C350', 'K138', 'E138', 'P138', 'cpu', 'ddr',
                      'cadence', 'stopped', 'input', 'health', 'crc']:
            with self.subTest(fault=fault):
                result = self.capture(disabled=True, fault=fault)
                self.assertFalse(result['passed'], result)
                self.assertIn('error', result)

    def test_disabled_does_not_bypass_control_or_polyphony_exercises(self):
        for exercise in ['--exercise-controls', '--exercise-polyphony']:
            with self.subTest(exercise=exercise):
                result = self.capture(disabled=True, exercises=[exercise], exercise_failure='exercise gate reached')
                self.assertFalse(result['passed'])
                self.assertEqual(result['error'], 'exercise gate reached')
                self.assertTrue(result['midi_control_commands'])

    def test_disabled_rejects_model_reports_arriving_during_exercises(self):
        result = self.capture(disabled=True, model=14, late_model=True, exercises=['--exercise-controls'])
        self.assertEqual(result['tests']['common_control_application'], 'passed')
        self.assertFalse(result['passed'])
        self.assertIn('recognition disabled but B138/model reports observed', result['error'])


if __name__ == '__main__':
    unittest.main()
