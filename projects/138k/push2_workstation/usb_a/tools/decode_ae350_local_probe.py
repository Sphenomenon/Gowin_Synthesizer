"""Decode captured probe UART bytes; never opens a port or changes a board."""
from pathlib import Path
import argparse
import json
import struct
import zlib

MAGIC=b'A138LM01'
SIZE=280

def frames(data):
    result=[];offset=0;rejected=0
    while True:
        start=data.find(MAGIC,offset)
        if start<0:break
        if len(data)-start<SIZE:break
        raw=data[start:start+SIZE]
        if zlib.crc32(raw[:276])!=int.from_bytes(raw[276:280],'little'):
            rejected+=1;offset=start+1;continue
        user,sequence,count=struct.unpack_from('<III',raw,8)
        if count!=64:rejected+=1;offset=start+1;continue
        result.append(dict(offset=start,user_code=user,sequence=sequence,words=list(struct.unpack_from('<64I',raw,20))))
        offset=start+SIZE
    return result,rejected

def assess(frame,manifest):
    w=frame['words'];fw=manifest['firmware'];s=fw['capacity']['symbols'];payload=fw['payload']
    dlm=max(0xa0201000,(s['__bss_end']+255)&~255);dlm_end=s['__stack_bottom']-256
    ilm=(s['__ilm_end']+255)&~255
    checks=dict(identity=frame['user_code']==int(manifest['user_code'],16),loader_pass=w[1]==0x50415353,
        service_pass=w[6]==0x50415353 and w[7]==0 and w[8]==7,
        payload_crc=w[32]==payload['crc32'] and w[33]==payload['crc32'],
        payload_edges=w[34]==payload['first'] and w[35]==payload['last'] and w[36]==8192 and w[9]==8192,
        local_geometry=all(((w[i]>>12)&7)!=0 and ((w[i]>>15)&31)==7 for i in (16,17)),
        local_enabled=bool(w[19]&1) and bool(w[20]&1),cache_disabled=w[21]&3==0,
        executing_ilm=s['__ilm_start']<=w[11]<s['__ilm_end'],
        stack=s['__stack_bottom']<=w[12]<=s['__stack_top'] and w[12]%16==0,
        memory_patterns=w[37]==(dlm_end-dlm)//4 and w[38]==(0xa000fffc-ilm)//4 and w[42]==0,
        upper_rom_observed=w[58]==1,external_unmapped_absent=w[59]==0,
        fresh_snapshot=w[61]&0x1f==15)
    def wide(index):return w[index]|(w[index+1]<<32)
    cycle=dict(readable=(w[56]&3)==3,start=wide(44),end=wide(46),delta=wide(48))
    inst=dict(readable=(w[56]&12)==12,start=wide(50),end=wide(52),delta=wide(54))
    for counter in (cycle,inst):counter['running']=counter['readable'] and counter['delta']>0 and ((counter['end']-counter['start'])&((1<<64)-1))==counter['delta']
    return dict(sequence=frame['sequence'],checks=checks,local_memory_checks_passed=all(checks.values()),
        mcycle=cycle,minstret=inst,counter_observation_passed=cycle['running'] and inst['running'],
        csr_valid_mask=w[14],optional_csr_traps=w[15],last_probe_trap=dict(cause=w[29],pc=w[30]),
        pc=w[11],sp=w[12],stack_pattern_observed_bytes=w[43],phase=w[8],progress=w[9],heartbeat=w[10],
        interpretation='Captured diagnostic checks only; root must bind exact JTAG/SRAM identity and physical timing evidence separately.')

def decode(data,manifest):
    accepted,rejected=frames(data)
    if not accepted:raise ValueError('no complete CRC-valid AE350 probe UART frame')
    observations=[assess(frame,manifest) for frame in accepted]
    return dict(schema=1,identity=manifest['identity'],valid_frames=len(accepted),rejected_frames=rejected,
        latest=observations[-1],observations=observations,flash_programmed=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    result=decode(args.input.read_bytes(),json.loads(args.manifest.read_text()))
    if args.output.exists():raise FileExistsError(str(args.output))
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['latest'],indent=2))

if __name__=='__main__':main()
