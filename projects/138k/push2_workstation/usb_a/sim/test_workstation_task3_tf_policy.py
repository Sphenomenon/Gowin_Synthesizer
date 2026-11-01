"""The M TF menu must retain real CDC constraints without restoring CNN."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_demo_policy as demo
from tools import workstation_recognition_policy as recognition
from tools import workstation_profile as profiles
from tools import workstation_task3_tf_direct as direct


class Task3TFPolicy(unittest.TestCase):
    def source(self):
        return ('create_clock -period 20 [get_ports {clk_50m}]\n' +
                ''.join(row + '\n' for row in recognition.RETIRED_LINES) +
                'set_max_delay 13.020 -to [get_pins {u_tf_audio/frames/meta/D '
                'u_tf_control_cdc/req_meta/D u_playlist_bridge/fifo/meta/D '
                'u_bluetooth/meta/D u_video/meta/D}]\n')

    def test_menu_keeps_every_existing_song_mailbox_bound(self):
        selected, evidence = recognition.adapt_constraints(self.source(), False, tf_menu_enabled=True)
        self.assertEqual(len(evidence['retired']), 16)
        for row in recognition.RETIRED_LINES:
            self.assertEqual(row in selected, 'u_song_command_cdc/' in row)
        recognition.verify_adaptation(selected, evidence, False, tf_menu_enabled=True)
        with self.assertRaises(ValueError):
            recognition.verify_adaptation(selected, evidence, False)
        with self.assertRaises(ValueError):
            recognition.verify_adaptation(selected.replace('20.000', '21.000'), evidence,
                                          False, tf_menu_enabled=True)

    def test_tf_survives_role_retirement_and_cnn_stays_absent(self):
        source, cnn = recognition.adapt_constraints(self.source(), False, tf_menu_enabled=True)
        selected, evidence = demo.adapt_constraints(source, 'M', tf_playback_enabled=True)
        self.assertEqual(demo.verify_constraints(selected, evidence, 'M', tf_playback_enabled=True), source)
        for scope in ('u_tf_audio/', 'u_tf_control_cdc/', 'u_playlist_bridge/', 'u_video/', 'u_song_command_cdc/'):
            self.assertIn(scope, selected)
        for scope in ('u_bluetooth/', 'u_music/', 'u_score_push_cdc/'):
            self.assertNotIn(scope, selected)
        with self.assertRaises(ValueError):
            demo.verify_constraints(selected, evidence, 'M')
        changed = copy.deepcopy(evidence)
        changed['policy'] = demo.POLICY
        with self.assertRaises(ValueError):
            demo.verify_constraints(selected, changed, 'M', tf_playback_enabled=True)
        with self.assertRaises(ValueError):
            demo.adapt_constraints(source, 'W', tf_playback_enabled=True)

    def test_menu_cannot_silently_waive_a_changed_or_missing_bound(self):
        for row in recognition.RETIRED_LINES:
            if 'u_song_command_cdc/' in row:
                with self.subTest(row=row), self.assertRaises(ValueError):
                    recognition.adapt_constraints(self.source().replace(row, row + ' '),
                                                  False, tf_menu_enabled=True)

    def test_new_profile_does_not_alias_demo_or_claim_remote_features(self):
        spec = profiles.specification(profiles.TASK3_M_TF_NAME)
        self.assertNotEqual(spec['provider'], profiles.specification(profiles.M_DEMO_NAME)['provider'])
        metadata = profiles.recognition_metadata({'name': profiles.TASK3_M_TF_NAME})
        self.assertTrue(metadata['tf_song_menu_available'])
        self.assertFalse(metadata['music_analysis_enabled'])
        self.assertFalse(metadata['cnn_score_follow_enabled'])
        self.assertFalse(metadata['recognition_menu_available'])
        self.assertEqual(spec['configuration']['tf_policy'], 'local_tf_ddr_with_independent_menu_v1')

    def test_direct_cdc_replaces_only_exact_legacy_subset(self):
        rows = direct.legacy(ROOT)['lines']
        before = ('create_clock -period 20 [get_ports {clk_50m}]\n' +
                  ''.join(old + '\n' for old, _ in direct.root_constraint_mappings()) + ''.join(rows[:16]) +
                  ''.join(row + '\n' for row in direct.root_display_retired_constraints()) +
                  'set_max_delay 2.000 -from [get_pins {live_source/Q}] -to [get_pins {live_sink/D}]\n' +
                  ''.join(rows[16:]))
        selected, evidence = direct.adapt_constraints(ROOT, before)
        self.assertEqual(direct.restore_constraints(ROOT, selected, evidence), before)
        self.assertIn('live_source/Q', selected)
        self.assertNotIn('u_tf_audio/path/', selected)
        self.assertNotIn('u_tf_audio/startup_memory', selected)
        self.assertIn('u_tf_audio/source_quiesce_level_s[0-9]*/Q', selected)
        self.assertIn('u_managed/runtime/g_direct_tf.tail/fence_gray_', selected)
        self.assertIn('u_usb_pll/u_pll_init/enable_r_0_s[0-9]*/Q', selected)
        self.assertIn('u_tf_audio/receipt_seen_s[0-9]*/Q', selected)
        self.assertNotIn('u_runtime/u_performance_cdc/source_release_', selected)
        for row in direct.root_display_retired_constraints():
            self.assertNotIn(row, selected)
        self.assertEqual(evidence['constraint_revision'], 2)
        self.assertFalse(evidence['non_tf_constraints_unchanged'])
        self.assertFalse(evidence['physical_cdc_verified'])
        for row in rows:
            with self.subTest(row=row[:80]), self.assertRaises(ValueError):
                direct.adapt_constraints(ROOT, before.replace(row, row.rstrip() + ' \n'))
        with self.assertRaises(ValueError):
            direct.adapt_constraints(ROOT, before + 'set_false_path -to [get_pins {u_tf_audio/unknown/D}]\n')
        with self.assertRaises(ValueError):
            direct.restore_constraints(ROOT, selected.replace('13.020', '99.000'), evidence)
        for old, new in direct.root_constraint_mappings():
            with self.subTest(anchor=old), self.assertRaises(ValueError):
                direct.adapt_constraints(ROOT, before.replace(old + '\n', old + ' \n'))
        for old in direct.root_display_retired_constraints():
            with self.subTest(display_anchor=old[:80]), self.assertRaises(ValueError):
                direct.adapt_constraints(ROOT, before.replace(old + '\n', old + ' \n'))
        historical, original = direct.adapt_constraints(ROOT, before, revision=1)
        self.assertEqual(direct.restore_constraints(ROOT, historical, original), before)
        self.assertTrue(original['non_tf_constraints_unchanged'])
        self.assertNotIn('constraint_revision', original)

    def test_direct_profile_is_explicit_and_separate(self):
        spec = profiles.specification(profiles.TASK3_M_DIRECT_NAME)
        self.assertTrue(spec['tf_direct_enabled'])
        self.assertTrue(spec['tf_menu_enabled'])
        self.assertFalse(spec['recognition_enabled'])
        self.assertEqual(spec['configuration']['tf_policy'], direct.POLICY)
        for old in (profiles.TASK3_M_TF_NAME, profiles.M_DEMO_NAME, profiles.W_DEMO_NAME):
            self.assertFalse(profiles.specification(old).get('tf_direct_enabled', False))

    def test_real_root_reset_is_selected_only_by_the_direct_provider(self):
        from tools.workstation_runtime_cdc import prepared_ble_reset_policy
        with tempfile.TemporaryDirectory() as temp:
            stage=Path(temp)
            for relative in ('rtl/workstation/gw138k_push_workstation_top.v',
                             'rtl/workstation/workstation_runtime_controlled.sv',
                             'rtl/workstation/workstation_profile_task3_m_direct_tf.sv'):
                target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/relative).read_bytes())
            project=stage/'Prj1.gprj'
            project.write_text('<Project><FileList><File path="rtl/workstation/workstation_profile_task3_m_direct_tf.sv" enable="1" /></FileList></Project>')
            selected=prepared_ble_reset_policy(stage)
            self.assertEqual(selected['root_common_reset'],'reset_n')
            self.assertTrue(selected['physical_root_reset_audit_required'])
            top=stage/'rtl/workstation/gw138k_push_workstation_top.v'
            original=top.read_text()
            top.write_text(original.replace('.common_reset_ni(runtime_common_reset_n)',
                                            '.common_reset_ni(runtime_reset_n)'))
            with self.assertRaises(ValueError):prepared_ble_reset_policy(stage)
            top.write_text(original)
            project.write_text('<Project><FileList /></Project>')
            legacy=prepared_ble_reset_policy(stage)
            self.assertEqual(legacy['mode'],'separate-common-own-ble-release')
            self.assertNotIn('root_common_reset',legacy)


if __name__ == '__main__':
    unittest.main()
