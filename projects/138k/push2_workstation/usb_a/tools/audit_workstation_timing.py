#!/usr/bin/env python3
"""Audit all routed workstation clocks and reset checks without board access."""
from pathlib import Path
import argparse
import hashlib
import json
if __package__:
    from .audit_clk50_timing import TimingTables
else:
    from audit_clk50_timing import TimingTables

TARGETS = {'clk_50m': 50.0, 'audio_76m8': 76.8, 'usb_48m': 48.0,
           'ddr_mem400': 400.0, 'ddr_ui100': 100.0, 'video_pixel148': 148.5,
           'cpu_bus50': 50.0, 'cpu_core100': 100.0}


def audit(build, *, report_path=None, targets=None):
    path = Path(report_path) if report_path is not None else build / 'Prj1/impl/pnr/Prj1_tr_content.html'
    targets = TARGETS if targets is None else targets
    text = path.read_text()
    parser = TimingTables()
    parser.feed(text)
    frequencies, checks, paths = {}, {}, {}
    global_slacks = {kind: [] for kind in ('setup', 'hold', 'recovery', 'removal')}
    pulse_width = []
    for command, rows in parser.tables:
        if not rows:
            continue
        if 'Actual Fmax' in rows[0]:
            for row in rows[1:]:
                frequencies[row[1]] = dict(required_mhz=float(row[2].split('(')[0]),
                                          actual_mhz=float(row[3].split('(')[0]))
        if rows[0] == ['Clock Name', 'Analysis Type', 'Endpoints TNS', 'Number of Endpoints']:
            for row in rows[1:]:
                checks.setdefault(row[0], {})[row[1].lower()] = dict(tns_ns=float(row[2]), endpoints=int(row[3]))
        if rows[0] == ['Number', 'Slack', 'Actual Width', 'Required Width', 'Type', 'Clock', 'Objects']:
            pulse_width.extend(dict(slack_ns=float(row[1]), clock=row[5], node=row[6])
                               for row in rows[1:] if len(row) == 7)
        if rows[0][0] != 'Path Number':
            continue
        kind = next((kind for kind in ('setup', 'hold', 'recovery', 'removal') if '-' + kind in command), None)
        if kind is None:
            continue
        for row in rows[1:]:
            if len(row) != 9:
                continue
            if '-from_clock' not in command and '-to_clock' not in command:
                global_slacks[kind].append(float(row[1]))
            record = dict(kind=kind, slack_ns=float(row[1]), source=row[2], destination=row[3],
                          source_clock=row[4], destination_clock=row[5], relation_ns=float(row[6]),
                          skew_ns=float(row[7]), data_delay_ns=float(row[8]), command=command)
            key = (kind, row[2], row[3], row[4], row[5])
            if key not in paths or paths[key]['slack_ns'] > record['slack_ns']:
                paths[key] = record
    problems = []
    for clock, target in targets.items():
        if clock not in frequencies or frequencies[clock]['required_mhz'] != target:
            problems.append('missing/changed clock requirement: ' + clock)
        elif frequencies[clock]['actual_mhz'] < target:
            problems.append('Fmax below requirement: ' + clock)
        if clock not in checks or not {'setup', 'hold'} <= checks[clock].keys():
            problems.append('missing setup/hold summary: ' + clock)
    for clock, kinds in checks.items():
        for kind, check in kinds.items():
            if check['tns_ns'] < 0 or check['endpoints']:
                problems.append('negative endpoints: ' + clock + '/' + kind)
    global_reports = {kind: 'report_timing -' + kind + ' -max_paths' in text
                      for kind in ('setup', 'hold', 'recovery', 'removal')}
    reset_reports = {kind: global_reports[kind] for kind in ('recovery', 'removal')}
    for kind, present in global_reports.items():
        if not present:
            problems.append('missing global timing check: ' + kind)
        elif not global_slacks[kind]:
            problems.append('empty global timing check: ' + kind)
    violations = sorted((p for p in paths.values() if p['slack_ns'] < 0), key=lambda p: p['slack_ns'])
    if violations:
        problems.append('negative detailed timing paths')
    pulse_violations = [path for path in pulse_width if path['slack_ns'] < 0]
    if pulse_violations:
        problems.append('negative pulse-width timing paths')
    return dict(timing_closed=not problems, problems=problems, frequencies=frequencies,
                global_worst_ns={kind: min(slacks, default=None) for kind, slacks in global_slacks.items()},
                pulse_width_worst_ns=min((path['slack_ns'] for path in pulse_width), default=None),
                pulse_width_violations=pulse_violations,
                checks=checks, global_reports=global_reports, reset_reports=reset_reports, negative_paths=violations,
                report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), hardware_tested=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('--require-closed', action='store_true')
    parser.add_argument('--output', type=Path, help='Write audit outside an immutable reference build')
    args = parser.parse_args()
    build = args.build.resolve()
    result = audit(build)
    output = args.output or build / 'workstation_timing.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('timing_closed', 'problems', 'frequencies')}, indent=2))
    if args.require_closed and not result['timing_closed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
