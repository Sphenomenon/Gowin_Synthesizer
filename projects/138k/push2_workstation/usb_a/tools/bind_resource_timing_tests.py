#!/usr/bin/env python3
"""Bind existing functional results to identical timing-candidate RTL hashes."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
T11 = ROOT / 'results/resource_timing_20261020_110314_988115'
T12 = ROOT / 'results/resource_timing_20261020_111212_369176'
REFERENCE = ROOT / 'results/resource_rework_final_route0_20261020_041042'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_maps(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'source_sha256':
                yield item
            else:
                yield from source_maps(item)
    elif isinstance(value, list):
        for item in value:
            yield from source_maps(item)


def bind(build, catalog=None):
    stage = build / 'Prj1'
    cases = [
        ('fifo_apb_services', T11 / 'timing_units/verification.json', None, T11),
        ('gain_effect_chain', T11 / 'gain_chain_ab/verification.json', None, T11),
        ('video_diagnostics', T11 / 'video_diag_timing/verification.json', None, T11),
        ('tf_dma', T12 / 'tf_dma_timing/verification.json', None, T12),
        ('pixel_numeric_mmio', ROOT / 'results/timing_equivalence_20261020_110337_366152/verification.json',
         ROOT / 'results/timing_equivalence_20261020_110337_366152/inputs_sha256.json', T11),
        ('vector_envelope', ROOT / 'results/scope_event_ab_20261020_110337_607709/verification.json',
         ROOT / 'results/scope_event_ab_20261020_110337_607709/inputs.json', T11),
    ]
    if catalog is not None:
        cases = [(item['label'], ROOT / item['report'],
                  ROOT / item['inputs'] if item.get('inputs') else None,
                  ROOT / item['tested_build']) for item in catalog['cases']]
    proofs, coverage = {}, {}
    for label, report, inputs, tested_build in cases:
        result = json.loads(report.read_text())
        hashes = json.loads(inputs.read_text()) if inputs else {
            name: digest for mapping in source_maps(result) for name, digest in mapping.items()}
        drift = [name for name, digest in hashes.items()
                 if not Path(name).is_file() or sha(Path(name)) != digest]
        matched, different = [], []
        for name, digest in hashes.items():
            path = Path(name)
            if not path.is_relative_to(tested_build / 'Prj1'):
                continue
            relative = path.relative_to(tested_build / 'Prj1').as_posix()
            target = stage / relative
            if target.is_file() and sha(target) == digest:
                matched.append(relative)
                coverage.setdefault(relative, []).append(label)
            else:
                different.append(relative)
        proofs[label] = dict(passed=result.get('passed') is True and not drift and not different,
                             report=str(report.relative_to(ROOT)), report_sha256=sha(report),
                             input_manifest_sha256=sha(inputs) if inputs else None,
                             tested_input_drift=drift, candidate_differences=different,
                             identical_candidate_inputs=sorted(matched))
    manifest = json.loads((build / 'workstation_inputs.json').read_text())
    changed_rtl = sorted(name for name in manifest if name.endswith(('.v', '.sv', '.svh'))
                         and (not (REFERENCE / 'Prj1' / name).is_file()
                              or sha(stage / name) != sha(REFERENCE / 'Prj1' / name)))
    uncovered = [name for name in changed_rtl if name not in coverage]
    # The 18-test integration run was performed with this complete T12 stage.
    # Route variants can reuse it only when every non-build input is identical.
    integration_build = ROOT / catalog['integration_build'] if catalog else T12
    source_manifest = json.loads((integration_build / 'workstation_inputs.json').read_text())
    from workstation_timing_constraints import gray_write_alias_constraints
    constraint_only_changes = []
    for name, digest in source_manifest.items():
        if name != 'constraints/tang_mega_138k.sdc' or sha(stage / name) == digest:
            continue
        actual = (stage / name).read_bytes()
        tested = (integration_build / 'Prj1' / name).read_bytes()
        alias_block = gray_write_alias_constraints().encode()
        if actual == tested + alias_block:
            constraint_only_changes.append(name)
    differences = [name for name, digest in source_manifest.items()
                   if name != 'scripts/build.tcl' and name not in constraint_only_changes
                   and '__pycache__' not in Path(name).parts
                   and (not (stage / name).is_file() or sha(stage / name) != digest)]
    integration = ROOT / catalog['integration_report'] if catalog else T12 / 'current_regression_20261020_111224_904492/verification.json'
    integration_result = json.loads(integration.read_text())
    integration_proof = dict(passed=integration_result.get('passed') is True and not differences,
                             report=str(integration.relative_to(ROOT)), report_sha256=sha(integration),
                             candidate_input_differences=differences,
                             exact_gray_msb_constraint_only_changes=constraint_only_changes,
                             tests=len(integration_result.get('tests', {})),
                             historical_tf_suite_uses_workspace_sources=True,
                             staged_tf_coverage='tf_dma')
    return dict(build=str(build.relative_to(ROOT)), cases=proofs,
                changed_rtl=changed_rtl, changed_rtl_coverage={name: coverage.get(name, []) for name in changed_rtl},
                uncovered_changed_rtl=uncovered, integration=integration_proof,
                passed=all(p['passed'] for p in proofs.values()) and not uncovered and integration_proof['passed'],
                hardware_tested=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, help='Explicit test reports, input manifests and source stages')
    args = parser.parse_args()
    result = bind(args.build.resolve(), json.loads(args.catalog.read_text()) if args.catalog else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=result['passed'], changed_rtl=len(result['changed_rtl']),
                          uncovered=result['uncovered_changed_rtl'],
                          cases={name: case['passed'] for name, case in result['cases'].items()},
                          integration=result['integration']['passed']), indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
