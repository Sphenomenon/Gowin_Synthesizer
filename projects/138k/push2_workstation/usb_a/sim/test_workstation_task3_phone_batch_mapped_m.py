#!/usr/bin/env python3
"""Actual M mapped command/snapshot proof with destructive controls; no EDA."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_phone_batch_mapped_m as mapped
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualMappedM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_TASK3_BATCH_MAPPED_M_STAGE')
        if not selected:
            raise unittest.SkipTest('explicit actual M batch stage required; no cache fallback')
        cls.stage=Path(selected).resolve()
        cls.vg=cls.stage/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.n=protocol_netlist(cls.vg.read_text(),mapping='synthesis')
        source=mapped.source_evidence(cls.stage)
        cls.before={str(p):sha(p) for p in (cls.vg,Path(__file__),
            ROOT/'tools/workstation_task3_phone_batch_mapped_m.py',
            cls.stage.parent.parent/'workstation_profile.json',
            *(cls.stage/p for p in source['root_source']['source_sha256']),
            *(cls.stage/p for p in mapped.SOURCE_SHA256))}
        cls.evidence=dict(positive=None,rejections=[],inputs_mutated=False,
            complete_APB_protocol_verified=False,whole_executor_state_machine_verified=False,
            physical_CDC_accepted=False,routed_timing_verified=False,hardware_tested=False)

    def setUp(self):
        type(self).result=self._outcome.result

    @classmethod
    def tearDownClass(cls):
        unchanged=cls.before=={p:sha(p) for p in cls.before}
        target=os.environ.get('GW138K_TASK3_BATCH_MAPPED_M_EVIDENCE')
        if target:
            Path(target).write_text(json.dumps(dict(cls.evidence,
                passed=cls.result.wasSuccessful() and unchanged,
                input_sha256=cls.before,inputs_unchanged=unchanged,
                negative_control_count=len(cls.evidence['rejections'])),indent=2)+'\n')
        assert unchanged,'immutable M stage or auditor changed during checks'

    def rejected(self,label,call):
        with self.assertRaises((ValueError,FileNotFoundError)) as error:
            call()
        self.evidence['rejections'].append(dict(case=label,rejected=True,error=str(error.exception)))

    def test_01_actual_local_mapping(self):
        proof=mapped.audit(self.n,stage=self.stage)
        self.assertTrue(proof['mapped_structure_verified'])
        self.assertEqual(proof['executor_snapshot_FFs'],640)
        self.assertEqual(proof['owner_snapshot_FFs'],414)
        self.assertEqual(proof['owner_snapshot_word_FFs'],381)
        self.assertEqual(proof['mailbox_request_bits'],49)
        self.assertEqual(proof['mailbox_response_bits'],33)
        self.assertTrue(proof['owner_read090_atomic_capture_verified'])
        self.assertFalse(proof['whole_executor_state_machine_verified'])
        self.assertFalse(proof['owner_snapshot_read_mux_verified'])
        self.assertFalse(proof['functional_batch_acceptance'])
        self.evidence['positive']=proof

    def test_02_actual_register_and_boundary_mutants(self):
        n,g=self.n,Graph(self.n)
        reg=lambda scope,stem,bit=None:g.register(scope,stem,bit)
        snap=reg(mapped.BATCH,'snapshot[0]',0)
        words=reg(mapped.OWNER,'g_snapshot.words[2]',0)
        capture=reg(mapped.OWNER,'g_snapshot.capture_id',0)
        valid=reg(mapped.OWNER,'g_snapshot.valid')
        request=reg(mapped.MAILBOX,'request_held',0)
        local=reg(mapped.MAILBOX,'request_local',0)
        response=reg(mapped.MAILBOX,'response_held',0)
        returned=reg(mapped.MAILBOX,'response_local',0)
        toggle=reg(mapped.MAILBOX,'request_toggle')
        sync=reg(mapped.MAILBOX,'req_meta')
        owner=reg(mapped.OWNER,'active_controller',0)
        found=[p for p in g.regs if n.scopes[p]=='' and
               n.pin(p,'Q')==n.canonical('','task3_m_owner_live_sync[0]')]
        self.assertEqual(len(found),1)
        live=found[0]
        cases=[
            ('executor snapshot INIT',snap,'parameters','INIT',"1'b1"),
            ('executor snapshot clock',snap,'ports','CLK',"1'b0"),
            ('executor snapshot reset',snap,'ports','CLEAR',"1'b0"),
            ('executor snapshot response',snap,'ports','D',"1'b0"),
            ('owner snapshot INIT',words,'parameters','INIT',"1'b1"),
            ('owner snapshot clock',words,'ports','CLK',"1'b0"),
            ('owner snapshot observer-reset borrowing',words,'ports','CLEAR',n.pin(request,'CLEAR')),
            ('owner snapshot data disconnected',words,'ports','D',"1'b0"),
            ('owner snapshot capture CE',words,'ports','CE',"1'b0"),
            ('capture ID increment',capture,'ports','D',"1'b0"),
            ('capture ID enable',capture,'ports','CE',"1'b0"),
            ('valid reset',valid,'ports','CLEAR',"1'b0"),
            ('valid stuck data',valid,'ports','D',"1'b0"),
            ('request word disconnected',request,'ports','D',"1'b0"),
            ('request local disconnected',local,'ports','D',"1'b0"),
            ('request capture enable',local,'ports','CE',"1'b0"),
            ('response disconnected',response,'ports','D',"1'b0"),
            ('returned response disconnected',returned,'ports','D',"1'b0"),
            ('response capture enable',response,'ports','CE',"1'b0"),
            ('request toggle no command',toggle,'ports','D',n.pin(toggle,'Q')),
            ('request toggle INIT',toggle,'parameters','INIT',"1'b1"),
            ('request synchronizer bypass',sync,'ports','D',"1'b0"),
            ('live chain clock',live,'ports','CLK',"1'b0"),
            ('original owner observer-reset borrowing',owner,'ports','CLEAR',n.pin(request,'CLEAR')),
            ('unknown FF port',words,'ports','UNREVIEWED',"1'b0"),
            ('unknown FF parameter',words,'parameters','UNREVIEWED','1'),
        ]
        for label,p,section,key,value in cases:
            original=copy.deepcopy(n.cells[p])
            try:
                n.cells[p][section][key]=value
                self.rejected(label,lambda:mapped.audit(n,stage=self.stage))
            finally:n.cells[p]=original
        old=n.cells.pop(snap)
        try:self.rejected('missing executor snapshot bit',lambda:mapped.audit(n,stage=self.stage))
        finally:n.cells[snap]=old
        old=n.frames[mapped.BATCH]['kind']
        try:
            n.frames[mapped.BATCH]['kind']='unreviewed_batch'
            self.rejected('wrong batch implementation',lambda:mapped.audit(n,stage=self.stage))
        finally:n.frames[mapped.BATCH]['kind']=old

    def test_03_exact_consumed_sources(self):
        with tempfile.TemporaryDirectory(prefix='task3-M-mapped-source-fixture-') as temp:
            output=Path(temp)/'fixture'
            stage=output/'workstation/Prj1'
            shutil.copytree(self.stage,stage,ignore=shutil.ignore_patterns('impl'))
            shutil.copyfile(self.stage.parent.parent/'workstation_profile.json',output/'workstation_profile.json')
            mapped.source_evidence(stage)
            for relative in mapped.SOURCE_SHA256:
                p=stage/relative
                original=p.read_bytes()
                for missing in (False,True):
                    if missing:p.unlink()
                    else:p.write_bytes(original+b'\n// altered test source\n')
                    self.rejected(('missing ' if missing else 'changed ')+relative,
                        lambda:mapped.source_evidence(stage))
                    p.write_bytes(original)


if __name__=='__main__':
    unittest.main()
