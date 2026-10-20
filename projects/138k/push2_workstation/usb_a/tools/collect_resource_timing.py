#!/usr/bin/env python3
"""Collect read-only routed timing/resource evidence into a separate report."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
from audit_clk50_timing import TimingTables
from audit_workstation_timing import audit as audit_timing
from workstation_timing_constraints import gray_write_alias_constraints

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'results/resource_rework_final_route0_20261020_041042'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(build, functional=None):
    stage = build / 'Prj1'
    inputs = json.loads((build / 'workstation_inputs.json').read_text())
    drift = [name for name, digest in inputs.items()
             if not (stage / name).is_file() or sha(stage / name) != digest]
    constraints = {name: sha(stage / name) for name in inputs
                   if name.endswith(('.sdc', '.cst'))}
    constraint_checks = {}
    for name in constraints:
        actual = (stage / name).read_bytes()
        original = (REFERENCE / 'Prj1' / name).read_bytes()
        aliases = (name == 'constraints/tang_mega_138k.sdc' and
                   actual == original + gray_write_alias_constraints().encode())
        constraint_checks[name] = dict(identical=actual == original,
                                      only_registered_gray_msb_aliases=bool(aliases))
    constraints_preserved = bool(constraint_checks) and all(
        item['identical'] or item['only_registered_gray_msb_aliases']
        for item in constraint_checks.values())
    spec = importlib.util.spec_from_file_location(
        'resource_comparison', ROOT / 'reports/resource_rework_20261020/collect_results.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resources = module.collect(build)
    timing = audit_timing(build)
    parser = TimingTables()
    parser.feed((stage / 'impl/pnr/Prj1_tr_content.html').read_text())
    global_checks, pulse_checks = {}, []
    for command, rows in parser.tables:
        if not rows:
            continue
        if rows[0][0] == 'Path Number' and '-from_clock' not in command and '-to_clock' not in command:
            for kind in ('setup', 'hold', 'recovery', 'removal'):
                if '-' + kind in command:
                    slacks = [float(row[1]) for row in rows[1:] if len(row) == 9]
                    global_checks[kind] = dict(paths=len(slacks), worst_ns=min(slacks, default=None))
        if rows[0] == ['Number', 'Slack', 'Actual Width', 'Required Width', 'Type', 'Clock', 'Objects']:
            pulse_checks.extend(dict(slack_ns=float(row[1]), clock=row[5], node=row[6])
                                for row in rows[1:] if len(row) == 7)
    clocks = {}
    for clock, checks in timing['checks'].items():
        clocks[clock] = dict(timing['frequencies'].get(clock, {}), checks=checks)
    result = dict(build=str(build.relative_to(ROOT)),
                  reference=str(REFERENCE.relative_to(ROOT)),
                  input_drift=drift, constraints_preserved=constraints_preserved,
                  constraints_sha256=constraints, constraint_checks=constraint_checks, resources=resources,
                  clocks=clocks, timing=timing, global_checks=global_checks,
                  pulse_width_worst_ns=min((p['slack_ns'] for p in pulse_checks), default=None),
                  pulse_width_violations=[p for p in pulse_checks if p['slack_ns'] < 0],
                  hardware_tested=False)
    # This is a physical audit, not functional acceptance or a release pointer.
    tool_path = build / 'tool_result.json'
    tool = json.loads(tool_path.read_text()) if tool_path.exists() else {}
    result['tool_flow_passed'] = tool.get('tool_flow_passed') is True
    bitstream = stage / 'impl/pnr/Prj1.fs'
    result['bitstream_sha256'] = sha(bitstream) if bitstream.is_file() else None
    metadata = json.loads((build / 'build_metadata.json').read_text())
    header = bitstream.open().read(1000) if bitstream.is_file() else ''
    code = re.search(r'//UserCode:\s*(0x[0-9a-fA-F]{8})', header)
    actual_code = code[1].lower() if code else None
    expected_code = str(metadata.get('user_code', '')).lower()
    identity_matches = bool(actual_code) and actual_code == expected_code
    result['bitstream_identity'] = dict(expected=expected_code, actual=actual_code,
                                        passed=identity_matches)
    result['physical_checks_passed'] = (
        result['tool_flow_passed'] and bool(result['bitstream_sha256']) and identity_matches
        and not drift and constraints_preserved and timing['timing_closed']
        and all(global_checks.get(kind, {}).get('paths', 0) > 0
                for kind in ('setup', 'hold', 'recovery', 'removal'))
        and not result['pulse_width_violations'])
    cdc_path, pll_path = build / 'workstation_cdc.json', build / 'pll_init_audit.json'
    cdc = json.loads(cdc_path.read_text()) if cdc_path.exists() else {}
    pll = json.loads(pll_path.read_text()) if pll_path.exists() else {}
    cdc_drift = [name for name, digest in cdc.get('evidence_sha256', {}).items()
                 if not (build / name).is_file() or sha(build / name) != digest]
    pll_evidence = pll.get('evidence', {})
    pll_bound = (pll_evidence.get('routed_netlist_sha256') == sha(stage / 'impl/pnr/Prj1.vo')
                 and pll_evidence.get('sdf_sha256') == sha(stage / 'impl/pnr/Prj1.sdf'))
    result['cdc'] = dict(passed=cdc.get('passed') is True and bool(cdc.get('evidence_sha256')) and not cdc_drift,
                         evidence_drift=cdc_drift, report_sha256=sha(cdc_path) if cdc_path.exists() else None)
    result['pll'] = dict(passed=pll.get('errors') == [] and pll_bound, artifacts_bound=pll_bound,
                         report_sha256=sha(pll_path) if pll_path.exists() else None)
    if functional is not None:
        proof = json.loads(functional.read_text())
        functional_bound = proof.get('build') == str(build.relative_to(ROOT)) and proof.get('passed') is True
        result['functional'] = dict(passed=functional_bound, report_sha256=sha(functional),
                                    report=str(functional.relative_to(ROOT)))
        result['offline_acceptance_passed'] = all((result['physical_checks_passed'],
            result['cdc']['passed'], result['pll']['passed'], functional_bound))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--functional', type=Path, help='Functional binding report for this exact stage')
    args = parser.parse_args()
    result = collect(args.build.resolve(), args.functional.resolve() if args.functional else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in (
        'build', 'physical_checks_passed', 'input_drift', 'constraints_preserved',
        'global_checks', 'pulse_width_worst_ns')}, indent=2))


if __name__ == '__main__':
    main()
