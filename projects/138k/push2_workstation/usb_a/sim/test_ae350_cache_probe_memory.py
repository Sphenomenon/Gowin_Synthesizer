#!/usr/bin/env python3
from pathlib import Path
import subprocess,tempfile,unittest,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.workstation_baselines import load_baseline
from tools.workstation_ae350_local_probe import native_sources
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'rtl/probe/workstation_ae350_cache_probe_memory.sv'
TB=ROOT/'sim/tb_ae350_cache_probe_memory.sv'
class CacheMemoryTest(unittest.TestCase):
    def run_rtl(self,text):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'memory.sv').write_text(text)
            compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(TB),str(p/'memory.sv')],text=True,capture_output=True)
            self.assertEqual(compile.returncode,0,compile.stderr)
            return subprocess.run(['vvp',str(p/'sim')],text=True,capture_output=True,timeout=10)
    def test_real_owner_phase_burst_alias_error_and_reset(self):
        run=self.run_rtl(SOURCE.read_text());self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn('PASS cache probe AHB owner',run.stdout)
    def test_actual_top_new_macro_hard_ip_ports_mmio_and_safe_dac(self):
        baseline=load_baseline(ROOT,'resource_rework_route0')
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'firmware').mkdir();(p/'firmware/boot.mem').write_text('00000000\n'*16384)
            (p/'probe_identity.vh').write_text("`define AE350_PROBE_USER_CODE 32'hC21031D3\n`define AE350_PROBE_BSRAM_GAO\n`define AE350_PROBE_CACHE_PMA\n")
            (p/'riscv_ae350_config.v').write_bytes(baseline.read_bytes('riscv_ae350_config.v'))
            header=baseline.read_bytes('src/ae350/riscv_ae350_top.v').decode().split(');',1)[0]
            (p/'cpu.v').write_text(header+');\nendmodule\n')
            (p/'pll.v').write_text('module gw138k_cpu_pll_cell(input clkin,init_clk,reset,enable0,output lock,clkout0,clkout1);assign lock=!reset;assign clkout0=clkin;assign clkout1=clkin;endmodule')
            (p/'tb.sv').write_text("""module tb;reg clk=0;always #5 clk=~clk;
wire pdn,mclk,bick,lrck,data,smute;
workstation_ae350_local_memory_probe_top dut(.clk_50m(clk),.debug_uart_tx(),.ak_pdn(pdn),
.ak_mclk(mclk),.ak_bick(bick),.ak_lrck(lrck),.ak_sdata(data),.ak_smute(smute));
initial begin
force dut.u_cpu.DDR_HCLK=clk;force dut.u_cpu.ROM_HCLK=clk;force dut.u_cpu.APB_PCLK=clk;
force dut.u_cpu.DDR_HRSTN=0;force dut.u_cpu.ROM_HRSTN=0;force dut.u_cpu.APB_PRSTN=0;
force dut.u_cpu.DDR_HTRANS=0;force dut.u_cpu.ROM_HTRANS=0;
force dut.u_cpu.APB_PSEL=0;force dut.u_cpu.APB_PENABLE=0;force dut.u_cpu.APB_PWRITE=0;
force dut.u_cpu.APB_PADDR=32'hf80000f0;force dut.u_cpu.APB_PSTRB=4'hf;
force dut.u_cpu.DDR_HADDR=32'h1000;force dut.u_cpu.DDR_HSIZE=3;
force dut.u_cpu.DDR_HBURST=3;force dut.u_cpu.DDR_HPROT=4'hf;force dut.u_cpu.DDR_HWRITE=0;
#21;force dut.u_cpu.DDR_HRSTN=1;force dut.u_cpu.ROM_HRSTN=1;force dut.u_cpu.APB_PRSTN=1;
@(negedge clk);force dut.u_cpu.DDR_HTRANS=2;@(posedge clk);#1;
if(dut.ram_ready!==1||dut.data_fault!==0||dut.u_cache_memory.burst!==3||dut.u_cache_memory.protection!==4'hf)$fatal(1,"real hard-IP bus port connection");
if(dut.u_boot_memory.ram_transfer!==0)$fatal(1,"old RAM owner enabled");
@(negedge clk);force dut.u_cpu.DDR_HADDR=32'h1008;force dut.u_cpu.DDR_HTRANS=3;
@(posedge clk);#1;if(dut.ram_ready!==1||dut.data_fault!==0)$fatal(1,"SEQ rejected");
@(negedge clk);force dut.u_cpu.DDR_HTRANS=0;force dut.u_cpu.APB_PSEL=1;force dut.u_cpu.APB_PENABLE=1;
#1;if(dut.prdata!==0)$fatal(1,"MMIO initial");@(posedge clk);#1;if(dut.prdata!==1)$fatal(1,"MMIO first read");
@(posedge clk);#1;if(dut.prdata!==2)$fatal(1,"MMIO repeated address cached");
@(negedge clk);force dut.u_cpu.APB_PWRITE=1;force dut.u_cpu.APB_PWDATA=32'hdeadbeef;
#1;if(dut.pslverr!==1)$fatal(1,"counter write allowed");@(posedge clk);#1;
if(dut.diagnostic[60]!==2)$fatal(1,"counter modified by rejected write");
if({smute,pdn,mclk,bick,lrck,data}!==6'b100000)$fatal(1,"DAC safe levels");
if($bits(dut.status_50mhz)!=704)$fatal(1,"explicit bsram4 width");
$display("PASS actual cache probe top ports MMIO counter and DAC safety");$finish;end
initial begin #10000;$fatal(1,"timeout");end endmodule""")
            run=subprocess.run(['iverilog','-g2012','-I.','-s','tb','-o','sim','tb.sv','cpu.v','pll.v',*[str(ROOT/n) for n in native_sources('bsram4','cache-pma-v1')]],cwd=p,text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr)
            run=subprocess.run(['vvp','sim'],cwd=p,text=True,capture_output=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertIn('PASS actual cache probe top',run.stdout)
    def test_representative_faults_are_detected(self):
        text=SOURCE.read_text()
        mutations={
            'wrong_alias':text.replace("{1'b1,address[11:3]}","{1'b0,address[11:3]}"),
            'wrong_data_phase':text.replace('ram[pending_index][lane*8+:8]','ram[index][lane*8+:8]'),
            'wrong_wrap':text.replace('(current&~span)|(low&span)','low'),
            'ignored_sequence':text.replace('wire sequence_error=transfer==3 &&','wire sequence_error=1\'b0 &&'),
            'no_forwarding':text.replace('pending_write && pending_index==index && pending_mask[lane]',"1'b0"),
            'reset_pending_retained':text.replace('fault<=0;error_second<=0;pending_write<=0;pending_index<=0;pending_mask<=0;', 'fault<=0;error_second<=0;'),
        }
        for name,changed in mutations.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(text,changed);run=self.run_rtl(changed)
                self.assertNotEqual(run.returncode,0,'mutant survived: '+name+'\n'+run.stdout)
if __name__=='__main__':unittest.main()
