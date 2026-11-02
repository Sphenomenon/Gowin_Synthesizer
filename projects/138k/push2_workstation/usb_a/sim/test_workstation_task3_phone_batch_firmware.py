#!/usr/bin/env python3
"""Explicit batch firmware source/role gates and actual-ELF receipt mutations."""
from pathlib import Path
import copy
import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_task3_w_paired_firmware as paired
from tools import workstation_task3_w_media_firmware as firmware
from tools import workstation_task3_w_media_profile as media
from tools import workstation_task3_w_paired_profile as profile
from tools import workstation_classic_runtime as runtime
from tools import workstation_ae350_memory as memory

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class PhoneBatchFirmware(unittest.TestCase):
    rejected=[]

    def test_01_separate_review_and_disabled_lineage(self):
        reviewed,lineage=firmware.verify_sources(ROOT,phone_batch=True)
        self.assertEqual(reviewed['policy'],firmware.PHONE_BATCH_POLICY)
        self.assertEqual(sha(ROOT/paired.PARENT_REVIEW),paired.PARENT_REVIEW_SHA256)
        self.assertEqual(set(lineage['phone_batch_disabled_parent']),{
            'firmware/ae350/'+name for name in ('classic_runtime.c','pcm_media.c','pcm_media.h')})
        with self.assertRaisesRegex(ValueError,'reviewed source drift'):
            firmware.verify_sources(ROOT)

    def test_02_source_mutations_fail_closed(self):
        reviewed=json.loads((ROOT/paired.BATCH_REVIEW).read_text())
        with tempfile.TemporaryDirectory(prefix='phone-batch-source-') as temp:
            root=Path(temp)
            for rel in (*reviewed['input_sha256'],paired.BATCH_REVIEW,paired.PARENT_REVIEW):
                target=root/rel;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/rel,target)
            expected=set(reviewed['input_sha256'])
            path=root/'firmware/ae350/pcm_media.c';original=path.read_bytes()
            path.write_bytes(original+b'\n/* unreviewed */\n')
            with self.assertRaisesRegex(ValueError,'reviewed source drift'):
                paired.verify_phone_batch_sources(root,expected)
            path.write_bytes(original)
            other=root/'firmware/ae350/hci_transport.c';other.write_bytes(other.read_bytes()+b'\n')
            changed=copy.deepcopy(reviewed)
            changed['input_sha256']['firmware/ae350/hci_transport.c']=sha(other)
            (root/paired.BATCH_REVIEW).write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'unrelated media source drift'):
                paired.verify_phone_batch_sources(root,expected)
        with self.assertRaisesRegex(ValueError,'unterminated'):
            paired.disabled_phone_batch_source(b'#ifdef A138_TASK3_PHONE_BATCH\n')

    def test_03_only_explicit_entry_enables_batch(self):
        for function in (firmware.build,media.build_firmware,profile.build_firmware,
                runtime.build,runtime.prepare_selection,runtime.verify_selection,runtime.verify_build):
            self.assertIs(inspect.signature(function).parameters['phone_batch'].default,False)
        with self.assertRaisesRegex(ValueError,'explicit paired'):
            firmware.build('/unused',root=ROOT,phone_batch=True)
        with self.assertRaisesRegex(ValueError,'explicit paired'):
            runtime.build(ROOT,'/unused',phone_batch=True)
        for provider in (profile.PROVIDER,profile.PHONE_PROVIDER):
            with self.assertRaises(ValueError):
                runtime._paired_media_helper(131072,selected_provider=provider,media_worker=True,phone_batch=True)
        with self.assertRaises(ValueError):
            runtime._paired_media_helper(131072,selected_provider=profile.BATCH_PROVIDER,media_worker=True)
        self.assertIs(runtime._paired_media_helper(131072,selected_provider=profile.BATCH_PROVIDER,
            media_worker=True,phone_batch=True),profile)

    def test_04_memory_policy_matches_exact_role(self):
        config=dict(ae350_memory_profile='ilm64k_dlm64k',ae350_boot_rom_bytes=131072,
            ae350_firmware_policy=paired.BATCH_POLICY,hci_transport_policy='native_shared_hci_owner_v1',
            ae350_pcm_policy='task3_W_HCI_decode_M_PCM1_v1',demo_role='W',
            display_policy='disabled_worker_media_v1',recording_owner_policy='single_C_BLE_ddr_60s_v1',
            recording_policy='task3_w_paired_single_C_BLE_recording_60s_v1',
            ble_recording_storage_policy='task3_w_paired_single_C_BLE_raw_ddr_60s_v1',
            business_owner_policy='ae350_single_C_BLE_recording_owner_v1',
            recognition_policy='task3_w_paired_native_CNN_stream_v1',
            interboard_transport_policy='task3_lcd_reqack_crc_session_budget_gated_v1',
            paired_config_policy='task3_f808_nonzero_nonce_v1',
            interboard_media_policy='task3_pcm_block6_credit8_phone_window5_atomic_snapshot_batch_v3',
            phone_window_policy='posted_window5_single_inflight_applied_barrier_v1',
            phone_batch_policy='full_key_atomic_owner_snapshot_command_v1',
            interboard_business_default_enabled=False,interboard_physical_acceptance_required=True)
        self.assertEqual(memory.selection(config),dict(memory_profile='ilm64k_dlm64k',boot_rom_bytes=131072))
        for key in config:
            changed=dict(config);changed.pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):memory.selection(changed)
        old=dict(config,ae350_firmware_policy=paired.POLICY)
        for key in ('interboard_media_policy','phone_window_policy','phone_batch_policy'):old.pop(key)
        self.assertEqual(memory.selection(old),dict(memory_profile='ilm64k_dlm64k',boot_rom_bytes=131072))

    def test_05_actual_elf_receipt_negative_controls(self):
        selected=os.environ.get('GW138K_TASK3_PHONE_BATCH_FIRMWARE_EVIDENCE')
        if not selected:self.skipTest('explicit independently built batch ELF evidence required')
        output=Path(selected).resolve()
        original=(output/'verification.json').read_text()
        record=json.loads(original)
        nominal=firmware.audit(output,ROOT)
        self.assertTrue(nominal['passed'])
        self.assertTrue(nominal['stack']['verified'])
        self.assertEqual(nominal['policy'],paired.BATCH_POLICY)
        mutations=[
            ('missing-source',lambda d:d['input_sha256'].pop('firmware/ae350/pcm_media.c')),
            ('one-TU-missing-define',lambda d:d['commands'][0]['argv'].remove('-DA138_TASK3_PHONE_BATCH')),
            ('one-TU-conflicting-define',lambda d:d['commands'][0]['argv'].insert(1,'-DA138_TASK3_PHONE_BATCH=0')),
            ('missing-compile-command',lambda d:d['commands'].pop(0)),
            ('wrong-source-command',lambda d:d['commands'][0]['argv'].__setitem__(-3,'wrong.c')),
            ('disabled-batch-claim',lambda d:d.update(phone_batch=False)),
            ('changed-ELF-identity',lambda d:d['phone_batch_artifacts_sha256'].update({'firmware.elf':'0'*64})),
            ('changed-memory-capacity',lambda d:d['capacity'].update(ilm_runtime_bytes=1)),
            ('missing-adapted-input',lambda d:d['adapted_inputs_sha256'].pop(next(iter(d['adapted_inputs_sha256'])))),
            ('missing-compiled-source',lambda d:d['compiled_sources'].pop()),
        ]
        original_loads=json.loads
        for name,change in mutations:
            changed=copy.deepcopy(record);change(changed)
            def receipt_loads(text,*args,**kwargs):
                return copy.deepcopy(changed)if text==original else original_loads(text,*args,**kwargs)
            with self.subTest(name=name),mock.patch.object(firmware.json,'loads',side_effect=receipt_loads):
                with self.assertRaises(ValueError)as error:firmware.audit(output,ROOT)
                self.rejected.append(dict(name=name,rejected=True,error=str(error.exception)))
        target=os.environ.get('GW138K_TASK3_PHONE_BATCH_FIRMWARE_TEST_EVIDENCE')
        if target:
            Path(target).write_text(json.dumps(dict(passed=True,source_review_sha256=sha(ROOT/paired.BATCH_REVIEW),
                actual_ELF_sha256=sha(output/'firmware.elf'),audit_sha256=sha(output/'media_callgraph_verification.json'),
                rejected_mutations=self.rejected,hardware_tested=False),indent=2)+'\n')

if __name__=='__main__':unittest.main()
