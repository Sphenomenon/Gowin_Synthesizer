"""Verify a 138K high-speed USB-MIDI loopback without raw-USB privileges."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import time


def find_device(sysfs=Path('/sys/bus/usb/devices')):
    matches = []
    for entry in sysfs.iterdir():
        try:
            if ((entry / 'idVendor').read_text().strip() != 'fb9a' or
                    (entry / 'idProduct').read_text().strip() != 'fb9b' or
                    (entry / 'product').read_text().strip() != 'GW138K USB2 Loopback'):
                continue
            matches.append(entry.resolve())
        except OSError:
            continue
    if len(matches) != 1:
        raise ValueError('Expected exactly one GW138K USB2 Loopback device')
    device = matches[0]
    if (device / 'speed').read_text().strip() != '480':
        raise ValueError('Probe is not enumerated at USB High-Speed 480 Mbit/s')
    if (device / 'bConfigurationValue').read_text().strip() != '1':
        raise ValueError('Probe has not selected configuration 1')
    return device


def payload(event_count):
    if event_count <= 0 or event_count % 2:
        raise ValueError('Use a positive even event count to balance Note On/Off')
    messages = bytearray()
    for index in range(event_count):
        channel = (index // 2) % 16
        note = 36 + (index // 2) % 60
        messages.extend(((0x90 if index % 2 == 0 else 0x80) | channel,
                         note, 1 + (index // 2) % 127 if index % 2 == 0 else 0))
    return bytes(messages)


def exchange(descriptor, transmitted, timeout):
    received = bytearray()
    sent = 0
    started = time.monotonic()
    deadline = started + timeout
    while sent < len(transmitted) or len(received) < len(transmitted):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f'Loopback timeout: sent {sent}, received {len(received)} of {len(transmitted)} bytes')
        readable, writable, _ = select.select([descriptor], [descriptor] if sent < len(transmitted) else [], [], remaining)
        if readable:
            block = os.read(descriptor, 65536)
            if not block:
                raise OSError('MIDI endpoint closed during loopback')
            received.extend(block)
        if writable:
            sent += os.write(descriptor, transmitted[sent:sent + 1024])
    if bytes(received) != transmitted:
        raise ValueError('Loopback payload differs from transmitted bytes')
    return dict(passed=True, sent_bytes=sent, received_bytes=len(received),
                elapsed_seconds=time.monotonic() - started,
                payload_sha256=hashlib.sha256(transmitted).hexdigest())


def run(event_count=4096, timeout=15):
    device = find_device()
    ports = [entry for entry in Path('/sys/class/sound').glob('midiC*D*')
             if entry.resolve().is_relative_to(device)]
    if len(ports) != 1:
        raise ValueError('Expected one ALSA raw MIDI port belonging to this USB probe')
    node = Path('/dev/snd') / ports[0].name
    descriptor = os.open(node, os.O_RDWR | os.O_NONBLOCK)
    try:
        while select.select([descriptor], [], [], 0)[0]:
            if not os.read(descriptor, 65536):
                break
        result = exchange(descriptor, payload(event_count), timeout)
    finally:
        os.close(descriptor)
    result.update(device=str(device), midi_node=str(node), events=event_count, usb_speed_mbps=480,
                  usb_configuration=1, scope='real_high_speed_bulk_MIDI_loopback_not_peak_bandwidth')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=int, default=4096)
    parser.add_argument('--timeout', type=float, default=15)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = dict(passed=False)
    try:
        record = run(args.events, args.timeout)
    except (OSError, ValueError) as error:
        record['error'] = str(error)
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
