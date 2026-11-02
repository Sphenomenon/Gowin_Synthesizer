"""Prepare/verify a locked offline task3 logical-framework source snapshot.

This is a helper of build.py. It neither selects a board profile nor invokes
synthesis, P&R, device discovery or programming.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

from .workstation_baselines import load_baseline

MANIFEST = 'rtl/workstation/task3_framework_sources.json'
TOOLS = ('build.py', 'tools/workstation_task3_framework.py', 'tools/workstation_baselines.py')
UART = 'src/control/uart_tx.v'
BASELINE = 'resource_rework_route0'
IDENTITY_PREFIX = 'task3-framework-logical-v1-'
LIMITS = dict(validation_stage='offline_logical_source_snapshot',
              full_workstation=False, board_profile_selected=False,
              physical_lcd_selected=False, pinout_verified=False, cdc_accepted=False,
              synthesis_performed=False, place_route_performed=False,
              bitstream=None, hardware_tested=False, deployment_allowed=False,
              sram_programmed=False, flash_written=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def decode(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate framework JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(payload, object_pairs_hook=unique)


def relative(value, allow_dot=False):
    if allow_dot and value == '.':
        return value
    if not isinstance(value, str) or not value or not re.fullmatch(r'[A-Za-z0-9_./-]+', value):
        raise ValueError('unsafe framework path: ' + repr(value))
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in ('.', '..') for p in path.parts):
        raise ValueError('unsafe framework path: ' + value)
    return value


def file_in(directory, name):
    name = relative(name)
    path = directory / name
    if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
        raise ValueError('framework file escapes its tree: ' + name)
    # Reject directory symlinks as well as terminal-file symlinks. The manifest
    # must name stable versioned inputs, not an alternate local source tree.
    current = path
    while current != directory:
        if current.is_symlink():
            raise ValueError('symlink in framework input: ' + name)
        current = current.parent
    if not path.is_file():
        raise ValueError('missing framework input: ' + name)
    return path


def checked_bytes(path, expected, label):
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('invalid framework SHA256: ' + label)
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError('framework input changed: ' + label)
    return data


def load_inputs(root, manifest_data=None):
    root = Path(root).resolve()
    payload = file_in(root, MANIFEST).read_bytes() if manifest_data is None else manifest_data
    plan = decode(payload)
    if type(plan.get('schema')) is not int or plan.get('schema') != 1 or plan.get('kind') != 'task3_logical_framework_sources':
        raise ValueError('unsupported task3 framework source manifest')
    if plan.get('hardware_tested') is not False or plan.get('bitstream', False) is not None:
        raise ValueError('logical framework cannot claim hardware/bitstream acceptance')
    tops = plan.get('entry_tops')
    if (not isinstance(tops, list) or not tops or
            any(not isinstance(t, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', t) for t in tops) or
            len(tops) != len(set(tops))):
        raise ValueError('invalid or duplicate framework entry tops')
    includes = plan.get('include_dirs')
    if (not isinstance(includes, list) or not includes or any(not isinstance(p, str) for p in includes) or
            len(includes) != len(set(includes))):
        raise ValueError('invalid or duplicate framework include directories')
    for name in includes:
        relative(name, allow_dot=True)
    if not isinstance(plan.get('configuration'), dict):
        raise ValueError('framework requires an explicit configuration')
    entries, inputs, baseline_evidence = [], {}, None
    ordinary, locked = plan.get('sources'), plan.get('baseline_sources')
    if not isinstance(ordinary, list) or not ordinary or not isinstance(locked, list) or len(locked) != 1:
        raise ValueError('framework requires maintained sources and exactly one locked UART member')
    for item in ordinary + locked:
        if not isinstance(item, dict) or type(item.get('compile')) is not bool:
            raise ValueError('every framework source requires an explicit compile boolean')
        name = relative(item.get('path'))
        if name in inputs:
            raise ValueError('duplicate framework source path: ' + name)
        expected = item.get('sha256')
        if item in locked:
            if (set(item) != {'path', 'baseline', 'source', 'sha256', 'compile'} or
                    item.get('baseline') != BASELINE or item.get('source') != UART or name != UART):
                raise ValueError('only the original locked UART baseline member is permitted')
            baseline = load_baseline(root, BASELINE)
            data = baseline.read_bytes(UART)
            if digest(data) != expected:
                raise ValueError('locked UART SHA256 differs from framework manifest')
            baseline_evidence = baseline.evidence()
            source = dict(kind='locked_baseline_member', baseline=BASELINE, member=UART)
        else:
            if set(item) != {'path', 'sha256', 'compile'} or not name.startswith('rtl/'):
                raise ValueError('maintained framework inputs must be explicit rtl/ files')
            data = checked_bytes(file_in(root, name), expected, name)
            source = dict(kind='maintenance_source', path=name)
        if item['compile'] and PurePosixPath(name).suffix not in ('.v', '.sv'):
            raise ValueError('non-RTL file selected for compilation: ' + name)
        inputs[name] = data
        entries.append(dict(path=name, compile=item['compile'], sha256=digest(data),
                            bytes=len(data), source=source))
    for name in includes:
        if name != '.' and not any(p.startswith(name + '/') for p in inputs):
            raise ValueError('framework include directory has no locked inputs: ' + name)
    compiled = [e['path'] for e in entries if e['compile']]
    if not compiled:
        raise ValueError('framework has no compilation inputs')
    return plan, payload, entries, inputs, baseline_evidence


def expected_artifacts(root, plan, manifest_bytes, entries, baseline):
    tool_hashes = {name: digest(file_in(root, name).read_bytes()) for name in TOOLS}
    binding = dict(schema=1, source_manifest_sha256=digest(manifest_bytes),
                   source_inputs=entries, tool_sha256=tool_hashes,
                   entry_tops=plan['entry_tops'], configuration=plan['configuration'],
                   include_dirs=plan['include_dirs'], baseline=baseline)
    fingerprint = digest(encode(binding))
    filelist = dict(working_directory='sources', entry_tops=plan['entry_tops'],
                    include_dirs=plan['include_dirs'],
                    compile=[e['path'] for e in entries if e['compile']],
                    data=[e['path'] for e in entries if not e['compile']])
    ftext = ''.join('+incdir+' + name + '\n' for name in filelist['include_dirs'])
    ftext += ''.join(name + '\n' for name in filelist['compile'])
    return binding, fingerprint, {'task3_framework_sources.json': manifest_bytes,
                                 'filelist.json': encode(filelist), 'filelist.f': ftext.encode()}


def git_evidence(root, input_names):
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    repository = Path(git('rev-parse', '--show-toplevel').decode().strip()).resolve()
    prefix = root.relative_to(repository).as_posix()
    names = [prefix + '/' + name for name in [*input_names, MANIFEST, *TOOLS]]
    patch = git('diff', '--binary', 'HEAD', '--', *names)
    return dict(commit=git('rev-parse', 'HEAD').decode().strip(),
                branch=git('branch', '--show-current').decode().strip(),
                status_porcelain=git('status', '--porcelain=v1', '--untracked-files=all').decode(),
                diff_scope='tracked selected inputs, source manifest and preparation tools versus HEAD; untracked inputs are bound by per-file hashes',
                diff_sha256=digest(patch)), patch


def verify(root, output):
    """Verify original locks, selected bytes, staged bytes and exact inventory."""
    root, output = Path(root).resolve(), Path(output).resolve()
    plan, raw, entries, inputs, baseline = load_inputs(root)
    binding, fingerprint, artifacts = expected_artifacts(root, plan, raw, entries, baseline)
    receipt = decode(file_in(output, 'task3_framework.json').read_bytes())
    if (receipt.get('schema') != 1 or receipt.get('identity') != IDENTITY_PREFIX + fingerprint[:16] or
            receipt.get('input_sha256') != fingerprint or receipt.get('input_binding') != binding):
        raise ValueError('framework receipt binding or identity changed')
    for key, value in LIMITS.items():
        if receipt.get(key) != value:
            raise ValueError('framework validation scope changed: ' + key)
    expected_stage = {}
    for name, data in inputs.items():
        staged = file_in(output, 'sources/' + name).read_bytes()
        if staged != data:
            raise ValueError('staged framework source changed: ' + name)
        expected_stage['sources/' + name] = digest(data)
    actual_names = {p.relative_to(output).as_posix() for p in (output / 'sources').rglob('*') if p.is_file() or p.is_symlink()}
    if actual_names != set(expected_stage):
        raise ValueError('framework staged source inventory changed')
    if receipt.get('staged_input_sha256') != expected_stage:
        raise ValueError('framework staged hash inventory changed')
    for name, data in artifacts.items():
        if file_in(output, name).read_bytes() != data:
            raise ValueError('framework metadata changed: ' + name)
    patch = file_in(output, 'source_git.patch').read_bytes()
    provenance = decode(file_in(output, 'source_git.json').read_bytes())
    if receipt.get('source_git') != provenance or provenance.get('diff_sha256') != digest(patch):
        raise ValueError('framework git provenance changed')
    if not re.fullmatch('[0-9a-f]{40,64}', provenance.get('commit', '')):
        raise ValueError('invalid framework source commit')
    return dict(passed=True, identity=receipt['identity'], input_sha256=fingerprint,
                source_files=len(entries), compile_files=sum(e['compile'] for e in entries),
                staged_files=len(expected_stage), validation_stage=LIMITS['validation_stage'],
                deployment_allowed=False)


def prepare(root, output):
    root, output = Path(root).resolve(), Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('framework output already exists: ' + str(output))
    plan, raw, entries, inputs, baseline = load_inputs(root)
    binding, fingerprint, artifacts = expected_artifacts(root, plan, raw, entries, baseline)
    source_git, patch = git_evidence(root, list(inputs))
    receipt = dict(schema=1, identity=IDENTITY_PREFIX + fingerprint[:16], input_sha256=fingerprint,
                   input_binding=binding, source_git=source_git,
                   staged_input_sha256={'sources/' + name: digest(data) for name, data in inputs.items()},
                   **LIMITS)
    # All locks are checked before creating the new snapshot. Never overwrite
    # another candidate, or fall back to a private build on missing inputs.
    output.mkdir(parents=True, exist_ok=False)
    for name, data in inputs.items():
        target = output / 'sources' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for name, data in artifacts.items():
        (output / name).write_bytes(data)
    (output / 'source_git.patch').write_bytes(patch)
    (output / 'source_git.json').write_bytes(encode(source_git))
    (output / 'task3_framework.json').write_bytes(encode(receipt))
    result = verify(root, output)
    return output, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', required=True, type=Path,
                        help='Verify a snapshot; create it through build.py --prepare-task3-framework')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(Path(__file__).resolve().parents[1], args.verify), indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
