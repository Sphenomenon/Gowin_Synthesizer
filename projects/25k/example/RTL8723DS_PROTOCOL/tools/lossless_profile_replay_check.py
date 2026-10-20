#!/usr/bin/env python3
"""Verify cached lossless READ cannot leak into a reopened legacy transfer."""
import argparse,asyncio,json,struct,wave,zlib
from pathlib import Path
from recording_check import Session
from protocol_v1 import TRANSFER
async def run(report):
 s=Session(write_command=True);report['commands']=s.commands
 with wave.open('audio/test_tone_1s.wav') as f:ref=f.readframes(f.getnframes())
 try:
  await s.connect();info=await s.info()
  if info['state'] in (4,5):await s.exchange(0x23,struct.pack('<QI',s.boot,info['id']))
  _,r,_=await s.exchange(0x20,struct.pack('<BBHI',1,0,0,4800),status=1);await s.task(struct.unpack_from('<I',r['payload'])[0])
  while True:
   info=await s.info()
   if info['state']==4:break
   await asyncio.sleep(.1)
  _,r,_=await s.exchange(0x3d,struct.pack('<QII',s.boot,info['id'],0));tid=struct.unpack_from('<I',r['payload'])[0]
  original=struct.pack('<IIHH',tid,0,8112,0);rid,_,d=await s.exchange(0x3e,original,data=True)
  d_first=d['payload'];wire_first=d['wire_payload'];assert d_first[28:]==ref[:8112];crc=zlib.crc32(ref[:8112])
  await s.exchange(0x32,struct.pack('<III',tid,8112,crc));await s.exchange(0x34,struct.pack('<I',tid))
  _,r,_=await s.exchange(0x3c,struct.pack('<QII',s.boot,info['id'],8112));legacy=struct.unpack_from('<I',r['payload'])[0]
  await s.exchange(0x3e,original,status=0x8d,rid=rid)
  try:await asyncio.wait_for(s.queues[TRANSFER].get(),.3);raise AssertionError('Long DATA leaked into legacy profile')
  except asyncio.TimeoutError:pass
  _,_,d=await s.exchange(0x31,struct.pack('<IIHH',legacy,8112,460,0),data=True)
  assert d['payload'][28:]==ref[8112:8572]
  await s.exchange(0x32,struct.pack('<III',legacy,8572,zlib.crc32(ref[8112:8572])));await s.exchange(0x34,struct.pack('<I',legacy))
  _,r,_=await s.exchange(0x3d,struct.pack('<QII',s.boot,info['id'],8572));again_tid=struct.unpack_from('<I',r['payload'])[0]
  _,_,replay=await s.exchange(0x3e,original,rid=rid,data=True);assert replay['payload']==d_first and replay['wire_payload']==wire_first
  _,_,fresh=await s.exchange(0x31,struct.pack('<IIHH',again_tid,8572,8112,0),data=True);assert fresh['payload'][28:]==ref[8572:16684]
  await s.exchange(0x32,struct.pack('<III',again_tid,16684,zlib.crc32(ref[8572:16684])));await s.exchange(0x34,struct.pack('<I',again_tid));await s.exchange(0x23,struct.pack('<QI',s.boot,info['id']))
  report.update(passed=True,cached_long_read_rejected_in_legacy=True,no_long_data_on_legacy=True,legacy_cursor_unchanged=True,legacy_read_matches=True,original_cache_success_preserved=True,encoded_replay_identical=True,long_replay_did_not_move_current_cursor=True)
 finally:await s.close()
p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();r={'passed':False}
try:asyncio.run(run(r))
except Exception as e:r['error']=repr(e)
a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='commands'},indent=2));raise SystemExit(0 if r['passed'] else 1)
