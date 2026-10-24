#!/usr/bin/env python3
"""Small FT2232/D2XX JTAG transport. No programming or flash instructions.

The FTDI channel is selected by USB location; serial numbers can be empty on
this board. GPIO changes are restricted to the four JTAG MPSSE pins.
"""
import argparse
import ctypes as c
import json
import time

LIBRARY = '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/Programmer/bin/libftd2xx.dylib'


class Jtag:
    def __init__(self, location=None, frequency=1000000):
        self.lib = c.CDLL(LIBRARY)
        self.handle = c.c_void_p()
        self.closed = True
        self.lib.FT_OpenEx.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_void_p)]
        self.lib.FT_Read.argtypes = [c.c_void_p, c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong)]
        self.lib.FT_Write.argtypes = self.lib.FT_Read.argtypes
        devices = self.devices()
        candidates = [x for x in devices if x['description'].endswith(' A')]
        if location is None:
            if len(candidates) != 1:
                raise RuntimeError('Need one FT2232 channel A or an explicit location')
            location = candidates[0]['location']
        if location not in [x['location'] for x in candidates]:
            raise RuntimeError('Requested location is not a known FT2232 channel A')
        self.location = location
        self.call('FT_OpenEx', c.c_void_p(location), c.c_ulong(4), c.byref(self.handle))
        self.closed = False
        try:
            self.call('FT_SetTimeouts', self.handle, 2000, 2000)
            self.call('FT_SetLatencyTimer', self.handle, 1)
            self.call('FT_SetBitMode', self.handle, 0, 0)
            self.call('FT_SetBitMode', self.handle, 0, 2)
            self.call('FT_Purge', self.handle, 3)
            # Disable loopback, divide-by-five, adaptive and three-phase clock.
            div = max(0, min(65535, round(30000000 / frequency) - 1))
            self.write(bytes([0x85, 0x8a, 0x97, 0x8d, 0x86, div & 255, div >> 8,
                              0x80, 0x08, 0x0b]))
            self.tms([1]*6+[0])
        except BaseException:
            self.close()
            raise

    def call(self, name, *args):
        status = getattr(self.lib, name)(*args)
        if status:
            raise OSError(f'{name}: FT_STATUS={status}')

    def devices(self):
        count = c.c_ulong()
        self.call('FT_CreateDeviceInfoList', c.byref(count))
        result = []
        for i in range(count.value):
            fields = [c.c_ulong() for _ in range(4)]
            serial, desc, handle = c.create_string_buffer(64), c.create_string_buffer(64), c.c_void_p()
            self.call('FT_GetDeviceInfoDetail', i, *(c.byref(x) for x in fields),
                      serial, desc, c.byref(handle))
            result.append(dict(index=i, flags=fields[0].value, location=fields[3].value,
                               serial=serial.value.decode(), description=desc.value.decode()))
        return result

    def write(self, data):
        written = c.c_ulong()
        self.call('FT_Write', self.handle, c.c_char_p(data), len(data), c.byref(written))
        if written.value != len(data):
            raise OSError('Short FTDI write')

    def read(self, size):
        data = bytearray()
        until = time.monotonic()+3
        while len(data) < size:
            chunk = c.create_string_buffer(size-len(data)); got = c.c_ulong()
            self.call('FT_Read', self.handle, chunk, len(chunk), c.byref(got))
            data.extend(chunk.raw[:got.value])
            if time.monotonic() > until:
                raise TimeoutError(f'FTDI read {len(data)}/{size} bytes')
        return bytes(data)

    def tms(self, bits):
        packet = bytearray()
        for i in range(0, len(bits), 7):
            group = bits[i:i+7]
            packet.extend([0x4b, len(group)-1, sum(b << n for n, b in enumerate(group))])
        self.write(bytes(packet))

    def shift(self, value, width, ir=False):
        """Start/end in Run-Test/Idle, shifting LSB first; capture all TDO bits."""
        if width < 1 or value < 0 or value.bit_length() > width:
            raise ValueError('Invalid shift width/value')
        self.tms([1, 1, 0, 0] if ir else [1, 0, 0])
        whole, remainder = divmod(width-1, 8)
        packet = bytearray()
        if whole:
            if whole > 65536:
                raise ValueError('Shift too long')
            packet.extend([0x39, (whole-1) & 255, (whole-1) >> 8])
            packet.extend((value & ((1 << (whole*8))-1)).to_bytes(whole, 'little'))
        if remainder:
            packet.extend([0x3b, remainder-1, (value >> (whole*8)) & 255])
        packet.extend([0x6b, 0, 1 | (((value >> (width-1)) & 1) << 7),
                       0x4b, 1, 1, 0x87])  # Exit1 -> Update -> Idle; flush TDO.
        self.write(bytes(packet))
        data = self.read(whole+bool(remainder)+1)
        result = int.from_bytes(data[:whole], 'little')
        if remainder:
            result |= (data[whole] >> (8-remainder)) << (whole*8)
        result |= ((data[-1] >> 7) & 1) << (width-1)
        if ir:
            self.tms([0, 0, 0])  # Gowin instruction settling clocks.
        return result

    def reg32(self, instruction):
        if instruction not in (0x11, 0x13, 0x41):
            raise ValueError('Only IDCODE, USERCODE and status register are allowed')
        self.shift(instruction, 8, ir=True)
        return self.shift(0, 32)

    def close(self):
        if not self.closed:
            self.call('FT_Close', self.handle)
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--location', type=int)
    args = parser.parse_args()
    with Jtag(args.location) as jtag:
        print(json.dumps({'location': jtag.location,
                          'idcode': f'{jtag.reg32(0x11):08x}',
                          'usercode': f'{jtag.reg32(0x13):08x}',
                          'status': f'{jtag.reg32(0x41):08x}'}, indent=2))
