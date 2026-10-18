"""Latency snapshot validity, interval boundaries and CLI behavior without hardware."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import instrument_cli as cli
from instrument_backend import (Ack, CommandRejected, SimulatedTransport,
                                decode_latency_status, read_latency_status,
                                input_to_digital_interval)


def snapshot(*, flags=0x7F, sequence=7, opcode=1, voice=31, schema=1):
    header = schema | sequence << 8 | opcode << 16 | voice << 24
    return struct.pack("<16I", header, flags, 1025, 50_000_000,
                       50_000, 100, 1000, 2000, 3000, 4000,
                       55_000, 90_000, 250, 1024, 120_000, 3)


def matching_ack(**overrides):
    return {"sequence": 7, "opcode": 1, "voice": 31, "status": 0,
            "connection_id": 4, "sound_generation": 10, "simulated": False,
            "timing_source": "serial", "queue_wait_ms": 2, "host_total_ms": 7,
            "rtt_ms": 5, **overrides}


class LatencyDecodeTests(unittest.TestCase):
    def test_schema_layout_and_clock_units(self):
        status = decode_latency_status(snapshot())
        self.assertEqual((status["schema"], status["sequence"], status["opcode"], status["voice"]), (1, 7, 1, 31))
        self.assertEqual(status["trace_id"], 1025)
        self.assertEqual(status["uart_rx_cycles"], 50_000)
        self.assertEqual(status["uart_rx_ms"], 1)
        self.assertEqual(status["commit_to_dac_note_ms"], .08)
        self.assertEqual(status["sample_period_cycles"], 1024)
        self.assertEqual(status["overwritten_pending_count"], 3)

    def test_valid_zero_durations_are_distinct_from_missing_endpoints(self):
        words = list(struct.unpack("<16I", snapshot()))
        words[4:12] = [0] * 8
        status = decode_latency_status(struct.pack("<16I", *words))
        self.assertEqual(status["commit_to_dac_note_ms"], 0)
        self.assertEqual(status["start_to_ack_ready_ms"], 0)
        words[1] = 1
        missing = decode_latency_status(struct.pack("<16I", *words))
        self.assertEqual(missing["uart_rx_ms"], 0)
        self.assertIsNone(missing["commit_to_state_sample_ms"])
        self.assertIsNone(missing["commit_to_dac_note_ms"])
        self.assertIsNone(missing["start_to_ack_ready_ms"])

    def test_note_only_fields_are_unavailable_for_non_note_on_and_invalid_trace(self):
        status = decode_latency_status(snapshot(opcode=2))
        self.assertIsNone(status["commit_to_note_sample_ms"])
        self.assertIsNone(status["commit_to_dac_note_ms"])
        self.assertIsNotNone(status["commit_to_dac_state_ms"])
        empty = decode_latency_status(snapshot(flags=0))
        self.assertIsNone(empty["uart_rx_ms"])
        self.assertIsNone(empty["trace_age_ms"])
        self.assertEqual(empty["latest_compute_cycles"], 250)

    def test_bad_size_schema_reserved_flags_and_clock_are_rejected(self):
        clockless = list(struct.unpack("<16I", snapshot()))
        clockless[3] = 0
        for data in (b"", snapshot()[:-1], snapshot() + b"\x00", snapshot(schema=2),
                     snapshot(flags=0x100), struct.pack("<16I", *clockless)):
            with self.assertRaises(ValueError):
                decode_latency_status(data)

    def test_atomic_reader_reads_all_indices_and_never_retries_partial_failure(self):
        raw = snapshot()
        transport = Mock()
        transport.command.side_effect = [Ack(index, 14, 0, byte, 1, "test") for index, byte in enumerate(raw)]
        self.assertEqual(read_latency_status(transport), raw)
        self.assertEqual([call.args for call in transport.command.call_args_list], [(14, 255, index) for index in range(64)])
        transport.reset_mock()
        transport.command.side_effect = [Ack(0, 14, 0, 1, 1, "test"), TimeoutError("partial")]
        with self.assertRaises(TimeoutError):
            read_latency_status(transport)
        self.assertEqual(transport.command.call_count, 2)

    def test_latency_ack_never_becomes_voice_mask_or_simulated_hardware_status(self):
        for status in (0, 1, 3):
            for simulated in (False, True):
                ack = Ack(0, 14, status, 255, 0, "test", simulated=simulated)
                self.assertIsNone(ack.as_dict()["active_mask"])
                self.assertEqual(ack.latency_status_byte, 255 if status == 0 and not simulated else None)
        model = SimulatedTransport()
        model.command(1, 31, 1)
        with self.assertRaises(CommandRejected) as rejection:
            read_latency_status(model)
        self.assertEqual(rejection.exception.ack.status, 1)
        self.assertEqual(model.active_mask, 1 << 31)


class LatencyIntervalTests(unittest.TestCase):
    def test_output_controls_use_first_new_gain_frame_and_name_both_opcodes(self):
        for opcode, name in ((16, "MASTER_VOLUME"), (17, "LR_BALANCE")):
            status = decode_latency_status(snapshot(opcode=opcode, voice=255))
            self.assertEqual(status["opcode_name"], name)
            self.assertIsNone(status["commit_to_note_sample_ms"])
            self.assertIsNone(status["commit_to_dac_note_ms"])
            result = input_to_digital_interval(status, matching_ack(opcode=opcode, voice=255), 4, 10)
            self.assertTrue(result["available"])
            self.assertEqual(result["endpoint"], "dac_state")
            self.assertIn("不代表增益斜坡已结束", result["reason"])
            self.assertAlmostEqual(result["lower_ms"], 3.062)
            self.assertAlmostEqual(result["upper_ms"], 6.962)

    def test_interval_uses_note_contribution_endpoint_without_adding_rtt_twice(self):
        result = input_to_digital_interval(decode_latency_status(snapshot()), matching_ack(), 4, 10)
        self.assertTrue(result["available"])
        # FPGA start -> DAC: 1.000 + .002 + .080 = 1.082 ms.
        self.assertAlmostEqual(result["lower_ms"], 3.082)
        self.assertAlmostEqual(result["upper_ms"], 6.982)
        self.assertEqual(result["endpoint"], "dac_note")

    def test_missing_note_endpoint_can_use_explicitly_zero_capable_state_endpoint(self):
        status = decode_latency_status(snapshot(flags=0x6B))
        result = input_to_digital_interval(status, matching_ack(), 4, 10)
        self.assertTrue(result["available"])
        self.assertEqual(result["endpoint"], "dac_state")
        self.assertIn("可能仍为零", result["reason"])

    def test_identity_generation_and_connection_must_all_match(self):
        status = decode_latency_status(snapshot())
        for changes in ({"sequence": 8}, {"opcode": 2}, {"voice": 0}, {"connection_id": 5},
                        {"sound_generation": 266}, {"sound_generation": None},
                        {"status": 3}, {"simulated": True}, {"timing_source": "unavailable"}):
            with self.subTest(changes=changes):
                self.assertFalse(input_to_digital_interval(status, matching_ack(**changes), 4, 10)["available"])
        # Identical 8-bit seq/op/voice after wrap still fails the monotonic host generation check.
        self.assertFalse(input_to_digital_interval(status, matching_ack(sound_generation=266), 4, 10)["available"])

    def test_expiry_missing_flags_negative_width_and_absent_host_times_do_not_produce_total(self):
        for status in (decode_latency_status(snapshot(flags=0xFF)), decode_latency_status(snapshot(flags=0)),
                       decode_latency_status(snapshot(flags=0x5F)), decode_latency_status(snapshot(flags=0x67))):
            self.assertFalse(input_to_digital_interval(status, matching_ack(), 4, 10)["available"])
        for changes in ({"host_total_ms": 2.5}, {"queue_wait_ms": None}, {"host_total_ms": float("nan")},
                        {"queue_wait_ms": -1}):
            self.assertFalse(input_to_digital_interval(decode_latency_status(snapshot()), matching_ack(**changes), 4, 10)["available"])


class LatencyCliTests(unittest.TestCase):
    def test_dry_run_encodes_all_64_snapshot_indices(self):
        output = io.StringIO()
        with patch.object(cli.sys, "argv", ["instrument_cli.py", "--dry-run", "latency-status"]), \
                patch.object(cli, "SerialTransport") as transport, contextlib.redirect_stdout(output):
            cli.main()
        transport.assert_not_called()
        self.assertEqual(output.getvalue().splitlines(), [cli.encode_packet(index, 14, 255, index).hex(" ") for index in range(64)])

    def test_json_and_text_cli_explain_digital_endpoint_without_inventing_host_total(self):
        for json_output in (False, True):
            transport = Mock(sequence=64, serial=object())
            transport.command.side_effect = [Ack(index, 14, 0, byte, 1, "test") for index, byte in enumerate(snapshot())]
            output = io.StringIO()
            args = ["instrument_cli.py", "--port", "FAKE", "latency-status"] + (["--json"] if json_output else [])
            with patch.object(cli.sys, "argv", args), patch.object(cli, "SerialTransport", return_value=transport), contextlib.redirect_stdout(output):
                cli.main()
            transport.close.assert_called_once()
            if json_output:
                self.assertEqual(json.loads(output.getvalue())["trace_id"], 1025)
            else:
                self.assertIn("final stereo-frame BCK rising edge", output.getvalue())
                self.assertIn("No input-to-output total", output.getvalue())


if __name__ == "__main__":
    unittest.main()
