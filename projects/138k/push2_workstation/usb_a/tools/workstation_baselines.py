"""Reconstruct locked source baselines without historical local build trees."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import argparse
import base64
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def relative_name(value):
    if not isinstance(value, str) or not value:
        raise ValueError('baseline path must be a nonempty relative POSIX path')
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in ('.', '..') for part in path.parts):
        raise ValueError('unsafe baseline path: ' + value)
    if '\\' in value or ':' in value or path == PurePosixPath('.'):
        raise ValueError('unsafe baseline path: ' + value)
    return value


def repository_file(repository, name):
    path = repository / relative_name(name)
    if not path.resolve().is_relative_to(repository.resolve()):
        raise ValueError('baseline source escapes repository: ' + name)
    return path


def read_locked(path, digest, label, normalize_crlf=False):
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('invalid baseline SHA256: ' + label)
    if not path.is_file():
        raise ValueError(label + ' is missing or changed: ' + str(path))
    payload = path.read_bytes()
    if normalize_crlf:
        payload = payload.replace(b'\r\n', b'\n')
    if sha256(payload) != digest:
        raise ValueError(label + ' is missing or changed: ' + str(path))
    return payload


def source_bytes(repository, entry, name):
    path = repository_file(repository, entry['source'])
    encoding = entry.get('encoding', 'raw')
    if encoding not in ('raw', 'base64', 'crlf'):
        raise ValueError('unsupported baseline encoding: ' + name)
    payload = read_locked(path, entry.get('source_sha256', entry['sha256']),
                          'baseline input tree drifted: ' + name, normalize_crlf=encoding == 'crlf')
    if encoding == 'base64':
        payload = base64.b64decode(payload.rstrip(b'\n'), validate=True)
    elif encoding == 'crlf':
        endings = entry.get('crlf_lines')
        if endings is None:
            payload = payload.replace(b'\n', b'\r\n')
        else:
            lines = payload.split(b'\n')
            if (not isinstance(endings, list) or
                    any(type(line) is not int or not 1 <= line < len(lines) for line in endings) or
                    len(endings) != len(set(endings))):
                raise ValueError('invalid baseline CRLF line map: ' + name)
            selected = set(endings)
            payload = b''.join(line + (b'\r\n' if number in selected else b'\n')
                               for number, line in enumerate(lines[:-1], 1)) + lines[-1]
    if sha256(payload) != entry['sha256']:
        raise ValueError('baseline decoded input tree drifted: ' + name)
    return payload


def exclusion_reason(name):
    if name.startswith('docs/') or PurePosixPath(name).suffix.lower() in ('.md', '.log'):
        return 'historical_documentation_or_capture'
    if name in ('firmware/boot.elf', 'firmware/boot.bin'):
        return 'firmware_build_intermediate'
    return None


@dataclass(frozen=True)
class Baseline:
    repository: Path
    manifest: Path
    manifest_sha256: str
    descriptor: dict

    @property
    def inputs(self):
        return {name: entry['sha256'] for name, entry in self.descriptor['files'].items()}

    @property
    def music(self):
        return {name: digest for name, digest in self.inputs.items() if name.startswith('rtl/music/')}

    def read_bytes(self, name):
        return source_bytes(self.repository, self.descriptor['files'][relative_name(name)], name)

    def copy_file(self, name, destination):
        payload = self.read_bytes(name)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    def verify(self):
        for name in self.descriptor['files']:
            self.read_bytes(name)
        for name, entry in self.descriptor['metadata'].items():
            source_bytes(self.repository, entry, name)
        references = []
        if 'Prj1.gprj' in self.inputs:
            project = ET.fromstring(self.read_bytes('Prj1.gprj'))
            references = [relative_name(element.get('path')) for element in project.iter('File')]
            missing = sorted(set(references) - self.inputs.keys())
            if missing:
                raise ValueError('project files missing from locked baseline: ' + repr(missing))
        return len(references)

    def import_evidence(self):
        """Preserve import identity across a checked documentation-only retirement."""
        parent = self.descriptor.get('documentation_parent')
        if parent is None:
            return self.evidence()
        manifest = repository_file(self.repository, parent['manifest'])
        original = json.loads(read_locked(manifest, parent['manifest_sha256'],
                                          'baseline documentation parent'))
        removed = original['files'].keys() - self.descriptor['files'].keys()
        expected_files = {name: entry for name, entry in original['files'].items()
                          if name not in removed}
        expected_excluded = dict(original['excluded'], **{
            name: 'historical_documentation_or_capture' for name in removed})
        if (not removed or original.get('schema_version') != 1 or
                original['name'] != self.descriptor['name'] or
                original['origin'] != self.descriptor['origin'] or
                original['metadata'] != self.descriptor['metadata'] or
                any(PurePosixPath(name).suffix.lower() not in ('.md', '.log') for name in removed) or
                self.descriptor['files'] != expected_files or
                self.descriptor['excluded'] != expected_excluded):
            raise ValueError('baseline documentation retirement changed production inputs')
        return dict(name=original['name'], manifest=parent['manifest'],
                    manifest_sha256=parent['manifest_sha256'], origin=original['origin'],
                    source_files=len(original['files']), excluded_files=len(original['excluded']))

    def materialize(self, destination):
        destination = Path(destination)
        self.verify()
        destination.mkdir(parents=True, exist_ok=False)
        try:
            for name in self.descriptor['files']:
                self.copy_file(name, destination / name)
        except Exception:
            shutil.rmtree(destination)
            raise

    def copy_metadata(self, destination):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for name, entry in self.descriptor['metadata'].items():
            (destination / name).write_bytes(source_bytes(self.repository, entry, name))

    def evidence(self):
        return dict(name=self.descriptor['name'],
                    manifest=self.manifest.relative_to(self.repository).as_posix(),
                    manifest_sha256=self.manifest_sha256, origin=self.descriptor['origin'],
                    source_files=len(self.inputs), excluded_files=len(self.descriptor['excluded']))


def load_baseline(root, name):
    root = Path(root).resolve()
    repository = root.parents[3]
    directory = root / 'baselines'
    index_path = directory / 'index.json'
    if not index_path.is_file():
        raise ValueError('locked baseline index is missing: ' + str(index_path) +
                         '; restore the versioned baseline sources, not a historical results directory')
    index = json.loads(index_path.read_text())
    if index.get('schema_version') != 1 or name not in index.get('baselines', {}):
        raise ValueError('unknown locked baseline: ' + name)
    lock = index['baselines'][name]
    manifest = directory / relative_name(lock['manifest'])
    if not manifest.resolve().is_relative_to(directory.resolve()):
        raise ValueError('baseline manifest escapes baseline directory')
    descriptor = json.loads(read_locked(manifest, lock['sha256'], 'baseline manifest'))
    if descriptor.get('schema_version') != 1 or descriptor.get('name') != name:
        raise ValueError('baseline manifest identity mismatch: ' + name)
    origin = descriptor['origin']
    original = json.loads(read_locked(repository_file(repository, origin['input_manifest']),
                                     origin['input_manifest_sha256'], 'baseline origin manifest'))
    files, excluded = descriptor['files'], descriptor['excluded']
    if not files or files.keys() & excluded.keys() or files.keys() | excluded.keys() != original.keys():
        raise ValueError('baseline manifest does not partition the origin inputs: ' + name)
    for target, entry in files.items():
        relative_name(target)
        if entry['sha256'] != original[target]:
            raise ValueError('baseline differs from origin input: ' + target)
    for target, reason in excluded.items():
        relative_name(target)
        if exclusion_reason(target) != reason or reason is None:
            raise ValueError('cannot exclude a production baseline input: ' + target)
    for target in descriptor['metadata']:
        if relative_name(target) != PurePosixPath(target).name:
            raise ValueError('baseline metadata must have a plain filename: ' + target)
    baseline = Baseline(repository, manifest, lock['sha256'], descriptor)
    baseline.import_evidence()
    baseline.verify()
    return baseline


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', help='Audit one baseline; the default audits all registered baselines')
    args = parser.parse_args()
    index = json.loads((root / 'baselines/index.json').read_text())
    names = [args.baseline] if args.baseline else sorted(index['baselines'])
    result = {}
    for name in names:
        baseline = load_baseline(root, name)
        result[name] = dict(baseline.evidence(), project_references=baseline.verify())
    print(json.dumps(dict(passed=True, baselines=result), indent=2))


if __name__ == '__main__':
    main()
