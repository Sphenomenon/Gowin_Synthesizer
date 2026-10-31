#!/usr/bin/env python3
"""Explicit joint source/memory selection and real prepared closure negatives."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_classic_runtime as runtime
from tools import workstation_profile as profile
from tools import workstation_ae350_memory as memory
from tools import workstation_ae350_pcm as pcm
from tools import stage_ae350_firmware as legacy

class Selection(unittest.TestCase):
    def test_joint_policy_locks_actual_sources_and_fails_closed(self):
        selected=profile.load(ROOT,profile.CLASSIC_RUNTIME_NAME)
        self.assertEqual(selected['configuration']['ae350_boot_rom_bytes'],131072)
        self.assertEqual(memory.selection(selected['configuration']),dict(memory_profile='ilm64k_dlm64k',boot_rom_bytes=131072))
        prefix='projects/138k/push2_workstation/usb_a/'
        for source in runtime.firmware_inputs(ROOT)+list(runtime.DEPENDENCIES)+list(pcm.SOURCES)+[runtime.PROVIDER]:
            self.assertIn(prefix+source,selected['source_sha256'])
        bundle=pcm.source_bundle(ROOT)
        self.assertEqual(bundle['caps']&0x18,0)
        self.assertFalse(bundle['sustained_verified'])
        self.assertFalse(bundle['measured_total_delay_valid'])
        for name,spec in profile.PROFILE_REGISTRY.items():
            self.assertEqual(spec.get('classic_runtime_enabled',False),name==profile.CLASSIC_RUNTIME_NAME)
        self.assertIn('firmware_runtime.enabled=0;',(ROOT/'firmware/ae350/classic_runtime.c').read_text())

    def test_rom128_requires_all_joint_policies_and_legacy_decoder_is_unchanged(self):
        selected=profile.load(ROOT,profile.CLASSIC_RUNTIME_NAME)['configuration']
        for field in ('ae350_firmware_policy','hci_transport_policy','ae350_pcm_policy','ae350_memory_profile'):
            changed=dict(selected);changed.pop(field)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'unsupported'):
                memory.selection(changed)
        self.assertEqual(memory.selection({})['boot_rom_bytes'],16384)
        self.assertEqual(memory.selection(dict(ae350_memory_profile='ilm64k_dlm64k',ae350_boot_rom_bytes=65536))['boot_rom_bytes'],65536)
        with tempfile.TemporaryDirectory()as d:
            rom=Path(d)/'boot.mem';rom.write_text('00000000\n'*32768)
            self.assertEqual(len(runtime.decode_rom(rom)),131072)
            with self.assertRaises(ValueError):legacy.decode_rom(rom,131072)
            rom.write_text('00000000\n'*16384)
            with self.assertRaisesRegex(ValueError,'exact physical ROM128'):runtime.decode_rom(rom)

    def test_changed_joint_configuration_cannot_be_loaded_as_an_existing_profile(self):
        config=ROOT/profile.CLASSIC_RUNTIME_CONFIG
        base=json.loads(config.read_text());original=Path.read_text
        for field,value in [('ae350_boot_rom_bytes',65536),('ae350_pcm_policy',None),('hci_transport_policy','none'),('ae350_firmware_policy',profile.AE350_POLICY)]:
            changed=copy.deepcopy(base);changed['configuration'][field]=value
            with self.subTest(field=field),patch.object(Path,'read_text',lambda p,*a,**k:json.dumps(changed)if p==config else original(p,*a,**k)),self.assertRaisesRegex(ValueError,'configuration mismatch'):
                profile.load(ROOT,profile.CLASSIC_RUNTIME_NAME)

    def test_legacy_business_review_still_locks_exact_selected_input_identities(self):
        review=json.loads((ROOT/'tools/ae350_ble_business_indirect_review.json').read_text())
        actual={'firmware/ae350/'+p:runtime.sha(ROOT/'firmware/ae350'/p)
                for p in legacy.selected_inputs(True,'ilm64k_dlm64k',True)}
        self.assertEqual(review['input_sha256'],actual)
        self.assertEqual(review['disassembly_sha256'],'4b75454ea9517d560d1c0efef744d5d974965e5060bcffe77ae60318620d8f1c')

    def test_cli_requires_explicit_custom_board_mode(self):
        for mode in ('--current-workstation','--resource-rework','--cnn-timing85'):
            q=subprocess.run([sys.executable,str(ROOT/'build.py'),'--workstation-profile',profile.CLASSIC_RUNTIME_NAME,mode],capture_output=True,text=True)
            self.assertNotEqual(q.returncode,0)
            self.assertIn('--workstation-profile requires --prepare-custom-board',q.stderr)

    def test_candidate_constraints_remain_scoped_and_unaccepted(self):
        cdc=runtime.cdc_bundle()
        self.assertFalse(cdc['physical_endpoint_resolution_verified'])
        self.assertFalse(cdc['physical_timing_verified'])
        self.assertNotIn('set_clock_groups',cdc['sdc'])
        self.assertNotIn('get_clocks',cdc['sdc'])
        self.assertIn('boot_id*',cdc['sdc'])
        self.assertNotIn('published_epoch*',cdc['sdc'])

@unittest.skipUnless(os.environ.get('GW138K_CLASSIC_RUNTIME_PREPARED'),'Set GW138K_CLASSIC_RUNTIME_PREPARED to actual joint prepare')
class Prepared(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.output=Path(self.temp.name)/'candidate'
        shutil.copytree(os.environ['GW138K_CLASSIC_RUNTIME_PREPARED'],self.output)
        self.stage=self.output/'workstation/Prj1'
        self.metadata=json.loads((self.output/'integration_inputs.json').read_text())
        self.record=self.metadata['classic_runtime']
        self.evidence=self.output/'ae350_firmware'
        self.build=self.metadata['ae350_firmware']['build']

    def test_actual_full_prepare_rom_and_callback_closure(self):
        artifact=profile.verify(ROOT,self.output)
        self.assertEqual(artifact['profile'],profile.CLASSIC_RUNTIME_NAME)
        graph=runtime.verify_build(ROOT,self.evidence,self.build)
        self.assertEqual(graph['reviewed_JALR_sites'],171)
        self.assertEqual(graph['stack']['conservative_peak_bytes'],1904)
        self.assertEqual(self.build['capacity']['rom_capacity_bytes'],131072)
        self.assertGreater(self.record['enabled_hdl_count'],270)
        self.assertEqual((self.stage/'firmware/boot.mem').read_bytes(),(self.evidence/'boot.mem').read_bytes())
        self.assertFalse(self.record['hardware_accepted'])

    def test_missing_real_nested_provider_is_rejected_by_preprocessor(self):
        (self.stage/'rtl/workstation/workstation_profile_ae350_business_v1.sv').unlink()
        tool=next(iter(self.record['tool_sha256']))
        with self.assertRaisesRegex(ValueError,'include/macro closure failed'):
            runtime._preprocess(self.stage,tool,runtime._selected_hdl(self.stage)[1])

    def test_actual_rom_and_pcm_macro_loss_fail_even_with_refreshed_preprocess_record(self):
        source=self.stage/runtime.PROVIDER;original=source.read_text()
        for macro in ('WORKSTATION_AE350_ROM128','WORKSTATION_AE350_PCM'):
            with self.subTest(macro=macro):
                source.write_text(original.replace('`define '+macro+'\n',''))
                _,hdl=runtime._selected_hdl(self.stage);tool=next(iter(self.record['tool_sha256']))
                argv,payload,_=runtime._preprocess(self.stage,tool,hdl)
                (self.output/'classic_runtime_preprocessed.v').write_bytes(payload)
                changed=copy.deepcopy(self.record)
                changed.update(command=argv,preprocessed_sha256=hashlib.sha256(payload).hexdigest(),enabled_hdl_sha256={p:runtime.sha(self.stage/p)for p in hdl})
                with self.assertRaisesRegex(ValueError,'actual macro/ABI branch missing'):
                    runtime.verify_selection(ROOT,self.stage,self.output,changed)
        source.write_text(original)

    def test_removed_pcm_compilation_owner_is_rejected(self):
        from xml.etree import ElementTree
        p=self.stage/'Prj1.gprj';tree=ElementTree.parse(p);entries=tree.find('FileList')
        for entry in entries:
            if entry.get('path')==pcm.SOURCES[0]:entry.set('enable','0')
        tree.write(p)
        with self.assertRaisesRegex(ValueError,'compilation owner omitted'):
            runtime.verify_selection(ROOT,self.stage,self.output,self.record)

    def test_binary_or_callback_review_cannot_be_forged(self):
        p=self.evidence/'firmware.bin';old=p.read_bytes();p.write_bytes(bytes([old[0]^1])+old[1:])
        with self.assertRaisesRegex(ValueError,'ELF/BIN/ROM identity drift'):runtime.verify_build(ROOT,self.evidence,self.build)
        p.write_bytes(old)
        p=self.evidence/'runtime_indirect_review.json';review=json.loads(p.read_text())
        # Removing a real JALR edge must fail actual report reconstruction.
        review['sites'].pop(0)
        p.write_text(json.dumps(review))
        with self.assertRaises((ValueError,AssertionError)):runtime.verify_build(ROOT,self.evidence,self.build)

    def test_capability_acceptance_cannot_be_fabricated(self):
        for field in ('GeneralBonding_enabled','PCM_sustained_verified','measured_delay_valid'):
            changed=dict(self.build);changed[field]=True
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'acceptance fabricated'):
                runtime.verify_build(ROOT,self.evidence,changed)
        for field in ('GeneralBonding_enabled','hardware_accepted','physical_CDC_accepted'):
            changed=dict(self.record);changed[field]=True
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'acceptance fabricated'):
                runtime.verify_selection(ROOT,self.stage,self.output,changed)

if __name__=='__main__':unittest.main()
