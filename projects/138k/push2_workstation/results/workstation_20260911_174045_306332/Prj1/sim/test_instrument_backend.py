"""Headless host concurrency / wire tests; no serial hardware is accessed."""
from __future__ import annotations

from pathlib import Path
from collections import deque
import queue
import sys
import struct
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from instrument_backend import (Ack, AckParser, CommandRejected, ControlWorker,
                                SerialTransport, SimulatedTransport, SYNC, crc16,
                                read_voice_status)
from instrument_backend.transport import _port_interface
from instrument_backend import worker as worker_module
from instrument_backend import transport as transport_module


def frame(seq=0, opcode=0, status=0, active=0):
    payload = bytes((seq, status, active, opcode))
    return SYNC + payload + crc16(payload).to_bytes(2, "little")


class WireTests(unittest.TestCase):
    def test_port_channel_uses_descriptor_not_com_number(self):
        a = SimpleNamespace(device="COM26", hwid=r"FTDIBUS\VID_0403+PID_6010+FT1234A\0000")
        b = SimpleNamespace(device="COM25", hwid=r"FTDIBUS\VID_0403+PID_6010+FT1234B\0000")
        unknown = SimpleNamespace(device="COM26", hwid="", description="USB Serial Port")
        self.assertEqual(_port_interface(a), "A")
        self.assertEqual(_port_interface(b), "B")
        self.assertEqual(_port_interface(unknown), "")

    def test_parser_resync_fragmented_crc_and_structured_fields(self):
        parser = AckParser()
        broken = bytearray(frame())
        broken[7] ^= 1
        packet = frame(23, 5, 3, 0x0D)
        self.assertEqual(parser.feed(b"noise" + broken + packet[:3]), [])
        replies = parser.feed(packet[3:])
        self.assertEqual(len(replies), 1)
        ack = replies[0].as_dict()
        self.assertEqual((ack["sequence"], ack["opcode"], ack["status"], ack["active_mask"]),
                         (23, 5, 3, 0x0D))
        self.assertEqual(ack["header"], packet.hex(" "))
        self.assertFalse(ack["simulated"])

    def test_memory_ack_events_never_expose_flags_as_voice_activity(self):
        for status, simulated in ((0, False), (1, False), (0, True), (1, True)):
            with self.subTest(status=status, simulated=simulated):
                ack = Ack(23, 0x0B, status, 0xCB, 1.5, "test", simulated=simulated)
                event = ack.as_dict()
                self.assertIsNone(event["active_mask"])
                self.assertEqual(event["memory_flags"], 0xCB if status == 0 and not simulated else None)
                self.assertEqual(ack.active_mask, 0xCB)  # Existing raw wire API remains compatible.

    def test_transaction_matches_both_sequence_and_opcode(self):
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                self.data = bytearray()
            def reset_input_buffer(self):
                pass
            def write(self, packet):
                sequence, opcode = packet[2:4]
                self.data.extend(frame(sequence + 1, opcode) + frame(sequence, opcode + 1)
                                 + frame(sequence, opcode, active=5))
                return len(packet)
            def read(self, count):
                data = bytes(self.data[:count])
                del self.data[:count]
                return data
            def close(self):
                pass
        transport = SerialTransport("FAKE", serial_factory=FakeSerial)
        ack = transport.command(3, 1, 42)
        self.assertEqual((ack.sequence, ack.opcode, ack.active_mask), (0, 3, 5))
        self.assertGreaterEqual(ack.rtt_ms, 0)
        transport.close()

    def test_rejection_keeps_ack_and_explains_old_waveform_bitstream(self):
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                self.data = bytearray(frame(0, 5, status=3))
            def reset_input_buffer(self):
                pass
            def write(self, packet):
                return len(packet)
            def read(self, count):
                result = bytes(self.data[:count])
                del self.data[:count]
                return result
            def close(self):
                pass
        transport = SerialTransport("FAKE", serial_factory=FakeSerial)
        with self.assertRaises(CommandRejected) as caught:
            transport.command(5, 0, 2)
        self.assertEqual(caught.exception.ack.status, 3)
        self.assertIn("updated FPGA bitstream", str(caught.exception))
        transport.close()

    def test_timeout_is_bounded_and_does_not_retry(self):
        class FakeSerial:
            writes = 0
            def __init__(self, *args, **kwargs):
                pass
            def reset_input_buffer(self):
                pass
            def write(self, packet):
                self.writes += 1
                return len(packet)
            def read(self, count):
                time.sleep(0.002)
                return b""
            def close(self):
                pass
        transport = SerialTransport("FAKE", timeout=0.03, serial_factory=FakeSerial)
        started = time.perf_counter()
        with self.assertRaises(TimeoutError):
            transport.command(0)
        self.assertLess(time.perf_counter() - started, 0.2)
        self.assertEqual(transport.serial.writes, 1)
        self.assertIsNone(transport.last_timing.ack_received)
        self.assertEqual(transport.last_timing.opcode, 0)
        transport.close()

    def test_offline_simulates_control_state_only(self):
        transport = SimulatedTransport()
        self.assertEqual(transport.command(1, 2, 10).active_mask, 4)
        ack = transport.command(2, 2)
        self.assertTrue(ack.simulated)
        self.assertEqual(ack.rtt_ms, 0)
        self.assertEqual(ack.active_mask, 0)
        self.assertEqual(transport.command(5, 0, 2).status, 0)
        self.assertEqual(transport.command(10).active_mask, 0)

    def test_voice_snapshot_is_atomic_for_all_32_bits(self):
        transport = SimulatedTransport()
        with self.assertRaises(CommandRejected) as invalid:
            transport.command(13, 255, 1)
        self.assertEqual(invalid.exception.ack.status, 3)
        for voice in (0, 8, 16, 31):
            transport.command(1, voice, 42)
        self.assertEqual(transport.command(0).active_mask, 1)
        first = transport.command(13, 255, 0)
        self.assertIsNone(first.as_dict()["active_mask"])
        transport.command(10)
        remaining = [transport.command(13, 255, index).voice_status_byte for index in (1, 2, 3)]
        self.assertEqual(bytes([first.voice_status_byte, *remaining]), b"\x01\x01\x01\x80")
        self.assertEqual(read_voice_status(transport), 0)
        for opcode, voice, value, status in ((1, 32, 1, 2), (13, 255, 4, 3), (13, 0, 0, 2)):
            with self.assertRaises(CommandRejected) as invalid:
                transport.command(opcode, voice, value)
            self.assertEqual(invalid.exception.ack.status, status)

    def test_incomplete_voice_snapshot_is_never_returned_or_retried(self):
        transport = SimulatedTransport()
        calls = []
        real_command = transport.command
        def command(opcode, voice, value):
            calls.append(value)
            if value == 2:
                raise TimeoutError("snapshot interrupted")
            return real_command(opcode, voice, value)
        with patch.object(transport, "command", side_effect=command):
            with self.assertRaises(TimeoutError):
                read_voice_status(transport)
        self.assertEqual(calls, [0, 1, 2])


class HostTimingTests(unittest.TestCase):
    """Deterministic local timing boundaries without opening a port or thread."""
    def setUp(self):
        self.clock = SimpleNamespace(now=1.0)
        local_time = SimpleNamespace(perf_counter=lambda: self.clock.now)
        self.addCleanup(patch.stopall)
        patch.object(worker_module, "time", local_time).start()
        patch.object(transport_module, "time", local_time).start()

    def worker(self, transport):
        worker = object.__new__(ControlWorker)
        worker._closing = False
        worker._state = "connected"
        worker._pending = deque()
        worker._background = deque()
        worker._background_ready_at = 0.0
        worker._condition = threading.Condition()
        worker.max_queue = 512
        worker.voice_count = 32
        worker.events = queue.Queue()
        worker._transport = transport
        return worker

    def dispatch(self, worker, at):
        self.clock.now = at
        item = worker._pending.popleft()
        worker._ack(item.command, item.tag, item.submitted_monotonic)
        return worker.events.get_nowait()

    def serial_transport(self, status=0):
        clock = self.clock
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                self.data = b""
            def reset_input_buffer(self):
                pass
            def write(self, packet):
                clock.now += 0.010
                self.data = frame(packet[2], packet[3], status=status)
                return len(packet)
            def read(self, count):
                clock.now += 0.012
                return self.data
            def close(self):
                pass
        return SerialTransport("FAKE", serial_factory=FakeSerial)

    def test_queue_ends_at_actual_write_and_total_ends_at_matching_ack(self):
        transport = self.serial_transport()
        worker = self.worker(transport)
        worker.submit([(1, 31, 42)], tag="intent")
        encode = transport_module.encode_packet
        def prepare(*args):
            # Packet preparation is after dispatch but before serial.write.
            self.clock.now += .003
            return encode(*args)
        with patch.object(transport_module, "encode_packet", side_effect=prepare):
            event = self.dispatch(worker, 1.050)
        self.assertAlmostEqual(event["queue_wait_ms"], 53)
        self.assertAlmostEqual(event["rtt_ms"], 22)
        self.assertAlmostEqual(event["host_total_ms"], 75)
        self.assertAlmostEqual(event["host_total_ms"], event["queue_wait_ms"] + event["rtt_ms"])
        self.assertEqual(event["timing_source"], "serial")
        self.assertFalse(event["simulated"])

    def test_callback_timestamp_includes_pre_submit_work_and_rejects_invalid_origins(self):
        worker = self.worker(SimulatedTransport())
        self.clock.now = 2
        self.assertTrue(worker.submit([(1, 0, 42)], submitted_at=1))
        self.assertEqual(self.dispatch(worker, 3)["queue_wait_ms"], 2000)
        for invalid in (True, float("nan"), float("inf"), 4, "1"):
            self.assertFalse(worker.submit([(1, 0, 42)], submitted_at=invalid))
            self.assertEqual(worker.events.get_nowait()["type"], "error")
        self.assertEqual(len(worker._pending), 0)

    def test_batch_replacement_and_urgent_priority_keep_each_submission_time(self):
        worker = self.worker(SimulatedTransport())
        worker.submit([(6, 1, 1), (7, 1, 1)], tag="obsolete", coalesce_key="patch:1")
        self.clock.now = 2
        worker.submit([(6, 1, 2), (7, 1, 2)], tag="replacement", coalesce_key="patch:1")
        self.clock.now = 3
        worker.submit([(2, 31, 0)], tag="release")
        events = [self.dispatch(worker, at) for at in (10, 11, 12)]
        self.assertEqual([event["tag"] for event in events], ["release", "replacement", "replacement"])
        self.assertEqual([event["queue_wait_ms"] for event in events], [7000, 9000, 10000])
        self.assertTrue(all(event["timing_source"] == "simulated" and event["simulated"] for event in events))
        self.assertTrue(all(event["rtt_ms"] == 0 for event in events))
        self.assertEqual([event["host_total_ms"] for event in events], [7000, 9000, 10000])

    def test_panic_submission_captures_intent_before_validation_and_cancels_queue(self):
        worker = self.worker(SimulatedTransport())
        worker.submit([(1, 0, 42)], tag="cancelled")
        self.clock.now = 2
        encode = worker_module.encode_packet
        def validate(*args):
            self.clock.now += .1
            return encode(*args)
        with patch.object(worker_module, "encode_packet", side_effect=validate):
            worker.submit([(10, 255, 0)], tag="panic-submit")
        self.assertEqual(len(worker._pending), 1)
        event = self.dispatch(worker, 3)
        self.assertEqual(event["tag"], "panic-submit")
        self.assertEqual(event["queue_wait_ms"], 1000)
        self.clock.now = 4
        worker.panic()
        self.assertEqual(self.dispatch(worker, 5)["queue_wait_ms"], 1000)

    def test_background_ack_does_not_claim_user_queue_or_total_latency(self):
        worker = self.worker(self.serial_transport())
        worker._ack((0, 255, 0), "poll")
        event = worker.events.get_nowait()
        self.assertIsNone(event["queue_wait_ms"])
        self.assertIsNone(event["host_total_ms"])
        self.assertEqual(event["timing_source"], "serial")
        self.assertAlmostEqual(event["rtt_ms"], 22)

    def test_preload_has_no_input_timestamp_and_foreground_cancels_its_slot(self):
        worker = self.worker(SimulatedTransport())
        self.assertTrue(worker.submit([(5, 31, 2), (4, 31, 42), (6, 0, 23)], tag="preload", background=True))
        self.assertEqual(worker.pending_count, 3)
        self.assertTrue(all(item.submitted_monotonic is None for item in worker._background))
        worker.submit([(1, 31, 42)], tag="note")
        self.assertEqual([item.command for item in worker._background], [(6, 0, 23)])
        self.assertEqual(worker.events.get_nowait(), {"type": "patch_preload_cancelled", "tag": "preload", "voice": 31})
        self.assertEqual(self.dispatch(worker, 2)["tag"], "note")
        item = worker._background.popleft()
        worker._ack(item.command, item.tag, item.submitted_monotonic)
        ack = worker.events.get_nowait()
        self.assertIsNone(ack["queue_wait_ms"])
        self.assertIsNone(ack["host_total_ms"])
        self.assertEqual(worker._background_ready_at, 2.5)

    def test_preload_only_accepts_parameters_and_never_blocks_foreground_capacity(self):
        worker = self.worker(SimulatedTransport())
        worker.max_queue = 8
        for command in ((1, 0, 42), (2, 0, 0), (10, 255, 0)):
            self.assertFalse(worker.submit([command], background=True))
        self.assertFalse(worker.submit([(4, 0, 42)], submitted_at=1.0, background=True))
        self.assertTrue(worker.submit([(4, 31, n) for n in range(8)], tag="preload", background=True))
        self.assertTrue(worker.submit([(4, 0, n) for n in range(8)], tag="foreground"))
        self.assertEqual(worker.pending_count, 8)
        self.assertFalse(worker._background)
        worker.panic()
        self.assertEqual(worker.pending_count, 1)

    def test_rejected_ack_retains_local_timing_without_claiming_success(self):
        worker = self.worker(self.serial_transport(status=3))
        worker.submit([(5, 0, 99)], tag="rejected")
        with self.assertRaises(CommandRejected):
            self.dispatch(worker, 2)
        event = worker.events.get_nowait()
        self.assertEqual(event["status"], 3)
        self.assertEqual(event["queue_wait_ms"], 1000)
        self.assertAlmostEqual(event["host_total_ms"], 1022)


class FakeTransport(SimulatedTransport):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.threads = set()
        self.block = threading.Event()
        self.entered = threading.Event()
        self.should_block = False
        self.failure = None
        self.cleanup_failure = False
        self.closed = False

    def command(self, opcode, voice=255, value=0):
        self.threads.add(threading.get_ident())
        self.calls.append((opcode, voice, value))
        if opcode == 3 and self.should_block:
            self.entered.set()
            if not self.block.wait(2):
                raise TimeoutError("test gate timed out")
            if self.failure:
                raise self.failure
        if opcode == 10 and self.cleanup_failure:
            raise OSError("cleanup failed")
        return super().command(opcode, voice, value)

    def close(self):
        self.threads.add(threading.get_ident())
        self.closed = True


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.worker = ControlWorker(ping_interval=60, max_queue=8,
                                    transport_factory=lambda **kwargs: self.transport)
        self.worker.connect("FAKE")
        self.wait_event("connected")

    def tearDown(self):
        self.transport.block.set()
        self.worker.close()
        self.wait_event("closed")
        self.worker._thread.join(1)
        self.assertFalse(self.worker.is_alive)

    def wait_event(self, kind, tag=None, timeout=2):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            try:
                event = self.worker.events.get(timeout=max(0.001, deadline - time.perf_counter()))
            except queue.Empty:
                break
            if event["type"] == kind and (tag is None or event.get("tag") == tag):
                return event
        self.fail(f"missing {kind} event with tag {tag}")

    def block_worker(self):
        self.transport.should_block = True
        self.worker.submit([(3, 0, 1)], tag="gate")
        self.assertTrue(self.transport.entered.wait(1))
        self.after_gate = len(self.transport.calls)

    def test_connect_starts_with_ping_and_panic(self):
        self.assertEqual(self.transport.calls[:2], [(0, 255, 0), (10, 255, 0)])
        self.assertEqual(self.transport.calls[2:6], [(13, 255, index) for index in range(4)])
        self.worker.submit([(1, 0, 42)], tag="note")
        event = self.wait_event("ack", "note")
        self.assertEqual(event["active_mask"], 1)
        self.assertEqual(len(self.transport.threads), 1)
        self.assertNotIn(threading.get_ident(), self.transport.threads)

    def test_memory_query_event_separates_flags_and_keeps_normal_poll_activity(self):
        self.worker.submit([(1, 2, 42)], tag="note")
        self.assertEqual(self.wait_event("ack", "note")["active_mask"], 4)
        memory_ack = Ack(2, 0x0B, 0, 0xCB, 1.5, "test")
        with patch.object(self.transport, "command", return_value=memory_ack) as command:
            self.assertTrue(self.worker.submit([(0x0B, 255, 0)], tag="memory"))
            event = self.wait_event("ack", "memory")
            command.assert_called_once_with(0x0B, 255, 0)
        self.assertIsNone(event["active_mask"])
        self.assertEqual(event["memory_flags"], 0xCB)
        self.worker.submit([(0, 255, 0)], tag="after-memory")
        normal = self.wait_event("ack", "after-memory")
        self.assertEqual(normal["active_mask"], 4)
        self.assertIsNone(normal["memory_flags"])

    def test_rejected_simulated_memory_query_has_no_hardware_or_voice_state(self):
        self.assertTrue(self.worker.submit([(0x0B, 255, 0)], tag="memory"))
        event = self.wait_event("ack", "memory")
        self.assertEqual(event["status"], 1)
        self.assertTrue(event["simulated"])
        self.assertIsNone(event["active_mask"])
        self.assertIsNone(event["memory_flags"])
        self.assertIn("unknown opcode", self.wait_event("error", "memory")["message"])

    def test_coalesce_keeps_only_latest_unsent_parameter_batch(self):
        self.block_worker()
        self.worker.submit([(6, 1, 10), (7, 1, 20)], coalesce_key="patch:1", tag="old")
        self.worker.submit([(6, 1, 30), (7, 1, 40)], coalesce_key="patch:1", tag="new")
        self.assertEqual(self.worker.pending_count, 2)
        self.transport.block.set()
        self.wait_event("ack", "new")
        self.wait_event("ack", "new")
        self.assertNotIn((6, 1, 10), self.transport.calls)
        self.assertEqual(self.transport.calls[-2:], [(6, 1, 30), (7, 1, 40)])

    def test_release_cancels_note_on_inside_unsent_batch(self):
        self.block_worker()
        self.worker.submit([(4, 1, 20), (1, 1, 100)], tag="note_on:1:60")
        self.worker.submit([(2, 1, 0)], tag="note_off:1")
        self.transport.block.set()
        self.wait_event("ack", "note_off:1")
        self.assertNotIn((1, 1, 100), self.transport.calls)
        self.assertEqual(self.transport.calls[self.after_gate], (2, 1, 0))

    def test_release_enters_full_queue_and_panic_flushes_it(self):
        self.block_worker()
        self.assertTrue(self.worker.submit([(4, 0, n) for n in range(8)]))
        self.assertFalse(self.worker.submit([(4, 1, 1)]))
        self.assertTrue(self.worker.submit([(2, 3, 0)], tag="release"))
        self.assertLessEqual(self.worker.pending_count, 8)
        self.assertTrue(self.worker.panic())
        self.assertEqual(self.worker.pending_count, 1)
        self.transport.block.set()
        self.wait_event("ack", "panic")
        self.assertEqual(self.transport.calls[self.after_gate:], [(10, 255, 0)])

    def test_release_waits_behind_already_queued_panic(self):
        self.block_worker()
        self.worker.panic()
        self.worker.submit([(2, 1, 0)], tag="release")
        self.transport.block.set()
        self.wait_event("ack", "release")
        self.assertEqual(self.transport.calls[self.after_gate:self.after_gate+2], [(10, 255, 0), (2, 1, 0)])

    def test_failure_clears_pending_and_preserves_initial_error(self):
        self.block_worker()
        self.transport.failure = TimeoutError("first transaction timeout")
        self.transport.cleanup_failure = True
        self.worker.submit([(1, 0, 111)], tag="must-not-replay")
        self.transport.block.set()
        event = self.wait_event("error", "gate")
        self.assertEqual(event["message"], "first transaction timeout")
        disconnected = self.wait_event("disconnected")
        self.assertEqual(disconnected["reason"], "first transaction timeout")
        self.assertTrue(self.transport.closed)
        self.assertEqual(self.worker.pending_count, 0)
        self.assertNotIn((1, 0, 111), self.transport.calls)
        self.assertFalse(self.worker.submit([(1, 0, 123)]))

    def test_disconnect_and_close_are_nonblocking_and_clear_commands(self):
        self.block_worker()
        self.worker.submit([(1, 0, 33)])
        started = time.perf_counter()
        self.worker.disconnect()
        self.assertLess(time.perf_counter() - started, 0.05)
        self.transport.block.set()
        self.wait_event("disconnected")
        self.assertTrue(self.transport.closed)
        self.assertNotIn((1, 0, 33), self.transport.calls)
        self.assertEqual(self.transport.calls[-1], (10, 255, 0))

    def test_close_in_flight_flushes_unsent_note_and_finishes_panic(self):
        self.block_worker()
        self.worker.submit([(1, 0, 33)])
        started = time.perf_counter()
        self.worker.close()
        self.assertLess(time.perf_counter() - started, 0.05)
        self.transport.block.set()
        self.wait_event("disconnected")
        self.assertTrue(self.transport.closed)
        self.assertNotIn((1, 0, 33), self.transport.calls)
        self.assertEqual(self.transport.calls[-1], (10, 255, 0))

    def test_periodic_poll_reads_full_voice_snapshot(self):
        self.worker.ping_interval = 0.02
        # An explicit ping establishes the next interval without waking via sleeps.
        self.worker.submit([(0, 255, 0)], tag="manual")
        self.wait_event("ack", "manual")
        self.assertEqual(self.wait_event("ack", "poll")["opcode"], 13)
        self.assertEqual(self.wait_event("voice_status")["active_mask"], 0)

    def test_preload_yields_after_one_ack_and_resumes_only_after_foreground_idle(self):
        original = self.transport.command
        before = len(self.transport.calls)
        def command(opcode, voice=255, value=0):
            ack = original(opcode, voice, value)
            if opcode == 5:
                self.worker.submit([(1, 0, 42)], tag="play")
                time.sleep(0.015)
            return ack
        with patch.object(self.transport, "command", side_effect=command):
            self.worker.submit([(5, 31, 2), (4, 31, 23)], tag="preload", background=True)
            self.wait_event("ack", "preload")
            self.wait_event("ack", "play")
            completed = time.perf_counter()
            self.wait_event("ack", "preload")
            self.assertGreaterEqual(time.perf_counter() - completed, 0.45)
        self.assertEqual(self.transport.calls[before:], [(5, 31, 2), (1, 0, 42), (4, 31, 23)])

    def test_due_background_poll_never_overtakes_queued_musical_work(self):
        self.worker.ping_interval = 0.005
        self.worker.submit([(0, 255, 0)], tag="prime")
        self.wait_event("ack", "prime")
        self.block_worker()
        self.worker.submit([(4, 31, 23), (1, 31, 42)], tag="foreground")
        time.sleep(0.015)  # poll becomes due while an ACK is in flight
        self.transport.block.set()
        self.wait_event("ack", "foreground")
        self.wait_event("ack", "foreground")
        self.assertEqual(self.transport.calls[self.after_gate:self.after_gate + 2],
                         [(4, 31, 23), (1, 31, 42)])

    def test_15ms_status_ack_blocks_note_or_parameter_for_one_byte_only(self):
        original = self.transport.command
        for opcode in (1, 4):
            with self.subTest(opcode=opcode):
                start = len(self.transport.calls)
                def command(operation, voice=255, value=0):
                    ack = original(operation, voice, value)
                    if operation == 13:
                        if value == 0:
                            self.worker.ping_interval = 60
                            self.worker.submit([(opcode, 31, 42)], tag="interactive")
                        time.sleep(0.015)  # reproduce a 15 ms USB ACK per byte
                    return ack
                with patch.object(self.transport, "command", side_effect=command):
                    self.worker.ping_interval = 0.005
                    self.worker.submit([(0, 255, 0)], tag="trigger")
                    self.wait_event("ack", "trigger")
                    events = []
                    while True:
                        event = self.worker.events.get(timeout=2)
                        events.append(event)
                        if event.get("tag") == "interactive":
                            break
                calls = self.transport.calls[start:]
                self.assertEqual(calls, [(0, 255, 0), (13, 255, 0), (opcode, 31, 42)])
                self.assertGreaterEqual(event["queue_wait_ms"], 14)
                self.assertFalse(any(item["type"] == "voice_status" for item in events))

    def test_top_voice_release_enters_full_queue_and_cancels_pending_note(self):
        self.block_worker()
        self.worker.submit([(4, 31, 20), (1, 31, 100)], tag="high-note")
        self.assertTrue(self.worker.submit([(2, 31, 0)], tag="high-release"))
        self.transport.block.set()
        self.wait_event("ack", "high-release")
        self.assertNotIn((1, 31, 100), self.transport.calls)
        self.assertEqual(self.transport.calls[self.after_gate], (2, 31, 0))

    def test_urgent_release_interrupts_snapshot_without_publishing_partial_mask(self):
        self.block_worker()
        self.worker.submit([(1, 31, 42)])
        self.transport.block.set()
        self.wait_event("ack", "gate")
        self.wait_event("ack")
        while not self.worker.events.empty():
            self.worker.events.get_nowait()
        original = self.transport.command
        def command(opcode, voice=255, value=0):
            ack = original(opcode, voice, value)
            if opcode == 13 and value == 1:
                self.worker.submit([(2, 31, 0)], tag="snapshot-release")
            return ack
        with patch.object(self.transport, "command", side_effect=command):
            self.worker.ping_interval = 0.02
            self.worker.submit([(0, 255, 0)], tag="trigger")
            self.wait_event("ack", "trigger")
            events = []
            while True:
                event = self.worker.events.get(timeout=2)
                events.append(event)
                if event.get("tag") == "snapshot-release":
                    break
        self.assertFalse(any(event["type"] == "voice_status" for event in events))
        self.assertEqual(self.transport.calls[-3:], [(13, 255, 0), (13, 255, 1), (2, 31, 0)])

    def test_latency_unsupported_keeps_playing_and_is_not_repeated(self):
        self.assertTrue(self.worker.request_latency_status())
        unsupported = self.wait_event("latency_unsupported")
        self.assertTrue(unsupported["simulated"])
        self.assertFalse(self.worker.request_latency_status())
        self.assertTrue(self.worker.submit([(1, 31, 42)], tag="still-playing"))
        self.assertEqual(self.wait_event("ack", "still-playing")["status"], 0)
        self.assertFalse(self.transport.closed)

    def test_latency_snapshot_reads_64_bytes_only_when_queue_is_empty(self):
        snapshot = struct.pack("<16I", 1, 0, 0, 50_000_000, *([0] * 9), 1024, 0, 0)
        original = self.transport.command
        def command(opcode, voice=255, value=0):
            if opcode == 14:
                self.transport.calls.append((opcode, voice, value))
                return Ack(value, opcode, 0, snapshot[value], 1, "test")
            return original(opcode, voice, value)
        with patch.object(self.transport, "command", side_effect=command):
            self.worker.request_latency_status()
            event = self.wait_event("latency_status")
        self.assertEqual(event["status"]["clock_hz"], 50_000_000)
        self.assertEqual(event["connection_id"], self.worker.connection_id)
        self.assertEqual(self.transport.calls[-64:], [(14, 255, index) for index in range(64)])

    def test_any_play_command_interrupts_latency_snapshot_and_discards_partial_data(self):
        original = self.transport.command
        def command(opcode, voice=255, value=0):
            if opcode == 14:
                self.transport.calls.append((opcode, voice, value))
                if value == 2:
                    self.worker.submit([(4, 31, 42)], tag="interactive")
                return Ack(value, opcode, 0, 0, 1, "test")
            return original(opcode, voice, value)
        with patch.object(self.transport, "command", side_effect=command):
            self.worker.request_latency_status()
            events = []
            while True:
                event = self.worker.events.get(timeout=2)
                events.append(event)
                if event.get("tag") == "interactive":
                    break
        self.assertTrue(any(event["type"] == "latency_status_aborted" for event in events))
        self.assertFalse(any(event["type"] == "latency_status" for event in events))
        self.assertEqual(self.transport.calls[-4:], [(14, 255, 0), (14, 255, 1), (14, 255, 2), (4, 31, 42)])

    def test_voice_onset_unknown_keeps_connection_and_does_not_repeat(self):
        self.assertTrue(self.worker.request_voice_onset_status(31))
        event = self.wait_event("voice_onset_unsupported")
        self.assertTrue(event["simulated"])
        self.assertFalse(self.worker.request_voice_onset_status(31))
        self.assertTrue(self.worker.submit([(1, 31, 42)], tag="play-after-onset"))
        self.assertEqual(self.wait_event("ack", "play-after-onset")["status"], 0)
        self.assertFalse(self.transport.closed)

    def test_voice_onset_atomic_query_keeps_one_voice_and_connection(self):
        raw = struct.pack("<8I", 1 | 31 << 8 | 9 << 16 | 7 << 24, 22, 50_000_000, 226, 1300, 1300, 5, 0)
        original = self.transport.command
        def command(opcode, voice=255, value=0):
            if opcode == 15:
                self.transport.calls.append((opcode, voice, value))
                return Ack(value, opcode, 0, raw[value], 1, "test")
            return original(opcode, voice, value)
        with patch.object(self.transport, "command", side_effect=command):
            self.worker.request_voice_onset_status(31)
            event = self.wait_event("voice_onset_status")
        self.assertEqual(event["connection_id"], self.worker.connection_id)
        self.assertEqual(event["status"]["note_id"], 22)
        self.assertEqual(self.transport.calls[-32:], [(15, 31, index) for index in range(32)])

    def test_parameter_command_interrupts_voice_onset_query_without_publishing_partial(self):
        original = self.transport.command
        def command(opcode, voice=255, value=0):
            if opcode == 15:
                self.transport.calls.append((opcode, voice, value))
                if value == 1:
                    self.worker.submit([(4, 0, 42)], tag="onset-interrupt")
                return Ack(value, opcode, 0, 0, 1, "test")
            return original(opcode, voice, value)
        with patch.object(self.transport, "command", side_effect=command):
            self.worker.request_voice_onset_status(31)
            events = []
            while True:
                event = self.worker.events.get(timeout=2)
                events.append(event)
                if event.get("tag") == "onset-interrupt":
                    break
        self.assertTrue(any(event["type"] == "voice_onset_aborted" for event in events))
        self.assertFalse(any(event["type"] == "voice_onset_status" for event in events))
        self.assertEqual(self.transport.calls[-3:], [(15, 31, 0), (15, 31, 1), (4, 0, 42)])

    def test_switching_selected_voice_aborts_old_snapshot_and_reads_new_voice(self):
        original = self.transport.command
        def command(opcode, voice=255, value=0):
            if opcode == 15:
                self.transport.calls.append((opcode, voice, value))
                if voice == 31 and value == 1:
                    self.worker.request_voice_onset_status(7)
                raw = struct.pack("<8I", 1 | voice << 8 | 1 << 24, 3, 50_000_000, 0, 0, 100, 4, 0)
                return Ack(value, opcode, 0, raw[value], 1, "test")
            return original(opcode, voice, value)
        with patch.object(self.transport, "command", side_effect=command):
            self.worker.request_voice_onset_status(31)
            self.assertEqual(self.wait_event("voice_onset_aborted")["voice"], 31)
            self.assertEqual(self.wait_event("voice_onset_status")["voice"], 7)
        onset_calls = [command for command in self.transport.calls if command[0] == 15]
        self.assertEqual(onset_calls, [(15, 31, 0), (15, 31, 1)] + [(15, 7, index) for index in range(32)])

    def test_bad_voice_onset_selection_is_rejected_before_queuing(self):
        before = len(self.transport.calls)
        for voice in (-1, 32, True, "0"):
            self.assertFalse(self.worker.request_voice_onset_status(voice))
        self.assertEqual(len(self.transport.calls), before)

    def test_cancel_between_queue_pop_and_query_dispatch_sends_no_onset_byte(self):
        original = self.worker._voice_onset_status
        def cancel_before_dispatch(voice, generation):
            self.worker.cancel_voice_onset_status()
            original(voice, generation)
        with patch.object(self.worker, "_voice_onset_status", side_effect=cancel_before_dispatch):
            self.worker.request_voice_onset_status(31)
            self.wait_event("voice_onset_aborted")
        self.assertFalse(any(command[0] == 15 for command in self.transport.calls))


class ConnectFailureTests(unittest.TestCase):
    def test_unknown_snapshot_opcode_downgrades_once_and_blocks_high_voices(self):
        class Legacy(FakeTransport):
            def command(self, opcode, voice=255, value=0):
                if opcode == 13:
                    self.calls.append((opcode, voice, value))
                    raise CommandRejected(Ack(2, 13, 1, 0, 0, "legacy"))
                return super().command(opcode, voice, value)
        transport = Legacy()
        worker = ControlWorker(ping_interval=0.02, transport_factory=lambda **kwargs: transport)
        worker.connect("LEGACY")
        try:
            events = []
            while True:
                event = worker.events.get(timeout=2)
                events.append(event)
                if event["type"] == "connected":
                    break
            self.assertEqual(event["voice_count"], 4)
            self.assertFalse(any(event["type"] == "error" for event in events))
            self.assertFalse(worker.submit([(1, 31, 42)]))
            while True:
                event = worker.events.get(timeout=2)
                if event.get("tag") == "poll":
                    break
            self.assertEqual(event["opcode"], 0)
            self.assertEqual(sum(opcode == 13 for opcode, voice, value in transport.calls), 1)
        finally:
            worker.close()
            worker._thread.join(1)
            self.assertFalse(worker.is_alive)

    def test_failed_handshake_never_announces_connection_or_replays(self):
        class Unresponsive(FakeTransport):
            def command(self, opcode, voice=255, value=0):
                self.calls.append((opcode, voice, value))
                raise TimeoutError("handshake timed out")
        transport = Unresponsive()
        worker = ControlWorker(transport_factory=lambda **kwargs: transport)
        events = []
        worker.connect("FAKE")
        try:
            while True:
                event = worker.events.get(timeout=2)
                events.append(event)
                if event["type"] == "disconnected":
                    break
            self.assertFalse(any(event["type"] == "connected" for event in events))
            self.assertEqual([event["message"] for event in events if event["type"] == "error"],
                             ["handshake timed out"])
            self.assertEqual(transport.calls, [(0, 255, 0), (10, 255, 0)])
            self.assertFalse(worker.submit([(1, 0, 12)]))
            self.assertTrue(transport.closed)
        finally:
            worker.close()
            worker._thread.join(1)
            self.assertFalse(worker.is_alive)


if __name__ == "__main__":
    unittest.main()
