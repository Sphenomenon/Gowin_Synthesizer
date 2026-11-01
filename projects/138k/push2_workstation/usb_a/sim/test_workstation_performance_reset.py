#!/usr/bin/env python3
"""Destructive tests against an explicitly selected real performance netlist."""
from contextlib import contextmanager
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_performance_reset import audit,netlist,proposed_constraints,validate_sdc,SCOPE
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_performance_reset import (
    DEMO_TIMING_TOOL, demo_clock_reports, select_demo_timing, verify_demo_timing,
    DEMO_TIMING_POLICY, DEMO_TIMING_LEGACY_POLICY, demo_timing_metadata,
    demo_held_handshake_constraints,
)


class DemoBuildSelection(unittest.TestCase):
    def w_return_stage(self, stage):
        from tools import workstation_w_return_mailbox_cdc as mailbox
        for relative in (DEMO_TIMING_TOOL, mailbox.TOOL, mailbox.RAW_STORE_PATH):
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        return mailbox

    def test_w_return_v3_is_explicit_and_seals_helper_and_raw_sources(self):
        import hashlib
        from tools.workstation_performance_reset import W_RETURN_TIMING_POLICY
        with tempfile.TemporaryDirectory(prefix='w-return-timing-v3-') as directory:
            stage = Path(directory)
            mailbox = self.w_return_stage(stage)
            original = '# retained upstream\n'
            selected, evidence = select_demo_timing(stage, original, 'W',
                                                    policy=W_RETURN_TIMING_POLICY)
            self.assertEqual(evidence['policy'], W_RETURN_TIMING_POLICY)
            self.assertEqual(len(evidence['added_lines']), 21)
            self.assertEqual(evidence['added_lines'][-2:], mailbox.constraints().splitlines())
            self.assertIsInstance(evidence['return_mailbox'], dict)
            self.assertTrue(evidence['return_mailbox'])
            encoded = json.dumps(evidence['return_mailbox'], sort_keys=True)
            self.assertIn(hashlib.sha256((stage / mailbox.TOOL).read_bytes()).hexdigest(), encoded)
            self.assertIn(mailbox.RAW_STORE_SHA256, encoded)
            self.assertTrue(verify_demo_timing(stage, selected, 'W', evidence)['installed_lines_verified'])
            default, old = select_demo_timing(stage, original, 'W')
            self.assertEqual(old['policy'], DEMO_TIMING_POLICY)
            self.assertEqual(len(old['added_lines']), 19)
            self.assertNotIn('return_mailbox', old)
            self.assertNotIn(mailbox.constraints(), default)
            for line in mailbox.constraints().splitlines():
                for changed in (selected.replace(line + '\n', '', 1), selected + line + '\n'):
                    with self.subTest(line=line), self.assertRaises(ValueError):
                        verify_demo_timing(stage, changed, 'W', evidence)
            for relative in (mailbox.TOOL, mailbox.RAW_STORE_PATH):
                source = stage / relative
                saved = source.read_bytes()
                source.write_bytes(saved + b'\n// cache test source drift\n')
                with self.subTest(source=relative), self.assertRaises((ValueError, OSError)):
                    verify_demo_timing(stage, selected, 'W', evidence)
                source.write_bytes(saved)
                source.unlink()
                with self.subTest(missing=relative), self.assertRaises((ValueError, OSError)):
                    verify_demo_timing(stage, selected, 'W', evidence)
                source.write_bytes(saved)
            altered = dict(evidence, return_mailbox=dict(evidence['return_mailbox'], unsealed_test=True))
            with self.assertRaises(ValueError):
                verify_demo_timing(stage, selected, 'W', altered)

    def test_w_return_v3_cannot_be_selected_or_replayed_for_m(self):
        from tools.workstation_performance_reset import W_RETURN_TIMING_POLICY
        with tempfile.TemporaryDirectory(prefix='w-return-role-v3-') as directory:
            stage = Path(directory)
            self.w_return_stage(stage)
            with self.assertRaises(ValueError):
                select_demo_timing(stage, '# retained upstream\n', 'M',
                                   policy=W_RETURN_TIMING_POLICY)
            selected, evidence = select_demo_timing(stage, '# retained upstream\n', 'W',
                                                    policy=W_RETURN_TIMING_POLICY)
            with self.assertRaises(ValueError):
                verify_demo_timing(stage, selected, 'M', evidence)

    def test_old_m_and_w_policies_need_no_return_helper_and_reject_its_lines(self):
        import hashlib
        from tools import workstation_w_return_mailbox_cdc as mailbox
        with tempfile.TemporaryDirectory(prefix='old-demo-no-return-helper-') as directory:
            stage = Path(directory)
            tool = stage / DEMO_TIMING_TOOL
            tool.parent.mkdir(parents=True)
            tool.write_text('sealed historical timing owner\n')
            digest = hashlib.sha256(tool.read_bytes()).hexdigest()
            self.assertFalse((stage / mailbox.TOOL).exists())
            self.assertFalse((stage / mailbox.RAW_STORE_PATH).exists())
            for role in ('M', 'W'):
                for legacy in (True, False):
                    evidence = demo_timing_metadata(role, digest, legacy=legacy)
                    selected = '\n'.join(evidence['added_lines']) + '\n'
                    with self.subTest(role=role, legacy=legacy):
                        self.assertTrue(verify_demo_timing(stage, selected, role, evidence)['installed_lines_verified'])
                        self.assertNotIn('return_mailbox', evidence)
                        self.assertNotIn(mailbox.constraints(), selected)
                        with self.assertRaises(ValueError):
                            verify_demo_timing(stage, selected + mailbox.constraints(), role, evidence)
                with self.subTest(role=role, evidence=None), self.assertRaises(ValueError):
                    verify_demo_timing(stage, mailbox.constraints(), role, None)

    def test_role_specific_selection_is_sealed_and_cannot_omit_lines(self):
        with tempfile.TemporaryDirectory(prefix='demo-runtime-timing-') as directory:
            stage=Path(directory);tool=stage/DEMO_TIMING_TOOL;tool.parent.mkdir()
            tool.write_bytes((ROOT/DEMO_TIMING_TOOL).read_bytes())
            for role in ('M','W'):
                sdc,evidence=select_demo_timing(stage,'# retained upstream\n',role)
                self.assertTrue(verify_demo_timing(stage,sdc,role,evidence)['installed_lines_verified'])
                self.assertEqual('source_release' in sdc,role=='W')
                self.assertEqual(sdc.count('report_timing'),4)
                self.assertEqual(evidence['policy'], DEMO_TIMING_POLICY)
                self.assertEqual(len(evidence['added_lines']), 14 if role == 'M' else 19)
                self.assertTrue(evidence['held_handshake_constraints_added'])
                self.assertFalse(evidence['whole_clock_exceptions_added'])
                self.assertNotIn('clock_or_business_exceptions_added', evidence)
                self.assertEqual(evidence['held_handshake_payload_bits'],dict(pc_request=8,apb_request=49))
                self.assertEqual(evidence['toggle_first_stage_exception_count'],3)
                for line in evidence['added_lines']:
                    for changed in (sdc.replace(line+'\n','',1),sdc+line+'\n'):
                        with self.subTest(role=role,line=line),self.assertRaisesRegex(ValueError,'absent or duplicated'):
                            verify_demo_timing(stage,changed,role,evidence)
                with self.assertRaisesRegex(ValueError,'lack sealed selection'):
                    verify_demo_timing(stage,sdc,role,None)
                with self.assertRaisesRegex(ValueError,'already installed'):
                    select_demo_timing(stage,sdc,role)
                with self.assertRaisesRegex(ValueError,'selection metadata changed'):
                    verify_demo_timing(stage,sdc,role,dict(evidence,role='X'))
            tool.write_text('changed helper\n')
            with self.assertRaisesRegex(ValueError,'source identity changed'):
                verify_demo_timing(stage,sdc,role,evidence)

    def test_legacy_and_exact_report_whitelist(self):
        from tools.workstation_runtime_cdc import NATIVE_PERIPHERAL_SDC, PERIPHERAL_SDC
        self.assertEqual(verify_demo_timing(ROOT,'# original\n','W',None)['mode'],
                         'sealed_legacy_without_demo_timing_additions')
        self.assertTrue(all(line in NATIVE_PERIPHERAL_SDC and line not in PERIPHERAL_SDC
                            for line in demo_clock_reports().splitlines()))

    def test_legacy_v1_keeps_original_lines_without_upgrading(self):
        import hashlib
        with tempfile.TemporaryDirectory(prefix='legacy-demo-runtime-timing-') as directory:
            stage=Path(directory);tool=stage/DEMO_TIMING_TOOL;tool.parent.mkdir()
            tool.write_text('sealed historical timing owner\n')
            digest=hashlib.sha256(tool.read_bytes()).hexdigest()
            for role in ('M','W'):
                evidence=demo_timing_metadata(role,digest,legacy=True)
                sdc='\n'.join(evidence['added_lines'])+'\n'
                self.assertEqual(evidence['policy'],DEMO_TIMING_LEGACY_POLICY)
                self.assertEqual(len(evidence['added_lines']),4 if role=='M' else 9)
                self.assertTrue(verify_demo_timing(stage,sdc,role,evidence)['installed_lines_verified'])
                with self.assertRaisesRegex(ValueError,'legacy DEMO timing cannot acquire'):
                    verify_demo_timing(stage,sdc+demo_held_handshake_constraints(),role,evidence)


class ActualRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('GW138K_PERFORMANCE_NETLIST')
        if not path:raise unittest.SkipTest('explicit real GW138K_PERFORMANCE_NETLIST required')
        cls.mapping=os.environ.get('GW138K_PERFORMANCE_MAPPING','synthesis')
        cls.n=netlist(Path(path).read_text(),mapping=cls.mapping)
        cls.index=Graph(cls.n)
        cls.mutations=[]

    @classmethod
    def tearDownClass(cls):
        selected=os.environ.get('GW138K_PERFORMANCE_EVIDENCE')
        if selected:Path(selected).write_text(json.dumps(dict(mapping=cls.mapping,mutations=cls.mutations,
            all_rejected=all(row['rejected'] for row in cls.mutations),physical_accepted=False),indent=2)+'\n')

    def reg(self,stem,bit=None):return self.index.register(SCOPE,stem,bit)

    @contextmanager
    def change(self,p,part,key,value):
        old=self.n.cells[p][part].get(key)
        self.n.cells[p][part][key]=value
        try:yield
        finally:
            if old is None:del self.n.cells[p][part][key]
            else:self.n.cells[p][part][key]=old

    def reject(self,p,part,key,value,message):
        with self.change(p,part,key,value),self.assertRaisesRegex(ValueError,message) as error:
            audit(self.n,mapping=self.mapping)
        self.mutations.append(dict(cell=p,key=key,rejected=True,error=str(error.exception)))

    def test_actual_six_clear_and_same_domain_functional_closure(self):
        r=audit(self.n,mapping=self.mapping)
        self.assertEqual(len(r['release_clear_pins']),6)
        self.assertEqual(len(r['chains']),2)
        checked=validate_sdc(proposed_constraints(),self.n,r)
        self.assertTrue(checked['functional_recovery_removal_exceptions_absent'])

    def test_initial_stage_cannot_hold_low_instead_of_releasing(self):
        p=self.reg('source_release',0)
        with self.change(p,'ports','D',"1'b0"),self.assertRaisesRegex(ValueError,'fill/bypass'):
            audit(self.n,mapping=self.mapping)
        self.mutations.append(dict(case='async receiver first-stage held zero',rejected=True))

    def test_async_receiver_cannot_be_a_synchronous_reset_primitive(self):
        p=self.reg('source_release',0);old=self.n.cells[p]['kind'];self.n.cells[p]['kind']='DFFRE'
        try:
            with self.assertRaisesRegex(ValueError,'release clock/CE'):
                audit(self.n,mapping=self.mapping)
        finally:self.n.cells[p]['kind']=old
        self.mutations.append(dict(case='async receiver changed to synchronous reset primitive',rejected=True))

    def test_release_must_use_its_own_clock(self):
        self.reject(self.reg('destination_release',1),'ports','CLK','audio_clk','release clock/CE|stage has extra consumer')

    def test_release_must_be_unconditional(self):
        self.reject(self.reg('source_release',0),'ports','CE',"1'b0",'release clock/CE')

    def test_stage_must_not_bypass_two_edge_settling(self):
        p=self.reg('source_release',2)
        self.reject(p,'ports','D',self.n.cells[self.reg('source_release',1)]['ports']['D'],'fill/bypass|stage has extra consumer')

    def test_release_stage_cannot_feed_functional_payload(self):
        p=self.reg('held_data',0)
        source=self.reg('source_release',0)
        self.reject(p,'ports','D',self.n.cells[source]['ports']['Q'],'stage has extra consumer')

    def test_common_assertion_cannot_drop_audio_reset(self):
        g=Graph(self.n);p=self.reg('source_release',0);gate=g.drivers[self.n.pin(p,'CLEAR')][0][0]
        self.reject(gate,'parameters','INIT',"4'h3",'common async CLEAR must be NAND')

    def test_final_release_cannot_reset_a_different_domain(self):
        self.reject(self.reg('held_data',0),'ports','CLK','memory_clk','same-domain local business')

    def test_sdc_must_retain_later_timing_and_functional_recovery(self):
        r=audit(self.n,mapping=self.mapping);sdc=proposed_constraints()
        for line in sdc.splitlines():
            with self.subTest(missing=line),self.assertRaisesRegex(ValueError,'absent or duplicated'):
                validate_sdc(sdc.replace(line+'\n','',1),self.n,r)
        for pin in (r['chains'][0]['stages'][1]+'/D',self.reg('held_data',0)+'/CLEAR'):
            for option in ('',' -hold'):
                for prefix in ('', ' ', '\t'):
                    with self.subTest(cut=pin,option=option,prefix=prefix),self.assertRaisesRegex(ValueError,'later data or functional'):
                        validate_sdc(sdc+f'{prefix}set_false_path{option} -to [get_pins {{{pin}}}]\n',self.n,r)


if __name__=='__main__':unittest.main()
