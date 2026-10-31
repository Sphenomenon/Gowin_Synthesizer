#!/usr/bin/env python3
"""Actual ROM96 address model and strict same-code physical-storage policy."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from tools import workstation_profile as profile
from tools import workstation_classic_runtime as runtime
from tools import workstation_ae350_memory as memory
from tools import stage_ae350_firmware as legacy
from test_ae350_boot_storage import SIGNALS,PORTS
from ae350_split_rv32 import SplitCpu
from ae350_rv32_startup import CpuTrap,ModelError,ROM

class Physical96Cpu(SplitCpu):
    """Reuse the actual instruction interpreter with exactly96K readable bytes.

    The inherited constructor validates its legacy link envelope. All access
    checks subsequently use len(image), so no padded byte stays accessible.
    """
    def __init__(self,image,symbols,**kwargs):
        if len(image)!=98304:raise ModelError('physical96 model requires exactly96K')
        super().__init__(image.ljust(131072,b'\0'),symbols,**kwargs)
        self.image=bytearray(image)

class Sources(unittest.TestCase):
    def test_explicit_physical_policy_keeps_128_and_default_capacities(self):
        selected=profile.load(ROOT,profile.CLASSIC_ROM96_NAME)
        self.assertEqual(memory.selection(selected['configuration']),dict(memory_profile='ilm64k_dlm64k',boot_rom_bytes=98304))
        for name,capacity in [(profile.CLASSIC_RUNTIME_NAME,131072),(profile.HCI_OWNER_NAME,65536),(profile.NAME,16384)]:
            self.assertEqual(memory.selection(profile.load(ROOT,name)['configuration'])['boot_rom_bytes'],capacity)
        for field,value in [('ae350_firmware_policy',runtime.POLICY),('ae350_memory_profile','pl16k_8k'),('ae350_pcm_policy','none'),('hci_transport_policy','none')]:
            c=dict(selected['configuration']);c[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'unsupported'):memory.selection(c)
        self.assertEqual(selected['configuration']['ae350_rtc_policy'],'reference50_fractional32768_bound1524_v1')
        self.assertEqual(profile.specification(profile.CLASSIC_RUNTIME_NAME)['provider'],runtime.PROVIDER)

    def test_actual_image_decoder_requires_explicit_physical_capacity(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'rom.mem';p.write_text('00000000\n'*24576)
            self.assertEqual(len(runtime.decode_rom(p,98304)),98304)
            with self.assertRaisesRegex(ValueError,'ROM128'):runtime.decode_rom(p)
            with self.assertRaises(ValueError):legacy.decode_rom(p,98304)
            p.write_text(p.read_text()+'00000000\n')
            with self.assertRaisesRegex(ValueError,'ROM96'):runtime.decode_rom(p,98304)
        self.assertIn('firmware_runtime.enabled=0;',(ROOT/'firmware/ae350/classic_runtime.c').read_text())

    def test_binary_growth_rejected_before_reference_or_padding(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d);(p/'firmware.bin').write_bytes(bytes(98308))
            with self.assertRaisesRegex(ValueError,'physical binary/cold bank overflow'):runtime.physical96_report(ROOT,p)

class NativeROM(unittest.TestCase):
    def run_model(self,source):
        with tempfile.TemporaryDirectory(prefix='rom96-address-')as d:
            p=Path(d)
            (p/'rom96.mem').write_text(''.join(f'{i^0x91357248:08x}\n'for i in range(24576)))
            (p/'rom128.mem').write_text(''.join(f'{i^0x91357248:08x}\n'for i in range(32768)))
            (p/'owner.sv').write_text(source)
            tb='module tb;\n'+SIGNALS+'\nwire[31:0]rom_data_ref,fetch_count_ref,last_fetch_ref;wire[63:0]ram_read_data_ref;\n'
            tb+='gw138k_boot_memory #(.ROM_BYTES(98304),.ROM_FILE("rom96.mem")) dut('+PORTS.format(suffix='')+');\n'
            tb+='gw138k_boot_memory #(.ROM_BYTES(131072),.ROM_FILE("rom128.mem")) reference('+PORTS.format(suffix='_ref')+');\n'
            tb+='''task fetch(input[31:0]address,input[31:0]expected96,input[31:0]expected128);begin
 @(negedge clk);rom_transfer=2;rom_address=address;
 @(posedge clk);#1;
 if(rom_data!==expected96)$fatal(1,"ROM96 range/alias at %h got %h expected %h",address,rom_data,expected96);
 if(rom_data_ref!==expected128)$fatal(1,"original128 branch at %h",address);
end endtask
initial begin
 @(negedge clk);reset_n=1;
 // Every actual word, including the middle32K rejected by a power2 mask.
 for(i=0;i<24576;i=i+1)fetch(32'h80000000+i*4,i^32'h91357248,i^32'h91357248);
 fetch(32'h80007fff,32'h1fff^32'h91357248,32'h1fff^32'h91357248);
 fetch(32'h8000ffff,32'h3fff^32'h91357248,32'h3fff^32'h91357248);
 fetch(32'h80017fff,32'h5fff^32'h91357248,32'h5fff^32'h91357248);
 fetch(32'h80018000,32'h00100073,32'h6000^32'h91357248);
 fetch(32'h8001fffc,32'h00100073,32'h7fff^32'h91357248);
 fetch(32'h80020000,32'h00100073,32'h00100073);
 fetch(32'h80030000,32'h00100073,32'h00100073);
 fetch(32'h90010000,32'h00100073,32'h00100073);
 fetch(32'h00008000,32'h00100073,32'h00100073);
 fetch(32'h7ffffffc,32'h00100073,32'h00100073);
 fetch(32'hffffffff,32'h00100073,32'h00100073);
 if(fetch_count!==24587||fetch_count!==fetch_count_ref||last_fetch!==32'hffffffff)$fatal(1,"diagnostics");
 @(negedge clk);rom_transfer=0;rom_address=32'h80000000;
 @(posedge clk);#1;if(rom_data!==32'h00100073||fetch_count!==24587)$fatal(1,"idle changed response");
 $display("PASS all24576 ROM96 words, same128 prefix, 64K/96K/128K boundaries, no aliases or idle change");$finish;
end endmodule'''
            (p/'tb.sv').write_text(tb)
            c=subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','tb.sv','owner.sv'],cwd=p,capture_output=True,text=True)
            self.assertEqual(c.returncode,0,c.stdout+c.stderr)
            return subprocess.run(['vvp','sim'],cwd=p,capture_output=True,text=True,timeout=30)

    def test_actual_all_words_and_128_prefix_equivalence(self):
        r=self.run_model((ROOT/memory.SOURCE).read_text())
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS all24576',r.stdout)

    def test_wrong_power2_mask_and_missing_upper_bound_are_killed(self):
        original=(ROOT/memory.SOURCE).read_text()
        anchor="(rom_address >= 32'h80000000 && rom_address < 32'h80018000)"
        self.assertEqual(original.count(anchor),1)
        for mutant in ["((rom_address & ROM_MASK) == 32'h80000000)","(rom_address >= 32'h80000000)"]:
            with self.subTest(mutant=mutant):
                r=self.run_model(original.replace(anchor,mutant))
                self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertIn('ROM96 range/alias',r.stdout)

@unittest.skipUnless(os.environ.get('GW138K_CLASSIC_ROM96_PREPARED'),'Set GW138K_CLASSIC_ROM96_PREPARED to actual ROM96 prepare')
class Prepared(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.output=Path(self.temp.name)/'candidate';shutil.copytree(os.environ['GW138K_CLASSIC_ROM96_PREPARED'],self.output)
        self.stage=self.output/'workstation/Prj1';self.evidence=self.output/'ae350_firmware'
        self.metadata=json.loads((self.output/'integration_inputs.json').read_text());self.build=self.metadata['ae350_firmware']['build']

    def test_actual_prepare_same_ELF_BIN_addresses_and_strict_physical_capacity(self):
        artifact=profile.verify(ROOT,self.output)
        self.assertEqual(artifact['profile'],profile.CLASSIC_ROM96_NAME)
        self.assertEqual(self.build['capacity']['rom_capacity_bytes'],98304)
        self.assertEqual(self.build['capacity']['cold_code_unallocated_bytes'],3552)
        graph=runtime.verify_build(ROOT,self.evidence,self.build,98304)
        self.assertEqual(graph['reviewed_JALR_sites'],171)
        self.assertEqual(graph['stack']['conservative_peak_bytes'],1904)
        ref=json.loads((ROOT/runtime.ROM96_REFERENCE).read_text())
        for file,key in [('firmware.elf','elf_sha256'),('firmware.bin','binary_sha256'),('firmware.nm','nm_sha256')]:self.assertEqual(runtime.sha(self.evidence/file),ref[key])
        rom=runtime.decode_rom(self.evidence/'boot.mem',98304);layout=runtime.decode_rom(self.evidence/'link_layout128_boot.mem')
        self.assertEqual(rom,layout[:98304]);self.assertEqual(layout[98304:],bytes(32768))
        self.assertEqual((self.stage/'firmware/boot.mem').read_bytes(),(self.evidence/'boot.mem').read_bytes())
        self.assertFalse(self.build['cache_enabled'])
        self.assertFalse(self.build['physical_storage']['actual_resource_savings_verified'])
        self.assertEqual(self.build['physical_storage']['legacy_layout_symbol']['value'],131072)

    def test_actual_RV32_loader_same_ILM_DLM_ABI_and_cache_rejection(self):
        image=runtime.decode_rom(self.evidence/'boot.mem',98304)
        layout=runtime.decode_rom(self.evidence/'link_layout128_boot.mem')
        symbols=self.build['capacity']['symbols']
        cpu=Physical96Cpu(image,symbols);reference=SplitCpu(layout,symbols)
        self.assertEqual(cpu.run(),'services_main');self.assertEqual(reference.run(),'services_main')
        self.assertEqual(cpu.ilm,reference.ilm);self.assertEqual(cpu.dlm,reference.dlm)
        self.assertEqual(cpu.registers,reference.registers);self.assertEqual(cpu.diagnostics,reference.diagnostics)
        self.assertTrue(cpu.fenced and cpu.executed_ilm)
        self.assertEqual(cpu.csrs[0x7ca],0)
        for address in range(ROM+65536,ROM+98304,4):self.assertEqual(cpu.read(address,fetch=True),reference.read(address,fetch=True))
        for address in [ROM-4,ROM+98304,ROM+131068,ROM+131072,ROM+196608]:
            with self.subTest(address=hex(address)),self.assertRaises(CpuTrap):cpu.read(address,fetch=True)
        for value in [1,2,3]:
            failed=Physical96Cpu(image,symbols,csr_overrides={0x7ca:value})
            self.assertEqual(failed.run(),'halt');self.assertFalse(failed.executed_ilm)
            self.assertEqual(failed.diagnostics[4],0x4641494c)

    def test_padding_or_capacity_metadata_cannot_be_fabricated(self):
        p=self.evidence/'link_layout128_boot.mem';words=p.read_text().splitlines();words[25000]='00000001';p.write_text('\n'.join(words)+'\n')
        with self.assertRaisesRegex(ValueError,'physical storage/padding evidence'):runtime.verify_build(ROOT,self.evidence,self.build,98304)
        changed=copy.deepcopy(self.build);changed['capacity']['rom_capacity_bytes']=131072
        with self.assertRaises(ValueError):runtime.verify_build(ROOT,self.evidence,changed,98304)

    def test_real_ELF_memory_span_escape_is_rejected(self):
        p=self.evidence/'firmware.elf';original=p.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',original)
        for owner in ['ROM','DLM']:
            raw=bytearray(original)
            for n in range(h[10]):
                o=h[5]+n*h[9];kind,offset,vma,lma,size,memsize,flags,align=struct.unpack_from('<IIIIIIII',raw,o)
                if kind==1 and ((owner=='ROM'and vma==0x80000000)or(owner=='DLM'and vma==0xa0200100)):
                    struct.pack_into('<I',raw,o+20,98308 if owner=='ROM'else 65536);break
            else:self.fail('actual load segment missing')
            p.write_bytes(raw)
            with self.subTest(owner=owner),self.assertRaisesRegex(ValueError,'actual ELF runtime memory span invalid'):runtime.physical96_report(ROOT,self.evidence)
        p.write_bytes(original)

    def test_real_128_link_success_cannot_hide_96_cold_overflow(self):
        # One new cold object tests the physical gate after a valid original128 link.
        work=Path(self.temp.name)/'overflow';shutil.copytree(self.evidence,work)
        record=json.loads((work/'verification.json').read_text())
        prefix=next(c['argv'][0]for c in record['commands']if c['name']=='link').removesuffix('-gcc')
        (work/'extra.S').write_text('.section .text,"ax",@progbits\n.space 4096\n')
        subprocess.run([prefix+'-gcc','-march=rv32im_zicsr_zifencei','-mabi=ilp32','-c','extra.S','-o','extra_classic_service.o'],cwd=work,check=True,capture_output=True)
        command=next(c['argv']for c in record['commands']if c['name']=='link')
        # The builder uses absolute object paths. Rebind each exact basename.
        command=[str(work/Path(x).name)if x.endswith('.o')else x for x in command]
        command.insert(command.index('-lgcc'),str(work/'extra_classic_service.o'))
        subprocess.run(command,cwd=work,check=True,capture_output=True)
        subprocess.run([prefix+'-objcopy','-O','binary','firmware.elf','firmware.bin'],cwd=work,check=True,capture_output=True)
        for flag,name in [('-n','firmware.nm')]:
            r=subprocess.run([prefix+'-nm',flag,'firmware.elf'],cwd=work,check=True,capture_output=True,text=True);(work/name).write_text(r.stdout)
        r=subprocess.run([prefix+'-size','firmware.elf'],cwd=work,check=True,capture_output=True,text=True);(work/'firmware.size').write_text(r.stdout)
        self.assertGreater((work/'firmware.bin').stat().st_size,98304)
        self.assertLess((work/'firmware.bin').stat().st_size,131072)
        with self.assertRaisesRegex(ValueError,'physical binary/cold bank overflow'):runtime.physical96_report(ROOT,work)

    def test_physical_ROM128_image_or_wrong_macro_is_rejected(self):
        shutil.copyfile(self.evidence/'link_layout128_boot.mem',self.evidence/'boot.mem')
        with self.assertRaisesRegex(ValueError,'exact physical ROM96'):runtime.decode_rom(self.evidence/'boot.mem',98304)
        record=copy.deepcopy(self.metadata['classic_runtime']);record['provider']=runtime.PROVIDER
        with self.assertRaisesRegex(ValueError,'joint source selection changed'):runtime.verify_selection(ROOT,self.stage,self.output,record,98304)

if __name__=='__main__':unittest.main()
