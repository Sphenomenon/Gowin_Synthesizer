"""Explicit pitch-prefix/delay-FIFO/prefix-counter source scope; never a CDC acceptance.

The old serial, c7 prefix and 6b Chorus scopes remain unchanged. Their metadata-only gate
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

SCOPE = 'runtime-r00-no-local-panel-ble-ddr-pitch-fifo-v1'
CANDIDATE = 'custom138k-workstation-r00-no-local-panel-v1-18ed947312186187'
CANDIDATE_INPUT_SHA256 = '18ed947312186187106b453991cfead196e1ba9c5f52381b33b58d09edbdfc2a'
COMPILED_INPUTS_SHA256 = '794c334f0e9c35a1aec5f8d1f6d5048df21f2aba56ecb4ae58cc13ed86d9a36e'
COMPILED_ORDER_SHA256 = '436daef0ff51c65cea591f874303f08754656fec14bfb207660246d05f8f40cc'
STAGED_INPUTS_SHA256 = 'f005ae32d8a18f36947e7eada6f3293a1549916f19b59b4e7a718d81ac16edd8'
SERIAL_METADATA_HELPER_SHA256 = '64740b28a8386f540bde14f459c448d948f6fba96f262e16735f9e6d8c9e7159'
COUNTER_SOURCE = NATIVE
COUNTER_SHA256 = 'c921ff58a2204dee35972d960a98d6820803155b89c090fdcb3d111137521f5c'
TF_SOURCE = 'rtl/tf_audio/workstation_tf_frame_bridge.sv'
TF_SHA256 = 'eb5895b975dc699178a6e451f2f05d481f63424848ebe153c1402a21a63baf31'
from tools.workstation_chorus_provenance import source_bundle as chorus_metadata
CHORUS_SOURCE_SHA256 = {
    'rtl/audio/workstation_runtime_chorus_effect.sv': 'f0d9200a165d40f0b44fc69c3aaae3a8a75ed14420dd91d11ff49136f22e0176',
    'rtl/audio/workstation_runtime_chorus_effect.provenance.json': '41babc5ece0ec3ca5cae68e2f7d5c5069e93d1acb63224771d7483c138f32b48',
    'rtl/audio/workstation_runtime_chorus_effect.rate_delay_narrowing.json': '0f2811bdfa33f04111cc036cace4b986eecf25306cdb13fd297b56d0bcfbadf4',
    'rtl/audio/WORKSTATION_RUNTIME_CHORUS_DELAY.md': '538a8b16bbeaa9df60d1096cc226b4bc1fe7225b2a601cada8ae0e5349fa60cb',
    'tools/workstation_chorus_provenance.py': 'd70d41c8a56130b149a5c364f27869dc0202e233cf90a95dc2d4dc4d3823180e',
}
from tools.workstation_delay_storage_provenance import (
    source_bundle as delay_metadata, verify as verify_delay, STORAGE_POLICY,
    SOURCE as DELAY_SOURCE, PROVENANCE as DELAY_PROVENANCE, ADAPTATION as DELAY_ADAPTATION,
)
PITCH_SOURCE = 'rtl/audio/workstation_rate_pitch_expression.sv'
PITCH_SHA256 = 'c4053635f66995bba38cf7726bff58a74308d7b2c85f4023548f16780f81d6f0'
PREPARED_PROFILE_SHA256 = 'b57928716218b220cb7dd8f90f39e3c90cef706ef8e9aea1ffb3583d80acf6ac'
DELAY_SOURCE_SHA256 = {'rtl/audio/workstation_runtime_stereo_effects.sv': 'ca9f50cd0c70add7c04fe6230686510dbbd128561aebf7a0920d1eb463c5686f', 'rtl/audio/workstation_runtime_stereo_effects.provenance.json': '5af689e1adc920524e83d0ae9da87382a75a6bc2868c08fc246abb47814df68c', 'rtl/audio/workstation_runtime_stereo_effects.delay_fifo_storage.json': '5590b0082117f53247f5d30236d5547ac2f358ee66e7b874c3ce6199ec13fe51', 'tools/workstation_delay_storage_provenance.py': '45dc11b1284f21f3233be3c63132127d358844d0c80f6febcbec872a06a92cac', 'rtl/music/music_async_fifo.sv': 'e5a190502bec8bb402ad3c44d45d9f61702ddbdbe144baeb67f4da416fe82792', 'rtl/audio/stereo_effects.sv': 'e1197cd8b843b3f98b6254eca081af51f0e9b8ce61cf30f6cfdcf9e9cb2c98c6'}
SOURCE_SHA256 = dict(BUSINESS_SOURCE_SHA256, **{COUNTER_SOURCE: COUNTER_SHA256, TF_SOURCE: TF_SHA256},
                     **CHORUS_SOURCE_SHA256, **DELAY_SOURCE_SHA256, **{PITCH_SOURCE: PITCH_SHA256})

# Hash the complete extra source/review dependency closure in public audits.
AUDIT_SOURCES = tuple(dict.fromkeys((
    'tools/workstation_ble_ddr_pitch_fifo_cdc_scope.py',
    'tools/workstation_ble_ddr_pitch_fifo_cdc_endpoints.py',
    'tools/workstation_ble_ddr_cdc_scope.py',
    'tools/workstation_ble_ddr_chorus_cdc_scope.py',
    'tools/workstation_ble_ddr_chorus_cdc_endpoints.py',
    'tools/workstation_ble_ddr_prefix_cdc_scope.py',
    'tools/workstation_ble_ddr_prefix_cdc_endpoints.py',
    'tools/workstation_runtime_counter.py',
    'tools/workstation_bluetooth_ddr.py',
    'tools/workstation_ble_recording_policy.py',
    'tools/workstation_recording_policy.py',
    'sim/test_workstation_ble_ddr_pitch_fifo_cdc_scope.py',
    'tools/WORKSTATION_BLE_DDR_PITCH_FIFO_CDC.md',
    *SOURCE_SHA256,
)))


def require(ok, message):
    if not ok:
        raise ValueError('Pitch/FIFO BLE DDR CDC scope: ' + message)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_compiled_inputs(prepared, enabled, actual_sha256=None):
    identities = prepared.get('enabled_inputs')
    require(isinstance(identities, dict) and set(enabled) == set(identities)
            and len(enabled) == len(set(enabled)), 'GPRJ enabled inputs differ from prepared compilation')
    require(len(enabled) == 269 and digest(identities) == COMPILED_INPUTS_SHA256
            and digest(enabled) == COMPILED_ORDER_SHA256
            and enabled.count(NATIVE) == 1 and LEGACY not in enabled,
            'reviewed pitch/FIFO compilation selection changed')
    if actual_sha256 is not None:
        require(actual_sha256 == {path: identity['sha256'] for path, identity in identities.items()},
                'compiled input bytes differ from prepared identities')
    return dict(enabled_input_count=269, enabled_inputs_sha256=COMPILED_INPUTS_SHA256,
                enabled_order_sha256=COMPILED_ORDER_SHA256, counter_source=NATIVE,
                counter_sha256=COUNTER_SHA256, balanced_counter_source_selected=True)


def validate_staged_inputs(prepared, integration, actual_sha256):
    identities = prepared.get('staged_input_sha256')
    require(isinstance(identities, dict) and len(identities) == 599
            and digest(identities) == STAGED_INPUTS_SHA256,
            'reviewed 599 staged input identities changed')
    require(integration.get('staged_input_sha256') == identities,
            'integration and prepared staged identities differ')
    require(actual_sha256 == identities, 'actual staged input bytes differ from prepared identities')
    return dict(staged_input_count=599, staged_inputs_sha256=STAGED_INPUTS_SHA256,
                all_staged_bytes_verified=True)


def validate_profile(root, prepared, *, stage=None):
    root = Path(root)
    require(file_sha(root / 'tools/workstation_ble_ddr_cdc_scope.py') == SERIAL_METADATA_HELPER_SHA256,
            'shared metadata-only helper bytes changed')
    # Do not pass a stage: this checks only the unchanged business metadata and
    # six source contracts, never the old serial compilation or graph closures.
    validate_business_metadata(root, prepared)
    require(prepared.get('profile_sha256') == PREPARED_PROFILE_SHA256,
            'fixed synthesized prepared profile source identity required')
    require(prepared.get('candidate_identity') == CANDIDATE
            and prepared.get('candidate_input_sha256') == CANDIDATE_INPUT_SHA256,
            'exact pitch/FIFO candidate source identity required')
    for source, expected in SOURCE_SHA256.items():
        require(file_sha(root / source) == expected, 'reviewed maintained composition changed: ' + source)
    expected_counter = counter_metadata(root)
    require(expected_counter['source_sha256'] == COUNTER_SHA256
            and prepared.get('runtime_audio', {}).get('counter_cdc') == expected_counter,
            'prepared native counter policy/identity changed')
    expected_chorus = chorus_metadata(root)
    require(prepared.get('runtime_audio', {}).get('chorus_source') == expected_chorus,
            'prepared explicit Chorus provenance policy/identity changed')
    expected_delay = delay_metadata(root)
    require(prepared.get('runtime_audio', {}).get('delay_fifo_storage') == expected_delay,
            'prepared explicit delay FIFO policy/provenance changed')
    compilation = staged = selected = None
    if stage is not None:
        stage = Path(stage)
        integration = json.loads((stage.parents[1] / 'integration_inputs.json').read_text())
        require(integration.get('runtime_audio', {}).get('counter_cdc') == expected_counter,
                'integration native counter policy/identity changed')
        require(integration.get('runtime_audio', {}).get('chorus_source') == expected_chorus
                and chorus_metadata(stage) == expected_chorus,
                'integration/staged explicit Chorus provenance changed')
        staged_delay = verify_delay(*((stage / path).read_bytes() for path in
            (DELAY_SOURCE, DELAY_PROVENANCE)), STORAGE_POLICY, (stage / DELAY_ADAPTATION).read_bytes())[1]
        require(integration.get('runtime_audio', {}).get('delay_fifo_storage') == expected_delay
                and all(expected_delay.get(k) == v for k, v in staged_delay.items()),
                'integration/staged explicit delay FIFO provenance changed')
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
            target = ('src/push2/gw138k_push_workstation_top.v' if source.startswith('rtl/workstation/gw138k_push_workstation_top')
                      else 'legacy/rtl/audio/stereo_effects.sv' if source == 'rtl/audio/stereo_effects.sv' else source)
            require(file_sha(stage / target) == expected, 'reviewed staged composition changed: ' + target)
        verify_address_map(root, stage, prepared['recording']['address_map'])
        verify_prepared(root, stage, prepared['ble_recording_storage']['adaptation'])
    return dict(scope=SCOPE, revision=2, complete_configuration_sha256=CONFIGURATION_SHA256,
                candidate_identity=CANDIDATE, candidate_input_sha256=CANDIDATE_INPUT_SHA256,
                prepared_profile_source_sha256=prepared['profile_sha256'],
                compilation_selection=compilation, staged_input_selection=staged,
                counter_source_selection=selected, old_serial_closure_inherited=False, old_c7_closure_inherited=False, old_6b_closure_inherited=False,
                current_root_profile_bytes_equivalence_claimed=False,
                source_synthesis_identity_separate_from_review_helpers=True,
                prepared_delay_fifo_storage=expected_delay, pitch_source_sha256=PITCH_SHA256,
                raw_root_reset='reset_n', ledger_reset_is_observed_only=True,
                physical_cdc_accepted=False, full_reset_accepted=False)
