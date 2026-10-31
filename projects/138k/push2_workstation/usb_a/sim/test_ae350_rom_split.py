#!/usr/bin/env python3
"""Compile real ROM128 split code, execute it, and exercise fail-closed gates."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from tools.experiment_ae350_rom_split import build
from tools.ae350_rom_split import split_memory_report
from tools.ae350_rom_split_audit import analyze,verify_tables
from tools.ae350_local_memory import call_chain_report,direct_long_calls,symbol_values
from ae350_split_rv32 import SplitCpu,m_result
from ae350_rom_split_checks import run_model_checks
from ae350_rv32_startup import CpuTrap,ModelError,ROM,ILM,DLM
from test_ae350_boot_storage import SIGNALS,PORTS


class SplitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.directory=Path(cls.temp.name)
        supplied=os.environ.get('GW138K_ROM_SPLIT_OUTPUT')
        cls.out=Path(supplied) if supplied else cls.directory/'split'
        if supplied:
            cls.record=json.loads((cls.out/'verification.json').read_text())
            for name,expected in cls.record['input_sha256'].items():
                if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
                    raise ValueError('supplied output source drift: '+name)
        else:
            cls.record=build(cls.out,os.environ.get('RISCV_PREFIX'))
        cls.graph=analyze(cls.out,ROOT)
        cls.tables=verify_tables(cls.out)
        cls.s=symbol_values((cls.out/'firmware.nm').read_text())
        cls.binary=(cls.out/'firmware.bin').read_bytes()
        cls.image=cls.binary.ljust(131072,b'\0')
        cls.dis=(cls.out/'firmware.dis').read_text()
        cls.review=json.loads((cls.out/'combined_indirect_review.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_split_loader_cross_region_protocol_and_real_sbc_vectors(self):
        r=run_model_checks(self.out,ROOT)
        self.assertEqual(len(r['vectors']),11)
        self.assertEqual(r['scalar_samples'],3712)
        self.assertGreater(r['rv32m_instructions'],0)
        self.assertLessEqual(r['maximum_lsb_error'],6)
        self.assertFalse(r['cache_enabled'])
        self.assertTrue(r['delay_reporting']['first_accept'])
        self.assertTrue(r['delay_reporting']['exact_deadline_fenced'])
        self.assertTrue(r['delay_reporting']['late_accept_fenced'])
        self.assertFalse(r['delay_reporting']['physical_delay_measured'])

    def test_actual_elf_and_capacity_reject_old_or_unsupported_size_and_tampering(self):
        capacity=self.record['capacity']
        self.assertGreater(capacity['binary_bytes'],65536)
        self.assertGreater(capacity['ilm_usable_remaining_bytes'],16000)
        self.assertEqual(capacity['static_ram_span_bytes'],8480)
        self.assertEqual(capacity['stack_capacity_bytes'],16384)
        for size in (16384,65536,98304):
            with self.assertRaisesRegex(ValueError,'explicit 128'):
                split_memory_report((self.out/'firmware.size').read_text(),
                    (self.out/'firmware.nm').read_text(),self.binary,self.out/'firmware.elf',size)
        bad=bytearray(self.binary);bad[65536]^=1
        with self.assertRaisesRegex(ValueError,'reconstruct'):
            split_memory_report((self.out/'firmware.size').read_text(),
                (self.out/'firmware.nm').read_text(),bad,self.out/'firmware.elf')

    def test_existing_profile_and_firmware_staging_still_reject_rom128(self):
        from tools import workstation_ae350_memory as memory
        from tools import stage_ae350_firmware as staging
        with self.assertRaises(ValueError):
            memory.selection(dict(ae350_memory_profile='ilm64k_dlm64k',ae350_boot_rom_bytes=131072))
        with self.assertRaises(ValueError):
            staging.stage_ae350_firmware(ROOT,self.directory/'production-rejected',
                recording_api=True,memory_profile='ilm64k_dlm64k',boot_rom_bytes=131072)
        with self.assertRaises(ValueError):
            staging.decode_rom(self.out/'boot.mem',131072)

    def test_actual_native_rom128_all_words_no_alias_and_boundary(self):
        work=self.directory/'rtl';work.mkdir()
        (work/'boot.mem').write_text(''.join(f'{i^0x91357248:08x}\n' for i in range(32768)))
        tb='module tb;\n'+SIGNALS+'\ngw138k_boot_memory #(.ROM_BYTES(131072),.ROM_FILE("boot.mem")) dut('+PORTS.format(suffix='')+''');
task fetch(input [31:0] address,input [31:0] expected);begin
  @(negedge clk);rom_transfer=2;rom_address=address;
  @(posedge clk);#1;if(rom_data!==expected)$fatal(1,"ROM128 alias/boundary %h",address);
end endtask
initial begin
  @(negedge clk);reset_n=1;
  for(i=0;i<32768;i=i+1) fetch(32'h80000000+i*4,i^32'h91357248);
  fetch(32'h80020000,32'h00100073);fetch(32'h7ffffffc,32'h00100073);
  fetch(32'h80030000,32'h00100073);fetch(32'h90000000,32'h00100073);
  if(fetch_count!==32772 || last_fetch!==32'h90000000)$fatal(1,"diagnostics");
  @(negedge clk);rom_transfer=0;rom_address=32'h80000000;
  @(posedge clk);#1;if(rom_data!==32'h00100073 || fetch_count!==32772)$fatal(1,"idle");
  $display("PASS actual native ROM128 all32768 words no upper alias");$finish;
end endmodule'''
        (work/'tb.sv').write_text(tb)
        subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','tb.sv',str(ROOT/'rtl/memory/workstation_ae350_boot_memory.sv')],cwd=work,check=True,capture_output=True)
        r=subprocess.run(['vvp','sim'],cwd=work,check=True,capture_output=True,text=True,timeout=30)
        self.assertIn('PASS',r.stdout)

    def test_loader_fails_geometry_cache_corruption_and_missing_fence(self):
        cases=[dict(csr_overrides={0x7ca:v}) for v in (1,2,3)]
        cases += [dict(csr_overrides={csr:0}) for csr in (0xfc0,0xfc1)]
        cases += [dict(corrupt_copy_address=address) for address in (self.s['__ilm_end']-4,self.s['__data_end']-4)]
        cases += [dict(rom_readable=False),dict(stuck_enable=[0x7c0]),dict(stuck_enable=[0x7c1])]
        for case in cases:
            with self.subTest(case=case):
                cpu=SplitCpu(self.image,self.s,**case)
                self.assertEqual(cpu.run(),'halt')
                self.assertFalse(cpu.executed_ilm)
                self.assertEqual(cpu.diagnostics[4],0x4641494c)
        cpu=SplitCpu(self.image,self.s)
        fence=bytes.fromhex('0f100000');offset=cpu.image[:self.s['__ilm_load_start']-ROM].index(fence)
        cpu.image[offset:offset+4]=bytes.fromhex('13000000')
        with self.assertRaisesRegex(ModelError,'before fence.i'):
            cpu.run()

    def test_upper_alias_or_outside_physical_rom_cannot_pass_cold_call(self):
        cpu=SplitCpu(self.image,self.s,upper_alias=True)
        self.assertEqual(cpu.run(),'services_main')
        with self.assertRaises(ModelError):
            cpu.call('a138_classic_init',self.s['budget_classic'],limit=20000)
        cpu=SplitCpu(self.image,self.s)
        for address in (ROM-4,ROM+131072,ROM+196608):
            with self.assertRaises(CpuTrap):cpu.read(address,fetch=True)
        with self.assertRaises(ModelError):SplitCpu(self.image[:98304],self.s)

    def callgraph(self,review=None,dis=None,capacity=16384,output=None):
        review=self.review if review is None else review
        return call_chain_report(output or self.out,self.graph['compiler_stack_frames'],
            self.dis if dis is None else dis,capacity,
            reviewed_indirect_calls=review,input_sha256=self.review['input_sha256'])

    def test_actual_long_calls_and_all_indirect_sites_are_closed(self):
        stack=self.graph['stack']
        self.assertEqual(stack['conservative_peak_bytes'],1808)
        self.assertEqual(len(stack['reachable_functions']),115)
        self.assertEqual(len(stack['resolved_direct_long_calls']),38)
        self.assertEqual(self.graph['reviewed_reachable_JALR_sites'],77)
        self.assertEqual(len(self.tables),4)
        self.assertEqual(self.graph['linked_translation_units'],25)
        self.assertEqual(self.graph['budget_adapter_bytes'],7852)
        self.assertEqual(self.graph['rv32_abi_witness']['abi_classic'],2876)
        self.assertEqual(self.graph['rv32_objects']['budget_classic']['bytes'],2876)
        self.assertEqual(self.graph['rv32_abi_witness']['abi_pcm_slot'],528)
        self.assertEqual(self.graph['rv32_objects']['budget_pcm']['bytes'],4*528)
        self.assertTrue(self.graph['unlinked_witness_not_in_image'])
        for name in ('a138_classic_tick','a138_classic_delay_update'):
            self.assertIn(name,stack['reachable_functions'])
            self.assertTrue(any(c['target']==name for c in stack['resolved_direct_long_calls']))
        with self.assertRaises(ValueError):self.callgraph(capacity=1807)
        bad=copy.deepcopy(self.review);bad['sites']=bad['sites'][:-1]
        with self.assertRaises(ValueError):self.callgraph(review=bad)
        bad=copy.deepcopy(self.review);bad['disassembly_sha256']='0'*64
        with self.assertRaises(ValueError):self.callgraph(review=bad)

    def test_actual_compiled_missing_new_hooks_and_wrong_abi_witness_are_rejected(self):
        prefix=next(r['argv'][0] for r in self.record['commands'] if r['name']=='link').removesuffix('-gcc')
        changes={
            'missing-tick':('sim/fixtures/ae350_combined_budget_adapter.c',
                'budget_status=a138_classic_tick(&budget_classic,link,generation,budget_now_ms);',
                'budget_status=A138_CLASSIC_OK;'),
            'missing-delay-update':('sim/fixtures/ae350_combined_budget_adapter.c',
                'budget_status=a138_classic_delay_update(&budget_classic,link,generation,budget_delay_tenths_ms);',
                'budget_status=A138_CLASSIC_OK;'),
            'wrong-abi-witness':('sim/fixtures/ae350_budget_abi_witness.c',
                'abi_classic[sizeof(struct a138_classic_service)]',
                'abi_classic[sizeof(struct a138_classic_service)-4]')}
        receipts=[]
        for tag,(name,old,new) in changes.items():
            with self.subTest(tag=tag):
                source=self.directory/(tag+'-source');source.mkdir()
                for name_input in self.record['input_sha256']:
                    dest=source/name_input;dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(ROOT/name_input,dest)
                path=source/name;text=path.read_text();self.assertEqual(text.count(old),1)
                path.write_text(text.replace(old,new))
                out=self.directory/(tag+'-build')
                record=build(out,prefix,root=source)
                self.assertEqual(record['link_returncode'],0)
                symbols=symbol_values((out/'firmware.nm').read_text())
                for hook in ('a138_classic_tick','a138_classic_delay_update'):
                    self.assertIn(hook,symbols)  # Exported code alone is insufficient.
                with self.assertRaises(AssertionError) as error:analyze(out,source)
                expected='a138_classic_tick' if tag=='missing-tick' else 'a138_classic_delay_update' if tag=='missing-delay-update' else 'classic'
                self.assertIn(expected,str(error.exception))
                receipts.append(dict(tag=tag,actual_compile_and_link=True,link_returncode=0,
                    audit_rejected=True,reason=str(error.exception),
                    elf_sha256=hashlib.sha256((out/'firmware.elf').read_bytes()).hexdigest()))
        (self.out/'negative_budget_verification.json').write_text(json.dumps(receipts,indent=2)+'\n')

    def test_long_call_instruction_words_and_compiler_graph_must_agree(self):
        long_calls=direct_long_calls(self.dis)
        site=next(s for s in long_calls.values() if s['caller']=='a138_classic_init')
        # Change the actual upper immediate but retain objdump's old comment.
        changed=self.dis.replace(site['auipc_instruction'],f'{int(site["auipc_instruction"],16)^0x1000:08x}',1)
        review=copy.deepcopy(self.review)
        review['disassembly_sha256']=hashlib.sha256(changed.encode()).hexdigest()
        with self.assertRaises(ValueError):self.callgraph(review=review,dis=changed)
        work=self.directory/'missing-edge';work.mkdir()
        for path in self.out.glob('*.ci'):shutil.copyfile(path,work/path.name)
        graph=work/'classic_service.ci'
        lines=graph.read_text().splitlines()
        matching=[l for l in lines if 'sourcename: "a138_classic_init"' in l and 'targetname: "memset"' in l]
        self.assertEqual(len(matching),1)
        graph.write_text('\n'.join(l for l in lines if l not in matching)+'\n')
        with self.assertRaisesRegex(ValueError,'long call escapes'):self.callgraph(output=work)

    def test_real_callgraph_and_equal_cost_witness_are_hash_seed_independent(self):
        script='''import json,sys
from pathlib import Path
root,out=map(Path,sys.argv[1:])
sys.path.insert(0,str(root))
from tools.ae350_local_memory import call_chain_report
graph=json.loads((out/'callgraph_verification.json').read_text())
review=json.loads((out/'combined_indirect_review.json').read_text())
result=call_chain_report(out,graph['compiler_stack_frames'],(out/'firmware.dis').read_text(),16384,
    reviewed_indirect_calls=review,input_sha256=review['input_sha256'])
print(json.dumps(result,sort_keys=True,separators=(',',':')))
'''
        results=[]
        for seed in ('0','1','17','random'):
            env=dict(os.environ,PYTHONHASHSEED=seed)
            value=subprocess.check_output([sys.executable,'-c',script,str(ROOT),str(self.out)],env=env,text=True)
            results.append(value)
        self.assertTrue(all(value==results[0] for value in results))
        self.assertEqual(json.loads(results[0]),self.graph['stack'])
        (self.out/'hash_seed_verification.json').write_text(json.dumps(dict(seeds=['0','1','17','random'],
            actual_complete_callgraph_identical=True,conservative_peak_bytes=1808,
            result_sha256=hashlib.sha256(results[0].encode()).hexdigest()),indent=2)+'\n')

    def test_real_link_rejects_old_capacity_missing_decoder_and_overflows(self):
        original=next(row['argv'] for row in self.record['commands'] if row['name']=='link')
        work=self.directory/'negative-link';work.mkdir()
        gates=[]
        for tag in ('rom64','rom96','no-decoder','ilm-overflow','dlm-stack-overlap'):
            command=list(original)
            if tag.startswith('rom'):
                value=65536 if tag=='rom64' else 98304
                command=[v.replace('__boot_rom_bytes=131072','__boot_rom_bytes='+str(value)) for v in command]
            elif tag=='no-decoder':command=[v for v in command if not v.endswith('/sbc_decoder_service.o')]
            else:
                kind='text' if tag=='ilm-overflow' else 'bss'
                extra=work/(tag+'.S');extra.write_text(f'.section .{kind}.overflow,"a'+('x' if kind=='text' else 'w')+'",@'+('progbits' if kind=='text' else 'nobits')+'\n.space 65536\n')
                obj=extra.with_suffix('.o')
                subprocess.run([command[0],'-march=rv32im_zicsr_zifencei','-mabi=ilp32','-c',str(extra),'-o',str(obj)],check=True,capture_output=True)
                command.insert(command.index('-lgcc'),str(obj))
            command=[v.replace('-Map=firmware.map','-Map='+str(work/(tag+'.map'))) for v in command]
            command[command.index('-o')+1]=str(work/(tag+'.elf'))
            run=subprocess.run(command,cwd=self.out,text=True,capture_output=True)
            self.assertNotEqual(run.returncode,0,tag)
            expected='split requires explicit' if tag.startswith('rom') else 'undefined reference' if tag=='no-decoder' else 'overlaps reserved' if tag=='ilm-overflow' else 'overlap reserved 16 KiB stack'
            self.assertIn(expected,run.stderr)
            (work/(tag+'.log')).write_text(run.stdout+run.stderr)
            gates.append(dict(tag=tag,rejected=True,returncode=run.returncode,reason=run.stderr))
        (self.out/'negative_link_verification.json').write_text(json.dumps(gates,indent=2)+'\n')

    def test_rv32m_signed_division_overflow_zero_and_high_products(self):
        cases=[(4,0x80000000,0xffffffff,0x80000000),(6,0x80000000,0xffffffff,0),
            (4,0xfffffff9,3,0xfffffffe),(6,0xfffffff9,3,0xffffffff),
            (4,5,0,0xffffffff),(5,5,0,0xffffffff),(6,0xfffffffd,0,0xfffffffd),
            (7,5,0,5),(1,0xffffffff,0xffffffff,0),(2,0xffffffff,0xffffffff,0xffffffff),
            (3,0xffffffff,0xffffffff,0xfffffffe),(0,0xffffffff,2,0xfffffffe)]
        for op,a,b,expected in cases:
            self.assertEqual(m_result(op,a,b)&0xffffffff,expected)


if __name__=='__main__':unittest.main()
