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
        options=dict(registered_tx_class=meta.get('w_tx_class',{}).get('policy')=='task3_W_registered_normal_tx_preference_v1')
        from tools.workstation_task3_w_delay_locality import arithmetic_layout
        options.update(fifo_compare_first=bool(meta.get('fifo_full_compare')),
            arithmetic_repair=arithmetic_layout(meta),
            cancel_ready_cofactor=bool(meta.get('w_tx_class',{}).get('record_cancel_ready')),
            combined_admission=meta.get('combined_event_admission',{}).get('policy')=='task3_W_combined_sample_event_admission_v1',
            cnn_retirement=bool(meta.get('cnn_staging_retirement')))
        result,generated=placement(cst,n,**options)
        self.assertEqual(result,(p/'physical.cst').read_bytes())
        self.assertEqual(reconstruct(cst,n,proof,**options),result)
        self.assertEqual(generated['selected_count'],2211 if options['cnn_retirement'] else 2210 if options['combined_admission'] else 2212 if options['cancel_ready_cofactor'] else 2211 if options['arithmetic_repair'] else 2241 if options['fifo_compare_first'] else 2240 if options['registered_tx_class'] else 2233)
        self.assertEqual(len(generated['RAMs_not_in_logic_regions']),8)
        for key,value in [('policy','other'),('before_CST_sha256','0'*64),
                          ('after_CST_sha256','0'*64),('selected_count',2234),
                          ('clocks_changed',True),('timing_exceptions_changed',True),
                          ('old_members_removed',[]),('new_groups',[]),
                          ('RAMs_not_in_logic_regions',[])]:
            bad=copy.deepcopy(proof);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):reconstruct(cst,n,bad,**options)
        path=generated['new_groups'][0]['members'][0]
        cell=n.cells.pop(path)
        try:
            with self.assertRaises(ValueError):placement(cst,n,**options)
        finally:n.cells[path]=cell
        with self.assertRaises(ValueError):placement(result,n,**options)
        print('W locality:',generated['selected_count'],'logic cells, eight RAMs excluded; exact replay and eleven corruptions rejected')


if __name__=='__main__':unittest.main()
