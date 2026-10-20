"""138K business protocol v1 wire codec (also used by the 25K smoke client)."""
import struct
import zlib

SERVICE = '9b6d0000-4c2a-4f87-9a31-138000000001'
CAPABILITY = SERVICE.replace('0000-', '0001-', 1)
COMMAND = SERVICE.replace('0000-', '0002-', 1)
RESPONSE = SERVICE.replace('0000-', '0003-', 1)
STATUS = SERVICE.replace('0000-', '0004-', 1)
TRANSFER = SERVICE.replace('0000-', '0005-', 1)


def encode(opcode, request_id, nonce, payload=b''):
    if not 0 < request_id < 2**32 or not 0 < nonce < 2**64 or len(payload) > 492:
        raise ValueError('Invalid request identity or payload length')
    body = struct.pack('<BBHIQ', opcode, 0, len(payload), request_id, nonce) + payload
    return body + struct.pack('<I', zlib.crc32(body))


def decode(raw, maximum=512):
    if maximum not in (512,1020,8160):raise ValueError("Invalid logical limit")
    if len(raw) < 20 or len(raw) > maximum:
        raise ValueError('Logical message length')
    op, status, size, request_id, nonce = struct.unpack_from('<BBHIQ', raw)
    if len(raw)>512 and (op!=0xd0 or status!=0):raise ValueError('Long DATA only')
    if len(raw) != 20 + size or size > maximum-20:
        raise ValueError('Declared logical message length')
    if zlib.crc32(raw[:-4]) != int.from_bytes(raw[-4:], 'little'):
        raise ValueError('Logical message CRC32')
    return {'opcode': op, 'status': status, 'request_id': request_id,
            'session_nonce': nonce, 'payload': raw[16:-4]}


def fragments(raw, token):
    if not 1 <= len(raw) <= 512 or not 0 <= token <= 65535:
        raise ValueError('Fragment source length or token')
    for index, offset in enumerate(range(0, len(raw), 14)):
        chunk = raw[offset:offset + 14]
        flags = (1 if index == 0 else 0) | (2 if offset + len(chunk) == len(raw) else 0)
        yield struct.pack('<BHBBB', 0xB1, token, index, flags, len(chunk)) + chunk


class Reassembler:
    def __init__(self, allow_compact=False, bulk_value_limit=None, long_data=False,extended_data=False):
        if (long_data or extended_data) and bulk_value_limit is None:raise ValueError("Long DATA requires B3")
        self.long_data=long_data or extended_data
        self.extended_data=extended_data
        if bulk_value_limit is not None and not 20 <= bulk_value_limit <= 244:
            raise ValueError('Invalid negotiated bulk ATT value limit')
        self.bulk_value_limit = bulk_value_limit
        self.allow_compact = allow_compact
        self.marker = None
        self.token = None
        self.index = 0
        self.buffer = bytearray()
        self.previous = None

    def feed(self, raw):
        raw = bytes(raw)
        try:
            bulk = raw[:1] == b'\xb3'
            compact = raw[:1] in (b'\xb2', b'\xb3')
            if compact:
                if not (self.bulk_value_limit is not None if bulk else self.allow_compact) or not 5 <= len(raw) <= (self.bulk_value_limit if bulk else 20):
                    raise ValueError('Compact fragment not negotiated or invalid length')
                marker, token, tag = struct.unpack_from('<BHB', raw)
                index, flags = tag & 63, tag >> 6
                size, header, capacity, maximum = len(raw) - 4, 4, (self.bulk_value_limit - 4 if bulk else 16), (63 if bulk and self.long_data else 31)
            else:
                if not 7 <= len(raw) <= 20:
                    raise ValueError('Fragment value length')
                marker, token, index, flags, size = struct.unpack_from('<BHBBB', raw)
                header, capacity, maximum = 6, 14, 36
                if marker != 0xB1 or flags & ~3 or len(raw) != size + header:
                    raise ValueError('Fragment header')
            if not 1 <= size <= capacity or index > maximum or bool(flags & 1) != (index == 0) or not flags & 2 and size != capacity:
                raise ValueError('Fragment index/flags/length')
            if self.previous == raw:
                return None
            if self.previous is not None and raw[:1] == self.previous[:1] and raw[1:3] == self.previous[1:3] and (raw[3] & 63 if compact else raw[3]) == (self.previous[3] & 63 if compact else self.previous[3]):
                raise ValueError('Conflicting fragment retry')
            if flags & 1:
                self.buffer.clear()
                self.token, self.index, self.marker = token, 0, marker
            if token != self.token or index != self.index or marker != self.marker:
                raise ValueError('Fragment ordering')
            if len(self.buffer) + size > (8160 if bulk and self.extended_data else 1020 if bulk and self.long_data else 512):
                raise ValueError('Logical message exceeds 512 bytes')
            self.buffer.extend(raw[header:])
            self.index += 1
            self.previous = raw
            if flags & 2:
                complete = bytes(self.buffer)
                self.token = None
                self.buffer.clear()
                return complete
            return None
        except ValueError:
            self.token = None
            self.previous = None
            self.buffer.clear()
            raise
