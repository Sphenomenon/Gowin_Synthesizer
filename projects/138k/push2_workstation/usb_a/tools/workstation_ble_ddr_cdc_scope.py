"""Exact revision2 source gate shared by read-only BLE DDR CDC reviews.

This is a new scope. It does not change the revision1 configuration identity
or establish physical CDC, reset or hardware acceptance.
"""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree

from tools.workstation_ble_recording_policy import metadata as ble_metadata
from tools.workstation_bluetooth_ddr import verify_prepared
from tools.workstation_recording_policy import metadata as recording_metadata, verify_address_map

SCOPE = 'runtime-r00-no-local-panel-ble-ddr-v2'
LEGACY_SCOPE = 'legacy-v1'
PROFILE = 'custom138k-workstation-r00-no-local-panel-v1'
PROFILE_SOURCE = 'boards/custom_138k/workstation_profile_r00_no_local_panel_v1.json'
CONFIGURATION_SHA256 = '91b4e11fd6c293d58784d38726c542e4f2379bfb3a1503cd8eb2aa21b2508f7c'
COMPILED_INPUTS_SHA256 = '2079bd030f6011aa74592f5916b60998e00ec007d3346fd3220346584b473d40'
COMPILED_ORDER_SHA256 = '8aa696190fcc15a6a8019c07e7221ae1f9f35df31e2d0865c275071e3d5e967f'
COUNTER_SOURCE = 'src/migration/gw138k_counter_cdc.sv'
COUNTER_SHA256 = '1b6ff697ccd951995b7331ac483f3c7672a959a9a767465eb57d92d80f3afa8c'
SOURCE_SHA256 = {
    'rtl/workstation/gw138k_push_workstation_top.v': '08237ed942a27b1f68422b913fa23f0debb3e035b6922f8aacfcc8b077f0869e',
    'rtl/services/workstation_recording_seal_bridge.sv': '1512a14e01725845350a76d2ea78e521f0a99bc362015f8cf87d3db8d61883f4',
    'rtl/memory/workstation_recording_ddr_authority.sv': 'cdef84729cf2f971597fdccfe6b5926eda7242b9d352fc14783059b01f8cc083',
    'rtl/memory/workstation_runtime_memory_guard.sv': 'c07b1db351c3a2851e5ba9446801a73cad99e90b5155afaed8c2fec6c4b3424d',
    'rtl/memory/workstation_recording_ddr_owner_mux.sv': '2af5a52d3bf9c67f93eef803e07bd9b9e636c1f65348676289dc13b487e76bf5',
    'rtl/music/music_async_fifo.sv': 'e5a190502bec8bb402ad3c44d45d9f61702ddbdbe144baeb67f4da416fe82792',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('revision2 BLE DDR CDC scope: ' + message)


def validate_compiled_inputs(prepared, enabled, actual_sha256=None):
    """Pin the actual selected compilation, including the serial counter.

    Merely finding the old staged file cannot establish that it was compiled.
    A later balanced source selection needs its own explicit source review,
    even when the business configuration and all register names are equal.
    """
    identities = prepared.get('enabled_inputs')
    require(isinstance(identities, dict) and set(enabled) == set(identities)
            and len(enabled) == len(set(enabled)),
            'GPRJ enabled inputs differ from prepared compilation')
    require(digest(identities) == COMPILED_INPUTS_SHA256
            and digest(enabled) == COMPILED_ORDER_SHA256 and enabled.count(COUNTER_SOURCE) == 1,
            'reviewed serial-counter compilation selection changed')
    if actual_sha256 is not None:
        require(actual_sha256 == {path:identity['sha256'] for path,identity in identities.items()},
                'compiled input bytes differ from prepared identities')
    return dict(enabled_input_count=len(enabled), enabled_inputs_sha256=COMPILED_INPUTS_SHA256,
                enabled_order_sha256=COMPILED_ORDER_SHA256,
                counter_source=COUNTER_SOURCE, counter_sha256=COUNTER_SHA256,
                balanced_counter_source_selected=False)


def validate_profile(root, prepared, *, stage=None):
    root = Path(root)
    descriptor = json.loads((root / PROFILE_SOURCE).read_text())
    require(prepared.get('schema') == 1 and prepared.get('profile') == PROFILE
            and prepared.get('revision') == 2 and prepared.get('profile_source') == PROFILE_SOURCE
            and re.fullmatch(r'[0-9a-f]{64}', prepared.get('profile_sha256', '')) is not None,
            'explicit prepared revision2 profile required')
    require(prepared.get('configuration') == descriptor.get('configuration')
            and digest(prepared.get('configuration')) == CONFIGURATION_SHA256,
            'complete supported revision2 configuration changed')
    require(descriptor.get('revision') == 2, 'maintained descriptor revision changed')
    recording = prepared.get('recording', {})
    require({k: v for k, v in recording.items() if k != 'address_map'} == recording_metadata(ble_raw_ddr=True),
            'owner8 recording metadata changed')
    ble = dict(prepared.get('ble_recording_storage', {}))
    adaptation = ble.pop('adaptation', None)
    require(ble == ble_metadata(), 'raw BLE storage metadata changed')
    require(isinstance(adaptation, dict), 'checked BLE adaptation evidence missing')
    for source, expected in SOURCE_SHA256.items():
        require(hashlib.sha256((root / source).read_bytes()).hexdigest() == expected,
                'reviewed maintained composition changed: ' + source)
    compilation = None
    if stage is not None:
        file_list = ElementTree.parse(Path(stage) / 'Prj1.gprj').find('FileList')
        require(file_list is not None, 'GPRJ FileList missing')
        enabled = [entry.get('path') for entry in file_list if entry.get('enable') == '1']
        compilation = validate_compiled_inputs(prepared, enabled,
            {path:hashlib.sha256((Path(stage)/path).read_bytes()).hexdigest() for path in enabled})
        require(hashlib.sha256((Path(stage) / COUNTER_SOURCE).read_bytes()).hexdigest() == COUNTER_SHA256,
                'reviewed compiled serial counter bytes changed')
        for source, expected in SOURCE_SHA256.items():
            target = ('src/push2/gw138k_push_workstation_top.v'
                      if source == 'rtl/workstation/gw138k_push_workstation_top.v' else source)
            require(hashlib.sha256((Path(stage) / target).read_bytes()).hexdigest() == expected,
                    'reviewed staged composition changed: ' + target)
        verify_address_map(root, stage, recording.get('address_map'))
        verify_prepared(root, stage, adaptation)
    return dict(scope=SCOPE, revision=2, complete_configuration_sha256=CONFIGURATION_SHA256,
                prepared_profile_source_sha256=prepared['profile_sha256'],
                compilation_selection=compilation,
                current_root_profile_bytes_equivalence_claimed=False,
                raw_root_reset='reset_n', ledger_reset_is_observed_only=True,
                physical_cdc_accepted=False, full_reset_accepted=False)
