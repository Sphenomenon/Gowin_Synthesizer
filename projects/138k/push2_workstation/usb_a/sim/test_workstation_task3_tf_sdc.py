#!/usr/bin/env python3
"""Actual DIRECT TF mailbox selectors and destructive installed-SDC tests."""
from pathlib import Path
import hashlib
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_task3_native_held import audit_direct_tf_owner
from tools.workstation_task3_receipt_audit import audit_direct_receipt
from tools.workstation_task3_root_reset_audit import audit_root_startup
from tools.workstation_task3_tf_sdc_audit import validate_tf_mailbox_sdc


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualTfMailboxSdc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vg,stage=(os.environ.get(key) for key in ('GW138K_TASK3_TF_SDC_VG','GW138K_TASK3_TF_SDC_STAGE'))
        if not vg or not stage:
            raise unittest.SkipTest('explicit matching actual DIRECT VG/stage required; no fallback')
        cls.path,cls.stage=Path(vg),Path(stage)
        cls.sdc_path=cls.stage/'constraints/custom_138k.sdc'
        cls.sdc=cls.sdc_path.read_text()
        cls.n=protocol_netlist(cls.path.read_text(),mapping=os.environ.get('GW138K_TASK3_TF_SDC_MAPPING','synthesis'))
        cls.root=audit_root_startup(cls.n,stage=cls.stage)
        cls.status=audit_direct_tf_owner(cls.n,stage=cls.stage,root=cls.root)
        cls.receipt=audit_direct_receipt(cls.n,root=cls.root,stage=cls.stage)
        cls.mutations,cls.positive,cls.failed=[],None,False
        cls.before={str(path):sha(path) for path in (cls.path,cls.sdc_path,cls.stage/'Prj1.gprj',
            cls.stage/'rtl/tf_audio/workstation_tf_direct_runtime_service.sv')}

    def tearDown(self):
        result=self._outcome.result
        self.__class__.failed |= bool(result.errors or result.failures)

    @classmethod
    def tearDownClass(cls):
        unchanged=cls.before=={path:sha(path) for path in cls.before}
        selected=os.environ.get('GW138K_TASK3_TF_SDC_EVIDENCE')
        if selected:
            Path(selected).write_text(json.dumps(dict(status='PASS' if unchanged and cls.positive and not cls.failed else 'FAIL',
                actual_input_sha256=cls.before, actual_local_tf_mailbox_sdc=cls.positive,
                mutations=cls.mutations,mutation_count=len(cls.mutations),
                inputs_unchanged=unchanged,full_tf_cdc_accepted=False,hardware_tested=False),indent=2)+'\n')
        assert unchanged,'actual input bytes changed'

    def check(self,sdc):
        return validate_tf_mailbox_sdc(sdc,self.n,status=self.status,receipt=self.receipt)

    def test_actual_status_receipt_exact_singleton_producers_and_bounds(self):
        result=self.check(self.sdc)
        self.assertTrue(result['exact_source_and_capture_queries'])
        self.assertEqual(result['exact_status_receipt_synchronizers_verified'],4)
        self.assertEqual((result['status_payload_pins_verified'],result['receipt_payload_pins_verified']),(67,34))
        self.__class__.positive=result

    def test_installed_actual_queries_and_later_state_cannot_be_weakened(self):
        lines=self.sdc.splitlines()
        status_line=next(line for line in lines if line.startswith('set_max_delay') and '/held_status_' in line)
        receipt_line=next(line for line in lines if line.startswith('set_max_delay') and '/receipt_payload_' in line)
        second_line=next(line for line in lines if line.startswith('set_max_delay') and '/status_request_sync_1_s*/D' in line)
        cases=[
            ('status setup bound missing',self.sdc.replace(status_line+'\n','',1)),
            ('status setup bound duplicate',self.sdc+status_line+'\n'),
            ('receipt setup bound missing',self.sdc.replace(receipt_line+'\n','',1)),
            ('receipt setup bound relaxed',self.sdc.replace(receipt_line,receipt_line.replace('20.000','40.000'),1)),
            ('second-stage bound missing',self.sdc.replace(second_line+'\n','',1)),
            ('second-stage bound overridden',self.sdc+second_line.replace('2.000','9.000')+'\n'),
            ('status capture setup cut',self.sdc+'set_false_path -to [get_pins {u_tf_audio/compute_status_1_s*/D}]\n'),
            ('receipt local capture setup cut',self.sdc+'set_false_path -to [get_pins {u_tf_audio/receipt_local_33_s*/D}]\n'),
            ('receipt dispatch setup cut',self.sdc+'set_false_path -to [get_pins {u_tf_audio/receipt_dispatch_s*/D}]\n'),
            ('receipt local register cut',self.sdc+'set_false_path -to [get_regs {u_tf_audio/receipt_local_0_s*}]\n'),
            ('whole-clock setup cut',self.sdc+'set_false_path -from [get_clocks {audio_76m8}] -to [get_clocks {clk_50m}]\n'),
        ]
        for stem in ('status_request','status_ack','receipt_request','receipt_seen'):
            row=next(line for line in lines if line.startswith('set_false_path -from ') and
                     'u_tf_audio/'+stem+'_s[0-9]*/Q' in line)
            wrong=stem if stem!='receipt_seen' else 'receipt_ack'
            replacement=row.replace(stem+'_s[0-9]*/Q',wrong+'_s*/Q')
            cases.append((stem+' source selector captures sync Qs',self.sdc.replace(row,replacement,1)))
        for label,changed in cases:
            with self.subTest(case=label),self.assertRaises(ValueError) as error:
                self.check(changed)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))


if __name__=='__main__':
    unittest.main()
