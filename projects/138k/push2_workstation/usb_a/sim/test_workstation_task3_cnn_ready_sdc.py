#!/usr/bin/env python3
"""Exact W readiness SDC selection plus explicit immutable mapped evidence."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_cnn_ready_sdc as ready
from tools import workstation_task3_paired_board as paired


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReadySdc(unittest.TestCase):
    def test_exact_roundtrip_and_legacy_default(self):
        original='# untouched before\n'+ready.BEFORE+'\n# untouched after\n'
        selected,evidence=ready.project(original)
        self.assertEqual(ready.restore(selected,evidence),original)
        self.assertEqual(selected.replace(ready.AFTER,ready.BEFORE),original)
        legacy,old_evidence=paired.adapt_constraints(ROOT,original,'W')
        self.assertEqual(legacy,original+paired.SDC)
        self.assertNotIn('W_CNN_ready_rebinding',old_evidence)
        current,current_evidence=paired.adapt_constraints(ROOT,original,'W',cnn_ready_policy=ready.POLICY)
        self.assertEqual(current,selected+paired.SDC)
        self.assertEqual(paired.restore_constraints(ROOT,current,current_evidence),original)
        self.assertEqual(current_evidence['W_CNN_ready_rebinding'],evidence)
        self.assertEqual(evidence['added_exceptions'],0)
        self.assertFalse(evidence['timing_budgets_changed'])

    def test_classic_runtime_requires_exact_paired_inverse_evidence(self):
        from tools.workstation_classic_runtime import cdc_bundle,verify_cdc_selection
        from tools.workstation_demo_policy import adapt_constraints
        from tools.workstation_task3_w_paired_profile import scoped_constraints
        cdc=cdc_bundle();record={k:v for k,v in cdc.items() if k!='sdc'}
        original,_=adapt_constraints(cdc['sdc'],'W')
        original,_=scoped_constraints(original)
        original=ready.BEFORE+'\n'+original
        legacy,_=paired.adapt_constraints(ROOT,original,'W')
        verify_cdc_selection(legacy,record,worker_demo=True,paired_worker=True)
        selected,evidence=paired.adapt_constraints(ROOT,original,'W',cnn_ready_policy=ready.POLICY)
        verify_cdc_selection(selected,record,worker_demo=True,paired_worker=True,paired_sdc_evidence=evidence)
        for bad in (None,{},dict(evidence,W_CNN_ready_rebinding={})):
            with self.subTest(evidence=bad),self.assertRaises(ValueError):
                verify_cdc_selection(selected,record,worker_demo=True,paired_worker=True,paired_sdc_evidence=bad)

    def test_fail_closed_input_and_evidence(self):
        original=ready.BEFORE+'\n'
        selected,evidence=ready.project(original)
        for sdc in (selected,original+original,original.replace('2.000','3.000'),
                original.replace(ready.FIRST,ready.FIRST+'/D'),
                original.replace(ready.STALE,ready.STALE+' other_register*'),
                original+'# '+ready.STALE+'\n'):
            with self.subTest(sdc=sdc),self.assertRaises(ValueError):ready.project(sdc)
        for sdc in (original,selected+selected,selected.replace('2.000','3.000')):
            with self.subTest(selected=sdc),self.assertRaises(ValueError):ready.restore(sdc,evidence)
        changed=dict(evidence,timing_budgets_changed=True)
        with self.assertRaises(ValueError):ready.restore(selected,changed)
        with self.assertRaises(ValueError):paired.restore_constraints(ROOT,selected+paired.SDC,{})
        for role,policy in ((None,ready.POLICY),('W','unreviewed')):
            with self.assertRaises(ValueError):paired.adapt_constraints(ROOT,original,role,cnn_ready_policy=policy)

    def test_actual_mapped_ready_and_stale_selector_rejection(self):
        selected=os.environ.get('GW138K_TASK3_READY_STAGE')
        if not selected:self.skipTest('explicit immutable synthesized W stage required')
        from tools.workstation_native_protocol_audit import protocol_netlist
        stage=Path(selected);vg=stage/'impl/gwsynthesis/custom_138k_integration.vg'
        paths=[vg,stage/'constraints/custom_138k.sdc',*(stage/p for p in (
            'rtl/music/basic_pitch_workstation_link.sv','rtl/music/workstation_cnn_task_service.sv',
            'rtl/music/workstation_task3_cnn_stream_w.sv'))]
        before={str(p):sha(p) for p in paths}
        original=(stage/'constraints/custom_138k.sdc').read_text()
        if ready.STALE in original:sdc,selection=ready.project(original)
        else:sdc,selection=original,None
        n=protocol_netlist(vg.read_text(),mapping='synthesis');proof=ready.audit(n,sdc,stage=stage)
        negative=[]
        for p in (proof['first'],proof['last']):
            for pin in ('CLK','CE','D','CLEAR'):
                old=copy.deepcopy(n.cells[p])
                try:
                    n.cells[p]['ports'][pin]="1'b0"
                    with self.subTest(register=p,pin=pin),self.assertRaises(ValueError):
                        ready.audit(n,sdc,stage=stage)
                    negative.append(dict(register=p,pin=pin,rejected=True))
                finally:n.cells[p]=old
        with self.assertRaises(ValueError):ready.audit(n,sdc.replace(ready.AFTER,ready.BEFORE),stage=stage)
        self.assertEqual(before,{str(p):sha(p) for p in paths})
        target=os.environ.get('GW138K_TASK3_READY_EVIDENCE')
        if target:Path(target).write_text(json.dumps(dict(passed=True,proof=proof,
            read_only_projection=selection,negative_controls=negative,stale_selector_rejected=True,
            input_sha256=before,inputs_unchanged=True,physical_CDC_accepted=False,
            routed_timing_verified=False,hardware_tested=False),indent=2)+'\n')


if __name__=='__main__':unittest.main()
