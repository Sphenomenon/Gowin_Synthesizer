"""Focused checks for the standalone direct-PC USB device probe."""

import json
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_usb2_device_probe as probe
from tools import workstation_usb2_device_loopback as loopback
from tools.stage_usb_firmware import sha


class DeviceProbe(unittest.TestCase):
    def status_samples(self, source_status=0x12002003):
        payloads = [source_status & 0xffffff, ((source_status >> 24) << 16) | 42,
                    (42 << 8) | 234, 0x55aa33]
        return [(payloads[(index // 8) % 4] << 8) | (((index // 8) % 4) << 6)
                | (15 << 2) | (((index // 32) & 1) << 1) | (index & 1)
                for index in range(1024)]

    def test_observer_keeps_full_status_and_unique_identity(self):
        document = ElementTree.fromstring(probe.gao_configuration('C11029D1'))
        core = document.find('AoCore')
        self.assertEqual(core.get('module_name'), probe.TOP)
        self.assertEqual(core.get('sample_clock'), 'clk_50m_d')
        self.assertEqual(document.findtext('GAO_ID'), '29D1')
        signals = [entry.text for entry in core.findall('SignalList/Signal')]
        self.assertEqual(signals, [f'status_50mhz[{index}]' for index in reversed(range(384))])

    def test_timing_preserves_sixty_mhz_io_and_limits_cdc_exceptions(self):
        constraints = probe.timing_constraints()
        self.assertIn('16.666667', constraints)
        self.assertIn('set_input_delay', constraints)
        self.assertIn('set_output_delay', constraints)
        self.assertIn('u_device*/bridge/hs_sync_0_s0/D', constraints)
        self.assertIn('observations*.native_monitor/snapshot_50_*_s0/D', constraints)
        self.assertNotIn('u_device*/bridge/hs_sync_1_s0/D', constraints)
        self.assertNotIn('set_clock_groups', constraints)
        exceptions = [line for line in constraints.splitlines() if line.startswith('set_false_path')]
        self.assertTrue(all('-hold' in line or '/CLEAR' in line or '/PRESET' in line for line in exceptions))
        self.assertNotIn('wr_bin', '\n'.join(exceptions))
        self.assertNotIn('rd_bin', '\n'.join(exceptions))

    def test_peer_input_drift_fails_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / 'source_snapshot'
            snapshot.mkdir()
            source = snapshot / 'device.v'
            source.write_text('original')
            artifact = root / 'original.fs'
            artifact.write_text('bitstream')
            stage = root / 'accepted'
            stage.mkdir()
            manifest = stage / 'build.json'
            manifest.write_text(json.dumps(dict(passed=True, timing=dict(passed=True),
                                                sha256={'device.v': sha(source)},
                                                artifacts=[dict(path=str(artifact), sha256=sha(artifact))])))
            self.assertEqual(probe.peer_inputs(manifest)[0], snapshot)
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Frozen peer input changed'):
                probe.peer_inputs(manifest)

    def test_build_rejects_negative_routed_timing_even_when_tool_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / 'inputs.json').write_text(json.dumps(dict(input_sha256={})))
            with patch.object(probe.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                    patch.object(probe, 'audit', return_value=dict(passed=False)):
                with self.assertRaisesRegex(RuntimeError, 'timing did not close'):
                    probe.build(output)
            self.assertFalse(json.loads((output / 'build_result.json').read_text())['audit']['passed'])

    def test_decode_keeps_byte_counters_and_separates_usb_mailbox(self):
        value = (987654321 << 128) | (123456 << 96) | (123456 << 64) | (42 << 48) | (42 << 32)
        decoder = runpy.run_path(str(ROOT.parents[2] / '25k/example/MIDI_KEYBOARD/tools/decode_usb2_debug.py'))
        result = probe.decode([value | status for status in self.status_samples()], decoder)
        self.assertEqual(result['bulk_rx_bytes'], 123456)
        self.assertEqual(result['bulk_tx_bytes'], 123456)
        self.assertEqual(result['midi_rx_words'], 42)
        self.assertEqual(result['midi_tx_words'], 42)
        self.assertEqual(result['reference_cycles'], 987654321)
        self.assertEqual(result['usb']['boot_stage'], 0x12)
        self.assertTrue(result['usb']['boot_done'])
        self.assertTrue(result['usb']['hs_active'])
        self.assertEqual(result['usb']['phy_clock_ticks_per_ms'], 234)
        self.assertEqual(result['complete_page_cycles'], 32)
        with self.assertRaisesRegex(ValueError, '1024'):
            probe.decode([value], {})

    def test_real_gao_bit_column_format_and_invalid_samples(self):
        samples = [(123456789 << 128) | word for word in self.status_samples()]
        header = 'time unit: us, ' + ', '.join(f'status_50mhz[{index}]' for index in reversed(range(160))) + ',\n'
        rows = [str(index) + ', ' + ', '.join(f'{word:0160b}') + ',\n'
                for index, word in enumerate(samples)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.csv'
            path.write_text('Data:\n' + header + ''.join(rows))
            self.assertEqual(probe.read_samples(path, 160), samples)
            path.write_text('Data:\n' + header + ''.join(rows[:-1]))
            with self.assertRaisesRegex(ValueError, '1024'):
                probe.read_samples(path, 160)
            path.write_text(('Data:\n' + header + ''.join(rows)).replace('status_50mhz[159]', 'other[159]'))
            with self.assertRaisesRegex(ValueError, 'ordered'):
                probe.read_samples(path, 160)
            path.write_text('Data:\n' + header + '0, X, ' + rows[0].split(', ', 2)[2])
            with self.assertRaisesRegex(ValueError, 'binary'):
                probe.read_samples(path, 160)

    def test_incoherent_or_corrupt_rotating_status_fails(self):
        with self.assertRaisesRegex(ValueError, 'coherent'):
            probe.decode_usb_status([0] * 1024, lambda value: {})
        samples = self.status_samples()
        samples = [word ^ (1 << 8) if (index // 8) % 4 == 3 else word
                   for index, word in enumerate(samples)]
        with self.assertRaisesRegex(ValueError, 'coherent'):
            probe.decode_usb_status(samples, lambda value: {})

    def test_native_statistics_are_decoded_from_independent_coherent_mailboxes(self):
        native = [0x0251000d, 180000, 180001, 0x0d000003, 0x80000004, 0xc3000004, 0x5f000005]
        samples = self.status_samples()
        for monitor, word in enumerate(native):
            samples = [sample | (status << (160 + 32 * monitor))
                       for sample, status in zip(samples, self.status_samples(word))]
        decoder = runpy.run_path(str(ROOT.parents[2] / '25k/example/MIDI_KEYBOARD/tools/decode_usb2_debug.py'))
        result = probe.decode(samples, decoder, 384)['native']
        self.assertEqual(result['raw_se0_max_cycles'], 180000)
        self.assertEqual(result['utmi_se0_max_cycles'], 180001)
        self.assertEqual(result['rxcmd_count'], 3)
        self.assertEqual(result['last_rxcmd'], '0D')
        self.assertEqual(result['phy_rx_bytes'], 4)
        self.assertEqual(result['link_nxt_count'], 5)
        self.assertEqual(result['states_seen'], 2)

    def test_midi_payload_balances_note_pairs_and_rejects_partial_pair(self):
        data = loopback.payload(128)
        self.assertEqual(len(data), 384)
        for offset in range(0, len(data), 6):
            self.assertEqual(data[offset] & 0xf0, 0x90)
            self.assertEqual(data[offset + 3] & 0xf0, 0x80)
            self.assertEqual(data[offset] & 15, data[offset + 3] & 15)
            self.assertEqual(data[offset + 1], data[offset + 4])
            self.assertEqual(data[offset + 5], 0)
        with self.assertRaises(ValueError):
            loopback.payload(3)

    def test_midi_exchange_checks_real_bidirectional_stream_bytes(self):
        transmitted = loopback.payload(128)
        client, server = socket.socketpair()
        client.setblocking(False)
        def echo():
            with server:
                remaining = len(transmitted)
                while remaining:
                    data = server.recv(min(23, remaining))
                    if not data:
                        return
                    remaining -= len(data)
                    server.sendall(data)
        worker = threading.Thread(target=echo)
        worker.start()
        try:
            result = loopback.exchange(client.fileno(), transmitted, 2)
            self.assertTrue(result['passed'])
            self.assertEqual(result['received_bytes'], len(transmitted))
        finally:
            client.close()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())

    def test_loopback_requires_specific_product_and_480_mbps_enumeration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / '3-1'
            device.mkdir()
            for name, value in dict(idVendor='fb9a', idProduct='fb9b', product='GW138K USB2 Loopback',
                                    speed='12', bConfigurationValue='1').items():
                (device / name).write_text(value)
            with self.assertRaisesRegex(ValueError, 'High-Speed'):
                loopback.find_device(root)
            (device / 'speed').write_text('480')
            self.assertEqual(loopback.find_device(root), device)
            (device / 'product').write_text('GW25K MIDI Screen')
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                loopback.find_device(root)

    def test_loopback_top_preserves_backpressure_and_counts_accepted_data(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'probe'
            command = ['iverilog', '-g2012', '-s', 'tb_workstation_usb2_device_probe', '-o', str(executable),
                       str(ROOT / probe.TOP_SOURCE), str(ROOT / 'sim/usb2/tb_workstation_usb2_device_probe.sv'),
                       str(ROOT.parents[2] / '25k/example/MIDI_KEYBOARD/rtl/usb_board/midi_usb2_debug.v')]
            compilation = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            execution = subprocess.run(['vvp', str(executable)], text=True, capture_output=True, timeout=10)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn('PASS workstation_usb2_device_probe', execution.stdout)


if __name__ == '__main__':
    unittest.main()
