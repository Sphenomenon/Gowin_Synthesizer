#!/usr/bin/env python3
"""Check the board's RTL8723-BLE advertisement, FFF1 read and notifications."""
import argparse
import asyncio
import binascii
import json
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

CHARACTERISTIC = "0000fff1-0000-1000-8000-00805f9b34fb"
SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"


def decode_sample(value):
    value = bytes(value)
    valid = (
        len(value) == 20
        and value[:4] == b"BTST"
        and value[12:18] == bytes(range(6))
        and int.from_bytes(value[18:20], "little")
        == binascii.crc_hqx(value[:18], 0xFFFF)
    )
    return {
        "hex": value.hex(),
        "valid": valid,
        "sequence": int.from_bytes(value[4:8], "little") if len(value) == 20 else None,
        "milliseconds": int.from_bytes(value[8:12], "little") if len(value) == 20 else None,
    }


async def check(args, result):
    def matches(device, advertisement):
        # FFF0 is a common vendor UUID used by unrelated products. Only the
        # actual advertisement name identifies this bring-up image.
        return advertisement.local_name == args.name

    device = await BleakScanner.find_device_by_filter(matches, timeout=args.scan_seconds)
    if device is None:
        result["status"] = "advertisement_not_found"
        return 2
    result.update({"device_name": device.name, "device_id": device.address})
    print("Target advertisement found", flush=True)
    async with BleakClient(device, timeout=20) as client:
        result["connected"] = client.is_connected
        service = client.services.get_service(SERVICE)
        if service is None:
            result["status"] = "fff0_not_found"
            return 3
        result["service_uuid"] = service.uuid
        characteristic = service.get_characteristic(CHARACTERISTIC)
        if characteristic is None:
            result["status"] = "fff1_not_found"
            return 3
        result["characteristic_uuid"] = characteristic.uuid
        result["properties"] = characteristic.properties
        if not {"read", "notify"}.issubset(characteristic.properties):
            result["status"] = "fff1_properties_mismatch"
            return 3
        result["read"] = decode_sample(await client.read_gatt_char(characteristic))
        result["notifications"] = []
        complete = asyncio.Event()

        def on_notification(_characteristic, data):
            sample = decode_sample(data)
            result["notifications"].append(sample)
            print(json.dumps(sample), flush=True)
            if len(result["notifications"]) >= args.minimum_notifications:
                complete.set()

        await client.start_notify(characteristic, on_notification)
        try:
            await asyncio.wait_for(complete.wait(), timeout=args.sample_seconds)
        except asyncio.TimeoutError:
            pass
        finally:
            await client.stop_notify(characteristic)
        samples = result["notifications"]
        ordered = all(
            (b["sequence"] - a["sequence"]) % (1 << 32) == 1
            for a, b in zip(samples, samples[1:])
        ) if all(s["valid"] for s in samples) else False
        elapsed = [
            (b["milliseconds"] - a["milliseconds"]) % (1 << 32)
            for a, b in zip(samples, samples[1:])
        ] if all(s["valid"] for s in samples) else []
        result["notification_intervals_ms"] = elapsed
        result["sequence_contiguous"] = ordered
        result["timestamps_increasing"] = bool(elapsed) and all(
            0 < interval < (1 << 31) for interval in elapsed
        )
        result["passed"] = (
            result["read"]["valid"]
            and len(samples) >= args.minimum_notifications
            and all(s["valid"] for s in samples)
            and ordered
            and result["timestamps_increasing"]
        )
        result["status"] = "pass" if result["passed"] else "data_validation_failed"
        return 0 if result["passed"] else 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="RTL8723-BLE")
    parser.add_argument("--scan-seconds", type=float, default=15)
    parser.add_argument("--sample-seconds", type=float, default=15)
    parser.add_argument("--minimum-notifications", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.minimum_notifications < 2:
        parser.error("at least two notifications are needed to check sequence progress")
    result = {"started_at": datetime.now().astimezone().isoformat(), "passed": False}
    try:
        code = asyncio.run(check(args, result))
    except Exception as error:
        result.update({"status": "error", "error": f"{type(error).__name__}: {error}"})
        code = 5
    result["finished_at"] = datetime.now().astimezone().isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
