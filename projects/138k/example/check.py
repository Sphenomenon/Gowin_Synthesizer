"""Verify the custom-board example catalog without building or operating hardware."""

import argparse
import hashlib
import json
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent
REPOSITORY = EXAMPLES.parents[2]
MODULES = ('USB_HS', 'HDMI', 'BLUETOOTH', 'AK4493_AMP')


def repository_path(repository, relative):
    path = repository / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(repository.resolve()):
        raise ValueError('reference is outside the repository: ' + relative)
    return path


def verify_module(directory, repository=REPOSITORY):
    directory, repository = Path(directory), Path(repository)
    manifest = json.loads((directory / 'module.json').read_text())
    if manifest['schema'] != 1 or manifest['id'] != directory.name:
        raise ValueError('module identity differs from directory: ' + str(directory))
    if manifest['assembly_status'] != 'pending':
        raise ValueError('classification must not grant workstation acceptance')
    for alias, relative in manifest['source_links'].items():
        target = repository_path(repository, relative)
        link = directory / alias
        if not link.is_symlink() or Path(link.readlink()).is_absolute():
            raise ValueError('source entry must be a relative symlink: ' + str(link))
        if not target.exists() or link.resolve() != target.resolve():
            raise ValueError('source entry is missing or points elsewhere: ' + str(link))
    for relative, expected in manifest['source_sha256'].items():
        actual = hashlib.sha256(repository_path(repository, relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('catalog source changed: ' + relative)
    for relative in manifest['evidence']:
        if not repository_path(repository, relative).is_file():
            raise ValueError('evidence is missing: ' + relative)
    for candidate in manifest['reference_candidates']:
        if len(candidate['bitstream_sha256']) != 64:
            raise ValueError('invalid reference bitstream identity')
        int(candidate['bitstream_sha256'], 16)
        int(candidate['user_code'], 16)
    return dict(module=manifest['id'], assembly_status=manifest['assembly_status'],
                source_files=len(manifest['source_sha256']),
                source_links=len(manifest['source_links']),
                reference_candidates=[entry['user_code'] for entry in manifest['reference_candidates']])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', choices=MODULES)
    arguments = parser.parse_args()
    selected = (arguments.module,) if arguments.module else MODULES
    failed = False
    for name in selected:
        try:
            result = verify_module(EXAMPLES / name)
            print('PASS ' + json.dumps(result, ensure_ascii=False))
        except (OSError, ValueError, KeyError) as error:
            failed = True
            print('FAIL ' + name + ': ' + str(error))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
