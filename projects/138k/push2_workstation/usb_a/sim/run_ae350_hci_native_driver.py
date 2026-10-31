#!/usr/bin/env python3
"""Actual C driver/native HCI RTL co-simulation; outer H5 RAM fixture, no board."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
NAMES=['workstation_hci_native_transport.sv','workstation_hci_cpu_mailbox.sv',
 'workstation_hci_host_bootstrap.sv','workstation_hci_flow_owner.sv',
 'workstation_hci_event_decoder.sv','workstation_hci_ble_queue.sv','workstation_hci_host_rx_owner.sv']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--rtl-root',type=Path,default=ROOT,help='usb_a root containing the explicit native owner')
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);r=a.rtl_root.resolve();commands=[]
 files={r/'rtl/bluetooth/hci_owner'/n:n for n in NAMES}
 files[r/'sim/services/workstation_hci_native_cosim.sv']='workstation_hci_native_cosim.sv'
 files[ROOT/'firmware/ae350/hci_transport.c']='hci_transport.c';files[ROOT/'firmware/ae350/hci_transport.h']='hci_transport.h'
 files[ROOT/'sim/services/ae350_hci_native_driver.cpp']='ae350_hci_native_driver.cpp'
 inputs={str(f):sha(f)for f in files}
 for f,n in files.items():shutil.copyfile(f,out/n);assert sha(out/n)==inputs[str(f)]
 (out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
 def run(argv,name):
  q=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=240)
  (out/(name+'.log')).write_text(q.stdout+q.stderr);commands.append(dict(argv=list(map(str,argv)),returncode=q.returncode))
  if q.returncode:raise RuntimeError((name,q.returncode,q.stdout[-3000:],q.stderr[-3000:]))
  return q
 cc=Path(shutil.which('cc')).resolve();v=Path(shutil.which('verilator')).resolve()
 run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-c',out/'hci_transport.c','-o',out/'hci_transport.o'],'cc')
 run([v,'--cc','--exe','--build','-j','2','--top-module','workstation_hci_native_cosim','-Wno-fatal','--Mdir',out/'obj',
      '-CFLAGS','-I'+str(out),'--LDFLAGS',out/'hci_transport.o',*[out/n for n in NAMES],
      out/'workstation_hci_native_cosim.sv',out/'ae350_hci_native_driver.cpp'],'build')
 result=run([out/'obj/Vworkstation_hci_native_cosim'],'run')
 m=re.search(r'actual C/native HCI RTL: (\d+) checks passed, (\d+) clocks, maxAPBwait(\d+)',result.stdout);assert m
 report=dict(schema='ae350-hci-native-driver-v1',inputs=inputs,
   current_sources_still_match=all(sha(f)==h for f,h in inputs.items()),
   actual_C_and_native_RTL=True,checks=int(m[1]),simulation_clocks=int(m[2]),maximum_APB_wait=int(m[3]),
   commands=commands,tools={str(x):sha(x)for x in [cc,v]},
   scope='actual C MMIO driver with native bootstrap/flow/event/hostRX/private synchronous RAM; outer physical H5 RAM fixture',
   actual_UART_H5_in_this_fixture=False,actual_CPU_cycles=False,phone_interoperability=False,hardware_tested=False)
 report['outputs']={str(f.relative_to(out)):sha(f)for f in sorted(out.rglob('*'))if f.is_file()}
 (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(result.stdout.strip())
if __name__=='__main__':main()
