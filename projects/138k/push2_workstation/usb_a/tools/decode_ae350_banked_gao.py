"""Decode four stable GAO pages of one atomic snapshot; no EDA or board access."""
from pathlib import Path
import argparse,csv,io,json,re,sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.decode_ae350_probe_gao import decode_value as assess_full,MAGIC as FULL_MAGIC

BITS=704
MAGIC=0xa1386402
METADATA=0x04401000

def page_value(value,manifest):
    if not isinstance(value,int) or value<0 or value>>BITS:raise ValueError('banked GAO value exceeds bus width')
    word=lambda i:(value>>(32*i))&0xffffffff
    if word(18)!=MAGIC:raise ValueError('banked GAO schema magic missing')
    if word(17)!=int(manifest['user_code'],16):raise ValueError('banked GAO UserCode differs from manifest')
    if word(19)&~7!=METADATA:raise ValueError('banked GAO page geometry or reserved bits changed')
    valid=bool(word(19)&4)
    if valid and not word(20)&2:raise ValueError('banked GAO published IO marker missing')
    return dict(page=word(19)&3,published=valid,sequence=word(16),user=word(17),
        words=[word(i) for i in range(16)],io=word(20),health=word(21))

def decode(text,manifest):
    rows=list(csv.reader(io.StringIO(text)))
    headers=[i for i,r in enumerate(rows) if len(r)>1 and r[0].strip().startswith('time unit:')]
    if len(headers)!=1:raise ValueError('missing or ambiguous banked GAO header')
    start=headers[0];header=[v.strip() for v in rows[start]]
    while header and not header[-1]:header.pop()
    if header[1:]!=['status_50mhz',*[f'status_50mhz[{i}]' for i in reversed(range(BITS))]]:
        raise ValueError('banked GAO requires exact 704-bit packed and bit columns')
    fingerprints={};metadata={};seen=set();key=None;page=None;counts={};pages={}
    latest=None;observations=[];valid_rows=unknown=unpublished=reset_rows=0
    for row in rows[start+1:]:
        row=[v.strip() for v in row]
        while row and not row[-1]:row.pop()
        if not row:continue
        if len(row)!=BITS+2:raise ValueError('truncated or extra banked GAO columns')
        if not re.fullmatch(r'\d+(?:\.\d+)?',row[0]):raise ValueError('invalid banked GAO sample position')
        if any(v.lower() in ('x','z') for v in row[1:]):
            unknown+=1;page=None;counts={};pages={};continue
        if not re.fullmatch('[0-9a-fA-F]+',row[1]) or any(v not in ('0','1') for v in row[2:]):
            raise ValueError('invalid banked GAO sample radix')
        value=int(row[1],16)
        if value>>BITS or value!=int(''.join(row[2:]),2):raise ValueError('banked GAO packed and individual bits disagree')
        # The retained top register is exactly zero during common reset.
        # It separates reset contexts; no other missing/corrupt magic is valid.
        if value==0:
            reset_rows+=1;key=None;page=None;counts={};pages={};latest=None
            fingerprints={};metadata={};seen=set();continue
        sample=page_value(value,manifest);valid_rows+=1
        if not sample['published']:
            unpublished+=1;key=None;page=None;counts={};pages={};latest=None
            fingerprints={};metadata={};seen=set();continue
        current=(sample['user'],sample['sequence'])
        if current!=key:
            if current in seen:raise ValueError('banked GAO snapshot sequence returned after a different snapshot')
            seen.add(current);key=current;page=None;counts={};pages={};latest=None
        bank=sample['page'];fingerprint=(tuple(sample['words']),sample['io'],sample['health'])
        slot=(*current,bank)
        if slot in fingerprints and fingerprints[slot]!=fingerprint:
            raise ValueError('banked GAO page changed without a new snapshot sequence')
        fingerprints[slot]=fingerprint
        common=(sample['io'],sample['health'])
        if current in metadata and metadata[current]!=common:
            raise ValueError('banked GAO frozen IO or health changed within one snapshot sequence')
        metadata[current]=common
        if page is None:
            if bank!=0:continue
            page=0;counts={0:0};pages={}
        elif bank!=page:
            if bank==page+1 and counts[page]>=2:
                page=bank;counts[bank]=0
            elif bank==0:
                page=0;counts={0:0};pages={}
            else:
                page=None;counts={};pages={};continue
        counts[bank]+=1;pages[bank]=sample['words']
        if bank==3 and counts[bank]==2 and set(pages)==set(range(4)):
            words=sum((pages[i] for i in range(4)),[])
            full=sum(n<<(32*i) for i,n in enumerate([*words,sample['sequence'],sample['user'],
                FULL_MAGIC,sample['io'],sample['health']]))
            result=assess_full(full,manifest)
            result['digital_io']['snapshot_frozen_platform_health']=result['digital_io'].pop('live_platform_health')
            result['digital_io']['frozen_at_new_sequence_sweep_boundary']=True
            result.update(transport='GAO four stable pages; no UART CRC captured or inferred',
                stable_page_samples={str(i):counts[i] for i in range(4)},complete_snapshot=True)
            latest=result;observations.append(result)
    if latest is None:raise ValueError('no complete stable four-page group for the latest published snapshot')
    return dict(schema=1,identity=manifest['identity'],capture_bits=BITS,valid_rows=valid_rows,
        unknown_rows=unknown,unpublished_rows=unpublished,reset_rows=reset_rows,latest=latest,observations=observations,
        hardware_acceptance=False,flash_programmed=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=decode(a.input.read_text(),json.loads(a.manifest.read_text()))
    if a.output.exists():raise FileExistsError(str(a.output))
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['latest'],indent=2))
if __name__=='__main__':main()
