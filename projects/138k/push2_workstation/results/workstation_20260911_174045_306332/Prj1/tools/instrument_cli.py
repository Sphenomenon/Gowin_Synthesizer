#!/usr/bin/env python3
"""Tang Mega instrument UART controller; never generates realtime PCM audio."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

# Keep direct script invocation and importlib-based integrations compatible.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from instrument_backend import (DEFAULT_SAMPLE_RATE, OPCODES, STATUS, SYNC, UNITY,
                                WAVEFORMS, SerialTransport, crc16, encode_packet,
                                envelope_step, gain_word, balance_word, phase_step,
                                decode_video_status, read_video_status,
                                VOICE_COUNT, read_voice_status,
                                read_latency_status, decode_latency_status,
                                read_voice_onset_status, decode_voice_onset_status)
from instrument_backend.protocol import (decode_memory_flags, VIDEO_FLAG_BITS,
                                         VIDEO_STATUS_BYTES, VIDEO_CLOCK_QUANTIZATION_MHZ,
                                         LATENCY_STATUS_BYTES, VOICE_ONSET_STATUS_BYTES, OUTPUT_OPCODES)
from instrument_backend.diagnostics import LATENCY_CYCLE_FIELDS


class Instrument:
    """CLI output adapter over the shared serial transport."""
    def __init__(self, port: str | None, baud: int, timeout: float, dry_run: bool,
                 serial_backend: str = "auto"):
        self.sequence = 0
        self.timeout = timeout
        self.dry_run = dry_run
        self.transport = None
        self.serial = None
        if not dry_run:
            if not port:
                raise ValueError("--port is required unless --dry-run is used")
            self.transport = SerialTransport(port, baud, timeout, backend=serial_backend)
            self.serial = self.transport.serial

    def command(self, opcode: int, voice: int = 0xFF, value: int = 0):
        if self.dry_run:
            packet = encode_packet(self.sequence, opcode, voice, value)
            self.sequence = (self.sequence + 1) & 0xFF
            print(packet.hex(" "))
            return None
        ack = self.transport.command(opcode, voice, value)
        self.sequence = self.transport.sequence
        if opcode == OPCODES["memory-status"]:
            if ack.memory_flags is None:
                print(f"seq={ack.sequence} {ack.status_text} memory_status=unknown (no hardware status)")
            else:
                print(f"seq={ack.sequence} {ack.status_text} memory_flags=0x{ack.memory_flags:02x}")
                for name, value in decode_memory_flags(ack.memory_flags).items():
                    print(f"{name}={int(value)}")
        elif opcode == OPCODES["video-status"]:
            if ack.video_status_byte is None:
                print(f"seq={ack.sequence} {ack.status_text} video_status_byte=unknown (no hardware status)")
            else:
                print(f"seq={ack.sequence} {ack.status_text} video_status_byte=0x{ack.video_status_byte:02x}")
        elif opcode == OPCODES["voice-status"]:
            print(f"seq={ack.sequence} {ack.status_text} voice_status_byte=0x{ack.voice_status_byte:02x}")
        elif opcode == OPCODES["latency-status"]:
            print(f"seq={ack.sequence} {ack.status_text} latency_status_byte={ack.latency_status_byte}")
        elif opcode == OPCODES["voice-onset"]:
            print(f"seq={ack.sequence} {ack.status_text} voice_onset_status_byte={ack.voice_onset_status_byte}")
        else:
            print(f"seq={ack.sequence} {ack.status_text} active_low8=0x{ack.active_mask:02x} (voices 0..7; use voice-status for all 32)")
        return ack

    def voice_status(self):
        if self.dry_run:
            for index in range(4):
                self.command(OPCODES["voice-status"], 0xFF, index)
            return None
        active = read_voice_status(self.transport)
        self.sequence = self.transport.sequence
        print(f"active=0x{active:08x} active_count={active.bit_count()} voice_count={VOICE_COUNT}")
        print("active_voices=" + ",".join(str(voice) for voice in range(VOICE_COUNT) if active & (1 << voice)))
        return active

    def latency_status(self, as_json=False):
        if self.dry_run:
            for index in range(LATENCY_STATUS_BYTES):
                self.command(OPCODES["latency-status"], 0xFF, index)
            return None
        status = decode_latency_status(read_latency_status(self.transport))
        self.sequence = self.transport.sequence
        if as_json:
            print(json.dumps(status, indent=2))
            return status
        print(f"trace_id={status['trace_id']} seq={status['sequence']} opcode=0x{status['opcode']:02x} {status['opcode_name']} voice={status['voice']}")
        print(f"flags=0x{status['flags']:02x} clock_hz={status['clock_hz']} expired={int(status['expired'])}")
        for name in LATENCY_CYCLE_FIELDS:
            value = status[name]
            milliseconds = status[name.removesuffix('_cycles') + '_ms']
            print(f"{name}=unavailable" if value is None else f"{name}={value} ({milliseconds:.6f} ms)")
        print(f"overwritten_pending_count={status['overwritten_pending_count']}")
        print("DAC endpoint: final stereo-frame BCK rising edge; not analog/headphone/speaker latency.")
        print("note endpoint: nonzero contribution from the commanded voice; final mix can still cancel.")
        if status["opcode"] in OUTPUT_OPCODES:
            print("output-control endpoint: first frame using the new target revision; gain slew may still be in progress.")
        print("No input-to-output total: this CLI query has no matching host submission timing.")
        return status

    def voice_onset(self, voice, as_json=False):
        if self.dry_run:
            for index in range(VOICE_ONSET_STATUS_BYTES):
                self.command(OPCODES["voice-onset"], voice, index)
            return None
        status = decode_voice_onset_status(read_voice_onset_status(self.transport, voice), voice)
        self.sequence = self.transport.sequence
        if as_json:
            print(json.dumps(status, indent=2))
            return status
        print(f"voice={status['voice']} note_id={status['note_id']} note_on_sequence={status['sequence']} revision={status['revision']}")
        print(f"state={status['state']} flags=0x{status['flags']:02x} clock_hz={status['clock_hz']}")
        print(f"was_active={int(status['was_active'])} amp_muted_at_DAC=" +
              (str(int(status['amp_muted_at_dac'])) if status['valid'] and status['dac_seen'] else "unavailable"))
        for endpoint in ("sample", "dac", "cancel"):
            cycles = status[f"trigger_to_{endpoint}_cycles"]
            milliseconds = status[f"trigger_to_{endpoint}_ms"]
            print(f"trigger_to_{endpoint}_cycles=unavailable" if cycles is None else
                  f"trigger_to_{endpoint}_cycles={cycles} ({milliseconds * 1000:.3f} us)")
        print(f"elapsed_cycles={status['elapsed_cycles']} exact={int(status['exact'])}")
        print("Trigger: this slot's NOTE_ON commit; threshold: its /32 contribution quantized to nonzero PCM16.")
        print("DAC endpoint: final stereo-frame BCK rising edge; not mixed-sample or analog/headphone onset.")
        print("was_active means retriggering a non-IDLE voice; it may already be sounding. Cancellation does not prove silence.")
        return status

    def video_status(self):
        if self.dry_run:
            for index in range(VIDEO_STATUS_BYTES):
                self.command(OPCODES["video-status"], 0xFF, index)
            return None
        raw = read_video_status(self.transport)
        self.sequence = self.transport.sequence
        print(f"video_status_raw={raw.hex(' ')}")
        status = decode_video_status(raw)
        print(f"schema={status['schema']} flags=0x{status['flags']:02x}")
        for name in VIDEO_FLAG_BITS:
            print(f"{name}={int(status[name])}")
        print(f"pixel_blocks_per_10ms={status['pixel_blocks_per_10ms']}")
        if status["pixel_measured_mhz"] is None:
            print("pixel_measured_mhz=unknown (measurement window not valid)")
        else:
            print(f"pixel_measured_mhz={status['pixel_measured_mhz']:.4f} "
                  f"(nominal 10 ms window; quantization +/-{VIDEO_CLOCK_QUANTIZATION_MHZ:.4f} MHz)")
        for name in ("pixel_vblank_frames", "rendered_frames", "underruns"):
            print(f"{name}={status[name]}")
        return status

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()


def play_demo(instrument: Instrument, commands: list[tuple[int, int, int]],
              seconds: float, sample_rate: float, dry_run: bool) -> None:
    """Include initialization in cleanup, preserving the first failure if PANIC also fails."""
    original_error = None
    try:
        for command in commands:
            instrument.command(*command)
        if not dry_run:
            time.sleep(seconds / 2)
        instrument.command(3, 1, phase_step(65, sample_rate))
        if not dry_run:
            time.sleep(seconds / 2)
    except BaseException as exc:
        original_error = exc
        raise
    finally:
        try:
            instrument.command(10)
        except BaseException as cleanup_error:
            if original_error is None:
                raise
            print(f"warning: demo PANIC cleanup also failed: {cleanup_error}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--serial-backend", choices=("auto", "pyserial", "ftdi"), default="auto",
                        help="auto uses the OS serial driver; ftdi explicitly tests D2XX on Windows UART channel B")
    parser.add_argument("--sample-rate", type=float, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--timeout", type=float, default=1)
    parser.add_argument("--dry-run", action="store_true", help="print packets without opening a port")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("ping", "panic", "memory-status", "video-status", "voice-status"):
        sub.add_parser(action)
    p = sub.add_parser("latency-status")
    p.add_argument("--json", action="store_true", help="print the decoded hardware snapshot as JSON")
    p = sub.add_parser("voice-onset")
    p.add_argument("voice", type=int, choices=range(VOICE_COUNT))
    p.add_argument("--json", action="store_true", help="print the selected voice's latest NOTE_ON record as JSON")
    for action in ("note-on", "pitch"):
        p = sub.add_parser(action)
        p.add_argument("voice", type=int, choices=range(VOICE_COUNT))
        p.add_argument("note", type=float, help="MIDI note, fractional notes are supported")
        if action == "note-on":
            p.add_argument("--velocity", type=float, help="optional pre-note gain configuration, 0..1")
            p.add_argument("--waveform", choices=tuple(WAVEFORMS))
    p = sub.add_parser("note-off")
    p.add_argument("voice", type=int, choices=range(VOICE_COUNT))
    p = sub.add_parser("velocity")
    p.add_argument("voice", type=int, choices=range(VOICE_COUNT))
    p.add_argument("gain", type=float)
    p = sub.add_parser("master-volume", help="global output gain; 0=mute, 1=unity")
    p.add_argument("gain", type=float, help="linear gain, 0..1")
    p = sub.add_parser("lr-balance", help="global stereo balance; center preserves both channels")
    p.add_argument("balance", type=float, help="-1=left only, 0=center, +1=right only")
    p = sub.add_parser("waveform")
    p.add_argument("voice", type=int, choices=range(VOICE_COUNT))
    p.add_argument("kind", choices=tuple(WAVEFORMS))
    p = sub.add_parser("adsr")
    p.add_argument("voice", type=int, choices=range(VOICE_COUNT))
    p.add_argument("--attack-ms", type=float, default=5)
    p.add_argument("--decay-ms", type=float, default=120)
    p.add_argument("--sustain", type=float, default=0.625)
    p.add_argument("--release-ms", type=float, default=100,
                   help="full-scale release time; a partial envelope releases sooner")
    p = sub.add_parser("demo")
    p.add_argument("--seconds", type=float, default=2)
    args = parser.parse_args()
    if not math.isfinite(args.sample_rate) or args.sample_rate <= 0:
        parser.error("--sample-rate must be positive and finite")
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.baud <= 0:
        parser.error("--timeout and --baud must be positive")
    instrument = None
    try:
        # Validate the complete action before writing any configuration to the device.
        commands = []
        if args.action in ("ping", "panic", "memory-status"):
            commands.append((OPCODES[args.action], 0xFF, 0))
        elif args.action in ("note-on", "pitch"):
            step = phase_step(args.note, args.sample_rate)
            if args.action == "note-on":
                if args.velocity is not None:
                    commands.append((4, args.voice, gain_word(args.velocity)))
                if args.waveform is not None:
                    commands.append((5, args.voice, WAVEFORMS[args.waveform]))
            commands.append((OPCODES[args.action], args.voice, step))
        elif args.action == "note-off":
            commands.append((2, args.voice, 0))
        elif args.action == "velocity":
            commands.append((4, args.voice, gain_word(args.gain)))
        elif args.action == "master-volume":
            commands.append((OPCODES[args.action], 0xFF, gain_word(args.gain)))
        elif args.action == "lr-balance":
            commands.append((OPCODES[args.action], 0xFF, balance_word(args.balance)))
        elif args.action == "waveform":
            commands.append((5, args.voice, WAVEFORMS[args.kind]))
        elif args.action == "adsr":
            sustain = gain_word(args.sustain)
            commands.extend([(6, args.voice, envelope_step(args.attack_ms, args.sample_rate)),
                             (7, args.voice, envelope_step(args.decay_ms, args.sample_rate, UNITY-sustain)),
                             (8, args.voice, sustain),
                             (9, args.voice, envelope_step(args.release_ms, args.sample_rate))])
        elif args.action == "demo":
            if not math.isfinite(args.seconds) or args.seconds <= 0:
                raise ValueError("--seconds must be positive and finite")
            commands.append((10, 0xFF, 0))
            for voice, note in enumerate((60, 64, 67, 72)):
                commands.extend([(5, voice, voice & 1), (4, voice, gain_word(0.6)),
                                 (1, voice, phase_step(note, args.sample_rate))])
        instrument = Instrument(args.port, args.baud, args.timeout, args.dry_run, args.serial_backend)
        if args.action == "demo":
            play_demo(instrument, commands, args.seconds, args.sample_rate, args.dry_run)
        elif args.action == "video-status":
            instrument.video_status()
        elif args.action == "voice-status":
            instrument.voice_status()
        elif args.action == "latency-status":
            instrument.latency_status(args.json)
        elif args.action == "voice-onset":
            instrument.voice_onset(args.voice, args.json)
        else:
            for command in commands:
                instrument.command(*command)
    except (ValueError, RuntimeError, TimeoutError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
    finally:
        if instrument is not None:
            instrument.close()


if __name__ == "__main__":
    main()
