"""Collect completed physical experiments without changing their manifests."""
from pathlib import Path
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(path):
    inputs = json.loads((path/'physical_inputs.json').read_text())
    for name, expected in inputs['input_sha256'].items():
        if sha(path/name) != expected:
            raise ValueError('physical input changed: '+str(path/name))
    timing = json.loads((path/'timing-audit.json').read_text())
    parent = json.loads((path/'parent_integration_inputs.json').read_text())
    report = path/'impl/pnr/custom_138k_integration.rpt.txt'
    text = report.read_text()
    resources = {}
    for name in ('Logic', 'Register', 'CLS', 'BSRAM', 'DSP'):
        match = re.search(r'^\s+'+name+r'\s+\|\s+([\d.]+)/([\d.]+)', text, re.M)
        if not match:
            raise ValueError('missing routed resource '+name)
        resources[name] = dict(used=float(match[1]), available=float(match[2]))
    gates = dict(timing=timing['timing_closed'])
    gate_errors = dict(timing=timing['problems'])
    reports = ['timing-audit.json']
    for gate, name in [('routes', 'native-routes-audit.json'), ('pll', 'pll-audit.json'),
                       ('cdc', 'common-cdc-audit.json'), ('storage', 'ble-storage-routes-audit.json')]:
        data = json.loads((path/name).read_text())
        gates[gate] = data['passed']
        gate_errors[gate] = data['errors']
        reports.append(name)
    artifacts = [path/name for name in ['physical_inputs.json', 'parent_synthesis_audit.json',
                 'parent_integration_inputs.json', 'run.tcl', 'physical.cst', 'physical.sdc',
                 'custom_138k_integration.vg', *reports]]
    artifacts += [path/('resource-checker-'+kind+'.json') for kind in ('timing', 'routes', 'pll', 'cdc')]
    base = path/'impl/pnr/custom_138k_integration'
    artifacts += [base.with_suffix(suffix) for suffix in ('.fs', '.bin', '.sdf', '.vo', '.tr', '.rpt.txt')]
    artifacts += [p for p in [path/'tool_result.json', path/'pnr-console.log'] if p.exists()]
    grouped = []
    seen = set()
    for row in timing['negative_paths']:
        # Limit reporting to distinct source/destination register families.
        key = tuple(re.sub(r'(\[[^]]+\])|(_\d+_s\d+)|(_s\d+)', '', row[k])
                    for k in ('source', 'destination'))
        if key not in seen:
            seen.add(key)
            grouped.append(row)
        if len(grouped) == 12:
            break
    return dict(identity=inputs['identity'], user_code=inputs['user_code'],
                output=path.relative_to(ROOT).as_posix(), parent_identity=inputs['parent_identity'],
                prepared_at=inputs.get('prepared_at'),
                tool_version=re.search(r'<Tool Version>:\s*(.+)', text)[1].strip(),
                execution=json.loads((path/'tool_result.json').read_text()) if (path/'tool_result.json').exists() else None,
                configuration={k: inputs[k] for k in ('device', 'place_option', 'route_option', 'replicate_resources')},
                source_identity=dict(source_policy=parent['source_policy'],
                    enabled_inputs=parent['enabled_inputs'],
                    source_snapshot_sha256=parent['source_snapshot_sha256'],
                    staged_input_sha256=parent['staged_input_sha256'],
                    native_timing_adaptations=parent['native_timing_adaptations'],
                    ble_source_snapshot_sha256=parent['bluetooth']['source_snapshot_sha256']),
                physical_resources=resources, gates=gates, gate_errors=gate_errors,
                offline_physical_passed=all(gates.values()),
                worst_ns=timing['global_worst_ns'], frequencies=timing['frequencies'],
                endpoint_summary=timing['checks'], worst_path_families=grouped,
                artifact_sha256={p.relative_to(path).as_posix(): sha(p) for p in artifacts},
                hardware_tested=False, deployment_allowed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('physical', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = dict(schema=1, date='2026-11-02', timezone='Asia/Shanghai',
                  baseline_commit='4e636f375a35b9bc8e0110e1e69f9d426c4be195',
                  branch='codex/138k-resource-optimization',
                  scope='offline_resource_candidate_timing_and_route_experiments',
                  experiments=[collect(p.resolve()) for p in args.physical],
                  collector_sha256=sha(Path(__file__)),
                  clocks_or_exceptions_relaxed=False, hardware_tested=False,
                  sram_programmed=False, flash_programmed=False, deployment_allowed=False,
                  remaining_gaps=['Any negative setup path still blocks timing closure.',
                                  'Reference CST is not current PCB/electrical acceptance.',
                                  'No hardware, USB/HDMI/audio/BLE end-to-end acceptance in this run.'],
                  rollback='Retain a27_checked and each distinct physical input manifest; '
                           'do not change accepted/full85 or existing deployment records.')
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps([{k: row[k] for k in ('user_code', 'gates', 'worst_ns')}
                      for row in result['experiments']], indent=2))


if __name__ == '__main__':
    main()
