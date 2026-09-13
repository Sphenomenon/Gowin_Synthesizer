"""UART wire protocol and unit conversions, shared by the CLI and GUI."""
from __future__ import annotations

from dataclasses import dataclass
import binascii
import math
import struct

SYNC = b"\xa5\x5a"
UNITY = 0x80000000
DEFAULT_SAMPLE_RATE = 50_000_000 / 1024
VOICE_COUNT = 32
OPCODES = {"ping": 0, "note-on": 1, "note-off": 2, "pitch": 3,
           "velocity": 4, "waveform": 5, "attack": 6, "decay": 7,
           "sustain": 8, "release": 9, "panic": 10, "memory-status": 11,
           "video-status": 12, "voice-status": 13, "latency-status": 14, "voice-onset": 15,
           "master-volume": 16, "lr-balance": 17}
OUTPUT_OPCODES = (OPCODES["master-volume"], OPCODES["lr-balance"])
OPCODE_NAMES = {value: name.upper().replace("-", "_") for name, value in OPCODES.items()}
WAVEFORMS = {"triangle": 0, "pulse": 1, "sine": 2}
STATUS = {0: "OK", 1: "unknown opcode", 2: "invalid voice",
          3: "invalid value or flags", 4: "malformed internal record"}
MEMORY_FLAG_BITS = {"calibrated": 0, "bist_done": 1, "bist_failed": 2,
                    "front_valid": 3, "fetch_fault": 4, "underrun_seen": 5,
                    "ddr_pll_locked": 6, "video_pll_locked": 7}
VIDEO_FLAG_BITS = {"hpd": 0, "video_locked": 1, "pixel_reset_n": 2,
                   "scanout_reset_n": 3, "serializer_reset": 4, "window_valid": 5}
VIDEO_STATUS_BYTES = 16
LATENCY_STATUS_BYTES = 64
VOICE_ONSET_STATUS_BYTES = 32
VIDEO_CLOCK_QUANTIZATION_MHZ = 0.1024  # 1024 pixels / nominal 10 ms window.


def decode_memory_flags(flags: int) -> dict[str, bool]:
    """Decode the 0x0B status byte; bits are observations, not a board-test verdict."""
    if type(flags) is not int or not 0 <= flags <= 255:
        raise ValueError("memory flags must be one unsigned byte")
    return {name: bool(flags & (1 << bit)) for name, bit in MEMORY_FLAG_BITS.items()}


def decode_video_status(data: bytes) -> dict:
    """Decode one schema-1 snapshot; HPD/PLL flags are not receiver-lock evidence."""
    if not isinstance(data, (bytes, bytearray)) or len(data) != VIDEO_STATUS_BYTES:
        raise ValueError("video status must contain exactly 16 bytes")
    if data[0] != 1:
        raise ValueError(f"unsupported video-status schema {data[0]}; expected 1")
    if data[1] & 0xC0:
        raise ValueError("video-status schema 1 has nonzero reserved flag bits")
    schema, flags, blocks, vblank_frames, rendered_frames, underruns = struct.unpack("<BBHIII", data)
    decoded = {"schema": schema, "flags": flags,
               **{name: bool(flags & (1 << bit)) for name, bit in VIDEO_FLAG_BITS.items()},
               "pixel_blocks_per_10ms": blocks,
               "pixel_measured_mhz": blocks * VIDEO_CLOCK_QUANTIZATION_MHZ if flags & 0x20 else None,
               "pixel_vblank_frames": vblank_frames, "rendered_frames": rendered_frames,
               "underruns": underruns}
    return decoded


def crc16(data: bytes) -> int:
    return binascii.crc_hqx(data, 0xFFFF)


def encode_packet(sequence: int, opcode: int, voice: int, value: int) -> bytes:
    payload = struct.pack("<BBBBI", sequence, opcode, voice, 0, value)
    return SYNC + payload + struct.pack("<H", crc16(payload))


@dataclass(frozen=True)
class Ack:
    sequence: int
    opcode: int
    status: int
    active_mask: int  # Raw byte 4; ordinary ACKs contain only voices 0..7.
    rtt_ms: float
    header: str
    simulated: bool = False

    @property
    def status_text(self) -> str:
        return STATUS.get(self.status, f"unknown status {self.status}")

    @property
    def memory_flags(self) -> int | None:
        """Only successful, non-simulated memory queries carry hardware status."""
        if self.opcode == OPCODES["memory-status"] and self.status == 0 and not self.simulated:
            return self.active_mask
        return None

    @property
    def video_status_byte(self) -> int | None:
        """Only a successful, non-simulated 0x0C ACK carries a snapshot byte."""
        if self.opcode == OPCODES["video-status"] and self.status == 0 and not self.simulated:
            return self.active_mask
        return None

    @property
    def voice_status_byte(self) -> int | None:
        """A byte of the atomic voice snapshot (also available in offline mode)."""
        if self.opcode == OPCODES["voice-status"] and self.status == 0:
            return self.active_mask
        return None

    @property
    def latency_status_byte(self) -> int | None:
        if self.opcode == OPCODES["latency-status"] and self.status == 0 and not self.simulated:
            return self.active_mask
        return None

    @property
    def voice_onset_status_byte(self) -> int | None:
        if self.opcode == OPCODES["voice-onset"] and self.status == 0 and not self.simulated:
            return self.active_mask
        return None

    def as_dict(self) -> dict:
        """Expose byte 4 only under its opcode-specific meaning to event consumers."""
        return {"sequence": self.sequence, "opcode": self.opcode,
                "status": self.status, "status_text": self.status_text,
                "active_mask": None if self.opcode in (OPCODES["memory-status"], OPCODES["video-status"], OPCODES["voice-status"], OPCODES["latency-status"], OPCODES["voice-onset"]) else self.active_mask,
                "memory_flags": self.memory_flags, "video_status_byte": self.video_status_byte,
                "voice_status_byte": self.voice_status_byte,
                "latency_status_byte": self.latency_status_byte,
                "voice_onset_status_byte": self.voice_onset_status_byte,
                "rtt_ms": self.rtt_ms,
                "header": self.header, "simulated": self.simulated}


class AckParser:
    """Incrementally resynchronize ACKs; callers match sequence and opcode."""
    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[Ack]:
        self.buffer.extend(data)
        replies = []
        while len(self.buffer) >= 8:
            if self.buffer[:2] != SYNC:
                del self.buffer[0]
                continue
            frame = bytes(self.buffer[:8])
            if crc16(frame[2:6]) != int.from_bytes(frame[6:8], "little"):
                del self.buffer[0]
                continue
            del self.buffer[:8]
            sequence, status, active_mask, opcode = frame[2:6]
            replies.append(Ack(sequence, opcode, status, active_mask, 0,
                               frame.hex(" ")))
        return replies


def phase_step(note: float, sample_rate: float = DEFAULT_SAMPLE_RATE) -> int:
    if not math.isfinite(note) or not math.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("note and sample rate must be finite; sample rate must be positive")
    try:
        frequency = 440 * 2 ** ((note - 69) / 12)
    except OverflowError as exc:
        raise ValueError("note frequency must be between 0 and Nyquist") from exc
    if not 0 < frequency < sample_rate / 2:
        raise ValueError("note frequency must be between 0 and Nyquist")
    return min(0x7FFFFFFF, max(1, round(frequency * 2**32 / sample_rate)))


def gain_word(value: float) -> int:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("gain must be in [0, 1]")
    return round(value * UNITY)


def balance_word(value: float) -> int:
    """Map -1 (left), 0 (center), +1 (right) to the offset-binary wire value."""
    if not math.isfinite(value) or not -1 <= value <= 1:
        raise ValueError("L/R balance must be in [-1, 1]; -1=left, 0=center, +1=right")
    return round((value + 1) * (UNITY // 2))


def envelope_step(milliseconds: float, sample_rate: float, span: int = UNITY) -> int:
    if not math.isfinite(milliseconds) or milliseconds < 0:
        raise ValueError("envelope time must be finite and nonnegative")
    if not math.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("sample rate must be positive and finite")
    if not 0 <= span <= UNITY:
        raise ValueError("envelope span must be between zero and unity")
    if milliseconds == 0 or span == 0:
        return 0  # zero encodes immediate transition at the next sample boundary
    return min(UNITY, max(1, math.ceil(span / (milliseconds * sample_rate / 1000))))
