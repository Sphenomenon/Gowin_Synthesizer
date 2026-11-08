#!/usr/bin/env python3
"""Positive and destructive controls for actual reset-release exceptions."""
from pathlib import Path
import copy,os,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools import workstation_preboard_physical_boundaries as proof
from tools.workstation_custom_board_implementation import primary_clk50_constraints

class PhysicalBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates=[]
        for role in ('M','W'):
            selected=os.environ.get('GW138K_PREBOARD_'+role+'_STAGE')
            if selected:
                stage=Path(selected).resolve()
                n=protocol_netlist((stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text(),mapping='synthesis')
                cls.candidates.append((role,stage,n))
        if not cls.candidates:raise unittest.SkipTest('explicit actual preboard stage required')

    def test_actual_release_and_mutants(self):
        for role,stage,n in self.candidates:
            positive,sdc=proof.audit(n,role=role,stage=stage)
            compute=positive['tf_compute_functional_reset']
            self.assertEqual(len(positive['exact_CLEAR_pins']),(37 if compute else 29)if role=='M' else 15)
            if compute:
                self.assertEqual(compute['functional_compute_register_count'],438)
                self.assertTrue(set(positive['exact_CLEAR_pins']).isdisjoint(
                    p+'/CLEAR'for p in compute['functional_register_release']))
            if role=='M':
                self.assertNotIn('set_max_delay',sdc)
                self.assertNotIn('-hold',sdc)
            else:
                self.assertEqual(sdc.count('set_false_path -hold '),1)
                self.assertEqual(positive['W_routed_first_captures']['fifo_binary_next_Q_equations'],3)
            g=Graph(n);chain=positive['release_chains'][0]['registers']
            for p,pin,bad in [(chain[1],'D',"1'b1"),(chain[0],'CE',"1'b0"),
                              (chain[2],'CLK','memory_clk')]:
                with self.subTest(role=role,cell=p,pin=pin):
                    old=copy.deepcopy(n.cells[p]);n.cells[p]['ports'][pin]=bad
                    try:
                        with self.assertRaises(ValueError):proof.audit(n,role=role,stage=stage)
                    finally:n.cells[p]=old
            p=chain[0];extra=copy.deepcopy(n.cells[chain[1]])
            extra['ports']['D']=n.cells[p]['ports']['Q'];extra['ports']['Q']='unreviewed_reset_consumer'
            n.cells['extra_reset_consumer_s0']=extra;n.scopes['extra_reset_consumer_s0']=n.scopes[p]
            try:
                with self.assertRaisesRegex(ValueError,'early release extra consumer'):
                    proof.audit(n,role=role,stage=stage)
            finally:n.cells.pop('extra_reset_consumer_s0');n.scopes.pop('extra_reset_consumer_s0')

    def test_primary_clock_is_the_actual_input_with_unchanged_data_and_IO(self):
        for role,stage,n in self.candidates:
            vg=(stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text()
            cst=(stage/'constraints/custom_138k.cst').read_bytes()
            selected,evidence=primary_clk50_constraints(cst,vg)
            self.assertTrue(selected.startswith(cst))
            self.assertGreater(evidence['registered_clock_loads'],1000)
            self.assertFalse(evidence['clock_frequency_changed'])
            with self.assertRaisesRegex(ValueError,'already has'):
                primary_clk50_constraints(selected,vg)
            # An altered top clock-buffer binding must fail before routing.
            wrong=vg.replace('.I(clk_50m)',".I(1'b0)")
            self.assertNotEqual(wrong,vg)
            with self.assertRaisesRegex(ValueError,'exact top input buffer'):
                primary_clk50_constraints(cst,wrong)

if __name__=='__main__':unittest.main()
