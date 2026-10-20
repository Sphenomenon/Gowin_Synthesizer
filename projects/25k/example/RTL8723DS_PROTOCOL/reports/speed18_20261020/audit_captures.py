"""Offline raw notification audit; no BLE access or use of normalized DATA."""
import sys,json,wave,struct,zlib,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT/'tools'))
from protocol_v1 import Reassembler,decode,TRANSFER
from pcm_lossless import decode as decode_pcm
with wave.open(str(ROOT/'audio/test_tone_1s.wav')) as f:reference=f.readframes(f.getnframes())
def block(raw):
 m=decode(raw,8160);assert m['opcode']==0xd0 and m['status']==0
 b=m['payload'];tid,boot,record,offset,n,mode,crc=struct.unpack_from('<IQIIHHI',b)
 pcm=decode_pcm(b[28:],n,mode,allow_second=mode==11)
 assert pcm==reference[offset:offset+n] and zlib.crc32(pcm)==crc
 return dict(request=m['request_id'],nonce=m['session_nonce'],offset=offset,pcm=n,encoded=len(b)-28,codec=mode,wire_sha256=hashlib.sha256(raw).hexdigest())
rows=[]
for name in ['baseline_speed','speed_initial']+[f'{mode}_{i}' for i in (1,2,3) for mode in ('lossless','second')]+['speed_flash']:
 p=HERE/(name+'.json')
 if not p.exists():continue
 r=json.loads(p.read_text());assert r['passed'];assembler=Reassembler(bulk_value_limit=182,extended_data=True);blocks=[]
 for note in r['notifications']:
  if note['characteristic']!=TRANSFER:continue
  raw=assembler.feed(bytes.fromhex(note['fragment']))
  if raw is not None:blocks.append(block(raw))
 assert sum(b['pcm'] for b in blocks)==r['pcm_bytes']
 cursor=0
 for b in blocks:assert b['offset']==cursor;cursor+=b['pcm']
 if r.get('second'):assert all(b['codec']==11 for b in blocks)
 elif r.get('lossless'):assert all(b['codec']==10 for b in blocks)
 else:assert all(b['codec']==0 for b in blocks)
 rows.append(dict(file=p.name,blocks=blocks,encoded_bytes=sum(b['encoded'] for b in blocks)))
for name in ('kotlin_second_sram','kotlin_second_flash','kotlin_old_sram'):
 p=HERE/(name+'.json')
 if not p.exists():continue
 r=json.loads(p.read_text());assert r['passed'];all_blocks=[]
 for c in r['connections']:
  assembler=Reassembler(bulk_value_limit=182,extended_data=True)
  for note in c.get('notifications',[]):
   if note['uuid']!=TRANSFER:continue
   raw=assembler.feed(bytes.fromhex(note['value']))
   if raw is not None:all_blocks.append(block(raw))
 seen={};duplicates=0
 for b in all_blocks:
  key=b['nonce'],b['request']
  if key in seen:assert seen[key]==b['wire_sha256'];duplicates+=1
  else:seen[key]=b['wire_sha256']
 rows.append(dict(file=p.name,blocks=all_blocks,identical_replays=duplicates))
(HERE/'wire_audit.json').write_text(json.dumps(dict(passed=True,captures=rows),indent=2)+'\n');print('PASS',len(rows),'raw notification captures')
