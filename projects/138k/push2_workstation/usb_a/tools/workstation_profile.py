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
import xml.etree.ElementTree as ElementTree

from tools.workstation_baselines import load_baseline


NAME = 'custom138k-workstation-v1'
CONFIG = 'boards/custom_138k/workstation_profile_v1.json'
ARTIFACT = 'workstation_profile.json'


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
            type(profile.get('revision')) is not int or profile['revision'] < 1):
        raise ValueError('workstation profile identity changed')
    if profile.get('configuration') != dict(hdmi_mode=hdmi_mode, high_speed_allowed=bool(allow_high_speed),
                                          tf_audio_kind='wav', implemented_sample_rates_hz=[48000]):
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


def _artifact(root, output, metadata, profile):
    repository = root.parents[3]
    stage = output / 'workstation/Prj1'
    if sha(output / 'parent_prepare_metadata.json') != metadata['parent_prepare_metadata_sha256']:
        raise ValueError('workstation profile parent metadata changed')
    parent = json.loads((output / 'parent_prepare_metadata.json').read_text())
    overlays = json.loads((output / 'workstation/resource_rework_overlays.json').read_text())
    bindings = {}

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
    for source in metadata['copied_sources_sha256']:
        bind(source, prefix + source)
    usage = {source: 'compiled_source' for source in bindings.values()}
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
    candidate_hash = identity_digest(dict(profile_sha256=config_hash,
                                          staged_input_sha256=metadata['staged_input_sha256'],
                                          firmware=metadata['firmware']))
    return dict(schema=1, profile=NAME, revision=profile['revision'], profile_source=CONFIG, profile_sha256=config_hash,
                candidate_identity=NAME + '-' + candidate_hash[:16], candidate_input_sha256=candidate_hash,
                configuration=profile['configuration'], parent_baseline=profile['parent_baseline'],
                enabled_inputs=inputs, reference_reuse=reuse, features=profile['features'],
                staged_input_sha256=metadata['staged_input_sha256'],
                source_sha256=profile['source_sha256'],
                firmware=metadata['firmware'],
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
