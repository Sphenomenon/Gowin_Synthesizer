import pathlib
import struct
import sys
import unittest
import zlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from protocol_v1 import encode, decode, fragments, Reassembler


class Codec(unittest.TestCase):
    def test_crc_reference_and_hello(self):
        self.assertEqual(zlib.crc32(b'123456789'), 0xCBF43926)
        message = encode(1, 1, 0x1020304050607080, struct.pack('<HH', 1, 0))
        self.assertEqual(message[:16].hex(), '01000400010000008070605040302010')
        self.assertEqual(decode(message)['payload'], b'\x01\0\0\0')

    def test_maximum_and_duplicate_fragment(self):
        message = encode(0x7f, 7, 9, bytes(range(246)) * 2)
        parts = list(fragments(message, 65535))
        self.assertEqual(len(parts), 37)
        assembler = Reassembler()
        self.assertIsNone(assembler.feed(parts[0]))
        self.assertIsNone(assembler.feed(parts[0]))
        for part in parts[1:-1]:
            self.assertIsNone(assembler.feed(part))
        self.assertEqual(assembler.feed(parts[-1]), message)
        self.assertEqual(decode(message)['request_id'], 7)

    def test_invalid_crc_and_declared_length(self):
        message = bytearray(encode(2, 1, 1))
        message[-1] ^= 1
        with self.assertRaises(ValueError):
            decode(message)
        message = bytearray(encode(2, 1, 1))
        message[2] = 1
        with self.assertRaises(ValueError):
            decode(message)

    def test_order_conflict_flags_and_recovery(self):
        message = encode(2, 1, 1)
        a, b = list(fragments(message, 1))
        assembler = Reassembler()
        with self.assertRaises(ValueError):
            assembler.feed(b)
        assembler.feed(a)
        changed = bytearray(a)
        changed[-1] ^= 1
        with self.assertRaises(ValueError):
            assembler.feed(changed)
        changed = bytearray(a)
        changed[4] |= 4
        with self.assertRaises(ValueError):
            assembler.feed(changed)
        assembler.feed(a)
        self.assertEqual(assembler.feed(b), message)

    @staticmethod
    def compact(raw, token=7):
        return [struct.pack('<BHB', 0xb2, token, i | (64 if i == 0 else 0) |
                (128 if off + 16 >= len(raw) else 0)) + raw[off:off+16]
                for i, off in enumerate(range(0, len(raw), 16))]

    def test_compact_all_sizes_require_opt_in_and_preserve_duplicates(self):
        for size in range(1, 513):
            raw = bytes(i & 255 for i in range(size))
            parts = self.compact(raw, 65535 if size % 2 else 0)
            a = Reassembler(allow_compact=True)
            for part in parts[:-1]:
                self.assertIsNone(a.feed(part))
                self.assertIsNone(a.feed(part))
            self.assertEqual(a.feed(parts[-1]), raw)
            with self.assertRaises(ValueError):
                Reassembler().feed(parts[0])
        self.assertEqual(len(self.compact(bytes(508))), 32)

    def test_compact_loss_conflict_mixed_versions_and_bounds(self):
        raw = bytes(i & 255 for i in range(508))
        parts = self.compact(raw)
        a = Reassembler(allow_compact=True)
        a.feed(parts[0])
        with self.assertRaises(ValueError):
            a.feed(parts[2])
        a.feed(parts[0])
        bad = bytearray(parts[0]); bad[-1] ^= 1
        with self.assertRaises(ValueError):
            a.feed(bad)
        a.feed(parts[0])
        with self.assertRaises(ValueError):
            a.feed(list(fragments(raw, 7))[1])
        bad = bytearray(parts[1]); bad[3] = 32
        with self.assertRaises(ValueError):
            a.feed(bad)
        for part in parts[:-1]:
            a.feed(part)
        self.assertEqual(a.feed(parts[-1]), raw)

    @staticmethod
    def bulk(raw, value_limit, token=7):
        capacity = value_limit - 4
        return [struct.pack('<BHB', 0xb3, token, i | (64 if i == 0 else 0) |
                (128 if off + capacity >= len(raw) else 0)) + raw[off:off+capacity]
                for i, off in enumerate(range(0, len(raw), capacity))]

    def test_bulk_sizes_and_opt_in_limits(self):
        for limit in (20, 21, 60, 182, 244):
            for size in range(1, 513):
                raw = bytes(i & 255 for i in range(size))
                parts = self.bulk(raw, limit, 65535 if size % 2 else 0)
                a = Reassembler(bulk_value_limit=limit)
                for part in parts[:-1]:
                    self.assertIsNone(a.feed(part))
                    self.assertIsNone(a.feed(part))
                self.assertEqual(a.feed(parts[-1]), raw)
                with self.assertRaises(ValueError):
                    Reassembler(allow_compact=True).feed(parts[0])
        for limit in (19, 245):
            with self.assertRaises(ValueError):
                Reassembler(bulk_value_limit=limit)

    def test_bulk_loss_conflict_and_negotiated_length(self):
        raw = bytes(i & 255 for i in range(508)); parts = self.bulk(raw, 182)
        self.assertEqual(len(parts), 3)
        a = Reassembler(bulk_value_limit=182)
        a.feed(parts[0])
        with self.assertRaises(ValueError): a.feed(parts[2])
        a.feed(parts[0]); bad = bytearray(parts[0]); bad[-1] ^= 1
        with self.assertRaises(ValueError): a.feed(bad)
        with self.assertRaises(ValueError): a.feed(parts[0][:-1])
        with self.assertRaises(ValueError): a.feed(self.bulk(raw, 244)[0])
        a.feed(parts[0])
        with self.assertRaises(ValueError): a.feed(list(fragments(raw, 7))[1])
        for part in parts[:-1]: a.feed(part)
        self.assertEqual(a.feed(parts[-1]), raw)


if __name__ == '__main__':
    unittest.main()
