"""Role retirement must keep live timing members and reject altered evidence."""
from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_demo_policy import adapt_constraints, verify_constraints, _adapt


class DemoConstraintPolicy(unittest.TestCase):
    def test_m_core_retires_tf_and_keeps_usb_in_mixed_queries(self):
        source = ('create_clock -name clk_50m -period 20 [get_ports {clk_50m}]\n'
            'set_false_path -to [get_pins {u_bluetooth/uart/meta/D u_native_usb/input_owner/meta/D}]\n'
            'set_max_delay 10 -from [get_regs {u_ble_pcm_cdc/held_data*}] '
            '-to [get_regs {u_ble_pcm_cdc/destination_data*}]\n'
            'set_max_delay 13.020 -to [get_pins {u_tf_audio/frames/meta/D}]\n')
        selected, evidence = adapt_constraints(source, 'M')
        self.assertIn('[get_pins {u_native_usb/input_owner/meta/D}]', selected)
        self.assertNotIn('u_tf_audio/', selected)
        self.assertNotIn('u_bluetooth/', selected)
        self.assertNotIn('u_ble_pcm_cdc/', selected)
        self.assertEqual(source, verify_constraints(selected, evidence, 'M'))
        old, old_evidence = _adapt(source, 'M', legacy=False, v3=True)
        self.assertIn('13.020 -to [get_pins {u_tf_audio/frames/meta/D}]', old)
        self.assertEqual(source, verify_constraints(old, old_evidence, 'M'))

    def test_m_tf_retirement_keeps_complete_effect_display_and_output_constraints(self):
        retired = ('u_tf_audio/frames/meta/D', 'u_tf_control_cdc/req_meta/D',
                   'u_audio_command_buffer/pending/D', 'u_playlist_bridge/fifo/meta/D',
                   'tf_format_meta50_s/D', 'tf_source_meta50_s/D')
        live = ('u_native_usb/input_owner/meta/D', 'u_video/u_runtime_display/meta/D',
                'u_managed/runtime/service/workstation/runtime_effects.effects/meta/D',
                'u_managed/runtime/serializer/meta/D')
        source = 'set_max_delay 13.020 -to [get_pins {' + ' '.join((*retired, *live)) + '}]\n'
        selected, evidence = adapt_constraints(source, 'M')
        self.assertEqual(selected, 'set_max_delay 13.020 -to [get_pins {' + ' '.join(live) + '}]\n')
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

    def test_w_binds_actual_generate_scopes_and_async_preset_only(self):
        source = ('set_max_delay 10.000 -from [get_regs {u_managed/pcm_apb/commands/request_held*}] '
            '-to [get_regs {u_managed/pcm_apb/commands/request_local*}]\n'
            'set_false_path -to [get_pins {u_managed/runtime/cpu_pcm/switch_inhibit_compute*/CLEAR '
            'u_managed/runtime/pcm_hold_serial*/CLEAR '
            'u_managed/runtime/cpu_pcm/session/live_o*/CLEAR}]\n'
            'set_false_path -to [get_pins {u_managed/pcm_apb/commands/p_release*/CLEAR '
            'u_managed/pcm_apb/commands/request_local*/CLEAR}]\n')
        selected, evidence = adapt_constraints(source, 'W')
        self.assertIn('set_max_delay 10.000 -from [get_regs {u_managed/pcm_apb.commands/request_held*}]', selected)
        self.assertIn('cpu_pcm.switch_inhibit_compute*/PRESET', selected)
        self.assertIn('pcm_hold_serial*/PRESET', selected)
        self.assertIn('cpu_pcm.session/live_o*/CLEAR', selected)
        self.assertIn('pcm_apb.commands/request_local*/CLEAR', selected)
        self.assertNotIn('p_release', selected)
        self.assertEqual(source, verify_constraints(selected, evidence, 'W'))
        changed = copy.deepcopy(evidence)
        changed['changes'][0]['rebound_selectors'][0]['selected'] += '*'
        with self.assertRaises(ValueError):
            verify_constraints(selected, changed, 'W')
        self.assertEqual(source, adapt_constraints(source, 'M')[0])

    def test_old_frozen_candidate_evidence_replays_its_original_policy(self):
        source = ('set_false_path -to [get_pins {u_display_push_cdc/req_meta/D '
                  'u_managed/pcm_apb/commands/request_local*/CLEAR}]\n')
        selected, evidence = _adapt(source, 'W', legacy=True)
        self.assertEqual(source, selected)
        self.assertEqual(source, verify_constraints(selected, evidence, 'W'))
        self.assertNotEqual(source, adapt_constraints(source, 'W')[0])

    def test_only_two_unused_w_diagnostics_retire_and_previous_v2_replays(self):
        source = ('set_max_delay 10.000 -from [get_regs {recording_ble_store/status_payload*}] '
            '-to [get_pins {recording_ble_store/failure_code_o_*_s*/D '
            'recording_ble_store/start_done_o_s*/CE recording_ble_store/clear_done_o_s*/D '
            'recording_ble_store/channel_fault_o_s*/CE recording_ble_store/committed_frames_o_*_s*/D}]\n')
        selected, evidence = adapt_constraints(source, 'W')
        self.assertNotIn('failure_code_o_', selected)
        self.assertNotIn('start_done_o_', selected)
        for live in ('clear_done_o_', 'channel_fault_o_', 'committed_frames_o_'):
            self.assertIn(live, selected)
        self.assertEqual(source, verify_constraints(selected, evidence, 'W'))
        old, old_evidence = _adapt(source, 'W', legacy=False, previous=True)
        self.assertEqual(old, source)
        self.assertEqual(source, verify_constraints(old, old_evidence, 'W'))
        self.assertEqual(source, adapt_constraints(source, 'M')[0])


if __name__ == '__main__':
    unittest.main()
