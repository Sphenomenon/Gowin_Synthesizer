"""Opt-in DATA codec10: bounded stereo PCM16 delta/Rice k9, MSB first."""
import struct
MAX_PCM=8112

def decode(encoded, pcm_size, codec, allow_second=False):
    if not 4<=pcm_size<=MAX_PCM or pcm_size%4:
        raise ValueError('PCM length')
    if codec==0:
        if len(encoded)!=pcm_size:raise ValueError('RAW length')
        return bytes(encoded)
    if (codec!=10 and not (allow_second and codec==11)) or not 0<len(encoded)<pcm_size:raise ValueError('Codec/encoded length')
    k=5 if codec==11 else 9
    at=0;end=len(encoded)*8
    def bit():
        nonlocal at
        if at>=end:raise ValueError('Truncated Rice')
        v=(encoded[at//8]>>(7-(at&7)))&1;at+=1;return v
    previous=[0,0];before=[0,0];pcm=bytearray()
    for index in range(pcm_size//2):
        q=0
        while q<15 and bit():q+=1
        v=0
        for _ in range(16 if q==15 else k):v=(v<<1)|bit()
        if q==15:
            if v>>k<15:raise ValueError('Noncanonical escape')
        else:v|=q<<k
        channel=index&1
        predictor=2*previous[channel]-before[channel] if codec==11 else previous[channel]
        sample=(predictor+((v>>1)^-(v&1)))&65535
        before[channel]=previous[channel]
        previous[channel]=sample;pcm.extend(struct.pack('<H',sample))
    if end-at>=8:raise ValueError('Trailing bytes')
    while at<end:
        if bit():raise ValueError('Nonzero padding')
    return bytes(pcm)

def encode(pcm, allow_second=False):
    """Independent reference; preserve legacy codec10 tie behavior."""
    if not 4<=len(pcm)<=MAX_PCM or len(pcm)%4:raise ValueError('PCM length')
    candidates=[]
    for codec,k in ((10,9),(11,5)) if allow_second else ((10,9),):
        previous=[0,0];before=[0,0];bits=[]
        for i,(sample,) in enumerate(struct.iter_unpack('<H',pcm)):
            channel=i&1;predictor=2*previous[channel]-before[channel] if codec==11 else previous[channel]
            delta=(sample-predictor)&65535;before[channel]=previous[channel];previous[channel]=sample
            if delta&32768:delta-=65536
            v=(delta<<1)^(delta>>15);q=v>>k
            if q>=15:bits.extend([1]*15);count=16
            else:bits.extend([1]*q+[0]);count=k
            bits.extend((v>>b)&1 for b in range(count-1,-1,-1))
        bits.extend([0]*(-len(bits)%8))
        coded=bytes(sum(bits[a+b]<<(7-b) for b in range(8)) for a in range(0,len(bits),8))
        candidates.append((codec,coded))
    mode,coded=min(candidates,key=lambda x:len(x[1]))
    return (mode,coded) if len(coded)<len(pcm) else (0,bytes(pcm))
