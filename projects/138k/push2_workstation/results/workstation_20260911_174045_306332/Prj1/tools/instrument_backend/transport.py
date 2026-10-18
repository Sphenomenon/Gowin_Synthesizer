"""Paced serial transactions, bounded ACK pipelining, and an offline simulator."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import os
import re
import time

from .protocol import Ack, AckParser, SYNC, UNITY, VOICE_COUNT, OUTPUT_OPCODES, crc16, encode_packet

_CLOCK_INFO = time.get_clock_info("perf_counter")


@dataclass(frozen=True)
class TransactionTiming:
    """Local monotonic timestamps; write entry is not a physical UART edge."""
    sequence: int
    opcode: int
    write_started: float
    ack_received: float | None = None


class CommandRejected(RuntimeError):
    def __init__(self, ack: Ack):
        self.ack = ack
        detail = ""
        if ack.opcode == 5 and ack.status == 3:
            detail = "; sine requires the updated FPGA bitstream"
        elif ack.opcode == 0x0C and ack.status == 1:
            detail = "; video-status requires the diagnostic FPGA bitstream"
        elif ack.opcode == 0x0D and ack.status == 1:
            detail = "; voice-status requires the 32-voice FPGA bitstream"
        elif ack.opcode == 0x0E and ack.status == 1:
            detail = "; latency-status requires the latency diagnostic FPGA bitstream"
        elif ack.opcode == 0x0F and ack.status == 1:
            detail = "; voice-onset requires the per-voice onset diagnostic FPGA bitstream"
        elif ack.opcode in OUTPUT_OPCODES and ack.status == 1:
            detail = "; master volume and L/R balance require the output-control FPGA bitstream"
        super().__init__(f"FPGA rejected command: {ack.status_text}{detail}")


class SerialTransport:
    """Single caller ownership, at most 16 asynchronous transactions, no replay.

    One write always contains exactly one 12-byte command. Async transmission
    waits for the measured bridge-safe interval after the previous write
    returns; elapsed idle time never accumulates credit for a burst. Responses
    remain eight-byte ACKs and are matched by both sequence and opcode.
    """
    supports_async = True
    max_in_flight = 16

    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.35,
                 serial_factory=None, backend: str = "auto"):
        if not port:
            raise ValueError("a serial port is required")
        if isinstance(baud, bool) or not isinstance(baud, int) or baud <= 0:
            raise ValueError("baud must be a positive integer")
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be a positive finite number of seconds")
        if backend not in ("auto", "pyserial", "ftdi"):
            raise ValueError("serial backend must be auto, pyserial or ftdi")
        identity = None
        if serial_factory is None:
            try:
                import serial
            except ImportError as exc:
                raise RuntimeError("install pyserial: python -m pip install pyserial") from exc
            # Keep the OS serial driver as the default. The board's compatible
            # bridge accepted a D2XX 1 ms timer but still measured ~17 ms RTT;
            # selecting it automatically adds no demonstrated latency benefit.
            identity = _ftdi_identity(port) if backend == "ftdi" else None
            if backend == "ftdi" and identity is None:
                raise ValueError("FTDI backend requires the detected 0403:6010 UART channel B on Windows")
            if identity is not None:
                from .ftdi_serial import FtdiSerial
                serial_factory = FtdiSerial
            else:
                serial_factory = serial.Serial
        self.timeout = timeout
        self.baud = baud
        self.sequence = 0
        self.last_timing = None
        self.send_interval = max(0.0015, 120 / baud + 0.0004)
        self.send_ready_at = 0.0
        self._pending_async: dict[tuple[int, int], TransactionTiming] = {}
        self._closed = False
        self._faulted = False
        self._fault_sequences: set[int] = set()
        self._emergency_started = False
        options = {"serial_number": identity} if identity is not None else {}
        self.serial = serial_factory(port, baudrate=baud, bytesize=8, parity="N", stopbits=1,
                                     timeout=min(0.02, timeout), write_timeout=timeout, **options)
        self.profile = dict(getattr(self.serial, "profile", {"backend": "pyserial", "port": port}))
        self.profile["clock"] = _CLOCK_INFO.implementation
        self.profile["clock_resolution_s"] = _CLOCK_INFO.resolution
        try:
            self.serial.reset_input_buffer()
        except BaseException:
            self.serial.close()
            raise
        self.parser = AckParser()

    @property
    def faulted(self) -> bool:
        """Ordinary traffic is prohibited after any uncertain transaction."""
        return self._faulted

    @property
    def pending_count(self) -> int:
        return len(self._pending_async)

    @property
    def next_deadline(self) -> float | None:
        """Earliest outstanding write deadline; None when no ACK is pending."""
        return min((item.write_started + self.timeout
                    for item in self._pending_async.values()), default=None)

    def _ensure_open(self):
        if self._closed:
            raise OSError("serial transport is closed; reconnect explicitly")
        if self._faulted:
            raise OSError("serial transport is faulted; only emergency_close() or close() is allowed")

    def _fail(self, error, attempted_sequence=None, *, write_failed=False):
        """Isolate uncertain traffic, retaining the handle for one explicit PANIC.

        A partly submitted packet may already have reached the FPGA. Its
        sequence and every pending sequence remain forbidden to the independent
        emergency command even though ordinary transaction ownership is cleared.
        """
        self._faulted = True
        self._fault_sequences.update(key[0] for key in self._pending_async)
        if attempted_sequence is not None:
            self._fault_sequences.add(attempted_sequence)
        if write_failed:
            self.send_ready_at = max(self.send_ready_at,
                                     time.perf_counter() + self.send_interval)
        self._pending_async.clear()
        self.parser = AckParser()
        raise error

    def _check_deadlines(self, now):
        for item in self._pending_async.values():
            if now >= item.write_started + self.timeout:
                self._fail(TimeoutError(
                    f"no valid FPGA reply for sequence {item.sequence}, "
                    f"opcode 0x{item.opcode:02X}; async session faulted without replay"))

    def send_async(self, opcode: int, voice: int = 0xFF,
                   value: int = 0) -> TransactionTiming | None:
        """Send one command, or return None if pacing/window ownership blocks it.

        None never consumes a sequence. Sequence advances modulo 256 only for
        a submitted packet; a value still owned by an outstanding command is
        never reused, even if acknowledgements arrive out of order. The wire
        has no generation field, so delayed duplicates spanning a whole 256-
        command cycle cannot be distinguished from a current ACK.
        """
        self._ensure_open()
        sequence = self.sequence
        packet = encode_packet(sequence, opcode, voice, value)
        started = time.perf_counter()
        self._check_deadlines(started)
        if (self.pending_count >= self.max_in_flight or started < self.send_ready_at
                or any(key[0] == sequence for key in self._pending_async)):
            return None
        timing = TransactionTiming(sequence, opcode, started)
        self.last_timing = timing
        try:
            if self.serial.write(packet) != len(packet):
                raise OSError("incomplete serial write; command was not replayed")
            finished = time.perf_counter()
        except Exception as error:
            self._fail(error, sequence, write_failed=True)
        self.sequence = (sequence + 1) & 0xFF
        self._pending_async[(sequence, opcode)] = timing
        self.send_ready_at = max(started, finished) + self.send_interval
        return timing

    def poll_acks(self) -> list[tuple[Ack, TransactionTiming]]:
        """Read only bytes already queued; return every matching ACK in that read.

        No sleeping, waiting for a full ACK, or reading an empty driver queue.
        Partial frames remain in AckParser. Rejected commands are returned as
        normal ACK results so the owner can process the whole received batch.
        A deadline or I/O failure isolates the session until explicit cleanup.
        """
        self._ensure_open()
        self._check_deadlines(time.perf_counter())
        try:
            available = self.serial.in_waiting
            if available <= 0:
                return []
            # Bounded work even if the line contains unexpected traffic. Under
            # exclusive ownership these bytes cannot be consumed by another reader.
            data = self.serial.read(min(4096, available))
            received = time.perf_counter()
        except Exception as error:
            self._fail(error)
        self._check_deadlines(received)
        completed = []
        for ack in self.parser.feed(data):
            pending = self._pending_async.pop((ack.sequence, ack.opcode), None)
            if pending is None:
                continue
            timing = replace(pending, ack_received=received)
            ack = replace(ack, rtt_ms=(received - timing.write_started) * 1000)
            self.last_timing = timing
            completed.append((ack, timing))
        return completed

    def command(self, opcode: int, voice: int = 0xFF, value: int = 0) -> Ack:
        self._ensure_open()
        if self.pending_count:
            raise RuntimeError("cannot use blocking command while asynchronous ACKs are pending")
        self.last_timing = None
        sequence = self.sequence
        self.sequence = (sequence + 1) & 0xFF
        packet = encode_packet(sequence, opcode, voice, value)
        started = time.perf_counter()
        self.last_timing = TransactionTiming(sequence, opcode, started)
        self.send_ready_at = max(self.send_ready_at, started + self.send_interval)
        try:
            if self.serial.write(packet) != len(packet):
                raise OSError("incomplete serial write")
            self.send_ready_at = max(self.send_ready_at, time.perf_counter() + self.send_interval)
        except Exception as error:
            self._fail(error, sequence, write_failed=True)
        deadline = started + self.timeout
        while time.perf_counter() < deadline:
            # Block for the first byte, then consume the bytes already queued.
            # Never wait for a fixed large buffer to fill or call serial.flush().
            try:
                available = getattr(self.serial, "in_waiting", 0)
                data = self.serial.read(max(1, min(256, available)))
            except Exception as error:
                self._fail(error, sequence)
            for ack in self.parser.feed(data):
                if ack.sequence != sequence or ack.opcode != opcode:
                    continue
                received = time.perf_counter()
                self.last_timing = TransactionTiming(sequence, opcode, started, received)
                ack = replace(ack, rtt_ms=(received - started) * 1000)
                if ack.status:
                    raise CommandRejected(ack)
                return ack
        self._fail(TimeoutError("no valid FPGA reply; check port, pin routing, baud and bitstream"), sequence)

    def emergency_close(self) -> dict:
        """Try one fresh PANIC on this handle, then close; never replay or reopen.

        This is an explicit sounding-session cleanup operation. Read-only/PING
        callers must use close(), which never sends anything. An ACK confirms
        only the digital PANIC command; failure leaves physical silence unknown.
        Repeated calls and calls after close are no-ops with attempted=False.
        """
        result = {"attempted": False, "acknowledged": False, "error": None}
        if self._closed or self._emergency_started:
            return result
        self._emergency_started = True
        self._faulted = True
        forbidden = self._fault_sequences | {key[0] for key in self._pending_async}
        self._pending_async.clear()
        self.parser = AckParser()
        try:
            sequence = next((self.sequence + offset) & 0xFF for offset in range(256)
                            if ((self.sequence + offset) & 0xFF) not in forbidden)
            packet = encode_packet(sequence, 0x0A, 0xFF, 0)
            while time.perf_counter() < self.send_ready_at:
                time.sleep(max(0, self.send_ready_at - time.perf_counter()))
            started = time.perf_counter()
            deadline = started + self.timeout
            self.sequence = (sequence + 1) & 0xFF
            result["attempted"] = True
            if self.serial.write(packet) != len(packet):
                raise OSError("incomplete emergency PANIC write; no retry was attempted")
            parser = AckParser()
            while time.perf_counter() < deadline:
                available = self.serial.in_waiting
                if available > 0:
                    data = self.serial.read(min(4096, available))
                    # Bytes arriving after the deadline are not confirmation.
                    if time.perf_counter() >= deadline:
                        break
                    for ack in parser.feed(data):
                        if ack.sequence == sequence and ack.opcode == 0x0A:
                            if ack.status:
                                raise CommandRejected(ack)
                            result["acknowledged"] = True
                            return result
                else:
                    time.sleep(min(0.001, max(0, deadline - time.perf_counter())))
            raise TimeoutError("no matching emergency PANIC ACK before timeout; silence is unconfirmed")
        except Exception as error:
            result["error"] = str(error)
        finally:
            try:
                self.close()
            except Exception as error:
                previous = result["error"]
                result["error"] = (f"{previous}; " if previous else "") + f"Serial close failed: {error}"
        return result

    def close(self) -> None:
        """Release ownership silently; safe for PING-only tools and repeated calls."""
        self._pending_async.clear()
        self.parser = AckParser()
        if self._closed:
            return
        self._closed = True
        self.serial.close()


def _ftdi_identity(port: str) -> str | None:
    """Select only the detected Tang Mega FT2232 UART channel; never its JTAG A.

    Reading the OS port inventory does not open a device. D2XX and VCP handles
    are mutually exclusive, and the selected adapter owns channel B alone.
    """
    if os.name != "nt":
        return None
    from serial.tools import list_ports as serial_ports
    for item in serial_ports.comports():
        number = getattr(item, "serial_number", None)
        if (item.device.upper() == port.upper() and item.vid == 0x0403 and item.pid == 0x6010
                and isinstance(number, str) and number.endswith("B") and _port_interface(item) != "A"):
            return number
    return None


class SimulatedTransport:
    """Control-state ACK simulation only: no audio, levels, or FPGA timing model."""
    def __init__(self):
        self.sequence = 0
        self.active_mask = 0
        self.voice_snapshot = None
        self.master_volume = UNITY
        self.lr_balance = UNITY // 2

    def command(self, opcode: int, voice: int = 0xFF, value: int = 0) -> Ack:
        status = 0
        if opcode not in (*range(11), 13, *OUTPUT_OPCODES):
            status = 1
        elif opcode not in (0, 10, 13, *OUTPUT_OPCODES) and voice not in range(VOICE_COUNT):
            status = 2
        elif opcode in (13, *OUTPUT_OPCODES) and voice != 255:
            status = 2
        elif opcode in OUTPUT_OPCODES and (type(value) is not int or not 0 <= value <= UNITY):
            status = 3
        elif opcode == 13 and (value not in range(4)
                               or (value != 0 and self.voice_snapshot is None)):
            status = 3
        elif opcode == 5 and value not in (0, 1, 2):
            status = 3
        if not status:
            if opcode == 1:
                self.active_mask |= 1 << voice
            elif opcode == 2:
                self.active_mask &= ~(1 << voice)
            elif opcode == 10:
                self.active_mask = 0
            elif opcode == 13 and value == 0:
                self.voice_snapshot = self.active_mask
            elif opcode == 16:
                self.master_volume = value
            elif opcode == 17:
                self.lr_balance = value
        reply_byte = ((self.voice_snapshot >> (value * 8)) & 255
                      if opcode == 13 and not status else self.active_mask & 255)
        payload = bytes((self.sequence, status, reply_byte, opcode))
        frame = SYNC + payload + crc16(payload).to_bytes(2, "little")
        ack = Ack(self.sequence, opcode, status, reply_byte, 0,
                  frame.hex(" "), simulated=True)
        self.sequence = (self.sequence + 1) & 0xFF
        if status:
            raise CommandRejected(ack)
        return ack

    def close(self) -> None:
        pass


def _port_interface(port) -> str:
    """Identify channels only when OS descriptors encode them explicitly."""
    declared = str(getattr(port, "interface", "") or "").strip().upper()
    if declared in ("A", "B"):
        return declared
    detail = " ".join(str(getattr(port, key, "") or "")
                      for key in ("interface", "description", "hwid"))
    match = re.search(r"(?:MI_|interface\s*|channel\s*)(00|01|A|B)\b", detail, re.I)
    if match:
        return {"00": "A", "01": "B", "A": "A", "B": "B"}[match[1].upper()]
    # FTDI's Windows bus identifiers append the channel letter to the device serial.
    hwid = str(getattr(port, "hwid", "") or "")
    match = re.search(r"FTDIBUS\\VID_0403\+PID_6010\+[^\\]+([AB])\\", hwid, re.I)
    return match[1].upper() if match else ""


def list_ports() -> list[dict]:
    """Read OS metadata only. Never open/probe ports or infer a board from COM numbers."""
    try:
        from serial.tools import list_ports as serial_ports
    except ImportError as exc:
        raise RuntimeError("install pyserial: python -m pip install pyserial") from exc
    results = []
    for port in serial_ports.comports():
        description = port.description or "Serial port"
        interface = _port_interface(port)
        suffix = f" [interface {interface}]" if interface else ""
        results.append({"device": port.device, "description": description,
                        "interface": interface, "hwid": port.hwid,
                        "display": f"{port.device} — {description}{suffix}",
                        "vid": port.vid, "pid": port.pid,
                        "serial_number": port.serial_number})
    return sorted(results, key=lambda item: [int(part) if part.isdigit() else part.lower()
                                            for part in re.split(r"(\d+)", item["device"])])
