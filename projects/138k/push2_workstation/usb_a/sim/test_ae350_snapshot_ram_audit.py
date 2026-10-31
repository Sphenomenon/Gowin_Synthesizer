#!/usr/bin/env python3
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_ae350_local_probe import audit_gao_synthesis,TOP,constraints

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
    for i in range(128):
        groups=[list(range(i,58*32,128))[j:j+8] for j in (0,8)]
        for bit in (58*32,59*32):
            if bit%128==i:groups[-1].append(bit)
        for group,bits in enumerate(groups):
            child+=['  LUT%d write_%d_%d (\n.F(write_%d_%d),\n'%(len(bits),i,group,i,group)+',\n'.join('.I%d(held_words[%d])'%(j,bit) for j,bit in enumerate(bits))+'\n);']
        child+=['  LUT2 write_%d (\n.F(di[%d]),\n.I0(write_%d_0),\n.I1(write_%d_1)\n);'%(i,i,i,i)]
    for i in range(32):child+=['  LUT4 uart_%d (\n.F(uart_%d),\n'%(i,i)+',\n'.join('.I%d(dq[%d])'%(j,i+32*j) for j in range(4))+'\n);']
    for stem,width in [('prefetch',384),('prepared_page0',512),('cache_data',32)]:
        for i in range(width):child+=['  DFF %s_%d_s0 (\n.Q(%s[%d]),\n.D(%s),\n.CLK(clk_50m)\n);'%(stem,i,stem,i,'uart_'+str(i) if stem=='cache_data' else 'dq[%d]'%(i%128))]
    child+=['endmodule']
    top=['module '+TOP+' (','input clk_50m,','input pclk',');','wire [383:0] payload;','wire [703:0] status_50mhz;',
        '  snapshot u_uart (\n.clk_50m(clk_50m),\n.pclk(pclk),\n.prefetch(payload[383:0])\n);']
    for i in range(704):top+=['  DFF s%d (\n.Q(status_50mhz[%d]),\n.D(payload[%d]),\n.CLK(clk_50m)\n);'%(i,i,i%384)]
    top+=['endmodule'];return '\n'.join(child+top)+'\n'
class RamAudit(unittest.TestCase):
 def test_actual_wrapper_constant_names_are_compared_by_proven_polarity(self):
  text=fixture();cells=[]
  for i in range(8):
   start=text.index('  SDPB lane'+str(i)+' (');end=text.index(');',start)+2
   text=text[:start]+text[start:end].replace('GND','GND_'+str(i)).replace('VCC','VCC_'+str(i))+text[end:]
   cells+=['  GND g%d (\n.G(GND_%d)\n);'%(i,i),'  VCC v%d (\n.V(VCC_%d)\n);'%(i,i)]
  text=text.replace('endmodule','\n'.join(cells)+'\nendmodule',1)
  self.assertEqual(audit_gao_synthesis(text,'bsram4')['snapshot_ram']['native_sdp_lanes'],8)
  with self.assertRaises(ValueError):audit_gao_synthesis(text.replace('.V(VCC_7)','.V(GND_7)'),'bsram4')
 def test_native_cdc_target_matches_actual_generated_wrapper_geometry(self):
  import fnmatch,re
  sdc=constraints(ROOT,'bsram4')
  target=re.search(r'set_max_delay 20.000 -from \[get_regs \{u_uart/held_words\*\}\] -to \[get_pins \{([^}]+)\}\]',sdc)[1]
  self.assertEqual(target,'u_uart/lanes*.ram/ram/DI*')
  for lane in range(8):
   for bit in range(16):self.assertTrue(fnmatch.fnmatchcase('u_uart/lanes[%d].ram/ram/DI[%d]'%(lane,bit),target))
  self.assertIn('set_false_path -hold -from [get_regs {u_uart/held_words*}] -to [get_pins {'+target+'}]',sdc)
 def test_actual_primitive_structure_gate_and_negative_controls(self):
  text=fixture();r=audit_gao_synthesis(text,'bsram4');self.assertEqual(r['snapshot_ram']['ram_read_bits_reaching_gao'],128)
  self.assertEqual(r['snapshot_ram']['held_pclk_bits'],1858)
  mutants=[text.replace('BIT_WIDTH_0=16','BIT_WIDTH_0=32',1),text.replace("READ_MODE=1'b0","READ_MODE=1'b1",1),
    text.replace('.CLKA(clk_50m)','.CLKA(pclk)',1),text.replace("4'b0011","4'b0001",1),
    text.replace(".CEB(re)",".CEB(GND)",1),text.replace(".OCE(VCC)",".OCE(GND)",1),text.replace(".RESET(GND)",".RESET(VCC)",1),
    text.replace('ra[4:0]',"5'b00000",1),text.replace('dq[31:16]','dq[15:0]',1),
    text.replace('.D(payload[0])','.D(zero)').replace('.D(payload[128])','.D(zero)').replace('.D(payload[256])','.D(zero)'),
    text.replace('.Q(held_words[0])','.Q(missing)',1),text.replace('.Q(prefetch[0])','.Q(missing)',1),
    text.replace('  SDPB lane0 (','  RAM16SDP4 lane0 (',1),
    text.replace('.I0(held_words[0])','.I0(GND)',1),text.replace('.I0(dq[0])','.I0(GND)',1)]
  # Remove every path of one native output bit to GAO, while retaining the
  # complete704-bit FF bank and all eight RAMs: decoy storage must fail.
  mutants.append(text.replace('.D(dq[0])','.D(zero)'))
  for i,m in enumerate(mutants):
   with self.subTest(mutant=i):
    with self.assertRaises(ValueError):audit_gao_synthesis(m,'bsram4')
if __name__=='__main__':unittest.main()
