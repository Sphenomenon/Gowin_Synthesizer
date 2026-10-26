from pathlib import Path
import runpy
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'reports/hdmi_usb3_20261025/decode_workstation_jtag.py'


class WorkstationJtagDecode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = runpy.run_path(str(ADAPTER), run_name='workstation_jtag_decode_test')

    def capture(self):
        signals = self.adapter['SIGNALS']
        values = dict.fromkeys(signals, 0)
        values.update(reset_n=1, debug_uart_tx_d=1)
        for prefix, low, width, word in (('memory_flags', 0, 8, 0xCB),
                                         ('video_diagnostics', 8, 6, 0x2F),
                                         ('video_diagnostics', 16, 16, 1450),
                                         ('video_diagnostics', 32, 8, 254),
                                         ('video_diagnostics', 64, 8, 129),
                                         ('video_diagnostics', 96, 8, 0),
                                         ('u_runtime/flags_sync', 0, 2, 3),
                                         ('u_runtime/sample_sync', 0, 4, 12)):
            for bit in range(low, low + width):
                values[f'{prefix}[{bit}]'] = (word >> (bit - low)) & 1
        header = 'Data:\ntime unit: us, ' + ', '.join(signals) + ',\n'
        rows = []
        for index in range(1024):
            values['u_runtime/sample_sync[0]'] = index & 1
            rows.append(str(index) + ', ' + ', '.join(str(values[name]) for name in signals) + ',\n')
        return header + ''.join(rows)

    def test_schema_bit_order_flags_counters_and_gray_transitions(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'capture.csv'
            source.write_text(self.capture())
            result = self.adapter['decode'](source)
            self.assertEqual(result['samples'], 1024)
            self.assertTrue(result['reset_released_throughout'])
            self.assertEqual(result['first']['memory_flags_hex'], '0xCB')
            self.assertTrue(result['first']['memory_flags']['front_valid'])
            self.assertFalse(result['first']['memory_flags']['bist_failed'])
            self.assertEqual(result['first']['video_flags_hex'], '0x2F')
            self.assertEqual(result['first']['pixel_blocks_per_window'], 1450)
            self.assertEqual(result['first']['vblank_low8'], 254)
            self.assertEqual(result['first']['rendered_frames_low8'], 129)
            self.assertEqual(result['first']['sample_gray_low4'], 12)
            self.assertEqual(result['last']['sample_gray_low4'], 13)
            self.assertEqual(result['signals']['u_runtime/sample_sync[0]']['transitions'], 1023)
            self.assertFalse(result['root_cause_confirmed'])

    def test_wrong_schema_unknown_bits_and_truncated_capture_are_rejected(self):
        capture = self.capture()
        for changed, message in (
            (capture.replace('memory_flags[7]', 'other_flags[7]', 1), '64-bit observation'),
            (capture.replace('0, 1,', '0, X,', 1), 'non-binary'),
            ('\n'.join(capture.splitlines()[:-1]) + '\n', '1024'),
            (capture.replace('\n1, ', '\n5, ', 1), 'contiguous'),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'bad.csv'
                source.write_text(changed)
                with self.assertRaisesRegex(ValueError, message):
                    self.adapter['decode'](source)


if __name__ == '__main__':
    unittest.main()
