"""Host-side protocol checks; no serial hardware or pyserial installation required."""
import importlib.util
import contextlib
import io
from pathlib import Path
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "instrument_cli.py"
SPEC = importlib.util.spec_from_file_location("instrument_cli", MODULE_PATH)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)
from instrument_backend import Ack, CommandRejected, SimulatedTransport
from instrument_backend.protocol import MEMORY_FLAG_BITS, decode_memory_flags


class HostProtocolTests(unittest.TestCase):
    def test_standard_ccitt_vector(self):
        self.assertEqual(cli.crc16(b"123456789"), 0x29B1)

    def test_packet_layout(self):
        packet = cli.encode_packet(0x42, 3, 2, 0x12345678)
        self.assertEqual(len(packet), 12)
        self.assertEqual(packet[:10], bytes.fromhex("a5 5a 42 03 02 00 78 56 34 12"))
        self.assertEqual(int.from_bytes(packet[10:], "little"), cli.crc16(packet[2:10]))

    def test_pitch_accuracy(self):
        for note in (0, 60, 69, 69.5, 127):
            actual = cli.phase_step(note) * cli.DEFAULT_SAMPLE_RATE / 2**32
            target = 440 * 2**((note-69)/12)
            self.assertLess(abs(actual-target), cli.DEFAULT_SAMPLE_RATE/2**32)

    def test_gain_and_envelope_boundaries(self):
        self.assertEqual(cli.gain_word(0), 0)
        self.assertEqual(cli.gain_word(1), 0x80000000)
        self.assertEqual(cli.envelope_step(0, cli.DEFAULT_SAMPLE_RATE), 0)
        self.assertEqual(cli.envelope_step(0.00001, cli.DEFAULT_SAMPLE_RATE), cli.UNITY)
        for value in (-1, 1.01, float("nan")):
            with self.assertRaises(ValueError):
                cli.gain_word(value)
        with self.assertRaises(ValueError):
            cli.phase_step(200)

    def test_memory_flag_bit_assignments(self):
        expected = ("calibrated", "bist_done", "bist_failed", "front_valid",
                    "fetch_fault", "underrun_seen", "ddr_pll_locked", "video_pll_locked")
        self.assertEqual(tuple(MEMORY_FLAG_BITS), expected)
        for bit, name in enumerate(expected):
            with self.subTest(bit=bit):
                decoded = decode_memory_flags(1 << bit)
                self.assertEqual([key for key, value in decoded.items() if value], [name])
        self.assertFalse(any(decode_memory_flags(0).values()))
        self.assertTrue(all(decode_memory_flags(255).values()))
        for invalid in (-1, 256, True, None):
            with self.assertRaises(ValueError):
                decode_memory_flags(invalid)

    def test_memory_status_dry_run_encodes_one_read_only_query(self):
        output = io.StringIO()
        with mock.patch.object(cli.sys, "argv", ["instrument_cli.py", "--dry-run", "memory-status"]), \
                mock.patch.object(cli, "SerialTransport") as transport, contextlib.redirect_stdout(output):
            cli.main()
        transport.assert_not_called()
        self.assertEqual(output.getvalue().strip(), cli.encode_packet(0, 0x0B, 0xFF, 0).hex(" "))

    def test_top_voice_cli_note_on_and_full_status_packets(self):
        for args, expected in ((["note-on", "31", "69"], [cli.encode_packet(0, 1, 31, cli.phase_step(69))]),
                               (["voice-status"], [cli.encode_packet(index, 13, 255, index) for index in range(4)])):
            output = io.StringIO()
            with mock.patch.object(cli.sys, "argv", ["instrument_cli.py", "--dry-run", *args]), \
                    mock.patch.object(cli, "SerialTransport") as transport, contextlib.redirect_stdout(output):
                cli.main()
            transport.assert_not_called()
            self.assertEqual(output.getvalue().splitlines(), [packet.hex(" ") for packet in expected])

    def test_voice_status_cli_reports_highest_bit_and_all_active_indices(self):
        transport = mock.Mock(sequence=4, serial=object())
        transport.command.side_effect = [Ack(index, 13, 0, value, 1, "test")
                                         for index, value in enumerate((1, 2, 4, 128))]
        output = io.StringIO()
        with mock.patch.object(cli.sys, "argv", ["instrument_cli.py", "--port", "FAKE", "voice-status"]), \
                mock.patch.object(cli, "SerialTransport", return_value=transport), contextlib.redirect_stdout(output):
            cli.main()
        self.assertEqual(transport.command.call_args_list, [mock.call(13, 255, index) for index in range(4)])
        self.assertIn("active=0x80040201 active_count=4 voice_count=32", output.getvalue())
        self.assertIn("active_voices=0,9,18,31", output.getvalue())

    def test_voice_32_is_rejected_before_opening_serial(self):
        with mock.patch.object(cli.sys, "argv", ["instrument_cli.py", "--port", "FAKE", "note-on", "32", "69"]), \
                mock.patch.object(cli, "SerialTransport") as transport, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.main()
        transport.assert_not_called()

    def test_memory_status_real_ack_prints_flags_not_voice_mask(self):
        transport = mock.Mock(sequence=1, serial=object())
        transport.command.return_value = Ack(0, 0x0B, 0, 0xCB, 1.5, "test")
        output = io.StringIO()
        with mock.patch.object(cli.sys, "argv", ["instrument_cli.py", "--port", "COM26", "memory-status"]), \
                mock.patch.object(cli, "SerialTransport", return_value=transport), \
                contextlib.redirect_stdout(output):
            cli.main()
        transport.command.assert_called_once_with(0x0B, 0xFF, 0)
        transport.close.assert_called_once_with()
        text = output.getvalue()
        self.assertIn("memory_flags=0xcb", text)
        self.assertNotIn("active=", text)
        for line in ("calibrated=1", "bist_done=1", "bist_failed=0", "front_valid=1",
                     "fetch_fault=0", "underrun_seen=0", "ddr_pll_locked=1", "video_pll_locked=1"):
            self.assertIn(line, text.splitlines())

    def test_memory_status_never_interprets_simulation_as_hardware(self):
        transport = mock.Mock(sequence=1, serial=object())
        transport.command.return_value = Ack(0, 0x0B, 0, 255, 0, "test", simulated=True)
        output = io.StringIO()
        with mock.patch.object(cli, "SerialTransport", return_value=transport), \
                contextlib.redirect_stdout(output):
            instrument = cli.Instrument("SIMULATED", 115200, 1, False)
            instrument.command(0x0B)
            instrument.close()
        self.assertIn("memory_status=unknown", output.getvalue())
        self.assertNotIn("calibrated=", output.getvalue())
        self.assertIsNone(Ack(0, 0x0B, 1, 255, 0, "test").memory_flags)
        self.assertIsNone(Ack(0, 0, 0, 15, 0, "test").memory_flags)

    def test_simulator_rejects_memory_query_and_preserves_voices(self):
        transport = SimulatedTransport()
        transport.command(1, 1, cli.phase_step(60))
        with self.assertRaises(CommandRejected) as caught:
            transport.command(0x0B, 0xFF, 0)
        self.assertEqual(caught.exception.ack.status, 1)
        self.assertTrue(caught.exception.ack.simulated)
        self.assertIsNone(caught.exception.ack.memory_flags)
        self.assertEqual(transport.command(0).active_mask, 2)

    def test_ping_output_still_uses_voice_mask(self):
        transport = mock.Mock(sequence=1, serial=object())
        transport.command.return_value = Ack(0, 0, 0, 5, 1.5, "test")
        output = io.StringIO()
        with mock.patch.object(cli, "SerialTransport", return_value=transport), \
                contextlib.redirect_stdout(output):
            instrument = cli.Instrument("COM26", 115200, 1, False)
            instrument.command(0)
            instrument.close()
        self.assertEqual(output.getvalue().strip(), "seq=0 OK active_low8=0x05 (voices 0..7; use voice-status for all 32)")

    def test_demo_initialization_failure_attempts_panic(self):
        initial_error = TimeoutError("voice 1 waveform ACK timeout")

        class FakeInstrument:
            def __init__(self):
                self.opcodes = []

            def command(self, opcode, voice=0xFF, value=0):
                self.opcodes.append(opcode)
                if len(self.opcodes) == 5:
                    raise initial_error

        instrument = FakeInstrument()
        commands = [(10, 255, 0), (5, 0, 0), (4, 0, cli.UNITY),
                    (1, 0, cli.phase_step(60)), (5, 1, 1)]
        with self.assertRaises(TimeoutError) as caught:
            cli.play_demo(instrument, commands, 1, cli.DEFAULT_SAMPLE_RATE, True)
        self.assertIs(caught.exception, initial_error)
        self.assertEqual(instrument.opcodes, [10, 5, 4, 1, 5, 10])

    def test_demo_cleanup_failure_preserves_initial_error(self):
        initial_error = TimeoutError("voice 1 waveform ACK timeout")

        class FakeInstrument:
            def __init__(self):
                self.opcodes = []

            def command(self, opcode, voice=0xFF, value=0):
                self.opcodes.append(opcode)
                if len(self.opcodes) == 5:
                    raise initial_error
                if len(self.opcodes) == 6:
                    raise OSError("port disconnected during PANIC")

        instrument = FakeInstrument()
        commands = [(10, 255, 0), (5, 0, 0), (4, 0, cli.UNITY),
                    (1, 0, cli.phase_step(60)), (5, 1, 1)]
        diagnostics = io.StringIO()
        with contextlib.redirect_stderr(diagnostics):
            with self.assertRaises(TimeoutError) as caught:
                cli.play_demo(instrument, commands, 1, cli.DEFAULT_SAMPLE_RATE, True)
        self.assertIs(caught.exception, initial_error)
        self.assertEqual(instrument.opcodes[-1], 10)
        self.assertIn("port disconnected during PANIC", diagnostics.getvalue())


if __name__ == "__main__":
    unittest.main()
