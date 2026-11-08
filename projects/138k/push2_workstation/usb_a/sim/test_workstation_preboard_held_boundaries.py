#!/usr/bin/env python3
"""Actual M/W held boundaries: mutation controls for the observed STA failures."""
from pathlib import Path
import copy,os,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_m_session_boundary import audit as session
from tools.workstation_task3_w_raw_command_capture import audit as raw
from tools.workstation_task3_preboard_held_timing import audit as paired
from tools.workstation_task3_tf_frame_arithmetic import audit as frame

class HeldBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n={}
        for role in ('M','W'):
            stage=os.environ.get('GW138K_PREBOARD_'+role+'_STAGE')
            if stage:cls.n[role]=protocol_netlist((Path(stage)/'impl/gwsynthesis/custom_138k_integration.vg').read_text(),mapping='synthesis')
        if not cls.n:raise unittest.SkipTest('explicit actual stages required')

    def reject(self,n,callback,cases):
        for path,pin,bad in cases:
            with self.subTest(path=path,pin=pin):
                old=copy.deepcopy(n.cells[path]);n.cells[path]['ports'][pin]=bad
                try:
                    with self.assertRaises(ValueError):callback(n)
                finally:n.cells[path]=old

    def test_M_session_and_frame(self):
        if 'M'not in self.n:self.skipTest('M required')
        n=self.n['M'];g=Graph(n);r,sdc=session(n)
        self.assertEqual(len(r['source_stability']),64);self.assertIn('set_min_delay 1.800',sdc);self.assertNotIn('set_false_path',sdc)
        self.reject(n,session,[(g.register('u_task3_m_endpoint','hci_ready_o'),'D',"1'b1"),
            (r['capture'][0],'D',n.cells[r['source'][1]]['ports']['Q']),
            (r['release'][1],'D',"1'b1"),(r['capture'][5],'CE',"1'b1")])
        f=frame(n);self.assertEqual(f['next_Q_equations'],148)
        self.reject(n,frame,[(f['publishers'][0]['binary'][0],'D',"1'b0"),
            (f['publishers'][1]['gray'][10],'D',"1'b1"),
            (f['publishers'][2]['gray'][0],'CE',"1'b1"),
            (f['publishers'][3]['binary'][0],'CLK','clk_50m')])

    def test_W_capture(self):
        if 'W'not in self.n:self.skipTest('W required')
        n=self.n['W'];g=Graph(n);r,sdc=raw(n)
        self.assertEqual(r['tuple_bits'],89);self.assertIn('set_min_delay 1.800',sdc);self.assertNotIn('set_false_path',sdc)
        self.reject(n,raw,[(r['capture'][0],'D',n.cells[r['source'][1]]['ports']['Q']),
            (r['capture'][10],'CE',"1'b1"),
            (g.register('u_task3_media/raw_store','g_command_capture.valid'),'D',"1'b1"),
            (r['toggle_chains'][0]['first'],'D',"1'b0")])

    def test_paired_mailboxes(self):
        for role,n in self.n.items():
            r,sdc=paired(n,role=role);self.assertTrue(r['hold_checks_retained'])
            self.assertNotIn('-hold',sdc);self.assertIn('set_min_delay 1.800',sdc)
            first=r['payloads'][0];src=first['source'][1].rsplit('/',1)[0]
            self.reject(n,lambda n:paired(n,role=role),[
                (first['capture'][0].rsplit('/',1)[0],'D',n.cells[src]['ports']['Q']),
                (r['toggle_chains'][0]['first'],'CE',"1'b0")])

if __name__=='__main__':unittest.main()
