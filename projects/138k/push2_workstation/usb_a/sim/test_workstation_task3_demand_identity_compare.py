"""Reject partial identities, implicit selection and unrelated endpoint drift."""
from pathlib import Path
import ast
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_demand_identity_compare as demand
from tools import workstation_task3_phone_identity_compare as phone
CONFIG=dict(demo_role='M',phone_batch_policy='full_key_atomic_owner_snapshot_command_v1',
    m_phone_identity_compare_policy=phone.POLICY,m_demand_identity_compare_policy=demand.POLICY)

class DemandIdentity(unittest.TestCase):
    def test_new_checkpoint_dispatches_existing_batch_and_midi_gates(self):
        # Evaluate the actual dispatch predicates: merely registering a profile
        # must not silently omit either independently required audit.
        tree=ast.parse((ROOT/'tools/workstation_task3_paired_audit.py').read_text())
        for gate,roles in [('phone_batch_mapped_structure',('m','w')),
                           ('M_MIDI_release_SDC_semantics',('m',))]:
            guards=[node.test for node in ast.walk(tree) if isinstance(node,ast.If)
                and any(isinstance(stmt,ast.Expr) and isinstance(stmt.value,ast.Call)
                    and isinstance(stmt.value.func,ast.Name) and stmt.value.func.id=='gate'
                    and stmt.value.args and isinstance(stmt.value.args[0],ast.Constant)
                    and stmt.value.args[0].value==gate for stmt in node.body)]
            self.assertEqual(len(guards),1)
            predicate=compile(ast.Expression(guards[0]),'<actual gate dispatch>','eval')
            for role in roles:
                for revision in (19,20):
                    name=f'custom138k-workstation-task3-{role}-paired-checkpoint-v{revision}'
                    with self.subTest(gate=gate,profile=name):
                        self.assertTrue(eval(predicate,{'__builtins__':{}},{'profile':{'profile':name}}))

    def test_publisher_admits_only_the_new_exact_endpoint_for_v20(self):
        from tools.workstation_task3_root_reset_audit import publisher_policy,M_SYNC_PROVIDER
        from tools import workstation_task3_m_phone_lease_source as lease
        current=dict(selected_provider=M_SYNC_PROVIDER,root_mapping_variant=lease.ROOT_VARIANT,root_profile=demand.PROFILE)
        self.assertEqual(publisher_policy(current)[2][demand.ENDPOINT],demand.SELECTED_SHA256)
        old=dict(current,root_profile='custom138k-workstation-task3-m-paired-checkpoint-v19')
        self.assertEqual(publisher_policy(old)[2][demand.ENDPOINT],demand.PARENT_SHA256)
        with self.assertRaises(ValueError):publisher_policy(dict(current,root_profile='unreviewed'))

    def stage(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        stage=Path(temp.name);p=stage/demand.ENDPOINT;p.parent.mkdir(parents=True);p.write_bytes((ROOT/demand.ENDPOINT).read_bytes())
        return stage
    def test_exact_nested_inverse_and_explicit_selection(self):
        text=(ROOT/demand.ENDPOINT).read_text()
        self.assertEqual(demand.digest(demand.restore_endpoint(text)),demand.PARENT_SHA256)
        phone.restore_endpoint(text)
        stage=self.stage();proof=demand.select(stage,CONFIG)
        self.assertEqual(proof,demand.evidence(stage,CONFIG));self.assertTrue(proof['same_cycle_revocation'])
        self.assertEqual(proof['compared_identity_bits'],96);self.assertEqual(proof['new_state_bits'],0)
        self.assertEqual(demand.native((stage/demand.ENDPOINT).read_text()),text)
        phone.restore_endpoint((stage/demand.ENDPOINT).read_text())
    def test_missing_or_partial_comparison_and_other_behavior_rejected(self):
        text=(ROOT/demand.ENDPOINT).read_text()
        for before,after in [('demand_byte<12','demand_byte<11'),
            ('rx_payload_i[demand_byte*8+:8]','rx_payload_i[1+demand_byte*8+:8]'),
            ('=&demand_byte_equal','=|demand_byte_equal'),
            ('wire demand_cancel_fire=','wire demand_cancel_fire=1\'b0 && '),
            (demand.PARAMETER,demand.PARAMETER.replace('96','16'))]:
            self.assertEqual(text.count(before),1)
            with self.subTest(before=before),self.assertRaises(ValueError):
                demand.restore_endpoint(text.replace(before,after,1))
    def test_unknown_policy_wrong_role_and_wrong_owner_rejected(self):
        for key,value in [(demand.KEY,'unknown'),('demo_role','W'),('phone_batch_policy',None),('m_phone_identity_compare_policy',None)]:
            with self.subTest(key=key),self.assertRaises(ValueError):demand.select(self.stage(),dict(CONFIG,**{key:value}))
    def test_unselected_missing_duplicate_and_changed_selected_source_rejected(self):
        stage=self.stage();self.assertIsNone(demand.evidence(stage,{}))
        with self.assertRaises(ValueError):demand.evidence(stage,CONFIG)
        demand.select(stage,CONFIG)
        with self.assertRaises(ValueError):demand.evidence(stage,{})
        with self.assertRaises(ValueError):demand.select(stage,CONFIG)
        p=stage/demand.ENDPOINT;source=p.read_text();p.write_text(source+'\n// drift\n')
        with self.assertRaises(ValueError):demand.evidence(stage,CONFIG)
        p.unlink()
        with self.assertRaises(OSError):demand.evidence(stage,CONFIG)

if __name__=='__main__':unittest.main()
