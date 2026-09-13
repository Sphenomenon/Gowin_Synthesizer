"""Transport selection and sub-millisecond timing without opening hardware."""
from pathlib import Path
from types import SimpleNamespace
import sys
import struct
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from instrument_backend.protocol import SYNC, crc16
from instrument_backend.transport import SerialTransport, _ftdi_identity


class BufferedSerial:
    def __init__(self, *args, **kwargs):
        self.options = kwargs
        self.buffer = bytearray()
        self.read_sizes = []
        self.closed = False

    def reset_input_buffer(self):
        self.buffer.clear()

    @property
    def in_waiting(self):
        return len(self.buffer)

    def write(self, packet):
        payload = bytes((packet[2], 0, 0, packet[3]))
        self.buffer.extend(SYNC + payload + crc16(payload).to_bytes(2, "little"))
        return len(packet)

    def read(self, count):
        self.read_sizes.append(count)
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data

    def close(self):
        self.closed = True


class SerialLowLatencyTests(unittest.TestCase):
    def test_qpc_measures_real_sub_tick_duration_and_drains_ack(self):
        clock = SimpleNamespace(perf_counter=unittest.mock.Mock(side_effect=[100.0, 100.00005, 100.0001, 100.002125]))
        with patch("instrument_backend.transport.time", clock):
            transport = SerialTransport("FAKE", serial_factory=BufferedSerial)
            ack = transport.command(0)
        self.assertAlmostEqual(ack.rtt_ms, 2.125, places=6)
        self.assertAlmostEqual(transport.last_timing.ack_received, 100.002125)
        self.assertEqual(transport.serial.read_sizes, [8])
        transport.close()

    def test_unsupported_or_jtag_channel_never_selects_d2xx(self):
        def port(name, number, vid=0x0403, pid=0x6010):
            return SimpleNamespace(device=name, serial_number=number, vid=vid, pid=pid,
                                   interface=None, description="USB Serial Port", hwid="")
        ports = [port("COM25", "SERIALA"), port("COM26", "SERIALB"),
                 port("COM7", "OTHERB", pid=0x6001), port("COM8", None)]
        with patch("instrument_backend.transport.os", SimpleNamespace(name="nt")), \
                patch("serial.tools.list_ports.comports", return_value=ports):
            self.assertIsNone(_ftdi_identity("COM25"))
            self.assertEqual(_ftdi_identity("com26"), "SERIALB")
            self.assertIsNone(_ftdi_identity("COM7"))
            self.assertIsNone(_ftdi_identity("COM8"))
            self.assertIsNone(_ftdi_identity("COM99"))

    def test_factory_injection_never_probes_hardware(self):
        with patch("instrument_backend.transport._ftdi_identity", side_effect=AssertionError("hardware probe")):
            transport = SerialTransport("FAKE", serial_factory=BufferedSerial)
            self.assertEqual(transport.command(0).opcode, 0)
            transport.close()

    def test_auto_keeps_os_driver_without_configuring_bridge(self):
        with patch("instrument_backend.transport._ftdi_identity", side_effect=AssertionError("unexpected D2XX selection")), \
                patch("serial.Serial", BufferedSerial):
            transport = SerialTransport("COM26")
            self.assertNotIn("serial_number", transport.serial.options)
            self.assertEqual(transport.command(0).status, 0)
            transport.close()

    def test_explicit_ftdi_uses_detected_exact_identity(self):
        with patch("instrument_backend.transport._ftdi_identity", return_value="SERIALB"), \
                patch("instrument_backend.ftdi_serial.FtdiSerial", BufferedSerial):
            transport = SerialTransport("COM26", backend="ftdi")
            self.assertEqual(transport.serial.options["serial_number"], "SERIALB")
            self.assertEqual(transport.command(0).status, 0)
            transport.close()

    def test_explicit_pyserial_bypasses_d2xx_and_explicit_ftdi_rejects_unknown_port(self):
        with patch("instrument_backend.transport._ftdi_identity", return_value=None) as identity, \
                patch("serial.Serial", BufferedSerial):
            transport = SerialTransport("COM26", backend="pyserial")
            identity.assert_not_called()
            transport.close()
            with self.assertRaises(ValueError):
                SerialTransport("COM25", backend="ftdi")
        with self.assertRaises(ValueError):
            SerialTransport("COM26", backend="invalid")


def ack_frame(sequence, opcode=0, status=0, active=0):
    payload = bytes((sequence, status, active, opcode))
    return SYNC + payload + crc16(payload).to_bytes(2, "little")


class AsyncSerial(BufferedSerial):
    """Explicitly delivered ACK bytes; an empty-queue read is a test failure."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.packets = []
        self.close_count = 0
        self.write_error = self.read_error = self.queue_error = None
        self.partial_write = None
        self.close_error = None
        self.on_write = None
        self.auto_ack = False

    @property
    def in_waiting(self):
        if self.queue_error:
            raise self.queue_error
        return len(self.buffer)

    def write(self, packet):
        assert len(packet) == 12, "one write must contain exactly one protocol packet"
        self.packets.append(bytes(packet))
        if self.write_error:
            raise self.write_error
        if self.on_write:
            self.on_write()
        if self.auto_ack:
            self.buffer.extend(ack_frame(packet[2], packet[3]))
        return len(packet) if self.partial_write is None else self.partial_write

    def read(self, count):
        if self.read_error:
            raise self.read_error
        assert 0 < count <= len(self.buffer), "poll_acks must never perform a waiting read"
        return super().read(count)

    def close(self):
        super().close()
        self.close_count += 1
        if self.close_error:
            raise self.close_error


class AsyncTransportTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.sleeps = []
        self.clock = patch("instrument_backend.transport.time",
                           SimpleNamespace(perf_counter=lambda: self.now, sleep=self.sleep))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration

    def transport(self, **kwargs):
        transport = SerialTransport("FAKE", serial_factory=AsyncSerial, **kwargs)
        self.addCleanup(transport.close)
        return transport

    def send(self, transport, opcode=0, voice=255, value=0):
        self.now = max(self.now, transport.send_ready_at)
        timing = transport.send_async(opcode, voice, value)
        self.assertIsNotNone(timing)
        return timing

    def test_pacing_window_and_none_do_not_consume_sequence_or_burst_after_idle(self):
        transport = self.transport()
        self.assertTrue(transport.supports_async)
        first = self.send(transport)
        self.assertEqual((first.sequence, transport.pending_count), (0, 1))
        self.assertAlmostEqual(transport.send_interval, 0.0015)
        for _ in range(5):
            self.assertIsNone(transport.send_async(0))
        self.assertEqual(transport.sequence, 1)
        self.now = first.write_started + .050
        self.send(transport)
        self.assertIsNone(transport.send_async(0))
        for _ in range(14):
            self.send(transport)
        self.assertEqual(transport.pending_count, 16)
        self.now = transport.send_ready_at
        self.assertIsNone(transport.send_async(0))
        self.assertEqual((transport.sequence, len(transport.serial.packets)), (16, 16))
        transport.serial.buffer.extend(ack_frame(8))
        self.assertEqual(transport.poll_acks()[0][0].sequence, 8)
        self.assertEqual(self.send(transport).sequence, 16)
        self.assertEqual(transport.pending_count, 16)

    def test_interval_accounts_for_wire_time_and_waits_after_write_returns(self):
        transport = self.transport(baud=9600)
        self.assertAlmostEqual(transport.send_interval, 120 / 9600 + .0004)
        def stalled_write():
            self.now += .010
        transport.serial.on_write = stalled_write
        timing = self.send(transport)
        self.assertEqual(timing.write_started, 100.0)
        self.assertAlmostEqual(transport.send_ready_at, 100.010 + 120 / 9600 + .0004)
        self.assertIsNone(transport.send_async(0))

    def test_empty_poll_never_reads_or_changes_pending_timing(self):
        transport = self.transport()
        timing = self.send(transport)
        self.now += .003
        self.assertEqual(transport.poll_acks(), [])
        self.assertEqual(transport.serial.read_sizes, [])
        self.assertEqual(transport.pending_count, 1)
        self.assertEqual(transport.last_timing, timing)

    def test_fragment_noise_crc_failure_wrong_identity_and_duplicates(self):
        transport = self.transport()
        first = self.send(transport, 1, 31, 42)
        second = self.send(transport, 2, 31)
        broken = bytearray(ack_frame(first.sequence, first.opcode))
        broken[-1] ^= 0x80
        packet = ack_frame(first.sequence, first.opcode, active=0x80)
        transport.serial.buffer.extend(b"noise" + broken
                                       + ack_frame(first.sequence, 3)
                                       + ack_frame(91, first.opcode) + packet[:5])
        self.assertEqual(transport.poll_acks(), [])
        self.assertEqual(transport.pending_count, 2)
        self.now += .004
        transport.serial.buffer.extend(packet[5:] + packet + ack_frame(second.sequence, second.opcode))
        completed = transport.poll_acks()
        self.assertEqual([(ack.sequence, ack.opcode) for ack, _ in completed], [(0, 1), (1, 2)])
        self.assertEqual(completed[0][0].active_mask, 0x80)
        self.assertEqual(transport.pending_count, 0)
        self.assertEqual(transport.poll_acks(), [])

    def test_all_batched_out_of_order_acks_keep_own_times_including_rejection(self):
        transport = self.transport()
        submitted = [self.send(transport, op, 31, 42 if op == 1 else 0) for op in (1, 2, 4)]
        self.now += .010
        received = self.now
        transport.serial.buffer.extend(ack_frame(2, 4) + ack_frame(0, 1, status=3) + ack_frame(1, 2))
        completed = transport.poll_acks()
        self.assertEqual([(ack.sequence, ack.status) for ack, _ in completed], [(2, 0), (0, 3), (1, 0)])
        for ack, timing in completed:
            self.assertEqual(timing.write_started, submitted[ack.sequence].write_started)
            self.assertEqual(timing.ack_received, received)
            self.assertAlmostEqual(ack.rtt_ms, (received - timing.write_started) * 1000)
        self.assertEqual(transport.pending_count, 0)
        self.assertFalse(transport.serial.closed)
        self.assertIsNone(transport.next_deadline)

    def test_deadline_tracks_oldest_remaining_transaction_not_reply_order(self):
        transport = self.transport()
        submitted = [self.send(transport) for _ in range(3)]
        self.assertEqual(transport.next_deadline, submitted[0].write_started + transport.timeout)
        transport.serial.buffer.extend(ack_frame(2) + ack_frame(0))
        self.assertEqual(len(transport.poll_acks()), 2)
        self.assertEqual(transport.next_deadline, submitted[1].write_started + transport.timeout)

    def test_modulo_sequence_wrap_is_shared_with_blocking_commands(self):
        transport = self.transport()
        transport.sequence = 254
        submitted = [self.send(transport) for _ in range(3)]
        self.assertEqual([item.sequence for item in submitted], [254, 255, 0])
        transport.serial.buffer.extend(b"".join(ack_frame(item.sequence) for item in submitted))
        self.assertEqual(len(transport.poll_acks()), 3)
        transport.serial.auto_ack = True
        self.assertEqual(transport.command(0).sequence, 1)
        self.assertEqual(self.send(transport).sequence, 2)

    def test_wrap_never_reuses_sequence_still_owned_by_an_older_pending_packet(self):
        transport = self.transport(timeout=2.0)
        self.send(transport)
        for sequence in range(1, 256):
            self.assertEqual(self.send(transport).sequence, sequence)
            transport.serial.buffer.extend(ack_frame(sequence))
            self.assertEqual(len(transport.poll_acks()), 1)
        self.now = transport.send_ready_at
        self.assertEqual((transport.sequence, transport.pending_count), (0, 1))
        self.assertIsNone(transport.send_async(1, 31, 42))
        self.assertEqual(len(transport.serial.packets), 256)
        transport.serial.buffer.extend(ack_frame(0))
        self.assertEqual(transport.poll_acks()[0][0].sequence, 0)
        self.assertEqual(self.send(transport, 1, 31, 42).sequence, 0)

    def test_blocking_command_cannot_consume_pending_async_response(self):
        transport = self.transport()
        self.send(transport)
        transport.serial.buffer.extend(ack_frame(0))
        with self.assertRaisesRegex(RuntimeError, "asynchronous ACKs are pending"):
            transport.command(0)
        self.assertEqual((transport.sequence, len(transport.serial.packets)), (1, 1))
        self.assertEqual(transport.serial.read_sizes, [])
        self.assertEqual(transport.poll_acks()[0][0].sequence, 0)

    def test_partial_write_invalidates_all_pending_without_replay(self):
        transport = self.transport()
        self.send(transport)
        transport.serial.partial_write = 5
        self.now = transport.send_ready_at
        with self.assertRaisesRegex(OSError, "incomplete serial write"):
            transport.send_async(1, 31, 42)
        self.assertEqual(transport.pending_count, 0)
        self.assertFalse(transport.serial.closed)
        self.assertTrue(transport.faulted)
        self.assertEqual(len(transport.serial.packets), 2)
        for operation in (lambda: transport.send_async(1, 31, 42),
                          transport.poll_acks, lambda: transport.command(0)):
            with self.assertRaisesRegex(OSError, "faulted"):
                operation()
        self.assertEqual(len(transport.serial.packets), 2)
        transport.close()
        self.assertEqual(transport.serial.close_count, 1)

    def test_io_errors_isolate_and_clear_session(self):
        for failed in ("write", "read", "queue"):
            with self.subTest(operation=failed):
                transport = self.transport()
                self.send(transport)
                setattr(transport.serial, failed + "_error", OSError("injected " + failed))
                if failed == "write":
                    self.now = transport.send_ready_at
                    operation = lambda: transport.send_async(0)
                else:
                    transport.serial.buffer.extend(ack_frame(0))
                    operation = transport.poll_acks
                with self.assertRaisesRegex(OSError, "injected " + failed):
                    operation()
                self.assertEqual(transport.pending_count, 0)
                self.assertFalse(transport.serial.closed)
                self.assertTrue(transport.faulted)

    def test_timeout_isolates_even_if_late_ack_is_now_queued_or_window_is_full(self):
        for operation in ("poll", "send"):
            with self.subTest(operation=operation):
                transport = self.transport(timeout=.1)
                first = self.send(transport)
                if operation == "send":
                    for _ in range(15):
                        self.send(transport)
                self.now = first.write_started + transport.timeout
                transport.serial.buffer.extend(ack_frame(first.sequence))
                with self.assertRaisesRegex(TimeoutError, "sequence 0.*without replay"):
                    transport.poll_acks() if operation == "poll" else transport.send_async(0)
                self.assertFalse(transport.serial.closed)
                self.assertTrue(transport.faulted)
                self.assertEqual(transport.pending_count, 0)
                self.assertEqual(transport.serial.read_sizes, [])

    def test_close_clears_pending_and_partial_parser_and_is_idempotent(self):
        transport = self.transport()
        self.send(transport)
        transport.serial.buffer.extend(ack_frame(0)[:4])
        self.assertEqual(transport.poll_acks(), [])
        transport.close()
        transport.close()
        self.assertEqual(transport.pending_count, 0)
        self.assertIsNone(transport.next_deadline)
        self.assertEqual(transport.serial.close_count, 1)
        self.assertEqual(transport.parser.feed(ack_frame(0)[4:]), [])

    def test_emergency_after_timeout_ignores_old_ack_and_sends_only_one_new_panic(self):
        transport = self.transport(timeout=.01)
        first = self.send(transport, 1, 31, 42)
        self.now = first.write_started + transport.timeout
        transport.serial.buffer.extend(ack_frame(first.sequence, first.opcode))
        with self.assertRaises(TimeoutError):
            transport.poll_acks()
        transport.serial.auto_ack = True
        result = transport.emergency_close()
        self.assertEqual(result, {"attempted": True, "acknowledged": True, "error": None})
        self.assertEqual([packet[3] for packet in transport.serial.packets], [1, 10])
        self.assertEqual([packet[2] for packet in transport.serial.packets], [0, 1])
        self.assertEqual(transport.serial.packets[-1][4], 255)
        self.assertEqual(transport.serial.close_count, 1)
        self.assertEqual(transport.pending_count, 0)
        self.assertTrue(transport.faulted)
        self.assertFalse(transport.emergency_close()["attempted"])
        transport.close()
        self.assertEqual(len(transport.serial.packets), 2)
        self.assertEqual(transport.serial.close_count, 1)
        with self.assertRaisesRegex(OSError, "closed"):
            transport.send_async(1, 31, 42)

    def test_emergency_partial_write_sequence_is_reserved_and_pacing_is_retained(self):
        transport = self.transport()
        transport.sequence = 255
        self.send(transport, 1, 31, 42)
        transport.serial.partial_write = 5
        self.now = transport.send_ready_at
        with self.assertRaises(OSError):
            transport.send_async(1, 30, 43)
        failed_at = self.now
        self.assertEqual(transport.sequence, 0)
        transport.serial.partial_write = None
        transport.serial.auto_ack = True
        result = transport.emergency_close()
        self.assertTrue(result["acknowledged"])
        self.assertEqual([packet[2] for packet in transport.serial.packets], [255, 0, 1])
        self.assertEqual([packet[3] for packet in transport.serial.packets], [1, 1, 10])
        self.assertAlmostEqual(self.now - failed_at, transport.send_interval)
        self.assertAlmostEqual(sum(self.sleeps), transport.send_interval)

    def test_emergency_skips_wrapped_inflight_sequence_even_for_old_panic(self):
        transport = self.transport()
        self.send(transport, 10)
        transport.sequence = 255
        self.send(transport, 1, 31, 42)
        self.assertEqual(transport.sequence, 0)
        transport.serial.queue_error = OSError("queue unavailable")
        with self.assertRaises(OSError):
            transport.poll_acks()
        transport.serial.queue_error = None
        transport.serial.buffer.extend(ack_frame(0, 10))
        transport.serial.auto_ack = True
        self.assertTrue(transport.emergency_close()["acknowledged"])
        self.assertEqual(transport.serial.packets[-1][2:4], bytes((1, 10)))

    def test_old_or_wrong_panic_ack_does_not_confirm_emergency_and_wait_is_bounded(self):
        transport = self.transport(timeout=.005)
        self.send(transport, 1, 31, 42)
        # Correct old NOTE_ON and old PANIC identities cannot confirm sequence 1.
        transport.serial.buffer.extend(ack_frame(0, 1) + ack_frame(0, 10) + ack_frame(1, 1))
        ready = transport.send_ready_at
        result = transport.emergency_close()
        self.assertTrue(result["attempted"])
        self.assertFalse(result["acknowledged"])
        self.assertIn("timeout", result["error"])
        self.assertAlmostEqual(self.now, ready + transport.timeout)
        self.assertEqual(transport.serial.close_count, 1)
        self.assertEqual(len(transport.serial.packets), 2)

    def test_emergency_io_failure_partial_write_and_rejection_never_retry(self):
        for failure in ("write", "partial", "queue", "read", "rejected"):
            with self.subTest(failure=failure):
                transport = self.transport(timeout=.005)
                self.send(transport, 1, 31, 42)
                if failure == "partial":
                    transport.serial.partial_write = 4
                elif failure == "rejected":
                    transport.serial.buffer.extend(ack_frame(1, 10, status=3))
                else:
                    setattr(transport.serial, failure + "_error", OSError("injected " + failure))
                    if failure == "read":
                        transport.serial.buffer.extend(ack_frame(1, 10))
                result = transport.emergency_close()
                self.assertTrue(result["attempted"])
                self.assertFalse(result["acknowledged"])
                self.assertIsInstance(result["error"], str)
                self.assertEqual([packet[3] for packet in transport.serial.packets], [1, 10])
                self.assertEqual(transport.serial.close_count, 1)
                self.assertFalse(transport.emergency_close()["attempted"])
                self.assertEqual(len(transport.serial.packets), 2)

    def test_emergency_close_failure_is_reported_with_original_failure_and_not_retried(self):
        for acknowledged in (False, True):
            with self.subTest(acknowledged=acknowledged):
                transport = self.transport(timeout=.002)
                transport.serial.auto_ack = acknowledged
                transport.serial.close_error = OSError("close failed")
                result = transport.emergency_close()
                self.assertEqual(result["acknowledged"], acknowledged)
                self.assertIn("Serial close failed: close failed", result["error"])
                if not acknowledged:
                    self.assertIn("timeout", result["error"])
                transport.close()
                self.assertFalse(transport.emergency_close()["attempted"])
                self.assertEqual(transport.serial.close_count, 1)

    def test_ping_only_close_after_fault_is_silent_even_when_close_fails(self):
        transport = self.transport(timeout=.002)
        first = self.send(transport)
        self.now = first.write_started + transport.timeout
        with self.assertRaises(TimeoutError):
            transport.poll_acks()
        transport.serial.close_error = OSError("close failed")
        with self.assertRaisesRegex(OSError, "close failed"):
            transport.close()
        transport.close()
        self.assertFalse(transport.emergency_close()["attempted"])
        self.assertEqual([packet[3] for packet in transport.serial.packets], [0])
        self.assertEqual(transport.serial.close_count, 1)

    def test_blocking_command_fault_retains_handle_and_failed_sequence_for_cleanup(self):
        for failure in ("write", "partial", "read", "timeout"):
            with self.subTest(failure=failure):
                transport = self.transport(timeout=.003)
                if failure == "partial":
                    transport.serial.partial_write = 5
                elif failure == "timeout":
                    def advance_then_return_empty(count):
                        self.now += .001
                        return b""
                    transport.serial.read = advance_then_return_empty
                else:
                    setattr(transport.serial, failure + "_error", OSError("injected " + failure))
                with self.assertRaises((OSError, TimeoutError)):
                    transport.command(1, 31, 42)
                self.assertTrue(transport.faulted)
                self.assertFalse(transport.serial.closed)
                transport.serial.write_error = None
                transport.serial.read_error = None
                transport.serial.partial_write = None
                transport.serial.read = lambda count: BufferedSerial.read(transport.serial, count)
                transport.serial.auto_ack = True
                result = transport.emergency_close()
                self.assertTrue(result["acknowledged"], result)
                self.assertEqual([packet[2:4] for packet in transport.serial.packets],
                                 [bytes((0, 1)), bytes((1, 10))])

    def test_blocking_write_completion_preserves_emergency_interval_on_read_error(self):
        transport = self.transport()
        def slow_write():
            self.now += .010
        transport.serial.on_write = slow_write
        transport.serial.read_error = OSError("read failed")
        with self.assertRaises(OSError):
            transport.command(1, 31, 42)
        failed_at = self.now
        transport.serial.on_write = None
        transport.serial.read_error = None
        transport.serial.auto_ack = True
        self.assertTrue(transport.emergency_close()["acknowledged"])
        self.assertAlmostEqual(self.now - failed_at, transport.send_interval)

    def test_fault_discards_partial_parser_and_late_emergency_ack_is_not_success(self):
        transport = self.transport(timeout=.004)
        self.send(transport, 1, 31, 42)
        transport.serial.buffer.extend(ack_frame(0, 1)[:4])
        transport.poll_acks()
        transport.serial.queue_error = OSError("queue failed")
        with self.assertRaises(OSError):
            transport.poll_acks()
        self.assertEqual(transport.parser.feed(ack_frame(0, 1)[4:]), [])
        transport.serial.queue_error = None
        transport.serial.buffer.extend(ack_frame(0, 1)[4:])
        transport.serial.auto_ack = True
        def read_too_late(count):
            self.now += transport.timeout
            return BufferedSerial.read(transport.serial, count)
        transport.serial.read = read_too_late
        result = transport.emergency_close()
        self.assertFalse(result["acknowledged"])
        self.assertIn("timeout", result["error"])
        self.assertEqual(transport.serial.close_count, 1)

    def test_invalid_command_does_not_write_or_consume_sequence(self):
        transport = self.transport()
        with self.assertRaises((ValueError, struct.error)):
            transport.send_async(1, 256, 42)
        self.assertEqual(transport.sequence, 0)
        self.assertEqual(transport.pending_count, 0)
        self.assertEqual(transport.serial.packets, [])
        self.assertFalse(transport.serial.closed)

    def test_invalid_timing_configuration_never_opens_serial(self):
        for kwargs in ({"baud": 0}, {"baud": True}, {"timeout": 0},
                       {"timeout": float("inf")}, {"timeout": float("nan")}):
            with self.subTest(kwargs=kwargs), patch("serial.Serial") as factory:
                with self.assertRaises(ValueError):
                    SerialTransport("FAKE", **kwargs)
                factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
