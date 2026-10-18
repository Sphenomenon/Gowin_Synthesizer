"""Video snapshot decoder, CLI and serial regressions; never access hardware."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import instrument_cli as cli
from instrument_backend import (Ack, CommandRejected, SerialTransport, SimulatedTransport,
                                crc16, decode_video_status, read_video_status)
from instrument_backend.protocol import VIDEO_FLAG_BITS


SNAPSHOT = bytes.fromhex("01 2f aa 05 78 56 34 12 ef cd ab 89 ff ff ff ff")


def reply(sequence, value, opcode=0x0C, status=0):
    payload = bytes((sequence, status, value, opcode))
    return b"\xa5\x5a" + payload + crc16(payload).to_bytes(2, "little")


class VideoDecoderTests(unittest.TestCase):
    def test_schema_little_endian_counters_and_quantized_clock(self):
        status = decode_video_status(SNAPSHOT)
        self.assertEqual(status["schema"], 1)
        self.assertEqual(status["flags"], 0x2F)
        self.assertEqual(status["pixel_blocks_per_10ms"], 1450)
        self.assertAlmostEqual(status["pixel_measured_mhz"], 148.48)
        self.assertEqual(status["pixel_vblank_frames"], 0x12345678)
        self.assertEqual(status["rendered_frames"], 0x89ABCDEF)
        self.assertEqual(status["underruns"], 0xFFFFFFFF)

    def test_each_flag_has_its_own_bit_including_active_high_serializer_reset(self):
        names = ("hpd", "video_locked", "pixel_reset_n", "scanout_reset_n",
                 "serializer_reset", "window_valid")
        self.assertEqual(tuple(VIDEO_FLAG_BITS), names)
        for bit, name in enumerate(names):
            with self.subTest(name=name):
                status = decode_video_status(bytes((1, 1 << bit)) + SNAPSHOT[2:])
                self.assertEqual([key for key in names if status[key]], [name])

    def test_incomplete_measurement_is_unknown_but_valid_zero_means_no_counted_clock(self):
        status = decode_video_status(bytes((1, 0x0F)) + SNAPSHOT[2:])
        self.assertEqual(status["pixel_blocks_per_10ms"], 1450)
        self.assertIsNone(status["pixel_measured_mhz"])
        status = decode_video_status(bytes((1, 0x20)) + bytes(14))
        self.assertEqual(status["pixel_measured_mhz"], 0)

    def test_bad_length_type_schema_and_reserved_bits_are_rejected(self):
        for invalid in (None, 16, list(SNAPSHOT), SNAPSHOT[:-1], SNAPSHOT + b"\0",
                        bytes(16), bytes((2,)) + SNAPSHOT[1:],
                        bytes((1, 0x40)) + SNAPSHOT[2:], bytes((1, 0x80)) + SNAPSHOT[2:]):
            with self.subTest(data=invalid), self.assertRaises(ValueError):
                decode_video_status(invalid)

    def test_video_ack_semantics_do_not_leak_data_into_voice_or_memory_state(self):
        for status, simulated in ((0, False), (1, False), (0, True), (1, True)):
            with self.subTest(status=status, simulated=simulated):
                ack = Ack(42, 0x0C, status, 0xFF, 1.2, "test", simulated=simulated)
                event = ack.as_dict()
                self.assertIsNone(event["active_mask"])
                self.assertIsNone(event["memory_flags"])
                self.assertEqual(event["video_status_byte"], 0xFF if status == 0 and not simulated else None)
        for opcode in (0, 0x0B):
            self.assertIsNone(Ack(0, opcode, 0, 0xFF, 0, "test").video_status_byte)

    def test_simulation_rejects_video_query_without_fabricating_hardware_state(self):
        transport = SimulatedTransport()
        transport.command(1, 2, 42)
        with self.assertRaises(CommandRejected) as caught:
            read_video_status(transport)
        self.assertTrue(caught.exception.ack.simulated)
        self.assertIsNone(caught.exception.ack.video_status_byte)
        self.assertIsNone(caught.exception.ack.as_dict()["active_mask"])
        self.assertEqual(transport.command(0).active_mask, 4)


class SnapshotSerial:
    """An indexed snapshot device with optional stale/rejected/missing replies."""
    def __init__(self, *args, **kwargs):
        self.buffer = bytearray()
        self.writes = []
        self.closed = False
        self.live = SNAPSHOT
        self.snapshot = None
        self.reject_index = None
        self.timeout_index = None

    def reset_input_buffer(self):
        self.buffer.clear()

    def write(self, packet):
        self.writes.append(packet)
        sequence, opcode, voice, flags = packet[2:6]
        index = int.from_bytes(packet[6:10], "little")
        if packet[:2] != b"\xa5\x5a" or crc16(packet[2:10]) != int.from_bytes(packet[10:], "little"):
            raise AssertionError("invalid request framing/CRC")
        if (opcode, voice, flags) != (0x0C, 0xFF, 0) or index not in range(16):
            raise AssertionError("unexpected write to diagnostic transport")
        if index == 0:
            self.snapshot = self.live
            self.live = bytes(16)  # Live values change while the old snapshot is read.
        if index == self.timeout_index:
            return len(packet)
        if index == self.reject_index:
            self.buffer.extend(reply(sequence, 0xFF, status=1))
            return len(packet)
        invalid_crc = bytearray(reply(sequence, 0xFF))
        invalid_crc[7] ^= 1
        self.buffer.extend(reply((sequence + 1) & 255, 0xFF) + reply(sequence, 0xEE, opcode=0x0B)
                           + invalid_crc + reply(sequence, self.snapshot[index]))
        return len(packet)

    def read(self, count):
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        if not data:
            time.sleep(0.001)
        return data

    def close(self):
        self.closed = True


class VideoTransportTests(unittest.TestCase):
    def setUp(self):
        self.transport = SerialTransport("FAKE", timeout=0.04, serial_factory=SnapshotSerial)
        self.addCleanup(self.transport.close)

    def test_wire_reads_one_snapshot_in_index_order_across_sequence_wrap(self):
        self.transport.sequence = 250
        raw = read_video_status(self.transport)
        self.assertEqual(raw, SNAPSHOT)
        packets = self.transport.serial.writes
        self.assertEqual(len(packets), 16)
        self.assertEqual([int.from_bytes(packet[6:10], "little") for packet in packets], list(range(16)))
        self.assertEqual([packet[2] for packet in packets], [(250 + index) & 255 for index in range(16)])
        self.assertEqual(self.transport.sequence, 10)
        self.assertNotEqual(raw, self.transport.serial.live)

    def test_rejection_stops_without_retrying_or_replacing_snapshot(self):
        self.transport.serial.reject_index = 5
        with self.assertRaises(CommandRejected) as caught:
            read_video_status(self.transport)
        self.assertEqual(len(self.transport.serial.writes), 6)
        self.assertEqual(caught.exception.ack.opcode, 0x0C)
        self.assertIsNone(caught.exception.ack.video_status_byte)
        self.assertIn("diagnostic FPGA bitstream", str(caught.exception))

    def test_timeout_stops_without_returning_partial_snapshot(self):
        self.transport.serial.timeout_index = 7
        with self.assertRaises(TimeoutError):
            read_video_status(self.transport)
        self.assertEqual(len(self.transport.serial.writes), 8)


class VideoCliTests(unittest.TestCase):
    def transport(self, raw=SNAPSHOT):
        transport = Mock(sequence=16, serial=object())
        transport.command.side_effect = [Ack(index, 0x0C, 0, value, 1, "test")
                                         for index, value in enumerate(raw)]
        return transport

    def run_cli(self, transport):
        with patch.object(cli.sys, "argv", ["instrument_cli.py", "--port", "FAKE", "video-status"]), \
                patch.object(cli, "SerialTransport", return_value=transport):
            cli.main()

    def test_dry_run_emits_sixteen_indexed_packets_without_opening_hardware(self):
        output = io.StringIO()
        with patch.object(cli.sys, "argv", ["instrument_cli.py", "--dry-run", "video-status"]), \
                patch.object(cli, "SerialTransport") as transport, contextlib.redirect_stdout(output):
            cli.main()
        transport.assert_not_called()
        self.assertEqual(output.getvalue().splitlines(),
                         [cli.encode_packet(index, 0x0C, 0xFF, index).hex(" ") for index in range(16)])

    def test_complete_report_prints_raw_flags_estimate_and_counters(self):
        transport = self.transport()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli(transport)
        transport.command.assert_has_calls([call(0x0C, 0xFF, index) for index in range(16)])
        self.assertEqual(transport.command.call_count, 16)
        transport.close.assert_called_once_with()
        text = output.getvalue()
        for line in (f"video_status_raw={SNAPSHOT.hex(' ')}", "schema=1 flags=0x2f", "hpd=1",
                     "video_locked=1", "pixel_reset_n=1", "scanout_reset_n=1", "serializer_reset=0",
                     "window_valid=1", "pixel_blocks_per_10ms=1450", "pixel_vblank_frames=305419896",
                     "rendered_frames=2309737967", "underruns=4294967295"):
            self.assertIn(line, text.splitlines())
        self.assertIn("pixel_measured_mhz=148.4800", text)
        self.assertIn("quantization +/-0.1024 MHz", text)
        self.assertNotIn("active=", text)

    def test_unready_clock_window_prints_unknown_instead_of_a_frequency(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli(self.transport(bytes((1, 0x0F)) + SNAPSHOT[2:]))
        self.assertIn("pixel_measured_mhz=unknown", output.getvalue())
        self.assertNotIn("148.4800", output.getvalue())

    def test_unknown_schema_keeps_raw_bytes_but_no_decoded_hardware_claim(self):
        raw = bytes((2,)) + SNAPSHOT[1:]
        output, error = io.StringIO(), io.StringIO()
        transport = self.transport(raw)
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error), \
                self.assertRaises(SystemExit) as caught:
            self.run_cli(transport)
        self.assertEqual(caught.exception.code, 1)
        self.assertIn(f"video_status_raw={raw.hex(' ')}", output.getvalue())
        self.assertNotIn("hpd=", output.getvalue())
        self.assertIn("unsupported video-status schema 2", error.getvalue())
        transport.close.assert_called_once_with()

    def test_mid_read_timeout_closes_port_without_partial_report_or_retry(self):
        transport = self.transport()
        transport.command.side_effect = [Ack(index, 0x0C, 0, value, 1, "test")
                                         for index, value in enumerate(SNAPSHOT[:3])] + [TimeoutError("lost reply")]
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error), \
                self.assertRaises(SystemExit) as caught:
            self.run_cli(transport)
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("lost reply", error.getvalue())
        self.assertEqual(transport.command.call_count, 4)
        transport.close.assert_called_once_with()

    def test_successful_simulated_ack_is_not_reported_as_a_hardware_snapshot(self):
        transport = self.transport()
        transport.command.side_effect = [Ack(0, 0x0C, 0, 1, 0, "test", simulated=True)]
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error), self.assertRaises(SystemExit):
            self.run_cli(transport)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("no valid hardware status", error.getvalue())
        self.assertEqual(transport.command.call_count, 1)
        transport.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
