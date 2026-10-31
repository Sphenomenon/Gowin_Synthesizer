#!/usr/bin/env python3
"""The W role checks its exact final SDC; default Classic keeps its source SDC."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_classic_runtime import cdc_bundle, verify_cdc_selection
from tools.workstation_demo_policy import adapt_constraints


class FinalClassicConstraints(unittest.TestCase):
    def setUp(self):
        bundle=cdc_bundle()
        self.original=bundle['sdc']
        self.record={k:v for k,v in bundle.items() if k!='sdc'}
        self.worker,_=adapt_constraints(self.original,'W')

    def test_explicit_worker_checks_final_preset_paths_and_unchanged_budgets(self):
        verify_cdc_selection(self.worker,self.record,worker_demo=True)
        self.assertIn('pcm_apb.commands/request_held*',self.worker)
        self.assertIn('cpu_pcm.session/epoch_o*',self.worker)
        self.assertIn('pcm_hold_serial*/PRESET',self.worker)
        self.assertIn('set_max_delay 10.000',self.worker)
        self.assertIn('set_max_delay 2.000',self.worker)
        self.assertIn('owner/flow/generations*',self.worker)

    def test_default_classic_keeps_original_lines_and_rejects_worker_paths(self):
        verify_cdc_selection(self.original,self.record)
        with self.assertRaisesRegex(ValueError,'scoped CDC input changed'):
            verify_cdc_selection(self.worker,self.record)
        with self.assertRaisesRegex(ValueError,'scoped CDC input changed'):
            verify_cdc_selection(self.original,self.record,worker_demo=True)

    def test_lost_duplicate_or_relaxed_worker_constraints_fail(self):
        lines=self.worker.splitlines()
        variants=('\n'.join(lines[1:])+'\n',self.worker+lines[0]+'\n',
                  self.worker.replace('set_max_delay 10.000','set_max_delay 100.000',1),
                  self.worker.replace('pcm_hold_serial*/PRESET','pcm_hold_serial*/CLEAR'))
        for changed in variants:
            with self.subTest(changed=changed[:100]),self.assertRaisesRegex(ValueError,'scoped CDC input changed'):
                verify_cdc_selection(changed,self.record,worker_demo=True)

    def test_changed_source_cdc_record_is_rejected(self):
        record=dict(self.record,physical_timing_verified=True)
        with self.assertRaisesRegex(ValueError,'scoped CDC input changed'):
            verify_cdc_selection(self.worker,record,worker_demo=True)


if __name__=='__main__':
    unittest.main()
