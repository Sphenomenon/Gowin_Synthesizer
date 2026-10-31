"""Role retirement must keep live timing members and reject altered evidence."""
from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_demo_policy import adapt_constraints, verify_constraints


class DemoConstraintPolicy(unittest.TestCase):
    def test_m_keeps_tf_and_usb_in_mixed_queries(self):
        source = ('create_clock -name clk_50m -period 20 [get_ports {clk_50m}]\n'
            'set_false_path -to [get_pins {u_bluetooth/uart/meta/D u_native_usb/input_owner/meta/D}]\n'
            'set_max_delay 10 -from [get_regs {u_ble_pcm_cdc/held_data*}] '
            '-to [get_regs {u_ble_pcm_cdc/destination_data*}]\n'
            'set_max_delay 13.020 -to [get_pins {u_tf_audio/frames/meta/D}]\n')
        selected, evidence = adapt_constraints(source, 'M')
        self.assertIn('[get_pins {u_native_usb/input_owner/meta/D}]', selected)
        self.assertIn('13.020 -to [get_pins {u_tf_audio/frames/meta/D}]', selected)
        self.assertNotIn('u_bluetooth/', selected)
        self.assertNotIn('u_ble_pcm_cdc/', selected)
        self.assertEqual(source, verify_constraints(selected, evidence, 'M'))

    def test_w_keeps_ble_effects_and_clock_limits(self):
        source = ('set_false_path -to [get_pins {u_tf_control_cdc/req_meta/D u_runtime/performance/req_meta/D}]\n'
            'set_max_delay 2.000 -to [get_pins {u_bluetooth/uart/meta/D}]\n'
            'set_max_delay 13.020 -to [get_pins {u_managed/runtime/bridge/reply/D}]\n'
            'set_false_path -to [get_pins {u_recording/old/D}]\n')
        selected, evidence = adapt_constraints(source, 'W')
        self.assertIn('[get_pins {u_runtime/performance/req_meta/D}]', selected)
        self.assertIn('2.000 -to [get_pins {u_bluetooth/uart/meta/D}]', selected)
        self.assertIn('13.020 -to [get_pins {u_managed/runtime/bridge/reply/D}]', selected)
        self.assertNotIn('u_recording/', selected)
        self.assertEqual(source, verify_constraints(selected, evidence, 'W'))

    def test_changed_live_member_and_retirement_evidence_fail(self):
        source = 'set_false_path -to [get_pins {u_ble_pcm_cdc/req_meta/D u_video/req_meta/D}]\n'
        selected, evidence = adapt_constraints(source, 'M')
        with self.assertRaises(ValueError):
            verify_constraints(selected.replace('u_video/', 'u_other/'), evidence, 'M')
        changed = copy.deepcopy(evidence)
        changed['changes'][0]['removed_selectors'].append('u_video/req_meta/D')
        with self.assertRaises(ValueError):
            verify_constraints(selected, changed, 'M')
        with self.assertRaises(ValueError):
            verify_constraints(selected, evidence, 'W')

    def test_no_general_retirement_mode(self):
        with self.assertRaises(ValueError):
            adapt_constraints('', 'unknown')


if __name__ == '__main__':
    unittest.main()
