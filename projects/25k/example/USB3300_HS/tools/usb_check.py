#!/usr/bin/env python3
"""Record one macOS USB target; optionally verify its CDC binary echo."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import time


IOREG = "/usr/sbin/ioreg"
CHILDREN = "IORegistryEntryChildren"
DEVICE_FIELDS = (
    "idVendor", "idProduct", "bcdUSB", "bcdDevice", "bDeviceClass",
    "bDeviceSubClass", "bDeviceProtocol", "bMaxPacketSize0",
    "bNumConfigurations", "USB Product Name", "kUSBProductString", "USB Vendor Name",
    "USB Serial Number", "USB Address", "locationID", "USBSpeed",
    "UsbLinkSpeed", "Device Speed",
    "kUSBCurrentConfiguration",
)
INTERFACE_FIELDS = (
    "bInterfaceNumber", "bAlternateSetting", "bInterfaceClass",
    "bInterfaceSubClass", "bInterfaceProtocol", "bNumEndpoints",
)
LOG_PREDICATE = (
    'subsystem CONTAINS[c] "usb" OR senderImagePath CONTAINS[c] "IOUSB" '
    'OR (process == "kernel" AND eventMessage CONTAINS[c] "USB")'
)
DEFAULT_CHUNK_SIZES = (1, 7, 31, 32, 33, 63, 64)


class RegistryQueryError(RuntimeError):
    def __init__(self, attempts):
        super().__init__("USB registry query failed")
        self.attempts = attempts


def timestamp():
    return datetime.now().astimezone().isoformat()


def json_value(value):
    if isinstance(value, bytes):
        return {"hex": value.hex(), "length": len(value)}
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_value(v) for v in value]
    return value


def parse_text_registry(text):
    """Parse ioreg's tree and scalar properties, without evaluating its text."""
    roots, stack = [], []
    node_pattern = re.compile(r"^(.*?)\+-o (.*?)\s+<class ([^,>]+), id (0x[0-9a-fA-F]+)")
    property_pattern = re.compile(r'^([ |]*)"([^"\n]+)" = (.*)$')
    property_indent = None
    for line in text.splitlines():
        match = node_pattern.match(line)
        if match:
            prefix, name, klass, registry_id = match.groups()
            depth = len(prefix)
            node = {"IORegistryEntryName": name, "IOObjectClass": klass,
                    "IORegistryEntryID": int(registry_id, 16), CHILDREN: []}
            while stack and stack[-1][0] >= depth:
                stack.pop()
            (stack[-1][1][CHILDREN] if stack else roots).append(node)
            stack.append((depth, node))
            property_indent = None
            continue
        match = property_pattern.match(line)
        if not stack or not match:
            continue
        prefix, key, raw = match.groups()
        # Nested dictionary fields are more indented than the node's fields.
        if property_indent is None:
            property_indent = len(prefix)
        if len(prefix) != property_indent:
            continue
        raw = raw.strip()
        if raw.startswith('"'):
            try:
                value = json.loads(raw)
            except ValueError:
                continue
        elif re.fullmatch(r"(?:0x[0-9a-fA-F]+|\d+)", raw):
            value = int(raw, 16 if raw.startswith("0x") else 10)
        elif re.fullmatch(r"<[0-9a-fA-F ]*>", raw):
            value = bytes.fromhex(raw[1:-1])
        elif raw in ("Yes", "No"):
            value = raw == "Yes"
        else:
            continue
        stack[-1][1][key] = value
    if not roots:
        raise ValueError("no registry tree nodes in ioreg text; query was not verified")
    return roots


def read_registry():
    attempts = []
    # IOService retains the driver/IOSerialBSDClient children needed to tie a
    # /dev/cu.* path to this device; the IOUSB plane alone cannot prove that.
    for archive in (True, False):
        command = [IOREG, "-p", "IOService", "-r", "-c", "IOUSBHostDevice", "-l", "-w", "0"]
        if archive:
            command.append("-a")
        try:
            process = subprocess.run(command, capture_output=True, timeout=15, check=False)
            record = {"command": command, "returncode": process.returncode,
                      "stderr": process.stderr.decode(errors="replace").strip()}
            attempts.append(record)
            if process.returncode or b"ioreg: error" in process.stderr.lower():
                continue
            roots = plistlib.loads(process.stdout) if archive else parse_text_registry(
                process.stdout.decode(errors="replace"))
            if not isinstance(roots, list):
                raise ValueError("registry archive is not a list")
            return roots, attempts, "ioreg_plist" if archive else "ioreg_text"
        except (OSError, ValueError, plistlib.InvalidFileException, subprocess.TimeoutExpired) as error:
            attempts.append({"command": command, "error": str(error)})
    raise RegistryQueryError(attempts)


def walk(nodes):
    for node in nodes:
        if isinstance(node, dict):
            yield node
            yield from walk(node.get(CHILDREN, []))


def is_device(node):
    return (node.get("IOObjectClass") in ("IOUSBHostDevice", "IOUSBDevice")
            or ("bNumConfigurations" in node and "bInterfaceNumber" not in node))


def descendants_of_device(node):
    yield node
    for child in node.get(CHILDREN, []):
        # Never associate a hub's downstream physical device with its parent.
        if isinstance(child, dict) and not is_device(child):
            yield from descendants_of_device(child)


def describe_target(roots, vid, pid, product):
    devices = {}
    for node in walk(roots):
        if not is_device(node) or (node.get("idVendor"), node.get("idProduct")) != (vid, pid):
            continue
        # macOS may sanitize USB Product Name (e.g. '-' to '_'). The
        # descriptor string remains in kUSBProductString when available.
        product_string = node.get("kUSBProductString", node.get("USB Product Name"))
        if product and product_string != product:
            continue
        key = node.get("IORegistryEntryID")
        if key is None:
            raise ValueError("target has no registry entry ID; cannot safely deduplicate devices")
        if key in devices:
            continue
        properties = {k: json_value(node[k]) for k in DEVICE_FIELDS if k in node}
        interfaces, ports = [], {}
        for child in descendants_of_device(node):
            if "bInterfaceNumber" in child:
                interfaces.append({k: child[k] for k in INTERFACE_FIELDS if k in child})
            path = child.get("IOCalloutDevice")
            if path:
                ports[path] = {"callout": path, "dialin": child.get("IODialinDevice"),
                               "registry_id": child.get("IORegistryEntryID")}
        devices[key] = {
            "registry_id": key, "registry_name": node.get("IORegistryEntryName"),
            "properties": properties, "interfaces": interfaces,
            "serial_ports": list(ports.values()),
            "descriptor_properties": {k: json_value(v) for k, v in node.items()
                                      if "descriptor" in k.lower()},
        }
    return list(devices.values())


def require_link_speed(device, expected_mbps):
    """Confirm negotiated speed from this target's host registry properties.

    UsbLinkSpeed is in bits/s. Device Speed uses the IOUSBHost speed enum;
    USBSpeed uses a different encoding and is retained as raw evidence only.
    bcdUSB describes supported protocol, not the negotiated connection speed.
    """
    properties = device["properties"]
    observations = {}
    if "UsbLinkSpeed" in properties:
        value = properties["UsbLinkSpeed"]
        if type(value) is not int or value <= 0:
            raise ValueError("refusing speed check: invalid UsbLinkSpeed registry value")
        observations["UsbLinkSpeed"] = value / 1_000_000
    if "Device Speed" in properties:
        value = properties["Device Speed"]
        speed_enum = {0: 1.5, 1: 12, 2: 480, 3: 5000, 4: 10000}
        if type(value) is not int or value not in speed_enum:
            raise ValueError("refusing speed check: unknown Device Speed registry value")
        observations["Device Speed"] = speed_enum[value]
    if not observations:
        raise ValueError("refusing speed check: target has no negotiated link speed evidence")
    if len(set(observations.values())) != 1:
        raise ValueError(f"refusing speed check: conflicting target registry speed evidence {observations}")
    actual = next(iter(observations.values()))
    if actual != expected_mbps:
        raise ValueError(f"refusing speed check: expected {expected_mbps} Mbps, target negotiated {actual:g} Mbps")
    return {"expected_speed_mbps": expected_mbps, "observed_speed_mbps": actual,
            "registry_evidence": {key: properties[key] for key in observations}, "passed": True}


def loopback_port(devices, expected_speed_mbps=None):
    if len(devices) != 1:
        raise ValueError(f"refusing serial open: expected one target device, found {len(devices)}")
    device = devices[0]
    if expected_speed_mbps is not None:
        require_link_speed(device, expected_speed_mbps)
    classes = {interface.get("bInterfaceClass") for interface in device["interfaces"]}
    if not {2, 10}.issubset(classes):
        raise ValueError("refusing serial open: CDC control and data interfaces were not both identified")
    ports = device["serial_ports"]
    if len(ports) != 1 or not ports[0]["callout"].startswith("/dev/cu."):
        raise ValueError("refusing serial open: target does not have exactly one /dev/cu.* callout")
    return device, ports[0]["callout"]


def binary_echo(port, args):
    try:
        import serial
    except ImportError as error:
        raise RuntimeError("loopback requires pyserial in the chosen Python environment") from error
    if not stat.S_ISCHR(os.stat(port).st_mode):
        raise ValueError("refusing serial open: callout path is not a character device")
    chunk_sizes = tuple(getattr(args, "chunk_sizes", DEFAULT_CHUNK_SIZES))
    sizes = chunk_sizes * args.rounds
    count = sum(sizes)
    nonce = os.urandom(16)
    payload = (nonce + bytes(range(256)) * ((count + 255) // 256))[:count]
    result = {"port": port, "baudrate": args.baud, "dtr": True,
              "chunk_sizes": list(chunk_sizes), "rounds": args.rounds,
              "timeout_seconds_per_chunk": args.timeout, "chunks": [], "passed": False}
    with serial.Serial(port=None, baudrate=args.baud, timeout=0.1,
                       write_timeout=args.timeout, exclusive=True) as connection:
        connection.dtr = True
        connection.rts = False
        connection.port = port
        connection.open()
        time.sleep(0.2)
        connection.reset_input_buffer()
        offset = 0
        for size in sizes:
            expected = payload[offset:offset+size]
            started = time.monotonic()
            written = connection.write(expected)
            received = bytearray()
            deadline = started + args.timeout
            while len(received) < size and time.monotonic() < deadline:
                received.extend(connection.read(size-len(received)))
            matched = written == size and received == expected
            result["chunks"].append({"offset": offset, "size": size, "written": written,
                                     "received": len(received), "passed": matched})
            if not matched:
                result.update({"status": "echo_mismatch_or_timeout", "failed_offset": offset,
                               "expected_hex": expected.hex(), "received_hex": received.hex()})
                return result
            offset += size
        # Detect trailing duplicates as well as missing or altered bytes.
        extra = connection.read(1)
        result.update({"bytes_sent": count, "bytes_received": offset,
                       "sha256": hashlib.sha256(payload).hexdigest(),
                       "extra_hex": extra.hex(), "passed": not extra,
                       "status": "pass" if not extra else "unexpected_extra_data"})
    return result


def collect_logs(seconds):
    command = ["/usr/bin/log", "show", "--style", "ndjson", "--last", f"{seconds}s",
               "--info", "--debug", "--predicate", LOG_PREDICATE]
    try:
        process = subprocess.run(command, capture_output=True, timeout=20, check=False)
        lines = process.stdout.decode(errors="replace").splitlines()
        return {"command": command, "returncode": process.returncode,
                "stderr": process.stderr.decode(errors="replace").strip(),
                "lines": lines[-2000:], "truncated": len(lines) > 2000,
                "scope": "USB events in this time window; not all can be attributed to the target"}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "error": str(error)}


def usb_id(text):
    try:
        value = int(text.removeprefix("0x").removeprefix("0X"), 16)
    except ValueError as error:
        raise argparse.ArgumentTypeError("USB IDs must be hexadecimal") from error
    if not 0 <= value <= 0xFFFF:
        raise argparse.ArgumentTypeError("USB ID must fit in 16 bits")
    return value


def parse_chunk_sizes(text):
    try:
        items = text.split(",")
        if any(not re.fullmatch(r"\s*\d+\s*", item) for item in items):
            raise ValueError
        values = tuple(int(item) for item in items)
        if not values or any(not 1 <= value <= 2048 for value in values):
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise argparse.ArgumentTypeError("chunk sizes must be a nonempty comma-separated list of integers in [1,2048]") from error
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vid", type=usb_id, default=0xFB9A, help="hexadecimal VID; default FB9A")
    parser.add_argument("--pid", type=usb_id, default=0xFB9A, help="hexadecimal PID; default FB9A")
    parser.add_argument("--product", default="FPGA-USB-Serial", help="exact product string")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--loopback", action="store_true", help="open only a unique target CDC callout and send binary echo data")
    parser.add_argument("--expected-speed-mbps", type=int, choices=(12, 480),
                        help="require this negotiated target link speed, including before serial open")
    parser.add_argument("--timeout", type=float, default=3, help="seconds per echo chunk")
    parser.add_argument("--rounds", type=int, default=8, help="rounds of the configured host write sizes")
    parser.add_argument("--chunk-sizes", type=parse_chunk_sizes, default=DEFAULT_CHUNK_SIZES,
                        help="comma-separated host write sizes in [1,2048]; default 1,7,31,32,33,63,64")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--logs-seconds", type=int, default=0, help="include recent USB logs; 0 disables")
    args = parser.parse_args()
    if not 0 < args.timeout <= 30 or not 1 <= args.rounds <= 64 or not 0 <= args.logs_seconds <= 300:
        parser.error("require timeout in (0,30], rounds in [1,64], logs-seconds in [0,300]")
    result = {"started_at": timestamp(), "passed": False,
              "mode": "loopback" if args.loopback else "enumeration_only",
              "target": {"vid": f"{args.vid:04X}", "pid": f"{args.pid:04X}", "product": args.product},
              "expected_speed_mbps": args.expected_speed_mbps,
              "descriptor_scope": "registry descriptor fields only; no raw GET_DESCRIPTOR transfer is issued"}
    code = 4
    try:
        if sys.platform != "darwin":
            raise RuntimeError("live USB checks are supported only on macOS")
        roots, attempts, provider = read_registry()
        result.update({"query_attempts": attempts, "provider": provider})
        devices = describe_target(roots, args.vid, args.pid, args.product)
        result.update({"devices": devices, "matching_devices": len(devices)})
        # Persist enumeration before any possible serial access.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        if args.expected_speed_mbps is not None:
            if len(devices) != 1:
                raise ValueError(f"refusing speed check: expected one target device, found {len(devices)}")
            result["speed_check"] = require_link_speed(devices[0], args.expected_speed_mbps)
        if args.loopback:
            device, port = loopback_port(devices, args.expected_speed_mbps)
            fresh, attempts, _ = read_registry()
            result["pre_open_query_attempts"] = attempts
            current_devices = describe_target(fresh, args.vid, args.pid, args.product)
            result["pre_open_devices"] = current_devices
            current, current_port = loopback_port(current_devices, args.expected_speed_mbps)
            if (device["registry_id"], port) != (current["registry_id"], current_port):
                raise ValueError("target registry ID or callout changed before open; rerun enumeration")
            if args.expected_speed_mbps is not None:
                result["pre_open_speed_check"] = require_link_speed(current, args.expected_speed_mbps)
            result["loopback"] = binary_echo(port, args)
            result["passed"] = result["loopback"]["passed"]
            result["status"] = result["loopback"]["status"]
        else:
            result["passed"] = len(devices) == 1
            result["status"] = "unique_target_enumerated" if len(devices) == 1 else (
                "target_not_enumerated" if not devices else "multiple_target_devices")
        code = 0 if result["passed"] else 2
    except RegistryQueryError as error:
        result.update({"status": "host_query_failed", "query_attempts": error.attempts,
                       "error": str(error)})
    except Exception as error:
        result.update({"status": "check_failed", "error": f"{type(error).__name__}: {error}"})
    if args.logs_seconds:
        result["usb_logs"] = collect_logs(args.logs_seconds)
    result["finished_at"] = timestamp()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
