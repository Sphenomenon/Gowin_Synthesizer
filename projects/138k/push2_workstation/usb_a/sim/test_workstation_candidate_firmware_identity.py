"""New preboard identities separate path-sensitive diagnostics from firmware."""
from pathlib import Path
import copy,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_profile import candidate_firmware_identity,identity_digest

class FirmwareIdentity(unittest.TestCase):
    def test_diagnostics_remain_outside_runtime_identity(self):
        keys=('input_sha256','tool_versions','compiled_sources','capacity','elf_sha256','binary_sha256',
              'rom_sha256','memory_profile','recording_api_enabled','business_owner_enabled')
        build={k:{'value':'a'}for k in keys};build['artifacts_sha256']={'firmware.map':'path-digest'}
        record=dict(policy='firmware-policy',project_rom_installed=True,installed_rom={'sha256':'rom'},build=build)
        self.assertIs(candidate_firmware_identity(record),record)
        policy='compiler_inputs_and_firmware_v1';base=identity_digest(candidate_firmware_identity(record,policy))
        other=copy.deepcopy(record);other['build']['artifacts_sha256']['firmware.map']='other-path-digest'
        self.assertEqual(base,identity_digest(candidate_firmware_identity(other,policy)))
        self.assertNotEqual(identity_digest(record),identity_digest(other))
        for key in keys:
            other=copy.deepcopy(record);other['build'][key]={'value':'changed'}
            self.assertNotEqual(base,identity_digest(candidate_firmware_identity(other,policy)),key)
        with self.assertRaises(ValueError):candidate_firmware_identity(record,'unknown')

if __name__=='__main__':unittest.main(verbosity=2)
