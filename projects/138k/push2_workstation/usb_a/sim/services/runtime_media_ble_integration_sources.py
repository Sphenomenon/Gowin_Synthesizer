"""Read-only staged BLE preparation for the physical-runtime media regression."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

from runtime_media_integration_sources import _unique_owners


def prepare_bluetooth(root,output):
    root,output=Path(root).resolve(),Path(output).resolve()
    repository=root.parents[3]
    sys.path.insert(0,str(root));sys.path.insert(0,str(root/'sim'))
    from tools import workstation_bluetooth,workstation_pinout
    from test_workstation_pinout import fixture
    pinout=output/'pinout';pinout.mkdir(exist_ok=False)
    profile,payloads,core=fixture()
    netlists={role:workstation_pinout.Netlist(payload) for role,payload in payloads.items()}
    plan=workstation_pinout.resolve(profile,netlists,core)
    with patch.object(workstation_pinout,'load_sources',return_value=(netlists,{})):
        metadata=workstation_bluetooth.prepare(root,output,output,pinout,plan,relative_rom_paths=True)
    prepared=output/'ble_prepare.json';prepared.write_text(json.dumps(metadata,indent=2)+'\n')
    staged=[output/name for name in metadata['sources']]
    maintained=[repository/name for name in metadata['source_snapshot_sha256']]
    maintained += [root/name for name in (
        'rtl/bluetooth/workstation_bluetooth.sv','tools/workstation_bluetooth.py',
        'tools/workstation_pinout.py','tools/stage_usb_firmware.py','sim/test_workstation_pinout.py',
        'boards/custom_138k/bluetooth.json','boards/custom_138k/pinout.json',
        'rtl/bluetooth/WORKSTATION_BLE_SEAL_CONTRACT.md')]
    fixtures=[prepared,output/'native_bluetooth/patch_path.vh',output/'native_bluetooth/rtl8723ds_patch.mem',
              *sorted(pinout.iterdir())]
    return staged,maintained+fixtures,metadata


def unique_sources(paths):
    if len(paths)!=len(set(paths)):raise ValueError('Duplicate runtime/BLE source path')
    _unique_owners(paths)
