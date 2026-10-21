"""Small locked-baseline fixtures shared by source-boundary tests."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write_baseline(root, name, files, excluded=None, metadata=None):
    root = Path(root)
    repository = root.parents[3]
    directory = root / 'baselines'
    directory.mkdir(parents=True, exist_ok=True)
    project = root / 'fixture_sources' / name / 'Prj1'
    entries = {}
    inputs = {}
    for target, value in dict(files, **(excluded or {})).items():
        payload = value.encode() if isinstance(value, str) else value
        path = project / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        inputs[target] = digest(payload)
        if target in files:
            entries[target] = dict(source=path.relative_to(repository).as_posix(), sha256=inputs[target])
    original = directory / (name + '.inputs.json')
    original.write_text(json.dumps(inputs, indent=2) + '\n')
    descriptor = dict(schema_version=1, name=name,
                      origin=dict(build='historical/' + name,
                                  input_manifest=original.relative_to(repository).as_posix(),
                                  input_manifest_sha256=digest(original.read_bytes())),
                      files=entries,
                      excluded={target: 'historical_documentation_or_capture' for target in excluded or {}},
                      metadata={})
    for target, payload in (metadata or {}).items():
        path = root / 'fixture_sources' / name / target
        path.write_bytes(payload)
        descriptor['metadata'][target] = dict(source=path.relative_to(repository).as_posix(), sha256=digest(payload))
    manifest = directory / (name + '.json')
    manifest.write_text(json.dumps(descriptor, indent=2) + '\n')
    index_path = directory / 'index.json'
    index = json.loads(index_path.read_text()) if index_path.exists() else dict(schema_version=1, baselines={})
    index['baselines'][name] = dict(manifest=manifest.name, sha256=digest(manifest.read_bytes()))
    index_path.write_text(json.dumps(index, indent=2) + '\n')
    return SimpleNamespace(project=project, original=original, manifest=manifest, inputs=inputs)


def rewrite_descriptor(root, name, change):
    directory = Path(root) / 'baselines'
    manifest = directory / (name + '.json')
    descriptor = json.loads(manifest.read_text())
    change(descriptor)
    manifest.write_text(json.dumps(descriptor, indent=2) + '\n')
    index_path = directory / 'index.json'
    index = json.loads(index_path.read_text())
    index['baselines'][name]['sha256'] = digest(manifest.read_bytes())
    index_path.write_text(json.dumps(index, indent=2) + '\n')
