#!/usr/bin/env python3
"""Standard-library host codec tests; run with Python 3 or unittest discovery."""

import binascii
import contextlib
import io
from pathlib import Path
import random
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import screen_control as protocol


def raw_frame(opcode, arg0=0, arg1=0, sequence=0, version=1, magic=b"MK"):
    """Independent oracle uses Python's C CRC implementation."""
    header = struct.pack("<2sBBHII", magic, version, opcode, sequence, arg0, arg1)
    return header + struct.pack("<H", binascii.crc_hqx(header, 0xFFFF))


class ScreenControlTest(unittest.TestCase):
    def test_crc_standard_vector(self):
        self.assertEqual(protocol.crc16_ccitt(b"123456789"), 0x29B1)
        self.assertEqual(protocol.crc16_ccitt(b""), 0xFFFF)
        self.assertEqual(protocol.crc16_ccitt(memoryview(b"123456789")), 0x29B1)

    def test_encode_all_command_boundaries(self):
        for opcode, values in (
            (protocol.GET_STATUS, [0]),
            (protocol.GET_TOUCH, [0, 24]),
            (protocol.SET_CHANNEL, [0, 15]),
            (protocol.SET_TRANSPOSE, [-48, -1, 0, 48]),
            (protocol.SET_PAGE, [0, 15]),
            (protocol.SET_THEME, [0, 0xFFFF]),
            (protocol.CLEAR, [0, 0xFFFF]),
        ):
            for value in values:
                for sequence in [0, 0xFFFF]:
                    with self.subTest(opcode=opcode, value=value, sequence=sequence):
                        encoded = protocol.encode_request(opcode, sequence, value)
                        self.assertEqual(encoded, raw_frame(opcode, value & 0xFFFFFFFF, sequence=sequence))
                        frame = protocol.decode_frame(encoded)
                        self.assertFalse(frame.is_response)
                        self.assertEqual(frame.sequence, sequence)
                        self.assertEqual(frame.arg0, value & 0xFFFFFFFF)
                        if opcode == protocol.SET_TRANSPOSE:
                            self.assertEqual(frame.signed_arg0, value)

    def test_deterministic_random_round_trip(self):
        rng = random.Random(0x4D4B)
        for _ in range(200):
            opcode = rng.choice(list(protocol.OPCODES))
            value = {
                0x01: 0, 0x02: rng.randrange(25), 0x10: rng.randrange(16), 0x11: rng.randrange(-48, 49),
                0x20: rng.randrange(16), 0x21: rng.randrange(65536),
                0x22: rng.randrange(65536),
            }[opcode]
            sequence = rng.randrange(65536)
            encoded = protocol.encode_request(opcode, sequence, value)
            self.assertEqual(encoded, raw_frame(opcode, value & 0xFFFFFFFF, sequence=sequence))
            self.assertEqual(protocol.decode_frame(encoded).arg0, value & 0xFFFFFFFF)

    def test_request_type_and_range_checks(self):
        bad_calls = [
            (0x80, 0, 0, 0), (0x7F, 0, 0, 0), (0x01, -1, 0, 0),
            (0x01, 65536, 0, 0), (0x01, 0, 1, 0), (0x01, 0, 0, 1),
            (0x02, 0, 25, 0), (0x02, 0, 0xFFFFFFFF, 0), (0x02, 0, 0, 1),
            (0x10, 0, 16, 0), (0x10, 0, -1, 0),
            (0x11, 0, -49, 0), (0x11, 0, 49, 0),
            (0x11, 0, 0xFFFFFFFF, 0), (0x20, 0, 16, 0),
            (0x21, 0, 65536, 0), (0x22, 0, 65536, 0),
            (0x10, 0, 0, -1), (0x10, 0, 0, 0x100000000),
        ]
        for args in bad_calls:
            with self.subTest(args=args), self.assertRaises(ValueError):
                protocol.encode_request(*args)
        for field in range(4):
            for value in [True, "0", 0.0, None]:
                args = [0x10, 0, 0, 0]
                args[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(TypeError):
                    protocol.encode_request(*args)

    def test_decode_framing_and_crc(self):
        frame = protocol.encode_request(0x01)
        for invalid in [b"", frame[:-1], frame + b"\x00", raw_frame(0x01, magic=b"XX")]:
            with self.assertRaises(ValueError):
                protocol.decode_frame(invalid)
        for index in range(len(frame)):
            damaged = bytearray(frame)
            damaged[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ValueError):
                protocol.decode_frame(damaged)
        with self.assertRaisesRegex(ValueError, "version"):
            protocol.decode_frame(raw_frame(0x01, version=2))
        for value in [None, 16, "4d4b", list(frame)]:
            with self.assertRaises(TypeError):
                protocol.decode_frame(value)
        self.assertEqual(protocol.decode_frame(bytearray(frame)).opcode, 0x01)
        self.assertEqual(protocol.decode_frame(memoryview(frame)).opcode, 0x01)

    def test_decode_invalid_request_fields(self):
        for opcode, arg0, arg1 in [
            (0x7F, 0, 0), (0x01, 1, 0), (0x01, 0, 1),
            (0x10, 16, 0), (0x11, 49, 0), (0x11, (-49) & 0xFFFFFFFF, 0),
            (0x20, 0, 1), (0x21, 0x10000, 0), (0x22, 0x10000, 0),
        ]:
            with self.subTest(opcode=opcode, arg0=arg0, arg1=arg1), self.assertRaises(ValueError):
                protocol.decode_frame(raw_frame(opcode, arg0, arg1))

    def test_response_round_trip_and_signed_result(self):
        for opcode, result in [(0x01, 0xFEDCBA98), (0x02, 0xFFFFFFFF), (0x10, 15), (0x11, 0xFFFFFFD0),
                               (0x20, 15), (0x21, 0xFFFF), (0x22, 0x8000)]:
            encoded = protocol.encode_response(opcode, 500, 0, result)
            self.assertEqual(encoded, raw_frame(opcode | 0x80, 0, result, sequence=500))
            frame = protocol.decode_frame(encoded)
            self.assertTrue(frame.is_response)
            self.assertEqual(frame.arg1, result)
        self.assertEqual(protocol.decode_frame(protocol.encode_response(0x11, 0, 0, 0xFFFFFFD0)).signed_arg1, -48)
        for status in range(1, 5):
            frame = protocol.decode_frame(protocol.encode_response(0x7F, 42, status))
            self.assertEqual(frame.arg0, status)
            self.assertEqual(frame.command, "unknown")
        # Request bit 7 is illegal; its rejection still produces a decodable error.
        self.assertEqual(protocol.decode_frame(protocol.encode_response(0x90, 42, 1)).opcode, 0x90)

    def test_response_validation(self):
        for opcode, arg0, arg1 in [(0x81, 5, 0), (0x81, 1, 1), (0xFF, 0, 0),
                                   (0x90, 0, 16), (0x91, 0, 49), (0xA1, 0, 65536)]:
            with self.subTest(opcode=opcode, arg0=arg0, arg1=arg1), self.assertRaises(ValueError):
                protocol.decode_frame(raw_frame(opcode, arg0, arg1))
        with self.assertRaises(ValueError):
            protocol.encode_response(0x10, 0, 1, 15)
        with self.assertRaises(ValueError):
            protocol.encode_response(0x10, 0, 5)
        with self.assertRaises(ValueError):
            protocol.encode_response(0x90, 0, 0, 15)
        with self.assertRaises(TypeError):
            protocol.encode_response(0x10, 0, True)

    def test_cli_prints_hex_and_decodes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(protocol.main(["transpose", "-12", "--seq", "0x1234"]), 0)
        expected = protocol.encode_request(0x11, 0x1234, -12)
        self.assertEqual(output.getvalue().strip(), expected.hex(" "))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            protocol.main(["decode", expected.hex()])
        self.assertIn('"transpose": -12', output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            protocol.main(["channel", "16"])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
