#!/usr/bin/env python3
"""Run the Android ProtocolSession against the physical 25K through a GATT-only bridge.

The bridge neither constructs nor validates logical messages. Kotlin from the APP
performs HELLO/GET_STATUS, fragmentation, CRC, nonce checks and unsupported errors.
Requires RealBoardSessionTest from the matching Android source bundle.
"""
import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys

from bleak import BleakClient, BleakScanner
from protocol_v1 import SERVICE, COMMAND


async def check(args, report):
    connections = report['connections'] = []
    tasks = set()

    async def bridge(reader, writer):
        record = {'operations': [], 'passed': False}
        connections.append(record)
        client = None

        def send(line):
            writer.write((line + '\n').encode())

        try:
            while line := await asyncio.wait_for(reader.readline(), 120):
                parts = line.decode().strip().split()
                op = parts[0]
                entry = {'operation': op, 'args': parts[1:]}
                record['operations'].append(entry)
                if op == 'CONNECT':
                    device = await BleakScanner.find_device_by_filter(
                        lambda d, a: a.local_name == 'GW25K-PROTO' and SERVICE in a.service_uuids,
                        timeout=25)
                    if device is None:
                        raise ValueError('GW25K-PROTO advertisement not found')
                    record['device'] = device.address
                    client = BleakClient(device, timeout=20)
                    await client.connect()
                    record['write_without_response']='write-without-response' in client.services.get_characteristic(COMMAND).properties
                    send('R')
                elif op == 'READ':
                    raw = bytes(await client.read_gatt_char(parts[1]))
                    entry['value'] = raw.hex()
                    send('R ' + raw.hex())
                elif op == 'SUBSCRIBE':
                    uuid = parts[1]

                    def notified(_char, raw, characteristic=uuid):
                        value = bytes(raw).hex()
                        record.setdefault('notifications', []).append({'uuid': characteristic, 'value': value})
                        send('N ' + characteristic + ' ' + value)
                    await client.start_notify(uuid, notified)
                    send('R')
                elif op == 'WRITE':
                    await client.write_gatt_char(COMMAND, bytes.fromhex(parts[1]), response=not record['write_without_response'])
                    record['writes'] = record.get('writes', 0) + 1
                    if record['writes'] % 200 == 0:
                        print(f"GATT connection {len(connections)}: {record['writes']} writes", flush=True)
                    send('R')
                else:
                    raise ValueError('Unknown bridge operation')
                await writer.drain()
            record['passed'] = client is not None
        except Exception as error:
            record['error'] = repr(error)
            if not writer.is_closing():
                send('E ' + str(error).replace('\n', ' '))
                await writer.drain()
        finally:
            if client:
                await client.disconnect()
            writer.close()
            await writer.wait_closed()

    def accept(reader, writer):
        task = asyncio.create_task(bridge(reader, writer))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    server = await asyncio.start_server(accept, '127.0.0.1', 0)
    env = dict(os.environ, GW25K_BLE_BRIDGE_PORT=str(server.sockets[0].getsockname()[1]))
    command = [str(args.gradle), args.task, '--tests', args.test, '--rerun-tasks', '--offline']
    report['gradle_command'] = command
    async with server:
        process = await asyncio.create_subprocess_exec(*command, cwd=args.android,
                    env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 900)
        except asyncio.TimeoutError:
            process.kill()
            output, _ = await process.communicate()
            raise TimeoutError('Gradle radio test exceeded 900 seconds')
        args.output.with_suffix('.gradle.log').write_bytes(output)
        report['returncode'] = process.returncode
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks), 30)
    report['passed'] = process.returncode == 0 and len(connections) == args.connections and all(x['passed'] for x in connections)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--android', required=True, type=Path)
    parser.add_argument('--gradle', type=Path, default=Path('/tmp/gw-android-tools/gradle-8.10.2/bin/gradle'))
    parser.add_argument('--task', default=':core:ble:testDebugUnitTest')
    parser.add_argument('--test', default='cn.gowin.control.ble.RealBoardSessionTest')
    parser.add_argument('--connections', type=int, default=2)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now().astimezone().isoformat(), 'passed': False,
              'scope': 'APP Kotlin session + codec over macOS BLE; not Android phone GATT/UI',
              'android_source': str(args.android.resolve())}
    try:
        asyncio.run(check(args, report))
    except Exception as error:
        report['error'] = repr(error)
    report['finished_at'] = datetime.now().astimezone().isoformat()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'connections'}, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
