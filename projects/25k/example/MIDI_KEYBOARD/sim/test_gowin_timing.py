import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from gowin_timing import timing_passed


class GowinTimingAcceptance(unittest.TestCase):
    def report(self, debug=False):
        timing = {'setup_violated_endpoints': 0, 'hold_violated_endpoints': 0,
                  'setup_worst_slack_ns': 0.452, 'hold_worst_slack_ns': 0.190,
                  'recovery_worst_slack_ns': 0.729, 'removal_worst_slack_ns': 0.758,
                  'clocks': [{'name': 'clk_50mhz', 'constraint_mhz': 50.0, 'actual_fmax_mhz': 51.157},
                             {'name': 'clk_ulpi60', 'constraint_mhz': 60.002, 'actual_fmax_mhz': 66.093}]}
        if debug:
            timing['clocks'].append({'name': 'tck_pad_i', 'constraint_mhz': 20.0, 'actual_fmax_mhz': 75.456})
        return timing

    def test_default_requires_exact_two_board_clocks(self):
        self.assertTrue(timing_passed(self.report()))
        self.assertFalse(timing_passed(self.report(True)))

    def test_debug_requires_board_and_jtag_clocks(self):
        self.assertTrue(timing_passed(self.report(True), True))
        self.assertFalse(timing_passed(self.report(), True))

    def test_missing_or_unknown_clock_rejected(self):
        for debug in (False, True):
            timing = self.report(debug)
            timing['clocks'].pop(0)
            self.assertFalse(timing_passed(timing, debug))
            timing = self.report(debug)
            timing['clocks'][0]['name'] = 'unknown'
            self.assertFalse(timing_passed(timing, debug))

    def test_duplicate_clock_rejected(self):
        timing = self.report(True)
        timing['clocks'].append(copy.deepcopy(timing['clocks'][0]))
        self.assertFalse(timing_passed(timing, True))

    def test_every_clock_must_meet_its_requested_frequency(self):
        for index in range(3):
            with self.subTest(clock=index):
                timing = self.report(True)
                timing['clocks'][index]['actual_fmax_mhz'] = timing['clocks'][index]['constraint_mhz'] - 0.001
                self.assertFalse(timing_passed(timing, True))

    def test_clock_constraints_cannot_be_relaxed_or_replaced(self):
        for index in range(3):
            for change in (-1, 1):
                timing = self.report(True)
                timing['clocks'][index]['constraint_mhz'] += change
                self.assertFalse(timing_passed(timing, True))

    def test_every_slack_class_must_be_nonnegative(self):
        for kind in ('setup', 'hold', 'recovery', 'removal'):
            timing = self.report(True)
            timing[kind+'_worst_slack_ns'] = -0.001
            self.assertFalse(timing_passed(timing, True))
            del timing[kind+'_worst_slack_ns']
            self.assertFalse(timing_passed(timing, True))

    def test_endpoint_violations_rejected(self):
        for kind in ('setup', 'hold'):
            timing = self.report(True)
            timing[kind+'_violated_endpoints'] = 1
            self.assertFalse(timing_passed(timing, True))

    def test_nonfinite_numbers_rejected(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            timing = self.report(True)
            timing['setup_worst_slack_ns'] = value
            self.assertFalse(timing_passed(timing, True))
            timing = self.report(True)
            timing['clocks'][0]['actual_fmax_mhz'] = value
            self.assertFalse(timing_passed(timing, True))


if __name__ == '__main__':
    unittest.main()
