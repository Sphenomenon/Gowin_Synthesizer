#!/usr/bin/env python3
"""Strict four-page GAO decoding and actual UART/bank RTL, without EDA."""
from pathlib import Path
import copy,csv,io,json,os,subprocess,sys,tempfile,unittest,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from tools.decode_ae350_bsram8_gao import decode,page_value,BITS,MAGIC,METADATA
from tools.decode_ae350_local_probe import frames
from tools.workstation_ae350_local_probe import gao,gao_record,native_sources

class NarrowDecoderTest(unittest.TestCase):
    def manifest(self):
        return dict(identity='offline-bsram8-only',user_code='0xc21031d4',gao=gao_record('bsram8'),firmware=dict(
            capacity=dict(symbols=dict(__ilm_start=0xa0000000,__ilm_end=0xa0001000,
                __bss_end=0xa0200200,__stack_bottom=0xa020c000,__stack_top=0xa0210000)),
            payload=dict(crc32=1,first=2,last=3)))

    def value(self,page=0,sequence=0,words=None,io=0x1234567b,health=0xffff078f,user=0xc21031d4,magic=MAGIC,published=True):
        if words is None:words=[15 if i==61 else 0x10000000+i for i in range(64)]
        data=[*words[page*8:(page+1)*8],sequence,user,magic,METADATA|int(published)*8|page,io,health]
        return sum(n<<(32*i) for i,n in enumerate(data))

    def sweep(self,**kw):return [self.value(page=p,**kw) for p in range(8) for _ in range(4)]

    def csv(self,values):
        out=io.StringIO();w=csv.writer(out);w.writerow(['Groups:']);w.writerow(['Data:'])
        w.writerow(['time unit: us','status_50mhz',*[f'status_50mhz[{i}]' for i in reversed(range(BITS))],''])
        for i,v in enumerate(values):
            w.writerow([str(i),'X',*['X']*BITS,''] if v is None else [str(i),f'{v:X}',*f'{v:0{BITS}b}',''])
        return out.getvalue()

    def test_exact_layout_all_words_and_repeated_sweeps(self):
        result=decode(self.csv([None,*self.sweep(),*self.sweep()]),self.manifest())
        self.assertEqual(result['capture_bits'],448);self.assertEqual(len(result['observations']),2)
        latest=result['latest'];self.assertEqual(latest['words'],[15 if i==61 else 0x10000000+i for i in range(64)])
        self.assertEqual(latest['sequence'],0);self.assertTrue(latest['complete_snapshot'])
        self.assertTrue(latest['digital_io']['frozen_at_new_sequence_sweep_boundary'])
        self.assertFalse(latest['digital_io']['external_uart_reception_verified'])
        self.assertNotIn('live_platform_health',latest['digital_io'])
        self.assertIn('no UART CRC',latest['transport']);self.assertFalse(result['hardware_acceptance'])

    def test_first_middle_last_truncation_and_unstable_pages_fail_closed(self):
        sweep=self.sweep()
        cases=[sweep[4:],sweep[:4]+sweep[8:],sweep[:12],sweep[:13],
            [self.value(page=p) for p in range(8)],
            [*sweep[:4],None,*sweep[4:]],
            [*sweep,*self.sweep(sequence=1)[:12]],
            [*sweep,*self.sweep(sequence=1),*self.sweep()]]
        for values in cases:
            with self.subTest(values=len(values)),self.assertRaises(ValueError):decode(self.csv(values),self.manifest())
        for bit in (0,32*12,32*13):
            bad=self.sweep();bad[1]^=1<<bit
            with self.assertRaises(ValueError):decode(self.csv(bad),self.manifest())
        # Matching page data cannot excuse differing frozen IO/health between pages.
        for field in ('io','health'):
            bad=self.sweep();bad[4]=self.value(page=1,**{field:3})
            with self.assertRaises(ValueError):decode(self.csv(bad),self.manifest())

    def test_reset_contexts_and_timeout_remain_explicit(self):
        changed=[15 if i==61 else 0x20000000+i for i in range(64)]
        for separator in (0,self.value(published=False,io=1)):
            r=decode(self.csv([*self.sweep(),separator,*self.sweep(words=changed)]),self.manifest())
            self.assertEqual(r['latest']['words'],changed)
            with self.assertRaises(ValueError):decode(self.csv([*self.sweep()[:8],separator,*self.sweep()[8:]]),self.manifest())
            with self.assertRaises(ValueError):decode(self.csv([*self.sweep(),separator]),self.manifest())
        changed[61]=31
        r=decode(self.csv(self.sweep(words=changed)),self.manifest())
        self.assertFalse(r['latest']['checks']['fresh_snapshot'])
        self.assertFalse(r['latest']['counter_observation_passed'])

    def test_unknown_tail_requires_another_complete_group(self):
        for tail in ([None],[None,*self.sweep()[:12]]):
            with self.assertRaises(ValueError):decode(self.csv([*self.sweep(),*tail]),self.manifest())
        for sequence in (0,1):
            r=decode(self.csv([*self.sweep(),None,*self.sweep(sequence=sequence)]),self.manifest())
            self.assertEqual(r['latest']['sequence'],sequence)
            self.assertEqual(r['unknown_rows'],1)

    def test_rejects_identity_schema_geometry_header_bits_and_legacy_width(self):
        for kw in (dict(user=1),dict(magic=0),dict(io=1)):
            with self.assertRaises(ValueError):decode(self.csv(self.sweep(**kw)),self.manifest())
        with self.assertRaises(ValueError):page_value(self.value()^(1<<(32*11+4)),self.manifest())
        rows=list(csv.reader(io.StringIO(self.csv(self.sweep()))));cases=[]
        bad=copy.deepcopy(rows);bad[2][2],bad[2][3]=bad[2][3],bad[2][2];cases.append(bad)
        bad=copy.deepcopy(rows);bad[-1].pop(100);cases.append(bad)
        bad=copy.deepcopy(rows);bad[-1][100]='1' if bad[-1][100]=='0' else '0';cases.append(bad)
        for width in (544,704,2208):
            bad=copy.deepcopy(rows);bad[2]=['time unit: us','status_50mhz',*[f'status_50mhz[{i}]' for i in reversed(range(width))]];cases.append(bad)
        for bad in cases:
            out=io.StringIO();csv.writer(out).writerows(bad)
            with self.assertRaises(ValueError):decode(out.getvalue(),self.manifest())

    def test_explicit_geometry_and_original_decoders_are_distinct(self):
        core=ET.fromstring(gao('C21031D4','bsram8')).find('AoCore')
        self.assertEqual([n.text for n in core.findall('SignalList/Bus/Signal')],[f'status_50mhz[{i}]' for i in reversed(range(448))])
        self.assertEqual(gao_record('bsram8')['page_words'],8)
        self.assertEqual(gao_record('bsram8')['pages'],8)
        self.assertEqual(gao_record('bsram8')['page_cycles'],4)
        self.assertEqual(gao_record('bsram4')['capture_bits'],704)
        self.assertEqual(gao_record('full64')['capture_bits'],2208)
        for field,value in [('mode','bsram4'),('schema','A1386403'),('capture_bits',704),('pages',4),('page_words',16),('page_cycles',2)]:
            m=self.manifest();m['gao'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):decode(self.csv(self.sweep()),m)
        from tools.decode_ae350_banked_gao import page_value as old_value
        with self.assertRaises(ValueError):old_value(self.value(),dict(self.manifest(),gao=gao_record('bsram4')))

if __name__=='__main__':unittest.main()
