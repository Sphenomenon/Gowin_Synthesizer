#!/usr/bin/env python3
"""PL codec and end-to-end host state tests; no USB device is required."""

import contextlib
import ctypes as ct
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import panel_display as protocol


def raw_frame(kind, session=0x12345678, seq=0, ack=0, channel=0,
              payload=b"", credit=1, flags=None):
    """Independent wire oracle uses explicit layout, not the production codec."""
    return struct.pack("<2sBBIHHHBB", b"PL", 1, kind, session, seq, ack,
                       len(payload), 1 | channel << 1 if flags is None else flags,
                       credit) + payload


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class DeviceEmulator:
    """Small independent device model checking channels, sequence and sessions."""

    def __init__(self, clock=None):
        self.clock = clock or FakeClock()
        self.session = None
        self.expected = {0: 0, 1: 0}
        self.queue = []
        self.writes = []
        self.health_times = []
        self.tiles = []
        self.ends = []
        self.manual = False
        self.remote = False
        self.redraw = True
        self.busy = 0
        self.end_busy = 0
        self.suppress_next = False
        self.response_hook = None
        self.chunk_size = 512

    def write(self, data):
        self.clock.sleep(0.0008)
        magic, version, kind, session, seq, ack, length, flags, credit = struct.unpack_from(
            "<2sBBIHHHBB", data)
        assert (magic, version, ack, credit) == (b"PL", 1, 0, 0)
        assert length == len(data) - 16 and flags in (1, 3)
        channel = flags >> 1
        payload = data[16:]
        self.writes.append(data)
        status = 0
        response_kind = {1: 0x81, 2: 0x82, 0x20: 0xA0, 0x21: 0xA1}[kind]
        page = frame = 0
        if kind == 1:
            assert channel == 0 and seq == 0 and session != 0 and not payload
            self.session = session
            self.expected = {0: 1, 1: 0}
            result = struct.pack("<HHBBHHH", 428, 142, 1, 0, 248, 512, 250)
        else:
            assert session == self.session and seq == self.expected[channel]
            if kind == 2:
                assert channel == 0 and not payload
                self.health_times.append(self.clock())
            else:
                assert channel == 1
                page, reserved, frame = struct.unpack_from("<HHI", payload)
                assert reserved == 0
                if kind == 0x20:
                    x, y, width, height = struct.unpack_from("<HHHH", payload, 8)
                    assert width * height <= 248 and length == 16 + width * height * 2
                if self.suppress_next:
                    self.suppress_next = False
                    self.manual = True
                    self.remote = False
                    self.redraw = True
                if self.manual:
                    status, response_kind = 1, 0xA0
                elif (self.busy if kind == 0x20 else self.end_busy) > 0:
                    status, response_kind = 2, 0xA0
                    if kind == 0x20:
                        self.busy -= 1
                    else:
                        self.end_busy -= 1
                elif kind == 0x20:
                    self.tiles.append((page, frame, x, y, width, height, payload[16:]))
                    self.remote = True
                    self.redraw = False
                else:
                    self.ends.append((page, frame))
                    self.remote = True
                    self.redraw = False
            state_flags = int(self.manual) | int(self.remote) << 1 | int(self.redraw) << 2
            result = struct.pack("<BBHI", status, state_flags, page, frame)
            if status != 2:
                self.expected[channel] = (seq + 1) & 0xFFFF
        response = raw_frame(response_kind, session, seq, seq, channel, result,
                             credit=0 if kind == 0x20 and not status else 1)
        if self.response_hook:
            response = self.response_hook(response)
        self.queue.append(response)

    def read(self):
        self.clock.sleep(0.0008)
        if not self.queue:
            raise protocol.ReadTimeout("no mock response")
        chunk = self.queue[0][:self.chunk_size]
        self.queue[0] = self.queue[0][self.chunk_size:]
        if not self.queue[0]:
            self.queue.pop(0)
        return chunk


def client_for(device):
    return protocol.PanelClient(device, 0x12345678, clock=device.clock,
                                sleep=device.clock.sleep)


class CodecTest(unittest.TestCase):
    def test_wire_header_and_little_endian_metadata(self):
        payload = protocol.tile_payload(0x1234, 0x89ABCDEF, 420, 140, 8, 2,
                                        b"\x00\xf8" * 16)
        expected = bytes.fromhex("34 12 00 00 ef cd ab 89 a4 01 8c 00 08 00 02 00")
        self.assertEqual(payload[:16], expected)
        frame = protocol.Frame(0x20, 0x12345678, 0x9ABC, channel=1, payload=payload)
        wire = protocol.encode_frame(frame)
        self.assertEqual(wire[:16], bytes.fromhex(
            "50 4c 01 20 78 56 34 12 bc 9a 00 00 30 00 03 00"))
        self.assertEqual(protocol.decode_frame(wire), frame)

    def test_codec_boundaries_and_invalid_frames(self):
        frame = protocol.Frame(255, 0xFFFFFFFF, 65535, 65535, 3, 255, bytes(512))
        self.assertEqual(protocol.decode_frame(protocol.encode_frame(frame)), frame)
        valid = raw_frame(1)
        mutations = [valid[:15], valid + b"x", b"MK" + valid[2:],
                     valid[:2] + b"\x02" + valid[3:],
                     valid[:14] + b"\x09" + valid[15:],
                     valid[:12] + b"\x01\x02" + valid[14:]]
        for wire in mutations:
            with self.subTest(wire=wire.hex()), self.assertRaises(ValueError):
                protocol.decode_frame(wire)
        for frame in (protocol.Frame(1, 0, -1), protocol.Frame(1, 0, 0, channel=4),
                      protocol.Frame(1, 0, 0, payload=bytes(513))):
            with self.assertRaises(ValueError):
                protocol.encode_frame(frame)
        with self.assertRaises(TypeError):
            protocol.encode_frame(protocol.Frame(True, 1, 0))

    def test_tile_bounds_and_exact_pixel_count(self):
        invalid = [(0, 0, 0, 1, b""), (427, 0, 2, 1, bytes(4)),
                   (0, 141, 1, 2, bytes(4)), (0, 0, 249, 1, bytes(498)),
                   (0, 0, 2, 1, bytes(2))]
        for x, y, width, height, pixels in invalid:
            with self.subTest(rect=(x, y, width, height)), self.assertRaises(ValueError):
                protocol.tile_payload(0, 1, x, y, width, height, pixels)

    def test_edge_tiles_reassemble_every_pixel_once(self):
        # Coordinates encode their position, so row-stride mistakes are visible.
        image = b"".join(struct.pack("<H", (x + y * 428) & 65535)
                         for y in range(142) for x in range(428))
        rebuilt = bytearray(len(image))
        coverage = bytearray(428 * 142)
        tiles = list(protocol.iter_tiles(image))
        self.assertEqual((tiles[-1][0:4]), (372, 140, 56, 2))
        for x, y, width, height, pixels in tiles:
            self.assertLessEqual(width * height, 248)
            for row in range(height):
                start = (y + row) * 428 + x
                rebuilt[start * 2:(start + width) * 2] = pixels[row * width * 2:(row + 1) * width * 2]
                for index in range(start, start + width):
                    coverage[index] += 1
        self.assertEqual(rebuilt, image)
        self.assertEqual(set(coverage), {1})

    def test_rgb565_and_ppm_binary_first_pixel(self):
        self.assertEqual(protocol.rgb888_to_rgb565(bytes.fromhex("ff0000 00ff00 0000ff")),
                         bytes.fromhex("00f8 e007 1f00"))
        rgb = b"\x0a\x23\x20" + bytes(428 * 142 * 3 - 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.ppm"
            path.write_bytes(b"P6\n# test comment\n428 142\n255\n" + rgb)
            self.assertEqual(protocol.read_ppm(path), protocol.rgb888_to_rgb565(rgb))
            path.write_bytes(b"P6\n428 142\n255\n" + rgb[:-1])
            with self.assertRaises(ValueError):
                protocol.read_ppm(path)
            path.write_bytes(b"P6\n1 1\n255\n\x00\x00\x00")
            with self.assertRaises(ValueError):
                protocol.read_ppm(path)

    def test_capability_and_status_reserved_validation(self):
        caps = struct.pack("<HHBBHHH", 428, 142, 1, 0, 248, 512, 250)
        self.assertEqual(protocol.Capabilities.decode(caps).heartbeat_ms, 250)
        for payload in (caps[:-1], caps[:5] + b"\x01" + caps[6:],
                        struct.pack("<HHBBHHH", 428, 142, 1, 0, 248, 500, 250)):
            with self.assertRaises(protocol.PanelError):
                protocol.Capabilities.decode(payload)
        with self.assertRaises(protocol.PanelError):
            protocol.DeviceStatus.decode(struct.pack("<BBHI", 0, 8, 0, 0))


class ClientTest(unittest.TestCase):
    def test_busy_retries_keep_sequence_and_suppressed_advances(self):
        device = DeviceEmulator()
        client = client_for(device)
        client.hello()
        client.health()
        device.busy = 300  # Model > 600 ms startup, longer than the LCD boot.
        status = client.tile(3, 7, 0, 0, 1, 1, b"\x00\xf8")
        self.assertEqual(status.status, protocol.OK)
        requests = [wire for wire in device.writes if wire[3] == 0x20]
        self.assertEqual(len(requests), 301)
        self.assertEqual(len(set(requests)), 1)
        self.assertEqual(client.sequences[1], 1)
        self.assertGreater(device.clock(), 0.6)
        self.assertGreater(len(device.health_times), 1)
        self.assertLess(max(b - a for a, b in zip(device.health_times, device.health_times[1:])), 0.1)
        device.suppress_next = True
        self.assertEqual(client.tile(3, 7, 1, 0, 1, 1, b"\xe0\x07").status,
                         protocol.SUPPRESSED)
        self.assertEqual(client.sequences[1], 2)
        self.assertEqual(client.end(3, 7).status, protocol.SUPPRESSED)
        self.assertEqual(client.sequences[1], 3)

    def test_busy_deadline_is_bounded_without_sequence_advance(self):
        device = DeviceEmulator()
        client = client_for(device)
        client.hello()
        device.busy = 10000
        with self.assertRaisesRegex(protocol.PanelError, "BUSY"):
            client.tile(0, 1, 0, 0, 1, 1, bytes(2))
        self.assertEqual(client.sequences[1], 0)
        self.assertLess(device.clock(), 2.1)

    def test_end_busy_ack_is_accepted_until_drawn(self):
        device = DeviceEmulator()
        client = client_for(device)
        client.hello()
        client.tile(1, 9, 0, 0, 1, 1, bytes(2))
        self.assertFalse(device.ends, "TILE acceptance must not be treated as drawn")
        device.end_busy = 3
        result = client.end(1, 9)
        self.assertEqual(result.status, protocol.OK)
        self.assertEqual(device.ends, [(1, 9)])
        ends = [wire for wire in device.writes if wire[3] == 0x21]
        self.assertEqual(len(ends), 4)
        self.assertEqual(len(set(ends)), 1)

    def test_fragmented_coalesced_and_stale_response_reads(self):
        device = DeviceEmulator()
        device.chunk_size = 7
        client = client_for(device)
        client.hello()
        self.assertEqual(client.sequences, {0: 1, 1: 0})
        device.chunk_size = 512
        def add_stale(response):
            stale = bytearray(response)
            stale[4:8] = struct.pack("<I", 0xFFFFFFFF)
            return bytes(stale) + response
        device.response_hook = add_stale
        self.assertEqual(client.health().status, 0)
        self.assertEqual(client.sequences[0], 2)
        self.assertFalse(client._incoming)

    def test_wrong_ack_channel_type_and_length_fail_boundedly(self):
        for mutation in ("ack", "channel", "type", "length", "unreliable"):
            with self.subTest(mutation=mutation):
                device = DeviceEmulator()
                client = client_for(device)
                client.hello()
                def corrupt(response, mutation=mutation):
                    wire = bytearray(response)
                    if mutation == "ack":
                        wire[10:12] = b"\xff\xff"
                    elif mutation == "channel":
                        wire[14] = 3
                    elif mutation == "type":
                        wire[3] = 0xA0
                    elif mutation == "length":
                        wire[12:14] = b"\x07\x00"
                    else:
                        wire[14] = 0
                    return bytes(wire)
                device.response_hook = corrupt
                with self.assertRaises(protocol.PanelError):
                    client.health()
                self.assertEqual(client.sequences[0], 1)
                self.assertEqual(len(device.writes), 2, "read failures must not rewrite requests")
                with self.assertRaises(protocol.PanelError):
                    client.health()
                self.assertEqual(len(device.writes), 2, "uncertain session requires a new HELLO")

    def test_empty_read_limit_and_partial_write_do_not_retry(self):
        class EmptyTransport:
            def __init__(self):
                self.writes = self.reads = 0
            def write(self, data):
                self.writes += 1
            def read(self):
                self.reads += 1
                return b""
        transport = EmptyTransport()
        client = protocol.PanelClient(transport, 1)
        with self.assertRaises(protocol.PanelError):
            client.hello()
        self.assertEqual((transport.writes, transport.reads), (1, 3))

        transport = EmptyTransport()
        transport.write = mock.Mock(side_effect=protocol.PartialWriteError("partial OUT"))
        client = protocol.PanelClient(transport, 1)
        with self.assertRaises(protocol.PartialWriteError):
            client.hello()
        self.assertEqual(transport.write.call_count, 1)
        self.assertEqual(transport.reads, 0)

    def test_manual_override_and_redraw_resume_send_whole_scene(self):
        device = DeviceEmulator()
        client = client_for(device)
        client.hello()
        scene = protocol.SceneController(client, protocol.demo_image(), page=4)
        self.assertTrue(scene.step())
        first = list(device.tiles)
        self.assertEqual(len(first), 252)
        self.assertEqual(scene.completed_frames, 1)
        self.assertFalse(scene.step(), "static scene only needs HEALTH")
        self.assertEqual(len(device.tiles), len(first))
        device.manual, device.remote, device.redraw = True, False, True
        self.assertFalse(scene.step())
        self.assertEqual(len(device.tiles), len(first), "manual settings suppress all pixel requests")
        device.manual = False
        self.assertTrue(scene.step())
        second = device.tiles[len(first):]
        self.assertEqual(len(second), len(first))
        self.assertEqual([tile[2:] for tile in second], [tile[2:] for tile in first])
        self.assertNotEqual(first[0][1], second[0][1])
        self.assertEqual(scene.completed_frames, 2)
        self.assertEqual(len(device.ends), 2)
        self.assertLess(max(b - a for a, b in zip(device.health_times, device.health_times[1:])), 0.1)
        device.redraw = True  # A missed canvas also requires a complete resend.
        self.assertTrue(scene.step())
        self.assertEqual(len(device.tiles), len(first) * 3)

    def test_override_during_upload_does_not_report_completion(self):
        device = DeviceEmulator()
        client = client_for(device)
        client.hello()
        scene = protocol.SceneController(client, bytes(428 * 142 * 2))
        device.suppress_next = True
        self.assertFalse(scene.step())
        self.assertEqual(scene.completed_frames, 0)
        self.assertFalse(device.ends)
        self.assertTrue(scene.needs_redraw)

    def test_usb_short_write_poisoning_and_partial_timeout_read(self):
        transport = protocol.UsbTransport()
        transport.handle = 1
        calls = []
        class Library:
            @staticmethod
            def libusb_bulk_transfer(handle, endpoint, buffer, length, transferred, timeout):
                calls.append(endpoint)
                ct.cast(transferred, ct.POINTER(ct.c_int))[0] = length - 1 if endpoint == 2 else 3
                if endpoint == 0x82:
                    buffer[0], buffer[1], buffer[2] = 80, 76, 1
                    return -7
                return 0
        transport.lib = Library()
        with self.assertRaises(protocol.PartialWriteError):
            transport.write(bytes(16))
        with self.assertRaises(protocol.PartialWriteError):
            transport.write(bytes(16))
        self.assertEqual(calls, [2])
        self.assertEqual(transport.read(), b"PL\x01")

    def test_decode_cli_does_not_open_usb(self):
        output = io.StringIO()
        with mock.patch.object(protocol, "UsbTransport") as usb, contextlib.redirect_stdout(output):
            result = protocol.main(["decode", raw_frame(1).hex()])
        self.assertEqual(result, 0)
        usb.assert_not_called()
        self.assertIn('"session": 305419896', output.getvalue())


if __name__ == "__main__":
    unittest.main()
