#!/usr/bin/env python3
"""Prepare reviewed single sounds for FAT/RTL import; no runtime media player."""
from pathlib import Path
import argparse,hashlib,json,math,struct,wave,zlib

class Rejected(ValueError): pass

def prepare(source, declaration, slot, owner, normalize=False):
    gran=declaration.get('granularity')
    if gran not in ('single_note','single_hit'):
        raise Rejected('granularity must be single_note or single_hit')
    for key in ('contains_rhythm','contains_melody','contains_arrangement'):
        if declaration.get(key) is not False:
            raise Rejected(key+' must explicitly be false')
    if declaration.get('reviewed_single_sound') is not True:
        raise Rejected('human review attestation required; duration cannot detect arrangement')
    if not 0<=slot<64 or not 0<=owner<256: raise Rejected('slot/owner out of range')
    try:
        with wave.open(str(source),'rb') as wav:
            channels,width,rate,n=wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes()
            if wav.getcomptype()!='NONE' or channels not in (1,2) or width not in (1,2,3,4) or not 8000<=rate<=192000:
                raise Rejected('unsupported PCM WAV format')
            raw=wav.readframes(n)
    except (wave.Error,EOFError) as e: raise Rejected('invalid/unsupported WAV: '+str(e)) from e
    if n==0 or len(raw)!=n*channels*width: raise Rejected('empty/truncated WAV')
    if n/rate>(2 if gran=='single_hit' else 6): raise Rejected('single sound exceeds duration policy')
    mono=[]
    for frame in range(n):
        values=[]
        for c in range(channels):
            offset=(frame*channels+c)*width
            b=raw[offset:offset+width]
            value=(b[0]-128)<<8 if width==1 else int.from_bytes(b,'little',signed=True) >> ((width-2)*8)
            values.append(value)
        mono.append(sum(values)//channels)
    count=(n*48000+rate-1)//rate
    samples=[]
    for i in range(count):
        pos=i*rate;lo=pos//48000;frac=pos%48000
        a=mono[min(lo,n-1)];b=mono[min(lo+1,n-1)]
        samples.append(a+((b-a)*frac)//48000)
    pcm=struct.pack('<'+'h'*len(samples),*samples)
    peak=max(abs(s) for s in samples)
    gain=(32767<<16)//peak if normalize and peak else 65536
    item=dict(slot=slot,owner=owner,frames=count,format='PCM16_MONO_48000',
        duration_seconds=count/48000,granularity=gran,reviewed_single_sound=True,
        contains_rhythm=False,contains_melody=False,contains_arrangement=False,
        gain_q16=gain,crc32=f'{zlib.crc32(pcm):08x}',pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        source_format=dict(channels=channels,bits=width*8,rate=rate),
        conversion='mono average; linear resample to 48000; signed PCM16',
        normalize=normalize)
    return pcm,item

def allocate(items,map_path):
    import re
    text=map_path.read_text()
    def macro(name):
        match=re.search(r'`define\s+'+name+r"\s+32'h([0-9a-fA-F_]+)",text)
        if not match: raise Rejected('address-map macro missing: '+name)
        return int(match[1].replace('_',''),16)
    base=macro('PRJ1_DDR_GROWTH_POOL_BYTE_BASE');last=macro('PRJ1_DDR_GROWTH_POOL_BYTE_LAST')
    granule=macro('PRJ1_DDR_ALLOC_GRANULE_BYTES');cursor=base;slots=set()
    for item in items:
        if item['slot'] in slots: raise Rejected('duplicate slot')
        slots.add(item['slot']);capacity=math.ceil(item['frames']*2/granule)*granule
        if cursor+capacity>last+1: raise Rejected('sample pool full')
        item.update(address_bytes=cursor,capacity_bytes=capacity,epoch=0,version=1)
        cursor+=capacity
    return dict(base_bytes=base,last_byte=last,granule_bytes=granule,allocated_bytes=cursor-base)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('spec',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--address-map',type=Path,default=Path(__file__).parent.parent/'ddr_address_map.vh')
    args=ap.parse_args();spec=json.loads(args.spec.read_text());prepared=[];items=[]
    try:
        for entry in spec['samples']:
            source=args.spec.parent/entry['file'];pcm,item=prepare(source,entry,entry['slot'],entry['owner'],entry.get('normalize',False))
            filename=f"S{item['slot']:02d}.WAV";item['file']=filename;items.append(item);prepared.append((filename,pcm))
        pool=allocate(items,args.address_map)
    except (Rejected,KeyError,OSError) as e: ap.error(str(e))
    args.output.mkdir(parents=True,exist_ok=False)
    for filename,pcm in prepared:
        with wave.open(str(args.output/filename),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(pcm)
    manifest=dict(schema='sampler-manifest-v1',sample_rate=48000,pool=pool,samples=items,
        policy=dict(single_hit_max_seconds=2,single_note_max_seconds=6,
            content_validation='required human declaration; no automatic musical-content classifier'),
        allocation='fresh pool import order; read back runtime descriptors after frees/reallocations')
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(samples=len(items),bytes=pool['allocated_bytes'])))
if __name__=='__main__': main()
