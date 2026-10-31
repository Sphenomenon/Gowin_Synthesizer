#!/usr/bin/env python3
from pathlib import Path
import re,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from test_ae350_snapshot_ram_audit import fixture
from tools.workstation_ae350_local_probe import audit_gao_synthesis,constraints

def narrow_fixture():
 s=fixture()
 s=re.sub(r'  DFF prefetch_(\d+)_s0 \(.*?\n\);',lambda m:'' if int(m[1])>=128 else m[0],s,flags=re.S)
 s=re.sub(r'  DFF prepared_page0_(\d+)_s0 \(.*?\n\);',lambda m:'' if int(m[1])>=256 else m[0],s,flags=re.S)
 s=re.sub(r'  DFF s(\d+) \(.*?\n\);',lambda m:'' if int(m[1])>=448 else m[0].replace('payload[%d]'%(int(m[1])%384),'payload[%d]'%(int(m[1])%128)),s,flags=re.S)
 return s.replace('[383:0]','[127:0]').replace('[511:0]','[255:0]').replace('[703:0]','[447:0]')
class NarrowAuditTest(unittest.TestCase):
 def test_structure_geometry_data_cones_and_unchanged_cdc(self):
  r=audit_gao_synthesis(narrow_fixture(),'bsram8');s=r['snapshot_ram']
  self.assertEqual(r['registered_bits'],448);self.assertEqual(s['cache_bits'],dict(prefetch=128,prepared_page0=256,cache_data=32))
  self.assertEqual(s['held_pclk_bits'],1858);self.assertEqual(s['native_sdp_lanes'],8)
  self.assertEqual(s['ram_read_bits_reaching_gao'],128);self.assertEqual(s['ram_read_bits_reaching_uart'],128)
  self.assertEqual(s['reference_register_limit'],1100)
  self.assertEqual(constraints(ROOT,'bsram8'),constraints(ROOT,'bsram4'))
 def test_old_geometry_decoy_ram_missing_lane_and_wrong_clocks_fail(self):
  text=narrow_fixture()
  mutants=[text.replace('.Q(status_50mhz[447])','.Q(missing)'),text.replace('BIT_WIDTH_0=16','BIT_WIDTH_0=32',1),
   text.replace('.D(dq[0])','.D(zero)'),text.replace('.I0(dq[0])','.I0(GND)'),
   text.replace('.I0(held_words[0])','.I0(GND)'),text.replace('.Q(prefetch[0])','.Q(missing)'),
   text.replace('.CLKA(clk_50m)','.CLKA(pclk)',1),text.replace('  SDPB lane0 (','  RAM16SDP4 lane0 (',1)]
  for i,changed in enumerate(mutants):
   with self.subTest(mutant=i),self.assertRaises(ValueError):audit_gao_synthesis(changed,'bsram8')
  with self.assertRaises(ValueError):audit_gao_synthesis(fixture(),'bsram8')
  with self.assertRaises(ValueError):audit_gao_synthesis(text,'bsram4')
if __name__=='__main__':unittest.main()
