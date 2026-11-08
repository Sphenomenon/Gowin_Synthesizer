#!/usr/bin/env python3
"""Actual M VG controls for the reviewed destination and retired MIDI input."""
from pathlib import Path
from copy import deepcopy
from contextlib import contextmanager
import os,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_task3_m_preboard_consumers import verify
from tools.workstation_task3_root_reset_audit import audit_root_startup
from tools.workstation_task3_m_midi_release_sdc import audit_midi_release_sdc, CORRECT_SELECTOR, STALE_SELECTOR
from tools.workstation_task3_m_paired_releases_audit import audit_paired_release_sdc

class MConsumers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage=os.environ.get('GW138K_PREBOARD_M_STAGE')
        if not stage:raise unittest.SkipTest('explicit immutable complete M stage required')
        cls.stage=Path(stage);cls.n=protocol_netlist((cls.stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text(),mapping='synthesis')
        cls.g=Graph(cls.n);cls.last=cls.g.register('u_task3_pair_link/config_cdc','a_release',2)
        cls.root=audit_root_startup(cls.n,stage=cls.stage)
        cls.sdc=(cls.stage/'constraints/custom_138k.sdc').read_text()

    def destination(self):
        g=Graph(self.n)
        return verify(self.n,g,complete_closure(self.n,g,[self.last]),role='destination',stage=self.stage)

    def midi(self,sdc=None):
        return audit_midi_release_sdc(self.n,self.sdc if sdc is None else sdc,root=self.root,stage=self.stage)

    @contextmanager
    def cell(self,p):
        old=deepcopy(self.n.cells[p])
        try:yield self.n.cells[p]
        finally:self.n.cells[p]=old

    def test_destination_positive_and_real_mutants(self):
        proof=self.destination()
        self.assertIn((proof['inventory_revision'],proof['ff_endpoints']),((2,8373),(3,8472),(4,8371),(5,8371),(6,8360),(7,8374),(8,8370)))
        closure=complete_closure(self.n,self.g,[self.last])
        p=next(ep.rsplit('/',1)[0] for ep in closure['ff_endpoints'] if ep.endswith('/D'))
        for field,value in [('CLK','audio_clk'),('D',"1'b0")]:
            with self.subTest(field=field),self.cell(p) as c:
                c['ports'][field]=value
                with self.assertRaises(ValueError):self.destination()
        with self.cell(p) as c:
            c['parameters']['INIT']="1'b1" if c['parameters'].get('INIT',"1'b0")=="1'b0" else "1'b0"
            with self.assertRaises(ValueError):self.destination()
        extra=deepcopy(self.n.cells[p]);extra['ports']['D']=self.n.cells[self.last]['ports']['Q'];extra['ports']['Q']='extra_destination_q'
        self.n.cells['extra_destination_s0']=extra;self.n.scopes['extra_destination_s0']=self.n.scopes[self.last]
        try:
            with self.assertRaises(ValueError):self.destination()
        finally:self.n.cells.pop('extra_destination_s0');self.n.scopes.pop('extra_destination_s0')
        for key,value in [('primitive_endpoints',{}),('top_output_endpoints',{})]:
            bad=deepcopy(closure);bad[key]=value
            with self.subTest(inventory=key),self.assertRaises(ValueError):
                verify(self.n,self.g,bad,role='destination',stage=self.stage)

    def test_retired_MIDI_exact_reset_and_stale_selector_mutants(self):
        proof=self.midi();self.assertTrue(proof['constant_high_physical_MIDI_branch_retired'])
        self.assertEqual(proof['final_reset_consumer_count'],524)
        with self.assertRaises(ValueError):self.midi(self.sdc.replace(CORRECT_SELECTOR,STALE_SELECTOR))
        p=self.g.register('u_managed/midi_drops','meta',0)
        with self.cell(p) as c:
            c['ports']['CLEAR']="1'b0"
            with self.assertRaises(ValueError):self.midi()
        # Restore a supposedly optimized MIDI branch: it must not be waived.
        self.n.cells['u_managed/midi_bytes/orphan_s0']=deepcopy(self.n.cells[p]);self.n.scopes['u_managed/midi_bytes/orphan_s0']='u_managed'
        try:
            with self.assertRaises(ValueError):self.midi()
        finally:self.n.cells.pop('u_managed/midi_bytes/orphan_s0');self.n.scopes.pop('u_managed/midi_bytes/orphan_s0')
        extra=deepcopy(self.n.cells[p]);extra['ports']['D']=self.n.cells[proof['actual_release']['stages'][-1]]['ports']['Q'];extra['ports']['Q']='midi_bypass_q'
        self.n.cells['midi_bypass_s0']=extra;self.n.scopes['midi_bypass_s0']='u_task3_m_panic_epoch'
        try:
            with self.assertRaises(ValueError):self.midi()
        finally:self.n.cells.pop('midi_bypass_s0');self.n.scopes.pop('midi_bypass_s0')

    def test_paired_release_retains_three_real_aliases(self):
        proof=audit_paired_release_sdc(self.n,self.sdc,root=self.root,stage=self.stage)
        self.assertEqual(proof['exact_installed_release_CLEAR_pins'],9)
        self.assertEqual(len(proof['retired_aliases']),1)
        selector='u_task3_pair_link/config_cdc/a_release_*_s*/CLEAR'
        with self.assertRaises(ValueError):
            audit_paired_release_sdc(self.n,self.sdc.replace(selector,''),root=self.root,stage=self.stage)

if __name__=='__main__':unittest.main()
