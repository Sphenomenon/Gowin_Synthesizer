"""Verify the frozen export; stage Gowin attributes and optional compact HCI/H5 buffers."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/rtl8723ds_ble'
RTL_NAMES = (VENDOR / 'sources.f').read_text().splitlines()
ADAPTATIONS = {
    'rtl/bt_hci_init.v': (
        '(* rom_style = "block" *)',
        '(* rom_style = "block", syn_romstyle = "block_rom" *)'),
    'rtl/bt_uart.v': (
        '(* ASYNC_REG = "TRUE" *)',
        '(* ASYNC_REG = "TRUE", syn_preserve = 1, syn_keep = 1 *)'),
    'rtl/reset_release_sync.v': (
        '(* ASYNC_REG = "TRUE" *)',
        '(* ASYNC_REG = "TRUE", syn_preserve = 1, syn_keep = 1 *)'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_vendor():
    manifest = json.loads((VENDOR / 'inputs.json').read_text())
    for name, record in manifest['files'].items():
        path = VENDOR / name
        if path.stat().st_size != record['bytes'] or sha(path) != record['sha256']:
            raise ValueError('BLE upstream input drift: ' + name)
    original = json.loads((VENDOR / 'MANIFEST.json').read_text())
    for name, record in original['files'].items():
        if manifest['files'][name] != record:
            raise ValueError('BLE export manifest mismatch: ' + name)
    return manifest


def stage_vendor(destination, compact_hci=False, compact_h5=False):
    verify_vendor()
    destination = Path(destination)
    shutil.copytree(VENDOR, destination)
    for name, (old, new) in ADAPTATIONS.items():
        path = destination / name
        text = path.read_text()
        if text.count(old) != 1:
            raise ValueError('BLE adaptation anchor mismatch: ' + name)
        path.write_text(text.replace(old, new))
    if compact_hci:
        shutil.copy2(ROOT / 'rtl/bluetooth/adaptations/bt_hci_init.v',
                     destination / 'rtl/bt_hci_init.v')
    if compact_h5:
        shutil.copy2(ROOT / 'rtl/bluetooth/adaptations/bt_h5_transport.v',
                     destination / 'rtl/bt_h5_transport.v')
    # A ROM path relative to the project root also works when Gowin spawns its
    # synthesis subprocess in impl/gwsynthesis (Gowin resolves project inputs).
    return [destination / name for name in RTL_NAMES]
