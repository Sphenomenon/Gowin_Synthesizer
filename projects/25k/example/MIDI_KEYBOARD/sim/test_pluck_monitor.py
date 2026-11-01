from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pluck_monitor as monitor
import screen_control as protocol


class FakeTransport:
    def __init__(self, unsupported=False, mismatch=False):
        self.unsupported = unsupported
        self.mismatch = mismatch
        self.pending = b""
        self.writes = []

    def write(self, data):
        request = protocol.decode_frame(data)
        self.writes.append(request)
        self.pending = protocol.encode_response(request.opcode, request.sequence + self.mismatch,
                                                int(self.unsupported), 0 if self.unsupported else request.arg0)

    def read(self):
        chunk, self.pending = self.pending[:3], self.pending[3:]
        return chunk


class PluckMonitorTest(unittest.TestCase):
    def test_snapshot_signed_values_and_metadata(self):
        data = bytearray(64)
        struct.pack_into("<3I", data, 0, 0x314B4C50, 0x00020503, 123)
        struct.pack_into("<6h", data, 12, -32768, -1, 0, 32767, 1234, -5432)
        struct.pack_into("<5H", data, 24, 32768, 1, 0, 32767, 1234)
        struct.pack_into("<3I", data, 36, 15, (512 << 16) | 1024, (4000 << 16) | (244 << 8) | 2)
        struct.pack_into("<5H", data, 48, 1, 2, 3, 4, 5)
        snapshot = monitor.Snapshot.decode(list(struct.unpack("<16I", data)))
        self.assertEqual(snapshot.raw, (-32768, -1, 0, 32767, 1234, -5432))
        self.assertEqual(snapshot.trigger_counts, (1, 2, 3, 4, 5))
        self.assertEqual((snapshot.gates, snapshot.timeouts, snapshot.transpose, snapshot.channel), (5, 2, -12, 2))
        self.assertTrue(snapshot.ready)
        self.assertEqual(snapshot.sample_hz, 4000)
        self.assertFalse(snapshot.detailed)
        struct.pack_into("<I", data, 4, snapshot.flags | 32)
        self.assertTrue(monitor.Snapshot.decode(list(struct.unpack("<16I", data))).detailed)

    def test_snapshot_rejects_unknown_version(self):
        for words in ([0] * 16, [0x314B4C50] * 15):
            with self.assertRaises(ValueError):
                monitor.Snapshot.decode(words)

    def test_vpp_capability_window_and_thresholds(self):
        words = [0x314B4C50] + [0] * 15
        words[1] = 8192 | 64 | 32
        words[10] = (32 << 16) | 64
        words[11] = 25000 << 16
        words[15] = (250 << 16) | 7
        snapshot = monitor.Snapshot.decode(words)
        self.assertTrue(snapshot.peak_to_peak)
        self.assertEqual((snapshot.window_samples, snapshot.overruns, snapshot.sample_hz), (250, 7, 25000))
        packed = (snapshot.off_threshold << 16) | snapshot.on_threshold
        request = protocol.encode_request(protocol.SET_PLUCK_THRESHOLDS, arg0=packed)
        self.assertEqual(protocol.decode_frame(request).arg0, packed)
        self.assertEqual(protocol.decode_frame(protocol.encode_response(protocol.SET_PLUCK_THRESHOLDS, 1, result=packed)).arg1, packed)

    def test_noise_snapshot_signedness_layout_and_readonly_codec(self):
        data = bytearray(64)
        struct.pack_into("<3I", data, 0, 0x314F4E50, 12345, (31 << 8) | 7)
        for offset, values in ((12, (10, 160, 30, 200, 40)), (24, (74, 224, 94, 264, 104)),
                               (36, (42, 192, 62, 232, 72)), (48, (65535, 1, 2, 3, 4))):
            struct.pack_into("<5H", data, offset, *values)
        struct.pack_into("<I", data, 60, (100 << 16) | 87)
        snapshot = monitor.NoiseSnapshot.decode(list(struct.unpack("<16I", data)))
        self.assertEqual(snapshot.floors, (10, 160, 30, 200, 40))
        self.assertEqual(snapshot.on_levels, (74, 224, 94, 264, 104))
        self.assertEqual(snapshot.off_levels, (42, 192, 62, 232, 72))
        self.assertEqual(snapshot.current_vpp, (65535, 1, 2, 3, 4))
        self.assertEqual((snapshot.sample_count, snapshot.valid_channels, snapshot.calibration_done, snapshot.calibration_length), (12345, 31, 87, 100))
        for invalid in ([0] * 16, [0x314F4E50] * 15):
            with self.assertRaises(ValueError):
                monitor.NoiseSnapshot.decode(invalid)
        for word in (0, 15):
            self.assertEqual(protocol.decode_frame(protocol.encode_request(protocol.GET_PLUCK_NOISE, arg0=word)).arg0, word)
        self.assertEqual(protocol.decode_frame(protocol.encode_response(protocol.GET_PLUCK_NOISE, 0, result=0xFFFFFFFF)).arg1, 0xFFFFFFFF)
        words = [0x314B4C50] + [0] * 15
        words[1] = 16384
        self.assertTrue(monitor.Snapshot.decode(words).adaptive_noise)

    def test_client_reads_noise_only_with_capability(self):
        class SnapshotTransport:
            def __init__(self, adaptive, carrier=False):
                self.commands = []
                self.result = b""
                self.main = [0x314B4C50, (16384 if adaptive else 0) | (32768 if carrier else 0)] + [0] * 14
                self.noise = [0x314F4E50, 0, 8 if carrier else 0] + [0] * 13

            def write(self, data):
                request = protocol.decode_frame(data)
                self.commands.append(request.opcode)
                values = self.noise if request.opcode == protocol.GET_PLUCK_NOISE else self.main
                self.result = protocol.encode_response(request.opcode, request.sequence, result=values[request.arg0])

            def read(self):
                result, self.result = self.result, b""
                return result

        for adaptive in (False, True):
            transport = SnapshotTransport(adaptive)
            snapshot = monitor.ControlClient(transport).snapshot()
            self.assertEqual(snapshot.noise is not None, adaptive)
            self.assertEqual(transport.commands.count(protocol.GET_PLUCK_NOISE), 16 if adaptive else 0)
        transport = SnapshotTransport(False, carrier=True)
        snapshot = monitor.ControlClient(transport).snapshot()
        self.assertTrue(snapshot.carrier_mode)
        self.assertFalse(snapshot.adaptive_noise)
        self.assertTrue(snapshot.noise.carrier_reference)
        self.assertEqual(transport.commands.count(protocol.GET_PLUCK_NOISE), 16)
        transport = SnapshotTransport(False, carrier=True)
        transport.noise[2] = 0
        with self.assertRaises(monitor.PanelError):
            monitor.ControlClient(transport).snapshot()

    def test_latest_telemetry_is_bounded_and_reports_no_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.json"
            worker = monitor.Monitor(path)
            worker.events.extend((sequence, "12:00:00", "Note On") for sequence in range(500))
            worker.event_count = 500
            worker.write_telemetry()
            import json
            first = json.loads(path.read_text())
            self.assertIsNone(first["snapshot"])
            self.assertIsNone(first["age_seconds"])
            self.assertEqual(len(first["events"]), 20)
            self.assertEqual(first["event_count"], 500)
            worker.events.clear()
            worker.write_telemetry()
            self.assertEqual(json.loads(path.read_text())["events"], [])
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_mk_chunks_and_identity(self):
        transport = FakeTransport()
        client = monitor.ControlClient(transport)
        self.assertEqual(client.query(protocol.GET_PLUCK, 15), 15)
        self.assertEqual(transport.writes[0].arg1, 0)
        with self.assertRaises(monitor.PanelError):
            monitor.ControlClient(FakeTransport(mismatch=True)).query(protocol.GET_STATUS)
        with self.assertRaises(monitor.UnsupportedFirmware):
            monitor.ControlClient(FakeTransport(unsupported=True)).query(protocol.GET_PLUCK)

    def test_pluck_codec_boundaries(self):
        for index in (0, 15):
            self.assertEqual(protocol.decode_frame(protocol.encode_request(protocol.GET_PLUCK, arg0=index)).arg0, index)
        with self.assertRaises(ValueError):
            protocol.encode_request(protocol.GET_PLUCK, arg0=16)
        frame = protocol.decode_frame(protocol.encode_response(protocol.GET_PLUCK, 1, result=0xFFFFFFFF))
        self.assertEqual(frame.arg1, 0xFFFFFFFF)

    def test_diagnostic_emitter_capability_and_command(self):
        words = [0x314B4C50] + [0] * 15
        words[1] = 64 | 128
        snapshot = monitor.Snapshot.decode(words)
        self.assertTrue(snapshot.diagnostic_only)
        self.assertTrue(snapshot.emitters_on)
        words[1] = 0
        self.assertFalse(monitor.Snapshot.decode(words).diagnostic_only)
        for value in (0, 1):
            request = protocol.encode_request(protocol.SET_PLUCK_EMITTERS, arg0=value)
            self.assertEqual(protocol.decode_frame(request).arg0, value)
        with self.assertRaises(ValueError):
            protocol.encode_request(protocol.SET_PLUCK_EMITTERS, arg0=2)

    def test_midi_running_status_and_realtime(self):
        parser = monitor.MidiParser()
        self.assertEqual(parser.feed(bytes([0x90, 48])), [])
        self.assertEqual(parser.feed(bytes([0xF8, 100, 49, 0])), [(0x90, 48, 100), (0x90, 49, 0)])
        self.assertEqual(parser.feed(bytes([0xC2, 73, 40, 0xE0, 0, 64])), [(0xC2, 73), (0xC2, 40), (0xE0, 0, 64)])

    def test_system_messages_cancel_running_status(self):
        parser = monitor.MidiParser()
        self.assertEqual(parser.feed(bytes([0x90, 48, 100, 0xF0, 1, 2, 0xF8, 0xF7, 49, 100])), [(0x90, 48, 100)])
        self.assertEqual(parser.feed(bytes([0xF2, 1, 2, 49, 100, 0x80, 48, 0])), [(0xF2, 1, 2), (0x80, 48, 0)])

    def test_monitor_tracks_actual_notes_and_panic(self):
        worker = monitor.Monitor()
        parser = monitor.MidiParser()
        import os
        read_fd, write_fd = os.pipe2(os.O_NONBLOCK)
        try:
            os.write(write_fd, bytes([0x90, 48, 100, 0x91, 48, 100, 0xB0, 123, 0]))
            worker.read_midi(read_fd, parser)
            self.assertEqual(worker.notes, {(1, 48)})
            os.write(write_fd, bytes([0x91, 48, 0]))
            worker.read_midi(read_fd, parser)
            self.assertEqual(worker.notes, set())
            self.assertEqual(worker.event_count, 4)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_device_discovery_never_selects_ambiguous_board(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(monitor.PanelError):
                monitor.discover_device(root)
            for name in ("3-1", "3-2"):
                device = root / name
                device.mkdir()
                (device / "idVendor").write_text("fb9a\n")
                (device / "idProduct").write_text("fb9b\n")
            with self.assertRaises(monitor.PanelError):
                monitor.discover_device(root)


if __name__ == "__main__":
    unittest.main()
