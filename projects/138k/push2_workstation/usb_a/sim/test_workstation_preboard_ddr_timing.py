#!/usr/bin/env python3
"""Actual routed DDR boundary: strict finite limits and misbinding rejection."""
from pathlib import Path
import hashlib
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_preboard_ddr_timing as ddr


class ActualDDRBoundary(unittest.TestCase):
    def test_actual_previous_routes_and_mutations(self):
        selected=[Path(v)for role in ('M','W')if (v:=os.environ.get('GW138K_PREBOARD_'+role+'_PHYSICAL'))]
        if not selected:self.skipTest('explicit actual previous physical directories required')
        for folder in selected:
            paths=[folder/'physical.cst',folder/'physical.sdc',folder/'impl/pnr/custom_138k_integration.vo']
            before={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}
            cst,sdc=paths[0].read_bytes(),paths[1].read_bytes();vo=paths[2].read_text()
            ct,st,e=ddr.tighten(cst,sdc,vo)
            self.assertTrue(ct.startswith(cst));self.assertEqual(e['minimum_data_delay_ns'],0.8)
            self.assertTrue(e['original_finite_hold_relationship_restored'])
            self.assertTrue(e['clock_skew_and_native_hold_checks_retained'])
            self.assertEqual(e['maximum_functional_reset_delay_ns'],7.5)
            self.assertEqual(st.count(ddr.MINIMUM.encode()),1)
            self.assertEqual(st.count(ddr.MAXIMUM.encode()),1)
            self.assertFalse(e['false_paths_added']);self.assertFalse(e['vendor_bytes_changed'])
            for label,c,s,v in [
                ('duplicate adaptation',ct,st,vo),
                ('duplicate minimum',cst,sdc+ddr.DDR_STRICT_MINIMUM.encode()+b'\n',vo),
                ('weaker prior minimum',cst,sdc.replace(b'3.500',b'0.000'),vo),
                ('swapped region',cst.replace(ddr.DDR_FAR_CAPTURE_REGION.encode(),ddr.DDR_FAR_LAUNCH_REGION.encode()),sdc,vo),
                ('missing functional reset',cst,sdc,vo.replace(ddr.RESET,ddr.RESET+'_missing')),
                ('missing vendor inverse',cst,sdc,vo.replace(ddr.INVERTER+' ',ddr.INVERTER+'_missing ')),
            ]:
                with self.subTest(folder=folder.name,case=label),self.assertRaises(ValueError):
                    ddr.tighten(c,s,v)
            self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths})


if __name__=='__main__':unittest.main()
