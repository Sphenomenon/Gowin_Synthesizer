"""Decode the complete GAO probe bus; no port, EDA or board operation."""
from pathlib import Path
import argparse
import csv
import io
import json
import re
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.decode_ae350_local_probe import assess

BITS=2208
MAGIC=0xa1386401


def decode_value(value,manifest):
    if not isinstance(value,int) or value<0 or value>>BITS:
        raise ValueError('GAO value exceeds complete bus width')
    word=lambda index:(value>>(index*32))&0xffffffff
    if word(66)!=MAGIC:
        raise ValueError('GAO complete diagnostic schema magic missing')
    words=[word(index) for index in range(64)]
    sequence,user,observation,health=word(64),word(65),word(67),word(68)
    result=assess(dict(words=words,sequence=sequence,user_code=user),manifest)
    result['checks']['gao_snapshot_published']=bool(observation&2)
    result['local_memory_checks_passed']=all(result['checks'].values())
    result['counter_observation_passed']=bool(result['counter_observation_passed'] and
        result['checks']['identity'] and result['checks']['fresh_snapshot'] and
        result['checks']['gao_snapshot_published'])
    result.update(words=words,declared_design_user_code=f'0x{user:08x}',
        software_owned_words={str(i):words[i] for i in range(58)},
        pl_sampled_words={'58_upper_rom_seen':words[58],'59_external_unmapped_seen':words[59]},
        transport_word61=words[61],
        digital_io=dict(uart_output_drive=observation&1,uart_output_edges_modulo_2_30=observation>>2,
            snapshot_published=bool(observation&2),live_platform_health=health,
            external_pad_readback=False,external_uart_reception_verified=False),
        transport='GAO full published bank; UART CRC was not captured or inferred',
        interpretation='Words0..57 are firmware reports; words58/59 are PL sampled flags. IO fields observe the RTL output driver, not the pad or USB serial receiver. Root must independently bind JTAG identity, bitstream and physical evidence.')
    return result


def decode(text,manifest):
    rows=list(csv.reader(io.StringIO(text)))
    expected=[f'status_50mhz[{i}]' for i in reversed(range(BITS))]
    headers=[i for i,row in enumerate(rows) if len(row)>1 and row[0].strip().startswith('time unit:')]
    if len(headers)!=1:
        raise ValueError('missing or ambiguous GAO data header')
    start=headers[0]
    header=[v.strip() for v in rows[start]]
    while header and not header[-1]:header.pop()
    if header[1:]!=['status_50mhz',*expected]:
        raise ValueError('GAO requires exact complete 2208-bit packed and bit columns')
    observations=[];unknown=0;banks={}
    for row in rows[start+1:]:
        if not row or all(not v.strip() for v in row):continue
        row=[v.strip() for v in row]
        while row and not row[-1]:row.pop()
        if len(row)!=BITS+2:
            raise ValueError('truncated or extra GAO sample columns')
        if not re.fullmatch(r'\d+(?:\.\d+)?',row[0]):
            raise ValueError('invalid GAO sample position')
        if any(v.lower() in ('x','z') for v in row[1:]):
            unknown+=1;continue
        if not re.fullmatch('[0-9a-fA-F]+',row[1]) or any(v not in ('0','1') for v in row[2:]):
            raise ValueError('invalid GAO sample radix')
        value=int(row[1],16)
        if value>>BITS or value!=int(''.join(row[2:]),2):
            raise ValueError('GAO packed and individual bits disagree')
        observation=decode_value(value,manifest)
        if observation['digital_io']['snapshot_published']:
            key=(observation['declared_design_user_code'],observation['sequence'])
            if key in banks and banks[key]!=observation['words']:
                raise ValueError('GAO published bank changed without a new sequence')
            banks[key]=observation['words']
        observations.append(observation)
    if not observations:raise ValueError('no complete known GAO diagnostic sample')
    return dict(schema=1,identity=manifest['identity'],capture_bits=BITS,
        valid_rows=len(observations),unknown_rows=unknown,latest=observations[-1],
        observations=observations,hardware_acceptance=False,flash_programmed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=decode(a.input.read_text(),json.loads(a.manifest.read_text()))
    if a.output.exists():raise FileExistsError(str(a.output))
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['latest'],indent=2))

if __name__=='__main__':main()
