"""Replay the actual W physical recipe; reject scope and receipt drift."""
from pathlib import Path
import copy
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_task3_w_delay_locality import placement,reconstruct
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_custom_board_implementation import (
    reference_constraints,primary_clk50_constraints,preboard_constraint_selection)


class WDelayLocality(unittest.TestCase):
    def test_actual_recipe_and_corruptions(self):
        selected=os.environ.get('GW138K_PREBOARD_W_PHYSICAL')
        if not selected:self.skipTest('explicit actual W physical recipe required')
        p=Path(selected);inputs=json.loads((p/'physical_inputs.json').read_text())
        meta=json.loads((p/'parent_integration_inputs.json').read_text())
        audit=json.loads((p/'parent_synthesis_audit.json').read_text())
        stage=Path(inputs['parent_candidate'])/'workstation/Prj1'
        vg=(p/'custom_138k_integration.vg').read_text()
        n=protocol_netlist(vg,mapping='synthesis')
        cst,_=reference_constraints((p/'reference.cst').read_bytes(),vg)
        cst,_=primary_clk50_constraints(cst,vg)
        cst,*_=preboard_constraint_selection(stage,meta,audit,cst,
            (stage/'constraints/custom_138k.sdc').read_bytes(),vg,
            preboard_releases=True,primary_clk50=True,
            ddr_reference=Path(inputs['preboard_ddr_adaptation']['routed_reference']).parents[2])
        proof=inputs['diagnosed_locality']
        result,generated=placement(cst,n)
        self.assertEqual(result,(p/'physical.cst').read_bytes())
        self.assertEqual(reconstruct(cst,n,proof),result)
        self.assertEqual(generated['selected_count'],2233)
        self.assertEqual(len(generated['RAMs_not_in_logic_regions']),8)
        for key,value in [('policy','other'),('before_CST_sha256','0'*64),
                          ('after_CST_sha256','0'*64),('selected_count',2234),
                          ('clocks_changed',True),('timing_exceptions_changed',True),
                          ('old_members_removed',[]),('new_groups',[]),
                          ('RAMs_not_in_logic_regions',[])]:
            bad=copy.deepcopy(proof);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):reconstruct(cst,n,bad)
        path=generated['new_groups'][0]['members'][0]
        cell=n.cells.pop(path)
        try:
            with self.assertRaises(ValueError):placement(cst,n)
        finally:n.cells[path]=cell
        with self.assertRaises(ValueError):placement(result,n)
        print('W locality: 2233 logic cells, eight RAMs excluded; exact replay and eleven corruptions rejected')


if __name__=='__main__':unittest.main()
