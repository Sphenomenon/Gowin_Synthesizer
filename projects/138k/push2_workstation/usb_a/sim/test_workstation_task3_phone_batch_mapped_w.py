#!/usr/bin/env python3
"""Actual immutable W batch mapping and destructive controls; never board acceptance."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_task3_phone_batch_mapped_w as mapped
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualMappedW(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_BATCH_MAPPED_W_STAGE')
        if not selected:
            raise unittest.SkipTest('explicit actual W batch stage required; no cache fallback')
        cls.stage = Path(selected).resolve()
        cls.vg = cls.stage / 'impl/gwsynthesis/custom_138k_integration.vg'
        cls.n = protocol_netlist(cls.vg.read_text(), mapping='synthesis')
        cls.before = {str(p):sha(p) for p in (cls.vg, Path(__file__),
            ROOT/'tools/workstation_task3_phone_batch_mapped_w.py',
            ROOT/'tools/workstation_task3_w_fault_cdc.py',
            cls.stage/'Prj1.gprj', *(cls.stage/p for p in mapped.SOURCE_SHA256))}
        cls.evidence = dict(positive=None, rejections=[], inputs_mutated=False,
            complete_state_machine_proven=False, full_protocol_functionality_proven=False,
            physical_CDC_accepted=False, routed_timing_verified=False, hardware_tested=False)

    def setUp(self):
        type(self).result = self._outcome.result

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.before == {p:sha(p) for p in cls.before}
        target = os.environ.get('GW138K_TASK3_BATCH_MAPPED_W_EVIDENCE')
        if target:
            Path(target).write_text(json.dumps(dict(cls.evidence,
                passed=cls.result.wasSuccessful() and unchanged,
                inputs_unchanged=unchanged, input_sha256=cls.before,
                negative_control_count=len(cls.evidence['rejections'])), indent=2)+'\n')
        assert unchanged, 'immutable W stage or auditor changed during checks'

    def rejected(self, label, call):
        with self.assertRaises(ValueError) as error:
            call()
        self.evidence['rejections'].append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_01_actual_local_mapping(self):
        proof = mapped.audit(self.n, stage=self.stage)
        self.assertEqual(proof['actual_batch_state_bits'], 969)
        self.assertEqual(proof['request_payload_bits'], 238)
        self.assertEqual(proof['key_comparison_bits'], 128)
        self.assertEqual(proof['reply_tag_comparison_bits'], 64)
        self.assertEqual(len(proof['reply_data_bit_equations']), 256)
        self.assertEqual(len(proof['transport_data_influence']), 238)
        self.assertTrue(proof['register_init_and_port_inventory_verified'])
        self.assertFalse(proof['high_padding_zero_proven'])
        self.assertFalse(proof['response_acceptance_function_proven'])
        self.assertFalse(proof['routed_timing_verified'])
        self.evidence['positive'] = proof

    def test_02_actual_register_and_equation_mutants(self):
        n, g = self.n, Graph(self.n)
        reg = lambda scope, stem, bit=None: g.register(scope, stem, bit)
        payload = g.group(mapped.B,'request_payload',238)
        reply = g.group(mapped.B,'reply',256)
        tx = g.group(mapped.E,'tx_payload_o',256)
        state = g.group(mapped.B,'state',3)
        preset = reg(mapped.B,'allow_context')
        window = reg(mapped.W,'held')
        flight = reg(mapped.W,'flight',0)
        flight_gate = g.drivers[n.pin(flight,'D')][0][0]
        load_gate = g.drivers[n.canonical(mapped.B,'n737_4')][0][0]
        token = g.group(mapped.B,'token',32)
        # Select actual mapped cells, never a source-level or invented seam.
        compare = g.drivers[n.canonical(mapped.B,'n44_3')][0][0]
        cases = [
            ('batch INIT',payload[0],'parameters','INIT',"1'b1"),
            ('preset INIT',preset,'parameters','INIT',"1'b0"),
            ('window INIT',window,'parameters','INIT',"1'b1"),
            ('TX INIT',tx[0],'parameters','INIT',"1'b1"),
            ('unknown FF parameter',payload[0],'parameters','UNREVIEWED','1'),
            ('unknown FF port',payload[0],'ports','UNREVIEWED',"1'b0"),
            ('batch clock',state[0],'ports','CLK',"1'b0"),
            ('batch clear',state[0],'ports','CLEAR',"1'b0"),
            ('preset root',preset,'ports','PRESET',"1'b0"),
            ('window clock',window,'ports','CLK',"1'b0"),
            ('window clear',window,'ports','CLEAR',"1'b0"),
            ('window flight gate truth table',flight_gate,'parameters','INIT',"16'h0000"),
            ('reply load gate truth table',load_gate,'parameters','INIT',"16'h0000"),
            ('window flight next state',flight,'ports','D',"1'b0"),
            ('TX clock',tx[0],'ports','CLK',"1'b0"),
            ('TX clear',tx[0],'ports','CLEAR',"1'b0"),
            ('request alias',payload[0],'ports','Q',n.pin(payload[1],'Q')),
            ('request first word',payload[0],'ports','D',"1'b0"),
            ('request last field',payload[237],'ports','D',"1'b0"),
            ('request shared CE',payload[5],'ports','CE',"1'b0"),
            ('key capture',token[0],'ports','D',"1'b0"),
            ('key capture CE',token[1],'ports','CE',"1'b0"),
            ('reply RX bit disconnected',reply[0],'ports','D',"1'b0"),
            ('reply enable',reply[2],'ports','CE',"1'b0"),
            ('transport bit disconnected',tx[0],'ports','D',"1'b0"),
            ('transport bit permutation',tx[0],'ports','D',n.pin(tx[1],'D')),
            ('key compare mode',compare,'parameters','ALU_MODE','0'),
            ('key compare operand',compare,'ports','I0',"1'b0"),
            ('watermark state disconnected',state[0],'ports','D',"1'b0"),
        ]
        for label,p,section,key,value in cases:
            original = copy.deepcopy(n.cells[p])
            try:
                n.cells[p][section][key] = value
                self.rejected(label,lambda:mapped.audit(n,stage=self.stage))
            finally:
                n.cells[p] = original
        old = n.cells.pop(payload[0])
        try:
            self.rejected('missing request FF',lambda:mapped.audit(n,stage=self.stage))
        finally:
            n.cells[payload[0]] = old

    def test_03_exact_source_and_selection(self):
        with tempfile.TemporaryDirectory(prefix='task3-W-mapped-source-fixture-') as temp:
            stage = Path(temp)
            from tools.workstation_task3_w_banked96 import PROVIDER as banked_provider
            extra = (banked_provider,) if (self.stage/banked_provider).is_file() else ()
            for relative in ('Prj1.gprj',*mapped.SOURCE_SHA256,*extra):
                target = stage/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(self.stage/relative,target)
            mapped.source_binding(stage)
            for relative in mapped.SOURCE_SHA256:
                p = stage/relative
                old = p.read_bytes()
                for missing in (False,True):
                    if missing: p.unlink()
                    else: p.write_bytes(old+b'\n// altered source fixture\n')
                    self.rejected(('missing ' if missing else 'changed ')+relative,
                        lambda:mapped.source_binding(stage))
                    p.write_bytes(old)
            project = stage/'Prj1.gprj'
            original = project.read_bytes()
            for label,path in (
                ('included provider standalone','rtl/workstation/workstation_profile_task3_w_paired.sv'),
                ('included top standalone','rtl/workstation/gw138k_push_workstation_top.v'),
                ('duplicate executor','rtl/workstation/workstation_task3_phone_batch_w.sv')):
                tree = ET.fromstring(original)
                ET.SubElement(tree.find('FileList'),'File',path=path,enable='1')
                project.write_bytes(ET.tostring(tree))
                self.rejected(label,lambda:mapped.source_binding(stage))
                project.write_bytes(original)

    def test_04_fault_synchronizer_mutations(self):
        proof = mapped.audit(self.n, stage=self.stage)['fault_control_boundaries']
        if proof is None:
            self.assertFalse(mapped.source_binding(self.stage)['fault_source_adaptations'])
            return
        self.assertFalse(proof['complete_CDC_accepted'])
        chains = [proof['recording_ready']]
        if proof['CNN_fault_control'] is not None:
            chains.append(proof['CNN_fault_control'])
        for chain in chains:
            first, last = chain['first'], chain['last']
            cases = [('first clock', first, 'CLK', "1'b0"),
                     ('first enable', first, 'CE', "1'b0"),
                     ('last clock', last, 'CLK', "1'b0"),
                     ('last enable', last, 'CE', "1'b0"),
                     ('last data', last, 'D', "1'b0"),
                     ('last reset', last, 'CLEAR', "1'b0")]
            for label, cell, pin, value in cases:
                old = self.n.cells[cell]['ports'][pin]
                try:
                    self.n.cells[cell]['ports'][pin] = value
                    self.rejected(chain['first'] + ' ' + label,
                        lambda:mapped.audit(self.n, stage=self.stage))
                finally:
                    self.n.cells[cell]['ports'][pin] = old


if __name__ == '__main__':
    unittest.main()
