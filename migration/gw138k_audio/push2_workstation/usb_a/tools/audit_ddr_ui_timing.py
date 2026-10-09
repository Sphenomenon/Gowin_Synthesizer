#!/usr/bin/env python3
"""Check actual routed DDR UI paths; Fmax alone omits constrained CE paths."""
import argparse,hashlib,json
from pathlib import Path
from audit_clk50_timing import TimingTables

def audit(build):
    path=build/'Prj1/impl/pnr/Prj1_tr_content.html'
    parser=TimingTables();parser.feed(path.read_text())
    reports={kind:[] for kind in ('setup','hold')}
    for command,rows in parser.tables:
        if not rows or rows[0][0]!='Path Number':continue
        if '-from_clock [get_clocks {ddr_ui100}] -to_clock [get_clocks {ddr_ui100}]' not in command:continue
        kind=next((k for k in reports if '-'+k in command),None)
        if kind is None:continue
        for row in rows[1:]:
            if len(row)==9 and row[4].split(':')[0]==row[5].split(':')[0]=='ddr_ui100':
                reports[kind].append(dict(slack_ns=float(row[1]),source=row[2],destination=row[3],constraint_relation_ns=float(row[6]),data_delay_ns=float(row[8])))
    result=dict(passed=False,scope='explicit same-clock DDR UI setup and hold reports; not wholeboard STA closure',report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),checks={})
    for kind,paths in reports.items():
        result['checks'][kind]=dict(explicit_report_available=bool(paths),reported_paths=len(paths),wns_ns=min((p['slack_ns'] for p in paths),default=None),negative_paths=sum(p['slack_ns']<0 for p in paths),worst_paths=sorted(paths,key=lambda p:p['slack_ns'])[:5])
    setup=reports['setup']
    original=[path for path in setup if abs(path['constraint_relation_ns']-10.0)<1e-6]
    tighter=[path for path in setup if path['constraint_relation_ns']<10.0-1e-6]
    result['setup_constraint_groups']=dict(
        original_10ns_clock=dict(reported_paths=len(original),wns_ns=min((path['slack_ns']for path in original),default=None),negative_paths=sum(path['slack_ns']<0 for path in original)),
        stricter_physical_budget=dict(reported_paths=len(tighter),wns_ns=min((path['slack_ns']for path in tighter),default=None),negative_paths=sum(path['slack_ns']<0 for path in tighter)))
    # Both groups remain mandatory; presentation does not waive tighter paths.
    result['passed']=all(c['explicit_report_available'] and c['wns_ns']>=0 for c in result['checks'].values())
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);p.add_argument('--output',type=Path);p.add_argument('--require-closed',action='store_true');a=p.parse_args()
    result=audit(a.build.resolve())
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if a.require_closed and not result['passed']:raise SystemExit(1)
