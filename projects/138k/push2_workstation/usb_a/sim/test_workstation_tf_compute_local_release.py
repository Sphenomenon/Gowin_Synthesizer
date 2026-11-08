#!/usr/bin/env python3
"""Keep the TF source inverse and explicit selection separate from board proof."""
from pathlib import Path
from copy import deepcopy
import os
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_tf_compute_local_release as reset
from tools import workstation_tf_failure_path as failure


class TFComputeRelease(unittest.TestCase):
    def test_source_inverse_and_explicit_selection(self):
        config={reset.KEY:reset.POLICY,'demo_role':'M','tf_policy':'task3_m_native_direct_tf_v1'}
        rows=reset.records()
        with tempfile.TemporaryDirectory()as directory:
            stage=Path(directory)
            for relative in (reset.SERVICE,reset.BRIDGE):
                text=(ROOT/relative).read_text();parent=reset.restore(relative,text)
                self.assertEqual(reset.digest(parent),rows[relative]['parent_sha256'])
                path=stage/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            self.assertIsNone(reset.select(stage,{}))
            result=reset.select(stage,config)
            self.assertEqual(result,reset.evidence(stage,config))
            self.assertEqual(failure.normalize((stage/reset.SERVICE).read_bytes()),
                             failure.normalize((ROOT/reset.SERVICE).read_bytes()))
            with self.assertRaises(ValueError):reset.select(stage,config)
            with self.assertRaises(ValueError):reset.configured(dict(config,demo_role='W'))
            for relative,old,new in [
                (reset.SERVICE,'? compute_n:common_n','? source_n:common_n'),
                (reset.SERVICE,'if(!compute_functional_n)begin receipt_request','if(!common_n)begin receipt_request'),
                (reset.SERVICE,'.LOCAL_COMPUTE_RESET_ENABLE(LOCAL_COMPUTE_RESET_ENABLE)',
                               '.LOCAL_COMPUTE_RESET_ENABLE(0)'),
                (reset.BRIDGE,'? compute_reset_n:rst_ni','? source_reset_n:rst_ni'),
                (reset.BRIDGE,'if(invalidate_i)begin source_generation_o','if(!invalidate_i)begin source_generation_o'),
            ]:
                path=stage/relative;text=path.read_text()
                self.assertEqual(text.count(old),1)
                path.write_text(text.replace(old,new,1))
                with self.subTest(source=relative,mutation=old),self.assertRaises(ValueError):
                    reset.evidence(stage,config)
                path.write_text(text)
            self.assertEqual(result,reset.evidence(stage,config))


class ActualComputeRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_PREBOARD_M_STAGE')
        if not selected:raise unittest.SkipTest('explicit actual preboard M stage required')
        from tools.workstation_native_protocol_audit import protocol_netlist
        from tools.workstation_task3_root_reset_audit import audit_root_startup
        cls.stage=Path(selected)
        cls.vg=cls.stage/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.before=reset.digest(cls.vg.read_bytes())
        cls.n=protocol_netlist(cls.vg.read_text(),mapping='synthesis')
        cls.root=audit_root_startup(cls.n,stage=cls.stage)

    @classmethod
    def tearDownClass(cls):
        assert reset.digest(cls.vg.read_bytes())==cls.before

    def test_actual_inventory_and_destructive_controls(self):
        from tools.workstation_runtime_pcm_cdc import Graph
        n=self.n;g=Graph(n)
        proof=reset.audit_mapped(n,stage=self.stage,root=self.root)
        self.assertEqual(proof['functional_compute_register_count'],438)
        self.assertEqual(len(proof['root_asserted_synchronizer_registers']),8)
        functional=g.register('u_tf_audio','receipt_payload',0)
        release=g.group('u_tf_audio/frames','compute_release',3)
        for p,pin,bad in [
            (functional,'CLEAR',n.pin(release[0],'CLEAR')),
            (functional,'CLK','clk_50m'),
            (release[1],'D',"1'b1"),
            (release[0],'CE',"1'b0"),
            (release[2],'CLEAR',n.pin(functional,'CLEAR')),
        ]:
            with self.subTest(register=p,pin=pin):
                old=deepcopy(n.cells[p]);n.cells[p]['ports'][pin]=bad
                try:
                    with self.assertRaises(ValueError):reset.audit_mapped(n,stage=self.stage,root=self.root)
                finally:n.cells[p]=old
        extra='u_tf_audio/unreviewed_compute_s0'
        n.cells[extra]=deepcopy(n.cells[functional]);n.scopes[extra]=n.scopes[functional]
        n.cells[extra]['ports']['Q']='unreviewed_compute_q'
        try:
            with self.assertRaisesRegex(ValueError,'complete compute inventory'):
                reset.audit_mapped(n,stage=self.stage,root=self.root)
        finally:del n.cells[extra];del n.scopes[extra]
        # An otherwise legal source FF must not consume an early compute stage.
        source=g.register('u_tf_audio/frames','source_release',2);old=deepcopy(n.cells[source])
        n.cells[source]['ports']['D']=n.cells[release[0]]['ports']['Q']
        self.assertEqual(n.pin(source,'D'),n.pin(release[0],'Q'))
        try:
            with self.assertRaisesRegex(ValueError,'early release has extra consumer'):
                reset.audit_mapped(n,stage=self.stage,root=self.root)
        finally:n.cells[source]=old


if __name__=='__main__':unittest.main()
