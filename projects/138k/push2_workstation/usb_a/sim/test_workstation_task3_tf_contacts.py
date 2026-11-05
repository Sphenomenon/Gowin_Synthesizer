#!/usr/bin/env python3
"""Real locked carrier pin selection, complete plan differences and negatives."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_pinout as pinout
from tools import workstation_task3_tf_contacts as contacts


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualTFContacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_TF_CONTACT_NETLISTS')
        if not selected:
            raise unittest.SkipTest('explicit actual locked netlists required; no fixture acceptance')
        cls.directory = Path(selected).resolve()
        cls.profile = json.loads((ROOT/pinout.PROFILE_PATH).read_text())
        cls.netlists, _ = pinout.load_sources(cls.profile, cls.directory)
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.old, cls.original = pinout.prepare(ROOT, cls.directory, cls.base/'original')
        cls.new, cls.plan = pinout.prepare(ROOT, cls.directory, cls.base/'selected',
                                         tf_contact_policy=contacts.POLICY)
        paths = [Path(__file__), ROOT/pinout.PROFILE_PATH, ROOT/'tools/workstation_pinout.py',
                 *(ROOT/p for p in contacts.DEPENDENCIES),
                 *(cls.directory/p['filename'] for p in cls.profile['sources'].values())]
        cls.inputs = {str(p): sha(p) for p in paths}
        cls.evidence = dict(rejections=[], selected_contacts=cls.plan['tf_contact_selection'])

    def setUp(self):
        type(self).result = self._outcome.result

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.inputs == {p: sha(p) for p in cls.inputs}
        target = os.environ.get('GW138K_TASK3_TF_CONTACT_EVIDENCE')
        if target:
            path = Path(target)
            assert not path.exists(), 'never overwrite evidence'
            path.write_text(json.dumps(dict(cls.evidence, passed=unchanged and cls.result.wasSuccessful(),
                input_sha256=cls.inputs, inputs_unchanged=unchanged,
                negative_control_count=len(cls.evidence['rejections']),
                hardware_tested=False, physical_electrical_acceptance=False), indent=2)+'\n')
        assert unchanged, 'source or locked carrier input changed during verification'

    def rejected(self, label, call):
        with self.assertRaises(ValueError) as error:
            call()
        self.evidence['rejections'].append(dict(case=label, error=str(error.exception)))

    def test_01_actual_contacts_and_exact_other_port_preservation(self):
        contacts.verify_plan(ROOT, self.original, None)
        contacts.verify_plan(ROOT, self.plan, contacts.POLICY)
        ports = set(contacts.CONTACTS)
        self.assertEqual({p:v for p,v in self.original['ports'].items() if p not in ports},
                         {p:v for p,v in self.plan['ports'].items() if p not in ports})
        self.assertEqual({p:v for p,v in self.original['reserved_balls'].items() if not p.startswith('U16.')},
                         {p:v for p,v in self.plan['reserved_balls'].items() if not p.startswith('U16.')})
        self.assertEqual(self.original['source_inputs'], self.plan['source_inputs'])
        original = (self.old/'custom_138k.locations.cst').read_text()
        selected = (self.new/'custom_138k.locations.cst').read_text()
        for port, (_, ball, _, old_ball, _) in contacts.CONTACTS.items():
            selected = selected.replace(f'IO_LOC "{port}" {ball};', f'IO_LOC "{port}" {old_ball};')
        self.assertEqual(selected, original)
        self.evidence['only_four_TF_locations_changed'] = True
        self.evidence['all_other_port_and_reserved_assignments_preserved'] = True

    def test_02_actual_netlist_and_policy_negatives(self):
        self.rejected('unknown policy', lambda: contacts.select_profile(ROOT, self.profile, self.netlists, 'unreviewed'))
        for node in ('U16.2','U16.3','U16.5','U16.7','U16.4','U16.6','U16.9','U16.10'):
            nets = copy.deepcopy(self.netlists)
            nets['carrier'].nodes[node] = '+3V3' if nets['carrier'].network(node) == 'GND' else 'GND'
            self.rejected('actual carrier '+node, lambda: contacts.select_profile(ROOT, self.profile, nets, contacts.POLICY))

    def test_03_descriptor_negatives(self):
        fixture = self.base/'descriptor_fixture'
        for relative in contacts.DEPENDENCIES:
            destination=fixture/relative; destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/relative, destination)
        original = json.loads((ROOT/contacts.SOURCE).read_text())
        for label in ('policy','carrier','contact','unused','acceptance'):
            data = copy.deepcopy(original)
            if label=='policy': data['policy']='unreviewed'
            if label=='carrier': data['carrier_sha256']='0'*64
            if label=='contact': data['ports']['sd_cs_n']['node']='U16.9'
            if label=='unused': data['unused_data_nodes']=['U16.2','U16.3']
            if label=='acceptance': data['hardware_verified']=True
            (fixture/contacts.SOURCE).write_text(json.dumps(data))
            self.rejected('descriptor '+label, lambda: contacts.select_profile(fixture, self.profile, self.netlists, contacts.POLICY))

    def test_04_prepared_plan_negatives(self):
        for label in ('port','reservation','receipt','collision','carrier','identity','recipe','unused_driven'):
            plan = copy.deepcopy(self.plan)
            if label=='port': plan['ports']['sd_miso']['balls']=['AA15']
            if label=='reservation': plan['reserved_balls']['U16.1']='AB15'
            if label=='receipt': plan['tf_contact_selection']['descriptor_sha256']='0'*64
            if label=='collision': plan['ports']['unexpected']=dict(balls=['V15'],origin='unreviewed')
            if label=='carrier': plan['source_inputs']['carrier']['sha256']='0'*64
            if label=='identity': plan['identity'] += '_unreviewed'
            if label=='recipe': del plan['recipe_inputs'][contacts.SOURCE]
            if label=='unused_driven': plan['ports']['unexpected']=dict(balls=['AA15'],origin='unreviewed')
            self.rejected('plan '+label, lambda: contacts.verify_plan(ROOT,plan,contacts.POLICY))
        self.rejected('corrected plan in unselected profile', lambda: contacts.verify_plan(ROOT,self.plan,None))
        self.rejected('original plan with selected policy', lambda: contacts.verify_plan(ROOT,self.original,contacts.POLICY))


if __name__ == '__main__':
    unittest.main()
