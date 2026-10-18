#!/usr/bin/env python3
"""Extract routed clk50 evidence, including async-reset recovery/removal checks."""
from pathlib import Path
from html.parser import HTMLParser
import argparse
import hashlib
import json


class TimingTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = self.row = self.cell = self.heading = None
        self.command = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'h4':
            self.heading = []
        elif tag == 'table':
            self.table = []
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        if self.heading is not None:
            self.heading.append(data)

    def handle_endtag(self, tag):
        if tag == 'h4' and self.heading is not None:
            text = ''.join(self.heading)
            if 'Report Command:report_timing' in text:
                self.command = text.split('Report Command:', 1)[1]
            self.heading = None
        elif tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.table is not None:
                self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append((self.command, self.table))
            self.table = None


def audit(build):
    path = build / 'Prj1/impl/pnr/Prj1_tr_content.html'
    parser = TimingTables()
    parser.feed(path.read_text())
    result = {'build': str(build), 'report_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'same_clock_setup': [], 'same_clock_hold': [], 'to_clk50_setup': [],
              'fmax_mhz': None, 'clock_period_ns': None, 'clock_required_mhz': None, 'tns': {}}
    required = {kind: False for kind in ('setup', 'hold')}
    reset_reports = {kind: {'explicit': False, 'global': False, 'paths': [], 'global_paths': []}
                     for kind in ('recovery', 'removal')}
    for command, rows in parser.tables:
        if not rows:
            continue
        head = rows[0]
        if 'Period' in head and 'Frequency(MHz)' in head:
            for row in rows[1:]:
                if len(row) >= 5 and row[1] == 'clk_50m':
                    result['clock_period_ns'] = float(row[3])
                    # Gowin 1.9.12 HTML omits the frequency td in this table;
                    # use the physical period, not a shifted Rise/Fall column.
                    result['clock_required_mhz'] = 1000.0 / result['clock_period_ns']
        if 'Actual Fmax' in head:
            for row in rows[1:]:
                if len(row) >= 4 and row[1] == 'clk_50m':
                    result['fmax_mhz'] = float(row[3].split('(')[0])
        if head == ['Clock Name', 'Analysis Type', 'Endpoints TNS', 'Number of Endpoints']:
            for row in rows[1:]:
                if row[0] == 'clk_50m':
                    result['tns'][row[1].lower()] = {'ns': float(row[2]), 'endpoints': int(row[3])}
        if not head or head[0] != 'Path Number' or 'Path Slack' not in head:
            continue
        kind = next((k for k in ('setup', 'hold', 'recovery', 'removal')
                     if '-' + k in command), None)
        if kind is None:
            continue
        same_report = '-from_clock [get_clocks {clk_50m}] -to_clock [get_clocks {clk_50m}]' in command
        if kind in reset_reports:
            reset_reports[kind]['explicit'] |= '-to_clock [get_clocks {clk_50m}]' in command
            reset_reports[kind]['global'] |= '-from_clock' not in command and '-to_clock' not in command
        elif same_report:
            required[kind] = True
        for row in rows[1:]:
            if len(row) != 9:
                continue
            source_clock, dest_clock = row[4].split(':')[0], row[5].split(':')[0]
            data = {'slack_ns': float(row[1]), 'from': row[2], 'to': row[3],
                    'from_clock': source_clock, 'to_clock': dest_clock,
                    'relation_ns': float(row[6]), 'skew_ns': float(row[7]), 'data_delay_ns': float(row[8])}
            if kind in reset_reports:
                if dest_clock == 'clk_50m':
                    reset_reports[kind]['paths'].append(data)
                if '-from_clock' not in command and '-to_clock' not in command:
                    reset_reports[kind]['global_paths'].append(data)
            elif same_report and source_clock == dest_clock == 'clk_50m':
                result['same_clock_' + kind].append(data)
            elif kind == 'setup' and '-to_clock [get_clocks {clk_50m}]' in command and dest_clock == 'clk_50m':
                result['to_clk50_setup'].append(data)
    result['explicit_reports_present'] = required
    for kind in ('setup', 'hold'):
        paths = result['same_clock_' + kind]
        result[kind + '_wns_ns'] = min((p['slack_ns'] for p in paths), default=None)
    result['same_clock_closed'] = (all(required.values()) and
        all(result[k + '_wns_ns'] is not None and result[k + '_wns_ns'] >= 0 for k in required))
    result['clk50_endpoint_tns_closed'] = (len(result['tns']) == 2 and
        all(r['ns'] >= 0 and r['endpoints'] == 0 for r in result['tns'].values()))
    result['clock_constraint_preserved'] = (result['clock_period_ns'] == 20 and
                                             result['clock_required_mhz'] == 50)
    result['clk50_setup_hold_closed'] = (result['clock_constraint_preserved'] and
        result['same_clock_closed'] and result['clk50_endpoint_tns_closed'] and
        result['fmax_mhz'] is not None and result['fmax_mhz'] >= 50)
    result['reset_checks'] = {}
    for kind, evidence in reset_reports.items():
        paths = evidence['paths']
        global_paths = evidence['global_paths']
        # A nonnegative global worst-path report certifies all domains. When a
        # different domain fails, require an explicit to-clk50 report instead.
        global_pass = (evidence['global'] and bool(global_paths) and
                       min(p['slack_ns'] for p in global_paths) >= 0)
        explicit_pass = (evidence['explicit'] and bool(paths) and
                         min(p['slack_ns'] for p in paths) >= 0)
        known_fail = any(p['slack_ns'] < 0 for p in paths)
        result['reset_checks'][kind] = {
            'explicit_report_present': evidence['explicit'],
            'global_report_present': evidence['global'],
            'global_wns_ns': min((p['slack_ns'] for p in global_paths), default=None),
            'to_clk50_wns_ns': min((p['slack_ns'] for p in paths), default=None),
            'to_clk50_paths': paths,
            'closed': (global_pass or explicit_pass) and not known_fail,
        }
    result['clk50_reset_closed'] = all(r['closed'] for r in result['reset_checks'].values())
    result['clk50_closed'] = result['clk50_setup_hold_closed'] and result['clk50_reset_closed']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--require-closed', action='store_true')
    args = parser.parse_args()
    result = audit(args.build.resolve())
    output = args.output or args.build / 'clk50_timing_audit.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if not isinstance(v, list)}, indent=2))
    for path in result['same_clock_setup'][:8]:
        print(path['slack_ns'], path['from'], '->', path['to'])
    if args.require_closed and not result['clk50_closed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
