"""Per-voice onset snapshots: wire framing, flags, CLI and simulator isolation."""
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
from instrument_backend import (Ack, CommandRejected, SerialTransport, SimulatedTransport,
                                decode_voice_onset_status, read_voice_onset_status,
                                crc16, SYNC)


def snapshot(voice=31, sequence=7, flags=7, note_id=18, sample=226, dac=1300,
             elapsed=1300, cancel=0, revision=0x123456):
    return struct.pack("<8I", 1 | voice << 8 | sequence << 16 | flags << 24,
                       note_id, 50_000_000, sample, dac, elapsed, revision, cancel)


class OnsetDecodeTests(unittest.TestCase):
    def test_layout_zero_endpoint_and_amp_muted(self):
        status = decode_voice_onset_status(snapshot(flags=0x47, sample=0, dac=0), 31)
        self.assertEqual((status["voice"], status["sequence"], status["note_id"], status["revision"]), (31, 7, 18, 0x123456))
        self.assertEqual(status["state"], "complete")
        self.assertEqual(status["trigger_to_sample_ms"], 0)
        self.assertEqual(status["trigger_to_dac_ms"], 0)
        self.assertTrue(status["amp_muted_at_dac"])

    def test_each_pending_cancelled_and_retrigger_state_has_correct_validity(self):
        for flags, state in ((0, "not_triggered"), (1, "waiting_sample"), (3, "waiting_dac"),
                             (7, "complete"), (0x11, "cancelled"), (0x0F, "complete")):
            with self.subTest(flags=flags):
                status = decode_voice_onset_status(snapshot(flags=flags, cancel=400))
                self.assertEqual(status["state"], state)
                self.assertEqual(status["trigger_to_sample_cycles"], 226 if flags & 2 else None)
                self.assertEqual(status["trigger_to_dac_cycles"], 1300 if flags & 4 else None)
                self.assertEqual(status["trigger_to_cancel_cycles"], 400 if flags & 16 else None)
                self.assertEqual(status["was_active"], bool(flags & 8))

    def test_expired_and_observer_overflow_never_offer_exact_endpoint_values(self):
        for flags, state in ((0x27, "expired"), (0x87, "observer_overflow"), (0xA7, "observer_overflow")):
            status = decode_voice_onset_status(snapshot(flags=flags, elapsed=0x80000000))
            self.assertEqual(status["state"], state)
            self.assertFalse(status["exact"])
            self.assertIsNone(status["trigger_to_sample_cycles"])
            self.assertIsNone(status["trigger_to_dac_ms"])
            self.assertIsNone(status["elapsed_ms"])
            self.assertEqual(status["elapsed_cycles"], 0x80000000)

    def test_bad_schema_size_voice_clock_and_reserved_revision_rejected(self):
        words = list(struct.unpack("<8I", snapshot()))
        wrong_schema = [*words]; wrong_schema[0] = (wrong_schema[0] & ~255) | 2
        wrong_clock = [*words]; wrong_clock[2] = 0
        documents = [b"", snapshot()[:-1], snapshot() + b"\x00", snapshot(voice=32),
                     snapshot(revision=0x01000000), struct.pack("<8I", *wrong_schema), struct.pack("<8I", *wrong_clock)]
        for document in documents:
            with self.assertRaises(ValueError):
                decode_voice_onset_status(document)
        with self.assertRaises(ValueError):
            decode_voice_onset_status(snapshot(voice=30), 31)

    def test_ack_byte_is_not_an_activity_mask_or_simulated_hardware_measurement(self):
        for rejected in (False, True):
            for simulated in (False, True):
                ack = Ack(0, 15, int(rejected), 255, 0, "test", simulated=simulated)
                self.assertIsNone(ack.as_dict()["active_mask"])
                self.assertEqual(ack.voice_onset_status_byte, None if rejected or simulated else 255)
        model = SimulatedTransport()
        model.command(1, 31, 42)
        with self.assertRaises(CommandRejected) as rejection:
            read_voice_onset_status(model, 31)
        self.assertEqual(rejection.exception.ack.status, 1)
        self.assertEqual(model.active_mask, 1 << 31)


class OnsetWireTests(unittest.TestCase):
    def test_real_transport_parser_reads_selected_voice_in_32_atomic_transactions(self):
        raw = snapshot(voice=31)
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                self.received = bytearray()
                self.calls = []
                self.snapshot_voice = None
            def reset_input_buffer(self):
                pass
            def write(self, packet):
                self.calls.append(packet)
                seq, opcode, voice, flags, index = struct.unpack("<BBBBI", packet[2:10])
                assert opcode == 15 and voice == 31 and flags == 0
                assert crc16(packet[2:10]) == int.from_bytes(packet[10:12], "little")
                if index == 0:
                    self.snapshot_voice = voice
                assert self.snapshot_voice == voice
                payload = bytes((seq, 0, raw[index], opcode))
                self.received.extend(SYNC + payload + crc16(payload).to_bytes(2, "little"))
                return len(packet)
            def read(self, count):
                data = bytes(self.received[:count]); del self.received[:count]; return data
            def close(self):
                pass
        transport = SerialTransport("FAKE", serial_factory=FakeSerial)
        self.assertEqual(read_voice_onset_status(transport, 31), raw)
        self.assertEqual([int.from_bytes(packet[6:10], "little") for packet in transport.serial.calls], list(range(32)))
        transport.close()

    def test_reader_stops_at_first_failure_and_rejects_bad_voice_before_io(self):
        transport = Mock()
        transport.command.side_effect = [Ack(0, 15, 0, 1, 1, "test"), TimeoutError("partial")]
        with self.assertRaises(TimeoutError):
            read_voice_onset_status(transport, 31)
        self.assertEqual(transport.command.call_count, 2)
        for voice in (-1, 32, True, "0"):
            with self.assertRaises(ValueError):
                read_voice_onset_status(transport, voice)
        self.assertEqual(transport.command.call_count, 2)


class OnsetCliTests(unittest.TestCase):
    def test_dry_run_uses_voice_argument_and_exactly_32_indices(self):
        output = io.StringIO()
        with patch.object(cli.sys, "argv", ["instrument_cli.py", "--dry-run", "voice-onset", "31"]), \
                patch.object(cli, "SerialTransport") as transport, contextlib.redirect_stdout(output):
            cli.main()
        transport.assert_not_called()
        self.assertEqual(output.getvalue().splitlines(), [cli.encode_packet(index, 15, 31, index).hex(" ") for index in range(32)])

    def test_cli_json_and_text_have_per_note_identity_and_clear_digital_boundaries(self):
        for as_json in (False, True):
            transport = Mock(sequence=32, serial=object())
            transport.command.side_effect = [Ack(index, 15, 0, byte, 1, "test") for index, byte in enumerate(snapshot(flags=0x0F))]
            output = io.StringIO()
            args = ["instrument_cli.py", "--port", "FAKE", "voice-onset", "31"] + (["--json"] if as_json else [])
            with patch.object(cli.sys, "argv", args), patch.object(cli, "SerialTransport", return_value=transport), contextlib.redirect_stdout(output):
                cli.main()
            transport.close.assert_called_once()
            if as_json:
                data = json.loads(output.getvalue())
                self.assertEqual((data["voice"], data["note_id"], data["sequence"]), (31, 18, 7))
            else:
                self.assertIn("trigger_to_sample_cycles=226 (4.520 us)", output.getvalue())
                self.assertIn("not mixed-sample or analog/headphone onset", output.getvalue())
                self.assertIn("may already be sounding", output.getvalue())


if __name__ == "__main__":
    unittest.main()
