"""Check this native physical candidate with the existing routed STA audit."""

from pathlib import Path
import argparse
import hashlib
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import audit_workstation_timing
from audit_clk50_timing import TimingTables
from workstation_custom_clocks import EXPECTED_HZ


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(physical):
    physical = Path(physical).resolve()
    inputs = json.loads((physical / 'physical_inputs.json').read_text())
    for name, expected in inputs['input_sha256'].items():
        if digest(physical / name) != expected:
            raise ValueError('physical experiment input drifted: ' + name)
    parent = json.loads((physical / 'parent_integration_inputs.json').read_text())
    for name in ('tools/audit_workstation_timing.py', 'tools/audit_clk50_timing.py',
                 'tools/workstation_custom_clocks.py'):
        if digest(ROOT / name) != parent['source_snapshot_sha256'][name]:
            raise ValueError('timing audit dependency drifted: ' + name)
    report = physical / 'impl/pnr/custom_138k_integration_tr_content.html'
    view = physical / 'timing-audit-view'
    target = view / 'Prj1/impl/pnr/Prj1_tr_content.html'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.exists():
        if target.resolve() != report:
            raise ValueError('physical timing audit view points to another report')
    else:
        target.symlink_to(report)
    original_targets = audit_workstation_timing.TARGETS
    try:
        audit_workstation_timing.TARGETS = {
            name: frequency / 1e6 for name, frequency in EXPECTED_HZ.items()
            if name not in ('video_ref49', 'video_serial742')}
        result = audit_workstation_timing.audit(view)
    finally:
        audit_workstation_timing.TARGETS = original_targets
    parser = TimingTables()
    parser.feed(report.read_text())
    clocks = {}
    for command, rows in parser.tables:
        if not rows or 'Period' not in rows[0] or 'Frequency(MHz)' not in rows[0]:
            continue
        for row in rows[1:]:
            if len(row) not in (9, 10):
                raise ValueError('unknown routed clock-summary format')
            offset = len(row) - 9
            clocks[row[1]] = dict(period_ns=float(row[3]), rise_ns=float(row[4 + offset]),
                                  fall_ns=float(row[5 + offset]), source=row[6 + offset],
                                  master_clock=row[7 + offset], target=row[8 + offset])
    if set(clocks) != set(EXPECTED_HZ):
        result['problems'].append('clock summary inventory differs from the native plan')
    for name, frequency in EXPECTED_HZ.items():
        if name not in clocks or abs(clocks[name]['period_ns'] - 1e9 / frequency) > 0.001:
            result['problems'].append('native clock period changed: ' + name)
    if ('video_pixel148' not in clocks or
            abs(clocks['video_pixel148']['fall_ns'] - 0.6e9 / EXPECTED_HZ['video_pixel148']) > 0.001):
        result['problems'].append('native pixel 60/40 waveform changed')
    result.update(timing_closed=not result['problems'], clock_summary=clocks,
                  identity=inputs['identity'], user_code=inputs['user_code'],
                  scope='routed STA; CDC topology, PLL control routes, electrical and hardware acceptance remain separate',
                  electrical_blocked=True, release_ready=False, deployment_allowed=False,
                  physical_inputs_sha256=digest(physical / 'physical_inputs.json'),
                  checker_sha256={str(path.relative_to(ROOT)): digest(path) for path in (
                      Path(__file__), ROOT / 'tools/audit_workstation_timing.py',
                      ROOT / 'tools/audit_clk50_timing.py', ROOT / 'tools/workstation_custom_clocks.py')})
    (physical / 'timing-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('physical', type=Path)
    args = parser.parse_args()
    result = audit(args.physical)
    print(json.dumps({name: result[name] for name in (
        'timing_closed', 'problems', 'global_worst_ns', 'frequencies')}, indent=2))
    raise SystemExit(0 if result['timing_closed'] else 1)
