"""The M TF menu must retain real CDC constraints without restoring CNN."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_demo_policy as demo
from tools import workstation_recognition_policy as recognition
from tools import workstation_profile as profiles


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


if __name__ == '__main__':
    unittest.main()
