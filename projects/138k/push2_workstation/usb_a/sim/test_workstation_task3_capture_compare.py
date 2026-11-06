"""Capture ordering must preserve full unsigned width and explicit admission."""
from pathlib import Path
import ast
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_capture_compare as capture
CONFIG=dict(demo_role='M',phone_batch_policy='full_key_atomic_owner_snapshot_command_v1',
    m_demand_identity_compare_policy='task3_m_demand_full96_identity_group8_v1',
    m_capture_compare_policy=capture.POLICY)

class CaptureOrdering(unittest.TestCase):
    def stage(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        stage=Path(temp.name);p=stage/capture.SOURCE;p.parent.mkdir(parents=True);p.write_bytes((ROOT/capture.SOURCE).read_bytes())
        return stage

    def test_exact_v20_inverse_and_explicit_selection(self):
        source=(ROOT/capture.SOURCE).read_text()
        self.assertEqual(capture.digest(capture.restore(source)),capture.PARENT_SHA256)
        stage=self.stage();proof=capture.select(stage,CONFIG)
        self.assertEqual(proof,capture.evidence(stage,CONFIG))
        self.assertEqual((proof['compared_bits'],proof['group_bits'],proof['groups']),(32,8,4))
        self.assertEqual((proof['extra_cycles'],proof['new_state_bits']),(0,0))
        self.assertEqual(capture.native((stage/capture.SOURCE).read_text()),source)

    def test_omitted_reordered_or_changed_comparison_rejected(self):
        source=(ROOT/capture.SOURCE).read_text()
        for before,after in [('capture_byte<4','capture_byte<3'),
            ('byte_less[3] || (byte_equal[3]','byte_less[2] || (byte_equal[2]'),
            ('byte_less[0] || byte_equal[0]','byte_less[0]'),
            ('command_response_data_i<=last_capture_id','command_response_data_i<last_capture_id'),
            ('if(command_response_data_i==0 || capture_not_newer)','if(capture_not_newer)'),
            (capture.PARAMETER,capture.PARAMETER.replace('32','16'))]:
            self.assertEqual(source.count(before),1)
            with self.subTest(before=before),self.assertRaises(ValueError):
                capture.restore(source.replace(before,after,1))

    def test_wrong_policy_role_or_owner_rejected(self):
        for key,value in [(capture.KEY,'unknown'),('demo_role','W'),('phone_batch_policy',None),
                          ('m_demand_identity_compare_policy',None)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                capture.select(self.stage(),dict(CONFIG,**{key:value}))

    def test_implicit_duplicate_and_drifted_selection_rejected(self):
        stage=self.stage();self.assertIsNone(capture.evidence(stage,{}))
        with self.assertRaises(ValueError):capture.evidence(stage,CONFIG)
        capture.select(stage,CONFIG)
        with self.assertRaises(ValueError):capture.evidence(stage,{})
        with self.assertRaises(ValueError):capture.select(stage,CONFIG)
        p=stage/capture.SOURCE;p.write_text(p.read_text()+'\n// drift\n')
        with self.assertRaises(ValueError):capture.evidence(stage,CONFIG)

    def test_publisher_scopes_new_hash_to_v21(self):
        from tools.workstation_task3_root_reset_audit import publisher_policy,M_SYNC_PROVIDER
        from tools import workstation_task3_m_phone_lease_source as lease
        current=dict(selected_provider=M_SYNC_PROVIDER,root_mapping_variant=lease.ROOT_VARIANT,root_profile=capture.PROFILE)
        self.assertEqual(publisher_policy(current)[2][capture.SOURCE],capture.SELECTED_SHA256)
        for revision in (19,20):
            old=dict(current,root_profile='custom138k-workstation-task3-m-paired-checkpoint-v'+str(revision))
            self.assertNotIn(capture.SOURCE,publisher_policy(old)[2])
        with self.assertRaises(ValueError):publisher_policy(dict(current,root_profile='unreviewed'))

    def test_actual_gate_dispatch_includes_both_new_profiles(self):
        tree=ast.parse((ROOT/'tools/workstation_task3_paired_audit.py').read_text())
        for gate,roles in [('phone_batch_mapped_structure',('m','w')),('M_MIDI_release_SDC_semantics',('m',))]:
            guards=[node.test for node in ast.walk(tree) if isinstance(node,ast.If)
                and any(isinstance(stmt,ast.Expr) and isinstance(stmt.value,ast.Call)
                    and isinstance(stmt.value.func,ast.Name) and stmt.value.func.id=='gate'
                    and stmt.value.args and isinstance(stmt.value.args[0],ast.Constant)
                    and stmt.value.args[0].value==gate for stmt in node.body)]
            self.assertEqual(len(guards),1)
            predicate=compile(ast.Expression(guards[0]),'<actual dispatch>','eval')
            for role in roles:
                for revision in (20,21):
                    self.assertTrue(eval(predicate,{'__builtins__':{}},
                        {'profile':{'profile':f'custom138k-workstation-task3-{role}-paired-checkpoint-v{revision}'}}))

if __name__=='__main__':unittest.main()
