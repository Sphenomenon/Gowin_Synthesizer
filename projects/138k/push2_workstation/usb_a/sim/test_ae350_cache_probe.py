#!/usr/bin/env python3
"""Actual firmware bytes + independent abstract cache/PMA negative controls."""
from pathlib import Path
import json,re,shutil,struct,subprocess,sys,tempfile,unittest,zlib
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from tools.workstation_ae350_local_probe import firmware,native_sources
from tools.workstation_ae350_cache_probe import audit_firmware
from tools.decode_ae350_cache_probe import decode
from tools.stage_ae350_firmware import decode_rom
from ae350_cache_probe_rv32 import CacheProbeCpu

class CacheProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.directory=Path(cls.temp.name)
        cls.fw=firmware(ROOT,cls.directory/'firmware',None,'cache-pma-v1')
        cls.image=decode_rom(cls.directory/'firmware/boot.mem',65536)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def cpu(self,**kwargs):return CacheProbeCpu(self.image,self.fw['probe_symbols'],**kwargs)
    def assert_restored(self,cpu):
        self.assertEqual(cpu.csrs[0x7ca]&3,0)
        self.assertEqual({k:cpu.csrs[k] for k in cpu.initial_pma},cpu.initial_pma)
    def test_actual_elf_success_control_order_geometry_and_memory_handoffs(self):
        cpu=self.cpu();self.assertEqual(cpu.run_cache(),'pass');d=cpu.diagnostics
        self.assert_restored(cpu);self.assertEqual(d[45*4],3)
        self.assertEqual(d[46*4],2308);self.assertEqual(len(cpu.cctl_trace),2308)
        self.assertEqual(cpu.cctl_trace[0],(23,0))
        self.assertEqual(cpu.cctl_trace[1:1025],[(24,a) for a in range(0,32768,32)])
        self.assertEqual([d[i*4] for i in (40,41,42)],[17,17,29])
        self.assertGreater(cpu.hits['i'],0);self.assertGreater(cpu.hits['d'],0)
        self.assertEqual(cpu.fills['i'],2);self.assertEqual(cpu.writebacks,128)
        self.assertEqual([d[i*4] for i in (22,23,24)],[32768,32768,0x00da00da])
        self.assertLessEqual(self.fw['call_chain_stack']['conservative_peak_bytes'],128)
        enable=cpu.control_trace.index((0x7ca,3));cfg=cpu.control_trace.index((0xbc0,0xf2f))
        self.assertLess(cfg,enable);self.assertEqual(cpu.control_trace[-3:],[(0xbc0,0),(0xbd0,0x100000),(0xbd1,0x100001)])
    def test_geometry_features_modes_and_existing_pma_fail_closed(self):
        cases=[({0xfc0:0x439ad9},1),({0xfc1:0x439ad9},1),({0xfc2:0x40000000},2),
               ({0xfc2:0x10000},2),({0x7ca:1<<9},0),({0xbc0:0xf},3),({0xbc3:3<<24},3)]
        for overrides,bit in cases:
            with self.subTest(overrides=overrides):
                cpu=self.cpu(csr_overrides=overrides);self.assertEqual(cpu.run_cache(),'fail')
                self.assertTrue(cpu.diagnostics[28]&(1<<bit));self.assert_restored(cpu)
                self.assertFalse(any(csr==0x7ca and value&3 for csr,value in cpu.control_trace))
        cpu=self.cpu(csr_overrides={0x7ca:1});self.assertEqual(cpu.run_cache(),'loader_halt')
    def test_ineffective_writeback_invalidate_alias_mmio_and_pma_are_detected(self):
        for fault,bit in [('drop_writeback',8),('drop_invalidate',10),('wrong_alias',6),
                          ('mmio_cacheable',13),('stuck_pma',4)]:
            with self.subTest(fault=fault):
                cpu=self.cpu(**{fault:True});self.assertEqual(cpu.run_cache(),'fail')
                self.assertTrue(cpu.diagnostics[28]&(1<<bit));self.assert_restored(cpu)
        cpu=self.cpu(stuck_enable=(0x7ca,));self.assertEqual(cpu.run_cache(),'fail')
        self.assertTrue(cpu.diagnostics[28]&(1<<5));self.assert_restored(cpu)
    def test_unsupported_controls_trap_terminal_without_fake_success(self):
        for csr in (0xfc2,0xbc0,0xbd0,0x7cc):
            with self.subTest(csr=csr):
                cpu=self.cpu(unsupported_csrs=(csr,));self.assertIn(cpu.run_cache(),('fail','trap_halt'))
                self.assertGreater(len(cpu.traps),0);self.assertEqual(cpu.diagnostics[28],0x80000000)
                self.assertEqual(cpu.diagnostics[8*4],0x80);self.assert_restored(cpu)
        cpu=self.cpu(trap_at_cctl=1026);self.assertIn(cpu.run_cache(),('fail','trap_halt'))
        self.assertGreater(len(cpu.traps),0);self.assert_restored(cpu)
        self.assertEqual(cpu.diagnostics[15*4],1);self.assertEqual(cpu.diagnostics[21*4]&3,0)
    def test_decoder_crc_latest_identity_and_no_schema_substitution(self):
        cpu=self.cpu();self.assertEqual(cpu.run_cache(),'pass')
        w=[cpu.diagnostics.get(i*4,0) for i in range(64)];w[61]=15
        m=dict(identity='model-only-D3',user_code='0xC21031D3',probe_program='cache-pma-v1')
        def frame(words,seq=0,user=0xc21031d3):
            b=b'A138LM01'+struct.pack('<III64I',user,seq,64,*words)
            return b+struct.pack('<I',zlib.crc32(b))
        good=frame(w);self.assertTrue(decode(good,m)['latest']['cache_probe_checks_passed'])
        for index in (0,5,6,15,19,20,21,22,24,25,31,34,35,36,37,38,39,40,41,42,44,45,46,48,54,55,56,57,59,61):
            bad=list(w);bad[index]^=1
            with self.subTest(index=index):self.assertFalse(decode(good+frame(bad,1),m)['latest']['cache_probe_checks_passed'])
        self.assertFalse(decode(frame(w,user=0),m)['latest']['checks']['identity'])
        bad=bytearray(good);bad[44]^=1
        with self.assertRaises(ValueError):decode(bad,m)
        self.assertEqual(decode(bytes(bad)+good+good[:100],m)['rejected_frames'],1)
        with self.assertRaises(ValueError):decode(good,dict(m,probe_program='local-memory'))
    def test_actual_disassembly_gate_rejects_changed_target_csrs_indirect_and_frames(self):
        original=(self.directory/'firmware/firmware.dis').read_text()
        frames=self.fw['compiler_stack_frames']
        def change_csr(text,old,new):
            def f(match):
                word=int(match[2],16)
                if word&127==0x73 and word>>20==old:word=(word&0xfffff)|(new<<20)
                return match[1]+f'{word:08x}'+match[3]
            return re.sub(r'(^\s*[0-9a-f]+:\s+)([0-9a-f]{8})(\s+)',f,text,flags=re.M)
        mutations=[original.replace('000012b7','000022b7'),change_csr(original,0xfc2,0xfc3),
                   change_csr(original,0x7ca,0x320)]
        entry=original.index('<services_main>:');tail=original[entry:]
        tail=re.sub(r'(^\s*[0-9a-f]+:\s+)[0-9a-f]{8}',r'\g<1>000300e7',tail,count=1,flags=re.M)
        mutations.append(original[:entry]+tail)
        for n,changed in enumerate(mutations):
            with self.subTest(mutation=n),tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)
                for source in (self.directory/'firmware').glob('*.ci'):shutil.copy(source,p/source.name)
                (p/'firmware.dis').write_text(changed)
                with self.assertRaises(ValueError):audit_firmware(p,frames)
        for kind,count in [('dynamic',16),('static',20000)]:
            changed=[dict(f,kind=kind,bytes=count) if f['function'].split(':',3)[-1]=='services_main' else f for f in frames]
            with self.subTest(kind=kind),self.assertRaises(ValueError):audit_firmware(self.directory/'firmware',changed)
    def test_program_requires_explicit_bsram4(self):
        for mode in ('full64','banked4'):
            with self.assertRaises(ValueError):native_sources(mode,'cache-pma-v1')
        self.assertIn('rtl/probe/workstation_ae350_cache_probe_memory.sv',native_sources('bsram4','cache-pma-v1'))
        self.assertNotIn('rtl/probe/workstation_ae350_cache_probe_memory.sv',native_sources('bsram4'))

if __name__=='__main__':unittest.main()
