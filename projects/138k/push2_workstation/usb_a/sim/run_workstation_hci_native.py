#!/usr/bin/env python3
"""Native shared HCI integration, immutable RAM ABI and actual UART/H5 closure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[3]
OWNER=ROOT/'rtl/bluetooth/hci_owner'
PROTOCOL=REPO/'projects/25k/example/RTL8723DS_PROTOCOL'
VENDOR=REPO/'example/RTL8723DS/vendor/rtl8723ds_ble'
MODULES=tuple(OWNER/('workstation_hci_'+name+'.sv')for name in (
    'native_transport','flow_owner','event_decoder','host_rx_owner','host_bootstrap','cpu_mailbox','ble_queue'))
BENCH=ROOT/'sim/tb_workstation_hci_native_transport.sv'
UART=ROOT/'sim/tb_workstation_hci_native_uart.sv'
BRIDGE=OWNER/'workstation_hci_ble_bridge.v'
MUTANTS=(
    ('physical_debit_removed','native_transport',
     '.acl_send_i(tx_accept && tx_type==2)',".acl_send_i(1'b0)"),
    ('cpu_ack_before_transport','cpu_mailbox',
     'tx_state==TRANSPORT_DONE && response_done','(tx_state==ACCEPTED || tx_state==TRANSPORT_DONE) && response_done'),
    ('response_token_lost','native_transport',
     'event_command_token<=pending_origin==O_CPU ? pending_token : 0;','event_command_token<=0;'),
    ('other_owner_raw_response','native_transport',
     '((decoder_event!=8\'h0e && decoder_event!=8\'h0f) || (decoder_opcode!=0 && event_origin==O_CPU))',
     '((decoder_event!=8\'h0e && decoder_event!=8\'h0f) || 1\'b1)'),
    ('quota_only_inherits_cpu_owner','native_transport',
     '(decoder_opcode!=0 && event_origin==O_CPU)', '(event_origin==O_CPU)'),
    ('host_return_waits_ordinary_quota','flow_owner',
     '(special_command || (!command_pending_o && command_credits_o != 0))',
     '(command_credits_o != 0 && (special_command || !command_pending_o))'),
    ('stale_cpu_generation_admitted','native_transport',
     'cpu_tx_epoch==epoch && tx_generation==current_br_generation &&','cpu_tx_epoch==epoch && 1\'b1 &&'),
    ('old_copy_not_retired','cpu_mailbox','retired[at]<=1;','retired[at]<=0;'),
    ('registered_ram_byte_shift','cpu_mailbox',
     'cpu_data<=rx_ram[{head,cpu_index}];',"cpu_data<=rx_ram[{head,(cpu_index+9'd1)}];"),
    ('physical_lease_never_released','native_transport',
     'R_ACL_RELEASE:if(host_release_ready)',"R_ACL_RELEASE:if(1'b0)"),
    ('zero_le_credit_steals_private_slot','native_transport',
     '(le_shared ? br_available!=0 : le_available!=0)',"1'b1"),
)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args,cwd,log,*,allow_failure=False,timeout=240):
    result=subprocess.run(list(map(str,args)),cwd=cwd,text=True,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,timeout=timeout)
    Path(log).write_text(result.stdout)
    if result.returncode and not allow_failure:
        raise RuntimeError(f'command failed ({result.returncode}): {args}; log={log}\n'+result.stdout[-2000:])
    return result


def integration(out,name,replacement=None):
    dest=out/name;dest.mkdir()
    modules=[replacement if replacement and source.name==replacement.name else source for source in MODULES]
    command(['iverilog','-g2012','-s','tb_workstation_hci_native_transport','-o',dest/'bench.vvp',
             BENCH,*modules,BRIDGE],out,dest/'compile.log')
    return command(['vvp',dest/'bench.vvp'],out,dest/'simulation.log',allow_failure=True)


def uart(out,extra=()):
    dest=out/'uart';dest.mkdir()
    adapted=dest/'adapted'
    command([sys.executable,PROTOCOL/'prepare_adapted.py','--output',adapted],out,dest/'adapt.log')
    cpu=ROOT/'rtl/bluetooth/cpu_owner'
    sources=[UART,adapted/'bt_h5_transport.v',PROTOCOL/'adaptations/bt_uart_fast.v',
        VENDOR/'rtl/reset_release_sync.v',*[cpu/name for name in ('bt_gatt.v','ble_protocol_command.v',
        'workstation_ble_record_data_engine.sv','workstation_ble_record_data_service.sv')],
        ROOT/'rtl/services/workstation_business_mailbox.sv',ROOT/'rtl/memory/workstation_sdp.sv',
        *MODULES,BRIDGE,OWNER/'workstation_hci_initializer.v',OWNER/'workstation_hci_native_core.v']
    command(['iverilog','-g2012','-s','tb_workstation_hci_native_uart','-o',dest/'bench.vvp',*extra,*sources],
            out,dest/'compile.log')
    result=command(['vvp',dest/'bench.vvp'],VENDOR,dest/'simulation.log',timeout=480)
    if not re.search(r'PASS native UART8E1/H5 patch=253 bootstrap=4 hostreturns=\d+ notifications=\d+ reconnect=1',result.stdout):
        raise RuntimeError('native UART closure did not reach its assertions')
    return {'summary':next(x for x in result.stdout.splitlines()if x.startswith('PASS native UART')),
            'adapted_h5_sha256':sha(adapted/'bt_h5_transport.v'),'patch_bytes':253,
            'physical_uart':True,'physical_board':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--skip-uart',action='store_true',help='Targeted owner regression only; no complete source-stage claim')
    parser.add_argument('--skip-prior',action='store_true',help='Do not repeat already sealed primitive regressions')
    args=parser.parse_args()
    out=args.output.resolve()if args.output else Path(tempfile.mkdtemp(prefix='gw138k-native-hci-'))
    if out==REPO or REPO in out.parents:parser.error('evidence must be outside source tree')
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):parser.error('evidence directory must be empty')
    inputs=[*MODULES,BRIDGE,BENCH,UART,Path(__file__),OWNER/'workstation_hci_initializer.v',
            OWNER/'workstation_hci_native_core.v',OWNER/'workstation_hci_bluetooth.sv',
            OWNER/'NATIVE_TRANSPORT_CONTRACT.md',ROOT/'sim/services/workstation_hci_native_cosim.sv',
            PROTOCOL/'prepare_adapted.py',PROTOCOL/'adaptations/bt_h5_transport.v',
            PROTOCOL/'adaptations/bt_uart_fast.v',VENDOR/'rtl/reset_release_sync.v',
            VENDOR/'rtl8723ds_patch.mem',VENDOR/'firmware/rtl8723ds_fw.bin',VENDOR/'firmware/rtl8723ds_config.bin',
            *[ROOT/'rtl/bluetooth/cpu_owner'/n for n in ('bt_gatt.v','ble_protocol_command.v',
            'workstation_ble_record_data_engine.sv','workstation_ble_record_data_service.sv')],
            ROOT/'rtl/services/workstation_business_mailbox.sv',ROOT/'rtl/memory/workstation_sdp.sv']
    identities={str(path.relative_to(REPO)):sha(path)for path in inputs}
    report={'stage':'native_shared_hci_source_integration','inputs':identities,
            'synthesis':False,'pnr':False,'hardware_tested':False,'sram_programmed':False,
            'flash_programmed':False,'deployment_allowed':False}
    if not args.skip_prior:
        command([sys.executable,'-B',ROOT/'sim/run_workstation_hci_host_bootstrap.py','--output',out/'prior'],
                out,out/'prior.log')
        report['prior']=json.loads((out/'prior/verification.json').read_text())
    command(['verilator','--lint-only','-Wall','-Wno-UNUSEDSIGNAL','-Wno-PINCONNECTEMPTY',
             '--top-module','workstation_hci_native_transport',*MODULES],out,out/'native-lint.log')
    report['lint']={'passed':True,'exceptions':['unused child diagnostic outputs','explicit unused output pins'],
                    'width_latch_multidriver_timing_warnings_suppressed':False}
    result=integration(out,'baseline');match=re.search(r'PASS native integration checks=(\d+).*',result.stdout)
    if result.returncode or not match:raise RuntimeError('native integration failed: '+result.stdout)
    report['baseline']={'summary':match.group(),'checks':int(match[1])}
    report['mutants']={}
    for name,module,before,after in MUTANTS:
        source=OWNER/('workstation_hci_'+module+'.sv');data=source.read_text()
        if data.count(before)!=1:raise RuntimeError('mutation anchor drift: '+name)
        mutation=out/(name+'-source');mutation.mkdir();path=mutation/source.name;path.write_text(data.replace(before,after))
        result=integration(out,name,path)
        if not result.returncode or 'FAIL 'not in result.stdout:raise RuntimeError('behavior mutant survived: '+name)
        report['mutants'][name]={'rejected':True,'source_sha256':sha(path),
            'failure':next(line for line in result.stdout.splitlines()if 'FAIL 'in line)}
    if not args.skip_uart:report['uart']=uart(out)
    for name,identity in identities.items():
        if sha(REPO/name)!=identity:raise RuntimeError('source drift during run: '+name)
    report['outputs']={str(path.relative_to(out)):sha(path)for path in sorted(out.rglob('*'))if path.is_file()}
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'output':str(out),'checks':report['baseline']['checks'],'mutants':len(report['mutants']),
                      'uart':report.get('uart'),'hardware_tested':False}))


if __name__=='__main__':main()
