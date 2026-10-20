#!/usr/bin/env python3
"""Verify 256/460-byte transfer changes at existing, non-chunk-aligned checkpoints."""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import struct
import wave
import zlib

from recording_check import Session
from protocol_v1 import TRANSFER


async def check(report):
    session = Session(write_command=True, observe=True, compact=True)
    report['sessions'] = [session.commands]
    with wave.open('audio/test_tone_1s.wav') as source:
        reference = source.readframes(source.getnframes())
    try:
        await session.connect()
        info = await session.info()
        if info['state'] in (4, 5):
            await session.exchange(0x23, struct.pack('<QI', session.boot, info['id']))
        _, started, _ = await session.exchange(0x20, struct.pack('<BBHI', 1, 0, 0, 16000), status=1)
        await session.task(struct.unpack_from('<I', started['payload'])[0])
        for _ in range(30):
            info = await session.info()
            if info['state'] == 4:
                break
            await asyncio.sleep(.05)
        assert info['state'] == 4 and info['bytes'] == 64000
        offset = 0
        pcm = bytearray()
        report['transfers'] = []
        for opcode, chunk in [(0x30, 256), (0x40, 8112), (0x3d, 8112), (0x3c, 8112), (0x3b, 972), (0x39, 460), (0x38, 460), (0x37, 460), (0x36, 460), (0x40, 8112), (0x3d, 8112), (0x3c, 8112), (0x3b, 972), (0x30, 256)]:
            _, opened, _ = await session.exchange(opcode, struct.pack('<QII', session.boot, info['id'], offset))
            transfer, size, crc, accepted, maximum, window, reserved = struct.unpack_from('<IIIIHBB', opened['payload'])
            assert (size, crc, accepted, maximum, window, reserved) == (info['bytes'], info['crc'], offset, chunk, 1, 0)
            session.notifications.clear()
            _, reply, data = await session.exchange(0x41 if opcode==0x40 else 0x3e if opcode==0x3d else 0x31, struct.pack('<IIHH', transfer, offset, chunk, 0), data=True)
            assert struct.unpack('<IIHH', reply['payload']) == (transfer, offset, chunk, 0)
            block = data['payload']
            tid, boot, recording, at, length, reserved, block_crc = struct.unpack_from('<IQIIHHI', block)
            assert (tid, boot, recording, at, length, reserved) == (transfer, session.boot, info['id'], offset, chunk, 0)
            assert block[28:] == reference[offset:offset + chunk] and zlib.crc32(block[28:]) == block_crc
            values = [bytes.fromhex(n['fragment']) for n in session.notifications if n['characteristic'] == TRANSFER]
            capacity = struct.unpack_from('<H', opened['payload'],20)[0]-4 if opcode in (0x38,0x39,0x3b,0x3c,0x3d,0x40) else 16 if opcode == 0x37 else 14
            assert len(values) == (len(data.get("wire_payload",block)) + 20 + capacity - 1) // capacity
            assert all(v[0] == (0xb3 if opcode in (0x38,0x39,0x3b,0x3c,0x3d,0x40) else 0xb2 if opcode == 0x37 else 0xb1) for v in values)
            pcm.extend(block[28:])
            report['transfers'].append({'opcode': opcode, 'max_chunk': maximum, 'offset': offset, 'bytes': chunk, 'notifications': len(values)})
            offset += chunk
            await session.exchange(0x32, struct.pack('<III', transfer, offset, block_crc))
            await session.exchange(0x34, struct.pack('<I', transfer))
        assert pcm == reference[:offset]
        await session.exchange(0x23, struct.pack('<QI', session.boot, info['id']))
        assert (await session.info())['state'] == 0
        report.update(passed=True, pcm_bytes=offset, reference_matches=True,
                      old_checkpoint_resumed_with_wide=True, wide_checkpoint_resumed_with_legacy=True, compact_profile_switched_both_directions=True, bulk_profile_switched_both_directions=True,lossless_profile_switched_both_directions=True,second_profile_switched_both_directions=True)
    finally:
        await session.close()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
report = {'passed': False, 'started_at': datetime.now().astimezone().isoformat()}
try:
    asyncio.run(check(report))
except Exception as error:
    report['error'] = repr(error)
report['finished_at'] = datetime.now().astimezone().isoformat()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'sessions'}, indent=2))
raise SystemExit(0 if report['passed'] else 1)
