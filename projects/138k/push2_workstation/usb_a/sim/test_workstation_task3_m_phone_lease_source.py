"""Reject unselected or incomplete source-clock lease/reset adaptations."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_m_phone_lease_source as lease


class SourceLease(unittest.TestCase):
    def setUp(self):
        self.parent=(ROOT/lease.BOARD).read_text()
        self.selected=lease.apply(self.parent)
        self.config={lease.KEY:lease.POLICY,'demo_role':'M',
            'phone_batch_policy':'full_key_atomic_owner_snapshot_command_v1',
            'm_phone_identity_compare_policy':'task3_m_phone_full96_identity_group8_v1'}
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stage=Path(self.temp.name)
        self.board=self.stage/lease.BOARD
        self.board.parent.mkdir(parents=True)

    def test_exact_roundtrip_and_other_bytes_remain_frozen(self):
        self.assertEqual(lease.restore(self.selected),self.parent)
        self.assertEqual(lease.digest(self.parent),lease.PARENT_SHA256)
        with self.assertRaises(ValueError):lease.apply(self.selected)
        with self.assertRaises(ValueError):lease.apply(self.parent+'\n')
        self.assertEqual(self.selected.count('task3_m_phone_live_source;'),1)

    def test_tampered_source_reset_clock_or_consumers_rejected(self):
        for before,after in [
            ('task3_m_phone_live_source<=task3_m_phone_live;','task3_m_phone_live_source<=1\'b1;'),
            ('task3_m_owner_live_sync[1:0],task3_m_phone_live_source}',
             'task3_m_owner_live_sync[1:0],task3_m_phone_live}'),
            ('(!TASK3_PHONE_BATCH || task3_m_phone_live_source)','(!TASK3_PHONE_BATCH || task3_m_phone_live)'),
            ('reg task3_m_phone_live_source','reg [1:0] task3_m_phone_live_source'),
            ('task3_m_phone_live_source<=0','task3_m_phone_live_source<=1'),
            ('wire task3_m_analysis_start','wire unrelated_task3_analysis_start')]:
            self.assertEqual(self.selected.count(before),1)
            with self.subTest(before=before),self.assertRaises(ValueError):
                lease.restore(self.selected.replace(before,after,1))

    def test_explicit_selection_and_preprocessed_binding_required(self):
        self.board.write_text(self.parent)
        self.assertIsNone(lease.selection(self.stage,{},self.parent))
        lease.prepare(self.stage,self.config)
        evidence=lease.selection(self.stage,self.config,self.selected)
        self.assertEqual(evidence['maximum_additional_delay_ns'],20)
        self.assertFalse(evidence['physical_CDC_accepted'])
        for config,top in [({},self.selected),(self.config,self.parent),
                           (dict(self.config,demo_role='W'),self.selected),
                           (dict(self.config,phone_batch_policy=None),self.selected),
                           (dict(self.config,m_phone_identity_compare_policy=None),self.selected),
                           (dict(self.config,**{lease.KEY:'unknown'}),self.selected)]:
            with self.subTest(config=config),self.assertRaises(ValueError):
                lease.selection(self.stage,config,top)


class ActualMappedLease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_TASK3_LEASE_STAGE')
        if not selected:raise unittest.SkipTest('explicit actual v17 stage required')
        from tools.workstation_native_protocol_audit import protocol_netlist
        from tools.workstation_runtime_pcm_cdc import Graph
        from tools import workstation_task3_phone_batch_mapped_m as mapped
        cls.stage=Path(selected)
        cls.vg=cls.stage/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.n=protocol_netlist(cls.vg.read_text(),mapping='synthesis')
        cls.g=Graph(cls.n);cls.mapped=mapped
        def top_ff(net):
            found=[p for p in cls.g.regs if cls.n.scopes[p]=='' and
                   cls.n.pin(p,'Q')==cls.n.canonical('',net)]
            if len(found)!=1:raise ValueError('actual top register missing/duplicate: '+net)
            return found[0]
        cls.source=top_ff('task3_m_phone_live_source')
        cls.sync=top_ff('task3_m_owner_live_sync[0]')
        cls.extra=top_ff('task3_m_idle_sync[0]')
        cls.before=hashlib.sha256(cls.vg.read_bytes()).hexdigest()
        cls.rejections=[];cls.positive=None

    def setUp(self):
        type(self).result=self._outcome.result

    @classmethod
    def tearDownClass(cls):
        unchanged=hashlib.sha256(cls.vg.read_bytes()).hexdigest()==cls.before
        target=os.environ.get('GW138K_TASK3_LEASE_EVIDENCE')
        if target:Path(target).write_text(json.dumps(dict(positive=cls.positive,
            rejections=cls.rejections,netlist_unchanged=unchanged,
            passed=cls.result.wasSuccessful() and unchanged),indent=2)+'\n')
        assert unchanged

    def test_actual_source_register_mailbox_and_owner_mapping(self):
        proof=self.mapped.audit(self.n,stage=self.stage)
        rows=[x for x in proof['proofs'] if 'source lease' in x['contract']]
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x['exact'] for x in rows))
        self.assertEqual(len(rows[1]['ff_endpoints']),7)
        self.assertTrue(proof['observer_reset_and_owner_root_separation_verified'])
        type(self).positive=proof

    def test_mapped_source_and_observer_faults_rejected(self):
        n=self.n
        mailbox=self.g.group(self.mapped.MAILBOX,'p_release',3)[0]
        raw=n.canonical('','task3_m_phone_live')
        cases=[(self.source,'ports','CLK','audio_clk'),
               (self.source,'ports','D',"1'b1"),
               (self.source,'ports','CE',"1'b0"),
               (self.source,'ports','CLEAR',n.pin(mailbox,'CLEAR')),
               (self.source,'parameters','INIT',"1'b1"),
               (self.sync,'ports','D',raw),
               (mailbox,'ports','CLEAR',"1'b0"),
               (self.extra,'ports','D',n.cells[self.source]['ports']['Q'])]
        for path,section,pin,value in cases:
            original=copy.deepcopy(n.cells[path])
            try:
                n.cells[path][section][pin]=value
                with self.subTest(path=path,pin=pin),self.assertRaises(ValueError):
                    self.mapped.audit(n,stage=self.stage)
                self.rejections.append(dict(path=path,pin=pin,rejected=True))
            finally:n.cells[path]=original

    def test_source_policy_and_profile_cannot_borrow_historical_admission(self):
        from tools import workstation_task3_root_reset_audit as roots
        original=json.loads((self.stage.parent.parent/'workstation_profile.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'candidate';stage=output/'workstation/Prj1'
            shutil.copytree(self.stage,stage,ignore=shutil.ignore_patterns('impl'))
            artifact=output/'workstation_profile.json'
            changes=[('missing policy',lambda x:x['configuration'].pop(lease.KEY)),
                     ('unknown policy',lambda x:x['configuration'].update({lease.KEY:'unknown'})),
                     ('old profile',lambda x:x.update(profile='custom138k-workstation-task3-m-paired-checkpoint-v16')),
                     ('wrong role',lambda x:x['configuration'].update(demo_role='W'))]
            for label,change in changes:
                value=copy.deepcopy(original);change(value);artifact.write_text(json.dumps(value))
                with self.subTest(case=label),self.assertRaises(ValueError):
                    self.mapped.source_evidence(stage)
                self.rejections.append(dict(case=label,rejected=True))
        source=roots.source_binding(self.stage)
        self.assertEqual(source['root_mapping_variant'],lease.ROOT_VARIANT)
        for variant in (roots.PHONE_GROUPED_ROOT_VARIANT,roots.GROUPED_ROOT_VARIANT):
            with self.assertRaises(ValueError):roots.publisher_policy(dict(source,root_mapping_variant=variant))
            self.rejections.append(dict(wrong_variant=variant,rejected=True))


if __name__=='__main__':unittest.main()
