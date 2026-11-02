#!/usr/bin/env python3
"""Register exact batch sources without inheriting an unproved mapped root.

Optional explicit old stages/VGs verify preservation of the existing real root
proof. Temporary new-provider fixtures test source binding and rejection only;
they are not new production candidates or new synthesis evidence.
"""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_task3_root_reset_audit as roots
from tools import workstation_task3_paired_audit as paired
from tools import workstation_task3_tf_direct as direct
from tools import workstation_task3_tf_storage_selection as storage
from tools.workstation_native_protocol_audit import protocol_netlist


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


NEW = {
    'M': ('custom138k-workstation-task3-m-paired-phone-batch-v1',
          'custom138k-native-task3-m-paired-phone-batch-revision1', roots.M_PHONE_BATCH_PROVIDER),
    'W': ('custom138k-workstation-task3-w-paired-phone-batch-v1',
          'custom138k-native-task3-w-paired-phone-batch-revision1', roots.W_PHONE_BATCH_PROVIDER),
}
REFERENCES = tuple('rtl/workstation/workstation_task3_' + name + '_top_reference.json'
                   for name in ('m_paired', 'w_paired', 'tf_storage', 'w_media'))


class BatchAuditRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = dict(source_bindings={}, rejections=[], old_actual_roots={},
                            pending_batch_aliases=[], batch_prepared={}, direct_batch_selection=None,
                            old_prepared_profiles_preserved=[], mutation_fixtures_are_candidates=False)
        cls.parents, cls.batch_outputs = {}, {}
        cls.before = {str(path): sha(path) for path in (
            Path(__file__), ROOT / 'tools/workstation_task3_root_reset_audit.py',
            ROOT / 'tools/workstation_task3_paired_audit.py',
            ROOT / 'tools/workstation_task3_tf_direct.py',
            ROOT / 'tools/workstation_task3_tf_storage_selection.py')}
        for role in NEW:
            batch = os.environ.get('GW138K_TASK3_BATCH_AUDIT_' + role + '_OUTPUT')
            if batch:
                cls.batch_outputs[role] = Path(batch).resolve()
                output = cls.batch_outputs[role]
                for relative in ('integration_inputs.json', 'workstation_profile.json',
                                 'classic_runtime_preprocessed.v'):
                    if (output / relative).is_file():
                        cls.before[str(output / relative)] = sha(output / relative)
                stage = output / 'workstation/Prj1'
                for relative in ('Prj1.gprj', roots.TOP_SOURCE, NEW[role][2],
                                 *roots.PROVIDER_POLICIES[NEW[role][2]][3]):
                    cls.before[str(stage / relative)] = sha(stage / relative)
            selected = os.environ.get('GW138K_TASK3_BATCH_AUDIT_' + role + '_STAGE')
            if selected:
                stage = Path(selected).resolve()
                vg = Path(os.environ.get('GW138K_TASK3_BATCH_AUDIT_' + role + '_VG',
                    stage / 'impl/gwsynthesis/custom_138k_integration.vg')).resolve()
                cls.parents[role] = dict(stage=stage, vg=vg)
                cls.before.update({str(path): sha(path) for path in (stage / 'Prj1.gprj', vg)})

    def setUp(self):
        type(self).test_result = self._outcome.result

    @classmethod
    def tearDownClass(cls):
        target = os.environ.get('GW138K_TASK3_BATCH_AUDIT_EVIDENCE')
        if target:
            unchanged = cls.before == {path: sha(path) for path in cls.before}
            complete = (cls.test_result.wasSuccessful() and unchanged and
                len(cls.evidence['source_bindings']) == 2 and len(cls.evidence['old_actual_roots']) == 2)
            Path(target).write_text(json.dumps(dict(cls.evidence, passed=complete,
                input_sha256=cls.before, inputs_unchanged=unchanged,
                new_batch_synthesis_verified=False, new_batch_root_alias_verified=False,
                both_batch_prepared_profiles_verified=len(cls.evidence['batch_prepared'])==2,
                routed_timing_verified=False, hardware_tested=False), indent=2) + '\n')

    def test_01_exact_new_registry_and_unchanged_old_entries(self):
        old = {
            'custom138k-workstation-task3-m-paired-phone-blocks-v1': ('M', 'custom138k-native-task3-m-paired-phone-blocks-revision1', roots.M_PHONE_PROVIDER),
            'custom138k-workstation-task3-w-paired-phone-blocks-v1': ('W', 'custom138k-native-task3-w-paired-phone-blocks-revision1', roots.W_PHONE_PROVIDER),
            'custom138k-workstation-task3-m-paired-cpu48-v1': ('M', 'custom138k-native-task3-m-paired-cpu48-revision1', roots.PAIRED_PROVIDER),
            'custom138k-workstation-task3-m-paired-v1': ('M', 'custom138k-native-task3-m-paired-revision1', roots.PAIRED_PROVIDER),
            'custom138k-workstation-task3-w-paired-v1': ('W', 'custom138k-native-task3-w-paired-revision1', roots.W_PAIRED_PROVIDER),
        }
        for name, value in old.items():
            self.assertEqual(paired.PROFILES[name], value)
        original_roots = {
            roots.PROVIDER: ('1a857e684cde13a83e598cf5d183858ba57e224d46048623974fa6b3716be071', None, 'reset_n', {}),
            roots.PAIRED_PROVIDER: ('e5e2764eafdcc59fc9904eae93f4f457cb2bd59595336ac88e878d0bb1e65169', 'M', 'terminal_ready', {}),
            roots.W_PAIRED_PROVIDER: ('a13cd5e6285e7d288a7e1eafe2179831dd339be7f8f8d98b243559124d322dac', 'W', 'reset_n', {}),
            roots.M_PHONE_PROVIDER: ('799306fde1aa3e0e8fa026e6b23a194e445578208bb0c91bab4d5327255e3f05', 'M', 'terminal_ready', {}),
            roots.W_PHONE_PROVIDER: ('9fe33e9ca0551b714882c5fee4018a791945cc80bfc131d8a16fd630111a3503', 'W', 'reset_n',
                                   {roots.W_PAIRED_PROVIDER: 'a13cd5e6285e7d288a7e1eafe2179831dd339be7f8f8d98b243559124d322dac'}),
        }
        for provider, value in original_roots.items():
            self.assertEqual(roots.PROVIDER_POLICIES[provider], value)
        for role, (name, identity, provider) in NEW.items():
            self.assertEqual(paired.PROFILES[name], (role, identity, provider))
            spec = profiles.specification(name)
            self.assertEqual((spec['provider'], spec['paired_role'], spec['integration_identity']),
                             (provider, role, identity))
            self.assertTrue(spec['phone_batch'])
            self.assertEqual(spec['configuration']['phone_batch_policy'], 'full_key_atomic_owner_snapshot_command_v1')
            self.assertEqual(spec['configuration']['interboard_media_policy'], 'task3_pcm_block6_credit8_phone_window5_atomic_snapshot_batch_v3')

    def test_02_exact_transitive_provider_hashes_and_pending_aliases(self):
        for role, (_, _, provider) in NEW.items():
            provider_hash, registered_role, alias, includes = roots.PROVIDER_POLICIES[provider]
            self.assertEqual(registered_role, role)
            self.assertEqual(sha(ROOT / provider), provider_hash)
            self.assertEqual(set(includes), {roots.M_PHONE_PROVIDER, roots.RUNTIME_PROVIDER, roots.HDMI_PROVIDER}
                             if role == 'M' else {roots.W_PAIRED_PROVIDER, roots.W_MEDIA_PROVIDER})
            for relative, expected in includes.items():
                self.assertEqual(sha(ROOT / relative), expected)
            # No new mapped alias is copied from an older candidate. Even a
            # forged familiar name cannot pass before reviewing a new real VG.
            self.assertIsNone(alias)
            for forged in ('reset_n', 'terminal_ready', 'u_reset/started'):
                with self.assertRaisesRegex(ValueError, 'requires actual synthesis review'):
                    roots.validate_root_publisher(None, None,
                        dict(selected_provider=provider, mapped_common_root_name=forged))
            self.evidence['pending_batch_aliases'].append(dict(role=role, provider=provider,
                mapped_alias=None, new_synthesis_required=True))

    def fixture(self, role, destination):
        if role not in self.parents:
            self.skipTest('explicit M/W old stage and VG inputs required; no cache fallback')
        shutil.copytree(self.parents[role]['stage'], destination, ignore=shutil.ignore_patterns('impl'))
        provider = NEW[role][2]
        policy = roots.PROVIDER_POLICIES[provider]
        for relative in (provider, *policy[3]):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        tree = ET.parse(destination / 'Prj1.gprj')
        selected = [row for row in tree.find('FileList') if row.get('enable') == '1' and
                    row.get('path', '').startswith('rtl/workstation/workstation_profile_')]
        self.assertEqual(len(selected), 1)
        selected[0].set('path', provider)
        tree.write(destination / 'Prj1.gprj')
        return provider

    def reject_source(self, stage, label):
        with self.assertRaises((ValueError, FileNotFoundError)) as error:
            roots.source_binding(stage)
        self.evidence['rejections'].append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_03_actual_source_binding_and_fail_closed_mutations(self):
        for role in NEW:
            with tempfile.TemporaryDirectory(prefix='task3-batch-root-source-') as temp:
                stage = Path(temp) / 'stage'
                provider = self.fixture(role, stage)
                proof = roots.source_binding(stage)
                expected_sources = {'Prj1.gprj', roots.TOP_SOURCE, roots.ROOT_SOURCE,
                                    provider, *roots.PROVIDER_POLICIES[provider][3]}
                self.assertEqual(set(proof['source_sha256']), expected_sources)
                self.assertEqual(proof['selected_provider'], provider)
                self.evidence['source_bindings'][role] = proof
                for relative in (provider, *roots.PROVIDER_POLICIES[provider][3], roots.ROOT_SOURCE):
                    target = stage / relative
                    original = target.read_bytes()
                    target.write_bytes(original + b'\n// altered audit input\n')
                    self.reject_source(stage, role + ' altered ' + relative)
                    target.write_bytes(original)
                for relative in roots.PROVIDER_POLICIES[provider][3]:
                    target = stage / relative
                    original = target.read_bytes()
                    target.unlink()
                    self.reject_source(stage, role + ' missing include ' + relative)
                    target.write_bytes(original)
                project = stage / 'Prj1.gprj'
                original = project.read_bytes()
                for label, path in (('standalone top bypass', roots.TOP_SOURCE),
                                    ('mixed providers', roots.W_PAIRED_PROVIDER if role == 'M' else roots.M_PHONE_PROVIDER)):
                    tree = ET.parse(project)
                    ET.SubElement(tree.find('FileList'), 'File', path=path, enable='1')
                    tree.write(project)
                    self.reject_source(stage, role + ' ' + label)
                    project.write_bytes(original)
                # A real old VG does not turn the new wrapper into a reviewed
                # batch implementation: the new alias remains unregistered.
                netlist = protocol_netlist(self.parents[role]['vg'].read_text(), mapping='synthesis')
                with self.assertRaisesRegex(ValueError, 'requires actual synthesis review'):
                    roots.audit_root_startup(netlist, stage=stage)
                self.evidence['rejections'].append(dict(case=role + ' old VG cannot authorize new alias', rejected=True))

    def test_04_old_real_root_proof_remains_strict(self):
        for role in NEW:
            if role not in self.parents:
                self.skipTest('explicit M/W old stage and VG inputs required; no cache fallback')
            row = self.parents[role]
            netlist = protocol_netlist(row['vg'].read_text(), mapping='synthesis')
            proof = roots.audit_root_startup(netlist, stage=row['stage'])
            self.assertEqual(proof['actual_state_bits'], 35)
            self.assertEqual(proof['state_assignment_count'], 1 << 35)
            self.assertTrue(proof['all_state_assignments_proven'])
            self.assertFalse(proof['routed_timing_verified'])
            self.assertFalse(proof['hardware_tested'])
            self.assertEqual(proof['selected_provider'], roots.M_PHONE_PROVIDER if role == 'M' else roots.W_PHONE_PROVIDER)
            self.evidence['old_actual_roots'][role] = proof

    def test_05_new_M_direct_delegation_checks_all_provider_hashes(self):
        if 'M' not in self.batch_outputs:
            self.skipTest('explicit new M output required; no cache fallback')
        source = self.batch_outputs['M'] / 'workstation/Prj1'
        configuration = profiles.specification(NEW['M'][0])['configuration']
        with tempfile.TemporaryDirectory(prefix='task3-batch-direct-test-fixture-') as temp:
            # A component fixture has no bound candidate manifests and cannot
            # become a release candidate. Its capture map is local test data.
            stage = Path(temp) / 'stage'
            shutil.copytree(source, stage, ignore=shutil.ignore_patterns('impl'))
            provider = NEW['M'][2]
            captured = {p: sha(stage/p) for p in (*direct.SOURCES, provider)}
            captured[storage.TOP] = storage.SELECTED_SHA256
            def verify():
                return storage.prepared_selection(stage, stage, configuration,
                    captured_source_sha256=captured)
            proof = verify()
            self.assertEqual(proof['provider'], provider)
            self.evidence['direct_batch_selection'] = proof
            for relative in (provider, *roots.PROVIDER_POLICIES[provider][3]):
                target = stage / relative
                original = target.read_bytes()
                for missing in (False, True):
                    if missing:
                        target.unlink()
                    else:
                        target.write_bytes(original + b'\n// invalid transitive provider fixture\n')
                    for validator in (verify, lambda: direct.selected_direct_top(
                            stage, (stage/storage.TOP).read_text())):
                        with self.assertRaises((ValueError, FileNotFoundError)):
                            validator()
                    self.evidence['rejections'].append(dict(case='M DIRECT ' +
                        ('missing ' if missing else 'altered ') + relative, rejected=True))
                    target.write_bytes(original)

    @staticmethod
    def bind_test_fixture(output, metadata, profile):
        # Mutations are rebound only inside a disposable test fixture so they
        # reach the semantic guard rather than fail an earlier digest check.
        profile['integration_metadata_sha256'] = paired.digest(
            {key: value for key, value in metadata.items() if key != 'workstation_profile'})
        artifact = output / 'workstation_profile.json'
        artifact.write_text(json.dumps(profile, indent=2) + '\n')
        metadata['workstation_profile']['artifact_sha256'] = sha(artifact)
        (output / 'integration_inputs.json').write_text(json.dumps(metadata, indent=2) + '\n')

    def test_06_new_prepared_evidence_is_recomputed_from_immutable_stage(self):
        available = [(role, output) for role, output in self.batch_outputs.items()
                     if (output/'integration_inputs.json').is_file()]
        if not available:
            self.skipTest('explicit completed new batch output required; no cache fallback')
        for role, output in available:
            metadata = json.loads((output/'integration_inputs.json').read_text())
            actual_role, profile, _, _ = paired.verify_prepared(output, metadata)
            self.assertEqual(actual_role, role)
            self.evidence['batch_prepared'][role] = dict(candidate_identity=profile['candidate_identity'],
                integration_sha256=sha(output/'integration_inputs.json'),
                stage_only_source_revalidation=True)
            with tempfile.TemporaryDirectory(prefix='task3-batch-prepared-test-fixture-') as temp:
                fixture = Path(temp)/'fixture'
                shutil.copytree(output, fixture, ignore=shutil.ignore_patterns('impl'))
                def reject(label, mutate, pattern):
                    record, artifact = copy.deepcopy(metadata), copy.deepcopy(profile)
                    mutate(record)
                    self.bind_test_fixture(fixture, record, artifact)
                    with self.assertRaisesRegex(ValueError, pattern):
                        paired.verify_prepared(fixture, record)
                    self.evidence['rejections'].append(dict(case=label, rejected=True,
                        rebound_test_fixture=True, production_candidate_changed=False))
                if role == 'M':
                    reject('M stale atomic snapshot evidence',
                        lambda record: record['task3_phone_batch'].update(atomic_owner_snapshot=False),
                        'M phone batch prepared source evidence changed')
                    reject('M omitted atomic snapshot evidence',
                        lambda record: record.pop('task3_phone_batch'),
                        'M phone batch prepared source evidence changed')
                else:
                    for key, value in (('provider', roots.W_PHONE_PROVIDER),
                            ('policy', 'task3_w_paired_media_single_recording_60s_v1'),
                            ('phone_batch', False), ('worker_paired', False), ('worker_media', False)):
                        reject('W stale batch runtime ' + key,
                            lambda record, key=key, value=value: record['classic_runtime'].update({key:value}),
                            'W phone batch runtime selection changed')
                    reject('W stale batch source evidence',
                        lambda record: record['classic_runtime']['worker_media_source'].update(
                            actual_endpoint_PHONE_BATCH=False),
                        'W phone batch prepared source evidence changed')
                    target = fixture/'classic_runtime_preprocessed.v'
                    original = target.read_bytes()
                    target.write_bytes(original+b'\n// altered preprocessing fixture\n')
                    reject('W stale preprocessed hash', lambda record: None,
                        'W phone batch preprocessed evidence changed')
                    target.write_bytes(original)
                    text = target.read_text()
                    old = "localparam bit TASK3_PHONE_BATCH=1'b1;"
                    self.assertEqual(text.count(old), 1)
                    target.write_text(text.replace(old, "localparam bit TASK3_PHONE_BATCH=1'b0;"))
                    reject('W rehashed semantic preprocessing drift',
                        lambda record: record['classic_runtime'].update(preprocessed_sha256=sha(target)),
                        'W paired actual binding drift')

    def test_07_old_prepared_profiles_do_not_consume_batch_evidence(self):
        if len(self.parents) != 2:
            self.skipTest('explicit old M/W stages required; no cache fallback')
        for role, row in self.parents.items():
            output = row['stage'].parent.parent
            metadata = json.loads((output/'integration_inputs.json').read_text())
            with patch('tools.workstation_task3_m_paired_profile.selected_batch_source_evidence',
                       side_effect=AssertionError('old M invoked new batch guard')), \
                 patch('tools.workstation_task3_w_paired_profile.selected_source_evidence',
                       side_effect=AssertionError('old W invoked new batch guard')):
                actual_role, profile, _, _ = paired.verify_prepared(output, metadata)
            self.assertEqual(actual_role, role)
            self.evidence['old_prepared_profiles_preserved'].append(profile['profile'])


if __name__ == '__main__':
    unittest.main()
