#!/usr/bin/env python3
"""Reproducible BSRAM accounting across builds: P&R primitive table plus the
routed-netlist primitive count per hierarchy. Read-only; writes one JSON.

Counts come from two independent places so stage mixing cannot recur:
  - Prj1/impl/pnr/Prj1.rpt.txt  (tool-reported utilization row)
  - Prj1/impl/pnr/Prj1.vo       (physical SDPB/SDPX9B instances, grouped)
  - Prj1/impl/gwsynthesis/Prj1_syn_rsc.xml (18Kb-equivalent SYN hierarchy)
"""
from pathlib import Path
import argparse
import collections
import json
import re
import xml.etree.ElementTree as ET

TOP = 'gw138k_push_workstation_top'
PRIM = re.compile(r'^\s*(SDPB|SDPX9B|SPB|SPX9B|DPB|DPX9B)\s+\\?([^\s(]+)\s*\(', re.M)
UTIL = re.compile(r'\s*BSRAM\s*\|\s*(\d+)/(\d+)\s*\|\s*\d+%')


def netlist_groups(stage, depth):
    vo = stage / 'impl/pnr/Prj1.vo'
    if not vo.exists():
        return None
    groups = collections.Counter()
    for match in PRIM.finditer(vo.read_text(errors='replace')):
        parts = match[2].lstrip('\\').split('/')
        groups['/'.join(parts[:depth])] += 1
    return dict(groups)


def pnr_utilization(stage):
    report = stage / 'impl/pnr/Prj1.rpt.txt'
    if not report.exists():
        return None
    lines = report.read_text().splitlines()
    for index, line in enumerate(lines):
        match = UTIL.fullmatch(line)
        if not match:
            continue
        breakdown = {}
        for extra in lines[index + 1:]:
            cell = re.fullmatch(r'\s*--(\S+)\s*\|\s*(\d+)\s*', extra)
            if not cell:
                break
            breakdown[cell[1]] = int(cell[2])
        return {'used': int(match[1]), 'capacity': int(match[2]), 'primitive_breakdown': breakdown}
    return None


def syn_total(stage):
    resource = stage / 'impl/gwsynthesis/Prj1_syn_rsc.xml'
    if not resource.exists():
        return None
    root = ET.parse(resource).getroot()
    if root.get('name') != TOP:
        raise ValueError('unexpected top ' + root.get('name'))
    match = re.fullmatch(r'(\d+)\((\d+)\)', root.get('T_Bsram'))
    return {'syn_bsram': int(match[1]), 'top_level': {
        child.get('name'): int(child.get('T_Bsram').split('(')[0])
        for child in root.findall('SubModule') if int(child.get('T_Bsram', '0').split('(')[0] or 0)}}


def audit(build, depth):
    stage = Path(build).resolve() / 'Prj1'
    return {
        'build': Path(build).resolve().name,
        'pnr_utilization': pnr_utilization(stage),
        'netlist_primitives': netlist_groups(stage, depth),
        'synthesis': syn_total(stage),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('builds', nargs='+', type=Path)
    parser.add_argument('--depth', type=int, default=2,
                        help='hierarchy segments kept from each primitive path (default 2)')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = [audit(build, args.depth) for build in args.builds]
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    for entry in result:
        pnr = entry['pnr_utilization'] or {}
        syn = entry['synthesis'] or {}
        nets = sum((entry['netlist_primitives'] or {}).values())
        print(f"{entry['build']}: SYN {syn.get('syn_bsram')} "
              f"P&R {pnr.get('used')}/{pnr.get('capacity')} "
              f"netlist primitives {nets}")


if __name__ == '__main__':
    main()
