import pathlib
import sys
import unittest

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from input_profiles import TOUCH_PORTS, panel_defines, remove_touch_constraints, select_panel


class InputProfilesTest(unittest.TestCase):
    def test_two_complete_profiles_and_alias(self):
        self.assertEqual(select_panel(), 'touch')
        self.assertEqual(select_panel('touch'), 'touch')
        self.assertEqual(select_panel('pluck'), 'pluck')
        self.assertEqual(select_panel(pluck_alias=True), 'pluck')
        self.assertEqual(panel_defines('touch'), [])
        self.assertEqual(panel_defines('pluck'), ['MIDI_PLUCK_ADC', 'MIDI_PLUCK_ONLY'])

    def test_conflicts_fail_before_build(self):
        for requested, alias, probe in [('touch', True, False), ('touch', False, True),
                                         ('pluck', False, True), (None, True, True), ('auto', False, False)]:
            with self.assertRaises(ValueError):
                select_panel(requested, alias, probe)

    def test_only_touch_constraints_are_removed(self):
        for suffix, expected in [('cst', 10), ('sdc', 5)]:
            original = (PROJECT / 'constraints' / ('midi_keyboard.' + suffix)).read_text()
            adapted, removed = remove_touch_constraints(original, suffix)
            self.assertEqual(len(removed), expected)
            self.assertTrue(all(not any(port in line for port in TOUCH_PORTS) for line in adapted.splitlines()
                                if line.startswith(('IO_LOC', 'IO_PORT', 'set_false_path'))))
            self.assertEqual(adapted + ''.join(line + '\n' for line in removed),
                             ''.join(line + '\n' for line in original.splitlines() if line not in removed) +
                             ''.join(line + '\n' for line in removed))
            for anchor in removed:
                with self.assertRaises(ValueError):
                    remove_touch_constraints(original.replace(anchor, ''), suffix)
                with self.assertRaises(ValueError):
                    remove_touch_constraints(original + anchor + '\n', suffix)


if __name__ == '__main__':
    unittest.main()
