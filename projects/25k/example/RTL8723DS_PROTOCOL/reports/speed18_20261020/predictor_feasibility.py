"""Offline predictor orders and fixed Rice costs; no deployed wire claim."""
import json,struct,wave,random,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]

def encode(pcm,order,k):
 last=[0,0];before=[0,0];bits=[]
 for i,(x,) in enumerate(struct.iter_unpack('<H',pcm)):
  ch=i&1;p=last[ch] if order==1 else 2*last[ch]-before[ch]
  d=(x-p)&65535
  if d&32768:d-=65536
  v=(d<<1)^(d>>15);before[ch]=last[ch];last[ch]=x;q=v>>k
  if q>=15:bits.extend([1]*15);count=16
  else:bits.extend([1]*q+[0]);count=k
  bits.extend((v>>b)&1 for b in range(count-1,-1,-1))
 bits.extend([0]*(-len(bits)%8))
 return bytes(sum(bits[a+b]<<(7-b) for b in range(8)) for a in range(0,len(bits),8))

def decode(raw,n,order,k):
 at=0;last=[0,0];before=[0,0];pcm=bytearray()
 def bit():
  nonlocal at
  if at>=len(raw)*8:raise ValueError('truncated')
  v=(raw[at//8]>>(7-at%8))&1;at+=1;return v
 for i in range(n//2):
  q=0
  while q<15 and bit():q+=1
  v=0
  for _ in range(16 if q==15 else k):v=(v<<1)|bit()
  if q==15:
   if v>>k<15:raise ValueError('escape')
  else:v|=q<<k
  ch=i&1;p=last[ch] if order==1 else 2*last[ch]-before[ch]
  x=(p+((v>>1)^-(v&1)))&65535
  before[ch]=last[ch];last[ch]=x;pcm+=struct.pack('<H',x)
 if len(raw)*8-at>=8:raise ValueError('trailing')
 while at<len(raw)*8:
  if bit():raise ValueError('padding')
 return bytes(pcm)

def main():
 with wave.open(str(ROOT/'audio/test_tone_1s.wav')) as f:pcm=f.readframes(f.getnframes())
 rows=[];rng=random.Random(0x2518)
 for order in (1,2):
  for k in range(3,11):
   total=0
   for off in range(0,len(pcm),8112):
    b=pcm[off:off+8112];coded=encode(b,order,k);assert decode(coded,len(b),order,k)==b
    total+=min(len(b),len(coded))
   rows.append(dict(order=order,k=k,encoded=total,reduction_percent=(1-total/len(pcm))*100))
 tests=[bytes(8112),rng.randbytes(8112),struct.pack('<hhhh',-32768,32767,32767,-32768)*1014,b''.join(struct.pack('<HH',i*13&65535,(32760+i*29)&65535) for i in range(2028))]
 for order in (1,2):
  for k in (3,4,5,9):
   for data in tests+[rng.randbytes(n) for n in (4,8,20,460,972,3600,7888)]:assert decode(encode(data,order,k),len(data),order,k)==data
 result=dict(passed=True,deployed=False,pcm_bytes=len(pcm),sha256=hashlib.sha256(pcm).hexdigest(),rows=rows)
 (HERE/'predictor_feasibility.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
