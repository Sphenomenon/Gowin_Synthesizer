#!/usr/bin/env python3
"""Structural resolution must never substitute naming compatibility for topology."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from workstation_serializer_startup_audit import logic_driver


class LogicResolverTests(unittest.TestCase):
    def fixture(self, suffix='pll_stop_d_s0'):
        name = 'phy/' + suffix
        cells = {name: ('LUT1', {'I0': 'stop2', 'F': 'gate'}),
                 'phy/stop2': ('DFFCE', {'D': 'stop1', 'Q': 'stop2'})}
        return cells, {(name, 'INIT'): "2'h1"}, name

    def test_legacy_and_new_names_require_same_structure(self):
        for suffix in ('pll_stop_s0', 'pll_stop_d_s0', 'unrelated_generated_name'):
            cells, parameters, name = self.fixture(suffix)
            self.assertEqual(logic_driver(cells, parameters, 'gate', 'LUT1', {'I0': 'stop2'}, 'phy', "2'h1"), name)

    def test_reject_polarity_even_with_historical_name(self):
        cells, parameters, name = self.fixture('pll_stop_s0')
        parameters[(name, 'INIT')] = "2'h2"
        with self.assertRaisesRegex(AssertionError, 'polarity'):
            logic_driver(cells, parameters, 'gate', 'LUT1', {'I0': 'stop2'}, 'phy', "2'h1")

    def test_reject_other_source_and_multiple_drivers(self):
        cells, parameters, name = self.fixture()
        for mode in ('wrong_input', 'second_driver'):
            changed = copy.deepcopy(cells)
            if mode == 'wrong_input':
                changed[name][1]['I0'] = 'bypass'
            else:
                changed['phy/second'] = ('INV', {'I': 'bypass', 'O': 'gate'})
            with self.assertRaises(AssertionError):
                logic_driver(changed, parameters, 'gate', 'LUT1', {'I0': 'stop2'}, 'phy', "2'h1")

    def test_reject_type_or_extra_input(self):
        cells, parameters, name = self.fixture()
        for kind, pins in [('INV', {'I': 'stop2', 'O': 'gate'}),
                           ('LUT1', {'I0': 'stop2', 'I1': 'unexpected', 'F': 'gate'})]:
            changed = copy.deepcopy(cells); changed[name] = (kind, pins)
            with self.assertRaises(AssertionError):
                logic_driver(changed, parameters, 'gate', 'LUT1', {'I0': 'stop2'}, 'phy', "2'h1")


if __name__ == '__main__':
    unittest.main()
