from pathlib import Path
import importlib.util
import json
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'capture_ddr_jtag', ROOT / 'reports/hdmi_usb3_20261025/capture_ddr_jtag.py')
CAPTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPTURE)


class DdrCaptureDecode(unittest.TestCase):
    def test_full_workstation_truncated_display_counters(self):
        sample = dict.fromkeys(CAPTURE.DISPLAY_COUNTER_SIGNALS, 0)
        sample.update({'reset_n': 1, 'memory_flags[0]': 1, 'video_diagnostics[9]': 1,
                       'video_diagnostics[32]': 1, 'video_diagnostics[65]': 1})
        sample.update({f'video_diagnostics[{bit + 96}]': int(bool(0xA5 & (1 << bit))) for bit in range(8)})
        decoded = CAPTURE.snapshot(sample, 'workstation-display-counters-16-v1')
        self.assertTrue(decoded['ddr_calibrated'])
        self.assertTrue(decoded['video_locked'])
        self.assertFalse(decoded['fetch_arbiter_or_shared_load_fault'])
        self.assertEqual(decoded['vblank_low2'], 1)
        self.assertEqual(decoded['rendered_frames_low2'], 2)
        self.assertEqual(decoded['underruns_low8'], 165)
        self.assertTrue(decoded['truncated_counters_wrap'])
        self.assertFalse(decoded['coherent_cross_domain_snapshot'])

    def test_full_workstation_counter_layout_rejected_before_board_access(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)
            signals = CAPTURE.DISPLAY_COUNTER_SIGNALS.copy()
            signals[-1] = 'video_diagnostics[104]'
            (candidate / 'inputs.json').write_text(json.dumps({
                'full_workstation': True, 'signals': signals,
                'signal_schema': 'workstation-display-counters-16-v1'}))
            with self.assertRaisesRegex(ValueError, 'unexpected full-workstation counter observer layout'):
                CAPTURE.capture(candidate, 1)
            self.assertFalse((candidate / 'jtag_capture_20261026_01').exists())

    def test_full_workstation_memory_and_video_flags(self):
        sample = dict.fromkeys(CAPTURE.WORKSTATION_SIGNALS, 0)
        sample['reset_n'] = 1
        sample.update({f'memory_flags[{bit}]': int(bool(0xCB & (1 << bit))) for bit in range(8)})
        sample.update({f'video_diagnostics[{bit + 8}]': int(bool(0x2F & (1 << bit))) for bit in range(6)})
        decoded = CAPTURE.snapshot(sample, 'workstation-memory-video-16-v1')
        self.assertEqual(decoded['memory_flags_hex'], '0xCB')
        self.assertTrue(decoded['memory_flags']['ddr_calibrated'])
        self.assertTrue(decoded['memory_flags']['bist_done'])
        self.assertTrue(decoded['memory_flags']['front_valid'])
        self.assertFalse(decoded['memory_flags']['bist_failed'])
        self.assertTrue(decoded['video_flags']['scanout_reset_released'])
        self.assertFalse(decoded['video_flags']['serializer_reset_asserted'])

    def test_full_workstation_layout_rejected_before_board_access(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)
            (candidate / 'inputs.json').write_text(json.dumps({
                'full_workstation': False, 'signals': CAPTURE.WORKSTATION_SIGNALS,
                'signal_schema': 'workstation-memory-video-16-v1'}))
            with self.assertRaisesRegex(ValueError, 'unexpected full-workstation observer layout'):
                CAPTURE.capture(candidate, 1)
            self.assertFalse((candidate / 'jtag_capture_20261026_01').exists())

    def test_official_reference_raw_sample(self):
        sample = dict.fromkeys(CAPTURE.OFFICIAL_SIGNALS, 0)
        sample.update(pll_lock=1, init_calib_complete=1, rstni=1)
        sample['error_int1[9]'] = 1
        sample['led_cnt[7]'] = 1
        decoded = CAPTURE.snapshot(sample, 'official-ddr-reference-32-v1')
        self.assertTrue(decoded['raw_controls']['init_calib_complete'])
        self.assertEqual(decoded['raw_error_word'], 512)
        self.assertEqual(decoded['raw_read_count_low8'], 128)
        self.assertFalse(decoded['coherent_cross_domain_snapshot'])

    def test_official_reference_layout_rejected_before_board_access(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)
            signals = CAPTURE.OFFICIAL_SIGNALS.copy()
            signals[-1] = 'unexpected'
            (candidate / 'inputs.json').write_text(json.dumps({
                'full_workstation': False, 'signals': signals,
                'signal_schema': 'official-ddr-reference-32-v1'}))
            with self.assertRaisesRegex(ValueError, 'unexpected official DDR reference layout'):
                CAPTURE.capture(candidate, 1)
            self.assertFalse((candidate / 'jtag_capture_20261026_01').exists())

    def test_twenty_bit_status_and_clock(self):
        sample = {f'status_sync[{bit}]': int(bool(3 & (1 << bit))) for bit in range(8)}
        sample.update({f'ui_gray_sync[{bit}]': int(bool(0xFD & (1 << bit))) for bit in range(8)})
        sample.update({'u_memory/' + name: value for name, value in (
            ('controller_rst_n', 1), ('controller_reset', 0),
            ('qualified_lock', 1), ('pll_stop_3', 1))})
        decoded = CAPTURE.snapshot(sample)
        self.assertEqual(decoded['status_hex'], '0x03')
        self.assertEqual(decoded['ui_gray_hex'], '0xFD')
        self.assertTrue(decoded['flags']['pll_locked'])
        self.assertFalse(decoded['flags']['calibrated'])
        self.assertEqual(decoded['raw_controls']['controller_reset'], 0)
        self.assertEqual(decoded['training_signals'], {})

    def test_training_sample_without_gray_or_raw_controls(self):
        sample = {f'status_sync[{bit}]': int(bool(0x1F & (1 << bit))) for bit in range(8)}
        state = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_ddr_init/init_state.INIT_DONE'
        sample[state] = 1
        decoded = CAPTURE.snapshot(sample)
        self.assertTrue(decoded['flags']['calibrated'])
        self.assertTrue(decoded['flags']['bist_done'])
        self.assertEqual(decoded['training_signals'], {state: 1})
        self.assertNotIn('ui_gray_hex', decoded)
        self.assertEqual(decoded['raw_controls'], {})

    def test_unknown_training_schema_rejected_before_board_access(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)
            signals = [f'status_sync[{bit}]' for bit in reversed(range(8))]
            signals.extend(f'invalid_{index}' for index in range(24))
            (candidate / 'inputs.json').write_text(json.dumps({
                'full_workstation': False, 'signals': signals,
                'signal_schema': 'unrecognized'}))
            with self.assertRaisesRegex(ValueError, 'unexpected DDR training schema'):
                CAPTURE.capture(candidate, 1)
            self.assertFalse((candidate / 'jtag_capture_20261026_01').exists())


if __name__ == '__main__':
    unittest.main()
