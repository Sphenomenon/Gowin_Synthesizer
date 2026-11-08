#!/usr/bin/env python3
"""Explicit selection and actual W count publication mutation controls."""
from pathlib import Path
from copy import deepcopy
import json,os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_ble_completion_publication as publication

class Selection(unittest.TestCase):
    def test_inverse_role_and_source_mutants(self):
        current=(ROOT/publication.SOURCE).read_text();parent=publication.restore(current)
        manifest=json.loads((ROOT/publication.MANIFEST).read_text())
        self.assertEqual(publication.digest(parent),manifest['parent_sha256'])
        config={publication.KEY:publication.POLICY,'demo_role':'W',
                'preboard_cdc_policy':'task3_W_proven_release_and_CNN_drain_CDC_v1'}
        with tempfile.TemporaryDirectory()as directory:
            stage=Path(directory);path=stage/publication.SOURCE;path.parent.mkdir(parents=True);path.write_text(current)
            self.assertIsNone(publication.select(stage,{}))
            result=publication.select(stage,config)
            self.assertEqual(result['public_ACK_added_memory_clocks'],1)
            self.assertEqual(publication.unselect(path.read_text()),current)
            self.assertEqual(publication.restore(path.read_text()),parent)
            with self.assertRaises(ValueError):publication.select(stage,config)
            with self.assertRaises(ValueError):publication.configured(dict(config,demo_role='M'))
        for old,new in [('completion_zero ? 32\'d0:completion_count_snapshot',"32'd0"),
                        ('if(completion_ready==command_ack)completion_count_snapshot<=memory_committed;',
                         'completion_count_snapshot<=memory_committed;'),
                        ('completion_ready:command_ack','command_ack:command_ack')]:
            self.assertEqual(current.count(old),1)
            with self.subTest(mutation=old),self.assertRaises(ValueError):
                publication.restore(current.replace(old,new,1))

class Actual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage=os.environ.get('GW138K_PREBOARD_W_STAGE')
        if not stage:raise unittest.SkipTest('explicit immutable selected complete W stage required')
        from tools.workstation_native_protocol_audit import protocol_netlist
        cls.vg=Path(stage)/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.before=publication.digest(cls.vg.read_bytes());cls.n=protocol_netlist(cls.vg.read_text(),mapping='synthesis')

    @classmethod
    def tearDownClass(cls):assert publication.digest(cls.vg.read_bytes())==cls.before

    def test_exact_publication_and_corruptions(self):
        from tools.workstation_runtime_pcm_cdc import Graph
        n=self.n;g=Graph(n);proof=publication.audit_mapped(n)
        self.assertEqual(proof['count_bits'],32)
        scope='u_task3_media/raw_store'
        ack=g.register(scope,'command_ack');count=g.register(scope,'completion_committed',0)
        snap=g.register(scope,'completion_count_snapshot',0)
        for p,pin,bad in [(ack,'D',"1'b0"),(count,'CLK','clk_50m'),
                          (count,'D',"1'b0"),(snap,'CE',"1'b1"),(snap,'CLEAR',"1'b0")]:
            old=deepcopy(n.cells[p]);n.cells[p]['ports'][pin]=bad
            try:
                with self.subTest(register=p,pin=pin),self.assertRaises(ValueError):publication.audit_mapped(n)
            finally:n.cells[p]=old

if __name__=='__main__':unittest.main()
