#!/usr/bin/env python3
"""Reject live retired endpoints and unresolved multi-layer paired bindings."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_task3_paired_audit import (audit_constraint_inventory,
    audit_paired_ports, audit_m_sync_storage, verify_m_batch_source_receipt, PROFILES, TOP)
from tools import workstation_task3_paired_board as common
from tools.workstation_task3_tf_direct import paired_release_constraint_mappings


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
    def test_sync_storage_cannot_accept_ram16_or_missing_owner(self):
        rows={'u_task3_m_endpoint/'+p:dict(Bsram=1,Ssram=0) for p in ('collector_m','recording')}
        self.assertFalse(audit_m_sync_storage(rows)['physical_block_count_verified'])
        for owner in tuple(rows):
            for counts in (None,dict(Bsram=0,Ssram=0),dict(Bsram=1,Ssram=256)):
                mutated=dict(rows)
                if counts is None:del mutated[owner]
                else:mutated[owner]=counts
                with self.subTest(owner=owner,counts=counts),self.assertRaises(ValueError):
                    audit_m_sync_storage(mutated)

    def test_source_only_and_exact_historical_receipts(self):
        expected = dict(source_sha256={'owner.sv': 'a'*64}, proof='exact')
        verify_m_batch_source_receipt(ROOT, expected, expected)
        document = 'rtl/workstation/TASK3_PHONE_BATCH_CONTRACT.md'
        historical = '605f3dc41c3fcbd7c1c8bf313a88433e4fa45d45a406f04a9ad6e73d724bae38'
        legacy = dict(expected, source_sha256=dict(expected['source_sha256'], **{document: historical}))
        # This fixture exercises receipt structure. The actual frozen stage is
        # independently checked by the read-only candidate audit.
        module = 'tools.workstation_task3_paired_audit'
        with patch(module+'.checked', return_value=ROOT/'retired_fixture'), patch(module+'.sha', return_value=historical):
            verify_m_batch_source_receipt(ROOT, legacy, expected)
            for changed in (dict(legacy, proof='changed'),
                    dict(legacy, source_sha256=dict(legacy['source_sha256'], **{'owner.sv': 'b'*64})),
                    dict(legacy, source_sha256=dict(legacy['source_sha256'], **{'extra.md': historical})),
                    dict(legacy, source_sha256=dict(legacy['source_sha256'], **{document: '0'*64}))):
                with self.assertRaises(ValueError):
                    verify_m_batch_source_receipt(ROOT, changed, expected)
        with patch(module+'.checked', return_value=ROOT/'retired_fixture'), patch(module+'.sha', return_value='0'*64), self.assertRaises(ValueError):
            verify_m_batch_source_receipt(ROOT, legacy, expected)
        with self.assertRaises(ValueError):
            verify_m_batch_source_receipt(ROOT, None, expected)

    def test_m_release_inverse_requires_exact_evidence(self):
        original = '\n'.join('set_false_path -to [get_pins {' + old + '}]'
                             for old, new in paired_release_constraint_mappings()) + '\n'
        selected, receipt = common.adapt_constraints(ROOT, original, 'M')
        self.assertEqual(common.restore_constraints(ROOT, selected, receipt), original)
        self.assertEqual(selected.count('set_false_path'), original.count('set_false_path'))
        with self.assertRaisesRegex(ValueError, 'requires sealed evidence'):
            common.restore_constraints(ROOT, selected)
        modified = dict(receipt, M_release_rebinding=dict(receipt['M_release_rebinding'], input_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'evidence drift'):
            common.restore_constraints(ROOT, selected, modified)
        for role in (None, 'W'):
            legacy, receipt = common.adapt_constraints(ROOT, original, role)
            self.assertEqual(common.restore_constraints(ROOT, legacy, receipt), original)

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


class PairedSelectedProvider(unittest.TestCase):
    """Exercise the public port audit with real GPRJ XML and preprocessing."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stage = Path(self.temporary.name)
        pinplan = json.loads((ROOT / common.PINPLAN).read_text())
        lcd = {row['port']: row['fpga_ball'] for row in pinplan['pins']
               if row['kind'] == 'programmable'}
        expected = {port: [ball] for port, ball in lcd.items()
                    if not port.startswith('lcd_ctp_')}
        expected['clk_12m288'] = ['K18']
        self.plan = dict(ports={port: dict(balls=balls) for port, balls in expected.items()})
        self.write(common.PINPLAN, json.dumps(pinplan))
        self.write('probes/audio_clock_i2s/probe.json', json.dumps(dict(pins=dict(
            clk_16m9344='J19', clk_12m288='K18'))))
        extra = {port: [ball] for port, ball in lcd.items() if port.startswith('lcd_ctp_')}
        extra['clk_16m9344'] = ['J19']
        for filename, locations in (('custom_138k.locations.cst', expected),
                                    ('custom_138k.cst', dict(expected, **extra))):
            self.write('constraints/' + filename, ''.join(
                f'IO_LOC "{port}" {",".join(balls)};\n'
                for port, balls in locations.items()))
        self.header = f'''module {TOP} #(parameter UNUSED = 0) (
    input wire clk_12m288, input wire clk_16m9344,
    inout wire [4:0] lcd_r, inout wire [5:0] lcd_g, inout wire [4:0] lcd_b,
    inout wire lcd_pclk, inout wire lcd_hsync, inout wire lcd_vsync,
    inout wire lcd_de, inout wire lcd_bl,
    inout wire lcd_ctp_rst, inout wire lcd_ctp_sda,
    inout wire lcd_ctp_scl, inout wire lcd_ctp_int,
    output wire tmds_clk_n, output wire [2:0] tmds_data_n,
    output wire ddr_ck_n, inout wire [3:0] ddr_dqs_n
); endmodule
'''

    def write(self, relative, value):
        path = self.stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def manifest(self, *entries):
        root = ET.Element('Project')
        files = ET.SubElement(root, 'FileList')
        for provider, enabled in entries:
            ET.SubElement(files, 'File', path=provider, enable=str(enabled))
        ET.ElementTree(root).write(self.stage / 'Prj1.gprj')

    def test_every_registered_profile_selects_its_actual_enabled_provider(self):
        # In particular, old paired and CPU48 candidates must not follow the
        # first same-role registry entry when a new phone policy is registered.
        providers = {row[2] for row in PROFILES.values()}
        for name, (role, _, selected) in PROFILES.items():
            with self.subTest(profile=name):
                for provider in providers:
                    self.write(provider, self.header if provider == selected
                               else '`error disabled_provider_must_not_be_preprocessed\n')
                self.manifest(*[(provider, int(provider == selected))
                                for provider in sorted(providers)])
                result = audit_paired_ports(self.stage, self.plan, role)
                self.assertEqual(result['compilation_provider'], selected)
                self.assertEqual(result['paired_LCD_inout_ports'], 25)
                self.assertFalse(result['hardware_electrical_acceptance'])

    def test_missing_enabled_provider_is_rejected(self):
        selected = PROFILES['custom138k-workstation-task3-m-paired-v1'][2]
        self.manifest((selected, 0), ('rtl/unrelated.sv', 1))
        with self.assertRaisesRegex(ValueError, 'provider missing or mixed'):
            audit_paired_ports(self.stage, self.plan, 'M')

    def test_multiple_or_duplicate_enabled_providers_are_rejected(self):
        old = PROFILES['custom138k-workstation-task3-m-paired-v1'][2]
        phone = PROFILES['custom138k-workstation-task3-m-paired-phone-blocks-v1'][2]
        worker = PROFILES['custom138k-workstation-task3-w-paired-v1'][2]
        for entries in (((old, 1), (phone, 1)), ((old, 1), (worker, 1)),
                        ((old, 1), (old, 1))):
            with self.subTest(entries=entries):
                self.manifest(*entries)
                with self.assertRaisesRegex(ValueError, 'provider missing or mixed'):
                    audit_paired_ports(self.stage, self.plan, 'M')

    def test_wrong_role_or_unpaired_registered_provider_is_rejected(self):
        from tools.workstation_profile import PROFILE_REGISTRY
        for provider in (PROFILES['custom138k-workstation-task3-w-paired-v1'][2],
                         PROFILE_REGISTRY['custom138k-workstation-task3-m-direct-tf-v1']['provider']):
            with self.subTest(provider=provider):
                self.manifest((provider, 1))
                with self.assertRaisesRegex(ValueError, 'does not match role M'):
                    audit_paired_ports(self.stage, self.plan, 'M')


if __name__ == '__main__':
    unittest.main()
