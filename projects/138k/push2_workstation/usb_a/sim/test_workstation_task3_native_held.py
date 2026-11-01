#!/usr/bin/env python3
"""Explicit actual DIRECT held/reset proof and destructive graph controls."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import (
    protocol_netlist, audit_native_protocol, audit_demo_held_boundaries,
    validate_native_protocol_sdc, RAM_SCOPE)
from tools.workstation_performance_reset import demo_held_handshake_constraints
from tools.workstation_runtime_profile import protocol_constraints
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_root_reset_audit import audit_root_startup
from tools.workstation_task3_native_held import audit_direct_held_boundaries, audit_direct_tf_owner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualDirectHeld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vg, stage = (os.environ.get(name) for name in
                     ('GW138K_TASK3_NATIVE_VG', 'GW138K_TASK3_NATIVE_STAGE'))
        if not vg or not stage:
            raise unittest.SkipTest('explicit actual VG and matching sealed stage required; no cache fallback')
        cls.path, cls.stage = Path(vg), Path(stage)
        cls.mapping = os.environ.get('GW138K_TASK3_NATIVE_MAPPING', 'synthesis')
        cls.n = protocol_netlist(cls.path.read_text(), mapping=cls.mapping)
        cls.root = audit_root_startup(cls.n, stage=cls.stage)
        cls.native = audit_native_protocol(cls.n, profile='m-task3-direct', mapping=cls.mapping)
        cls.held = audit_direct_held_boundaries(cls.n, cls.native, root=cls.root)
        cls.mutations = []
        cls.failed = False
        cls.before = {str(path):sha(path) for path in
                      (cls.path, cls.stage/'Prj1.gprj', *[cls.stage/name for name in cls.root['source_sha256']])}

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {path:sha(path) for path in cls.before}, 'actual input bytes drifted'
        selected = os.environ.get('GW138K_TASK3_NATIVE_EVIDENCE')
        if selected:
            tf = next(row for row in cls.native['level_proofs'] if 'full_direct_tf_cdc_accepted' in row)
            Path(selected).write_text(json.dumps(dict(status='FAIL' if cls.failed else 'PASS', mapping=cls.mapping,
                actual_inputs_sha256=cls.before, actual_held=cls.held, actual_tf=tf,
                mutations=cls.mutations, mutation_count=len(cls.mutations),
                full_direct_tf_cdc_accepted=tf['full_direct_tf_cdc_accepted'],
                physical_timing_verified=False, hardware_tested=False), indent=2)+'\n')

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed = self.__class__.failed or bool(result.errors or result.failures)

    @contextmanager
    def change(self, path, part, key, value):
        row = self.n.cells[path][part]
        exists, old = key in row, row.get(key)
        row[key] = value
        try:
            yield
        finally:
            if exists:
                row[key] = old
            else:
                del row[key]

    def reject(self, label, path, part, key, value, tf=False):
        with self.change(path, part, key, value), self.assertRaises(ValueError) as error:
            if tf:
                audit_direct_tf_owner(self.n)
            else:
                audit_direct_held_boundaries(self.n, self.native, root=self.root)
        self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_exact_direct_inventory_and_old_constant_proof_rejected(self):
        self.assertEqual(self.native['mailbox_count'], 5)
        display = next(row for row in self.native['mailboxes'] if row['scope']=='u_managed/display')
        self.assertEqual((display['held_ff_bits'], display['registered_ram_bits']), (230, 0))
        self.assertEqual(len(self.held['pc_actual_reset']['reset_inclusive_next_q']), 13)
        with self.assertRaises(ValueError):
            audit_demo_held_boundaries(self.n, self.native)
        self.mutations.append(dict(case='DIRECT cannot use legacy constant-common-reset proof', rejected=True))

    def test_actual_pc_and_apb_destructive_controls(self):
        g = Graph(self.n)
        r = lambda scope, stem, bit=None:g.register(scope,stem,bit)
        pc, apb = 'u_managed/pc_bytes', 'u_managed/control_cdc'
        src = self.held['pc_actual_reset']['releases']['source']['stages']
        dst = self.held['pc_actual_reset']['releases']['destination']['stages']
        cases = [
            ('PC source release INIT',src[0],'parameters','INIT',"1'b1"),
            ('PC source release CE',src[1],'ports','CE',"1'b0"),
            ('PC source release bypass',src[2],'ports','D',"1'b1"),
            ('PC source assertion removed',src[0],'ports','CLEAR',"1'b0"),
            ('PC destination release bypass',dst[1],'ports','D',"1'b1"),
            ('PC destination clock',dst[0],'ports','CLK','clk_50m'),
            ('PC payload reset removed',r(pc,'destination_data',7),'ports','CLEAR',"1'b0"),
            ('PC capture CE removed',r(pc,'destination_data',0),'ports','CE',"1'b1"),
            ('PC source ACK bypass',r(pc,'ack_meta'),'ports','D',"1'b1"),
            ('PC request settle bypass',r(pc,'req_settled'),'ports','D',"1'b1"),
            ('APB common assertion removed',r(apb,'p_release',0),'ports','CLEAR',"1'b0"),
            ('APB local release CE',r(apb,'a_release',1),'ports','CE',"1'b0"),
            ('APB functional reset',r(apb,'request_local',0),'ports','CLEAR',"1'b0"),
            ('APB payload INIT',r(apb,'response_held',32),'parameters','INIT',"1'b1"),
        ]
        for case in cases:
            with self.subTest(case=case[0]):
                self.reject(*case)

    def test_root_proof_cannot_be_replaced_by_binding_names(self):
        for label, root in (
                ('root all-state proof removed', dict(self.root, all_state_assignments_proven=False)),
                ('root policy replaced', dict(self.root, policy='legacy-constant-reset')),
                ('root source identity removed', dict(self.root, source_sha256={})),
                ('root Q disconnected', dict(self.root, root_q="1'b1"))):
            with self.subTest(case=label),self.assertRaises(ValueError) as error:
                audit_direct_held_boundaries(self.n,self.native,root=root)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))

    def test_actual_status_next_q_and_destructive_controls(self):
        g = Graph(self.n)
        r = lambda stem, bit=None:g.register('u_tf_audio',stem,bit)
        status = audit_direct_tf_owner(self.n)
        self.assertTrue(status['full_status_acceptance_next_q_proven'])
        self.assertEqual(len(status['reset_inclusive_state_updates']),138)
        cases = [
            ('status held source CE',r('held_status',0),'ports','CE',"1'b1"),
            ('status exact bit mapping',r('compute_status',67),'ports','D',"1'b0"),
            ('status request toggle removed',r('status_request'),'ports','D',"1'b0"),
            ('status request clock',r('status_request'),'ports','CLK','audio_clk'),
            ('status source synchronizer bypass',r('status_ack_sync',0),'ports','D',"1'b1"),
            ('status capture settled state',r('status_capture'),'ports','D',"1'b1"),
            ('status capture CE',r('status_capture'),'ports','CE',"1'b0"),
            ('status ACK root reset',r('status_ack'),'ports','CLEAR',"1'b0"),
            ('status ACK capture CE',r('status_ack'),'ports','CE',"1'b1"),
            ('status payload root reset',r('compute_status',3),'ports','CLEAR',"1'b0"),
            ('status held INIT',r('held_status',0),'parameters','INIT',"1'b1"),
        ]
        for case in cases:
            with self.subTest(case=case[0]):
                self.reject(*case, tf=True)

    def test_local_direct_sdc_exact_230_and_60_ff_bounds(self):
        # This is the shared native subset. Root/TF selection and complete
        # physical inventory remain additional gates over the installed SDC.
        sdc = '\n'.join(line for line in protocol_constraints().splitlines()
                        if RAM_SCOPE not in line and 'u_tf_audio/' not in line)+'\n'
        sdc += demo_held_handshake_constraints()
        result = dict(self.native, demo_held_handshakes=self.held)
        checked = validate_native_protocol_sdc(sdc,self.n,result,
                    demo_held_handshakes=demo_held_handshake_constraints())
        self.assertTrue(checked['direct_display_hmi_ff_bounds_verified'])
        self.assertEqual(checked['registered_ram_source_pins'],[])
        bounds = [line for line in sdc.splitlines() if
                  ('u_managed/display/' in line or 'u_video/u_applied_parameters_cdc/' in line)]
        cases = [
            ('DIRECT display bound missing',sdc.replace(bounds[0]+'\n','',1)),
            ('DIRECT display bound duplicate',sdc+bounds[0]+'\n'),
            ('DIRECT held payload setup false path',sdc+'set_false_path -to [get_pins {u_managed/display/destination_data_105_s*/D}]\n'),
            ('DIRECT HMI second stage cut',sdc+'set_false_path -to [get_pins {u_video/u_applied_parameters_cdc/req_sync_s*/D}]\n'),
            ('DIRECT payload bound overridden',sdc+'set_max_delay 40.000 -to [get_pins {u_managed/display/destination_data_105_s*/D}]\n'),
            ('DIRECT retired RAM bound restored',sdc+'\n'.join(line for line in protocol_constraints().splitlines() if RAM_SCOPE in line)+'\n'),
        ]
        for label, changed in cases:
            with self.subTest(case=label),self.assertRaises(ValueError) as error:
                validate_native_protocol_sdc(changed,self.n,result,
                    demo_held_handshakes=demo_held_handshake_constraints())
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))


if __name__=='__main__':
    unittest.main()
