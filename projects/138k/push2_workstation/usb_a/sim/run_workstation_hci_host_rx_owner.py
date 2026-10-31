#!/usr/bin/env python3
"""Host RX ledger/lease RTL, shared-owner regressions and behavior mutants."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from run_workstation_hci_owner import command, sha

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[3]
FLOW=ROOT/'rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv'
RX=ROOT/'rtl/bluetooth/hci_owner/workstation_hci_host_rx_owner.sv'
BENCH=ROOT/'sim/tb_workstation_hci_host_rx_owner.sv'
MUTANTS=(
    ('ble_reserve_removed', '(rx_le||free_count>BLE_RESERVE)', "1'b1"),
    ('drop_return_lost', "rx_dropped_o<=1;pending[rx_owner]<=pending[rx_owner]+1'b1;", 'rx_dropped_o<=1;pending[rx_owner]<=pending[rx_owner];'),
    ('disconnect_credit_lost', 'controller_budget_o<=controller_budget_o+outstanding[disconnect_slot];', 'controller_budget_o<=controller_budget_o;'),
    ('retired_dma_ram_reused', 'retired[index]<=1;', 'leased[index]<=0;'),
    ('retirement_identity_lost', 'retired[index]<=1;', 'retired[index]<=0;'),
    ('old_return_snapshot_not_cancelled', 'if(offered&&!(|(offer_handle^disconnect_handle_i))&&!(|(offer_generation^disconnect_generation_i)))', "if(1'b0)"),
    ('inflight_payload_overwritten', 'if(active_o&&!offered&&!return_inflight_o&&return_candidate!=-1&&', 'if(active_o&&!offered&&return_candidate!=-1&&'),
    ('lease_token_wrap_allowed', "last_lease!=32'hffffffff", "1'b1"),
    ('lease_release_identity_ignored', 'leased[at]&&!(|(tokens[at]^release_lease_i))', 'leased[at]'),
    ('return_does_not_retire_outstanding', 'outstanding[offer_slot]<=outstanding[offer_slot]-offer_count;', 'outstanding[offer_slot]<=outstanding[offer_slot];'),
    ('payload_cleared_at_accept', 'offered<=0;return_inflight_o<=1;', 'offered<=0;return_inflight_o<=1;offer_handle<=0;'),
    ('owner_drift_ignored', 'else if(owner_drift)fail(F_OWNER);', "else if(1'b0)fail(F_OWNER);"),
    ('host_command_parameter_length_wrong', '2:return_data_o=5;', '2:return_data_o=4;'),
)


def simulate(out,name,source):
    dest=out/name;dest.mkdir()
    executable=dest/'bench.vvp'
    command(['iverilog','-g2012','-s','tb_workstation_hci_host_rx_owner','-o',str(executable),
             str(FLOW),str(source),str(BENCH)],dest,dest/'compile.log')
    return command(['vvp',str(executable)],dest,dest/'simulation.log',False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
    out=a.output.resolve()if a.output else Path(tempfile.mkdtemp(prefix='gw138k-hci-host-rx-'))
    if out==REPO or REPO in out.parents:p.error('evidence must be outside source tree')
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):p.error('evidence directory must be empty')
    prior=out/'shared-owner'
    command([sys.executable,'-B',str(ROOT/'sim/run_workstation_hci_owner.py'),'--output',str(prior)],out,out/'shared-owner.log')
    old=json.loads((prior/'verification.json').read_text())
    report={'stage':'unselected_host_rx_source_only','inputs':dict(old['inputs']),'tools':old['tools'],
            'prior_shared_owner':{'flow_checks':old['baseline']['flow']['checks'],
                                  'event_checks':old['baseline']['event']['checks'],'mutants':len(old['mutants'])}}
    for source in (RX,BENCH,Path(__file__).resolve()):report['inputs'][str(source.relative_to(ROOT))]=sha(source)
    command(['verilator','--lint-only','-Wall','--top-module',RX.stem,str(RX)],out,out/'host-rx-lint.log')
    report['strict_lint']='passed_Wall_no_waivers'
    r=simulate(out,'baseline',RX);match=re.search(r'PASS checks=(\d+).*',r.stdout)
    if r.returncode or not match:raise RuntimeError('host RX baseline failed')
    report['baseline']={'summary':match.group(),'checks':int(match[1])}
    report['mutants']={}
    text=RX.read_text()
    for name,before,after in MUTANTS:
        if text.count(before)!=1:raise RuntimeError(f'{name}: mutation anchor drift')
        mutated=out/(name+'.sv');mutated.write_text(text.replace(before,after))
        r=simulate(out,name,mutated)
        if r.returncode==0 or 'FAIL 'not in r.stdout:raise RuntimeError(f'{name}: mutant survived or failed without assertion')
        report['mutants'][name]={'rejected':True,'sha256':sha(mutated),
            'failure':next(x for x in r.stdout.splitlines()if x.startswith('FAIL '))}
    report['invalid_parameters']={}
    for key,value in (('HANDLE_SLOTS',0),('HANDLE_SLOTS',17),('RX_SLOTS',1),('RX_SLOTS',17),
                      ('BLE_RESERVE',0),('BLE_RESERVE',4),('HOST_DATA_LIMIT',3),('HOST_DATA_LIMIT',277)):
        name=f'{key}-{value}';executable=out/(name+'.vvp')
        command(['iverilog','-g2012','-s',RX.stem,'-P',f'{RX.stem}.{key}={value}','-o',str(executable),str(RX)],out,out/(name+'-compile.log'))
        r=command(['vvp',str(executable)],out,out/(name+'-simulation.log'),False)
        if r.returncode==0 or 'unsupported host RX owner parameter'not in r.stdout:raise RuntimeError(f'{name}: accepted bad parameter')
        report['invalid_parameters'][name]='rejected'
    for name,identity in report['inputs'].items():
        if sha(ROOT/name)!=identity:raise RuntimeError(f'input drift during verification: {name}')
    report['outputs']={str(f.relative_to(out)):sha(f)for f in sorted(out.rglob('*'))if f.is_file()}
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'output':str(out),'baseline':report['baseline'],'mutants':len(MUTANTS),'invalid_parameters':len(report['invalid_parameters'])}))


if __name__=='__main__':main()
