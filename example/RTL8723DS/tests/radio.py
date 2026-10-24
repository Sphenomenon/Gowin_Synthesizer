"""Pin-level SDIO error cases, physical status UART, continuous BLE setting."""
from pathlib import Path
import json, subprocess, sys, time
p=Path(__file__).resolve().parents[1]
r=p/'reports'; r.mkdir(exist_ok=True)
subprocess.run([sys.executable,str(p/'prepare_adapted.py')],check=True)
core=[p/'generated/rtl'/f.name if f.name in {'bt_h5_transport.v','bt_gatt.v','bt_verilog_core.v'} else f
      for f in sorted((p/'vendor/rtl8723ds_ble/rtl').glob('*.v'))]
cases={
 'sdio':('tb_sdio_identify',['rtl/sdio_command.v','rtl/sdio_identify.v'], 'PASS: SDIO native discovery'),
 'status_uart':('tb_radio_status_uart',['rtl/radio_status_uart.v','rtl/uart_tx.v'],'PASS: 262-byte'),
 'continuous':('tb_continuous',core,'PASS: SESSION_MS=0'),
 'sdio_transfer':('tb_sdio_transfer',['rtl/sdio_command.v','rtl/sdio_transfer.v'],'PASS'),
 'wifi_mailbox':('tb_wifi_mailbox',['rtl/wifi_jtag_mailbox.v'],'PASS mailbox'),
}
results={}
for name,(top,sources,token) in cases.items():
 out=r/(name+'.vvp'); begin=time.monotonic()
 files=[p/'tests'/(top+'.v'),*[p/s if isinstance(s,str) else s for s in sources]]
 c=subprocess.run(['iverilog','-g2012','-s',top,'-o',str(out),*map(str,files)],cwd=p,text=True,capture_output=True,timeout=60)
 (r/(name+'_compile.log')).write_text(c.stdout+c.stderr)
 if c.returncode: raise SystemExit(c.stderr)
 v=subprocess.run(['vvp',str(out)],cwd=p,text=True,capture_output=True,timeout=60)
 (r/(name+'.log')).write_text(v.stdout+v.stderr)
 passed=v.returncode==0 and token in v.stdout
 results[name]={'pass':passed,'seconds':round(time.monotonic()-begin,3)}
 print(name+': '+('PASS' if passed else 'FAIL'),flush=True)
 if not passed: raise SystemExit(v.stdout+v.stderr)
(r/'radio_simulation_results.json').write_text(json.dumps(results,indent=2)+'\n')
