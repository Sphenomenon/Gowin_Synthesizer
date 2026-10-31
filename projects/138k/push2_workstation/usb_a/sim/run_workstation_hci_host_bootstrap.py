#!/usr/bin/env python3
"""Four-command HCI bootstrap and complete preceding source regressions."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
from run_workstation_hci_owner import command,sha

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[3]
RTL=ROOT/'rtl/bluetooth/hci_owner/workstation_hci_host_bootstrap.sv'
FLOW=ROOT/'rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv'
RX=ROOT/'rtl/bluetooth/hci_owner/workstation_hci_host_rx_owner.sv'
BENCH=ROOT/'sim/tb_workstation_hci_host_bootstrap.sv'
MUTANTS=(
    ('br_query_opcode_wrong', "step==0 ? 16'h1005", "step==0 ? 16'h1006"),
    ('le_shared_pool_rejected', 'response_acl_count_i==0||response_acl_length_i!=0', 'response_acl_count_i!=0&&response_acl_length_i!=0'),
    ('le_query_skipped', 'if(step==1)state<=POOL;', 'if(step==0)state<=POOL;'),
    ('sync_buffers_advertised', '8,9:command_data_o=0;', '8,9:command_data_o=1;'),
    ('transport_retirement_ignored', '(!transport_owned||command_transport_done_i)', "1'b1"),
    ('failed_status_ignored', 'else if(owner_response&&started&&response_status_i!=0)', "else if(1'b0)"),
    ('configuration_drift_ignored', 'else if(config_drift)fail(F_CONFIG);', "else if(1'b0)fail(F_CONFIG);"),
    ('deadline_ignored', 'else if(deadline)fail(F_TIMEOUT);', "else if(1'b0)fail(F_TIMEOUT);"),
    ('unexpected_response_ignored', 'else if(owner_response&&started&&!expected_response)', "else if(1'b0)"),
    ('flow_enable_skipped', 'else if(step==3)begin state<=DONE;', 'else if(step==2)begin state<=DONE;'),
    ('pool_backpressure_ignored', 'POOL: if(pool_config_ready_i)', "POOL: if(1'b1)"),
    ('activation_repeats', 'DONE:begin end', 'DONE:begin activate_host_rx_o<=1;end'),
    ('host_parameter_length_wrong', '2:command_data_o=step<2 ? 0 : step==2 ? 7 : 1;', '2:command_data_o=step<2 ? 0 : step==2 ? 6 : 1;'),
    ('timer_stops_while_waiting', "if(busy)elapsed<=elapsed+1'b1;", "if(command_valid_o)elapsed<=elapsed+1'b1;"),
    ('br_capacity_invented', 'br_acl_count_o<=response_acl_count_i;', "br_acl_count_o<=16'd1;"),
    ('other_owner_response_consumed', 'wire owner_response=response_valid_i&&response_owner_i==0;', 'wire owner_response=response_valid_i;'),
    ('command_status_accepted_as_complete', 'state==WAIT&&!response_seen&&response_is_complete_i&&response_opcode_i==command_opcode_o', 'state==WAIT&&!response_seen&&response_opcode_i==command_opcode_o'),
)


def simulate(out,name,source):
    dest=out/name;dest.mkdir();executable=dest/'bench.vvp'
    command(['iverilog','-g2012','-s','tb_workstation_hci_host_bootstrap','-o',str(executable),
             str(FLOW),str(RX),str(source),str(BENCH)],dest,dest/'compile.log')
    return command(['vvp',str(executable)],dest,dest/'simulation.log',False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
    out=a.output.resolve()if a.output else Path(tempfile.mkdtemp(prefix='gw138k-hci-bootstrap-'))
    if out==REPO or REPO in out.parents:p.error('evidence must be outside source tree')
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):p.error('evidence directory must be empty')
    prior=out/'host-rx'
    command([sys.executable,'-B',str(ROOT/'sim/run_workstation_hci_host_rx_owner.py'),'--output',str(prior)],out,out/'host-rx.log')
    old=json.loads((prior/'verification.json').read_text())
    report={'stage':'unselected_host_bootstrap_source_only','inputs':dict(old['inputs']),
            'tools':old['tools'],'prior_host_rx':{'checks':old['baseline']['checks'],'mutants':len(old['mutants'])},
            'prior_shared_owner':old['prior_shared_owner']}
    for source in(RTL,BENCH,Path(__file__).resolve()):report['inputs'][str(source.relative_to(ROOT))]=sha(source)
    command(['verilator','--lint-only','-Wall','--top-module',RTL.stem,str(RTL)],out,out/'bootstrap-lint.log')
    report['strict_lint']='passed_Wall_no_waivers'
    result=simulate(out,'baseline',RTL);match=re.search(r'PASS checks=(\d+).*',result.stdout)
    if result.returncode or not match:raise RuntimeError('bootstrap baseline failed')
    report['baseline']={'summary':match.group(),'checks':int(match[1])}
    report['mutants']={};text=RTL.read_text()
    for name,before,after in MUTANTS:
        if text.count(before)!=1:raise RuntimeError(f'{name}: mutation anchor drift')
        path=out/(name+'.sv');path.write_text(text.replace(before,after));r=simulate(out,name,path)
        if r.returncode==0 or 'FAIL 'not in r.stdout:raise RuntimeError(f'{name}: behavior mutant survived or failed without assertion')
        report['mutants'][name]={'rejected':True,'sha256':sha(path),
                                'failure':next(x for x in r.stdout.splitlines()if x.startswith('FAIL '))}
    report['invalid_parameters']={}
    for value in(0,1,1000000001):
        name=f'timeout-{value}';executable=out/(name+'.vvp')
        command(['iverilog','-g2012','-s',RTL.stem,'-P',f'{RTL.stem}.STEP_TIMEOUT_CYCLES={value}',
                 '-o',str(executable),str(RTL)],out,out/(name+'-compile.log'))
        r=command(['vvp',str(executable)],out,out/(name+'-simulation.log'),False)
        if r.returncode==0 or 'unsupported HCI bootstrap timeout'not in r.stdout:raise RuntimeError('invalid timeout accepted')
        report['invalid_parameters'][str(value)]='rejected'
    for name,identity in report['inputs'].items():
        if sha(ROOT/name)!=identity:raise RuntimeError(f'input drift during verification: {name}')
    report['outputs']={str(f.relative_to(out)):sha(f)for f in sorted(out.rglob('*'))if f.is_file()}
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'output':str(out),'baseline':report['baseline'],'mutants':len(MUTANTS),'prior_host_rx':report['prior_host_rx']}))


if __name__=='__main__':main()
