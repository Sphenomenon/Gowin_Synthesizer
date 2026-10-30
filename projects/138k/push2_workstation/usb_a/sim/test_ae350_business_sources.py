#!/usr/bin/env python3
"""Check native business selection, unchanged wire engines and isolation."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[3]
sys.path.insert(0,str(ROOT))
from tools import workstation_cpu_business as selection
from tools import workstation_bluetooth_ddr as legacy
from tools import workstation_profile as profile
class BusinessSources(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.stage=Path(self.temp.name);native=self.stage/'native_bluetooth'
        subprocess.run([sys.executable,str(REPO/'projects/25k/example/RTL8723DS_PROTOCOL/prepare_adapted.py'),
            '--output',str(native)],check=True,capture_output=True)
        protocol=REPO/'projects/25k/example/RTL8723DS_PROTOCOL'
        for name,relative in legacy.STAGED_PATHS.items():
            if name=='bt_gatt.v':continue
            original=(ROOT/'rtl/bluetooth'/name if name=='workstation_bluetooth.sv' else
                protocol/('adaptations' if name=='bt_verilog_core.v' else 'rtl')/name)
            target=self.stage/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
    def test_versioned_bytes_replace_retired_owner(self):
        evidence=selection.prepare(ROOT,self.stage)
        self.assertFalse((self.stage/'native_bluetooth/ble_recording.v').exists())
        self.assertFalse(evidence['rtl_text_generation'])
        for dest,source in selection.COPIES.items():self.assertEqual((self.stage/dest).read_bytes(),(ROOT/source).read_bytes())
        selection.verify_prepared(ROOT,self.stage,evidence)
    def test_original_input_drift_is_rejected(self):
        p=self.stage/'native_bluetooth/ble_recording.v';p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'original stage drift'):selection.prepare(ROOT,self.stage)
    def test_staged_drift_and_retired_owner_are_rejected(self):
        evidence=selection.prepare(ROOT,self.stage);p=self.stage/'native_bluetooth/ble_protocol_command.v'
        p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'staged source drift'):selection.verify_prepared(ROOT,self.stage,evidence)
        shutil.copyfile(ROOT/selection.COPIES['native_bluetooth/ble_protocol_command.v'],p)
        (self.stage/'native_bluetooth/ble_recording.v').write_text('module ble_recording; endmodule\n')
        with self.assertRaisesRegex(ValueError,'retired RTL business owner'):selection.verify_prepared(ROOT,self.stage,evidence)
    def test_five_native_glue_layers_elaborate(self):
        selection.prepare(ROOT,self.stage)
        protocol=REPO/'projects/25k/example/RTL8723DS_PROTOCOL'
        native=self.stage/'native_bluetooth'
        for name in ('bt_hci_init.v','bt_uart_fast.v','bt_acl_bridge.v'):
            shutil.copyfile(protocol/'adaptations'/name,native/name)
        for name in ('bt_uart.v','reset_release_sync.v'):
            shutil.copyfile(REPO/'example/RTL8723DS/vendor/rtl8723ds_ble/rtl'/name,native/name)
        (native/'patch_path.vh').write_text('`define WORKSTATION_BLE_PATCH_FILE "unused.mem"\n')
        files=[*native.glob('*.v'),self.stage/'rtl/bluetooth/workstation_bluetooth.sv',
            *(ROOT/n for n in selection.SOURCES),ROOT/'rtl/memory/workstation_sdp.sv']
        result=subprocess.run(['iverilog','-g2012','-s','workstation_bluetooth','-I'+str(self.stage),
            '-o',str(self.stage/'glue.vvp'),*map(str,files)],text=True,capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_new_profile_is_explicit_and_has_real_firmware_and_native_owners(self):
        selected=profile.load(ROOT,profile.CPU_BUSINESS_NAME)
        self.assertTrue(profile.specification(selected['name'])['business_owner_enabled'])
        for name,spec in profile.PROFILE_REGISTRY.items():
            if name!=selected['name']:self.assertFalse(spec.get('business_owner_enabled',False))
        self.assertEqual(selected['configuration']['ae350_boot_rom_bytes'],65536)
        self.assertIn('projects/138k/push2_workstation/usb_a/firmware/ae350/ble_business_owner.c',selected['source_sha256'])
        self.assertIn('projects/138k/push2_workstation/usb_a/'+selection.SOURCES[0],selected['source_sha256'])
@unittest.skipUnless(os.environ.get('GW138K_BUSINESS_PREPARED'),'Set GW138K_BUSINESS_PREPARED to a real prepared business candidate')
class PreparedBusiness(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.output=Path(self.temp.name)/'candidate'
        shutil.copytree(os.environ['GW138K_BUSINESS_PREPARED'],self.output)
        self.stage=self.output/'workstation/Prj1'
    def test_actual_compilation_and_reachable_c_owner(self):
        artifact=profile.verify(ROOT,self.output)
        self.assertEqual(artifact['profile'],profile.CPU_BUSINESS_NAME)
        self.assertNotIn('native_bluetooth/ble_recording.v',artifact['enabled_inputs'])
        self.assertFalse((self.stage/'native_bluetooth/ble_recording.v').exists())
        build=artifact['ae350_firmware']['build']
        self.assertTrue(build['business_owner_enabled'])
        self.assertEqual(build['capacity']['rom_capacity_bytes'],65536)
        self.assertIn('a138_ble_business_firmware_pump',build['call_chain_stack']['reachable_functions'])
        self.assertEqual(build['call_chain_stack']['reviewed_indirect_calls']['sites'],
            json.loads((ROOT/'tools/ae350_ble_business_indirect_review.json').read_text())['sites'])
        self.assertFalse(artifact['hardware_tested'])
    def test_changed_native_engine_and_reintroduced_retired_owner_rejected(self):
        p=self.stage/selection.SOURCES[0];old=p.read_bytes();p.write_bytes(old+b'\n')
        with self.assertRaisesRegex(ValueError,'drift|closure changed'):profile.verify(ROOT,self.output)
        p.write_bytes(old)
        (self.stage/'native_bluetooth/ble_recording.v').write_text('module ble_recording; endmodule\n')
        with self.assertRaisesRegex(ValueError,'retired|inventory'):profile.verify(ROOT,self.output)
    def test_changed_callback_review_rejected(self):
        p=self.output/'ae350_firmware/indirect_call_review.json'
        p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'artifact|changed|drift'):profile.verify(ROOT,self.output)
if __name__=='__main__':unittest.main()

