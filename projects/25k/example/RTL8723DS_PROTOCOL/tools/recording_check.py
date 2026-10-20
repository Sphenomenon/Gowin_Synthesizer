#!/usr/bin/env python3
"""Independent real BLE recording/transfer checker; compares every PCM byte to the source WAV."""
import argparse, asyncio, json, secrets, struct, time, wave, zlib
from datetime import datetime
from pathlib import Path
from bleak import BleakClient, BleakScanner
from protocol_v1 import SERVICE,CAPABILITY,COMMAND,RESPONSE,TRANSFER,encode,decode,fragments,Reassembler

class Session:
    def __init__(self,write_command=False,observe=False,compact=False,bulk=False):
        self.write_command=write_command;self.direct=False;self.long_data=False;self.extended_data=False;self.lossless=False;self.second=False
        self.observe=observe;self.notifications=[]
        self.client=None;self.nonce=secrets.randbits(64) or 1;self.rid=1;self.token=1
        self.queues={u:asyncio.Queue() for u in [RESPONSE,TRANSFER]}
        self.assemblers={u:Reassembler(allow_compact=compact and u==TRANSFER) for u in self.queues}
        self.commands=[]
    async def connect(self):
        device=await BleakScanner.find_device_by_filter(lambda d,a:a.local_name=='GW25K-PROTO' and SERVICE in a.service_uuids,timeout=25)
        if device is None:raise RuntimeError('GW25K-PROTO not found')
        self.client=BleakClient(device,timeout=20);await self.client.connect()
        cap=bytes(await self.client.read_gatt_char(CAPABILITY))
        major,value,maximum,self.boot,flags,chunk,window,slots=struct.unpack('<BBHQIHBB',cap)
        assert (major,value,maximum,flags,chunk,window,slots)==(1,20,512,0x68,256,1,1)
        for uuid in self.queues:
            def receive(_c,value,u=uuid):
                if self.observe:self.notifications.append({'characteristic':u,'time':time.perf_counter(),'fragment':bytes(value).hex()})
                raw=self.assemblers[u].feed(value)
                if raw is not None:self.queues[u].put_nowait(raw)
            await self.client.start_notify(uuid,receive)
        _,hello,_=await self.exchange(1,struct.pack('<HH',1,0))
        assert struct.unpack_from('<QII',hello['payload'])==(self.boot,0x68,1)
    async def close(self):
        if self.client:await self.client.disconnect()
    async def exchange(self,op,payload=b'',status=0,data=False,rid=None):
        if rid is None:rid=self.rid;self.rid+=1
        raw=encode(op,rid,self.nonce,payload)
        token=self.token;self.token=(self.token+1)&65535
        for part in fragments(raw,token):await self.client.write_gatt_char(COMMAND,part,response=not self.write_command)
        transfer=None
        receipt_only=data and self.direct and status==0
        if receipt_only:
            transfer=decode(await asyncio.wait_for(self.queues[TRANSFER].get(),5),8160 if self.extended_data else 1020 if self.long_data else 512)
            assert (transfer['opcode'],transfer['request_id'],transfer['session_nonce'],transfer['status'])==(0xd0,rid,self.nonce,0)
            wire_payload=transfer['payload']
            tid,boot,record,at,n,reserved,crc=struct.unpack_from('<IQIIHHI',wire_payload)
            from pcm_lossless import decode as decode_pcm
            allowed=self.lossless and op in (0x3e,0x3f,0x41,0x42)
            if not allowed:assert reserved==0
            if reserved==11:assert self.second and op in (0x41,0x42)
            pcm=decode_pcm(wire_payload[28:],n,reserved,allow_second=self.second and op in (0x41,0x42))
            transfer['payload']=wire_payload[:22]+b'\0\0'+wire_payload[24:28]+pcm
            transfer['wire_payload']=wire_payload
            expected_tid,expected_at,expected_n,zero=struct.unpack_from('<IIHH',payload)
            assert (tid,at,n,reserved)==(expected_tid,expected_at,expected_n,reserved)
            assert boot==self.boot and zlib.crc32(transfer['payload'][28:])==crc
            response=encode(op,rid,self.nonce,struct.pack('<IIHH',tid,at,n,0))
            result=decode(response)
        else:
            response=await asyncio.wait_for(self.queues[RESPONSE].get(),5)
            result=decode(response)
            assert (result['opcode'],result['request_id'],result['session_nonce'],result['status'])==(op,rid,self.nonce,status),result
            if data:
                transfer=decode(await asyncio.wait_for(self.queues[TRANSFER].get(),5),8160 if self.extended_data else 1020 if self.long_data else 512)
                assert (transfer['opcode'],transfer['request_id'],transfer['session_nonce'],transfer['status'])==(0xd0,rid,self.nonce,0)
        if status == 0 and op in (0x30,0x36,0x37,0x38,0x39,0x3b,0x3c,0x3d,0x40):
            if op in (0x38,0x39,0x3b,0x3c,0x3d,0x40):
                assert len(result['payload']) == 24 and result['payload'][22:] == b'\0\0'
                value_limit = struct.unpack_from('<H', result['payload'],20)[0]
            else:value_limit = None
            self.direct=op in (0x39,0x3b,0x3c,0x3d,0x40);self.long_data=op==0x3b;self.extended_data=op in (0x3c,0x3d,0x40);self.lossless=op in (0x3d,0x40);self.second=op==0x40
            self.assemblers[TRANSFER] = Reassembler(allow_compact=op==0x37,bulk_value_limit=value_limit,long_data=self.long_data,extended_data=self.extended_data)
        self.commands.append({'opcode':op,'id':rid,'status':status,'request':raw.hex(),'response':response.hex(),'response_synthesized_from_data':receipt_only,
                              **({'data':transfer['payload'].hex(),**({'wire_data':transfer['wire_payload'].hex()} if 'wire_payload' in transfer else {})} if transfer else {})})
        return rid,result,transfer
    async def info(self):
        _,r,_=await self.exchange(0x22,struct.pack('<I',0));b=r['payload'];assert len(b)==48
        fields=struct.unpack('<QIBBBBIIIIIHHII',b)
        keys=['boot','id','state','format','channels','flags','rate','frames','bytes','capacity','crc','reason','detail','operation','reserved']
        return dict(zip(keys,fields))
    async def task(self,operation):
        for _ in range(30):
            _,r,_=await self.exchange(4,struct.pack('<I',operation))
            b=r['payload'];assert len(b)==20 and struct.unpack_from('<I',b)[0]==operation
            if b[9]==2:assert b[10]==0;return
            await asyncio.sleep(.05)
        raise TimeoutError('Operation not completed')

async def check(args,report):
    chunk=8112 if (args.extended or args.lossless or args.second) else 972 if args.long else 460 if args.wide or args.compact or args.bulk or args.direct else 256
    s=Session(args.write_command,compact=args.compact,bulk=args.bulk);report['chunk']=chunk;report['write_command']=args.write_command;report['ack_read']=args.ack_read;sessions=report['sessions']=[];sessions.append(s.commands)
    with wave.open(str(args.reference)) as f:reference=f.readframes(f.getnframes())
    try:
        await s.connect();info=await s.info()
        report['initial_info']=dict(info)
        if args.previous_boot is not None:
            assert s.boot!=args.previous_boot and info['state']==0 and info['id']==0
            await s.exchange(0x30,struct.pack('<QII',args.previous_boot,args.previous_record,0),status=0x88)
            report['previous_boot_object_rejected']=True
        if info['state'] in [4,5]:await s.exchange(0x23,struct.pack('<QI',s.boot,info['id']))
        _,start,_=await s.exchange(0x20,struct.pack('<BBHI',1,0,0,args.frames),status=1)
        operation,recording=struct.unpack('<II',start['payload'])
        await s.task(operation)
        for _ in range(30):
            info=await s.info()
            if info['state']==4:break
            await asyncio.sleep(.05)
        assert info['state']==4 and info['id']==recording and info['flags']&2
        assert info['frames']==args.frames and info['bytes']==args.frames*4 and info['rate']==48000
        expected=reference[:info['bytes']];assert info['crc']==zlib.crc32(expected)
        report['recording']=info
        await s.exchange(0x30,struct.pack('<QII',s.boot^1,recording,0),status=0x88)
        pcm=bytearray();offset=0
        async def open_transfer():
            _,r,_=await s.exchange(0x40 if args.second else 0x3d if args.lossless else 0x3c if args.extended else 0x3b if args.long else (0x39 if args.direct else (0x38 if args.bulk else (0x37 if args.compact else (0x36 if args.wide else 0x30)))),struct.pack('<QII',s.boot,recording,offset))
            tid,size,crc,accepted,reported_chunk,window,_=struct.unpack_from('<IIIIHBB',r['payload'])
            assert (size,crc,accepted,reported_chunk,window)==(info['bytes'],info['crc'],offset,chunk,1)
            return tid
        tid=await open_transfer();previous_crc=None;combined_replay=False;combined_invalid=False
        await s.exchange(0x23,struct.pack('<QI',s.boot,recording),status=0x82)
        await s.exchange(0x33,struct.pack('<II',tid,info['crc']),status=0x8d)
        while offset<info['bytes']:
            n=min(chunk,info['bytes']-offset)
            payload=struct.pack('<IIHH',tid,offset,n,0)
            op=(0x42 if args.second else 0x3f if args.lossless else 0x35) if args.ack_read and previous_crc is not None else (0x41 if args.second else 0x3e if args.lossless else 0x31)
            if op in (0x35,0x3f,0x42):
                if not combined_invalid:
                    await s.exchange(op,payload+struct.pack('<I',previous_crc^1),status=0x8d)
                    await s.exchange(op,struct.pack('<IIHHI',tid,offset,chunk+4,0,previous_crc),status=0x89)
                    combined_invalid=True
                payload+=struct.pack('<I',previous_crc)
            request,reply,data=await s.exchange(op,payload,data=True)
            assert struct.unpack('<IIHH',reply['payload'])==(tid,offset,n,0)
            b=data['payload'];t,boot,rid,at,length,reserved,crc=struct.unpack_from('<IQIIHHI',b)
            assert (t,boot,rid,at,length,reserved)==(tid,s.boot,recording,offset,n,0)
            assert b[28:]==expected[offset:offset+n] and zlib.crc32(b[28:])==crc
            if offset==0:
                _,again,again_data=await s.exchange(op,payload,data=True,rid=request)
                assert again['payload']==reply['payload'] and again_data['payload']==b
                await s.exchange(0x32,struct.pack('<III',tid,offset+n,crc^1),status=0x8d)
            if op in (0x35,0x3f,0x42) and not combined_replay:
                _,again,again_data=await s.exchange(op,payload,data=True,rid=request)
                assert again['payload']==reply['payload'] and again_data['payload']==b
                combined_replay=True
            ack=struct.pack('<III',tid,offset+n,crc)
            flush=not args.ack_read or offset==0 or offset+n in (chunk*2,chunk*4,info['bytes'])
            if flush:
                await s.exchange(0x32,ack)
                if offset==0:await s.exchange(0x32,ack)
                previous_crc=None
            else:previous_crc=crc
            pcm.extend(b[28:]);offset+=n
            if offset==chunk*2:
                await s.exchange(0x34,struct.pack('<I',tid));tid=await open_transfer()
            if offset==chunk*4:
                old_boot=s.boot;await s.close();s=Session(args.write_command,compact=args.compact,bulk=args.bulk);sessions.append(s.commands);await s.connect()
                assert s.boot==old_boot;again=await s.info();assert again['id']==recording and again['crc']==info['crc']
                tid=await open_transfer();report['reconnect_resume']=True
            if offset%4096==0:print(f'independent PCM {offset}/{info["bytes"]}',flush=True)
        assert pcm==expected and zlib.crc32(pcm)==info['crc']
        await s.exchange(0x31,struct.pack('<IIHH',tid,offset,4,0),status=0x89)
        await s.exchange(0x33,struct.pack('<II',tid,info['crc']))
        out=args.output.with_suffix('.wav')
        with wave.open(str(out),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000);f.writeframes(pcm)
        report['wav']=str(out);report['pcm_matches_reference']=True
        if args.ack_read:
            assert combined_replay and combined_invalid
            report['combined_replay_verified']=True;report['combined_invalid_crc_and_range_rejected']=True
        await s.exchange(0x23,struct.pack('<QI',s.boot,recording));assert (await s.info())['state']==0
        # A second recording exercises user stop and nonzero committed-prefix CRC.
        _,start,_=await s.exchange(0x20,struct.pack('<BBHI',1,0,0,0),status=1)
        operation,recording=struct.unpack('<II',start['payload']);await s.task(operation)
        _,stop,_=await s.exchange(0x21,struct.pack('<QI',s.boot,recording),status=1)
        operation,_=struct.unpack('<II',stop['payload']);await s.task(operation)
        stopped=await s.info()
        assert stopped['state']==4 and stopped['reason']==1 and 0<stopped['frames']<48000
        assert stopped['crc']==zlib.crc32(reference[:stopped['bytes']])
        report['manual_stop']=stopped
        await s.exchange(0x23,struct.pack('<QI',s.boot,recording))
        report['passed']=True
    finally:await s.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',type=Path,default=Path('audio/test_tone_1s.wav'))
    p.add_argument('--frames',type=int,default=4800)
    p.add_argument('--write-command',action='store_true')
    p.add_argument('--ack-read',action='store_true')
    p.add_argument('--wide',action='store_true')
    p.add_argument('--compact',action='store_true')
    p.add_argument('--bulk',action='store_true')
    p.add_argument('--extended',action='store_true')
    p.add_argument('--lossless',action='store_true')
    p.add_argument('--second',action='store_true')
    p.add_argument('--long',action='store_true');p.add_argument('--direct',action='store_true')
    p.add_argument('--previous-boot',type=lambda v:int(v,0))
    p.add_argument('--previous-record',type=int,default=1)
    args=p.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    report={'started_at':datetime.now().astimezone().isoformat(),'passed':False}
    try:asyncio.run(check(args,report))
    except Exception as e:report['error']=repr(e)
    report['finished_at']=datetime.now().astimezone().isoformat()
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='sessions'},ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
