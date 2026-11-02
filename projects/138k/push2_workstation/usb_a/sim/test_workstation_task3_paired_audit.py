#!/usr/bin/env python3
"""Reject live retired endpoints and unresolved multi-layer paired bindings."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_task3_paired_audit import audit_constraint_inventory, TOP


def changed(old, new):
    return dict(original='set_false_path -to [get_pins {' + old + '}]',
        removed_selectors=[old] if new is None else [],
        rebound_selectors=[] if new is None else [dict(query='get_pins', original=old, selected=new)])


def fixture(*registers):
    return SimpleNamespace(cells={name: dict(kind='DFFCE', ports={'D': 'd', 'Q': 'q', 'CLEAR': 'r'})
                                   for name in registers}, directions={TOP: {}})


def metadata(*changes, delegated=()):
    value = dict(demo_constraint_retirement=dict(changes=list(changes)))
    if delegated:
        value['worker_media'] = dict(constraints=dict(changes=[delegated[-1]],
            delegated_media=dict(changes=list(delegated[:-1]))))
    return value


class PairedConstraintInventory(unittest.TestCase):
    def test_retired_live_endpoint_cannot_be_hidden(self):
        with self.assertRaisesRegex(ValueError, 'source is still live'):
            audit_constraint_inventory('', metadata(changed('owner/live*/D', None)),
                                       fixture('owner/live_0_s0'))

    def test_removed_generate_slash_also_checks_real_dot_alias(self):
        old = 'u_managed/pcm_apb/commands/p_release*/CLEAR'
        actual = 'u_managed/pcm_apb.commands/p_release_0_s0'
        with self.assertRaisesRegex(ValueError, 'canonical source is still live'):
            audit_constraint_inventory('', metadata(changed(old, None)), fixture(actual))

    def test_two_layers_require_actual_final_replacement(self):
        evidence = metadata(changed('old/live*/D', 'middle/live*/D'),
                            delegated=(changed('middle/live*/D', 'paired/live*/D'),))
        result = audit_constraint_inventory('', evidence, fixture('paired/live_0_s0'))
        self.assertTrue(result['every_retained_rebinding_live'])
        self.assertFalse(result['physical_CDC_accepted'])
        with self.assertRaisesRegex(ValueError, 'no final endpoint'):
            audit_constraint_inventory('', evidence, fixture('unrelated/live_0_s0'))

    def test_later_retirement_cannot_hide_an_existing_replacement(self):
        evidence = metadata(changed('old/live*/D', 'middle/live*/D'),
                            delegated=(changed('middle/live*/D', None),))
        self.assertTrue(audit_constraint_inventory('', evidence, fixture())[
            'every_retired_selector_absent'])
        with self.assertRaisesRegex(ValueError, 'remains live'):
            audit_constraint_inventory('', evidence, fixture('middle/live_0_s0'))


if __name__ == '__main__':
    unittest.main()
