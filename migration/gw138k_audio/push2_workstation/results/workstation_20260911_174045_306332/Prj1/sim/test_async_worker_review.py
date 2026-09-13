"""Adversarial asynchronous worker regressions; no threads or hardware ports."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import queue
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from instrument_backend import Ack, CommandRejected
from instrument_backend.transport import TransactionTiming
from instrument_backend import worker as worker_module


class DelayedTransport:
    supports_async = True
    max_in_flight = 16
    send_interval = .0015

    def __init__(self, clock, ack_delay=.017):
        self.clock = clock
        self.ack_delay = ack_delay
        self.send_ready_at = 0.0
        self.sequence = 0
        self.frames = {}
        self.sent = []
        self.completed = []
        self.closed = False
        self.hold_acks = False
        self.reject = {}
        self.before_send = None
        self.during_poll = None
        self.max_pending_seen = 0
        self.sync_calls = []
        self.last_timing = TransactionTiming(255, 255, -100, -50)

    @property
    def pending_count(self):
        return len(self.frames)

    @property
    def next_deadline(self):
        return min((timing.write_started + .35 for _, timing in self.frames.values()), default=None)

    def command(self, *command):
        self.sync_calls.append(command)
        raise AssertionError("the connected async worker must never use synchronous command")

    def send_async(self, opcode, voice=255, value=0):
        if self.closed:
            raise OSError("closed test transport")
        if self.before_send is not None:
            hook, self.before_send = self.before_send, None
            if hook(opcode, voice, value) is False:
                return None
        now = self.clock.now
        if len(self.frames) >= self.max_in_flight or now < self.send_ready_at or self.sequence in self.frames:
            return None
        timing = TransactionTiming(self.sequence, opcode, now)
        self.sequence = (self.sequence + 1) & 255
        self.frames[timing.sequence] = ((opcode, voice, value), timing)
        self.sent.append(((opcode, voice, value), timing))
        self.send_ready_at = now + self.send_interval
        self.max_pending_seen = max(self.max_pending_seen, len(self.frames))
        return timing

    def _ack_byte(self, command):
        opcode, voice, value = command
        if opcode == 13:
            return (0x80000001 >> (8 * value)) & 255
        if opcode == 14:
            return struct.pack("<16I", 1, 0, 0, 50_000_000, *([0] * 9), 1024, 0, 0)[value]
        if opcode == 15:
            return struct.pack("<8I", 1 | voice << 8, 0, 50_000_000, 0, 0, 0, 0, 0)[value]
        return 0

    def poll_acks(self):
        if self.during_poll is not None:
            hook, self.during_poll = self.during_poll, None
            hook()
        if self.hold_acks:
            return []
        replies = []
        for sequence, (command, timing) in list(self.frames.items()):
            if self.clock.now < timing.write_started + self.ack_delay:
                continue
            opcode = command[0]
            ack = Ack(sequence, opcode, self.reject.get(opcode, 0), self._ack_byte(command),
                      (self.clock.now - timing.write_started) * 1000, "fake", simulated=False)
            completion = replace(timing, ack_received=self.clock.now)
            replies.append((ack, completion))
            self.completed.append((command, completion))
            del self.frames[sequence]
        return replies

    def close(self):
        self.closed = True


class AsyncWorkerReviewTests(unittest.TestCase):
    def setUp(self):
        self.clock = SimpleNamespace(now=100.0)
        clock_api = SimpleNamespace(perf_counter=lambda: self.clock.now, sleep=self.advance)
        self.addCleanup(patch.stopall)
        patch.object(worker_module, "time", clock_api).start()
        with patch.object(worker_module.threading.Thread, "start"):
            self.worker = worker_module.ControlWorker(ping_interval=60)
        self.transport = DelayedTransport(self.clock)
        self.worker._transport = self.transport
        self.worker._state = "connected"
        self.worker.connection_id = 7
        self.worker._async_next_ping = 160.0

    def advance(self, seconds):
        self.clock.now += seconds

    def step(self, seconds=.002):
        self.advance(seconds)
        self.worker._async_step()

    def events(self):
        result = []
        while True:
            try:
                result.append(self.worker.events.get_nowait())
            except queue.Empty:
                return result

    def commands(self):
        return [command for command, timing in self.transport.sent]

    def test_second_ready_voice_sends_before_first_17ms_ack(self):
        self.worker.submit([(1, 0, 42)], tag="first")
        self.step()
        first = self.transport.sent[0][1]
        self.worker.submit([(1, 31, 43)], tag="second")
        self.step()
        second = self.transport.sent[1][1]
        self.assertEqual(self.commands(), [(1, 0, 42), (1, 31, 43)])
        self.assertLess(second.write_started - first.write_started, .010)
        self.assertEqual(self.transport.completed, [])
        self.assertEqual(self.transport.pending_count, 2)

    def test_each_ack_uses_its_own_timing_not_last_timing(self):
        self.worker.submit([(1, 0, 42)], tag="first")
        self.step()
        self.advance(.004)
        self.worker.submit([(1, 31, 43)], tag="second")
        self.step()
        self.step(.020)
        acks = [event for event in self.events() if event["type"] == "ack"]
        self.assertEqual([event["tag"] for event in acks], ["first", "second"])
        self.assertAlmostEqual(acks[0]["queue_wait_ms"], 2)
        self.assertAlmostEqual(acks[1]["queue_wait_ms"], 2)
        self.assertGreater(acks[0]["rtt_ms"], acks[1]["rtt_ms"])
        for event in acks:
            self.assertAlmostEqual(event["host_total_ms"], event["queue_wait_ms"] + event["rtt_ms"])
            self.assertEqual(event["timing_source"], "serial")

    def test_same_slot_note_waits_for_all_six_parameter_acks(self):
        parameters = [(opcode, 0, 1) for opcode in (5, 4, 6, 7, 8, 9)]
        self.worker.submit(parameters + [(1, 0, 42)], tag="cold")
        for _ in parameters:
            self.step()
        self.assertEqual(self.commands(), parameters)
        self.assertEqual(self.transport.completed, [])
        self.step(.012)  # earliest parameter ACKs arrive, last ones remain
        self.assertNotIn((1, 0, 42), self.commands())
        self.step(.010)
        self.assertEqual(self.commands()[-1], (1, 0, 42))
        self.assertEqual(len(self.transport.completed), 6)

    def test_other_ready_slot_passes_waiting_cold_note_and_unrelated_parameters(self):
        self.worker.submit([(5, 0, 2), (4, 0, 1), (1, 0, 42)], tag="cold")
        self.step()
        self.worker.submit([(1, 31, 43)], tag="ready")
        self.step()
        self.assertEqual(self.commands()[:2], [(5, 0, 2), (1, 31, 43)])
        self.assertEqual(self.transport.completed, [])
        self.step()
        self.assertEqual(self.commands()[-1], (4, 0, 1))
        self.step()
        self.assertNotIn((1, 0, 42), self.commands())

    def test_parameter_rejection_never_dispatches_dependent_note(self):
        self.transport.reject[5] = 3
        self.worker.submit([(5, 0, 2), (4, 0, 1), (1, 0, 42)], tag="rejected-patch")
        self.step()
        self.step()
        with self.assertRaises(CommandRejected):
            self.step(.020)
        self.assertNotIn((1, 0, 42), self.commands())
        self.worker._cleanup("parameter rejected")
        self.assertNotIn((1, 0, 42), self.commands())
        self.assertEqual(self.commands()[-1], (10, 255, 0))
        self.assertTrue(self.transport.closed)
        self.assertEqual(self.transport.sync_calls, [])

    def test_release_cancels_unsent_note_and_passes_parameter_ack_wait(self):
        self.worker.submit([(5, 0, 2), (1, 0, 42)], tag="cold")
        self.step()
        self.worker.submit([(2, 0, 0)], tag="release")
        self.step()
        self.assertEqual(self.commands(), [(5, 0, 2), (2, 0, 0)])
        self.assertEqual(self.transport.completed, [])
        self.step(.020)
        self.assertNotIn((1, 0, 42), self.commands())

    def test_panic_follows_sent_note_and_cancels_unsent_tail_before_new_note(self):
        self.worker.submit([(1, 0, 42), (1, 1, 43)], tag="old")
        self.step()
        self.worker.panic()
        self.worker.submit([(1, 31, 44)], tag="new-after-panic")
        self.step()
        self.step()
        self.assertEqual(self.commands(), [(1, 0, 42), (10, 255, 0), (1, 31, 44)])
        self.assertEqual(self.transport.completed, [])

    def test_none_send_restores_uncancelled_reservation_once(self):
        self.worker.submit([(1, 0, 42)], tag="note")
        self.transport.before_send = lambda *args: False
        self.step()
        self.assertEqual(self.commands(), [])
        self.assertEqual(self.worker.pending_count, 1)
        self.assertIsNone(self.worker._reserved)
        self.step()
        self.assertEqual(self.commands(), [(1, 0, 42)])
        self.assertEqual(self.worker.pending_count, 0)

    def test_none_send_after_release_cannot_resurrect_reserved_note(self):
        self.worker.submit([(1, 0, 42)], tag="note")
        def release(*args):
            self.worker.submit([(2, 0, 0)], tag="release")
            return False
        self.transport.before_send = release
        self.step()
        self.step()
        self.assertEqual(self.commands(), [(2, 0, 0)])
        self.assertEqual(self.worker.pending_count, 0)

    def test_none_send_after_panic_cannot_resurrect_reserved_note(self):
        self.worker.submit([(1, 0, 42)], tag="note")
        def panic(*args):
            self.worker.panic()
            return False
        self.transport.before_send = panic
        self.step()
        self.step()
        self.assertEqual(self.commands(), [(10, 255, 0)])

    def test_none_send_after_coalescing_keeps_only_replacement(self):
        self.worker.submit([(4, 0, 1)], tag="old", coalesce_key="gain")
        def replace_gain(*args):
            self.worker.submit([(4, 0, 2)], tag="new", coalesce_key="gain")
            return False
        self.transport.before_send = replace_gain
        self.step()
        self.step()
        self.assertEqual(self.commands(), [(4, 0, 2)])

    def test_successful_reserved_note_stays_before_later_panic_on_wire(self):
        self.worker.submit([(1, 0, 42)], tag="note")
        self.transport.before_send = lambda *args: self.worker.panic()
        self.step()
        self.step()
        self.assertEqual(self.commands(), [(1, 0, 42), (10, 255, 0)])

    def test_background_inflight_does_not_block_foreground_and_old_tail_is_cancelled(self):
        self.worker.submit([(5, 31, 2), (4, 31, 1)], tag="preload", background=True)
        self.step()
        self.worker.submit([(4, 31, 2), (1, 31, 42)], tag="new-patch")
        self.worker.submit([(1, 0, 43)], tag="ready")
        self.step()
        self.assertEqual(self.commands()[:2], [(5, 31, 2), (1, 0, 43)])
        self.assertNotIn((4, 31, 1), self.commands())
        self.assertTrue(any(event["type"] == "patch_preload_cancelled" and event["voice"] == 31
                            for event in self.events()))
        self.step()
        self.step(.020)
        self.assertEqual(self.commands()[-1], (1, 31, 42))
        self.assertNotIn((4, 31, 1), self.commands())

    def test_snapshot_starts_only_after_all_sound_acks_and_captures_generation(self):
        self.worker.submit([(1, 31, 42)], tag="note")
        self.step()
        self.worker.request_latency_status()
        self.step()
        self.assertEqual(self.commands(), [(1, 31, 42)])
        self.step(.020)
        self.assertEqual(self.commands()[-1], (14, 255, 0))
        self.assertEqual(self.worker._async_snapshot.sound_generation, 1)

    def test_frontend_interrupts_each_diagnostic_and_late_ack_is_not_published(self):
        for opcode in (13, 14, 15):
            with self.subTest(opcode=opcode):
                self.transport.sent.clear()
                self.events()
                if opcode == 13:
                    self.worker._async_next_ping = self.clock.now
                elif opcode == 14:
                    self.worker.request_latency_status()
                else:
                    self.worker.request_voice_onset_status(31)
                self.step()
                self.assertEqual(self.commands()[0][0], opcode)
                self.worker.submit([(1, 0, 42)], tag="interrupt")
                self.step()
                self.assertEqual(self.commands()[1], (1, 0, 42))
                self.assertEqual(sum(command[0] == opcode for command in self.commands()), 1)
                self.step(.020)
                self.assertEqual(sum(command[0] == opcode for command in self.commands()), 1)
                events = self.events()
                self.assertFalse(any(event["type"] in ("voice_status", "latency_status", "voice_onset_status") for event in events))
                if opcode != 13:
                    expected = "latency_status_aborted" if opcode == 14 else "voice_onset_aborted"
                    self.assertEqual(sum(event["type"] == expected for event in events), 1)

    def test_snapshot_has_at_most_one_query_index_inflight(self):
        self.worker.request_voice_onset_status(31)
        for _ in range(8):
            self.step()
        self.assertEqual(self.commands(), [(15, 31, 0)])
        self.step(.010)
        self.assertEqual(self.commands(), [(15, 31, 0), (15, 31, 1)])
        self.assertEqual(self.transport.pending_count, 1)

    def test_window_stops_at_16_and_no_catchup_burst_after_long_pause(self):
        self.transport.ack_delay = .100
        self.worker.submit([(1, voice, 42) for voice in range(32)], tag="chord")
        for _ in range(20):
            self.step()
        self.assertEqual(len(self.commands()), 16)
        self.assertEqual(self.transport.max_pending_seen, 16)
        self.step(.200)
        self.assertEqual(len(self.commands()), 17)
        for _ in range(10):
            self.step(0)
        self.assertEqual(len(self.commands()), 17)

    def test_close_sends_paced_panic_with_inflight_notes_and_never_uses_command(self):
        self.worker.submit([(1, 0, 42), (1, 31, 43)], tag="chord")
        self.step()
        self.worker.close()
        self.worker._cleanup("closed")
        self.assertEqual(self.commands(), [(1, 0, 42), (10, 255, 0)])
        self.assertEqual(self.transport.sync_calls, [])
        self.assertTrue(self.transport.closed)
        self.assertFalse(self.worker._inflight)

    def test_shutdown_missing_ack_is_bounded_and_reports_uncertain_panic(self):
        self.worker.submit([(1, 0, 42)], tag="note")
        self.step()
        self.transport.hold_acks = True
        started = self.clock.now
        self.worker._cleanup("requested")
        self.assertLessEqual(self.clock.now - started, self.worker.timeout + .002)
        self.assertTrue(self.transport.closed)
        self.assertEqual(self.commands(), [(1, 0, 42), (10, 255, 0)])
        self.assertTrue(any(event["type"] == "log" and "PANIC" in event["message"] for event in self.events()))
        self.assertEqual(self.transport.sync_calls, [])


    def test_faulted_transport_uses_emergency_once_without_fabricating_ack(self):
        self.transport.faulted = True
        with patch.object(self.transport, "poll_acks") as poll, patch.object(
                self.transport, "emergency_close", create=True,
                return_value={"attempted": True, "acknowledged": False, "error": "lost ACK"}) as emergency:
            self.worker._cleanup("already faulted")
        emergency.assert_called_once_with()
        poll.assert_not_called()
        events = self.events()
        self.assertTrue(any(event["type"] == "log" and "unconfirmed" in event["message"] for event in events))
        self.assertFalse(any(event["type"] == "ack" for event in events))
        self.assertTrue(self.transport.closed)

    def test_old_ack_timeout_before_cleanup_panic_uses_one_emergency_attempt(self):
        def fail_poll():
            self.transport.faulted = True
            raise TimeoutError("old note ACK expired")
        with patch.object(self.transport, "poll_acks", side_effect=fail_poll), patch.object(
                self.transport, "emergency_close", create=True,
                return_value={"attempted": True, "acknowledged": True}) as emergency:
            self.worker._cleanup("requested")
        emergency.assert_called_once_with()
        self.assertEqual(self.commands(), [])
        self.assertFalse(any(event["type"] == "ack" for event in self.events()))
        self.assertTrue(self.transport.closed)

    def test_partial_cleanup_panic_does_not_trigger_a_second_emergency_panic(self):
        def partial_write(opcode, voice, value):
            self.transport.last_timing = TransactionTiming(17, opcode, self.clock.now)
            self.transport.faulted = True
            raise OSError("partial panic write")
        self.transport.before_send = partial_write
        with patch.object(self.transport, "emergency_close", create=True) as emergency:
            self.worker._cleanup("requested")
        emergency.assert_not_called()
        self.assertTrue(self.worker._cleanup_panic_sent)
        self.assertTrue(self.transport.closed)
        self.assertTrue(any(event["type"] == "log" and "partial panic write" in event["message"]
                            for event in self.events()))

    def test_cleanup_panic_ack_timeout_does_not_send_another_panic(self):
        original_poll = self.transport.poll_acks
        def timeout_after_panic():
            if any(command[0] == 10 for command in self.commands()):
                self.transport.faulted = True
                raise TimeoutError("cleanup panic ACK expired")
            return original_poll()
        with patch.object(self.transport, "poll_acks", side_effect=timeout_after_panic), patch.object(
                self.transport, "emergency_close", create=True) as emergency:
            self.worker._cleanup("requested")
        emergency.assert_not_called()
        self.assertEqual(self.commands(), [(10, 255, 0)])
        self.assertTrue(self.transport.closed)

    def test_rejected_cleanup_panic_is_reported_without_retry(self):
        self.transport.reject[10] = 3
        with patch.object(self.transport, "emergency_close", create=True) as emergency:
            self.worker._cleanup("requested")
        emergency.assert_not_called()
        self.assertEqual(self.commands(), [(10, 255, 0)])
        self.assertTrue(any(event["type"] == "log" and "PANIC" in event["message"] for event in self.events()))

    def test_cancel_while_final_diagnostic_ack_is_polled_prevents_publication(self):
        raw = struct.pack("<16I", 1, 0, 0, 50_000_000, *([0] * 9), 1024, 0, 0)
        snapshot = worker_module._Snapshot(14, 255, 64, "latency_poll", self.worker._latency_generation)
        snapshot.data.extend(raw[:63])
        self.worker._async_snapshot = snapshot
        self.step()
        self.assertEqual(self.commands(), [(14, 255, 63)])
        self.transport.during_poll = self.worker.cancel_latency_status
        self.step(.020)
        events = self.events()
        self.assertTrue(any(event["type"] == "latency_status_aborted" for event in events))
        self.assertFalse(any(event["type"] == "latency_status" for event in events))

    def test_background_coalescing_does_not_restore_replaced_none_send_reservation(self):
        self.worker.submit([(4, 31, 1)], tag="old-preload", coalesce_key="preload", background=True)
        def replace_preload(*args):
            self.worker.submit([(4, 31, 2)], tag="new-preload", coalesce_key="preload", background=True)
            return False
        self.transport.before_send = replace_preload
        self.step()
        self.step()
        self.assertEqual(self.commands(), [(4, 31, 2)])

    def test_none_send_restore_keeps_unrelated_new_release_ahead_of_ordinary_work(self):
        self.worker.submit([(1, 0, 42)], tag="note")
        def release_other_voice(*args):
            self.worker.submit([(2, 31, 0)], tag="release")
            return False
        self.transport.before_send = release_other_voice
        self.step()
        self.step()
        self.assertEqual(self.commands(), [(2, 31, 0)])
        self.step()
        self.assertEqual(self.commands(), [(2, 31, 0), (1, 0, 42)])

if __name__ == "__main__":
    unittest.main()