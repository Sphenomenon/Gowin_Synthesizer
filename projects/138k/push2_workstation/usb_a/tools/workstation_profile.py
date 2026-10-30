"""Lock one explicit native workstation source policy without promoting it.

The profile is an implementation checkpoint, not a hardware capability claim.
It reuses the existing native preparation and records its complete staged
closure. Accepted, pinned and resource-only entry points never select it.
"""

from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ElementTree

from tools.workstation_baselines import load_baseline


NAME = 'custom138k-workstation-v1'
CONFIG = 'boards/custom_138k/workstation_profile_v1.json'
ARTIFACT = 'workstation_profile.json'
AE350_POLICY = 'maintained_ae350_v1'
AE350_DIRECTORY = 'ae350_firmware'
REVISION = 5
RUNTIME_CONFIGURATION = dict(hdmi_mode='1080p60', high_speed_allowed=True,
    tf_audio_kind='wav', implemented_sample_rates_hz=[48000, 44100],
    ae350_firmware_policy=AE350_POLICY, scan_window_policy='native_admission_v1',
    audio_policy='native_dual_rate_runtime_v1', reserve_zero_epoch=True,
    display_metadata_minor=1,
    media_preparation_policy='seal_record_stop_score_tf_ble_v1')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checked_path(base, relative):
    path = (base / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(base) or not path.is_file():
        raise ValueError('workstation profile missing or escaping input: ' + relative)
    return path


def load(root, name, *, allow_high_speed=True, hdmi_mode='1080p60'):
    root = Path(root).resolve()
    repository = root.parents[3]
    if name != NAME:
        raise ValueError('unknown workstation profile: ' + str(name))
    config = checked_path(root, CONFIG)
    profile = json.loads(config.read_text())
    if (profile.get('schema') != 1 or profile.get('name') != name or
            type(profile.get('revision')) is not int or profile['revision'] != REVISION):
        raise ValueError('workstation profile identity changed')
    if (profile.get('configuration') != RUNTIME_CONFIGURATION or
            hdmi_mode != '1080p60' or allow_high_speed is not True):
        raise ValueError('workstation profile configuration mismatch')
    if not profile.get('source_sha256') or not profile.get('features') or not profile.get('references'):
        raise ValueError('incomplete workstation profile')
    for relative, expected in profile['source_sha256'].items():
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('invalid workstation source hash: ' + relative)
        if sha(checked_path(repository, relative)) != expected:
            raise ValueError('workstation profile source drift: ' + relative)
    for directory, expected in profile['source_sets'].items():
        directory_path = (repository / directory).resolve()
        if not directory_path.is_relative_to(repository) or not directory_path.is_dir():
            raise ValueError('workstation profile missing or escaping directory: ' + directory)
        selected = sorted(path.relative_to(repository).as_posix()
                          for path in directory_path.rglob('*') if path.is_file())
        if selected != expected or not set(expected).issubset(profile['source_sha256']):
            raise ValueError('workstation profile source inventory drift: ' + directory)
    baseline = load_baseline(root, profile['parent_baseline']['name'])
    if baseline.evidence() != profile['parent_baseline']:
        raise ValueError('workstation profile parent baseline changed')
    for reference in profile['references'].values():
        for relative, expected in reference['source_sha256'].items():
            if relative not in profile['source_sha256']:
                raise ValueError('workstation reference source is not locked: ' + relative)
            if len(expected) != 64:
                raise ValueError('invalid workstation reference hash: ' + relative)
    return profile


def prepare_ae350(root, output, stage, riscv_prefix=None):
    """Install maintained AE350 ROM only for the explicitly selected profile."""
    from tools.stage_ae350_firmware import stage_ae350_firmware
    root, output, stage = map(lambda path: Path(path).resolve(), (root, output, stage))
    baseline = load_baseline(root, 'resource_rework_route0')
    rom_path = 'firmware/boot.mem'
    historical = hashlib.sha256(baseline.read_bytes(rom_path)).hexdigest()
    if sha(stage / rom_path) != historical:
        raise ValueError('AE350 profile installation requires the unchanged parent ROM')
    evidence = output / AE350_DIRECTORY
    build = stage_ae350_firmware(root, evidence, riscv_prefix)
    if sha(evidence / 'boot.mem') != build['rom_sha256']:
        raise ValueError('AE350 generated ROM changed before installation')
    shutil.copyfile(evidence / 'boot.mem', stage / rom_path)
    if sha(stage / rom_path) != build['rom_sha256']:
        raise ValueError('AE350 installed ROM identity differs from the build')
    return dict(policy=AE350_POLICY, project_rom_installed=True, evidence_directory=AE350_DIRECTORY,
                installed_rom=dict(path=rom_path, sha256=build['rom_sha256'],
                                   parent_baseline_sha256=historical),
                build=build, artifacts_sha256={path.relative_to(evidence).as_posix(): sha(path)
                                               for path in sorted(evidence.rglob('*')) if path.is_file()})


def _ae350_evidence(root, output, metadata, profile):
    selected = metadata.get('ae350_firmware', {})
    if (selected.get('policy') != profile['configuration']['ae350_firmware_policy'] or
            selected.get('project_rom_installed') is not True or
            selected.get('evidence_directory') != AE350_DIRECTORY):
        raise ValueError('workstation profile AE350 firmware policy changed')
    evidence = output / AE350_DIRECTORY
    actual = {source.relative_to(evidence).as_posix() for source in evidence.rglob('*') if source.is_file()}
    if actual != set(selected['artifacts_sha256']):
        raise ValueError('workstation profile AE350 evidence inventory changed')
    for relative, expected in selected['artifacts_sha256'].items():
        if sha(checked_path(evidence, relative)) != expected:
            raise ValueError('workstation profile AE350 evidence changed: ' + relative)
    build = selected['build']
    if json.loads((evidence / 'build_metadata.json').read_text()) != build:
        raise ValueError('workstation profile AE350 build metadata changed')
    prefix = root.relative_to(root.parents[3]).as_posix() + '/'
    for relative, expected in build['input_sha256'].items():
        if profile['source_sha256'].get(prefix + relative) != expected:
            raise ValueError('workstation profile omitted or changed AE350 input: ' + relative)
    rom = selected['installed_rom']
    if (rom.get('path') != 'firmware/boot.mem' or rom.get('sha256') != build['rom_sha256'] or
            sha(checked_path(output / 'workstation/Prj1', rom['path'])) != rom['sha256'] or
            sha(evidence / 'boot.mem') != rom['sha256']):
        raise ValueError('workstation profile AE350 installed ROM changed')
    baseline = load_baseline(root, profile['parent_baseline']['name'])
    if rom['parent_baseline_sha256'] != hashlib.sha256(baseline.read_bytes(rom['path'])).hexdigest():
        raise ValueError('workstation profile AE350 historical ROM identity changed')
    return selected


def _artifact(root, output, metadata, profile):
    repository = root.parents[3]
    stage = output / 'workstation/Prj1'
    if sha(output / 'parent_prepare_metadata.json') != metadata['parent_prepare_metadata_sha256']:
        raise ValueError('workstation profile parent metadata changed')
    parent = json.loads((output / 'parent_prepare_metadata.json').read_text())
    overlays = json.loads((output / 'workstation/resource_rework_overlays.json').read_text())
    # Recompute the runtime-only BLE adaptation from its source authority.
    # Metadata cannot promote an omitted live path or erase its replacement.
    from tools.workstation_bluetooth import SDC as bluetooth_sdc
    from tools.workstation_runtime_profile import bluetooth_constraints
    bluetooth = bluetooth_constraints(bluetooth_sdc)
    if metadata.get('runtime_audio', {}).get('bluetooth_cdc_adaptation') != bluetooth['evidence']:
        raise ValueError('workstation profile runtime BLE constraint policy changed')
    staged_sdc = (stage / 'constraints/custom_138k.sdc').read_text().splitlines()
    if (any(row['constraint'] in staged_sdc for row in bluetooth['evidence']['omitted']) or
            any(staged_sdc.count(line) != 1 for line in bluetooth['sdc'].splitlines()) or
            staged_sdc.count(bluetooth['evidence']['replacement']['constraint']) != 1):
        raise ValueError('workstation profile runtime BLE constraint installation changed')
    bindings = {}
    from tools.workstation_custom_board import source_snapshot
    if source_snapshot(root, metadata['source_snapshot_extra_inputs']) != metadata['source_snapshot_sha256']:
        raise ValueError('workstation profile complete source snapshot drift')
    if metadata.get('scan_window') != dict(policy='native_admission_v1', enabled=True,
            provider='rtl/workstation/workstation_profile_hdmi.sv',
            compilation_provider='rtl/workstation/workstation_profile_runtime.sv',
            provider_selection='included_with_runtime_macro',
            implementation='rtl/workstation/workstation_hdmi_display.sv',
            admission='rtl/display_data/workstation_ddr_scan_window.sv',
            provenance_sha256=sha(stage / 'rtl/workstation/workstation_hdmi_display.provenance.json'),
            physical_deadlines_verified=False, d01_complete=False, d04_complete=False):
        raise ValueError('workstation profile scan window source policy changed')

    def bind(destination, source):
        if source not in profile['source_sha256']:
            raise ValueError('workstation profile omitted selected source: ' + source)
        previous = bindings.get(destination)
        if previous is not None and previous != source:
            raise ValueError('workstation profile ambiguous source: ' + destination)
        bindings[destination] = source

    prefix = root.relative_to(repository).as_posix() + '/'
    for source, expected in profile['source_sha256'].items():
        relative = source[len(prefix):] if source.startswith(prefix) else None
        if (relative in metadata['source_snapshot_sha256'] and
                metadata['source_snapshot_sha256'][relative] != expected):
            raise ValueError('workstation profile source snapshot drift: ' + source)
    for source, record in overlays.items():
        bind(record['destination'], prefix + source)
    for source, record in parent['composition']['sources'].items():
        bind(record['destination'], prefix + source)
    copies = metadata['copied_source_destinations']
    if set(copies) != set(metadata['copied_sources_sha256']) or len(set(copies.values())) != len(copies):
        raise ValueError('workstation profile copied source ownership changed')
    for source, target in copies.items():
        bind(target, prefix + source)
        if (metadata['copied_sources_sha256'][source] != profile['source_sha256'][prefix + source] or
                sha(checked_path(stage, target)) != metadata['copied_sources_sha256'][source]):
            raise ValueError('workstation profile copied source drift: ' + source)
    usage = {source: 'compiled_source' if target in metadata['enabled_inputs'] else 'staged_dependency'
             for target, source in bindings.items()}
    for source in metadata['firmware']['input_sha256']:
        if prefix + source not in profile['source_sha256']:
            raise ValueError('workstation profile omitted firmware source: ' + source)
        usage[prefix + source] = 'usb_firmware_build_input'
    for source in metadata['bluetooth']['source_snapshot_sha256']:
        if source not in profile['source_sha256']:
            raise ValueError('workstation profile omitted BLE source: ' + source)
        usage[source] = 'ble_build_input'
    for source in metadata['peripherals']['reviewed_sources']:
        if source not in profile['source_sha256']:
            raise ValueError('workstation profile omitted peripheral source: ' + source)

    baseline = load_baseline(root, profile['parent_baseline']['name'])
    inputs = {}
    for relative in metadata['enabled_inputs']:
        source = checked_path(stage, relative)
        expected = metadata['staged_input_sha256'].get(relative)
        if sha(source) != expected:
            raise ValueError('workstation profile prepared input drift: ' + relative)
        record = dict(sha256=expected)
        if relative in bindings:
            origin = bindings[relative]
            record.update(origin='versioned_source', source=origin,
                          source_sha256=profile['source_sha256'][origin],
                          adapted=expected != profile['source_sha256'][origin])
        elif relative in baseline.inputs:
            original = hashlib.sha256(baseline.read_bytes(relative)).hexdigest()
            record.update(origin='locked_parent_baseline', source=relative,
                          source_sha256=original, adapted=expected != original)
            equivalent = metadata['unchanged_parent_inputs'].get(relative)
            if equivalent:
                owner = prefix + equivalent['source']
                if (profile['source_sha256'].get(owner) != original or
                        equivalent['sha256'] != original or expected != original):
                    raise ValueError('workstation profile unchanged parent equivalence drift: ' + relative)
                record['versioned_equivalent'] = dict(source=owner, sha256=original)
        elif relative in metadata['bluetooth']['sources']:
            record.update(origin='checked_ble_adaptation',
                          source_sha256=metadata['bluetooth']['source_snapshot_sha256'])
        elif relative in ('constraints/custom_138k.cst', 'constraints/custom_138k.sdc'):
            record.update(origin='reviewed_board_constraint_composition',
                          source_sha256={name: value for name, value in profile['source_sha256'].items()
                                         if '/boards/custom_138k/' in name or '/tools/' in name})
        else:
            raise ValueError('workstation profile has no input provenance: ' + relative)
        inputs[relative] = record

    reuse = {}
    for name, reference in profile['references'].items():
        rows = {}
        for source, historical in reference['source_sha256'].items():
            destinations = [target for target, origin in bindings.items() if origin == source]
            rows[source] = dict(reference_sha256=historical,
                                current_sha256=profile['source_sha256'][source],
                                same_bytes_as_reference=profile['source_sha256'][source] == historical,
                                selected_destinations=destinations,
                                selection=usage.get(source, 'reference_or_preparation_input'))
        reuse[name] = dict(user_code=reference['user_code'], scope=reference['scope'],
                           evidence=reference['evidence'], files=rows)
    config_hash = sha(root / CONFIG)
    ae350 = _ae350_evidence(root, output, metadata, profile)
    bluetooth = metadata['bluetooth']
    if bluetooth.get('rom_path_policy') != 'stage_relative':
        raise ValueError('workstation runtime BLE ROM path policy changed')
    ble_inputs = bluetooth.get('generated_input_provenance', {})
    header_path, patch_path = 'native_bluetooth/patch_path.vh', 'native_bluetooth/rtl8723ds_patch.mem'
    if set(ble_inputs) != {header_path, patch_path}:
        raise ValueError('workstation runtime BLE generated input inventory changed')
    for relative, record in ble_inputs.items():
        if sha(checked_path(stage, relative)) != record['sha256']:
            raise ValueError('workstation runtime BLE generated input changed: ' + relative)
    header, patch = ble_inputs[header_path], ble_inputs[patch_path]
    if (header.get('origin') != 'checked_ble_rom_path_header' or
            header.get('generator') != 'tools/workstation_bluetooth.py' or
            header.get('generator_sha256') != profile['source_sha256'][prefix + header['generator']] or
            header.get('target') != patch_path or header.get('target_path') != patch_path or
            (stage / header_path).read_text() != '`define WORKSTATION_BLE_PATCH_FILE ' + json.dumps(patch_path) + '\n'):
        raise ValueError('workstation runtime BLE header provenance changed')
    if (patch.get('origin') != 'locked_ble_vendor_patch' or
            patch.get('source') != 'example/RTL8723DS/vendor/rtl8723ds_ble/rtl8723ds_patch.mem' or
            profile['source_sha256'].get(patch['source']) != patch.get('source_sha256') or
            patch['sha256'] != patch['source_sha256']):
        raise ValueError('workstation runtime BLE patch provenance changed')
    candidate_hash = identity_digest(dict(profile_sha256=config_hash,
                                          staged_input_sha256=metadata['staged_input_sha256'],
                                          source_snapshot_sha256=metadata['source_snapshot_sha256'],
                                          firmware=metadata['firmware'], ae350_firmware=ae350))
    return dict(schema=1, profile=NAME, revision=profile['revision'], profile_source=CONFIG, profile_sha256=config_hash,
                candidate_identity=NAME + '-' + candidate_hash[:16], candidate_input_sha256=candidate_hash,
                configuration=profile['configuration'], parent_baseline=profile['parent_baseline'],
                enabled_inputs=inputs, reference_reuse=reuse, features=profile['features'],
                staged_input_sha256=metadata['staged_input_sha256'],
                source_sha256=profile['source_sha256'],
                source_snapshot_sha256=metadata['source_snapshot_sha256'],
                selected_source_owners={target: dict(source=owner,
                    sha256=profile['source_sha256'][owner],
                    selection='compiled_source' if target in inputs else 'staged_dependency')
                    for target, owner in bindings.items()},
                firmware=metadata['firmware'],
                ae350_firmware=ae350,
                scan_window=metadata['scan_window'],
                runtime_audio=metadata.get('runtime_audio'),
                generated_data_inputs={**ble_inputs, 'firmware/boot.mem': dict(origin='maintained_ae350_firmware',
                    sha256=ae350['installed_rom']['sha256'], source_sha256=ae350['build']['input_sha256'],
                    tool_versions=ae350['build']['tool_versions'], capacity=ae350['build']['capacity'])},
                integration_metadata_sha256=identity_digest({key: value for key, value in metadata.items()
                                                             if key != 'workstation_profile'}),
                resource_overlays_sha256=sha(output / 'workstation/resource_rework_overlays.json'),
                adaptations=dict(resource_timing=parent['timing_structure'],
                                 native_timing=metadata['native_timing_adaptations'],
                                 video=metadata['hdmi'], bluetooth=metadata['bluetooth']),
                validation_stage='prepare_only', synthesis_passed=False, physical_gates_passed=False,
                hardware_tested=False, sram_programmed=False, flash_programmed=False,
                deployment_allowed=False, bitstream_sha256=None)


def attach(root, output, metadata, name):
    root, output = Path(root).resolve(), Path(output).resolve()
    profile = load(root, name, allow_high_speed=metadata['high_speed_allowed'],
                   hdmi_mode=metadata['hdmi']['mode'])
    artifact = _artifact(root, output, metadata, profile)
    destination = output / ARTIFACT
    destination.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    metadata['workstation_profile'] = dict(name=NAME, candidate_identity=artifact['candidate_identity'],
                                         configuration_sha256=artifact['profile_sha256'],
                                         artifact=ARTIFACT, artifact_sha256=sha(destination))
    return metadata['workstation_profile']


def verify(root, output):
    """Recheck source lock, compiled selection, staged closure and feature matrix."""
    root, output = Path(root).resolve(), Path(output).resolve()
    metadata = json.loads((output / 'integration_inputs.json').read_text())
    selected = metadata.get('workstation_profile', {})
    profile = load(root, selected.get('name'), allow_high_speed=metadata['high_speed_allowed'],
                   hdmi_mode=metadata['hdmi']['mode'])
    if selected.get('artifact') != ARTIFACT or selected.get('artifact_sha256') != sha(output / ARTIFACT):
        raise ValueError('workstation profile artifact changed')
    artifact = json.loads((output / ARTIFACT).read_text())
    if artifact != _artifact(root, output, metadata, profile):
        raise ValueError('workstation profile manifest changed')
    if (selected.get('configuration_sha256') != artifact['profile_sha256'] or
            selected.get('candidate_identity') != artifact['candidate_identity']):
        raise ValueError('workstation profile selection changed')
    stage = output / 'workstation/Prj1'
    enabled = [entry.get('path') for entry in ElementTree.parse(stage / 'Prj1.gprj').find('FileList')
               if entry.get('enable') == '1']
    if enabled != metadata['enabled_inputs'] or len(enabled) != len(set(enabled)):
        raise ValueError('workstation profile compilation selection changed')
    actual = {source.relative_to(stage).as_posix() for source in stage.rglob('*')
              if source.is_file() and 'impl' not in source.relative_to(stage).parts}
    if actual != set(metadata['staged_input_sha256']):
        raise ValueError('workstation profile staged file inventory changed')
    for relative, expected in metadata['staged_input_sha256'].items():
        if sha(checked_path(stage, relative)) != expected:
            raise ValueError('workstation profile staged closure changed: ' + relative)
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'verify'))
    parser.add_argument('candidate', type=Path, nargs='?')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == 'check':
        if args.candidate is not None:
            parser.error('check does not take a candidate')
        profile = load(root, NAME)
        result = dict(profile=NAME, source_files=len(profile['source_sha256']),
                      configuration_sha256=sha(root / CONFIG), validation_stage='source_lock_only')
    else:
        if args.candidate is None:
            parser.error('verify requires a prepared candidate directory')
        artifact = verify(root, args.candidate)
        result = dict(profile=NAME, candidate_identity=artifact['candidate_identity'],
                      enabled_inputs=len(artifact['enabled_inputs']), validation_stage='prepare_only')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
