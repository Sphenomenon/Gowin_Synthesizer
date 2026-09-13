"""Global output controls: wire conversions, optional firmware support, and queues."""
from pathlib import Path
import contextlib
import io
import queue
import sys
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from instrument_backend import (Ack, CommandRejected, ControlWorker, SimulatedTransport,
                                UNITY, balance_word, gain_word, encode_packet)
from instrument_backend import worker as worker_module
import instrument_cli as cli
from test_async_worker_review import DelayedTransport


class OutputProtocolTests(unittest.TestCase):
    def test_balance_conversion_matches_endpoints_and_both_half_ranges(self):
        self.assertEqual([balance_word(value) for value in (-1, -.5, 0, .5, 1)],
                         [0, 0x20000000, 0x40000000, 0x60000000, 0x80000000])
        for value in (-1.01, 1.01, float("inf"), float("nan")):
            with self.assertRaises(ValueError): balance_word(value)

    def test_cli_commands_encode_single_global_request_without_serial_access(self):
        for action, arg, opcode, value in (("master-volume", "0.5", 16, 0x40000000),
                                            ("master-volume", "0", 16, 0),
                                            ("lr-balance", "-1", 17, 0),
                                            ("lr-balance", "0", 17, 0x40000000),
                                            ("lr-balance", "1", 17, 0x80000000)):
            output = io.StringIO()
            with patch.object(sys, "argv", ["cli", "--dry-run", action, arg]), \
                    patch.object(cli, "SerialTransport") as serial, contextlib.redirect_stdout(output):
                cli.main()
            serial.assert_not_called()
            self.assertEqual(output.getvalue().strip(), encode_packet(0, opcode, 255, value).hex(" "))

    def test_cli_rejects_invalid_output_values_before_opening_port(self):
        for action, arg in (("master-volume", "1.01"), ("master-volume", "nan"),
                            ("lr-balance", "-1.01"), ("lr-balance", "inf")):
            with patch.object(sys, "argv", ["cli", "--port", "FAKE", action, arg]), \
                    patch.object(cli, "SerialTransport") as serial, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit): cli.main()
            serial.assert_not_called()

    def test_offline_controls_validate_global_scope_and_persist_across_panic(self):
        transport = SimulatedTransport()
        self.assertEqual((transport.master_volume, transport.lr_balance), (UNITY, UNITY // 2))
        transport.command(1, 31, 5)
        for opcode, attribute in ((16, "master_volume"), (17, "lr_balance")):
            for value in (0, UNITY // 2, UNITY):
                ack = transport.command(opcode, 255, value)
                self.assertEqual(getattr(transport, attribute), value)
                self.assertTrue(ack.simulated)
                self.assertEqual(transport.active_mask, 1 << 31)
            for voice, value, status in ((0, 0, 2), (255, UNITY + 1, 3), (255, -1, 3)):
                with self.assertRaises(CommandRejected) as caught: transport.command(opcode, voice, value)
                self.assertEqual(caught.exception.ack.status, status)
                self.assertEqual(getattr(transport, attribute), UNITY)
        transport.command(10)
        self.assertEqual((transport.master_volume, transport.lr_balance), (UNITY, UNITY))
        self.assertEqual(transport.active_mask, 0)


class OutputWorkerTests(unittest.TestCase):
    def drain(self, worker):
        result = []
        while not worker.events.empty(): result.append(worker.events.get_nowait())
        return result

    def wait_for(self, worker, kind):
        deadline = time.monotonic() + 2
        events = []
        while time.monotonic() < deadline:
            event = worker.events.get(timeout=max(.001, deadline - time.monotonic()))
            events.append(event)
            if event["type"] == kind: return event, events
        self.fail(f"no {kind} event: {events}")

    def close_worker(self, worker):
        worker.close()
        worker._thread.join(2)
        self.assertFalse(worker.is_alive)

    def test_connect_synchronizes_desired_output_after_panic_and_before_connected(self):
        class RecordingTransport(SimulatedTransport):
            def __init__(self):
                super().__init__(); self.calls = []
            def command(self, *command):
                self.calls.append(command)
                return super().command(*command)
        transport = RecordingTransport()
        worker = ControlWorker(ping_interval=60, transport_factory=lambda **kw: transport)
        self.addCleanup(self.close_worker, worker)
        self.assertTrue(worker.connect("FAKE", output_controls=(0x60000000, 0x20000000)))
        connected, events = self.wait_for(worker, "connected")
        self.assertEqual(transport.calls, [(0, 255, 0), (10, 255, 0),
                         *[(13, 255, index) for index in range(4)],
                         (16, 255, 0x60000000), (17, 255, 0x20000000)])
        self.assertEqual(connected["output_controls_supported"], {16: True, 17: True})
        self.assertEqual(connected["output_values"], {16: 0x60000000, 17: 0x20000000})
        self.assertEqual(events[-2]["opcode"], 17)

    def test_old_firmware_keeps_connection_and_notes_usable(self):
        class OldTransport(SimulatedTransport):
            def command(self, opcode, voice=255, value=0):
                if opcode in (16, 17):
                    raise CommandRejected(Ack(0, opcode, 1, 0, 0, "old", simulated=True))
                return super().command(opcode, voice, value)
        transport = OldTransport()
        worker = ControlWorker(ping_interval=60, transport_factory=lambda **kw: transport)
        self.addCleanup(self.close_worker, worker)
        worker.connect("FAKE", output_controls=(UNITY, UNITY // 2))
        connected, events = self.wait_for(worker, "connected")
        self.assertEqual(connected["output_controls_supported"], {16: False, 17: False})
        self.assertEqual(connected["output_values"], {})
        self.assertEqual(sum(event["type"] == "output_control_unsupported" for event in events), 2)
        self.assertFalse(worker.submit([(16, 255, 0)]))
        self.assertTrue(worker.submit([(1, 31, 1)], tag="note"))
        self.wait_for(worker, "ack")
        self.assertEqual(transport.active_mask, 1 << 31)
        self.assertEqual(worker._state, "connected")

    def test_sync_optional_rejection_after_connect_does_not_close_session(self):
        class LateOldTransport(SimulatedTransport):
            def command(self, opcode, voice=255, value=0):
                if opcode == 17:
                    raise CommandRejected(Ack(0, opcode, 1, 0, 0, "old", simulated=True))
                return super().command(opcode, voice, value)
        transport = LateOldTransport()
        worker = ControlWorker(ping_interval=60, transport_factory=lambda **kw: transport)
        self.addCleanup(self.close_worker, worker)
        worker.connect("FAKE")
        self.wait_for(worker, "connected")
        worker.submit([(17, 255, 0), (1, 8, 5)], tag="late")
        self.wait_for(worker, "output_control_unsupported")
        self.wait_for(worker, "ack")
        self.assertEqual(transport.active_mask, 1 << 8)
        self.assertEqual(worker._state, "connected")

    def test_invalid_connect_values_never_open_transport(self):
        with patch.object(worker_module.threading.Thread, "start"):
            worker = ControlWorker()
        for value in ((0,), (0, UNITY + 1), (0, True), "bad"):
            self.assertFalse(worker.connect("FAKE", output_controls=value))
        self.assertEqual(worker._state, "disconnected")


class AsyncOutputTests(unittest.TestCase):
    def setUp(self):
        self.clock = SimpleNamespace(now=100.0)
        self.addCleanup(patch.stopall)
        patch.object(worker_module, "time", SimpleNamespace(perf_counter=lambda: self.clock.now)).start()
        with patch.object(worker_module.threading.Thread, "start"):
            self.worker = ControlWorker(ping_interval=60)
        self.transport = DelayedTransport(self.clock)
        self.worker._transport = self.transport
        self.worker._state = "connected"
        self.worker.connection_id = 7
        self.worker._async_next_ping = 160

    def step(self, count=1):
        for _ in range(count):
            self.clock.now += .002
            self.worker._async_step()

    def test_output_coalescing_keeps_independent_final_values_and_release_priority(self):
        for value in (UNITY, UNITY // 2, 0):
            self.worker.submit([(16, 255, value)], coalesce_key="output:16")
        self.worker.submit([(17, 255, UNITY)], coalesce_key="output:17")
        self.worker.submit([(2, 31, 0)])
        self.assertEqual(self.worker.pending_count, 3)
        self.step(20)
        self.assertEqual([command for command, timing in self.transport.sent],
                         [(2, 31, 0), (16, 255, 0), (17, 255, UNITY)])
        self.assertFalse(self.transport.sync_calls)
        self.assertEqual(self.worker._sound_generation, 3)

    def test_prepared_note_cannot_overtake_global_mute_but_does_not_wait_for_its_ack(self):
        self.worker.submit([(16, 255, 0)])
        self.worker.submit([(1, 31, 10)])
        self.step(2)
        self.assertEqual([command for command, timing in self.transport.sent],
                         [(16, 255, 0), (1, 31, 10)])
        self.assertEqual(len(self.transport.completed), 0)

    def test_coalesced_global_value_stays_before_note_queued_behind_original(self):
        self.worker.submit([(16, 255, UNITY // 8)], coalesce_key="output:16")
        self.worker.submit([(1, 31, 10)])
        self.worker.submit([(16, 255, 0)], coalesce_key="output:16")
        self.step(2)
        self.assertEqual([command for command, timing in self.transport.sent],
                         [(16, 255, 0), (1, 31, 10)])
        self.assertFalse(self.transport.completed)

    def test_independent_balance_volume_replacements_keep_positions_and_release_priority(self):
        self.worker.submit([(1, 2, 5)])
        self.worker.submit([(16, 255, UNITY // 8)], coalesce_key="output:16")
        self.worker.submit([(1, 31, 5)])
        self.worker.submit([(17, 255, UNITY)], coalesce_key="output:17")
        self.worker.submit([(1, 30, 5)])
        self.worker.submit([(17, 255, 0)], coalesce_key="output:17")
        self.worker.submit([(16, 255, 0)], coalesce_key="output:16")
        self.worker.submit([(2, 8, 0)])
        self.step(6)
        self.assertEqual([command for command, timing in self.transport.sent],
                         [(2, 8, 0), (1, 2, 5), (16, 255, 0), (1, 31, 5),
                          (17, 255, 0), (1, 30, 5)])

    def test_replaced_reserved_global_still_precedes_note_when_old_send_returns_none(self):
        self.worker.submit([(16, 255, UNITY // 8)], coalesce_key="output:16")
        def during_send(*command):
            self.worker.submit([(1, 31, 5)])
            self.worker.submit([(16, 255, 0)], coalesce_key="output:16")
            return False
        self.transport.before_send = during_send
        self.step()
        self.assertFalse(self.transport.sent)
        self.step(2)
        self.assertEqual([command for command, timing in self.transport.sent],
                         [(16, 255, 0), (1, 31, 5)])

    def test_replaced_reserved_global_that_did_send_is_not_replayed(self):
        self.worker.submit([(17, 255, UNITY)], coalesce_key="output:17")
        def during_send(*command):
            self.worker.submit([(1, 31, 5)])
            self.worker.submit([(17, 255, 0)], coalesce_key="output:17")
            return True
        self.transport.before_send = during_send
        self.step(3)
        self.assertEqual([command for command, timing in self.transport.sent],
                         [(17, 255, UNITY), (17, 255, 0), (1, 31, 5)])
        self.assertFalse(self.transport.completed)

    def test_inflight_control_retains_wire_order_without_replay_or_new_ack_wait(self):
        self.worker.submit([(16, 255, UNITY // 8)], coalesce_key="output:16")
        self.step()
        self.worker.submit([(1, 31, 5)])
        self.worker.submit([(16, 255, 0)], coalesce_key="output:16")
        self.step(2)
        self.assertEqual([command for command, timing in self.transport.sent],
                         [(16, 255, UNITY // 8), (1, 31, 5), (16, 255, 0)])
        self.assertFalse(self.transport.completed)

    def test_async_unknown_output_cancels_queued_values_without_losing_notes(self):
        self.transport.reject[17] = 1
        self.worker.submit([(17, 255, 0)])
        self.step()
        self.worker.submit([(17, 255, UNITY)])
        self.worker.submit([(1, 31, 5)])
        self.step(20)
        self.assertFalse(self.worker.output_controls_supported[17])
        self.assertIn((1, 31, 5), [command for command, timing in self.transport.sent])
        self.assertEqual(self.worker._state, "connected")
        self.assertFalse(self.worker.submit([(17, 255, UNITY // 2)]))
        events = []
        while not self.worker.events.empty(): events.append(self.worker.events.get_nowait())
        self.assertEqual(sum(event["type"] == "output_control_unsupported" for event in events), 1)
        self.assertFalse(any(event["type"] == "disconnected" for event in events))

    def test_global_edit_interrupts_diagnostics_without_changing_onset_cache_contract(self):
        self.worker.request_latency_status()
        self.step()
        self.assertIsNotNone(self.worker._async_snapshot)
        self.worker.submit([(16, 255, 0)], coalesce_key="output:16")
        self.step(20)
        self.assertIsNone(self.worker._async_snapshot)
        self.assertEqual(self.worker._sound_generation, 1)
        events = []
        while not self.worker.events.empty(): events.append(self.worker.events.get_nowait())
        self.assertTrue(any(event["type"] == "latency_status_aborted" for event in events))
        self.assertFalse(any(event["type"] == "latency_status" for event in events))


if __name__ == "__main__":
    unittest.main()
