#!/usr/bin/env python3
"""Extract routed clk50 evidence; require explicit setup/hold path reports."""
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
              'fmax_mhz': None, 'tns': {}}
    required = {kind: False for kind in ('setup', 'hold')}
    for command, rows in parser.tables:
        if not rows:
            continue
        head = rows[0]
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
        kind = 'setup' if '-setup' in command else 'hold' if '-hold' in command else None
        if kind is None:
            continue
        same_report = '-from_clock [get_clocks {clk_50m}] -to_clock [get_clocks {clk_50m}]' in command
        if same_report:
            required[kind] = True
        for row in rows[1:]:
            if len(row) != 9:
                continue
            source_clock, dest_clock = row[4].split(':')[0], row[5].split(':')[0]
            data = {'slack_ns': float(row[1]), 'from': row[2], 'to': row[3],
                    'from_clock': source_clock, 'to_clock': dest_clock,
                    'relation_ns': float(row[6]), 'skew_ns': float(row[7]), 'data_delay_ns': float(row[8])}
            if same_report and source_clock == dest_clock == 'clk_50m':
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
    result['clk50_closed'] = (result['same_clock_closed'] and result['clk50_endpoint_tns_closed'] and
                             result['fmax_mhz'] is not None and result['fmax_mhz'] >= 50)
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
