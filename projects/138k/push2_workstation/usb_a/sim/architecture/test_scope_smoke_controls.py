import itertools
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
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


if __name__ == '__main__':
    unittest.main()
