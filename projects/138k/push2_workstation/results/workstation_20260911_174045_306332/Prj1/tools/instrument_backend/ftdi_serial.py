"""A single-owner D2XX UART session for an explicitly identified FT2232 B channel.

The session holds the receive latency timer at 1 ms. It does not change the VCP
registry, reset the USB device, or touch the A/JTAG channel. D2XX and VCP must not
own the same channel simultaneously.
"""
from __future__ import annotations

import ctypes
import math
import operator
import os
from pathlib import Path


# Windows DWORD is always 32 bits, including tests on LP64 hosts.
DWORD = ctypes.c_uint32
FT_HANDLE = ctypes.c_void_p
_DWORD_PTR = ctypes.POINTER(DWORD)
_FT_OK = 0
_FT_OPEN_BY_SERIAL_NUMBER = 1
_FT_PURGE_RX = 1
_USB_ID = 0x04036010
_SIGNATURES = {
    "FT_OpenEx": [ctypes.c_void_p, DWORD, ctypes.POINTER(FT_HANDLE)],
    "FT_GetDeviceInfo": [FT_HANDLE, _DWORD_PTR, _DWORD_PTR,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
    "FT_SetBaudRate": [FT_HANDLE, DWORD],
    "FT_SetDataCharacteristics": [FT_HANDLE, ctypes.c_ubyte, ctypes.c_ubyte,
                                   ctypes.c_ubyte],
    "FT_SetFlowControl": [FT_HANDLE, ctypes.c_ushort, ctypes.c_ubyte, ctypes.c_ubyte],
    "FT_SetTimeouts": [FT_HANDLE, DWORD, DWORD],
    "FT_SetLatencyTimer": [FT_HANDLE, ctypes.c_ubyte],
    "FT_GetLatencyTimer": [FT_HANDLE, ctypes.POINTER(ctypes.c_ubyte)],
    "FT_GetQueueStatus": [FT_HANDLE, _DWORD_PTR],
    "FT_Read": [FT_HANDLE, ctypes.c_void_p, DWORD, _DWORD_PTR],
    "FT_Write": [FT_HANDLE, ctypes.c_void_p, DWORD, _DWORD_PTR],
    "FT_Purge": [FT_HANDLE, DWORD],
    "FT_Close": [FT_HANDLE],
}


def _system_dll():
    """Use Windows' system directory, never a current-directory DLL search."""
    if os.name != "nt":
        raise OSError("FTDI D2XX backend requires Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True, winmode=0x800)
    get_directory = kernel32.GetSystemDirectoryW
    get_directory.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    get_directory.restype = ctypes.c_uint32
    directory = ctypes.create_unicode_buffer(32768)
    length = get_directory(directory, len(directory))
    if not length or length >= len(directory):
        raise OSError("cannot locate the Windows system directory")
    path = Path(directory.value) / "ftd2xx.dll"
    if not path.is_absolute():
        raise OSError("Windows returned a non-absolute system directory")
    try:
        return ctypes.WinDLL(str(path), use_last_error=True, winmode=0x900)
    except OSError as exc:
        raise OSError(f"cannot load the installed FTDI D2XX library: {path}") from exc


def _timeout_ms(value, name, *, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number of seconds")
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'nonnegative' if allow_zero else 'positive'}")
    if value > 0xFFFFFFFF / 1000:
        raise ValueError(f"{name} exceeds the D2XX timeout range")
    milliseconds = max(1, math.ceil(value * 1000))
    if milliseconds > 0xFFFFFFFF:
        raise ValueError(f"{name} exceeds the D2XX timeout range")
    return milliseconds


class FtdiSerial:
    """The serial subset used by SerialTransport; no automatic retries or fallback.

    ``serial_number`` is mandatory and must name channel B exactly. The caller
    resolves COM-port metadata before choosing this backend. ``dll`` is an
    injectable D2XX-compatible object for hardware-free tests.
    """

    def __init__(self, port: str, baudrate: int = 115200, bytesize=8, parity="N",
                 stopbits=1, timeout=0.02, write_timeout=0.35, *,
                 serial_number: str, dll=None):
        self._handle = None
        self._previous_latency_ms = None
        self._latency_modified = False
        if not isinstance(port, str) or not port:
            raise ValueError("a COM-port label is required")
        if (not isinstance(serial_number, str) or not serial_number.endswith("B")
                or len(serial_number) < 2):
            raise ValueError("an exact FTDI channel B serial number is required")
        try:
            serial_bytes = serial_number.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("FTDI serial number must be ASCII") from exc
        if len(serial_bytes) > 15 or b"\0" in serial_bytes:
            raise ValueError("FTDI serial number must fit its 16-byte device field")
        if (isinstance(baudrate, bool) or not isinstance(baudrate, int)
                or not 0 < baudrate <= 0xFFFFFFFF):
            raise ValueError("baudrate must be a positive DWORD integer")
        if (bytesize, parity, stopbits) != (8, "N", 1):
            raise ValueError("this FTDI UART backend supports 8N1 only")
        read_ms = _timeout_ms(timeout, "timeout", allow_zero=True)
        write_ms = _timeout_ms(write_timeout, "write_timeout")
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.serial_number = serial_number
        self.latency_ms = None
        self._dll = _system_dll() if dll is None else dll
        for name, arguments in _SIGNATURES.items():
            function = getattr(self._dll, name)
            function.argtypes = arguments
            function.restype = DWORD

        handle = FT_HANDLE()
        serial_buffer = ctypes.create_string_buffer(serial_bytes)
        self._call("FT_OpenEx", serial_buffer, _FT_OPEN_BY_SERIAL_NUMBER,
                   ctypes.byref(handle))
        if not handle.value:
            raise OSError("FT_OpenEx returned an empty device handle")
        self._handle = handle
        try:
            device_type, usb_id = DWORD(), DWORD()
            actual_serial = ctypes.create_string_buffer(16)
            description = ctypes.create_string_buffer(64)
            self._call("FT_GetDeviceInfo", handle, ctypes.byref(device_type),
                       ctypes.byref(usb_id), actual_serial, description, None)
            if usb_id.value != _USB_ID or actual_serial.value != serial_bytes:
                raise OSError("FTDI device identity mismatch; expected USB 0403:6010 "
                              f"channel B serial {serial_number!r}, got "
                              f"ID 0x{usb_id.value:08X}, serial {actual_serial.value!r}")
            previous = ctypes.c_ubyte()
            self._call("FT_GetLatencyTimer", handle, ctypes.byref(previous))
            self._previous_latency_ms = previous.value
            self._call("FT_SetBaudRate", handle, baudrate)
            # FT_BITS_8=8, FT_STOP_BITS_1=0, FT_PARITY_NONE=0, FT_FLOW_NONE=0.
            self._call("FT_SetDataCharacteristics", handle, 8, 0, 0)
            self._call("FT_SetFlowControl", handle, 0, 0, 0)
            self._call("FT_SetTimeouts", handle, read_ms, write_ms)
            self._latency_modified = True
            self._call("FT_SetLatencyTimer", handle, 1)
            actual_latency = ctypes.c_ubyte()
            self._call("FT_GetLatencyTimer", handle, ctypes.byref(actual_latency))
            if actual_latency.value != 1:
                raise OSError(f"FTDI latency verification failed: {actual_latency.value} ms")
            self.latency_ms = actual_latency.value
            self.profile = {
                "backend": "ftdi-d2xx", "port": port, "serial_number": serial_number,
                "vid": 0x0403, "pid": 0x6010, "device_type": device_type.value,
                "description": description.value.decode("ascii", errors="replace"),
                "latency_ms": self.latency_ms,
                "previous_latency_ms": self._previous_latency_ms,
            }
        except BaseException as exc:
            try:
                self.close()
            except Exception as cleanup_error:
                if hasattr(exc, "add_note"):
                    exc.add_note(f"FTDI cleanup also failed: {cleanup_error}")
            raise

    def _call(self, name, *arguments):
        status = getattr(self._dll, name)(*arguments)
        # ctypes returns a Python int; injected functions may return a DWORD.
        status = getattr(status, "value", status)
        if status != _FT_OK:
            raise OSError(f"{name} failed (FT_STATUS={status})")

    def _open_handle(self):
        if self._handle is None:
            raise OSError("FTDI serial port is closed")
        return self._handle

    @property
    def is_open(self):
        return self._handle is not None

    @property
    def in_waiting(self):
        count = DWORD()
        self._call("FT_GetQueueStatus", self._open_handle(), ctypes.byref(count))
        return count.value

    def read(self, size=1):
        handle = self._open_handle()
        size = operator.index(size)
        if not 0 <= size <= 0xFFFFFFFF:
            raise ValueError("read size must fit a DWORD")
        if size == 0:
            return b""
        available = self.in_waiting
        if available:
            size = min(size, available)
        elif self.timeout == 0:
            return b""
        buffer = ctypes.create_string_buffer(size)
        received = DWORD()
        self._call("FT_Read", handle, buffer, size, ctypes.byref(received))
        if received.value > size:
            raise OSError("FT_Read returned an invalid byte count")
        return buffer.raw[:received.value]

    def write(self, data):
        handle = self._open_handle()
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("write requires bytes-like data")
        data = bytes(data)
        if len(data) > 0xFFFFFFFF:
            raise ValueError("write size must fit a DWORD")
        if not data:
            return 0
        buffer = ctypes.create_string_buffer(data, len(data))
        written = DWORD()
        self._call("FT_Write", handle, buffer, len(data), ctypes.byref(written))
        if written.value > len(data):
            raise OSError("FT_Write returned an invalid byte count")
        # Preserve partial writes: SerialTransport treats them as an error.
        return written.value

    def reset_input_buffer(self):
        self._call("FT_Purge", self._open_handle(), _FT_PURGE_RX)

    def close(self):
        if self._handle is None:
            return
        restore_error = None
        if self._latency_modified and self._previous_latency_ms is not None:
            try:
                self._call("FT_SetLatencyTimer", self._handle, self._previous_latency_ms)
                self._latency_modified = False
            except Exception as exc:
                restore_error = exc
        try:
            self._call("FT_Close", self._handle)
        except Exception as close_error:
            if restore_error is not None and hasattr(close_error, "add_note"):
                close_error.add_note(f"Latency restoration also failed: {restore_error}")
            # Keep a failed-to-close handle available for an explicit retry.
            raise
        else:
            self._handle = None
        if restore_error is not None:
            raise restore_error

    def __enter__(self):
        self._open_handle()
        return self

    def __exit__(self, *_exc):
        self.close()
