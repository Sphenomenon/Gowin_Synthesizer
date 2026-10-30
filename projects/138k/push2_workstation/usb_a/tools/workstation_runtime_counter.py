"""Explicit native counter source ownership; no RTL generation or EDA."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

POLICY = 'native_balanced_gray32_v1'
LEGACY = 'src/migration/gw138k_counter_cdc.sv'
NATIVE = 'rtl/migration/workstation_runtime_counter_cdc.sv'
LEGACY_SHA256 = '1b6ff697ccd951995b7331ac483f3c7672a959a9a767465eb57d92d80f3afa8c'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metadata(root):
    return dict(policy=POLICY, source=NATIVE, source_sha256=sha(Path(root) / NATIVE),
        disabled_parent=LEGACY, disabled_parent_sha256=LEGACY_SHA256,
        implementation='five_combinational_parallel_prefix_xor_levels',
        source_gray_and_two_stage_synchronizer_unchanged=True,
        destination_clock_latency_added=0, physical_timing_verified=False,
        complete_cdc_accepted=False)


def selection_evidence(stage, integration=None):
    """Resolve the enabled owner, including old serial candidates, without fallback."""
    stage = Path(stage).resolve()
    files = ET.parse(stage / 'Prj1.gprj').getroot().find('FileList')
    entries = {name: [entry for entry in files if entry.get('path') == name] for name in (LEGACY, NATIVE)}
    def require(ok, message):
        if not ok:
            raise ValueError('runtime counter source: ' + message)
    require(len(entries[LEGACY]) == 1 and len(entries[NATIVE]) <= 1, 'ambiguous or missing source declaration')
    active = [name for name, rows in entries.items() if rows and rows[0].get('enable') == '1']
    require(len(active) == 1, 'exactly one legacy/native implementation must be enabled')
    require((stage / LEGACY).is_file() and sha(stage / LEGACY) == LEGACY_SHA256, 'locked parent bytes changed')
    prepared_consumer = integration is None
    if integration is None:
        path = stage.parents[1] / 'integration_inputs.json'
        integration = json.loads(path.read_text()) if path.is_file() else {}
    record = integration.get('runtime_audio', {}).get('counter_cdc')
    name = active[0]
    require((stage / name).is_file(), 'enabled implementation is missing: ' + name)
    actual = sha(stage / name)
    if name == NATIVE:
        expected = dict(policy=POLICY, source=NATIVE, source_sha256=actual,
            disabled_parent=LEGACY, disabled_parent_sha256=LEGACY_SHA256,
            implementation='five_combinational_parallel_prefix_xor_levels',
            source_gray_and_two_stage_synchronizer_unchanged=True,
            destination_clock_latency_added=0, physical_timing_verified=False,
            complete_cdc_accepted=False)
        require(record == expected, 'native source policy/identity changed or absent')
        binding = integration.get('replaced_compilation_inputs', {}).get(LEGACY, {})
        require(binding.get('sha256') == LEGACY_SHA256 and binding.get('replacement') == NATIVE and
                binding.get('selected_destination') == NATIVE, 'disabled parent replacement binding changed')
        require(integration.get('copied_source_destinations', {}).get(NATIVE) == NATIVE and
                integration.get('copied_sources_sha256', {}).get(NATIVE) == actual and
                NATIVE in integration.get('enabled_inputs', []) and LEGACY not in integration['enabled_inputs'],
                'compiled/copied native source binding changed')
        require(integration.get('staged_input_sha256', {}).get(NATIVE) == actual and
                integration['staged_input_sha256'].get(LEGACY) == LEGACY_SHA256,
                'staged source identity changed')
        if prepared_consumer:
            profile_path = stage.parents[1] / 'workstation_profile.json'
            require(profile_path.is_file(), 'native prepared profile identity is missing')
            profile = json.loads(profile_path.read_text())
            require(profile.get('enabled_inputs', {}).get(NATIVE, {}).get('sha256') == actual and
                    LEGACY not in profile['enabled_inputs'] and
                    profile.get('staged_input_sha256', {}).get(NATIVE) == actual and
                    profile['staged_input_sha256'].get(LEGACY) == LEGACY_SHA256,
                    'prepared profile compiled source identity changed')
        selection = 'compiled_native_balanced'
    else:
        require(record is None, 'native policy cannot select legacy serial implementation')
        selection = 'compiled_locked_serial'
    return dict(policy=POLICY if name == NATIVE else 'locked_serial_gray32_v1',
                selection=selection, source=name, sha256=actual,
                legacy_sha256=LEGACY_SHA256, physical_timing_verified=False,
                complete_cdc_accepted=False)


def selected_source(stage):
    return Path(stage).resolve() / selection_evidence(stage)['source']
