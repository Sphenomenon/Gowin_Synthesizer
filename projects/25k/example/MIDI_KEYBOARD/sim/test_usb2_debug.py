import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'tools'))
from capture_usb2_debug import validate_manifest
from decode_usb2_debug import BUS, GAO_ID, PROBE_ID, decode, phy_fields, load_config


class Usb2DebugTools(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def capture(self, count=128, bus=BUS, oversized=False):
        path = self.root/'capture.csv'
        phy = (0x12 << 24) | (5 << 21) | (1 << 14) | (1 << 13) | 0x43
        payloads = [phy & 0xffffff, (0x12 << 16) | 3, (4 << 8) | 234, 0x55aa33]
        with path.open('w', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(['Data:'])
            writer.writerow(['time unit: ns', bus])
            for sample in range(count):
                page = (sample // 8) % 4
                value = (payloads[page] << 8) | (page << 6) | 0x3c | (((sample // 32) & 1) << 1) | (sample & 1)
                writer.writerow([sample*20, f'{1 << 32 if oversized else value:X}'])
        return path

    def test_coherent_pages_decode_phy_and_real_midi_counts(self):
        result = decode(self.capture())
        self.assertEqual(len(result['complete_page_cycles']), 4)
        self.assertEqual(result['sample_count'], 128)
        latest = result['latest']
        self.assertEqual((latest['boot_stage'], latest['phy_state'], latest['device_address']), (0x12, 5, 1))
        self.assertTrue(latest['boot_done'])
        self.assertFalse(latest['boot_error'])
        self.assertTrue(latest['online'] and latest['hs_active'] and latest['source_clock_alive'])
        self.assertEqual(latest['phy_clock_ticks_per_ms'], 234)
        self.assertEqual(latest['phy_clock_quantized_hz'], 59904000)
        self.assertEqual((latest['midi_tx_accepted_words16'], latest['midi_rx_accepted_words16']), (3, 4))

    def test_short_capture_rejected(self):
        with self.assertRaises(ValueError):
            decode(self.capture(count=127))

    def test_wrong_bus_rejected(self):
        with self.assertRaises(ValueError):
            decode(self.capture(bus='other[63:0]'))

    def test_oversized_status_rejected(self):
        with self.assertRaises(ValueError):
            decode(self.capture(oversized=True))

    def test_error_and_stopped_reset_flags(self):
        result = phy_fields((0x21 << 24) | (1 << 12) | (1 << 11))
        self.assertTrue(result['boot_error'] and result['protocol_reset'])
        self.assertFalse(result['boot_done'] or result['reset60_released'])

    def test_mismatched_cohort_never_forms_a_cycle(self):
        path = self.capture()
        rows = list(csv.reader(path.read_text().splitlines()))
        for index in range(10, len(rows), 32):
            rows[index][1] = f'{int(rows[index][1],16) ^ 2:X}'
        with path.open('w', newline='') as output:
            csv.writer(output).writerows(rows)
        self.assertIsNone(decode(path)['latest'])

    def test_wrong_marker_rejects_affected_cycle(self):
        path = self.capture()
        rows = list(csv.reader(path.read_text().splitlines()))
        for row in rows[26:34]:
            value = int(row[1], 16)
            row[1] = f'{value ^ 256:X}'
        with path.open('w', newline='') as output:
            csv.writer(output).writerows(rows)
        self.assertEqual(len(decode(path)['complete_page_cycles']), 3)

    def test_payload_change_rejects_affected_page_rotation(self):
        path = self.capture()
        rows = list(csv.reader(path.read_text().splitlines()))
        rows[10][1] = f'{int(rows[10][1],16) ^ 256:X}'
        with path.open('w', newline='') as output:
            csv.writer(output).writerows(rows)
        result = decode(path)
        self.assertEqual(len(result['complete_page_cycles']), 3)
        self.assertEqual(result['latest']['midi_tx_accepted_words16'], 3)

    def test_capture_config_has_independent_clock_and_distinct_identity(self):
        self.assertEqual(load_config(PROJECT/'config/usb2_debug.gao'), GAO_ID)
        config = self.root/'wrong.gao'
        config.write_text((PROJECT/'config/usb2_debug.gao').read_text().replace('midi_keyboard_top', 'usb2_device_top'))
        with self.assertRaises(ValueError):
            load_config(config)

    def test_probe_config_is_explicit_and_not_the_complete_keyboard(self):
        self.assertEqual(load_config(PROJECT/'config/usb2_probe.gao', probe=True), PROBE_ID)
        with self.assertRaises(ValueError):
            load_config(PROJECT/'config/usb2_probe.gao')
        with self.assertRaises(ValueError):
            load_config(PROJECT/'config/usb2_debug.gao', probe=True)

    def probe_capture(self):
        path = self.capture()
        rows = list(csv.reader(path.read_text().splitlines()))
        history = (0x3e << 24) | (0xf << 20) | (0xf << 16) | (255 << 8) | 0x41
        sources = [history, (2 << 24) | 180001, (3 << 24) | 180000,
                   (0x41 << 24) | 27, (0x9a << 24) | 17, (0xa5 << 24) | 13, (0x5f << 24) | 8]
        rows[1][1] = 'status_50mhz[255:0]'
        for index, row in enumerate(rows[2:]):
            page = (index // 8) % 4
            value = int(row[1],16)
            for lane, source in enumerate(sources, start=1):
                payloads = [source & 0xffffff, (source >> 24) << 16, 234, 0x55aa33]
                status = (payloads[page] << 8) | (page << 6) | 0x3c | (((index // 32) & 1) << 1) | (index & 1)
                value |= status << (32*lane)
            row[1] = f'{value:X}'
        with path.open('w', newline='') as output:
            csv.writer(output).writerows(rows)
        return path

    def test_probe_decodes_persistent_events_separately_from_current_state(self):
        path = self.probe_capture()
        latest = decode(path, probe=True)['latest']
        self.assertEqual(latest['device_address'], 1)
        self.assertEqual(latest['states_seen'], [1, 2, 3, 4, 5])
        self.assertEqual(latest['lines_seen'], [0, 1, 2, 3])
        self.assertTrue(latest['rxerror_seen'] and latest['txvalid_seen'] and latest['rxactive_seen'])
        self.assertEqual(latest['received_utmi_bytes_saturated8'], 255)
        self.assertEqual(latest['last_rxcmd'], 0x41)

    def test_probe_decodes_raw_and_wrapper_se0_and_separate_bus_counts(self):
        latest = decode(self.probe_capture(), probe=True)['latest']
        self.assertEqual((latest['raw_se0_max_cycles24'], latest['utmi_se0_max_cycles24']), (180001, 180000))
        self.assertEqual((latest['raw_se0_runs8'], latest['utmi_se0_runs8']), (2, 3))
        self.assertEqual(latest['utmi_se0_max_us_nominal60mhz'], 3000)
        self.assertEqual((latest['raw_rxcmd_count24'], latest['raw_phy_rx_bytes24'], latest['utmi_rx_bytes24']), (27, 17, 13))
        self.assertEqual((latest['last_phy_rx_byte'], latest['last_utmi_rx_byte'], latest['link_nxt_cycles24']), (0x9a, 0xa5, 8))
        self.assertEqual((latest['raw_line_state'], latest['monitored_utmi_line_state']), (1, 1))
        self.assertTrue(latest['raw_line_valid'] and latest['raw_se0_armed'] and latest['utmi_se0_armed'] and latest['protocol_active'])
        self.assertFalse(latest['statistics_snapshot_atomic_across_lanes'])

    def test_probe_rejects_old_width_and_incomplete_statistics_lane(self):
        with self.assertRaises(ValueError):
            decode(self.capture(bus='status_50mhz[63:0]'), probe=True)
        path = self.probe_capture()
        rows = list(csv.reader(path.read_text().splitlines()))
        for row in rows[2:]:
            row[1] = f'{int(row[1],16) ^ (1 << (224+8)):X}'
        with path.open('w', newline='') as output:
            csv.writer(output).writerows(rows)
        self.assertIsNone(decode(path, probe=True)['latest'])

    def manifest(self):
        bitstream = self.root/'candidate.fs'
        bitstream.write_text('//Part Number: GW5A-LV25MG121NC1/I0\n//UserCode: 0xC12528D6\n'
                             '//GAOCRC: '+GAO_ID+'\n//SecurityBit: OFF\n//CRCCheck: ON\n')
        record = {'passed': True, 'timing': {'passed': True}, 'configuration': {'usb2_debug': True},
                  'user_code': '0xC12528D6', 'sha256': {'config/usb2_debug.gao':
                  hashlib.sha256((PROJECT/'config/usb2_debug.gao').read_bytes()).hexdigest()},
                  'artifacts': [{'path': str(bitstream), 'sha256': hashlib.sha256(bitstream.read_bytes()).hexdigest()}]}
        manifest = self.root/'build.json'
        manifest.write_text(json.dumps(record))
        return manifest, bitstream, record

    def test_manifest_checks_identity_and_config(self):
        manifest, _, _ = self.manifest()
        self.assertEqual(validate_manifest(manifest, PROJECT/'config/usb2_debug.gao')['user_code'], '0xC12528D6')

    def test_changed_bitstream_rejected(self):
        manifest, bitstream, _ = self.manifest()
        bitstream.write_text(bitstream.read_text()+'changed\n')
        with self.assertRaises(ValueError):
            validate_manifest(manifest, PROJECT/'config/usb2_debug.gao')

    def test_non_debug_or_failed_timing_rejected(self):
        manifest, _, record = self.manifest()
        for key in ('timing', 'configuration'):
            changed = json.loads(json.dumps(record))
            changed[key] = {}
            manifest.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                validate_manifest(manifest, PROJECT/'config/usb2_debug.gao')


if __name__ == '__main__':
    unittest.main()
