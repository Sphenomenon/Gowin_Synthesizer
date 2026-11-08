"""Actual M Gray publisher arithmetic, including absorbed LSB event enables."""
from pathlib import Path
from copy import deepcopy
import json,os,sys,unittest,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_task3_tf_frame_arithmetic import audit
from tools.workstation_runtime_pcm_cdc import Graph

class ActualFrameArithmetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_TASK3_TF_FRAME_STAGE')
        if not selected:raise unittest.SkipTest('explicit actual M synthesis stage required')
        cls.vg=Path(selected)/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.n=protocol_netlist(cls.vg.read_text(),mapping='synthesis')
        cls.sha=hashlib.sha256(cls.vg.read_bytes()).hexdigest()
        cls.positive=audit(cls.n);cls.mutations=[]

    def test_actual_binary_gray_invariant(self):
        self.assertEqual(len(self.positive['publishers']),4)
        for row in self.positive['publishers']:
            self.assertTrue(row['registered_Gray_invariant_inductive'])
            self.assertTrue(row['at_most_one_changed_Gray_bit_per_source_edge'])

    def test_real_enable_D_and_Gray_mutations(self):
        n=self.n;g=Graph(n);generation=self.positive['publishers'][0]
        binary,gray=generation['binary'],generation['gray']
        dcell=g.drivers[n.pin(binary[0],'D')][0][0]
        cases=[('LSB truth',dcell,'parameters','INIT',"16'h0000"),
               ('generation high-bit CE',binary[1],'ports','CE',"1'b0"),
               ('generation high-bit D',binary[15],'ports','D',"1'b0"),
               ('generation Gray D',gray[0],'ports','D',"1'b0"),
               ('generation reset',binary[0],'ports','CLEAR',"1'b0")]
        guard=generation['absorbed_LSB_event_proof']
        if guard:cases.append(('event LUT truth',guard['actual_event_LUT'],'parameters','INIT',"8'h00"))
        for label,path,section,key,value in cases:
            old=deepcopy(n.cells[path]);n.cells[path][section][key]=value
            try:
                with self.subTest(case=label),self.assertRaises(ValueError):audit(n)
                self.mutations.append(dict(case=label,rejected=True))
            finally:n.cells[path]=old

    @classmethod
    def tearDownClass(cls):
        assert hashlib.sha256(cls.vg.read_bytes()).hexdigest()==cls.sha
        target=os.environ.get('GW138K_TASK3_TF_FRAME_EVIDENCE')
        if target:Path(target).write_text(json.dumps(dict(actual_arithmetic=cls.positive,
            mutations=cls.mutations,netlist_sha256=cls.sha,inputs_unchanged=True,
            routed_timing_verified=False,hardware_tested=False),indent=2)+'\n')

if __name__=='__main__':unittest.main()
