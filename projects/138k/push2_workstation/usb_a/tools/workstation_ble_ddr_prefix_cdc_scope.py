"""Explicit prefix-counter/registered-TF source scope; never a CDC acceptance.

The old serial scope remains byte-for-byte unchanged. Its metadata-only gate
is reused below; its compilation identities and mapped closures are not.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

from tools.workstation_ble_ddr_cdc_scope import (
    PROFILE, PROFILE_SOURCE, CONFIGURATION_SHA256, digest,
    SOURCE_SHA256 as BUSINESS_SOURCE_SHA256, validate_profile as validate_business_metadata,
)
from tools.workstation_bluetooth_ddr import verify_prepared
from tools.workstation_recording_policy import verify_address_map
from tools.workstation_runtime_counter import metadata as counter_metadata, selection_evidence, LEGACY, NATIVE

SCOPE = 'runtime-r00-no-local-panel-ble-ddr-prefix-v1'
CANDIDATE = 'custom138k-workstation-r00-no-local-panel-v1-c7d66b419868f7f4'
CANDIDATE_INPUT_SHA256 = 'c7d66b419868f7f4a0bbd2b98e4ab17c8cdaf8d8e21ba8b78cbe779dc97332c2'
COMPILED_INPUTS_SHA256 = '33ba5f56ab7c95d650b38f61520c83e1cfea4b0e16ffa7c41b6c2fe172302362'
COMPILED_ORDER_SHA256 = '436daef0ff51c65cea591f874303f08754656fec14bfb207660246d05f8f40cc'
STAGED_INPUTS_SHA256 = 'fa701dd831bcb1523739497ad5e5e3c0dfedef431555f76506e4aa5e9ec4ad1a'
SERIAL_METADATA_HELPER_SHA256 = '64740b28a8386f540bde14f459c448d948f6fba96f262e16735f9e6d8c9e7159'
COUNTER_SOURCE = NATIVE
COUNTER_SHA256 = 'c921ff58a2204dee35972d960a98d6820803155b89c090fdcb3d111137521f5c'
TF_SOURCE = 'rtl/tf_audio/workstation_tf_frame_bridge.sv'
TF_SHA256 = 'eb5895b975dc699178a6e451f2f05d481f63424848ebe153c1402a21a63baf31'
SOURCE_SHA256 = dict(BUSINESS_SOURCE_SHA256, **{COUNTER_SOURCE: COUNTER_SHA256, TF_SOURCE: TF_SHA256})


def require(ok, message):
    if not ok:
        raise ValueError('prefix BLE DDR CDC scope: ' + message)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_compiled_inputs(prepared, enabled, actual_sha256=None):
    identities = prepared.get('enabled_inputs')
    require(isinstance(identities, dict) and set(enabled) == set(identities)
            and len(enabled) == len(set(enabled)), 'GPRJ enabled inputs differ from prepared compilation')
    require(len(enabled) == 269 and digest(identities) == COMPILED_INPUTS_SHA256
            and digest(enabled) == COMPILED_ORDER_SHA256
            and enabled.count(NATIVE) == 1 and LEGACY not in enabled,
            'reviewed prefix compilation selection changed')
    if actual_sha256 is not None:
        require(actual_sha256 == {path: identity['sha256'] for path, identity in identities.items()},
                'compiled input bytes differ from prepared identities')
    return dict(enabled_input_count=269, enabled_inputs_sha256=COMPILED_INPUTS_SHA256,
                enabled_order_sha256=COMPILED_ORDER_SHA256, counter_source=NATIVE,
                counter_sha256=COUNTER_SHA256, balanced_counter_source_selected=True)


def validate_staged_inputs(prepared, integration, actual_sha256):
    identities = prepared.get('staged_input_sha256')
    require(isinstance(identities, dict) and len(identities) == 593
            and digest(identities) == STAGED_INPUTS_SHA256,
            'reviewed 593 staged input identities changed')
    require(integration.get('staged_input_sha256') == identities,
            'integration and prepared staged identities differ')
    require(actual_sha256 == identities, 'actual staged input bytes differ from prepared identities')
    return dict(staged_input_count=593, staged_inputs_sha256=STAGED_INPUTS_SHA256,
                all_staged_bytes_verified=True)


def validate_profile(root, prepared, *, stage=None):
    root = Path(root)
    require(file_sha(root / 'tools/workstation_ble_ddr_cdc_scope.py') == SERIAL_METADATA_HELPER_SHA256,
            'shared metadata-only helper bytes changed')
    # Do not pass a stage: this checks only the unchanged business metadata and
    # six source contracts, never the old serial compilation or graph closures.
    validate_business_metadata(root, prepared)
    require(prepared.get('candidate_identity') == CANDIDATE
            and prepared.get('candidate_input_sha256') == CANDIDATE_INPUT_SHA256,
            'exact prefix candidate source identity required')
    for source, expected in SOURCE_SHA256.items():
        require(file_sha(root / source) == expected, 'reviewed maintained composition changed: ' + source)
    expected_counter = counter_metadata(root)
    require(expected_counter['source_sha256'] == COUNTER_SHA256
            and prepared.get('runtime_audio', {}).get('counter_cdc') == expected_counter,
            'prepared native counter policy/identity changed')
    compilation = staged = selected = None
    if stage is not None:
        stage = Path(stage)
        integration = json.loads((stage.parents[1] / 'integration_inputs.json').read_text())
        require(integration.get('runtime_audio', {}).get('counter_cdc') == expected_counter,
                'integration native counter policy/identity changed')
        file_list = ET.parse(stage / 'Prj1.gprj').find('FileList')
        require(file_list is not None, 'GPRJ FileList missing')
        old = [entry for entry in file_list if entry.get('path') == LEGACY]
        native = [entry for entry in file_list if entry.get('path') == NATIVE]
        require(len(old) == len(native) == 1 and old[0].get('enable') == '0'
                and native[0].get('enable') == '1', 'exact disabled-serial/enabled-native declarations required')
        enabled = [entry.get('path') for entry in file_list if entry.get('enable') == '1']
        compilation = validate_compiled_inputs(prepared, enabled, {path: file_sha(stage / path) for path in enabled})
        staged = validate_staged_inputs(prepared, integration,
            {path: file_sha(stage / path) for path in prepared.get('staged_input_sha256', {})})
        selected = selection_evidence(stage)
        require(selected['selection'] == 'compiled_native_balanced' and selected['sha256'] == COUNTER_SHA256,
                'compiled native counter binding changed')
        for source, expected in SOURCE_SHA256.items():
            target = 'src/push2/gw138k_push_workstation_top.v' if source.startswith('rtl/workstation/gw138k_push_workstation_top') else source
            require(file_sha(stage / target) == expected, 'reviewed staged composition changed: ' + target)
        verify_address_map(root, stage, prepared['recording']['address_map'])
        verify_prepared(root, stage, prepared['ble_recording_storage']['adaptation'])
    return dict(scope=SCOPE, revision=2, complete_configuration_sha256=CONFIGURATION_SHA256,
                candidate_identity=CANDIDATE, candidate_input_sha256=CANDIDATE_INPUT_SHA256,
                prepared_profile_source_sha256=prepared['profile_sha256'],
                compilation_selection=compilation, staged_input_selection=staged,
                counter_source_selection=selected, old_serial_closure_inherited=False,
                current_root_profile_bytes_equivalence_claimed=False,
                raw_root_reset='reset_n', ledger_reset_is_observed_only=True,
                physical_cdc_accepted=False, full_reset_accepted=False)
