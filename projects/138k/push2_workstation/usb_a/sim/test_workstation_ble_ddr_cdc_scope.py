#!/usr/bin/env python3
"""Explicit revision2 gates plus optional sealed actual-VG negative checks."""
from pathlib import Path
import copy
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_ble_ddr_cdc_scope import (SCOPE, PROFILE, PROFILE_SOURCE, validate_profile,
    validate_compiled_inputs, COUNTER_SOURCE)
from tools.workstation_ble_recording_policy import metadata as ble_metadata
from tools.workstation_recording_policy import metadata as recording_metadata
from tools.workstation_runtime_shared_cdc import validate_precision_profile
from tools.workstation_usb2_owner_reset import validate_profile as validate_usb_profile, OwnerResetNetlist
from tools.workstation_recording_phase1_cdc import audit_netlist as phase1, P, D
from tools.workstation_ble_ddr_cdc_inventory import audit_netlist as inventory, B, F, A
from tools.workstation_runtime_pcm_cdc import Graph, TOP
from tools.workstation_runtime_clock_audit import VG_RELATIVE, verify_synthesis_identity, file_sha


class Revision2Gate(unittest.TestCase):
    def setUp(self):
        self.profile = dict(schema=1, profile=PROFILE, revision=2, profile_source=PROFILE_SOURCE,
            profile_sha256='0'*64, configuration=json.loads((ROOT/PROFILE_SOURCE).read_text())['configuration'],
            recording=dict(recording_metadata(ble_raw_ddr=True), address_map={}),
            ble_recording_storage=dict(ble_metadata(), adaptation={}),
            recognition=dict(policy='disabled_cnn_and_follow_v1', music_analysis_enabled=False,
                cnn_score_follow_enabled=False, constraints=dict(enabled=False)))

    def test_new_explicit_gate_and_unchanged_legacy_rejection(self):
        self.assertEqual(validate_profile(ROOT, self.profile)['scope'], SCOPE)
        validate_precision_profile(ROOT, self.profile, SCOPE)
        validate_usb_profile(ROOT, self.profile, PROFILE, scope=SCOPE)
        with self.assertRaisesRegex(ValueError, 'supported configuration changed'):
            validate_precision_profile(ROOT, self.profile, 'runtime-r00-no-local-panel-v1')
        with self.assertRaisesRegex(ValueError, 'supported configuration changed'):
            validate_usb_profile(ROOT, self.profile, PROFILE)

    def test_revision_configuration_and_metadata_mutants_rejected(self):
        changes = [
            ('revision1', lambda p:p.update(revision=1)),
            ('wrong profile', lambda p:p.update(profile='custom138k-workstation-r00-v1')),
            ('missing provenance', lambda p:p.update(profile_sha256='invalid')),
            ('configuration addition', lambda p:p['configuration'].update(extra_policy=True)),
            ('wrong storage policy', lambda p:p['configuration'].update(ble_recording_storage_policy='ram')),
            ('missing BLE', lambda p:p.pop('ble_recording_storage')),
            ('wrong root reset', lambda p:p['ble_recording_storage'].update(root_reset='ddr_client_reset_n')),
            ('missing adapter', lambda p:p['ble_recording_storage'].pop('adaptation')),
            ('recording acceptance claim', lambda p:p['recording'].update(source_cdc_complete=True)),
        ]
        for label, change in changes:
            p=copy.deepcopy(self.profile); change(p)
            with self.subTest(case=label), self.assertRaises(ValueError):
                validate_profile(ROOT,p)

    def test_unreviewed_counter_selection_cannot_hide_behind_staged_legacy_bytes(self):
        for enabled in ([COUNTER_SOURCE], ['rtl/control/workstation_counter_cdc.sv'],
                        [COUNTER_SOURCE,'rtl/control/workstation_counter_cdc.sv']):
            with self.subTest(enabled=enabled),self.assertRaisesRegex(ValueError,'compilation selection changed'):
                validate_compiled_inputs(dict(enabled_inputs={path:{} for path in enabled}),list(enabled))
        with self.assertRaisesRegex(ValueError,'differ from prepared'):
            validate_compiled_inputs(dict(enabled_inputs={COUNTER_SOURCE:{}}),[])


class ActualRevision2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage, evidence = os.environ.get('GW138K_BLE_DDR_CDC_STAGE'), os.environ.get('GW138K_BLE_DDR_CDC_PROCESS')
        if not stage or not evidence:
            raise unittest.SkipTest('explicit completed sealed revision2 stage required; no EDA fallback')
        cls.stage, cls.evidence = Path(stage), Path(evidence)
        cls.before = verify_synthesis_identity(cls.stage, cls.evidence)
        cls.paths = (Path(__file__), ROOT/'tools/workstation_ble_ddr_cdc_inventory.py',
            ROOT/'tools/workstation_ble_ddr_cdc_scope.py', ROOT/'tools/workstation_recording_phase1_cdc.py')
        cls.hashes = {str(p):file_sha(p) for p in cls.paths}
        cls.n = OwnerResetNetlist((cls.stage/VG_RELATIVE).read_text(), TOP)
        cls.baseline = inventory(cls.n)
        cls.phase1_baseline = phase1(cls.n, scope=SCOPE)
        cls.mutations = []

    @classmethod
    def tearDownClass(cls):
        if cls.before != verify_synthesis_identity(cls.stage,cls.evidence):
            raise AssertionError('original sealed synthesis inputs changed')
        if cls.hashes != {str(p):file_sha(p) for p in cls.paths}:
            raise AssertionError('audit/test sources changed')
        output = os.environ.get('GW138K_BLE_DDR_CDC_TEST_EVIDENCE')
        if output:
            Path(output).write_text(json.dumps(dict(schema=1, synthesis=cls.before,
                audit_source_sha256=cls.hashes, mutations=cls.mutations, mutation_count=len(cls.mutations),
                original_VG_rewritten=False, original_SDC_rewritten=False,
                eda_invoked=False, hardware_operated=False, recording_cdc_complete=False,
                physical_cdc_accepted=False, deployment_allowed=False),indent=2,sort_keys=True)+'\n')

    def test_inventory_scope_and_nonacceptance(self):
        r=self.baseline
        self.assertEqual((r['ordinary_pair_count'],r['gray_bits'],r['raw_payload_logical_bits'],
            r['raw_payload_mapped_source_FFs']),(13,50,528,524))
        self.assertEqual(len(r['complete_source_fanout']),42)
        self.assertEqual((self.phase1_baseline['complete_reviewed_FF_count'],
            self.phase1_baseline['gray_first_stage_bits'],self.phase1_baseline['payload_bits']),(425,42,82))
        for key in ('recording_cdc_complete','full_reset_accepted','physical_cdc_accepted',
            'constraints_complete','routed_timing_verified','deployment_allowed','release_ready'):
            self.assertFalse(r[key], key)
        self.assertFalse(r['seal_result_payload']['eliminated_code_constant_or_alias_accepted'])

    def test_actual_register_and_complete_closure_mutants(self):
        n=self.n; g=Graph(n); reg=lambda s,t,b=None:g.register(s,t,b)
        cases=[
            ('raw first D disconnected',reg(B,'command_req_meta'),'D',"1'b0",'producer/receiving'),
            ('raw first clock changed',reg(B,'command_req_meta'),'CLK','clk_50m','kind/clock|endpoint identity'),
            ('raw first CE conditional',reg(B,'command_req_meta'),'CE',"1'b0",'conditional receiving CE'),
            ('raw second D bypass',reg(B,'command_req_sync'),'D',"1'b0",'producer/receiving'),
            ('Gray MSB source changed',reg(F,'read_gray_meta',8),'D',n.cells[reg(F,'read_gray',7)]['ports']['Q'],'Gray producer'),
            ('Gray first extra CE consumer',reg(F,'write_binary',0),'CE',n.cells[reg(F,'read_gray_meta',0)]['ports']['Q'],'Gray first-Q|endpoint identity'),
            ('payload source clock changed',reg(B,'command_generation',0),'CLK','memory_clk','kind/clock|endpoint identity'),
            ('held payload extra consumer',reg(B,'cancel_seen'),'CE',n.cells[reg(B,'command_generation',0)]['ports']['Q'],'endpoint identity'),
            ('seal registered ready bypass',reg('u_recording/seal_cdc','ready_meta'),'D',"1'b1",'producer/receiving'),
            ('authority heartbeat source swapped',reg(A,'gray_meta',0),'D',n.cells[reg(A,'memory_gray',1)]['ports']['Q'],'Gray producer'),
            ('raw control reset release CE changed',reg('u_usb_pll/u_pll_init','enable_r',0),'CE',"1'b0",'conditional receiving CE'),
        ]
        for label,path,pin,value,error in cases:
            old=n.cells[path]['ports'][pin];n.cells[path]['ports'][pin]=value
            try:
                with self.subTest(case=label),self.assertRaisesRegex(ValueError,error) as raised:
                    inventory(n)
                self.mutations.append(dict(case=label,rejected=hasattr(raised,'exception'),
                    error=str(getattr(raised,'exception','mutation was not rejected'))))
            finally:
                n.cells[path]['ports'][pin]=old
        # Explicitly reject any additional consumer of the shared reset stage.
        path=reg(D,'sync_value',0);pin='CE';old=n.cells[path]['ports'][pin]
        n.cells[path]['ports'][pin]=n.cells[reg(D,'destination_release',1)]['ports']['Q']
        try:
            with self.assertRaisesRegex(ValueError,'seal/reset alias complete closure') as raised:
                phase1(n,scope=SCOPE)
            self.mutations.append(dict(case='shared seal reset stage extra CE consumer',rejected=True,error=str(raised.exception)))
        finally:
            n.cells[path]['ports'][pin]=old
        inventory(n)
        phase1(n,scope=SCOPE)


if __name__ == '__main__':
    unittest.main()
