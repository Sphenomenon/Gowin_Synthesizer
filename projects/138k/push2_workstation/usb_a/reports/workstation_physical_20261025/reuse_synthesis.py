"""Reuse only this experiment's synthesis after an auditor-only correction.

This is dated evidence tooling, not a production source or deployment command.
"""

from pathlib import Path
import argparse
import ast
import hashlib
import json
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reuse(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    previous = json.loads((source / 'integration_inputs.json').read_text())
    current = json.loads((destination / 'integration_inputs.json').read_text())
    if previous['identity'] != current['identity'] or current['identity'] not in (
            'custom138k-native-integration-20261025-a18', 'custom138k-native-integration-20261025-a19',
            'custom138k-native-integration-20261025-a22', 'custom138k-native-integration-20261025-a23'):
        raise ValueError('only the unchanged dated a18/a19/a22/a23 execution profile can be reused')
    changed = {name for name in previous['source_snapshot_sha256'].keys() | current['source_snapshot_sha256'].keys()
               if previous['source_snapshot_sha256'].get(name) != current['source_snapshot_sha256'].get(name)}
    allowed = {'tools/workstation_custom_board_audit.py', 'tools/workstation_custom_timing.py',
               'tools/workstation_custom_board_implementation.py'}
    if not changed or not changed.issubset(allowed):
        raise ValueError('source change is not auditor-only: ' + repr(changed))
    if 'tools/workstation_custom_timing.py' in changed:
        name = 'tools/workstation_custom_timing.py'
        original = source / 'source_audit_snapshots/workstation_custom_timing.py'
        current_source = Path(__file__).resolve().parents[2] / name
        if digest(original) != previous['source_snapshot_sha256'][name] or digest(current_source) != current['source_snapshot_sha256'][name]:
            raise ValueError('reset-audit-only source evidence drifted')
        def execution_tree(text):
            tree = ast.parse(text)
            tree.body = [node for node in tree.body if not isinstance(node, ast.FunctionDef) or node.name != 'audit_resets']
            return ast.dump(tree, include_attributes=False)
        if execution_tree(original.read_text()) != execution_tree(current_source.read_text()):
            raise ValueError('native timing adaptation or constraints changed, not just reset auditing')
    if 'tools/workstation_custom_board_implementation.py' in changed:
        name = 'tools/workstation_custom_board_implementation.py'
        original = source / 'source_audit_snapshots/workstation_custom_board_implementation.py'
        current_source = Path(__file__).resolve().parents[2] / name
        if digest(original) != previous['source_snapshot_sha256'][name] or digest(current_source) != current['source_snapshot_sha256'][name]:
            raise ValueError('physical-option correction source evidence drifted')
        anchor = "        'set_option -use_mspi_as_gpio 1\\n'\n"
        before = original.read_text()
        if before.count(anchor) != 1 or before.replace(anchor, anchor + "        'set_option -use_cpu_as_gpio 1\\n'\n") != current_source.read_text():
            raise ValueError('physical correction is not the single validated CPU-pad ownership option')
    if previous['enabled_inputs'] != current['enabled_inputs']:
        raise ValueError('selected compilation inputs changed')
    old_stage, new_stage = source / 'workstation/Prj1', destination / 'workstation/Prj1'
    if previous['staged_input_sha256'].keys() != current['staged_input_sha256'].keys():
        raise ValueError('staged input inventory changed')
    relocated = []
    for name, expected in previous['staged_input_sha256'].items():
        old_file, new_file = old_stage / name, new_stage / name
        if digest(old_file) != expected or digest(new_file) != current['staged_input_sha256'][name]:
            raise ValueError('staged input drifted: ' + name)
        if digest(old_file) == digest(new_file):
            continue
        if name != 'native_bluetooth/patch_path.vh':
            raise ValueError('compilation support input changed: ' + name)
        old_rom, new_rom = old_stage / 'native_bluetooth/rtl8723ds_patch.mem', new_stage / 'native_bluetooth/rtl8723ds_patch.mem'
        old_directive = '`define WORKSTATION_BLE_PATCH_FILE "' + str(old_rom) + '"\n'
        new_directive = '`define WORKSTATION_BLE_PATCH_FILE "' + str(new_rom) + '"\n'
        if old_file.read_text() != old_directive or new_file.read_text() != new_directive or digest(old_rom) != digest(new_rom):
            raise ValueError('BLE ROM relocation changed content or directive')
        relocated.append(dict(source=name, old_sha256=expected, new_sha256=digest(new_file), rom_sha256=digest(new_rom)))
    if digest(old_stage / 'Prj1.gprj') != digest(new_stage / 'Prj1.gprj'):
        raise ValueError('project configuration changed')
    if (source / 'synthesis_returncode.txt').read_text().strip() != '0':
        raise ValueError('origin synthesis did not succeed')
    log = source / 'synthesis.log'
    if 'GowinSynthesis finish' not in log.read_text():
        raise ValueError('origin synthesis completion is missing')
    output = new_stage / 'impl/gwsynthesis'
    if output.exists():
        raise FileExistsError('destination synthesis outputs already exist')
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(old_stage / 'impl/gwsynthesis', output)
    shutil.copyfile(log, destination / 'synthesis.log')
    result = dict(schema=1, purpose='auditor-only correction, not new synthesis execution',
                  origin=str(source), destination=str(destination), identity=current['identity'],
                  changed_source=sorted(changed), relocated_ROM_paths=relocated,
                  origin_manifest_sha256=digest(source / 'integration_inputs.json'),
                  destination_manifest_sha256=digest(destination / 'integration_inputs.json'),
                  staged_input_count=len(current['staged_input_sha256']),
                  compilation_inputs_unchanged=True, preserved_features=True,
                  output_sha256={path.name: digest(path) for path in output.iterdir() if path.is_file()},
                  origin_log_sha256=digest(log), script_sha256=digest(Path(__file__)),
                  release_ready=False, deployment_allowed=False, hardware_tested=False)
    for name, expected in result['output_sha256'].items():
        if digest(old_stage / 'impl/gwsynthesis' / name) != expected:
            raise ValueError('synthesis output changed during copy: ' + name)
    (destination / 'synthesis_reuse.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reuse(args.source, args.destination), indent=2))
