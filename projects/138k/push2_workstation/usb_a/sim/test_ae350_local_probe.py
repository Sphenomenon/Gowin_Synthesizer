#!/usr/bin/env python3
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(Path(__file__).resolve().parent)]
from tools.workstation_ae350_local_probe import (firmware,safe_dac_constraints,SAFE_DAC_PINS,gao,TOP,
    audit_cpu_pll_constraint,audit_cpu_pll_placement,CPU_PLL_CONSTRAINT)
from tools.workstation_baselines import load_baseline
from tools.stage_ae350_firmware import decode_rom
from tools.decode_ae350_local_probe import decode,frames
from ae350_probe_rv32 import ProbeCpu

class ProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.directory=Path(cls.temp.name)
        cls.fw=firmware(ROOT,cls.directory/'firmware',None)
        cls.image=decode_rom(cls.directory/'firmware/boot.mem',65536)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def cpu(self,**kwargs):return ProbeCpu(self.image,self.fw['capacity']['symbols'],**kwargs)

    def test_required_core_pll_location_in_constraint_and_actual_route(self):
        audit_cpu_pll_constraint('IO_LOC "clk_50m" A11;\n'+CPU_PLL_CONSTRAINT+'\n')
        for invalid in ('',CPU_PLL_CONSTRAINT.replace('PLL_R[0]','PLL_B[2]'),
                CPU_PLL_CONSTRAINT+'\n'+CPU_PLL_CONSTRAINT,
                CPU_PLL_CONSTRAINT.replace('u_cpu_pll','wrong_pll')):
            with self.subTest(constraint=invalid),self.assertRaises(ValueError):
                audit_cpu_pll_constraint(invalid)
        # Actual .tr row layout: AT, delay, type, edge, fanout, LOC, NODE.
        row='  0.000  0.000 tCL RR 5 PLL_R[0] u_cpu_pll/PLL_inst/CLKOUT1\n'
        result=audit_cpu_pll_placement(row+row.replace('CLKOUT1','CLKOUT0'))
        self.assertEqual(result['reported_rows'],2)
        self.assertEqual(result['site'],'PLL_R[0]')
        for invalid in ('',row.replace('PLL_R[0]','PLL_B[2]'),
                row+row.replace('PLL_R[0]','PLL_B[2]'),row.replace('CLKOUT1','CLKOUT0'),
                row.replace('u_cpu_pll','wrong_pll')):
            with self.subTest(route=invalid),self.assertRaises(ValueError):
                audit_cpu_pll_placement(invalid)

    def test_gao_uses_working_core_expression_and_bus_schema(self):
        document=ET.fromstring(gao('C21031C7'));core=document.find('AoCore')
        self.assertEqual(core.get('module_name'),TOP)
        self.assertEqual(core.get('sample_clock'),'clk_50m_d')
        self.assertEqual(core.get('storage_depth'),core.get('capture_amount'))
        self.assertEqual(core.get('storage_depth'),'128')
        self.assertIsNone(document.find('Expressions'))
        self.assertEqual(core.find('Expressions/Expression').text,'M0|!M0')
        self.assertEqual(document.find('GAO_ID').text,'0011000111000111')
        self.assertEqual([n.text for n in core.findall('SignalList/Bus/Signal')],
            [f'status_50mhz[{bit}]' for bit in reversed(range(544))])

    def test_actual_probe_executes_crc_patterns_and_counter_difference(self):
        cpu=self.cpu();self.assertEqual(cpu.run_probe(),'probe_pass')
        d=cpu.diagnostics;p=self.fw['payload']
        self.assertEqual(d[32*4],p['crc32']);self.assertEqual(d[34*4],p['first']);self.assertEqual(d[35*4],p['last'])
        self.assertEqual(d[9*4],8192);self.assertGreater(d[37*4],1000);self.assertGreater(d[38*4],1000)
        self.assertEqual(d[42*4],0);self.assertEqual(d[56*4],15)
        self.assertGreater(d[48*4],0);self.assertGreater(d[54*4],0)
        self.assertLess(self.fw['call_chain_stack']['conservative_peak_bytes'],1024)
        self.assertGreater(self.fw['capacity']['binary_bytes'],32768)

    def test_rom16k_alias_and_service_address_alias_are_detected(self):
        cpu=self.cpu(rom_alias_16k=True)
        self.assertIn(cpu.run_probe(),('loader_halt','probe_fail'))
        self.assertTrue(cpu.diagnostics[1*4]==0x4641494c or cpu.diagnostics[7*4]&1)
        cpu=self.cpu(ilm_pattern_alias=True);self.assertEqual(cpu.run_probe(),'probe_fail')
        self.assertTrue(cpu.diagnostics[7*4]&2);self.assertGreater(cpu.diagnostics[42*4],0)

    def test_optional_counter_csr_traps_resume_without_enabling_any_counter(self):
        cpu=self.cpu(unsupported_csrs=(0xb00,0xb80,0xb02,0xb82))
        self.assertEqual(cpu.run_probe(),'probe_pass')
        self.assertEqual(cpu.diagnostics[56*4],0);self.assertGreater(cpu.diagnostics[15*4],0)
        self.assertEqual(cpu.diagnostics[29*4],2)
        self.assertEqual(cpu.csrs[0x320],0);self.assertEqual(cpu.csrs[0x7ca],0)

    def test_decoder_latest_frame_and_corruption_are_explicit(self):
        cpu=self.cpu();self.assertEqual(cpu.run_probe(),'probe_pass')
        words=[cpu.diagnostics.get(index*4,0) for index in range(64)]
        words[58]=1;words[61]=15
        manifest=dict(identity='model-only',user_code='0xc21031c6',firmware=self.fw)
        def frame(values,sequence=0,user=0xc21031c6):
            data=b'A138LM01'+struct.pack('<III64I',user,sequence,64,*values)
            return data+struct.pack('<I',zlib.crc32(data))
        good=frame(words)
        result=decode(good,manifest)
        self.assertTrue(result['latest']['local_memory_checks_passed'])
        self.assertTrue(result['latest']['counter_observation_passed'])
        wrong=list(words);wrong[61]=31
        result=decode(good+frame(wrong,1),manifest)
        self.assertFalse(result['latest']['local_memory_checks_passed'])
        self.assertFalse(result['latest']['checks']['fresh_snapshot'])
        self.assertFalse(decode(frame(words,user=1),manifest)['latest']['checks']['identity'])
        corrupted=bytearray(good);corrupted[44]^=1
        with self.assertRaises(ValueError):decode(bytes(corrupted),manifest)
        result=decode(bytes(corrupted)+good+good[:100],manifest)
        self.assertEqual(result['valid_frames'],1);self.assertEqual(result['rejected_frames'],1)

    def test_actual_top_ports_and_permanent_dac_safety_levels(self):
        cst,references=safe_dac_constraints(ROOT)
        self.assertEqual(set(SAFE_DAC_PINS),{'ak_pdn','ak_mclk','ak_bick','ak_lrck','ak_sdata','ak_smute'})
        self.assertEqual(len(references),2);self.assertEqual(cst.count('DRIVE=4 BANK_VCCIO=3.3'),6)
        baseline=load_baseline(ROOT,'resource_rework_route0')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'firmware').mkdir()
            (path/'firmware/boot.mem').write_text('00000000\n'*16384)
            (path/'probe_identity.vh').write_text("`define AE350_PROBE_USER_CODE 32'hC21031C6\n")
            (path/'riscv_ae350_config.v').write_bytes(baseline.read_bytes('riscv_ae350_config.v'))
            # Keep the actual frozen wrapper's conditional port declaration;
            # only its encrypted implementation is replaced for this RTL test.
            header=baseline.read_bytes('src/ae350/riscv_ae350_top.v').decode().split(');',1)[0]
            (path/'cpu_stub.v').write_text(header+');\nendmodule\n')
            (path/'pll_stub.v').write_text('''module gw138k_cpu_pll_cell(input clkin,init_clk,reset,enable0,
output lock,clkout0,clkout1);assign lock=!reset;assign clkout0=clkin;assign clkout1=clkin;endmodule''')
            (path/'tb.sv').write_text('''module tb;reg clk=0;always #10 clk=~clk;
wire pdn,mclk,bick,lrck,data,smute;
workstation_ae350_local_memory_probe_top dut(.clk_50m(clk),.debug_uart_tx(),
.ak_pdn(pdn),.ak_mclk(mclk),.ak_bick(bick),.ak_lrck(lrck),.ak_sdata(data),.ak_smute(smute));
integer i;initial begin for(i=0;i<32;i=i+1)begin #21;
if({smute,pdn,mclk,bick,lrck,data}!==6'b100000)$fatal(1,"DAC safety levels changed");
end $display("PASS probe top frozen wrapper ports and permanent DAC safety");$finish;end endmodule''')
            result=subprocess.run(['iverilog','-g2012','-I.','-s','tb','-o','sim','tb.sv','cpu_stub.v','pll_stub.v',
                str(ROOT/'rtl/probe/workstation_ae350_local_memory_probe_top.sv'),
                str(ROOT/'rtl/probe/workstation_ae350_probe_uart.sv'),
                str(ROOT/'rtl/memory/workstation_ae350_boot_memory.sv')],cwd=path,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run(['vvp','sim'],cwd=path,check=True,text=True,capture_output=True,timeout=10)
            self.assertIn('PASS probe top',result.stdout)

    def test_uart_async_atomic_snapshot_crc_and_timeout(self):
        for timeout in (False,True):
            with self.subTest(timeout=timeout),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)
                tb='''module tb;reg clk=0,pclk=0,rst=0;always #10 clk=~clk;always #7 pclk=~pclk;
reg [2047:0] source=0;wire tx;wire [511:0] monitor;
workstation_ae350_probe_uart #(.USER_CODE(32'hC21031C6),.BAUD_DIVISOR(4),.PERIOD_CYCLES(50),.SNAPSHOT_TIMEOUT(100)) dut(
.clk_50m(clk),.reset_n(rst),.pclk(pclk),.preset_n(PRESET),.source_words(source),.platform_flags(4'hf),.tx(tx),.status_50mhz(monitor));
integer i,j,b;reg [7:0] value;
integer epoch=0;
always @(posedge pclk)if(rst)begin
epoch=epoch+1;for(i=0;i<64;i=i+1)source[i*32+:32]<=32'ha1000000|(epoch<<8)|i;end
initial begin #100;rst=1;
for(j=0;j<560;j=j+1)begin @(negedge tx);#120;value=0;
for(b=0;b<8;b=b+1)begin value[b]=tx;#80;end
if(tx!==1)$fatal(1,"UART stop bit");$display("BYTE %02x",value);end
$finish;end endmodule'''.replace('PRESET',"1'b0" if timeout else 'rst')
                (path/'tb.sv').write_text(tb)
                subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','tb.sv',str(ROOT/'rtl/probe/workstation_ae350_probe_uart.sv')],cwd=path,check=True,capture_output=True)
                result=subprocess.run(['vvp','sim'],cwd=path,check=True,text=True,capture_output=True,timeout=30)
                data=bytes(int(line.split()[1],16) for line in result.stdout.splitlines() if line.startswith('BYTE '))
                accepted,bad=frames(data);self.assertEqual(bad,0);self.assertEqual(len(accepted),2)
                for sequence,frame in enumerate(accepted):
                    self.assertEqual(frame['user_code'],0xc21031c6);self.assertEqual(frame['sequence'],sequence)
                    if timeout:
                        self.assertEqual(frame['words'][61],31)
                        self.assertTrue(all(value==0 for i,value in enumerate(frame['words']) if i!=61))
                    else:
                        prefix=frame['words'][0]&0xffffff00
                        for i,value in enumerate(frame['words']):self.assertEqual(value,15 if i==61 else prefix|i)
                corrupted=bytearray(data[:280]);corrupted[44]^=1
                with self.assertRaises(ValueError):decode(bytes(corrupted),{})

if __name__=='__main__':unittest.main()
