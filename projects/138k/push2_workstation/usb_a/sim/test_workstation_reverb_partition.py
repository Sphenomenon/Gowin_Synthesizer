#!/usr/bin/env python3
"""Matched subsystem experiment identity and actual hierarchy census checks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_reverb_partition as partition


class ReverbPartitionManifestTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='reverb-partition-identity-')
        self.output = Path(self.temp.name) / 'new-candidate'
        self.manifest = partition.prepare(self.output)

    def tearDown(self):
        self.temp.cleanup()

    def rewrite_manifest(self, modify):
        path = self.output / 'manifest.json'
        manifest = json.loads(path.read_text())
        modify(manifest)
        path.write_text(json.dumps(manifest, indent=2) + '\n')
        # Refresh the outer accidental-corruption hash deliberately. Semantic
        # source inventory checks must independently reject omissions/forgery.
        (self.output / 'manifest.sha256').write_text(partition.sha(path) + '\n')

    def test_matched_dynamic_interfaces_and_synthesis_only(self):
        partition.verify(self.output)
        local = (self.output / 'local/binding.sv').read_text()
        remote = (self.output / 'm_remote/binding.sv').read_text()
        self.assertEqual(local.replace('.REMOTE_REVERB_ENABLE(0)', '.REMOTE_REVERB_ENABLE(1)'), remote)
        for name in ('synth_i', 'pcm_left_i', 'effect_mask_i', 'config_valid_i',
                     'remote_reverb_req_valid_o', 'remote_reverb_rsp_valid_i'):
            self.assertIn(name, local)
        for case in partition.CASES:
            text = (self.output / case / 'run.tcl').read_text()
            self.assertEqual(text.count('run syn'), 1)
            self.assertNotIn('run pnr', text)
            self.assertNotIn('program', text)
            self.assertIn(partition.CONFIG['device'], text)
            self.assertIn(partition.CONFIG['compute_period_ns'], (self.output / case / 'experiment.sdc').read_text())
        self.assertNotIn('impl', {path.name for path in self.output.iterdir()})

    def test_omitted_maintained_source_manifest_rejected(self):
        self.rewrite_manifest(lambda manifest: manifest['source_files'].pop(partition.CHAIN))
        with self.assertRaisesRegex(ValueError, 'source manifest omitted or modified'):
            partition.verify(self.output)

    def test_omitted_locked_source_manifest_rejected(self):
        self.rewrite_manifest(lambda manifest: manifest['source_files'].pop(partition.LOCKED[0]))
        with self.assertRaisesRegex(ValueError, 'source manifest omitted or modified'):
            partition.verify(self.output)

    def test_forged_source_hash_rejected(self):
        self.rewrite_manifest(lambda manifest: manifest['source_files'][partition.CHAIN].update(sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'source manifest omitted or modified'):
            partition.verify(self.output)

    def test_modified_staged_source_rejected(self):
        path = self.output / 'sources' / partition.ACTIVE[2]
        path.write_bytes(path.read_bytes() + b'\n// unreviewed drift\n')
        with self.assertRaisesRegex(ValueError, 'staged source drifted'):
            partition.verify(self.output)

    def test_omitted_staged_source_rejected(self):
        (self.output / 'sources' / partition.LOCKED[1]).unlink()
        with self.assertRaisesRegex(ValueError, 'staged source inventory changed'):
            partition.verify(self.output)

    def test_modified_synthesis_script_rejected(self):
        path = self.output / 'm_remote/run.tcl'
        path.write_text(path.read_text().replace('run syn', 'run all'))
        with self.assertRaisesRegex(ValueError, 'generated input drifted'):
            partition.verify(self.output)

    def test_omitted_case_source_rejected(self):
        self.rewrite_manifest(lambda manifest: manifest['cases']['m_remote']['compiled_sources'].pop())
        with self.assertRaisesRegex(ValueError, 'case configuration/source manifest drifted'):
            partition.verify(self.output)

    def test_changed_clock_configuration_rejected(self):
        self.rewrite_manifest(lambda manifest: manifest['configuration'].update(compute_clock_hz=50000000))
        with self.assertRaisesRegex(ValueError, 'configuration drifted'):
            partition.verify(self.output)

    def test_existing_output_rejected(self):
        with self.assertRaisesRegex(ValueError, 'output must not exist'):
            partition.prepare(self.output)


class ReverbPartitionCensusTest(unittest.TestCase):
    def test_recursive_instance_multiplicity_and_no_physical_conversion(self):
        text = '''module child (i,o);
input i;
output o;
LUT4 l0 (.I0(i), .F(o));
SDPB ram (.CLK(i), .DO(o));
endmodule
module top (i,o);
input i;
output o;
child a (.i(i), .o(o));
child b (.i(i), .o(o));
endmodule
'''
        result = partition.census(text, 'top')
        self.assertEqual(result['leaf_primitive_instances'], {'LUT4': 2, 'SDPB': 2})
        self.assertEqual(result['bsram_primitive_instances'], {'SDPB': 2})
        self.assertEqual(result['recursive_leaf_instances'], 4)
        self.assertIn('not_routed_physical_BSRAM', result['resource_scope'])
        self.assertNotIn('physical_BSRAM_count', result)


if __name__ == '__main__':
    unittest.main()
