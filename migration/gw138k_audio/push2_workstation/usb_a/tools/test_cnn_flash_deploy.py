#!/usr/bin/env python3
"""Offline deploy/rollback fault tests using one completed candidate; no hardware I/O."""
import argparse,sys,types,json,tempfile,importlib,contextlib,io
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--build',type=Path,required=True)
ap.add_argument('--output',type=Path)
options=ap.parse_args()
sys.path.insert(0,str(root/'tools'))
mod=importlib.import_module('deploy_cnn_flash_boot')
build=options.build.resolve()
target_code=int(json.loads((build/'flash_bundle.json').read_text())['user_code'],16)
results=[]
# A CPU/video regression must stop before any programmer or UART command,
# even when clk50 itself is closed. Use real artifact/hash validation above.
with patch.object(sys,'argv',['deploy_cnn_flash_boot.py',str(build),'--program']), \
     patch.object(mod,'audit_clk50',return_value={'clk50_closed':True}), \
     patch.object(mod,'audit_previous_positive_clocks',return_value={'passed':False,'failed_clocks':['cpu_bus50','video_pixel148']}), \
     patch.object(mod.subprocess,'run',side_effect=AssertionError('timing rejection performed hardware IO')), \
     contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
 try:mod.main()
 except SystemExit as e:assert e.code==2
 else:raise AssertionError('CPU/video regression was not rejected')
results.append(dict(case='cpu_video_timing_gate_before_hardware_io',passed=True,commands=0,hardware_io_used=False))
for failure in (None,'uart_fallback','auto_boot_fail','stale_flash_success'):
 with tempfile.TemporaryDirectory(prefix='cnn_deploy_host_') as tmp:
  out=Path(tmp)/'record';clock=[0.];state={'code':0x85,'status':0x26020,'reloads':0,'commands':[],'rolled_back':False}
  def now():clock[0]+=.02;return clock[0]
  def sleep(s):clock[0]+=s
  class Port:
   def __init__(self,*a,**kw):self.received=0
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def reset_input_buffer(self):pass
   def readline(self):
    clock[0]+=1;self.received+=1
    bad=failure=='uart_fallback' or failure=='stale_flash_success' and self.received>2
    return b'B138 00000004 AC44B042 00000000 '+(b'00000243' if bad else b'0000013B')+b'\r\n'
  def fake_run(args,**kw):
   state['commands'].append(args)
   if '--operation_index' in args:
    op=int(args[args.index('--operation_index')+1]);text=''
    if op==0:text=f'User Code is: 0x{state["code"]:08X}\nStatus Code is: 0x{state["status"]:08X}\n'
    elif op==51:text='Flash ID is 0x0B4018'
    elif op in (54,56):
     text='Program and Verify Flash successfully'
     if op==54:
      fs=args[args.index('--fsFile')+1]
      if 'song_guide_full85' in fs:state['code']=0x85;state['status']=0x26020;state['rolled_back']=True
      else:state['code']=target_code
    elif op==66:text='Verify Flash successfully'
    elif op==24:text='SRAM Erase';state['status']=0
    elif op==1:
     text='Reprogram'
     if not state['rolled_back']:
      state['reloads']+=1;state['status']=0x26230 if failure=='auto_boot_fail' else 0x26020
     else:state['status']=0x26020
    else:raise AssertionError('unexpected programmer command '+str(args))
   elif 'upload_cnn_ddr_uart.py' in args[1]:
    assert state['rolled_back'];text='model_status=E';state['uart_recovered']=True
   elif 'capture_scope_smoke.py' in args[1]:
    assert state.get('uart_recovered');Path(args[args.index('--output')+1]).write_text('{"passed":true}\n');text='PASS'
   else:raise AssertionError('external process not stubbed '+str(args))
   return CompletedProcess(args,0,text,'')
  argv=['deploy_cnn_flash_boot.py',str(build),'--program','--allow-clk50-open','--output',str(out)]
  raised=False
  with patch.object(sys,'argv',argv),patch.dict(sys.modules,{'serial':types.SimpleNamespace(Serial=Port)}),patch.object(mod.subprocess,'run',fake_run),patch.object(mod.fcntl,'flock',lambda *a:None),patch.object(mod,'verify_debugger_identity',lambda *a:None),patch.object(mod.time,'monotonic',now),patch.object(mod.time,'sleep',sleep),contextlib.redirect_stdout(io.StringIO()):
   try:mod.main()
   except AssertionError:raised=True
  d=json.loads((out/'result.json').read_text())
  if failure:
   assert raised and not d['passed']
   assert d['rollback_bitstream_restored'] and d['rollback_uart_model_restored'] and d['rollback_workstation_smoke_passed']
   assert state['code']==0x85 and state['rolled_back']
  else:
   assert not raised and d['passed'] and len(d['boots'])==3 and state['reloads']==3
   assert not state.get('uart_recovered') and not d['uart_model_upload_used'] and not d['sram_download_used']
  results.append(dict(case=failure or 'three_flash_boots',passed=True,commands=len(state['commands']),hardware_io_used=False))
report={'passed':True,'tests':results,'build':str(build),'notes':'Programmer, serial, board inventory, lock and waits are stubbed; all unknown external commands fail closed. Actual candidate input/hash/status logic is exercised.'}
if options.output:options.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
