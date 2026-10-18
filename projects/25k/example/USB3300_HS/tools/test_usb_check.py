"""Offline parser and serial-safety checks; no device calls are made."""
import copy
import argparse
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import usb_check as usb


TEXT = '''+-o FPGA-USB-Serial@00100000  <class IOUSBHostDevice, id 0x100001, registered>
  | {
  |   "idVendor" = 64410
  |   "idProduct" = 64410
  |   "bNumConfigurations" = 1
  |   "USB Product Name" = "FPGA-USB-Serial"
  |   "locationID" = 1048576
  | }
  +-o Control  <class IOUSBHostInterface, id 0x100002, registered>
  | | {
  | |   "bInterfaceNumber" = 0
  | |   "bInterfaceClass" = 2
  | | }
  +-o Data  <class IOUSBHostInterface, id 0x100003, registered>
    | {
    |   "bInterfaceNumber" = 1
    |   "bInterfaceClass" = 10
    | }
    +-o Serial  <class IOSerialBSDClient, id 0x100004, registered>
        {
          "IOCalloutDevice" = "/dev/cu.usbmodemTEST"
          "IODialinDevice" = "/dev/tty.usbmodemTEST"
        }
'''


def targets(roots):
    return usb.describe_target(roots, 0xFB9A, 0xFB9A, "FPGA-USB-Serial")


class RegistryTests(unittest.TestCase):
    def test_registry_keeps_negotiated_speed_evidence(self):
        roots = usb.parse_text_registry(TEXT)
        roots[0].update({"UsbLinkSpeed": 480_000_000, "Device Speed": 2, "bcdUSB": 0x200})
        device = targets(roots)[0]
        self.assertEqual(device["properties"]["UsbLinkSpeed"], 480_000_000)
        self.assertEqual(device["properties"]["Device Speed"], 2)
        _, port = usb.loopback_port([device], 480)
        self.assertEqual(port, "/dev/cu.usbmodemTEST")
        self.assertEqual(usb.require_link_speed(device, 480)["observed_speed_mbps"], 480)

    def test_full_speed_is_rejected_when_high_speed_expected(self):
        device = targets(usb.parse_text_registry(TEXT))[0]
        device["properties"].update({"UsbLinkSpeed": 12_000_000, "Device Speed": 1,
                                     "bcdUSB": 0x200})
        with self.assertRaisesRegex(ValueError, "expected 480 Mbps.*12 Mbps"):
            usb.loopback_port([device], 480)
        self.assertTrue(usb.require_link_speed(device, 12)["passed"])

    def test_missing_conflicting_or_invalid_speed_evidence_is_rejected(self):
        device = targets(usb.parse_text_registry(TEXT))[0]
        device["properties"].update({"bcdUSB": 0x200, "USBSpeed": 3})
        with self.assertRaisesRegex(ValueError, "no negotiated link speed evidence"):
            usb.loopback_port([device], 480)
        device["properties"].update({"UsbLinkSpeed": 480_000_000, "Device Speed": 1})
        with self.assertRaisesRegex(ValueError, "conflicting"):
            usb.loopback_port([device], 480)
        device["properties"].update({"Device Speed": 2, "UsbLinkSpeed": "480000000"})
        with self.assertRaisesRegex(ValueError, "invalid UsbLinkSpeed"):
            usb.loopback_port([device], 480)
        device["properties"].pop("UsbLinkSpeed")
        self.assertTrue(usb.require_link_speed(device, 480)["passed"])
        device["properties"]["Device Speed"] = 99
        with self.assertRaisesRegex(ValueError, "unknown Device Speed"):
            usb.loopback_port([device], 480)

    def test_text_fallback_preserves_device_interface_port_association(self):
        roots = usb.parse_text_registry(TEXT)
        # ioreg -r can return a physical node both nested and as another root.
        devices = targets(roots + copy.deepcopy(roots))
        self.assertEqual(len(devices), 1)
        device, port = usb.loopback_port(devices)
        self.assertEqual(port, "/dev/cu.usbmodemTEST")
        self.assertEqual(device["properties"]["locationID"], 1048576)

    def test_hub_downstream_serial_is_not_its_own_port(self):
        child = usb.parse_text_registry(TEXT)[0]
        hub = dict(child, IORegistryEntryID=1)
        hub[usb.CHILDREN] = [child]
        devices = targets([hub])
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["serial_ports"], [])
        with self.assertRaisesRegex(ValueError, "expected one target"):
            usb.loopback_port(devices)

    def test_canonical_product_matches_despite_sanitized_display_name(self):
        roots = usb.parse_text_registry(TEXT)
        roots[0]["USB Product Name"] = "FPGA_USB_Serial"
        roots[0]["kUSBProductString"] = "FPGA-USB-Serial"
        devices = targets(roots)
        self.assertEqual(len(devices), 1)
        device, port = usb.loopback_port(devices)
        self.assertEqual(port, "/dev/cu.usbmodemTEST")
        self.assertEqual(device["properties"]["USB Product Name"], "FPGA_USB_Serial")
        self.assertEqual(device["properties"]["kUSBProductString"], "FPGA-USB-Serial")
        self.assertEqual(usb.describe_target(roots, 0xFB9A, 0xFB9A, "FPGA_USB_Serial"), [])
        # The display name must not override a present, different descriptor.
        roots[0]["USB Product Name"] = "FPGA-USB-Serial"
        roots[0]["kUSBProductString"] = "unrelated"
        self.assertEqual(targets(roots), [])

    def test_wrong_product_missing_cdc_and_multiple_ports_refuse_open(self):
        roots = usb.parse_text_registry(TEXT)
        roots[0]["USB Product Name"] = "unrelated"
        self.assertEqual(targets(roots), [])
        device = targets(usb.parse_text_registry(TEXT))[0]
        device["interfaces"] = []
        with self.assertRaisesRegex(ValueError, "CDC control and data"):
            usb.loopback_port([device])
        device = targets(usb.parse_text_registry(TEXT))[0]
        device["serial_ports"].append({"callout": "/dev/cu.other"})
        with self.assertRaisesRegex(ValueError, "exactly one"):
            usb.loopback_port([device])

    def test_archive_error_falls_back_instead_of_reporting_device_absent(self):
        responses = [subprocess.CompletedProcess([], 1, b"", b"ioreg: error: can't open file"),
                     subprocess.CompletedProcess([], 0, TEXT.encode(), b"")]
        with patch.object(usb.subprocess, "run", side_effect=responses):
            roots, attempts, provider = usb.read_registry()
        self.assertEqual(provider, "ioreg_text")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(targets(roots)), 1)

    def test_total_query_failure_is_not_empty_enumeration(self):
        response = subprocess.CompletedProcess([], 1, b"", b"not permitted")
        with patch.object(usb.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "query failed"):
                usb.read_registry()


class FakeSerial:
    corrupt = False

    def __init__(self, **kwargs):
        self.buffer = bytearray()
        self.opened = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.opened = False

    def open(self):
        self.opened = True

    def reset_input_buffer(self):
        self.buffer.clear()

    def write(self, value):
        self.buffer.extend(value)
        if self.corrupt:
            self.buffer[0] ^= 1
        return len(value)

    def read(self, count):
        # Exercise partial reads rather than returning the full echo at once.
        value = self.buffer[:min(count, 3)]
        del self.buffer[:len(value)]
        return bytes(value)


class EchoTests(unittest.TestCase):
    def run_echo(self, corrupt=False, chunk_sizes=None):
        FakeSerial.corrupt = corrupt
        args = SimpleNamespace(baud=115200, timeout=0.1, rounds=2)
        if chunk_sizes is not None:
            args.chunk_sizes = chunk_sizes
        with patch.dict(sys.modules, {"serial": SimpleNamespace(Serial=FakeSerial)}), \
             patch.object(usb.os, "stat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
             patch.object(usb.time, "sleep"):
            return usb.binary_echo("/dev/cu.usbmodemTEST", args)

    def test_binary_data_and_short_reads_match(self):
        result = self.run_echo()
        self.assertTrue(result["passed"])
        self.assertEqual(result["bytes_sent"], 462)
        self.assertEqual(result["bytes_received"], 462)
        self.assertEqual(result["chunk_sizes"], list(usb.DEFAULT_CHUNK_SIZES))
        self.assertEqual(result["rounds"], 2)

    def test_custom_chunks_cross_512_byte_packet_boundary_with_short_reads(self):
        sizes = usb.parse_chunk_sizes("1,511,512,513,1024,2048")
        result = self.run_echo(chunk_sizes=sizes)
        self.assertTrue(result["passed"])
        self.assertEqual(result["chunk_sizes"], list(sizes))
        self.assertEqual(result["bytes_sent"], 2 * sum(sizes))
        self.assertEqual(result["bytes_received"], 2 * sum(sizes))
        self.assertEqual([chunk["size"] for chunk in result["chunks"]], list(sizes) * 2)

    def test_corrupt_data_fails_on_first_chunk(self):
        result = self.run_echo(corrupt=True)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["chunks"]), 1)
        self.assertEqual(result["failed_offset"], 0)

    def test_expired_chunk_deadline_returns_failure(self):
        FakeSerial.corrupt = False
        with patch.dict(sys.modules, {"serial": SimpleNamespace(Serial=FakeSerial)}), \
             patch.object(usb.os, "stat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
             patch.object(usb.time, "sleep"), \
             patch.object(usb.time, "monotonic", side_effect=[0, 1]):
            result = usb.binary_echo("/dev/cu.usbmodemTEST", SimpleNamespace(
                baud=115200, timeout=0.1, rounds=1))
        self.assertFalse(result["passed"])
        self.assertEqual(result["chunks"][0]["received"], 0)


class ArgumentTests(unittest.TestCase):
    def test_chunk_size_parser_rejects_empty_out_of_range_and_noninteger(self):
        for value in ("", " ", "1,", ",1", "1,,2", "0", "2049", "-1", "1.5", "1,abc"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                usb.parse_chunk_sizes(value)
        self.assertEqual(usb.parse_chunk_sizes(" 1, 512 ,1024,2048 "), (1, 512, 1024, 2048))

    def test_speed_mismatch_cannot_reach_binary_echo_even_after_recheck(self):
        fs = usb.parse_text_registry(TEXT)
        fs[0].update({"UsbLinkSpeed": 12_000_000, "Device Speed": 1})
        hs = copy.deepcopy(fs)
        hs[0].update({"UsbLinkSpeed": 480_000_000, "Device Speed": 2})
        for snapshots in ([fs], [hs, fs]):
            with self.subTest(snapshots=len(snapshots)), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "result.json"
                queries = [(roots, [], "offline_fixture") for roots in snapshots]
                argv = ["usb_check.py", "--loopback", "--expected-speed-mbps", "480",
                        "--output", str(output)]
                with patch.object(sys, "argv", argv), patch.object(sys, "platform", "darwin"), \
                     patch.object(usb, "read_registry", side_effect=queries), \
                     patch.object(usb, "binary_echo") as echo, patch("builtins.print"):
                    self.assertEqual(usb.main(), 4)
                echo.assert_not_called()
                result = json.loads(output.read_text())
                self.assertFalse(result["passed"])
                self.assertIn("expected 480 Mbps", result["error"])
                self.assertIn("UsbLinkSpeed", result["devices"][0]["properties"])

    def test_matching_high_speed_opens_only_after_fresh_speed_confirmation(self):
        roots = usb.parse_text_registry(TEXT)
        roots[0].update({"UsbLinkSpeed": 480_000_000, "Device Speed": 2})
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "result.json"
            argv = ["usb_check.py", "--loopback", "--expected-speed-mbps", "480",
                    "--chunk-sizes", "511,512,513,1024", "--output", str(output)]
            with patch.object(sys, "argv", argv), patch.object(sys, "platform", "darwin"), \
                 patch.object(usb, "read_registry", return_value=(roots, [], "offline_fixture")), \
                 patch.object(usb, "binary_echo", return_value={"passed": True, "status": "pass"}) as echo, \
                 patch("builtins.print"):
                self.assertEqual(usb.main(), 0)
            echo.assert_called_once()
            self.assertEqual(echo.call_args.args[1].chunk_sizes, (511, 512, 513, 1024))
            result = json.loads(output.read_text())
            self.assertTrue(result["passed"])
            self.assertEqual(result["speed_check"]["observed_speed_mbps"], 480)
            self.assertTrue(result["pre_open_speed_check"]["passed"])


if __name__ == "__main__":
    unittest.main()
