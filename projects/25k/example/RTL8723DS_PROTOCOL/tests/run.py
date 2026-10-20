"""Run the actual staged RTL, independent UART controller, and host codec tests."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

project = Path(__file__).resolve().parents[1]
vendor = project/'vendor/rtl8723ds_ble'
run = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
out = project/'reports'/'simulations'/run
out.mkdir(parents=True)
core = [vendor/'rtl'/name for name in ['rtl8723ds_ble.v','bt_uart.v','reset_release_sync.v']]
core += [project/'adaptations'/name for name in ['bt_hci_init.v','bt_verilog_core.v','bt_uart_fast.v','bt_acl_bridge.v']]
core += [project/'generated/rtl'/name for name in ['bt_gatt.v','bt_h5_transport.v']]
core += [project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v']
extra_parameters={}
cases = [
    ('acl_bridge','tb_acl_bridge',[project/'tests/tb_acl_bridge.sv',project/'adaptations/bt_acl_bridge.v'],project,[],'PASS: ACL 27-byte TX segmentation'),
    ('long_profile_replay', 'tb_long_profile_replay', [project/'tests/tb_long_profile_replay.sv', project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'], project, [], 'PASS: recording START/STOP'),
    ('long_recording', 'tb_protocol_recording', [project/'tests/tb_protocol_recording.sv', project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'], project, [], 'PASS: recording START/STOP'),
    ('recording', 'tb_protocol_recording', [project/'tests/tb_protocol_recording.sv', project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'], project, [], 'PASS: recording START/STOP'),
    ('compact_recording', 'tb_protocol_recording', [project/'tests/tb_protocol_recording.sv', project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'], project, [], 'PASS: recording START/STOP'),
    ('compact_gatt', 'tb_compact_gatt', [project/'tests/tb_compact_gatt.sv', *core], project, [], 'PASS: negotiated B2/B3 DATA'),
    ('direct_recording', 'tb_protocol_recording', [project/'tests/tb_protocol_recording.sv', project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'], project, [], 'PASS: recording START/STOP'),
    ('direct_gatt', 'tb_direct_gatt', [project/'tests/tb_direct_gatt.sv', *core], project, [], 'PASS: direct DATA receipts'),
    ('bulk_recording', 'tb_protocol_recording', [project/'tests/tb_protocol_recording.sv', project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'], project, [], 'PASS: recording START/STOP'),
    ('bulk_gatt_23', 'tb_compact_gatt', [project/'tests/tb_compact_gatt.sv', *core], project, [], 'PASS: negotiated B2/B3 DATA'),
    ('bulk_gatt_64', 'tb_compact_gatt', [project/'tests/tb_compact_gatt.sv', *core], project, [], 'PASS: negotiated B2/B3 DATA'),
    ('bulk_gatt_247', 'tb_compact_gatt', [project/'tests/tb_compact_gatt.sv', *core], project, [], 'PASS: negotiated B2/B3 DATA'),
    ('command', 'tb_protocol_command', [project/'tests/tb_protocol_command.sv', project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'], project, [], 'PASS: protocol HELLO'),
    ('board', 'tb_ble_bringup', [project/'tests/tb_ble_bringup.v', project/'rtl/ble_bringup_top.v', project/'rtl/usb1_passive_monitor.v', *core], project, [], 'PASS: POR'),
    ('h5', 'tb_bt_h5', [project/'tests/tb_h5_sync.sv', *core], vendor, [], 'BT_H5_PASS'),
    ('credits', 'tb_gatt_credits', [project/'tests/tb_gatt_credits.sv', *core], vendor, [], 'PASS: negotiated ACL credits'),
    ('legacy_gatt', 'tb_bt_gatt', [project/'tests/tb_gatt_legacy.sv', *core], vendor, [], 'PASS: bt_gatt'),
    ('uart_system', 'tb_bt_verilog_system', [project/'tests/tb_protocol_system.sv', *core], vendor, [], 'PASS: protocol UART8E1'),
    ('uart_write_command', 'tb_bt_verilog_system', [project/'tests/tb_protocol_system.sv', *core], vendor, ['+write_command'], 'PASS: protocol UART8E1'),
    ('uart_slow', 'tb_bt_verilog_system', [project/'tests/tb_protocol_system.sv', *core], vendor, [], 'PASS: protocol UART8E1'),
    ('bad_fast', 'tb_bt_verilog_system', [project/'tests/tb_protocol_system.sv', *core], vendor, ['+bad_fast'], 'PASS: rejected UART baud command fails closed'),
    ('wrong_rom', 'tb_bt_verilog_system', [project/'tests/tb_protocol_system.sv', *core], vendor, ['+wrong_rom'], 'PASS: pure Verilog system rejects'),
    ('bad_rand', 'tb_bt_verilog_system', [project/'tests/tb_protocol_system.sv', *core], vendor, ['+bad_rand'], 'PASS: unavailable/zero HCI LE Rand'),
    ('zero_rand', 'tb_bt_verilog_system', [project/'tests/tb_protocol_system.sv', *core], vendor, ['+zero_rand'], 'PASS: unavailable/zero HCI LE Rand'),
]
for value in (20,61,182,244):
    name='extended_recording_'+str(value)
    cases.insert(0,(name,'tb_extended_recording',[project/'tests/tb_extended_recording.sv',project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'],project,[],'PASS: recording START/STOP'))
    extra_parameters[name]=['-Ptb_extended_recording.ATT_VALUE='+str(value)]
for mtu in (23,64,185,247):
    name='extended_gatt_'+str(mtu)
    cases.insert(0,(name,'tb_extended_gatt',[project/'tests/tb_extended_gatt.sv',*core],project,[],'PASS: negotiated B2/B3 DATA'))
    extra_parameters[name]=['-Ptb_extended_gatt.ATT_MTU='+str(mtu)]
for old in (48,59):
    name='extended_replay_'+str(old)
    cases.insert(0,(name,'tb_extended_profile_replay',[project/'tests/tb_extended_profile_replay.sv',project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'],project,[],'PASS: recording START/STOP'))
    extra_parameters[name]=['-Ptb_extended_profile_replay.OLD_OPCODE='+str(old)]
for value in (20,61,182,244):
    name='lossless_recording_'+str(value)
    cases.insert(0,(name,'tb_lossless_recording',[project/'tests/tb_lossless_recording.sv',project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'],project,[],'PASS: recording START/STOP'))
    extra_parameters[name]=['-Ptb_lossless_recording.ATT_VALUE='+str(value)]
for old in (48,59,60):
    name='lossless_replay_'+str(old)
    cases.insert(0,(name,'tb_lossless_profile_replay',[project/'tests/tb_lossless_profile_replay.sv',project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'],project,[],'PASS: recording START/STOP'))
    extra_parameters[name]=['-Ptb_lossless_profile_replay.OLD_OPCODE='+str(old)]
for value in (20,61,182,244):
    name='second_recording_'+str(value)
    cases.insert(0,(name,'tb_second_recording',[project/'tests/tb_second_recording.sv',project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'],project,[],'PASS: recording START/STOP'))
    extra_parameters[name]=['-Ptb_second_recording.ATT_VALUE='+str(value)]
for old in (48,59,60,61):
    name='second_replay_'+str(old)
    cases.insert(0,(name,'tb_second_profile_replay',[project/'tests/tb_second_profile_replay.sv',project/'rtl/ble_protocol_command.v',project/'rtl/ble_recording.v'],project,[],'PASS: recording START/STOP'))
    extra_parameters[name]=['-Ptb_second_profile_replay.OLD_OPCODE='+str(old)]
inputs = sorted(set(f for _,_,files,_,_,_ in cases for f in files))
before = {str(f.relative_to(project)): hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs}
results = {'started_at': datetime.now().astimezone().isoformat(), 'source_sha256':before, 'passed':False, 'cases':{}}
try:
    for name, top, files, cwd, args, marker in cases:
        executable = out/(name+'.vvp')
        compile_run = subprocess.run(['iverilog','-g2012','-s',top,'-o',str(executable),*extra_parameters.get(name,[]),*(['-Ptb_protocol_recording.OPEN_OPCODE=59'] if name=='long_recording' else []),*(['-Ptb_protocol_recording.OPEN_OPCODE=57'] if name=='direct_recording' else []),*(['-Ptb_protocol_recording.OPEN_OPCODE=56'] if name=='bulk_recording' else []),*(['-Ptb_compact_gatt.USE_BULK=1','-Ptb_compact_gatt.ATT_MTU='+name.split('_')[-1]] if name.startswith('bulk_gatt_') else []),*(['-Ptb_protocol_recording.OPEN_OPCODE=55'] if name=='compact_recording' else []),*(['-Ptb_bt_verilog_system.RUN_FAST=0'] if name=='uart_slow' else []),*(['-Ptb_bt_verilog_system.MODEL_PATCH_BYTES=253'] if top=='tb_bt_verilog_system' and name!='uart_system' else []),*map(str,files)], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        (out/(name+'_compile.log')).write_text(compile_run.stdout)
        if compile_run.returncode:
            raise RuntimeError(name+' compile: '+compile_run.stdout)
        if name.startswith(('lossless_','second_')):
            for dump in Path('/private/tmp').glob('gw25k-lossless-block-*.hex'):dump.unlink()
        with (out/(name+'.log')).open('w') as log:
            simulation = subprocess.run(['vvp','-i',str(executable),*args], cwd=cwd, text=True, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        simulation.stdout = (out/(name+'.log')).read_text()
        passed = simulation.returncode==0 and marker in simulation.stdout and not re.search(r'FAIL:|FATAL:|ERROR:', simulation.stdout)
        results['cases'][name] = {'passed':passed,'log':str(out/(name+'.log'))}
        print(name+': '+('PASS' if passed else 'FAIL'),flush=True)
        if not passed:
            raise RuntimeError(simulation.stdout)
        if name.startswith(('lossless_','second_')):
            subprocess.run([sys.executable,str(project/'tests/audit_lossless_vectors.py'),*(['--second'] if name.startswith('second_') else []),'--output',str(out/(name+'_audit.json'))],cwd=project,check=True,timeout=30)
            dumps=out/(name+'_blocks');dumps.mkdir()
            for dump in Path('/private/tmp').glob('gw25k-lossless-block-*.hex'):
                dump.rename(dumps/dump.name)

    codec = subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_codec.py','-v'], cwd=project, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    (out/'codec.log').write_text(codec.stdout)
    results['cases']['codec']={'passed':codec.returncode==0,'log':str(out/'codec.log')}
    if codec.returncode:
        raise RuntimeError(codec.stdout)
    after={str(f.relative_to(project)):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs}
    if before!=after:
        raise RuntimeError('RTL inputs changed during regression')
    results['passed']=True
except Exception as error:
    results['error']=str(error)
finally:
    results['finished_at']=datetime.now().astimezone().isoformat()
    (out/'result.json').write_text(json.dumps(results,indent=2)+'\n')
    (project/'reports/last_simulation.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'passed':results['passed'],'report':str(out/'result.json'),'error':results.get('error')},indent=2))
raise SystemExit(0 if results['passed'] else 1)
