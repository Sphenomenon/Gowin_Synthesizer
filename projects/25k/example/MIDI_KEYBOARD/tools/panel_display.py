#!/usr/bin/env python3
"""PL local-v1 screen client using Python's standard library and libusb.

USB2 interface 2, OUT 0x02 / IN 0x82, VID:PID fb9a:fb9b is shared with MK
settings. Run only one host controller on this interface at a time. MIDI uses
its separate interface. This local request/reply adaptation echoes the request
sequence in both response sequence and acknowledgement fields; it is not the
reference protocol's future full-duplex sequence model.

Examples::

    python3 tools/panel_display.py demo --seconds 10
    python3 tools/panel_display.py image picture.ppm --seconds 30
    python3 tools/panel_display.py hello
    python3 tools/panel_display.py decode '50 4c ...'

Images must be binary PPM P6, 428 x 142, maxval 255. RGB888 input is converted
to little-endian RGB565 and sent in bounded tiles. No Python packages are
required; libusb-1.0 must be installed. --library overrides its lookup path.

HEALTH runs every 50 ms, including during uploads and BUSY retries. Holding
the encoder's settings override suppresses output; the whole scene is resent
after resuming or observing the redraw flag. A TILE ACK means accepted only;
completion is reported only after FRAME_END returns DRAWN. Exiting stops the
heartbeat, allowing the device's 250 ms timeout to restore its local screen.
An uncertain/partial USB write is never retried: close, reopen and HELLO with
a new session instead. All responses and retries have bounded waits.
"""

from __future__ import annotations

import argparse
import ctypes as ct
import ctypes.util
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import secrets
import struct
import sys
import time
from typing import Any, Callable, Iterator

MAGIC = b"PL"
VERSION = 1
HEADER = struct.Struct("<2sBBIHHHBB")
HEADER_SIZE = HEADER.size
MAX_PAYLOAD = 512
WIDTH = 428
HEIGHT = 142
MAX_PIXELS = 248
VID, PID = 0xFB9A, 0xFB9B
INTERFACE, EP_OUT, EP_IN = 2, 0x02, 0x82
HELLO, HEALTH, TILE, END = 0x01, 0x02, 0x20, 0x21
CAPS, STATUS, ACK, DRAWN, ERROR = 0x81, 0x82, 0xA0, 0xA1, 0xFF
OK, SUPPRESSED, BUSY = 0, 1, 2
MANUAL, REMOTE, REDRAW = 1, 2, 4
STATUS_NAMES = {
    0: "ok", 1: "suppressed", 2: "busy", 3: "version", 4: "session",
    5: "sequence", 6: "format", 7: "bounds/frame", 8: "unknown command",
}


class PanelError(RuntimeError):
    """Transport failure or a rejected/inconsistent protocol transaction."""


class ReadTimeout(PanelError):
    """A read timed out; the outstanding request must not be rewritten."""


class PartialWriteError(PanelError):
    """Some outgoing bytes may have arrived: a new session is required."""


def _integer(name: str, value: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not 0 <= value <= maximum:
        raise ValueError(f"{name} must be in 0..{maximum}")
    return value


@dataclass(frozen=True)
class Frame:
    message_type: int
    session: int
    sequence: int
    acknowledgement: int = 0
    channel: int = 0
    credit: int = 0
    payload: bytes = b""
    reliable: bool = True


def encode_frame(frame: Frame) -> bytes:
    """Encode a structurally validated 16-byte header and up to 512 bytes."""
    _integer("message_type", frame.message_type, 255)
    _integer("session", frame.session, 0xFFFFFFFF)
    _integer("sequence", frame.sequence, 0xFFFF)
    _integer("acknowledgement", frame.acknowledgement, 0xFFFF)
    _integer("channel", frame.channel, 3)
    _integer("credit", frame.credit, 255)
    if not isinstance(frame.reliable, bool):
        raise TypeError("reliable must be a bool")
    if not isinstance(frame.payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes")
    payload = bytes(frame.payload)
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload exceeds 512 bytes")
    flags = int(frame.reliable) | (frame.channel << 1)
    return HEADER.pack(MAGIC, VERSION, frame.message_type, frame.session,
                       frame.sequence, frame.acknowledgement, len(payload),
                       flags, frame.credit) + payload


def decode_frame(data: bytes) -> Frame:
    """Decode exactly one complete PL local-v1 frame, rejecting reserved bits."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("frame must be bytes")
    data = bytes(data)
    if len(data) < HEADER_SIZE:
        raise ValueError("truncated PL header")
    magic, version, kind, session, seq, ack, length, flags, credit = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise ValueError("invalid PL magic")
    if version != VERSION:
        raise ValueError(f"unsupported PL version {version}")
    if flags & ~7:
        raise ValueError("reserved header flags must be zero")
    if length > MAX_PAYLOAD or len(data) != HEADER_SIZE + length:
        raise ValueError("invalid PL payload length")
    return Frame(kind, session, seq, ack, (flags >> 1) & 3, credit,
                 data[HEADER_SIZE:], bool(flags & 1))


@dataclass(frozen=True)
class Capabilities:
    width: int
    height: int
    pixel_format: int
    max_pixels: int
    max_payload: int
    heartbeat_ms: int

    @classmethod
    def decode(cls, payload: bytes) -> "Capabilities":
        if len(payload) != 12:
            raise PanelError("CAPS must contain exactly 12 bytes")
        width, height, pixel_format, reserved, pixels, maximum, heartbeat = struct.unpack(
            "<HHBBHHH", payload)
        if reserved or (width, height, pixel_format) != (WIDTH, HEIGHT, 1):
            raise PanelError("unsupported panel geometry or pixel format")
        if not 1 <= pixels <= MAX_PIXELS or not 18 <= maximum <= MAX_PAYLOAD or not heartbeat:
            raise PanelError("invalid panel capacities/heartbeat")
        if 16 + 2 * pixels > maximum:
            raise PanelError("CAPS tile capacity exceeds its payload limit")
        return cls(width, height, pixel_format, pixels, maximum, heartbeat)


@dataclass(frozen=True)
class DeviceStatus:
    status: int
    flags: int
    page: int
    frame: int

    @classmethod
    def decode(cls, payload: bytes) -> "DeviceStatus":
        if len(payload) != 8:
            raise PanelError("status response must contain exactly eight bytes")
        status, flags, page, frame = struct.unpack("<BBHI", payload)
        if status not in STATUS_NAMES or flags & ~7:
            raise PanelError("invalid response status/flags")
        return cls(status, flags, page, frame)

    @property
    def manual(self) -> bool:
        return bool(self.flags & MANUAL)

    @property
    def redraw(self) -> bool:
        return bool(self.flags & REDRAW)


def tile_payload(page: int, frame: int, x: int, y: int, width: int,
                 height: int, pixels: bytes) -> bytes:
    """Build one bounded RGB565LE rectangle with the reserved field zero."""
    for name, value in (("page", page), ("x", x), ("y", y),
                        ("width", width), ("height", height)):
        _integer(name, value, 0xFFFF)
    _integer("frame", frame, 0xFFFFFFFF)
    if not width or not height or x + width > WIDTH or y + height > HEIGHT:
        raise ValueError("tile is outside the 428 x 142 panel")
    if width * height > MAX_PIXELS:
        raise ValueError("tile exceeds 248 pixels")
    if not isinstance(pixels, (bytes, bytearray, memoryview)) or len(pixels) != width * height * 2:
        raise ValueError("tile pixels must be exactly width * height * 2 bytes")
    return struct.pack("<HHIHHHH", page, 0, frame, x, y, width, height) + bytes(pixels)


def iter_tiles(image: bytes, tile_width: int = 62, tile_height: int = 4,
               max_pixels: int = MAX_PIXELS) -> Iterator[tuple[int, int, int, int, bytes]]:
    """Split a complete RGB565LE scene, preserving short right/bottom edges."""
    if len(image) != WIDTH * HEIGHT * 2:
        raise ValueError("image must contain exactly 428 * 142 RGB565 pixels")
    if (not isinstance(tile_width, int) or not isinstance(tile_height, int) or
            not 1 <= tile_width <= WIDTH or not 1 <= tile_height <= HEIGHT or
            tile_width * tile_height > max_pixels):
        raise ValueError("invalid tile dimensions/capacity")
    for y in range(0, HEIGHT, tile_height):
        height = min(tile_height, HEIGHT - y)
        for x in range(0, WIDTH, tile_width):
            width = min(tile_width, WIDTH - x)
            pixels = b"".join(image[((y + row) * WIDTH + x) * 2:
                                    ((y + row) * WIDTH + x + width) * 2]
                              for row in range(height))
            yield x, y, width, height, pixels


def rgb888_to_rgb565(rgb: bytes) -> bytes:
    if len(rgb) % 3:
        raise ValueError("RGB888 byte count must be divisible by three")
    pixels = bytearray(len(rgb) // 3 * 2)
    for index in range(len(rgb) // 3):
        red, green, blue = rgb[index * 3:index * 3 + 3]
        value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        struct.pack_into("<H", pixels, index * 2, value)
    return bytes(pixels)


def read_ppm(path: str | Path) -> bytes:
    """Read strict P6; do not mistake a whitespace-valued first pixel for a header."""
    data = Path(path).read_bytes()
    position = 0

    def token() -> bytes:
        nonlocal position
        while position < len(data):
            if data[position] in b" \t\r\n\v\f":
                position += 1
            elif data[position] == 35:
                newline = data.find(b"\n", position)
                position = len(data) if newline < 0 else newline + 1
            else:
                break
        start = position
        while position < len(data) and data[position] not in b" \t\r\n\v\f#":
            position += 1
        if position == start:
            raise ValueError("incomplete PPM header")
        return data[start:position]

    if token() != b"P6":
        raise ValueError("image must be binary PPM P6")
    try:
        width, height, maximum = int(token()), int(token()), int(token())
    except ValueError as error:
        raise ValueError("invalid PPM dimensions/maxval") from error
    if (width, height, maximum) != (WIDTH, HEIGHT, 255):
        raise ValueError("PPM must be exactly 428 x 142 with maxval 255")
    if position >= len(data) or data[position] not in b" \t\r\n\v\f":
        raise ValueError("PPM raster requires a whitespace separator")
    if data[position:position + 2] == b"\r\n":
        position += 2
    else:
        position += 1
    rgb = data[position:]
    if len(rgb) != WIDTH * HEIGHT * 3:
        raise ValueError("PPM raster has a truncated or extra pixel count")
    return rgb888_to_rgb565(rgb)


def demo_image() -> bytes:
    """Generate color bars, a grayscale ramp and a pixel alignment border."""
    colors = (0xF800, 0xFFE0, 0x07E0, 0x07FF, 0x001F, 0xF81F, 0xFFFF, 0x0000)
    image = bytearray(WIDTH * HEIGHT * 2)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if x in (0, WIDTH - 1) or y in (0, HEIGHT - 1):
                color = 0xFFFF
            elif y < HEIGHT * 2 // 3:
                color = colors[min(7, x * 8 // WIDTH)]
            else:
                level = x * 255 // (WIDTH - 1)
                color = ((level >> 3) << 11) | ((level >> 2) << 5) | (level >> 3)
                if (x // 8 + y // 8) % 2:
                    color &= 0x7BEF
            struct.pack_into("<H", image, (y * WIDTH + x) * 2, color)
    return bytes(image)


class UsbTransport:
    """One claimed vendor interface with byte-stream reads of at most 512 B."""

    def __init__(self, library: str | None = None, timeout_ms: int = 80):
        self.library = library
        self.timeout_ms = timeout_ms
        self.context = ct.c_void_p()
        self.handle: Any = None
        self.claimed = False
        self.poisoned = False
        self.lib: Any = None

    def __enter__(self) -> "UsbTransport":
        library = self.library or ctypes.util.find_library("usb-1.0")
        if not library:
            for candidate in ("/opt/homebrew/lib/libusb-1.0.dylib",
                              "/usr/local/lib/libusb-1.0.dylib", "libusb-1.0.so.0"):
                if Path(candidate).exists():
                    library = candidate
                    break
        if not library:
            raise PanelError("libusb-1.0 not found; pass --library PATH")
        try:
            self.lib = ct.CDLL(library)
            declarations = {
                "libusb_init": ([ct.POINTER(ct.c_void_p)], ct.c_int),
                "libusb_exit": ([ct.c_void_p], None),
                "libusb_open_device_with_vid_pid":
                    ([ct.c_void_p, ct.c_uint16, ct.c_uint16], ct.c_void_p),
                "libusb_claim_interface": ([ct.c_void_p, ct.c_int], ct.c_int),
                "libusb_release_interface": ([ct.c_void_p, ct.c_int], ct.c_int),
                "libusb_close": ([ct.c_void_p], None),
                "libusb_bulk_transfer": ([ct.c_void_p, ct.c_ubyte, ct.POINTER(ct.c_ubyte),
                                          ct.c_int, ct.POINTER(ct.c_int), ct.c_uint], ct.c_int),
                "libusb_error_name": ([ct.c_int], ct.c_char_p),
            }
            for name, (arguments, result) in declarations.items():
                function = getattr(self.lib, name)
                function.argtypes, function.restype = arguments, result
            self._check(self.lib.libusb_init(ct.byref(self.context)), "initialize libusb")
            self.handle = self.lib.libusb_open_device_with_vid_pid(self.context, VID, PID)
            if not self.handle:
                raise PanelError(f"USB {VID:04x}:{PID:04x} not found or cannot be opened")
            self._check(self.lib.libusb_claim_interface(self.handle, INTERFACE), "claim interface 2")
            self.claimed = True
            return self
        except BaseException:
            self.close()
            raise

    def _check(self, result: int, operation: str) -> None:
        if result < 0:
            name = self.lib.libusb_error_name(result)
            label = name.decode("ascii", errors="replace") if name else str(result)
            raise PanelError(f"{operation}: {label} ({result})")

    def write(self, data: bytes) -> None:
        if self.poisoned or not self.handle:
            raise PartialWriteError("USB session is closed/uncertain; reopen and use a new HELLO session")
        outgoing = (ct.c_ubyte * len(data)).from_buffer_copy(data)
        transferred = ct.c_int()
        result = self.lib.libusb_bulk_transfer(self.handle, EP_OUT, outgoing, len(data),
                                              ct.byref(transferred), self.timeout_ms)
        if result < 0 or transferred.value != len(data):
            self.poisoned = True
            raise PartialWriteError(f"uncertain bulk OUT ({transferred.value}/{len(data)} bytes, "
                                    f"result {result}); reopen with a new HELLO session")

    def read(self) -> bytes:
        incoming = (ct.c_ubyte * 512)()
        transferred = ct.c_int()
        result = self.lib.libusb_bulk_transfer(self.handle, EP_IN, incoming, 512,
                                              ct.byref(transferred), self.timeout_ms)
        if result == -7:
            if transferred.value:
                return bytes(incoming[:transferred.value])
            raise ReadTimeout("bulk IN timed out")
        self._check(result, "bulk IN")
        return bytes(incoming[:transferred.value])

    def close(self) -> None:
        if self.handle:
            try:
                if self.claimed:
                    self.lib.libusb_release_interface(self.handle, INTERFACE)
            finally:
                self.claimed = False
                self.lib.libusb_close(self.handle)
                self.handle = None
        if self.context.value:
            self.lib.libusb_exit(self.context)
            self.context = ct.c_void_p()

    def __exit__(self, *_exc: Any) -> None:
        self.close()


class PanelClient:
    """Serialized stop-and-wait client; BUSY retries retain the exact request."""

    def __init__(self, transport: Any, session: int | None = None, *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.transport = transport
        self.session = session if session is not None else (secrets.randbits(32) or 1)
        _integer("session", self.session, 0xFFFFFFFF)
        if not self.session:
            raise ValueError("session must be nonzero")
        self.clock, self.sleep = clock, sleep
        self.sequences = {0: 0, 1: 0}
        self.capabilities: Capabilities | None = None
        self.status = DeviceStatus(OK, REDRAW, 0, 0)
        self.health_interval = 0.05
        self.last_health = float("-inf")
        self._incoming = bytearray()
        self._broken = False

    def _read_frame(self) -> Frame:
        empty_reads = 0
        for _ in range(32):
            if len(self._incoming) >= HEADER_SIZE:
                length = struct.unpack_from("<H", self._incoming, 12)[0]
                if self._incoming[:2] != MAGIC or length > MAX_PAYLOAD:
                    raise PanelError("invalid response stream header")
                total = HEADER_SIZE + length
                if len(self._incoming) >= total:
                    data = bytes(self._incoming[:total])
                    del self._incoming[:total]
                    try:
                        return decode_frame(data)
                    except (ValueError, TypeError) as error:
                        raise PanelError(str(error)) from error
            try:
                data = self.transport.read()
            except ReadTimeout:
                data = b""
            if not data:
                empty_reads += 1
                if empty_reads >= 3:
                    raise PanelError("no complete response after three empty/timed-out reads")
            else:
                self._incoming.extend(data)
                if len(self._incoming) > 4096:
                    raise PanelError("response stream exceeds bounded receive buffer")
        raise PanelError("response exceeded bounded fragmented-read count")

    def _exchange(self, kind: int, payload: bytes, channel: int) -> Frame:
        if self._broken:
            raise PanelError("session is uncertain; reopen and start a new HELLO session")
        sequence = self.sequences[channel]
        outgoing = encode_frame(Frame(kind, self.session, sequence, channel=channel, payload=payload))
        busy_deadline = self.clock() + 2.0
        try:
            for attempt in range(2000):
                # The only rewrite is after an explicit BUSY rejection. A read
                # timeout or partial OUT is never treated as permission to retry.
                self.transport.write(outgoing)
                response = None
                for _ in range(8):
                    candidate = self._read_frame()
                    if (candidate.session, candidate.channel, candidate.sequence,
                            candidate.acknowledgement) != (self.session, channel, sequence, sequence):
                        continue  # Discard a bounded number of stale replies.
                    if not candidate.reliable:
                        raise PanelError("response is missing the reliable flag")
                    response = candidate
                    break
                if response is None:
                    raise PanelError("too many stale responses")
                expected = {HELLO: CAPS, HEALTH: STATUS, TILE: ACK, END: DRAWN}[kind]
                if response.message_type == CAPS and kind == HELLO:
                    Capabilities.decode(response.payload)
                    self.sequences[channel] = (sequence + 1) & 0xFFFF
                    return response
                status = DeviceStatus.decode(response.payload)
                allowed = response.message_type == expected or response.message_type == ERROR
                if kind == END and status.status in (SUPPRESSED, BUSY) and response.message_type == ACK:
                    allowed = True
                if not allowed:
                    raise PanelError(f"unexpected response type 0x{response.message_type:02x}")
                self.status = status
                if status.status == BUSY:
                    if response.message_type == ERROR:
                        raise PanelError("BUSY must be a command response")
                    if self.clock() >= busy_deadline:
                        raise PanelError("device remained BUSY beyond the two-second deadline")
                    if channel == 1:
                        self.maybe_health()
                    self.sleep(0.001)
                    continue
                if status.status not in (OK, SUPPRESSED) or response.message_type == ERROR:
                    raise PanelError(f"device rejected request: {STATUS_NAMES[status.status]}")
                if kind == END and status.status == OK and response.message_type != DRAWN:
                    raise PanelError("FRAME_END requires DRAWN, not an acceptance ACK")
                self.sequences[channel] = (sequence + 1) & 0xFFFF
                return response
            raise PanelError("device remained BUSY after 2000 bounded retries")
        except (PanelError, ValueError, TypeError) as error:
            self._broken = True
            if isinstance(error, PanelError):
                raise
            raise PanelError(str(error)) from error

    def hello(self) -> Capabilities:
        if self.capabilities is not None:
            raise PanelError("HELLO already completed; create a new client for a new session")
        response = self._exchange(HELLO, b"", 0)
        self.capabilities = Capabilities.decode(response.payload)
        self.health_interval = min(0.05, self.capabilities.heartbeat_ms / 4000)
        return self.capabilities

    def health(self) -> DeviceStatus:
        if self.capabilities is None:
            raise PanelError("HELLO must complete before HEALTH")
        response = self._exchange(HEALTH, b"", 0)
        self.status = DeviceStatus.decode(response.payload)
        self.last_health = self.clock()
        return self.status

    def maybe_health(self) -> DeviceStatus:
        if self.clock() - self.last_health >= self.health_interval:
            return self.health()
        return self.status

    def tile(self, page: int, frame: int, x: int, y: int, width: int,
             height: int, pixels: bytes) -> DeviceStatus:
        if self.capabilities is None:
            raise PanelError("HELLO must complete before TILE")
        payload = tile_payload(page, frame, x, y, width, height, pixels)
        if width * height > self.capabilities.max_pixels or len(payload) > self.capabilities.max_payload:
            raise ValueError("tile exceeds the advertised capabilities")
        response = self._exchange(TILE, payload, 1)
        status = DeviceStatus.decode(response.payload)
        if (status.page, status.frame) != (page, frame):
            self._broken = True
            raise PanelError("TILE response refers to a different page/frame")
        return status

    def end(self, page: int, frame: int) -> DeviceStatus:
        _integer("page", page, 0xFFFF)
        _integer("frame", frame, 0xFFFFFFFF)
        response = self._exchange(END, struct.pack("<HHI", page, 0, frame), 1)
        status = DeviceStatus.decode(response.payload)
        if (status.page, status.frame) != (page, frame):
            self._broken = True
            raise PanelError("FRAME_END response refers to a different page/frame")
        return status


class SceneController:
    """Retain a complete scene so manual override/resume always repaints it."""

    def __init__(self, client: PanelClient, image: bytes, page: int = 0):
        if len(image) != WIDTH * HEIGHT * 2:
            raise ValueError("scene must be a complete 428 x 142 RGB565 image")
        _integer("page", page, 0xFFFF)
        self.client, self.image, self.page = client, bytes(image), page
        self.frame = 0
        self.needs_redraw = True
        self.completed_frames = 0

    def step(self) -> bool:
        """Check HEALTH and, if needed, upload the whole scene; return drawn."""
        status = self.client.health()
        if status.manual:
            self.needs_redraw = True
            return False
        if status.redraw or not status.flags & REMOTE:
            self.needs_redraw = True
        if not self.needs_redraw:
            return False
        self.frame = (self.frame + 1) & 0xFFFFFFFF
        capabilities = self.client.capabilities
        if capabilities is None:
            raise PanelError("HELLO must complete before displaying a scene")
        tile_height = min(4, capabilities.max_pixels)
        tile_width = min(62, capabilities.max_pixels // tile_height)
        for x, y, width, height, pixels in iter_tiles(
                self.image, tile_width, tile_height, capabilities.max_pixels):
            if self.client.maybe_health().manual:
                self.needs_redraw = True
                return False
            result = self.client.tile(self.page, self.frame, x, y, width, height, pixels)
            if result.status == SUPPRESSED or result.manual:
                self.needs_redraw = True
                return False
        result = self.client.end(self.page, self.frame)
        if result.status == SUPPRESSED or result.manual:
            self.needs_redraw = True
            return False
        self.needs_redraw = False
        self.completed_frames += 1
        return True


def _number(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected an integer, optionally 0x hexadecimal") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--library", help="path to libusb-1.0 shared library")
    parser.add_argument("--session", type=_number, help="nonzero uint32 session (default: random)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hello", help="query capabilities without sending pixels")
    decode = commands.add_parser("decode", help="decode one hex PL frame without USB")
    decode.add_argument("hex")
    demo = commands.add_parser("demo", help="show the built-in color/alignment pattern")
    image = commands.add_parser("image", help="show an exact 428 x 142 binary PPM P6")
    image.add_argument("file", type=Path)
    for command in (demo, image):
        command.add_argument("--seconds", type=float, default=10)
        command.add_argument("--page", type=_number, default=0)
    args = parser.parse_args(argv)
    try:
        if args.command == "decode":
            frame = decode_frame(bytes.fromhex(args.hex))
            fields = asdict(frame)
            fields["payload"] = frame.payload.hex()
            print(json.dumps(fields, sort_keys=True))
            return 0
        if args.command != "hello" and not 0 < args.seconds < 86400:
            raise ValueError("--seconds must be greater than zero and less than 86400")
        pixels = None if args.command == "hello" else (
            read_ppm(args.file) if args.command == "image" else demo_image())
        with UsbTransport(args.library) as transport:
            client = PanelClient(transport, args.session)
            print(json.dumps({"session": client.session, "capabilities": asdict(client.hello())}, sort_keys=True))
            if args.command == "hello":
                return 0
            scene = SceneController(client, pixels, args.page)
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                if scene.step():
                    print(f"DRAWN page={scene.page} frame={scene.frame} (complete scene)", flush=True)
                time.sleep(min(client.health_interval, max(0, deadline - time.monotonic())))
        return 0
    except KeyboardInterrupt:
        return 130
    except (PanelError, ValueError, TypeError, OSError) as error:
        print(f"panel_display: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
