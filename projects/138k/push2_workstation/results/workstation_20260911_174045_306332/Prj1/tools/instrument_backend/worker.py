"""One serial owner thread with a bounded, release-aware command queue."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
import queue
import threading
import time

from .protocol import VOICE_COUNT, UNITY, OUTPUT_OPCODES, LATENCY_STATUS_BYTES, VOICE_ONSET_STATUS_BYTES, encode_packet
from .diagnostics import decode_latency_status, decode_voice_onset_status
from .transport import CommandRejected, SerialTransport, SimulatedTransport, TransactionTiming


@dataclass(frozen=True)
class _Pending:
    command: tuple[int, int, int]
    tag: str
    key: object = None
    submitted_monotonic: float | None = None
    diagnostic_generation: int | None = None


@dataclass
class _Snapshot:
    opcode: int
    voice: int
    count: int
    tag: str
    generation: int | None = None
    sound_generation: int = 0
    data: bytearray = field(default_factory=bytearray)
    waiting: bool = False
    aborted: bool = False


@dataclass
class _Flight:
    pending: _Pending
    timing: TransactionTiming
    snapshot: _Snapshot | None = None


@dataclass
class _Dispatch:
    pending: _Pending
    background: bool = False
    cancelled: bool = False


class ControlWorker:
    """All public actions are nonblocking; consume ``events`` from Tk's main thread.

    NoteOff cancels queued NoteOn for that voice and takes priority over parameters.
    PANIC cancels the complete pending queue. Async serial sessions send releases
    at the next paced opportunity without waiting for older ACKs; transmitted
    packets retain UART order. Synchronous fallback finishes its current ACK first.
    Each command is reserved individually, so a batch has no hidden unsent tail.
    Background patch preparation yields to foreground work and resumes after
    500 ms without a foreground sound command; it has no input-latency timestamp.
    """
    def __init__(self, timeout: float = 0.35, ping_interval: float = 0.30,
                 max_queue: int = 512, transport_factory=None):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if not math.isfinite(ping_interval) or ping_interval <= 0 or max_queue < 8:
            raise ValueError("ping_interval must be positive and max_queue at least eight")
        self.timeout = timeout
        self.ping_interval = ping_interval
        self.max_queue = max_queue
        self.events = queue.Queue(maxsize=2048)
        self._factory = transport_factory
        self._condition = threading.Condition()
        self._pending = deque()
        self._background = deque()
        self._background_ready_at = 0.0
        self._inflight = {}
        self._reserved = None
        self._async_snapshot = None
        self._async_next_ping = 0.0
        self._control = None
        self._state = "disconnected"
        self._closing = False
        self._transport = None
        self.voice_count = VOICE_COUNT
        self.connection_id = 0
        self._sound_generation = 0
        self._latency_requested = False
        self._latency_generation = 0
        self._latency_supported = None
        self._onset_requested_voice = None
        self._onset_generation = 0
        self._onset_supported = None
        self.output_controls_supported = {}
        self._thread = threading.Thread(target=self._run, name="instrument-uart", daemon=True)
        self._thread.start()

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def pending_count(self) -> int:
        with self._condition:
            return len(self._pending) + len(self._background)

    def _emit(self, event_type: str, **data) -> None:
        event = {"type": event_type, **data}
        # A paused GUI cannot cause unbounded memory growth or block the serial owner.
        while True:
            try:
                self.events.put_nowait(event)
                return
            except queue.Full:
                try:
                    self.events.get_nowait()
                except queue.Empty:
                    pass

    def connect(self, port: str | None, baud: int = 115200, simulated: bool = False,
                output_controls: tuple[int, int] | None = None) -> bool:
        with self._condition:
            if self._closing or self._state != "disconnected":
                self._emit("error", message="disconnect before opening another connection")
                return False
            if not simulated and not port:
                self._emit("error", message="select a serial port first")
                return False
            if not isinstance(baud, int) or baud <= 0:
                self._emit("error", message="baud must be a positive integer")
                return False
            if output_controls is not None and (not isinstance(output_controls, (tuple, list))
                    or len(output_controls) != 2
                    or any(type(value) is not int or not 0 <= value <= UNITY for value in output_controls)):
                self._emit("error", message="output_controls must contain master and balance words in 0..0x80000000")
                return False
            self._state = "connecting"
            self._control = ("connect", port, baud, simulated,
                             tuple(output_controls) if output_controls is not None else None)
            self._condition.notify()
            return True

    def submit(self, commands: list[tuple[int, int, int]], tag: str = "",
               coalesce_key=None, submitted_at: float | None = None, background: bool = False) -> bool:
        entered = time.perf_counter()
        submitted = entered if submitted_at is None else submitted_at
        if (isinstance(submitted, bool) or not isinstance(submitted, (int, float))
                or not math.isfinite(submitted) or submitted > entered):
            self._emit("error", message="submitted_at must be a finite perf_counter timestamp no later than submission", tag=tag)
            return False
        try:
            normalized = [tuple(command) for command in commands]
            for command in normalized:
                encode_packet(0, *command)  # validate the entire batch before enqueueing
                if command[0] in OUTPUT_OPCODES and (command[1] != 255
                        or type(command[2]) is not int or not 0 <= command[2] <= UNITY):
                    raise ValueError("global output controls require voice=255 and value in 0..0x80000000")
        except Exception as exc:
            self._emit("error", message=f"invalid command batch: {exc}", tag=tag)
            return False
        if not normalized:
            return True
        if background and (submitted_at is not None or any(command[0] not in range(4, 10) for command in normalized)):
            self._emit("error", message="background work must contain only patch parameters, without an input timestamp", tag=tag)
            return False
        if len(normalized) > self.max_queue:
            self._emit("error", message="command batch exceeds queue capacity", tag=tag)
            return False
        if any(command[0] == 10 for command in normalized):
            # Treat PANIC as a dedicated fence; never allow a mixed batch to restart it.
            if len(normalized) != 1:
                self._emit("error", message="submit PANIC separately from other commands", tag=tag)
                return False
            return self._enqueue_panic(tag or "panic", submitted)
        with self._condition:
            if self._closing or self._state != "connected":
                self._emit("error", message="instrument is not connected", tag=tag)
                return False
            if any(opcode in range(1, 10) and voice not in range(self.voice_count)
                   for opcode, voice, value in normalized):
                self._emit("error", message=f"connected firmware supports voices 0..{self.voice_count - 1}", tag=tag)
                return False
            if any(opcode in OUTPUT_OPCODES and self.output_controls_supported.get(opcode) is False
                   for opcode, voice, value in normalized):
                self._emit("error", message="connected firmware does not support this output control", tag=tag)
                return False
            background_work = deque(item for item in self._background
                                    if not (coalesce_key is not None and item.key == coalesce_key))
            if background:
                if len(self._pending) + len(background_work) + len(normalized) > self.max_queue:
                    self._emit("error", message="command queue is full; patch preload was not queued", tag=tag)
                    return False
                background_work.extend(_Pending(command, tag, coalesce_key) for command in normalized)
                self._background = background_work
                reserved = getattr(self, "_reserved", None)
                if (reserved is not None and reserved.background and coalesce_key is not None
                        and reserved.pending.key == coalesce_key):
                    reserved.cancelled = True
                self._condition.notify()
                return True
            touched = {voice for opcode, voice, value in normalized if 1 <= opcode <= 9}
            # A foreground edit or note supersedes stale preload values for its
            # slot. A parameter already on the wire finishes before new work.
            cancelled_preloads = {(item.tag, item.command[1]) for item in background_work if item.command[1] in touched}
            background_work = deque(item for item in background_work if item.command[1] not in touched)
            released = {command[1] for command in normalized if command[0] == 2}
            output_predecessors = None
            if len(normalized) == 1 and normalized[0][0] in OUTPUT_OPCODES and coalesce_key is not None:
                # Keep a replaced global control at its original ordering
                # barrier. Appending it after an intervening NOTE_ON could let
                # that note sound before the attenuation it was queued behind.
                preceding = set()
                for item in self._pending:
                    if item.key == coalesce_key and item.command[0] == normalized[0][0]:
                        output_predecessors = preceding
                        break
                    preceding.add(id(item))
                reserved = getattr(self, "_reserved", None)
                if (reserved is not None and reserved.pending.key == coalesce_key
                        and reserved.pending.command[0] == normalized[0][0]):
                    # Reservation is already removed from the queue but may
                    # still return unsent because of transport pacing.
                    output_predecessors = set()
            # Replace pending values only; a command already on the wire is never replayed.
            retained = deque(item for item in self._pending
                             if not (coalesce_key is not None and item.key == coalesce_key)
                             and not (item.command[1] in released and item.command[0] in (1, 2)))
            additions = [_Pending(command, tag, coalesce_key, submitted) for command in normalized]
            urgent = []
            for item in additions:
                if item.command[0] == 2:
                    if not any(prior.command[1] == item.command[1] for prior in urgent):
                        urgent.append(item)
            ordinary = [item for item in additions if item.command[0] != 2
                        and not (item.command[0] == 1 and item.command[1] in released)]
            while background_work and len(retained) + len(urgent) + len(ordinary) + len(background_work) > self.max_queue:
                dropped = background_work.pop()
                cancelled_preloads.add((dropped.tag, dropped.command[1]))
            if len(retained) + len(urgent) + len(ordinary) > self.max_queue:
                if ordinary:
                    self._emit("error", message="command queue is full; wait or release keys / PANIC", tag=tag)
                    return False
                # Releases always enter. Discard newest ordinary work if needed.
                while len(retained) + len(urgent) > self.max_queue:
                    retained.pop()
            # Preserve previously queued urgent commands, especially a PANIC fence.
            prefix = deque()
            while retained and retained[0].command[0] in (2, 10):
                prefix.append(retained.popleft())
            if output_predecessors is not None:
                position = sum(id(item) in output_predecessors for item in retained)
                retained.insert(position, ordinary.pop())
            self._pending = prefix + deque(urgent) + retained + deque(ordinary)
            self._background = background_work
            reserved = getattr(self, "_reserved", None)
            if reserved is not None and (
                    (coalesce_key is not None and reserved.pending.key == coalesce_key)
                    or (reserved.pending.command[1] in released and reserved.pending.command[0] in (1, 2))
                    or (reserved.background and reserved.pending.command[1] in touched)):
                reserved.cancelled = True
            for cancelled_tag, voice in cancelled_preloads:
                self._emit("patch_preload_cancelled", tag=cancelled_tag, voice=voice)
            if any(1 <= opcode <= 10 or opcode in OUTPUT_OPCODES for opcode, voice, value in normalized):
                self._background_ready_at = max(self._background_ready_at, entered + 0.5)
            self._condition.notify()
            return True

    def panic(self, tag: str = "panic") -> bool:
        return self._enqueue_panic(tag, time.perf_counter())

    def _enqueue_panic(self, tag: str, submitted: float) -> bool:
        with self._condition:
            self._pending.clear()
            self._background.clear()
            if getattr(self, "_reserved", None) is not None:
                self._reserved.cancelled = True
            if self._closing or self._state != "connected":
                self._emit("error", message="instrument is not connected", tag=tag)
                return False
            self._pending.append(_Pending((10, 255, 0), tag, submitted_monotonic=submitted))
            self._condition.notify()
            return True

    def disconnect(self) -> None:
        with self._condition:
            if self._closing:
                return
            self._pending.clear()
            self._background.clear()
            if self._reserved is not None:
                self._reserved.cancelled = True
            self._latency_requested = False
            self._latency_generation += 1
            self._onset_requested_voice = None
            self._onset_generation += 1
            self._state = "disconnecting"
            self._control = ("disconnect",)
            self._condition.notify()

    def close(self) -> None:
        with self._condition:
            self._closing = True
            self._pending.clear()
            self._background.clear()
            if self._reserved is not None:
                self._reserved.cancelled = True
            self._latency_requested = False
            self._latency_generation += 1
            self._onset_requested_voice = None
            self._onset_generation += 1
            self._condition.notify()

    def request_latency_status(self) -> bool:
        """Schedule one idle-time snapshot, preemptible after every ACK byte."""
        with self._condition:
            if self._closing or self._state != "connected" or self._latency_supported is False:
                return False
            self._latency_requested = True
            self._condition.notify()
            return True

    def cancel_latency_status(self) -> None:
        with self._condition:
            self._latency_requested = False
            self._latency_generation += 1

    def request_voice_onset_status(self, voice: int) -> bool:
        if type(voice) is not int or voice not in range(VOICE_COUNT):
            self._emit("error", message="voice-onset voice must be in 0..31")
            return False
        with self._condition:
            if self._closing or self._state != "connected" or self._onset_supported is False:
                return False
            self._onset_requested_voice = voice
            self._onset_generation += 1
            self._condition.notify()
            return True

    def cancel_voice_onset_status(self) -> None:
        with self._condition:
            self._onset_requested_voice = None
            self._onset_generation += 1

    def _ack(self, command: tuple[int, int, int], tag: str, submitted_monotonic=None):
        dispatched = time.perf_counter()
        try:
            ack = self._transport.command(*command)
        except CommandRejected as exc:
            self._emit_ack(exc.ack, command[1], tag, submitted_monotonic, dispatched)
            raise
        self._emit_ack(ack, command[1], tag, submitted_monotonic, dispatched)
        return ack

    def _emit_ack(self, ack, voice, tag, submitted, dispatched, timing=None):
        completed = time.perf_counter()
        timing = timing if timing is not None else getattr(self._transport, "last_timing", None)
        source = "unavailable"
        if ack.simulated:
            # Only local scheduling/model execution is measured; no UART exists.
            source = "simulated"
            started, received = dispatched, completed
        elif (isinstance(timing, TransactionTiming)
              and (timing.sequence, timing.opcode) == (ack.sequence, ack.opcode)
              and timing.ack_received is not None):
            source = "serial"
            started, received = timing.write_started, timing.ack_received
        else:
            started = received = None
        # Background polls/handshakes have no user submission. Never display
        # their near-zero dispatch delay as a measured keyboard/control delay.
        measured = submitted is not None and started is not None
        sound_generation = None
        if ack.status == 0 and (1 <= ack.opcode <= 10 or ack.opcode in OUTPUT_OPCODES):
            self._sound_generation = getattr(self, "_sound_generation", 0) + 1
            sound_generation = self._sound_generation
            if submitted is not None:
                with self._condition:
                    self._background_ready_at = max(self._background_ready_at, completed + 0.5)
        self._emit("ack", **ack.as_dict(), tag=tag, voice=voice,
                   connection_id=getattr(self, "connection_id", None), timing_source=source,
                   sound_generation=sound_generation,
                   queue_wait_ms=(started - submitted) * 1000 if measured else None,
                   host_total_ms=(received - submitted) * 1000 if measured else None)

    def _unsupported_output(self, ack) -> bool:
        """Unsupported optional controls leave the musical connection usable."""
        if ack.opcode not in OUTPUT_OPCODES or ack.status != 1:
            return False
        with self._condition:
            first = self.output_controls_supported.get(ack.opcode) is not False
            self.output_controls_supported[ack.opcode] = False
            self._pending = deque(item for item in self._pending if item.command[0] != ack.opcode)
            if self._reserved is not None and self._reserved.pending.command[0] == ack.opcode:
                self._reserved.cancelled = True
        if first:
            self._emit("output_control_unsupported", opcode=ack.opcode,
                       connection_id=self.connection_id, simulated=ack.simulated)
        return True

    def _voice_status(self, tag="poll") -> None:
        # A partial snapshot is never published. All foreground work can
        # interrupt between bytes, waiting at most one in-flight transaction.
        snapshot = bytearray()
        for index in range(4):
            with self._condition:
                if self._closing or self._control is not None or self._pending:
                    return
            ack = self._ack((13, 255, index), tag)
            if ack.voice_status_byte is None:
                raise RuntimeError(f"voice-status byte {index} is invalid")
            snapshot.append(ack.voice_status_byte)
        self._emit("voice_status", active_mask=int.from_bytes(snapshot, "little"),
                   simulated=ack.simulated)

    def _latency_status(self, generation=None) -> None:
        generation = self._latency_generation if generation is None else generation
        sound_generation = self._sound_generation
        snapshot = bytearray()
        for index in range(LATENCY_STATUS_BYTES):
            with self._condition:
                if (self._closing or self._control is not None or self._pending
                        or generation != self._latency_generation):
                    self._emit("latency_status_aborted", connection_id=self.connection_id)
                    return
            try:
                ack = self._ack((14, 255, index), "latency_poll")
            except CommandRejected as exc:
                if index == 0 and exc.ack.status == 1:
                    self._latency_supported = False
                    self._emit("latency_unsupported", connection_id=self.connection_id,
                               simulated=exc.ack.simulated)
                    return
                raise
            value = ack.latency_status_byte
            if value is None:
                raise RuntimeError(f"latency-status byte {index} has no valid hardware status")
            snapshot.append(value)
        self._latency_supported = True
        self._emit("latency_status", status=decode_latency_status(bytes(snapshot)),
                   connection_id=self.connection_id, sound_generation=sound_generation)

    def _voice_onset_status(self, voice: int, generation=None) -> None:
        generation = self._onset_generation if generation is None else generation
        snapshot = bytearray()
        for index in range(VOICE_ONSET_STATUS_BYTES):
            with self._condition:
                if (self._closing or self._control is not None or self._pending
                        or generation != self._onset_generation):
                    self._emit("voice_onset_aborted", connection_id=self.connection_id, voice=voice)
                    return
            try:
                ack = self._ack((15, voice, index), "onset_poll")
            except CommandRejected as exc:
                if index == 0 and exc.ack.status == 1:
                    self._onset_supported = False
                    self._emit("voice_onset_unsupported", connection_id=self.connection_id,
                               simulated=exc.ack.simulated, voice=voice)
                    return
                raise
            value = ack.voice_onset_status_byte
            if value is None:
                raise RuntimeError(f"voice-onset byte {index} has no valid hardware status")
            snapshot.append(value)
        self._onset_supported = True
        self._emit("voice_onset_status", status=decode_voice_onset_status(bytes(snapshot), voice),
                   connection_id=self.connection_id, voice=voice)

    def _abort_async_snapshot(self):
        snapshot = self._async_snapshot
        if snapshot is None:
            return
        snapshot.aborted = True
        self._async_snapshot = None
        if snapshot.opcode in (0, 13):
            self._async_next_ping = time.perf_counter() + self.ping_interval
        elif snapshot.opcode == 14:
            self._emit("latency_status_aborted", connection_id=self.connection_id)
        else:
            self._emit("voice_onset_aborted", connection_id=self.connection_id, voice=snapshot.voice)

    def _check_async_snapshot_locked(self):
        snapshot = self._async_snapshot
        if snapshot is not None and (self._closing or self._control is not None or self._pending
                or (snapshot.opcode == 14 and snapshot.generation != self._latency_generation)
                or (snapshot.opcode == 15 and snapshot.generation != self._onset_generation)):
            self._abort_async_snapshot()

    def _finish_async_snapshot_byte(self, snapshot, ack):
        if snapshot.aborted:
            return
        snapshot.waiting = False
        if snapshot.opcode == 0:
            self._async_snapshot = None
            self._async_next_ping = time.perf_counter() + self.ping_interval
            return
        value = {13: ack.voice_status_byte, 14: ack.latency_status_byte,
                 15: ack.voice_onset_status_byte}[snapshot.opcode]
        if value is None:
            raise RuntimeError(f"diagnostic byte {len(snapshot.data)} has no valid hardware status")
        snapshot.data.append(value)
        if len(snapshot.data) != snapshot.count:
            return
        self._async_snapshot = None
        if snapshot.opcode == 13:
            self._async_next_ping = time.perf_counter() + self.ping_interval
            self._emit("voice_status", active_mask=int.from_bytes(snapshot.data, "little"), simulated=ack.simulated)
        elif snapshot.opcode == 14:
            self._latency_supported = True
            self._emit("latency_status", status=decode_latency_status(bytes(snapshot.data)),
                       connection_id=self.connection_id, sound_generation=snapshot.sound_generation)
        else:
            self._onset_supported = True
            self._emit("voice_onset_status", status=decode_voice_onset_status(bytes(snapshot.data), snapshot.voice),
                       connection_id=self.connection_id, voice=snapshot.voice)

    def _collect_async_acks(self, *, cleanup=False):
        first_error = None
        replies = self._transport.poll_acks()
        for ack, timing in replies:
            with self._condition:
                self._check_async_snapshot_locked()
                flight = self._inflight.pop(timing.sequence, None)
                if (flight is None or flight.timing.opcode != timing.opcode
                        or flight.timing.write_started != timing.write_started):
                    raise RuntimeError("asynchronous ACK has no matching worker transaction")
                item, snapshot = flight.pending, flight.snapshot
                self._emit_ack(ack, item.command[1], item.tag, item.submitted_monotonic,
                               timing.write_started, timing=timing)
                if ack.status:
                    unsupported = (snapshot is not None and not snapshot.aborted and not snapshot.data
                                   and ack.status == 1 and snapshot.opcode in (14, 15))
                    if self._unsupported_output(ack):
                        pass
                    elif unsupported:
                        if snapshot.opcode == 14:
                            self._latency_supported = False
                            self._emit("latency_unsupported", connection_id=self.connection_id, simulated=ack.simulated)
                        else:
                            self._onset_supported = False
                            self._emit("voice_onset_unsupported", connection_id=self.connection_id,
                                       simulated=ack.simulated, voice=snapshot.voice)
                        snapshot.aborted = True
                        self._async_snapshot = None
                    elif not cleanup and not (snapshot is not None and snapshot.aborted):
                        first_error = first_error or CommandRejected(ack)
                elif snapshot is not None:
                    self._finish_async_snapshot_byte(snapshot, ack)
        if first_error is not None:
            raise first_error
        return replies

    def _async_foreground_locked(self):
        if not self._pending:
            return None
        if self._pending[0].command[0] in (2, 10):
            return self._pending[0]
        parameters_inflight = {flight.pending.command[1] for flight in self._inflight.values()
                               if flight.pending.command[0] in range(4, 10)}
        earlier_voices, blocked_voices = set(), set()
        first = None
        for item in self._pending:
            opcode, voice, value = item.command
            # Output changes affect every voice. A ready note may pass
            # unrelated per-slot preparation, but not an earlier mute/balance.
            # UART ordering suffices; this does not add another ACK wait.
            if opcode in OUTPUT_OPCODES:
                return first if first is not None else item
            blocked = voice in blocked_voices or (opcode == 1 and voice in parameters_inflight)
            if blocked:
                blocked_voices.add(voice)
            else:
                # A prepared note can pass unrelated parameter work. Commands
                # for its own slot retain their order and all parameter ACKs.
                if opcode == 1 and voice not in earlier_voices:
                    return item
                if first is None:
                    first = item
            if 1 <= opcode <= 9:
                earlier_voices.add(voice)
        return first

    @staticmethod
    def _remove_dispatched(items, dispatched):
        return deque(item for item in items if item is not dispatched)

    def _async_step(self):
        with self._condition:
            self._check_async_snapshot_locked()
            if self._closing or self._control is not None:
                return
        self._collect_async_acks()
        with self._condition:
            self._check_async_snapshot_locked()
            if self._closing or self._control is not None:
                return
            now = time.perf_counter()
            if (self._transport.pending_count >= self._transport.max_in_flight
                    or now < self._transport.send_ready_at):
                return
            snapshot, background = None, False
            pending = self._async_foreground_locked()
            if pending is None and self._pending:
                return  # same-slot NOTE_ON waits for its parameter acknowledgements
            if pending is None and self._async_snapshot is not None:
                snapshot = self._async_snapshot
                if snapshot.waiting:
                    return
                pending = _Pending((snapshot.opcode, snapshot.voice, len(snapshot.data)), snapshot.tag)
            elif pending is None and self._background and now >= self._background_ready_at:
                pending, background = self._background[0], True
            elif pending is None and self._transport.pending_count == 0:
                # No pre-snapshot sound ACK may arrive later and change the
                # local generation associated with this hardware snapshot.
                if now >= self._async_next_ping:
                    opcode = 13 if self.voice_count == VOICE_COUNT else 0
                    snapshot = _Snapshot(opcode, 255, 4 if opcode == 13 else 1, "poll")
                elif self._latency_requested:
                    self._latency_requested = False
                    snapshot = _Snapshot(14, 255, LATENCY_STATUS_BYTES, "latency_poll",
                                         self._latency_generation, self._sound_generation)
                elif self._onset_requested_voice is not None:
                    voice = self._onset_requested_voice
                    self._onset_requested_voice = None
                    snapshot = _Snapshot(15, voice, VOICE_ONSET_STATUS_BYTES, "onset_poll",
                                         self._onset_generation, self._sound_generation)
                if snapshot is not None:
                    self._async_snapshot = snapshot
                    pending = _Pending((snapshot.opcode, snapshot.voice, 0), snapshot.tag)
            if pending is None:
                return
        with self._condition:
            self._check_async_snapshot_locked()
            if self._closing or self._control is not None or (snapshot is not None and snapshot.aborted):
                return
            if snapshot is None and not any(item is pending for item in (self._background if background else self._pending)):
                return
            # This lock defines dispatch ordering against NoteOff/PANIC and
            # coalescing. The reservation is no longer queued, but a None send
            # may restore it only if no intervening action cancelled it.
            reservation = _Dispatch(pending, background)
            self._reserved = reservation
            if snapshot is not None:
                snapshot.waiting = True
            elif background:
                self._background = self._remove_dispatched(self._background, pending)
            else:
                self._pending = self._remove_dispatched(self._pending, pending)
        timing = self._transport.send_async(*pending.command)
        with self._condition:
            self._reserved = None
            if timing is not None:
                self._inflight[timing.sequence] = _Flight(pending, timing, snapshot)
            elif snapshot is not None:
                snapshot.waiting = False
            elif not reservation.cancelled and not self._closing and self._control is None:
                if background:
                    self._background.appendleft(pending)
                elif pending.command[0] in (2, 10):
                    self._pending.appendleft(pending)
                else:
                    # A newly queued release keeps its priority when pacing
                    # prevented this reserved ordinary command from being sent.
                    urgent_count = 0
                    while (urgent_count < len(self._pending)
                           and self._pending[urgent_count].command[0] in (2, 10)):
                        urgent_count += 1
                    self._pending.insert(urgent_count, pending)

    def _async_wait_locked(self):
        if self._closing or self._control is not None:
            return
        if self._inflight or self._pending or self._async_snapshot is not None:
            # Python 3.11 Windows sleep uses a high-resolution waitable timer.
            # Short Condition.wait timeouts can round up to a 15.625 ms tick.
            # The serial owner sleeps, never spins; new input waits at most this
            # one short sleep before the next paced transmit decision.
            self._condition.release()
            try:
                time.sleep(0.001)
            finally:
                self._condition.acquire()
        else:
            now = time.perf_counter()
            deadline = self._async_next_ping
            if self._background:
                deadline = min(deadline, max(self._background_ready_at, self._transport.send_ready_at))
            self._condition.wait(max(0.001, deadline - now))

    def _shutdown_async(self):
        self._abort_async_snapshot()
        deadline = time.perf_counter() + self.timeout
        panic_sequence = None
        while time.perf_counter() < deadline:
            replies = self._collect_async_acks(cleanup=True)
            for ack, timing in replies:
                if timing.sequence == panic_sequence and ack.status:
                    raise CommandRejected(ack)
            if panic_sequence is not None and panic_sequence not in self._inflight:
                return
            if panic_sequence is None:
                attempting_at = time.perf_counter()
                try:
                    timing = self._transport.send_async(10, 255, 0)
                except Exception:
                    latest = getattr(self._transport, "last_timing", None)
                    if (isinstance(latest, TransactionTiming) and latest.opcode == 10
                            and latest.write_started >= attempting_at):
                        self._cleanup_panic_sent = True  # includes a partial write attempt
                    raise
                if timing is not None:
                    self._cleanup_panic_sent = True
                    panic_sequence = timing.sequence
                    self._inflight[timing.sequence] = _Flight(_Pending((10, 255, 0), "cleanup"), timing)
            time.sleep(0.001)
        raise TimeoutError("best-effort PANIC did not receive an ACK before cleanup deadline")

    def _emergency_cleanup(self):
        self._abort_async_snapshot()
        self._cleanup_panic_sent = True
        emergency_close = getattr(self._transport, "emergency_close", None)
        if emergency_close is None:
            self._emit("log", message="faulted transport cannot attempt emergency PANIC")
            return
        try:
            result = emergency_close()
            if not result.get("acknowledged", False):
                self._emit("log", message=f"emergency PANIC unconfirmed: {result.get('error') or 'no ACK'}")
        except Exception as exc:
            self._emit("log", message=f"emergency PANIC failed: {exc}")

    def _cleanup(self, reason: str) -> None:
        with self._condition:
            self._pending.clear()
            self._background.clear()
            self._latency_requested = False
            self._onset_requested_voice = None
            self._state = "disconnecting"
        if self._transport is not None:
            self._cleanup_panic_sent = False
            try:
                if getattr(self._transport, "faulted", False):
                    self._emergency_cleanup()
                elif getattr(self._transport, "supports_async", False):
                    self._shutdown_async()
                else:
                    self._ack((10, 255, 0), "cleanup")
            except Exception as exc:
                self._emit("log", message=f"best-effort PANIC failed: {exc}")
                # An older lost ACK may fault the session before cleanup can
                # send PANIC. Make that one independent attempt on its handle.
                # Do not repeat a PANIC already attempted by this cleanup.
                if getattr(self._transport, "faulted", False) and not self._cleanup_panic_sent:
                    self._emergency_cleanup()
            try:
                self._transport.close()
            except Exception as exc:
                self._emit("log", message=f"serial close failed: {exc}")
            self._transport = None
        self._inflight.clear()
        self._reserved = None
        self._async_snapshot = None
        with self._condition:
            self._state = "disconnected"
        self._emit("disconnected", reason=reason)

    def _open(self, port, baud, simulated, output_controls=None) -> None:
        self.connection_id += 1
        self._sound_generation = 0
        self._latency_supported = None
        self._latency_requested = False
        self._onset_supported = None
        self._onset_requested_voice = None
        self.output_controls_supported = {}
        self._inflight.clear()
        self._async_snapshot = None
        if self._factory is not None:
            self._transport = self._factory(port=port, baud=baud, timeout=self.timeout,
                                            simulated=simulated)
        else:
            self._transport = SimulatedTransport() if simulated else SerialTransport(port, baud, self.timeout)
        self._ack((0, 255, 0), "connect")
        self._ack((10, 255, 0), "connect")
        self.voice_count = VOICE_COUNT
        try:
            self._voice_status("connect")
        except CommandRejected as exc:
            if exc.ack.opcode != 13 or exc.ack.status != 1:
                raise
            self.voice_count = 4
        output_values = {}
        if output_controls is not None:
            # PANIC precedes output synchronization; no note can be submitted
            # until both optional settings have been acknowledged or rejected.
            for opcode, value in zip(OUTPUT_OPCODES, output_controls):
                with self._condition:
                    if self._closing or self._control is not None:
                        return
                try:
                    self._ack((opcode, 255, value), "connect_output")
                except CommandRejected as exc:
                    if not self._unsupported_output(exc.ack):
                        raise
                else:
                    self.output_controls_supported[opcode] = True
                    output_values[opcode] = value
        with self._condition:
            if self._closing or self._control is not None:
                return
            self._state = "connected"
        self._async_next_ping = time.perf_counter() + self.ping_interval
        self._emit("connected", port=port or "Offline simulation", baud=baud,
                   simulated=simulated, voice_count=self.voice_count, connection_id=self.connection_id,
                   output_controls_supported=dict(self.output_controls_supported), output_values=output_values,
                   transport_profile=dict(getattr(self._transport, "profile", {})))

    def _run(self) -> None:
        next_ping = time.perf_counter() + self.ping_interval
        try:
            while True:
                with self._condition:
                    if self._closing:
                        break
                    asynchronous = (self._control is None and self._state == "connected"
                                    and getattr(self._transport, "supports_async", False))
                if asynchronous:
                    try:
                        self._async_step()
                    except Exception as exc:
                        self._emit("error", message=str(exc), tag="async")
                        self._cleanup(str(exc))
                    else:
                        with self._condition:
                            self._async_wait_locked()
                    continue
                with self._condition:
                    if self._closing:
                        break
                    control = self._control
                    self._control = None
                    pending = None
                    if control is None and self._state == "connected":
                        if self._pending:
                            pending = self._pending.popleft()
                        elif self._background and time.perf_counter() >= self._background_ready_at:
                            pending = self._background.popleft()
                        elif time.perf_counter() >= next_ping:
                            pending = _Pending((0, 255, 0), "poll")
                        elif self._latency_requested:
                            self._latency_requested = False
                            pending = _Pending((14, 255, 0), "latency_poll", diagnostic_generation=self._latency_generation)
                        elif self._onset_requested_voice is not None:
                            voice = self._onset_requested_voice
                            self._onset_requested_voice = None
                            pending = _Pending((15, voice, 0), "onset_poll", diagnostic_generation=self._onset_generation)
                    if control is None and pending is None:
                        delay = max(0.001, next_ping - time.perf_counter()) if self._state == "connected" else None
                        if self._state == "connected" and self._background:
                            delay = min(delay, max(0.001, self._background_ready_at - time.perf_counter()))
                        self._condition.wait(delay)
                        continue
                try:
                    if control is not None:
                        if control[0] == "connect":
                            self._open(*control[1:])
                            next_ping = time.perf_counter() + self.ping_interval
                        else:
                            self._cleanup("requested")
                    elif pending is not None:
                        if pending.tag == "poll" and self.voice_count == VOICE_COUNT:
                            self._voice_status()
                        elif pending.tag == "latency_poll":
                            self._latency_status(pending.diagnostic_generation)
                        elif pending.tag == "onset_poll":
                            self._voice_onset_status(pending.command[1], pending.diagnostic_generation)
                        else:
                            self._ack(pending.command, pending.tag, pending.submitted_monotonic)
                        if pending.command[0] == 0:
                            next_ping = time.perf_counter() + self.ping_interval
                except Exception as exc:
                    if isinstance(exc, CommandRejected) and self._unsupported_output(exc.ack):
                        continue
                    # Preserve the first failure; cleanup failures are only diagnostic logs.
                    self._emit("error", message=str(exc), tag=pending.tag if pending else "connect")
                    self._cleanup(str(exc))
        finally:
            self._cleanup("closed")
            self._emit("closed")
