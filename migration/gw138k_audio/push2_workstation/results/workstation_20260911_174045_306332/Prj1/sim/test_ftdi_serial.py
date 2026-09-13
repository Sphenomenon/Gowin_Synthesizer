"""D2XX adapter contracts exercised with a fake DLL; never opens USB hardware."""
from __future__ import annotations

from collections import defaultdict, deque
import ctypes
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from instrument_backend import ftdi_serial as module
from instrument_backend.ftdi_serial import DWORD, FT_HANDLE, FtdiSerial


SERIAL = "2025030317B"
HANDLE = 0x1234567887654321 if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x87654321


def put(pointer, kind, value):
    ctypes.cast(pointer, ctypes.POINTER(kind))[0] = value


class FakeFunction:
    def __init__(self, dll, name):
        self.dll, self.name = dll, name
        self.argtypes = self.restype = None

    def __call__(self, *args):
        self.dll.calls.append((self.name, args))
        errors = self.dll.failures[self.name]
        status = errors.popleft() if errors else 0
        if status:
            return status
        return self.dll.invoke(self.name, *args)


class FakeDll:
    def __init__(self, *, serial=SERIAL, usb_id=0x04036010):
        self.calls = []
        self.failures = defaultdict(deque)
        self.serial, self.usb_id = serial, usb_id
        self.latency = 16
        self.latency_reads = 0
        self.verify_latency = None
        self.rx = bytearray()
        self.queue_override = None
        self.write_limit = None
        self.written = bytearray()
        self.closed = False
        for name in module._SIGNATURES:
            setattr(self, name, FakeFunction(self, name))

    def invoke(self, name, *args):
        if name == "FT_OpenEx":
            assert ctypes.string_at(args[0]) == SERIAL.encode("ascii")
            assert args[1] == 1
            put(args[2], FT_HANDLE, HANDLE)
            return 0
        assert args[0].value == HANDLE, "pointer-width handle must survive every API"
        if name == "FT_GetDeviceInfo":
            put(args[1], DWORD, 6)  # FT_DEVICE_2232H
            put(args[2], DWORD, self.usb_id)
            ctypes.memmove(args[3], self.serial.encode("ascii") + b"\0", len(self.serial) + 1)
            ctypes.memmove(args[4], b"Tang Mega B\0", 12)
            assert args[5] is None
        elif name == "FT_GetLatencyTimer":
            self.latency_reads += 1
            timer = (self.verify_latency if self.latency_reads > 1
                     and self.verify_latency is not None else self.latency)
            put(args[1], ctypes.c_ubyte, timer)
        elif name == "FT_SetLatencyTimer":
            self.latency = args[1]
        elif name == "FT_GetQueueStatus":
            put(args[1], DWORD, len(self.rx) if self.queue_override is None
                else self.queue_override)
        elif name == "FT_Read":
            data = bytes(self.rx[:args[2]])
            del self.rx[:len(data)]
            ctypes.memmove(args[1], data, len(data))
            put(args[3], DWORD, len(data))
        elif name == "FT_Write":
            count = args[2] if self.write_limit is None else min(args[2], self.write_limit)
            self.written.extend(ctypes.string_at(args[1], count))
            put(args[3], DWORD, count)
        elif name == "FT_Purge":
            assert args[1] == 1, "only the receive queue may be purged"
            self.rx.clear()
        elif name == "FT_Close":
            self.closed = True
        return 0

    def named_calls(self, name):
        return [args for called, args in self.calls if called == name]


class FtdiSerialTests(unittest.TestCase):
    def connect(self, dll=None, **kwargs):
        dll = FakeDll() if dll is None else dll
        return FtdiSerial("COM26", serial_number=SERIAL, dll=dll, **kwargs), dll

    def test_initialization_configures_exact_b_and_verified_one_ms(self):
        serial, dll = self.connect()
        self.assertTrue(serial.is_open)
        self.assertEqual(dll.named_calls("FT_SetBaudRate")[0][1:], (115200,))
        self.assertEqual(dll.named_calls("FT_SetDataCharacteristics")[0][1:], (8, 0, 0))
        self.assertEqual(dll.named_calls("FT_SetFlowControl")[0][1:], (0, 0, 0))
        self.assertEqual(dll.named_calls("FT_SetTimeouts")[0][1:], (20, 350))
        self.assertEqual(dll.latency, 1)
        self.assertEqual(serial.latency_ms, 1)
        self.assertEqual(serial.profile, {
            "backend": "ftdi-d2xx", "port": "COM26", "serial_number": SERIAL,
            "vid": 0x0403, "pid": 0x6010, "device_type": 6,
            "description": "Tang Mega B", "latency_ms": 1,
            "previous_latency_ms": 16,
        })
        self.assertEqual(ctypes.sizeof(DWORD), 4)
        self.assertIs(dll.FT_OpenEx.restype, DWORD)
        self.assertIs(dll.FT_OpenEx.argtypes[2]._type_, FT_HANDLE)
        self.assertIs(dll.FT_Read.argtypes[3]._type_, DWORD)
        self.assertNotIn("FT_ResetDevice", [name for name, _ in dll.calls])
        self.assertNotIn("FT_SetBitMode", [name for name, _ in dll.calls])
        serial.close()

    def test_partial_write_preserves_nuls_count_and_never_retries(self):
        serial, dll = self.connect()
        dll.write_limit = 3
        self.assertEqual(serial.write(b"a\0bcd"), 3)
        self.assertEqual(dll.written, b"a\0b")
        self.assertEqual(len(dll.named_calls("FT_Write")), 1)
        self.assertEqual(serial.write(b""), 0)
        self.assertEqual(len(dll.named_calls("FT_Write")), 1)
        serial.close()

    def test_read_drains_available_bytes_without_waiting_for_larger_request(self):
        serial, dll = self.connect()
        dll.rx.extend(b"a\0bc")
        self.assertEqual(serial.in_waiting, 4)
        self.assertEqual(serial.read(2), b"a\0")
        self.assertEqual(serial.read(64), b"bc")
        self.assertEqual([args[2] for args in dll.named_calls("FT_Read")], [2, 2])
        self.assertEqual(serial.read(1), b"")  # finite driver timeout, no retry
        self.assertEqual(len(dll.named_calls("FT_Read")), 3)
        serial.close()

    def test_empty_queue_can_receive_during_bounded_read(self):
        serial, dll = self.connect()
        dll.rx.extend(b"X")
        dll.queue_override = 0
        self.assertEqual(serial.read(1), b"X")
        serial.close()

    def test_zero_timeout_is_nonblocking_even_if_d2xx_zero_means_infinite(self):
        serial, dll = self.connect(timeout=0)
        self.assertEqual(dll.named_calls("FT_SetTimeouts")[0][1], 1)
        self.assertEqual(serial.read(4), b"")
        self.assertEqual(dll.named_calls("FT_Read"), [])
        dll.rx.extend(b"abc")
        self.assertEqual(serial.read(4), b"abc")
        serial.close()

    def test_read_zero_and_rx_purge_do_not_touch_tx(self):
        serial, dll = self.connect()
        serial.write(b"keep")
        dll.rx.extend(b"discard")
        before = len(dll.calls)
        self.assertEqual(serial.read(0), b"")
        self.assertEqual(len(dll.calls), before)
        serial.reset_input_buffer()
        self.assertEqual(dll.rx, b"")
        self.assertEqual(dll.written, b"keep")
        self.assertEqual(dll.named_calls("FT_Purge")[0][1], 1)
        serial.close()

    def test_close_restores_timer_then_closes_exact_handle_once(self):
        serial, dll = self.connect()
        serial.close()
        self.assertFalse(serial.is_open)
        self.assertEqual(dll.latency, 16)
        self.assertTrue(dll.closed)
        self.assertEqual([name for name, _ in dll.calls[-2:]],
                         ["FT_SetLatencyTimer", "FT_Close"])
        before = len(dll.calls)
        serial.close()
        self.assertEqual(len(dll.calls), before)
        for action in (lambda: serial.read(1), lambda: serial.write(b"a"),
                       lambda: serial.in_waiting, serial.reset_input_buffer):
            with self.assertRaisesRegex(OSError, "closed"):
                action()

    def test_status_errors_surface_api_and_status_without_retry(self):
        for name, action in (("FT_Write", lambda s: s.write(b"a")),
                             ("FT_Read", lambda s: s.read(1)),
                             ("FT_GetQueueStatus", lambda s: s.in_waiting),
                             ("FT_Purge", lambda s: s.reset_input_buffer())):
            with self.subTest(api=name):
                serial, dll = self.connect()
                dll.failures[name].append(4)
                with self.assertRaisesRegex(OSError, rf"{name}.*FT_STATUS=4"):
                    action(serial)
                self.assertEqual(len(dll.named_calls(name)), 1)
                serial.close()

    def test_identity_mismatch_closes_before_any_uart_configuration(self):
        for kwargs in ({"serial": "2025030317A"}, {"usb_id": 0x04036001}):
            with self.subTest(kwargs=kwargs):
                dll = FakeDll(**kwargs)
                with self.assertRaisesRegex(OSError, "identity mismatch"):
                    self.connect(dll)
                self.assertTrue(dll.closed)
                self.assertEqual(dll.named_calls("FT_SetBaudRate"), [])
                self.assertEqual(dll.named_calls("FT_SetLatencyTimer"), [])

    def test_open_failure_does_not_operate_on_unowned_handle(self):
        dll = FakeDll()
        dll.failures["FT_OpenEx"].append(3)
        with self.assertRaisesRegex(OSError, "FT_OpenEx.*FT_STATUS=3"):
            self.connect(dll)
        self.assertEqual([name for name, _ in dll.calls], ["FT_OpenEx"])

    def test_initialization_errors_always_close_and_restore_only_after_change(self):
        for name in ("FT_GetDeviceInfo", "FT_GetLatencyTimer", "FT_SetBaudRate",
                     "FT_SetDataCharacteristics", "FT_SetFlowControl", "FT_SetTimeouts",
                     "FT_SetLatencyTimer"):
            with self.subTest(api=name):
                dll = FakeDll()
                dll.failures[name].append(4)
                with self.assertRaisesRegex(OSError, rf"{name}.*FT_STATUS=4"):
                    self.connect(dll)
                self.assertTrue(dll.closed)
                self.assertEqual(dll.latency, 16)
                self.assertEqual(len(dll.named_calls("FT_Close")), 1)
                if name == "FT_SetLatencyTimer":
                    self.assertEqual([args[1] for args in dll.named_calls(name)], [1, 16])
                else:
                    self.assertEqual(dll.named_calls("FT_SetLatencyTimer"), [])

    def test_failed_latency_verification_restores_and_closes(self):
        dll = FakeDll()
        dll.verify_latency = 16
        with self.assertRaisesRegex(OSError, "latency verification failed"):
            self.connect(dll)
        self.assertTrue(dll.closed)
        self.assertEqual(dll.latency, 16)
        self.assertEqual([args[1] for args in dll.named_calls("FT_SetLatencyTimer")], [1, 16])

    def test_failed_verification_read_restores_and_closes(self):
        dll = FakeDll()
        dll.failures["FT_GetLatencyTimer"].extend([0, 4])
        with self.assertRaisesRegex(OSError, "FT_GetLatencyTimer.*FT_STATUS=4"):
            self.connect(dll)
        self.assertTrue(dll.closed)
        self.assertEqual(dll.latency, 16)

    def test_restore_error_still_closes_and_is_reported(self):
        serial, dll = self.connect()
        dll.failures["FT_SetLatencyTimer"].append(4)
        with self.assertRaisesRegex(OSError, "FT_SetLatencyTimer.*FT_STATUS=4"):
            serial.close()
        self.assertTrue(dll.closed)
        self.assertFalse(serial.is_open)
        serial.close()
        self.assertEqual(len(dll.named_calls("FT_Close")), 1)

    def test_close_error_keeps_handle_for_explicit_retry(self):
        serial, dll = self.connect()
        dll.failures["FT_Close"].append(4)
        with self.assertRaisesRegex(OSError, "FT_Close.*FT_STATUS=4"):
            serial.close()
        self.assertTrue(serial.is_open)
        self.assertEqual(dll.latency, 16)
        serial.close()
        self.assertFalse(serial.is_open)
        self.assertEqual([args[1] for args in dll.named_calls("FT_SetLatencyTimer")], [1, 16])

    def test_cleanup_error_does_not_hide_initialization_error(self):
        dll = FakeDll()
        dll.verify_latency = 16
        dll.failures["FT_SetLatencyTimer"].extend([0, 4])
        with self.assertRaisesRegex(OSError, "latency verification failed") as caught:
            self.connect(dll)
        self.assertTrue(dll.closed)
        self.assertIn("cleanup also failed", str(getattr(caught.exception, "__notes__", "")))

    def test_invalid_configuration_is_rejected_before_loading_or_opening(self):
        cases = ({"serial_number": "2025030317A"}, {"serial_number": "B"},
                 {"serial_number": "x\0B"}, {"serial_number": "x" * 16 + "B"},
                 {"serial_number": "\u4e32B"}, {"bytesize": 7}, {"parity": "E"},
                 {"stopbits": 2}, {"baudrate": 0}, {"baudrate": True},
                 {"timeout": None}, {"timeout": float("nan")}, {"timeout": -1},
                 {"write_timeout": 0}, {"write_timeout": float("inf")},
                 {"write_timeout": 5000000}, {"timeout": 1e308})
        for values in cases:
            with self.subTest(values=values), patch.object(module, "_system_dll") as loader:
                settings = {"serial_number": SERIAL, **values}
                with self.assertRaises(ValueError):
                    FtdiSerial("COM26", **settings)
                loader.assert_not_called()

    def test_fractional_millisecond_timeout_rounds_up(self):
        serial, dll = self.connect(timeout=0.0011, write_timeout=0.0021)
        self.assertEqual(dll.named_calls("FT_SetTimeouts")[0][1:], (2, 3))
        serial.close()

    def test_context_manager_closes_and_restores_on_body_exception(self):
        serial, dll = self.connect()
        with self.assertRaisesRegex(RuntimeError, "body"):
            with serial:
                raise RuntimeError("body")
        self.assertTrue(dll.closed)
        self.assertEqual(dll.latency, 16)

    @unittest.skipUnless(os.name == "nt", "Windows DLL-loading contract")
    def test_default_loader_uses_system_absolute_path_and_safe_search_flags(self):
        class GetDirectory:
            def __call__(self, buffer, count):
                buffer.value = r"C:\Windows\System32"
                return len(buffer.value)
        class Kernel:
            GetSystemDirectoryW = GetDirectory()
        sentinel = object()
        with patch.object(ctypes, "WinDLL", side_effect=[Kernel(), sentinel]) as loader:
            self.assertIs(module._system_dll(), sentinel)
        self.assertEqual(loader.call_args_list[0].args, ("kernel32",))
        self.assertEqual(loader.call_args_list[0].kwargs["winmode"], 0x800)
        self.assertEqual(loader.call_args_list[1].args, (r"C:\Windows\System32\ftd2xx.dll",))
        self.assertEqual(loader.call_args_list[1].kwargs["winmode"], 0x900)


if __name__ == "__main__":
    unittest.main()
