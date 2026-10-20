#!/usr/bin/env python3
"""Measure physical v1 PCM download without compilation/recording time."""
import argparse,asyncio,json,struct,time,wave,zlib
from datetime import datetime
from pathlib import Path
from recording_check import Session

async def measure(args,report):
    s=Session(observe=args.observe,compact=args.compact,bulk=args.bulk)
    with wave.open('audio/test_tone_1s.wav') as f:reference=f.readframes(f.getnframes())
    try:
        await s.connect();info=await s.info()
        if info['state'] in (4,5):await s.exchange(0x23,struct.pack('<QI',s.boot,info['id']))
        _,r,_=await s.exchange(0x20,struct.pack('<BBHI',1,0,0,0),status=1)
        await s.task(struct.unpack_from('<I',r['payload'])[0])
        while True:
            info=await s.info()
            if info['state']==4:break
            await asyncio.sleep(.1)
        report['recording']=info
        _,r,_=await s.exchange(0x40 if args.second else 0x3d if args.lossless else 0x3c if args.extended else 0x3b if args.long else (0x39 if args.direct else (0x38 if args.bulk else (0x37 if args.compact else (0x36 if args.chunk>256 else 0x30)))),struct.pack('<QII',s.boot,info['id'],0))
        tid=struct.unpack_from('<I',r['payload'])[0]
        assert struct.unpack_from('<H',r['payload'],16)[0]>=args.chunk
        report['long']=(args.long or args.extended or args.lossless or args.second);report['direct']=args.direct or (args.long or args.extended or args.lossless or args.second);report['bulk']=args.bulk or args.direct or (args.long or args.extended or args.lossless or args.second);report['bulk_value_limit']=struct.unpack_from('<H',r['payload'],20)[0] if args.bulk or args.direct or (args.long or args.extended or args.lossless or args.second) else None
        report['lossless']=args.lossless or args.second;report['second']=args.second;report['chunk']=args.chunk;report['compact']=args.compact
        report['write_command']=args.write_command
        report['ack_read']=args.ack_read
        report['command_properties']=s.client.services.get_characteristic('9b6d0002-4c2a-4f87-9a31-138000000001').properties
        writes=[];original=s.client.write_gatt_char
        async def timed_write(*a,**kw):
            t=time.perf_counter();kw['response']=not args.write_command;v=await original(*a,**kw);writes.append(time.perf_counter()-t);return v
        s.client.write_gatt_char=timed_write
        s.notifications.clear()
        pcm=bytearray();blocks=[];previous_crc=None;limit=min(info['bytes'],args.pcm_bytes or args.blocks*args.chunk);start=time.perf_counter()
        for offset in range(0,limit,args.chunk):
            t=time.perf_counter();n=min(args.chunk,limit-offset)
            op=(0x42 if args.second else 0x3f if args.lossless else 0x35) if args.ack_read and previous_crc is not None else (0x41 if args.second else 0x3e if args.lossless else 0x31)
            payload=struct.pack('<IIHH',tid,offset,n,0)+(struct.pack('<I',previous_crc) if op in (0x35,0x3f,0x42) else b'')
            _,_,data=await s.exchange(op,payload,data=True)
            got=time.perf_counter();b=data['payload'];crc=struct.unpack_from('<I',b,24)[0]
            assert b[28:]==reference[offset:offset+n] and zlib.crc32(b[28:])==crc
            previous_crc=crc
            if not args.ack_read or offset+n>=limit:await s.exchange(0x32,struct.pack('<III',tid,offset+n,crc))
            end=time.perf_counter()
            pcm.extend(b[28:]);blocks.append({'read_data_s':got-t,'ack_s':end-got})
            if len(blocks)%32==0:print(f'{len(pcm)} PCM bytes / {end-start:.2f}s',flush=True)
        elapsed=time.perf_counter()-start
        await s.exchange(0x34,struct.pack('<I',tid))
        await s.exchange(0x23,struct.pack('<QI',s.boot,info['id']))
        report.update(passed=True,pcm_bytes=len(pcm),transfer_seconds=elapsed,bytes_per_second=len(pcm)/elapsed,
                      block_timings=blocks,write_seconds=writes,reference_matches=True)
        if args.observe:report['notifications']=[dict(n,time=n['time']-start) for n in s.notifications]
    finally:await s.close()

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--extended',action='store_true');p.add_argument('--lossless',action='store_true');p.add_argument('--second',action='store_true');p.add_argument('--long',action='store_true');p.add_argument('--direct',action='store_true');p.add_argument('--bulk',action='store_true');p.add_argument('--compact',action='store_true');p.add_argument('--blocks',type=int,default=32);p.add_argument('--write-command',action='store_true');p.add_argument('--ack-read',action='store_true');p.add_argument('--observe',action='store_true');p.add_argument('--chunk',type=int,choices=(256,456,460,964,972,8112),default=256);p.add_argument('--pcm-bytes',type=int);p.add_argument('--output',required=True,type=Path)
a=p.parse_args();r={'started_at':datetime.now().astimezone().isoformat(),'passed':False}
try:asyncio.run(measure(a,r))
except Exception as e:r['error']=repr(e)
r['finished_at']=datetime.now().astimezone().isoformat();a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ('write_seconds','block_timings','notifications')},indent=2))
raise SystemExit(0 if r['passed'] else 1)
