#!/usr/bin/env python3
"""Physical bank identity, same-edge ROM/scratch ABI and actual W ELF startup."""
from pathlib import Path
from copy import deepcopy
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
from tools import workstation_task3_w_banked96 as banked
from tools import workstation_profile as profiles
from tools import workstation_ae350_memory as memory
from tools import workstation_classic_runtime as runtime
from tools import workstation_task3_w_paired_profile as paired
from test_ae350_boot_storage import SIGNALS,PORTS
from test_workstation_classic_rom96 import Physical96Cpu
from ae350_split_rv32 import SplitCpu
from ae350_rv32_startup import CpuTrap,ROM


class Banked96(unittest.TestCase):
    def config(self):
        return deepcopy(profiles.specification(profiles.TASK3_W_BANKED96_NAME)['configuration'])

    def test_explicit_configuration_and_unchanged_parent_contract(self):
        config=self.config();parent=profiles.specification(profiles.TASK3_W_NO_USB_NAME)
        self.assertTrue(banked.configured(config));self.assertFalse(banked.configured(parent['configuration']))
        self.assertEqual(config,dict(parent['configuration'],ae350_boot_rom_bytes=98304,**{banked.KEY:banked.POLICY}))
        self.assertEqual(memory.selection(config),dict(memory_profile='ilm64k_dlm64k',boot_rom_bytes=98304))
        self.assertEqual(paired.cnn_memory_configuration(config)['provider'],banked.PROVIDER)
        for field,value in [(banked.KEY,None),('ae350_boot_rom_bytes',131072),('demo_role','M'),
                ('phone_batch_policy','old'),('usb_adapter_policy','old'),
                ('interboard_business_default_enabled',True),('interboard_physical_acceptance_required',False)]:
            altered=dict(config,**{field:value})
            with self.subTest(field=field),self.assertRaises(ValueError):memory.selection(altered)
        with self.assertRaises(ValueError):runtime._paired_media_helper(98304,media_worker=True,phone_batch=False)
        with self.assertRaises(ValueError):runtime._paired_media_helper(98304,media_worker=True,phone_batch=True,selected_provider=paired.BATCH_PROVIDER)
        with self.assertRaises(ValueError):runtime._paired_media_helper(131072,media_worker=True,phone_batch=True,selected_provider=banked.PROVIDER)

    def test_bank_split_and_corruption_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            path=Path(d)/'boot.mem'
            path.write_text(''.join(f'{i^0x91357248:08x}\n'for i in range(24576)))
            self.assertEqual(banked.split_image(path),banked.verify_banks(path))
            for b in range(3):
                p=path.with_name('boot.mem.bank'+str(b));original=p.read_text()
                p.write_text(original.replace(original[:8],'00000000',1))
                with self.assertRaises(ValueError):banked.verify_banks(path)
                p.write_text(original)
            p.write_text(original+'00000000\n')
            with self.assertRaises(ValueError):banked.verify_banks(path)
            path.write_text(path.read_text()+'00000000\n')
            with self.assertRaises(ValueError):banked.split_image(path)

    def test_actual_RTL_all_words_latency_idle_reset_scratch_and_no_alias(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d);rom=p/'boot.mem'
            rom.write_text(''.join(f'{i^0x91357248:08x}\n'for i in range(24576)))
            banked.split_image(rom)
            original=(ROOT/memory.SOURCE).read_text().replace('module gw138k_boot_memory','module reference_memory')
            (p/'reference.sv').write_text(original)
            (p/'banked.sv').write_bytes((ROOT/banked.SOURCE).read_bytes())
            tb='module tb;\n'+SIGNALS+'''
wire[31:0]rom_data_ref,fetch_count_ref,last_fetch_ref;wire[63:0]ram_read_data_ref;
gw138k_boot_memory #(.ROM_BYTES(98304),.ROM_FILE("boot.mem")) dut('''+PORTS.format(suffix='')+''');
reference_memory #(.ROM_BYTES(98304),.ROM_FILE("boot.mem")) reference('''+PORTS.format(suffix='_ref')+''');
task check;begin
 @(posedge clk);#1;
 if({rom_data,fetch_count,last_fetch,ram_read_data} !==
    {rom_data_ref,fetch_count_ref,last_fetch_ref,ram_read_data_ref})
   $fatal(1,"ROM/scratch ABI mismatch at %h bank %d",rom_address,dut.bank);
end endtask
task fetch(input[31:0]address,input[31:0]expected);begin
 @(negedge clk);rom_transfer=2;rom_address=address;check();
 if(rom_data!==expected)$fatal(1,"range/word %h got %h expected %h",address,rom_data,expected);
end endtask
initial begin
 for(i=0;i<1024;i=i+1)begin
   dut.ram[i]=64'h9037a555ea321b08^i;reference.ram[i]=64'h9037a555ea321b08^i;
 end
 check();@(negedge clk);reset_n=1;
 for(i=0;i<24576;i=i+1)fetch(32'h80000000+i*4,i^32'h91357248);
 fetch(32'h80007fff,32'h1fff^32'h91357248);
 fetch(32'h8000ffff,32'h3fff^32'h91357248);
 fetch(32'h80017fff,32'h5fff^32'h91357248);
 fetch(32'h80018000,32'h00100073);fetch(32'h8001fffc,32'h00100073);
 fetch(32'h80020000,32'h00100073);fetch(32'h90010000,32'h00100073);
 fetch(32'h00008000,32'h00100073);fetch(32'h7ffffffc,32'h00100073);
 fetch(32'hffffffff,32'h00100073);
 // NONSEQ/SEQ active, IDLE/BUSY hold, asynchronous diagnostic reset.
 for(i=0;i<64;i=i+1)begin
   @(negedge clk);rom_transfer=i%4;rom_address=32'h80007ffc+(i%3)*4;check();
   if(i%9==0)begin @(negedge clk);reset_n=0;check();@(negedge clk);reset_n=1;end
 end
 // All byte lanes/sizes, pending write forwarding and invalid writes.
 for(i=0;i<4096;i=i+1)begin
   @(negedge clk);ram_address=(i%17==0)?32'h80000000:((i/64)%17)*8+(i%8);
   ram_transfer=(i/64)%4;ram_size=(i/8)%8;ram_write=(i%3!=0);
   ram_write_data=64'hd039caddfedcba98^i;check();
 end
 @(negedge clk);ram_transfer=0;check();
 for(i=0;i<1024;i=i+1)if(dut.ram[i]!==reference.ram[i])$fatal(1,"scratch state %d",i);
 $display("PASS 24576 ROM words,3 banks,all range seams,idle/reset,4096 scratch cycles");$finish;
end endmodule'''
            (p/'tb.sv').write_text(tb)
            subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','tb.sv','banked.sv','reference.sv'],cwd=p,check=True,capture_output=True,text=True)
            run=subprocess.run(['vvp','sim'],cwd=p,capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertIn('PASS 24576',run.stdout)


@unittest.skipUnless(os.environ.get('GW138K_TASK3_W_BANKED96_PREPARED'),'requires actual C prepare')
class ActualPrepared(unittest.TestCase):
    def setUp(self):
        self.output=Path(os.environ['GW138K_TASK3_W_BANKED96_PREPARED'])
        self.evidence=self.output/'ae350_firmware';self.stage=self.output/'workstation/Prj1'
        self.metadata=json.loads((self.output/'integration_inputs.json').read_text())
        self.build=self.metadata['ae350_firmware']['build']

    def test_selected_source_closure_firmware_and_three_bank_inputs(self):
        profiles.verify(ROOT,self.output)
        self.assertEqual(self.build['capacity']['rom_capacity_bytes'],98304)
        self.assertEqual(self.build['capacity']['cold_code_unallocated_bytes'],7888)
        self.assertEqual(banked.verify_banks(self.stage/'firmware/boot.mem'),self.build['banked96_storage']['banks_sha256'])
        self.assertEqual(self.metadata['classic_runtime']['provider'],banked.PROVIDER)
        runtime.verify_build(ROOT,self.evidence,self.build,98304,paired_worker=True,phone_batch=True)

    def test_actual_loader_cold_execution_and_cache_rejection(self):
        from tools.ae350_local_memory import symbol_values
        image=runtime.decode_rom(self.evidence/'boot.mem',98304);symbols=symbol_values((self.evidence/'firmware.nm').read_text())
        cpu=Physical96Cpu(image,symbols);reference=SplitCpu(image+bytes(32768),symbols)
        self.assertEqual(cpu.run(),'services_main');self.assertEqual(reference.run(),'services_main')
        for field in ('ilm','dlm','registers','diagnostics'):self.assertEqual(getattr(cpu,field),getattr(reference,field))
        self.assertTrue(cpu.fenced and cpu.executed_ilm)
        for address in range(ROM+65536,ROM+98304,4):self.assertEqual(cpu.read(address,fetch=True),reference.read(address,fetch=True))
        for address in (ROM-4,ROM+98304,ROM+131068,ROM+131072,ROM+196608):
            with self.subTest(address=hex(address)),self.assertRaises(CpuTrap):cpu.read(address,fetch=True)
        for value in (1,2,3):
            failed=Physical96Cpu(image,symbols,csr_overrides={0x7ca:value})
            self.assertEqual(failed.run(),'halt');self.assertFalse(failed.executed_ilm)
        # Execute real cold service/security functions after the copied startup.
        for name,args in [('a138_classic_init',(0xa0204000,)),
                ('a138_classic_begin',(0xa0204000,1,1,1,272)),
                ('a138_security_init',(0xa0207000,)),
                ('a138_security_start_session',(0xa0207000,1,272,0xa0204000))]:
            with self.subTest(function=name):
                self.assertEqual(cpu.call(name,*args),reference.call(name,*args))
                self.assertEqual(cpu.dlm,reference.dlm)
        self.assertGreater(cpu.upper_rom_fetches,0)


    def test_actual_mapped_ROM_words_and_destructive_controls(self):
        import re
        from tools.workstation_synthesis_netlist import SynthesisNetlist
        vg=self.stage/'impl/gwsynthesis/custom_138k_integration.vg'
        if not vg.is_file():self.skipTest('actual C synthesis is not present')
        blocks=re.findall(r'^module gw138k_boot_memory\b.*?^endmodule\b',vg.read_text(),re.M|re.S)
        self.assertEqual(len(blocks),1)
        net=SynthesisNetlist(blocks[0]+'\nmodule mapped_test ();\ngw138k_boot_memory u_boot_memory ();\nendmodule\n','mapped_test')
        receipt=banked.check_mapped_rom(self.stage,net)
        self.assertEqual(receipt['ROM_blocks'],48);self.assertEqual(receipt['scratch_SDPB_blocks'],8)
        self.assertEqual(receipt['words'],24576)
        name=next(name for name,cell in net.cells.items()if cell['kind']=='pROM')
        original=net.cells[name]
        for operation in ('word','width','missing'):
            net.cells[name]=deepcopy(original)
            if operation=='word':
                params=net.cells[name]['parameters'];key='INIT_RAM_00'
                value=params.get(key,"256'h0");params[key]="256'h"+format(int(value.split("'h")[1],16)^1,'x')
            elif operation=='width':net.cells[name]['parameters']['BIT_WIDTH']='1'
            else:del net.cells[name]
            with self.subTest(operation=operation),self.assertRaises(ValueError):banked.check_mapped_rom(self.stage,net)
        net.cells[name]=original

    def test_actual_ELF_span_and_image_changes_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'fw';shutil.copytree(self.evidence,out)
            original=(out/'firmware.elf').read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',original)
            for owner in ('ROM','DLM'):
                raw=bytearray(original)
                for n in range(h[10]):
                    o=h[5]+n*h[9];kind,offset,vma,lma,size,memsize,flags,align=struct.unpack_from('<IIIIIIII',raw,o)
                    if kind==1 and ((owner=='ROM'and vma==ROM)or(owner=='DLM'and vma==0xa0200100)):
                        struct.pack_into('<I',raw,o+20,98308 if owner=='ROM'else 65536);break
                else:self.fail('actual segment absent')
                (out/'firmware.elf').write_bytes(raw)
                with self.subTest(owner=owner),self.assertRaises(ValueError):banked.physical_report(ROOT,out)
            (out/'firmware.elf').write_bytes(original)
            (out/'firmware.bin').write_bytes(bytes(98308))
            with self.assertRaisesRegex(ValueError,'physical binary/cold bank overflow'):banked.physical_report(ROOT,out)

if __name__=='__main__':unittest.main()
