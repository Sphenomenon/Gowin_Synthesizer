#!/usr/bin/env python3
"""Destructive controls on the exact fresh W reset/Gray CDC boundaries."""
from pathlib import Path
import copy,json,os,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools import workstation_task3_w_preboard_cdc as cdc

class PreboardCDC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_PREBOARD_W_STAGE')
        if not selected:raise unittest.SkipTest('explicit exact prepared W stage required')
        cls.stage=Path(selected).resolve();cls.metadata=json.loads((cls.stage.parent.parent/'integration_inputs.json').read_text())
        cls.sdc=(cls.stage/'constraints/custom_138k.sdc').read_text()
        cls.n=protocol_netlist((cls.stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text(),mapping='synthesis')

    def test_gray_positive_and_actual_mutants(self):
        n=self.n;g=Graph(n);positive=cdc.audit_gray(n,g)
        self.assertEqual(positive['binary_next_Q_equations'],16)
        self.assertEqual(positive['Gray_next_Q_equations'],15)
        cases=[(positive['second'][4],'D',"1'b0"),
               (positive['first'][7],'CE',"1'b0"),
               (positive['source'][0],'D',"1'b0"),
               (positive['second'][15],'CLK','memory_clk')]
        for p,pin,bad in cases:
            with self.subTest(cell=p,pin=pin):
                old=copy.deepcopy(n.cells[p]);n.cells[p]['ports'][pin]=bad
                try:
                    with self.assertRaises(ValueError):cdc.audit_gray(n,Graph(n))
                finally:n.cells[p]=old
        extra=copy.deepcopy(n.cells[positive['second'][0]])
        extra['ports']['D']=n.cells[positive['first'][0]]['ports']['Q'];extra['ports']['Q']='unreviewed_capture_q'
        n.cells['unreviewed_capture']=extra
        n.scopes['unreviewed_capture']=n.scopes[positive['second'][0]]
        try:
            with self.assertRaises(ValueError):cdc.audit_gray(n,Graph(n))
        finally:
            n.cells.pop('unreviewed_capture');n.scopes.pop('unreviewed_capture')

    def test_exact_SDC_and_local_release_mutants(self):
        cdc.restore(self.sdc,self.metadata['task3_w_preboard_cdc'])
        for old,new in [('set_max_delay 10.000','set_max_delay 20.000'),
                        ('set_false_path -hold','set_false_path'),
                        ('writes_gray_meta_0_s*/D','writes_gray_sync_0_s*/D')]:
            marker=cdc.constraints();self.assertIn(old,marker)
            with self.assertRaises(ValueError):cdc.restore(self.sdc[:-len(marker)]+marker.replace(old,new,1),self.metadata['task3_w_preboard_cdc'])
        g=Graph(self.n);p=g.group(cdc.STREAM,'control_release',3)[1]
        old=copy.deepcopy(self.n.cells[p]);self.n.cells[p]['ports']['D']="1'b1"
        try:
            with self.assertRaisesRegex(ValueError,'reset release shift chain changed'):
                cdc.audit(self.n,self.stage,self.sdc,self.metadata)
        finally:self.n.cells[p]=old

if __name__=='__main__':unittest.main()
