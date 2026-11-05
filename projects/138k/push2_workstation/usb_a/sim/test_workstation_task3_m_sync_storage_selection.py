#!/usr/bin/env python3
"""Actual prepared M selection and rejected partial storage opt-ins."""
from pathlib import Path
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_m_paired_profile as m


class Selection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected=os.environ.get('GW138K_TASK3_M_SYNC_OUTPUT')
        if not selected:raise unittest.SkipTest('explicit prepared candidate required')
        output=Path(selected)
        cls.stage=output/'workstation/Prj1'
        cls.config=json.loads((output/'workstation_profile.json').read_text())['configuration']
        cls.metadata=json.loads((output/'integration_inputs.json').read_text())
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.fixture=Path(cls.temp.name)/'stage'
        shutil.copytree(cls.stage,cls.fixture,ignore=shutil.ignore_patterns('impl'))

    def test_real_selection_and_legacy_default(self):
        actual=m.selected_batch_source_evidence(self.stage,self.stage,self.config,m.SYNC_PROVIDER)
        self.assertEqual(actual,self.metadata['task3_phone_batch'])
        self.assertEqual(actual['local_storage']['tap_capacity_frames'],256)
        self.assertEqual(actual['local_storage']['score_capacity_notes'],2048)
        self.assertFalse(actual['local_storage']['physical_BSRAM_mapping_verified'])
        old=copy.deepcopy(self.config);old.pop('m_endpoint_storage_policy')
        default=m.selected_batch_source_evidence(self.stage,self.stage,old,m.BATCH_PROVIDER)
        self.assertNotIn('local_storage',default)

    def test_partial_selection_rejected(self):
        for provider,value in ((m.BATCH_PROVIDER,m.SYNC_POLICY),(m.SYNC_PROVIDER,None),
                               (m.SYNC_PROVIDER,'unknown'),(m.BATCH_PROVIDER,'unknown')):
            config=dict(self.config,m_endpoint_storage_policy=value)
            with self.subTest(provider=provider,value=value),self.assertRaises(ValueError):
                m.selected_batch_source_evidence(self.stage,self.stage,config,provider)

    def test_wrapper_scope_rejected(self):
        path=self.fixture/m.SYNC_PROVIDER;original=path.read_text()
        for mutated in (original.replace('`define WORKSTATION_TASK3_M_SYNC_STORAGE',''),
                        original.replace('`undef WORKSTATION_TASK3_M_SYNC_STORAGE',''),
                        original+'\n`define WORKSTATION_DEMO_NO_TF\n',
                        original.replace('phone_batch.sv','phone_blocks.sv')):
            path.write_text(mutated)
            with self.subTest(mutated=mutated),self.assertRaises(ValueError):
                m.selected_batch_source_evidence(self.fixture,self.fixture,self.config,m.SYNC_PROVIDER)
        path.write_text(original)

    def test_binding_and_default_rejected(self):
        changes=[(m.BOARD,"defparam u_task3_m_endpoint.SYNC_READ_STORAGE=1'b1;",
                          "defparam u_task3_m_endpoint.SYNC_READ_STORAGE=1'b0;"),
            ('rtl/workstation/workstation_task3_m_bus_endpoint.sv',
             "parameter bit SYNC_READ_STORAGE=1'b0","parameter bit SYNC_READ_STORAGE=1'b1"),
            ('rtl/workstation/workstation_task3_m_bus_endpoint.sv',
             'workstation_task3_score_commit_m #(.SYNC_READ_STORAGE(SYNC_READ_STORAGE))',
             'workstation_task3_score_commit_m #(.SYNC_READ_STORAGE(0))'),
            ('rtl/workstation/workstation_task3_m_bus_endpoint.sv',
             'workstation_task3_final_tap_export #(.SYNC_READ_STORAGE(SYNC_READ_STORAGE))',
             'workstation_task3_final_tap_export #(.SYNC_READ_STORAGE(0))')]
        for relative,old,new in changes:
            path=self.fixture/relative;original=path.read_text();self.assertEqual(original.count(old),1)
            path.write_text(original.replace(old,new))
            with self.subTest(relative=relative,old=old),self.assertRaises(ValueError):
                m.selected_batch_source_evidence(self.fixture,self.fixture,self.config,m.SYNC_PROVIDER)
            path.write_text(original)


if __name__=='__main__':unittest.main()
