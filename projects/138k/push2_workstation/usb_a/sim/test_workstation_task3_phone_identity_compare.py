"""Fail closed on partial identity, extra behavior, and unselected bindings."""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_phone_identity_compare as phone
from tools import workstation_task3_identity_compare as pair


class PhoneIdentity(unittest.TestCase):
    def test_exact_nested_inverse_preserves_both_legacy_guards(self):
        original=(ROOT/phone.ENDPOINT).read_text()
        restored=phone.restore_endpoint(original)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),phone.REFERENCE_ENDPOINT_SHA256)
        pair.restore_endpoint(restored)
        phone.restore_board((ROOT/phone.BOARD).read_text())

    def test_source_and_binding_mutations_rejected(self):
        original=(ROOT/phone.ENDPOINT).read_text()
        for old,new in [('byte_group<12','byte_group<11'),('82+byte_group*8','83+byte_group*8'),
                        ('=&byte_equal','=|byte_equal'),(phone.PARAMETER,phone.PARAMETER.replace('96','8')),
                        ('assign phone_owner_live_o=','assign phone_owner_live_o=1\'b1 || ')]:
            self.assertEqual(original.count(old),1)
            with self.subTest(mutation=old),self.assertRaises(ValueError):
                phone.restore_endpoint(original.replace(old,new,1))
        board=(ROOT/phone.BOARD).read_text()
        for changed in (board.replace(phone.BINDING,''),board+phone.BINDING,
                        board.replace('IDENTITY_COMPARE_GROUP_BITS=8','IDENTITY_COMPARE_GROUP_BITS=96')):
            with self.assertRaises(ValueError):phone.restore_board(changed)

    def test_explicit_selection_and_legacy_default(self):
        top=phone.BINDING.strip()
        config=dict(m_identity_compare_policy=pair.POLICY,m_phone_identity_compare_policy=phone.POLICY,
                    m_score_terminal_policy='task3_m_one_slot_terminal_validation_v1')
        proof=phone.selection(ROOT,config,top,sync_selected=True)
        self.assertEqual(proof['compared_identity_bits'],96)
        self.assertTrue(proof['same_cycle_revocation'])
        self.assertIsNone(phone.selection(ROOT,{},'',sync_selected=False))
        for c,t,s in [({},top,True),(dict(config,m_phone_identity_compare_policy='unknown'),top,True),
                      (config,'',True),(config,top+top,True),(config,top,False),
                      (dict(config,m_identity_compare_policy=None),top,True)]:
            with self.subTest(config=c,top=t,sync=s),self.assertRaises(ValueError):
                phone.selection(ROOT,c,t,sync_selected=s)


if __name__=='__main__':unittest.main()
