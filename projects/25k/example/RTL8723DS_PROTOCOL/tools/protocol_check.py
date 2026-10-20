#!/usr/bin/env python3
"""Exercise Capability, HELLO, GET_STATUS, retries, errors and BLE reconnect."""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import secrets
import struct

from bleak import BleakClient, BleakScanner
from protocol_v1 import SERVICE, CAPABILITY, COMMAND, RESPONSE, STATUS, TRANSFER
from protocol_v1 import Reassembler, encode, decode, fragments


async def connection_test(device, record, negatives):
    queue = asyncio.Queue()
    reassembler = Reassembler()
    nonce = secrets.randbits(64) or 1
    token = 1
    record['session_nonce'] = f'{nonce:016x}'
    record['commands'] = []

    def notification(_char, value):
        try:
            message = reassembler.feed(value)
            if message is not None:
                queue.put_nowait(message)
        except ValueError as error:
            queue.put_nowait(error)

    async with BleakClient(device, timeout=20) as client:
        service = client.services.get_service(SERVICE)
        if service is None:
            raise ValueError('Business service not discovered')
        chars = {uuid: service.get_characteristic(uuid) for uuid in
                 [CAPABILITY, COMMAND, RESPONSE, STATUS, TRANSFER]}
        if any(char is None for char in chars.values()):
            raise ValueError('Incomplete v1 GATT database')
        for uuid, required in [(CAPABILITY, {'read'}), (COMMAND, {'write'}),
                               (RESPONSE, {'notify'}), (STATUS, {'read', 'notify'}),
                               (TRANSFER, {'notify'})]:
            if not required.issubset(chars[uuid].properties):
                raise ValueError('Characteristic properties: ' + uuid)
        cap = bytes(await client.read_gatt_char(chars[CAPABILITY]))
        if len(cap) != 20:
            raise ValueError('Capability length')
        major, limit, maximum, boot, capabilities, chunk, window, slots = struct.unpack('<BBHQIHBB', cap)
        if (major, limit, maximum, window) != (1, 20, 512, 1) or (capabilities,chunk,slots) not in [(0,0,0),(0x68,256,1)] or boot == 0:
            raise ValueError('Unexpected minimum-test Capability')
        record['capability'] = {'raw': cap.hex(), 'major': major, 'value_limit': limit,
                                'max_logical_message': maximum, 'boot_id': f'{boot:016x}',
                                'capabilities': capabilities, 'max_pcm_chunk': chunk,
                                'max_transfer_window': window, 'recording_slots': slots}
        summary = bytes(await client.read_gatt_char(chars[STATUS]))
        if len(summary) != 20 or (summary[16] not in range(6) or summary[17:] != bytes([255,255,8])):
            raise ValueError('Status summary must mark unknown mode/voices and open test window')
        record['status_summary'] = summary.hex()
        await client.start_notify(chars[RESPONSE], notification)

        async def send(raw, duplicate_first=False):
            nonlocal token
            pieces = list(fragments(raw, token))
            token = (token + 1) & 65535
            for index, piece in enumerate(pieces):
                await client.write_gatt_char(chars[COMMAND], piece, response=True)
                if index == 0 and duplicate_first:
                    await client.write_gatt_char(chars[COMMAND], piece, response=True)

        async def exchange(op, request_id, payload=b'', status=0, duplicate_first=False):
            raw = encode(op, request_id, nonce, payload)
            await send(raw, duplicate_first)
            response = await asyncio.wait_for(queue.get(), 3)
            if isinstance(response, Exception):
                raise response
            decoded = decode(response)
            if (decoded['opcode'], decoded['request_id'], decoded['session_nonce'], decoded['status']) != (op, request_id, nonce, status):
                raise ValueError('Response identity/status mismatch: ' + repr(decoded))
            record['commands'].append({'opcode': op, 'request_id': request_id,
                                       'request': raw.hex(), 'response': response.hex(),
                                       'status': status, 'response_payload': decoded['payload'].hex()})
            print(f'command={op:02x} id={request_id} status={status:02x} bytes={len(response)}', flush=True)
            return response, decoded['payload']

        try:
            hello, payload = await exchange(1, 1, struct.pack('<HH', 1, 0))
            if len(payload) != 20 or struct.unpack_from('<QII', payload) != (boot, capabilities, 1):
                raise ValueError('HELLO capability/boot/revision')
            repeated, _ = await exchange(1, 1, struct.pack('<HH', 1, 0))
            if repeated != hello:
                raise ValueError('HELLO replay was not byte-identical')
            first, payload = await exchange(2, 2, duplicate_first=True)
            if len(payload) != 64 or int.from_bytes(payload[8:12], 'little') != (4 if capabilities else 0) or payload[44:48] != bytes([8, 0, 0, 0]):
                raise ValueError('GET_STATUS validity mask/flags')
            record['status_snapshot_id'] = int.from_bytes(payload[:4], 'little')
            repeated, _ = await exchange(2, 2)
            if repeated != first:
                raise ValueError('GET_STATUS replay changed snapshot')
            if negatives:
                await exchange(0x7F, 2, status=0x86)  # cached ID, different bytes
                await exchange(0x7F, 3, status=0x80)  # unsupported does not consume ID
                await exchange(2, 3)
                raw = bytearray(encode(2, 99, nonce))
                raw[-1] ^= 1
                await send(raw)
                try:
                    unexpected = await asyncio.wait_for(queue.get(), 0.35)
                except asyncio.TimeoutError:
                    record['bad_crc_silently_rejected'] = True
                else:
                    raise ValueError('Bad CRC produced a response: ' + repr(unexpected))
                # Invalid second fragment with no FIRST must fail at ATT.
                piece = struct.pack('<BHBBB', 0xB1, token, 1, 2, 1) + b'X'
                token = (token + 1) & 65535
                try:
                    await client.write_gatt_char(chars[COMMAND], piece, response=True)
                except Exception as error:
                    record['out_of_order_att_rejected'] = str(error)
                else:
                    raise ValueError('Out-of-order fragment was accepted')
                await exchange(2, 4)
            record['passed'] = True
        finally:
            await client.stop_notify(chars[RESPONSE])
    record['disconnected'] = True
    return boot


async def check(args, result):
    result['connections'] = []
    first_boot = None
    for index in range(args.connections):
        advertisement = {}

        def matches(device, adv):
            if adv.local_name == 'GW25K-PROTO' and SERVICE in [u.lower() for u in adv.service_uuids]:
                advertisement.update({'name': adv.local_name, 'service_uuids': adv.service_uuids,
                                      'device_id': device.address})
                return True
            return False

        device = await BleakScanner.find_device_by_filter(matches, timeout=args.scan_seconds)
        if device is None:
            raise ValueError('GW25K-PROTO business advertisement not found, connection ' + str(index + 1))
        record = {'advertisement': advertisement, 'passed': False}
        result['connections'].append(record)
        boot = await connection_test(device, record, negatives=index == 0)
        if first_boot is None:
            first_boot = boot
        elif boot != first_boot:
            raise ValueError('boot_id changed during an ordinary BLE reconnect')
    result['boot_id'] = f'{first_boot:016x}'
    result['automatic_reconnect_passed'] = args.connections >= 2
    result['passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--connections', type=int, choices=(1, 2), default=2)
    parser.add_argument('--scan-seconds', type=float, default=30)
    args = parser.parse_args()
    result = {'started_at': datetime.now().astimezone().isoformat(), 'passed': False}
    try:
        asyncio.run(check(args, result))
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result['finished_at'] = datetime.now().astimezone().isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
