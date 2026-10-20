"""Audit integration simulation dumps using independent PCM decoder/WAV."""
from pathlib import Path
import argparse
import sys,wave,struct,json,zlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from pcm_lossless import decode
with wave.open(str(ROOT/'audio/test_tone_1s.wav')) as f:pcm=f.readframes(f.getnframes())
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'reports/speed17_20261020/integration_audit.json');parser.add_argument('--second',action='store_true');args=parser.parse_args()
rows=[]
for p in sorted(Path('/private/tmp').glob('gw25k-lossless-block-*.hex')):
 b=bytes.fromhex(p.read_text());assert zlib.crc32(b[:-4])==int.from_bytes(b[-4:],'little')
 tid,boot,record,offset,n,mode,crc=struct.unpack_from('<IQIIHHI',b,16)
 got=decode(b[44:-4],n,mode,allow_second=args.second);assert got==pcm[offset:offset+n] and zlib.crc32(got)==crc
 rows.append(dict(file=p.name,offset=offset,pcm=n,encoded=len(b)-48,mode=mode))
assert len(rows)>=9 and any(r['mode'] in ((10,11) if args.second else (10,)) for r in rows) and any(r['mode']==0 for r in rows)
args.output.write_text(json.dumps(dict(passed=True,blocks=rows),indent=2)+'\n');print('PASS',len(rows),'raw/encoded exact PCM blocks')
