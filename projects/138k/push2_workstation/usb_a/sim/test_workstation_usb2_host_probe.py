"""Checks for the headless, native-ULPI-clocked host probe."""

import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_usb2_host_probe as probe
from tools import workstation_usb2_hotplug as hotplug
from tools.stage_usb_firmware import sha


class HostProbe(unittest.TestCase):
    def capture_file(self, directory, count=1024, values=None, core=0):
        values = values or {}
        fields, signals = ((probe.FIELDS, probe.SIGNALS), (probe.CPU_FIELDS, probe.CPU_SIGNALS),
                           (probe.RECOVERY_FIELDS, probe.RECOVERY_SIGNALS))[core]
        bits = ''.join(f'{values.get(name, 0):0{width}b}' for name, _, width, *_ in fields)
        path = Path(directory) / 'capture.csv'
        with path.open('w') as stream:
            writer = csv.writer(stream)
            writer.writerow(['time unit: ns', *signals])
            for index in range(count):
                writer.writerow([index, *bits])
        return path

    def test_observer_uses_native_ulpi_clock_and_unique_identity(self):
        document = ElementTree.fromstring(probe.gao_configuration('C11029A1'))
        core = document.find('AoCore')
        self.assertEqual(core.get('sample_clock'), 'usb2_ulpi_clk_d')
        self.assertEqual(core.get('module_name'), hotplug.TOP)
        self.assertEqual(document.findtext('GAO_ID'), '29A1')
        self.assertEqual([entry.text for entry in core.findall('SignalList/Signal')], list(probe.SIGNALS))
        self.assertFalse(any('/cpu/' in signal or 'telemetry' in signal for signal in probe.SIGNALS))
        native_top = (probe.ROOT / 'rtl/workstation/workstation_usb2_hotplug_top.sv').read_text()
        self.assertIn('(* syn_keep = 1 *) wire traffic_enable;', native_top)

    def test_decoding_retains_failure_and_does_not_invent_enumeration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture_file(directory, values=dict(state_history=(1 << 7) | (1 << 18),
                                                           failure_history=1 << 3, received_peak=123,
                                                           high_speed=1, connected=1))
            result = probe.decode_csv(path)
            self.assertEqual(result['states_seen'], [7, 18])
            self.assertEqual(result['failures_seen'], [3])
            self.assertEqual(result['last']['received_peak'], 123)
            self.assertFalse(result['enumeration_verified'])
            self.assertFalse(result['application_communication_verified'])

    def test_cpu_observer_uses_its_own_clock(self):
        document = ElementTree.fromstring(probe.gao_configuration('C11029A3'))
        cores = document.findall('AoCore')
        self.assertEqual([core.get('index') for core in cores], ['0', '1', '2'])
        self.assertEqual([core.get('sample_clock') for core in cores], ['usb2_ulpi_clk_d', 'usb_clk', 'usb2_ulpi_clk_d'])
        self.assertEqual([entry.text for entry in cores[1].findall('SignalList/Signal')], list(probe.CPU_SIGNALS))
        self.assertEqual([entry.text for entry in cores[2].findall('SignalList/Signal')], list(probe.RECOVERY_SIGNALS))

    def test_recovery_capture_retains_exit_cause_and_no_ep0_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture_file(directory, core=2, values=dict(recovery_count=9, recovery_aborts=9,
                recovery_exit_state=1, recovery_exit_ticks=90000, recovery_exit_rxcmd=0x30,
                recovery_exit_sofs=12, last_sof_token=0x1000))
            result = probe.decode_csv(path, core=2)['last']
            self.assertEqual(result['recovery_exit_rxcmd'], 0x30)
            self.assertEqual(result['recovery_exit_ticks'], 90000)
            self.assertEqual(result['recovery_exit_sofs'], 12)
            self.assertEqual(result['active_count'], 0)
            self.assertEqual(result['command_count'], 0)

    def test_cpu_capture_preserves_real_owner_and_event_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture_file(directory, core=1, values=dict(connected=1, generic_midi=1,
                                                                  gw25k=1, received_events=128,
                                                                  milliseconds=3456))
            result = probe.decode_csv(path, core=1)
            self.assertEqual(result['last']['connected'], 1)
            self.assertEqual(result['last']['gw25k'], 1)
            self.assertEqual(result['last']['received_events'], 128)
            self.assertEqual(result['last']['milliseconds'], 3456)

    def test_short_capture_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                probe.decode_csv(self.capture_file(directory, count=1023))

    def test_reordered_signals_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture_file(directory)
            path.write_text(path.read_text().replace(probe.SIGNALS[0], 'wrong_signal', 1))
            with self.assertRaisesRegex(ValueError, 'signal order'):
                probe.decode_csv(path)

    def test_invalid_binary_sample_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture_file(directory)
            rows = path.read_text().splitlines()
            rows[1] = rows[1].replace(',0', ',2', 1)
            path.write_text('\n'.join(rows) + '\n')
            with self.assertRaisesRegex(ValueError, 'invalid'):
                probe.decode_csv(path)

    def test_input_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            source = output / 'source.v'
            source.write_text('original')
            native = output / 'hotplug_inputs.json'
            native.write_text(json.dumps(dict(staged_input_sha256={'source.v': sha(source)})))
            (output / 'host_probe_inputs.json').write_text(json.dumps(dict(
                native_manifest_sha256=sha(native), inputs={})))
            probe.verify_inputs(output)
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'input changed'):
                probe.verify_inputs(output)

    def test_clock_pull_is_explicit_and_does_not_move_ports(self):
        plan = {'ports': {port: {'balls': ['C18' if port == 'usb2_ulpi_clk' else 'A1']}
                          for port in hotplug.PORTS}}
        physical = '\n'.join(f'IO_LOC "{port}" {entry["balls"][0]};'
                             for port, entry in plan['ports'].items()) + '\n'
        physical += 'IO_PORT "usb2_ulpi_clk" IO_TYPE=LVCMOS33;\n'
        with patch.object(hotplug, 'render_constraints', return_value=physical), \
                patch.object(hotplug, 'ulpi_bypass_constraints', side_effect=lambda payload, _: (payload, {})):
            original = hotplug.board_constraints(plan)[0]
            explicit = hotplug.board_constraints(plan, 'NONE')[0]
        self.assertEqual(explicit, original.replace(b'IO_TYPE=LVCMOS33;', b'IO_TYPE=LVCMOS33 PULL_MODE=NONE;'))
        self.assertEqual(hotplug.parse_locations(original.decode()), hotplug.parse_locations(explicit.decode()))


if __name__ == '__main__':
    unittest.main()
