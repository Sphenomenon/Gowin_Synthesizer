#!/usr/bin/env python3
"""Revision2 BLE source selection, real-top wiring and prepared provenance."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_ble_recording_policy as policy

def compact(text):
    return re.sub(r'\s+','',re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S))

def ports(text,instance):
    match=re.search(r'\b'+re.escape(instance)+r'\s*\(',text)
    if not match:raise AssertionError('missing actual instance '+instance)
    start=match.end();depth=1;end=start
    while depth:
        if text[end]=='(':depth+=1
        if text[end]==')':depth-=1
        end+=1
    pairs=re.findall(r'\.(\w+)\(([^()]*)\)',compact(text[start:end-1]))
    if len(pairs)!=len(dict(pairs)):raise AssertionError('duplicate port on '+instance)
    return dict(pairs)

class Selection(unittest.TestCase):
    def test_revision2_is_explicit_and_preserves_other_profile_defaults(self):
        selected=profiles.load(ROOT,profiles.R00_NO_LOCAL_PANEL_NAME)
        self.assertEqual(selected['revision'],2)
        self.assertEqual(selected['configuration']['ble_recording_storage_policy'],policy.POLICY)
        self.assertTrue(profiles.specification(selected['name'])['ble_recording_storage_enabled'])
        self.assertEqual(profiles.specification(selected['name'])['integration_identity'],
            'custom138k-native-dual-rate-r00-no-local-panel-revision2')
        for name in (profiles.NAME,profiles.NO_CNN_NAME,profiles.R00_NAME):
            self.assertFalse(profiles.specification(name).get('ble_recording_storage_enabled',False))
            self.assertNotIn('ble_recording_storage_policy',profiles.specification(name)['configuration'])
        for name in (*policy.SOURCES,*policy.DEPENDENCIES):
            self.assertIn('projects/138k/push2_workstation/usb_a/'+name,selected['source_sha256'])
        metadata=policy.metadata()
        self.assertEqual(metadata['sample_rates_hz'],[48000])
        self.assertEqual(metadata['capacity_bytes'],65536)
        self.assertFalse(metadata['format_extended'])
        for field in ('net_resource_saving_proven','physical_cdc_accepted','hardware_tested','deployment_allowed'):
            self.assertFalse(metadata[field])

    def test_actual_selected_top_connects_owned_interfaces_and_common_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'top.sv'
            run=subprocess.run(['iverilog','-g2012','-E','-I',str(ROOT),'-o',str(output),
                str(ROOT/profiles.R00_NO_LOCAL_PANEL_PROVIDER)],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            text=output.read_text()
        store=ports(text,'recording_ble_store');ble=ports(text,'u_bluetooth')
        fields={
            'start_valid':('i','o','raw_start_valid&&recording_channel_ready50','raw_start_valid'),
            'start_ready':('o','i','raw_start_ready','raw_start_ready&&recording_channel_ready50'),
            'start_done':('o','i','raw_start_done','raw_start_done'),
            'clear_valid':('i','o','raw_clear_valid','raw_clear_valid'),
            'clear_ready':('o','i','raw_clear_ready','raw_clear_ready'),
            'clear_done':('o','i','raw_clear_done','raw_clear_done'),
            'capture_valid':('i','o','raw_capture_valid','raw_capture_valid'),
            'capture_index':('i','o','raw_capture_index','raw_capture_index'),
            'capture_pcm':('i','o','raw_capture_pcm','raw_capture_pcm'),
            'capture_ready':('o','i','raw_capture_ready','raw_capture_ready'),
            'close_valid':('i','o','raw_close_valid','raw_close_valid'),
            'close_ready':('o','i','raw_close_ready','raw_close_ready'),
            'drained':('o','i','raw_drained','raw_drained'),
            'fault':('o','i','raw_fault','raw_fault'),
            'object_fault':('o','i','raw_object_fault','raw_object_fault'),
            'channel_fault':('o','i','raw_channel_fault','raw_channel_fault'),
            'failure_code':('o','i','raw_failure','raw_failure'),
            'accepted_frames':('o','i','raw_accepted','raw_accepted'),
            'committed_frames':('o','i','raw_committed','raw_committed'),
            'fetch_valid':('i','o','raw_fetch_valid','raw_fetch_valid'),
            'fetch_ready':('o','i','raw_fetch_ready','raw_fetch_ready'),
            'fetch_offset':('i','o','raw_fetch_offset','raw_fetch_offset'),
            'fetch_length':('i','o','raw_fetch_length','raw_fetch_length'),
            'fetch_done':('o','i','raw_fetch_done','raw_fetch_done'),
            'fetch_fault':('o','i','raw_fetch_fault','raw_fetch_fault'),
            'cache_valid':('o','i','raw_cache_valid','raw_cache_valid'),
            'sample_addr':('i','o','raw_sample_addr','raw_sample_addr'),
            'sample_word':('o','i','raw_sample_word','raw_sample_word'),
        }
        for field,(store_direction,ble_direction,store_wire,ble_wire) in fields.items():
            with self.subTest(port=field):
                self.assertEqual(store[field+'_'+store_direction],store_wire)
                self.assertEqual(ble['raw_'+field+'_'+ble_direction],ble_wire)
        self.assertEqual(store['rst_ni'],'reset_n')
        self.assertEqual(store['native_protocol_fault_o'],'recording_bridge_protocol_fault[1]')
        cpu=ports(text,'u_recording')
        self.assertEqual(cpu['reset_ni'],'recording_memory_reset_n')
        self.assertEqual(cpu['backend_ready_i'],'recording_channel_ready')
        self.assertEqual(cpu['native_protocol_fault_o'],'recording_bridge_protocol_fault[0]')
        authority=ports(text,'recording_authority')
        self.assertEqual(authority['root_reset_ni'],'reset_n')
        self.assertEqual(authority['ledger_reset_ni'],'ddr_client_reset_n')
        mux=ports(text,'recording_owner8')
        self.assertEqual(mux['rst_ni'],'recording_memory_reset_n')
        self.assertEqual(mux['channel_ready_i'],'recording_channel_ready')
        self.assertEqual(mux['transport_fault_i'],
            'recording_transport_fault||recording_authority_fault|||recording_bridge_protocol_fault')
        self.assertTrue(ble['source_allowed_i'].startswith('recording_channel_ready50&&memory_guard_ready&&'))
        self.assertIn("!rate44",ble['source_allowed_i'])
        self.assertIn('recording_channel_meta<=recording_channel_ready;recording_channel_ready50<=recording_channel_meta;',compact(text))
        self.assertIn("recording_memory_release<={recording_memory_release[0],1'b1};",compact(text))
        self.assertIn('.EXTERNAL_RAW_STORE(1),.RAW_DRAIN_TIMEOUT_CYCLES(5000000)',compact(text))

@unittest.skipUnless(os.environ.get('GW138K_BLE_DDR_PREPARED'),'set GW138K_BLE_DDR_PREPARED to a real revision2 prepare')
class Prepared(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='ble-ddr-prepare-')
        self.addCleanup(temporary.cleanup)
        self.output=Path(temporary.name)/'candidate'
        shutil.copytree(Path(os.environ['GW138K_BLE_DDR_PREPARED']),self.output,
            ignore=shutil.ignore_patterns('impl','__pycache__'))
        self.path=self.output/'integration_inputs.json'
        self.metadata=json.loads(self.path.read_text())

    def test_real_prepare_seals_selected_sources_and_adapted_wrapper(self):
        artifact=profiles.verify(ROOT,self.output)
        self.assertEqual(artifact['revision'],2)
        self.assertEqual(artifact['ble_recording_storage']['policy'],policy.POLICY)
        for source in policy.SOURCES:self.assertIn(source,artifact['enabled_inputs'])
        wrapper='rtl/bluetooth/workstation_bluetooth.sv'
        self.assertTrue(artifact['enabled_inputs'][wrapper]['adapted'])
        self.assertEqual(artifact['enabled_inputs'][wrapper]['sha256'],
            self.metadata['ble_recording_storage']['adaptation']['output_sha256']['workstation_bluetooth.sv'])
        self.assertTrue(artifact['recording']['default_ble_backend_replaced'])
        self.assertFalse(artifact['hardware_tested'])

    def test_claimed_policy_or_checked_adaptation_identity_cannot_be_forged(self):
        for kind in ('policy','hash','missing'):
            changed=copy.deepcopy(self.metadata)
            if kind=='policy':changed['ble_recording_storage']['policy']='on_chip_ram'
            elif kind=='hash':changed['ble_recording_storage']['adaptation']['output_sha256']['workstation_bluetooth.sv']='0'*64
            else:del changed['ble_recording_storage']
            self.path.write_text(json.dumps(changed))
            with self.subTest(kind=kind),self.assertRaises((ValueError,TypeError)):
                profiles.verify(ROOT,self.output)

    def test_staged_adapted_wrapper_drift_is_rejected(self):
        wrapper=self.output/'workstation/Prj1/rtl/bluetooth/workstation_bluetooth.sv'
        wrapper.write_bytes(wrapper.read_bytes()+b'\n// changed after checked adaptation\n')
        with self.assertRaises(ValueError):profiles.verify(ROOT,self.output)

if __name__=='__main__':unittest.main()
