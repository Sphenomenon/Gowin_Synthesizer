from pathlib import Path
from datetime import datetime
import hashlib,json,subprocess,shutil,os
B=Path(__file__).resolve().parents[1];P=B/'results/workstation_20260911_163432_689986/Prj1';O=B/'results'/datetime.now().strftime('link_probe_%Y%m%d_%H%M%S_%f');O.mkdir()
files=[B/'probe/push_link_probe.sv',B/'rtl/push2_hspi_link.sv',B/'integration/gw138k_push_performance_uart.sv']+[B/'rtl'/n for n in ['push_hspi_phy.sv','push2_host_gate.sv']]+[next(P.rglob(n)) for n in ['reset_release.v','uart_rx.sv','uart_tx.v','gw138k_stream_cdc.sv']]
for f in files:shutil.copy2(f,O/f.name)
cst=(B/'integration/push.cst').read_text()
for name,pin in [('clk_50m','V22'),('button1_n','AB13'),('pc_uart_rx_i','V14'),('debug_uart_tx','U15')]:
 cst+=f'\nIO_LOC "{name}" {pin};\nIO_PORT "{name}" IO_TYPE=LVCMOS33 PULL_MODE=UP;\n'
(O/'probe.cst').write_text(cst)
sdc='create_clock -name clk_50m -period 20.000 -waveform {0.000 10.000} [get_ports {clk_50m}]\n'
sdc+='set_false_path -from [get_ports {button1_n}]\nset_false_path -to [get_pins {gate/rx/rx_sync_0*/D}]\nset_false_path -to [get_ports {debug_uart_tx}]\n'
sdc+='\n'.join(x.replace('u_push/link/','link/').replace('u_push/midi/*','') for x in (B/'integration/push.sdc').read_text().splitlines() if 'u_usb_host/' not in x and 'u_push/events' not in x and 'u_push/event_release' not in x and 'u_push/feedback' not in x)
# Probe telemetry clocks are identical; all its snapshots are synchronous.
(O/'probe.sdc').write_text(sdc+'\n')
entries='\n'.join(f'<File path="{f.name}" type="file.verilog" enable="1"/>' for f in files)
(O/'probe.gprj').write_text('<?xml version="1.0" encoding="UTF-8"?><Project><Template>FPGA</Template><Version>5</Version><Device name="GW5AST-138C" pn="GW5AST-LV138PG484AC2/I1">gw5ast138c-006</Device><FileList>'+entries+'<File path="probe.cst" type="file.cst" enable="1"/><File path="probe.sdc" type="file.sdc" enable="1"/></FileList></Project>')
(O/'build.tcl').write_text('''open_project probe.gprj
set_option -top_module push_link_probe
set_option -output_base_name probe
set_option -verilog_std sysv2017
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -timing_driven 1
set_option -correct_hold_violation 1
set_option -gen_text_timing_rpt 1
set_option -gen_sdf 1
set_option -gen_verilog_sim_netlist 1
run all
''')
previous=os.environ.get('PUSH_PROBE_REUSE_SYNTHESIS')
if previous:
 previous=Path(previous).resolve()
 for f in files:
  assert (previous/f.name).read_bytes()==(O/f.name).read_bytes(),'Changed RTL cannot reuse synthesis'
 shutil.copytree(previous/'impl/gwsynthesis',O/'impl/gwsynthesis')
 t=O/'build.tcl';t.write_text(t.read_text().replace('run all','run pnr'))
hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in O.iterdir() if f.is_file()};print(O,flush=True)
with (O/'gowin.log').open('w') as log:r=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'build.tcl'],cwd=O,stdout=log,stderr=subprocess.STDOUT)
(O/'build.json').write_text(json.dumps(dict(exit_code=r.returncode,inputs=hashes,hardware_tested=False),indent=2));print('exit',r.returncode)
