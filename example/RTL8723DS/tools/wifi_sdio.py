#!/usr/bin/env python3
"""Host SDIO access through the wifi_scan_top JTAG mailbox, original board pins."""
import argparse
import json
import struct
import time
from pathlib import Path

from jtag_mpsse import Jtag


class Sdio:
    def __init__(self, jtag):
        self.jtag = jtag
        self.sequence = 0
        self.powered = False
        usercode = jtag.reg32(0x13)
        if usercode != 0x13802303:
            raise RuntimeError(f'Need Wi-Fi mailbox SRAM image 13802303, found {usercode:08x}')
        jtag.shift(0x42, 8, ir=True)
        if self.exchange(127) != 0x5344494f:
            raise RuntimeError('Invalid SDIO mailbox signature')

    def exchange(self, op, argument=0, data=0, timeout=2):
        self.sequence = self.sequence % 0xffffff + 1
        tag = self.sequence << 8 | op
        packet = int.from_bytes(struct.pack('<4I', 0x47544a57, tag, argument, data), 'little')
        self.jtag.shift(packet, 128)
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            value = self.jtag.shift(0, 128)
            magic, echoed, response, error = struct.unpack('<4I', value.to_bytes(16, 'little'))
            if magic == 0x31505357 and echoed == tag:
                if error:
                    raise OSError(f'JTAG SDIO operation {op} error {error:02x}, argument {argument:08x}')
                return response
        raise TimeoutError(f'JTAG mailbox response timeout, op={op}, tag={tag:08x}')

    def command(self, command, argument=0):
        flags = command | (0x40 if command == 0 else 0) | (0x80 if command in (0, 5) else 0)
        if command == 7:
            flags |= 0x100
        return self.exchange(1, argument, flags)

    def cmd52(self, function, address, value=None):
        if not 0 <= address < 0x20000 or not 0 <= function < 8:
            raise ValueError('CMD52 address/function out of range')
        argument = function << 28 | address << 9
        if value is not None:
            argument |= 0x80000000 | (value & 255)
        response = self.command(52, argument)
        if response & 0xcb00:
            raise OSError(f'CMD52 R5 error {response:08x}, addr={address:05x}')
        return response & 255

    def cmd53(self, address, length=None, data=None, increment=True):
        if not 0 <= address < 0x20000:
            raise ValueError('CMD53 address out of range')
        writing = data is not None
        if writing:
            data = bytes(data)
            length = len(data)
        if length is None or not 1 <= length <= 2048:
            raise ValueError('CMD53 supports 1..2048 bytes')
        block = length > 512
        if block and length % 512:
            raise ValueError('CMD53 block transfer length must be a multiple of 512')
        count = length // 512 if block else length % 512
        if writing:
            payload = data + bytes((-length) % 4)
            for offset in range(0, len(payload), 4):
                self.exchange(2, offset//4, int.from_bytes(payload[offset:offset+4], 'little'))
        argument = (int(writing) << 31 | 1 << 28 | int(block) << 27 |
                    int(increment) << 26 | address << 9 | count)
        response = self.command(53, argument)
        if response & 0xcb00:
            raise OSError(f'CMD53 R5 error {response:08x}, addr={address:05x}')
        if writing:
            return
        result = bytearray()
        for offset in range(0, length, 4):
            result.extend(self.exchange(3, offset//4).to_bytes(4, 'little'))
        return bytes(result[:length])

    def enumerate(self):
        self.exchange(4, 0); time.sleep(.2)
        self.exchange(4, 1); time.sleep(.2)
        self.command(0)
        ocr = self.command(5)
        if not (ocr & 0x00300000):
            raise RuntimeError(f'Unsupported SDIO voltage OCR {ocr:08x}')
        for _ in range(100):
            ocr = self.command(5, 0x00300000)
            if ocr & 0x80000000:
                break
            time.sleep(.01)
        else:
            raise TimeoutError('SDIO OCR ready timeout')
        r6 = self.command(3)
        rca = r6 >> 16
        if not rca or r6 & 0xe000:
            raise RuntimeError(f'Invalid RCA/R6 {r6:08x}')
        self.command(7, rca << 16)
        revision = self.cmd52(0, 0)
        pointer = sum(self.cmd52(0, 9+i) << (8*i) for i in range(3))
        cursor = pointer
        ids = None
        for _ in range(256):
            code = self.cmd52(0, cursor); cursor += 1
            if code == 0xff:
                break
            if code == 0:
                continue
            length = self.cmd52(0, cursor); cursor += 1
            if length == 0xff or cursor+length >= 0x20000:
                raise RuntimeError('Invalid CIS tuple boundary')
            if code == 0x20 and length >= 4:
                ids = [sum(self.cmd52(0, cursor+i+j) << (8*j) for j in range(2)) for i in (0, 2)]
                break
            cursor += length
        if ids != [0x024c, 0xd723]:
            raise RuntimeError(f'Unexpected SDIO MANFID {ids}')
        self.cmd52(0, 2, self.cmd52(0, 2) | 2)
        for _ in range(100):
            if self.cmd52(0, 3) & 2:
                break
            time.sleep(.01)
        else:
            raise TimeoutError('Function 1 ready timeout')
        self.cmd52(0, 0x110, 0)
        self.cmd52(0, 0x111, 2)
        self.identity = dict(ocr=f'{ocr:08x}', rca=f'{rca:04x}', revision=revision,
                             vendor_id='024c', device_id='d723', function1_ready=True, block_size=512)
        return self.identity

    @staticmethod
    def address(offset, local=False):
        return (0 if local else 0x10000) | (offset & (0x0fff if local else 0x7fff))

    def read(self, offset, size=1, local=False):
        address = self.address(offset, local)
        if self.powered:
            return int.from_bytes(self.cmd53(address, size), 'little')
        return sum(self.cmd52(1, address+i) << (8*i) for i in range(size))

    def write(self, offset, value, size=1, local=False):
        address = self.address(offset, local)
        if self.powered:
            self.cmd53(address, data=value.to_bytes(size, 'little'))
        else:
            for i in range(size):
                self.cmd52(1, address+i, value >> (8*i))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--location', type=int)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'passed': False, 'operation': 'SDIO mailbox and enumeration; not a Wi-Fi scan'}
    try:
        with Jtag(args.location) as jtag:
            sdio = Sdio(jtag)
            result['identity'] = sdio.enumerate()
            result['registers_cmd52'] = {f'{a:04x}': f'{sdio.read(a,4):08x}' for a in (0, 4, 0xf0)}
            result['passed'] = True
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
