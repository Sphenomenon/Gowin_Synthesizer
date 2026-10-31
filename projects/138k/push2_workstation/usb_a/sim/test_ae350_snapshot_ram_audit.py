#!/usr/bin/env python3
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_ae350_local_probe import audit_gao_synthesis,TOP

def fixture():
    child=['module snapshot (clk_50m,pclk,prefetch);','input clk_50m;','input pclk;','output [383:0] prefetch;',
      'wire [4:0] wa;','wire [4:0] ra;','wire [127:0] di;','wire [127:0] dq;',
      'wire [2047:0] held_words;','wire [511:0] prepared_page0;','wire [31:0] cache_data;',
      '  GND g (\n.G(GND)\n);','  VCC v (\n.V(VCC)\n);']
    for i in range(8):
        name='lane'+str(i)
        child+=['  SDPB '+name+' (', '.DO({16\'b0000000000000000,dq[%d:%d]}),'%(i*16+15,i*16),
          '.DI({16\'b0000000000000000,di[%d:%d]}),'%(i*16+15,i*16),
          '.ADA({5\'b00000,wa[4:0],4\'b0011}),','.ADB({5\'b00000,ra[4:0],4\'b0000}),',
          '.CLKA(clk_50m),','.CLKB(clk_50m),','.CEA(we),','.CEB(re),','.OCE(VCC),','.RESET(GND),',
          '.BLKSELA(3\'b000),','.BLKSELB(3\'b000)',');']
        child+=['defparam '+name+'.'+k+'='+v+';' for k,v in dict(BIT_WIDTH_0='16',BIT_WIDTH_1='16',READ_MODE="1'b0",RESET_MODE='"SYNC"',BLK_SEL_0="3'b000",BLK_SEL_1="3'b000").items()]
    for i in [*range(58*32),58*32,59*32]:child+=['  DFF held%d (\n.Q(held_words[%d]),\n.D(src),\n.CLK(pclk)\n);'%(i,i)]
    for stem,width in [('prefetch',384),('prepared_page0',512),('cache_data',32)]:
        for i in range(width):child+=['  DFF %s_%d_s0 (\n.Q(%s[%d]),\n.D(dq[%d]),\n.CLK(clk_50m)\n);'%(stem,i,stem,i,i%128)]
    child+=['endmodule']
    top=['module '+TOP+' (','input clk_50m,','input pclk',');','wire [383:0] payload;','wire [703:0] status_50mhz;',
        '  snapshot u_uart (\n.clk_50m(clk_50m),\n.pclk(pclk),\n.prefetch(payload[383:0])\n);']
    for i in range(704):top+=['  DFF s%d (\n.Q(status_50mhz[%d]),\n.D(payload[%d]),\n.CLK(clk_50m)\n);'%(i,i,i%384)]
    top+=['endmodule'];return '\n'.join(child+top)+'\n'
class RamAudit(unittest.TestCase):
 def test_actual_primitive_structure_gate_and_negative_controls(self):
  text=fixture();r=audit_gao_synthesis(text,'bsram4');self.assertEqual(r['snapshot_ram']['ram_read_bits_reaching_gao'],128)
  self.assertEqual(r['snapshot_ram']['held_pclk_bits'],1858)
  mutants=[text.replace('BIT_WIDTH_0=16','BIT_WIDTH_0=32',1),text.replace("READ_MODE=1'b0","READ_MODE=1'b1",1),
    text.replace('.CLKA(clk_50m)','.CLKA(pclk)',1),text.replace("4'b0011","4'b0001",1),
    text.replace(".CEB(re)",".CEB(GND)",1),text.replace(".RESET(GND)",".RESET(VCC)",1),
    text.replace('ra[4:0]',"5'b00000",1),text.replace('dq[31:16]','dq[15:0]',1),
    text.replace('.D(payload[0])','.D(zero)').replace('.D(payload[128])','.D(zero)').replace('.D(payload[256])','.D(zero)'),
    text.replace('.Q(held_words[0])','.Q(missing)',1),text.replace('.Q(prefetch[0])','.Q(missing)',1),
    text.replace('  SDPB lane0 (','  RAM16SDP4 lane0 (',1)]
  # Remove every path of one native output bit to GAO, while retaining the
  # complete704-bit FF bank and all eight RAMs: decoy storage must fail.
  mutants.append(text.replace('.D(dq[0])','.D(zero)'))
  for i,m in enumerate(mutants):
   with self.subTest(mutant=i):
    with self.assertRaises(ValueError):audit_gao_synthesis(m,'bsram4')
if __name__=='__main__':unittest.main()
