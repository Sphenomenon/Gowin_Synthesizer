#!/usr/bin/env python3
"""Validate the actual Gowin PLLA model and the unmodified PLL_INIT helper."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import tempfile

clock_dir = Path(__file__).resolve().parents[1]
ide = Path(os.environ.get('GW25K_IDE_DIR',
           '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE'))
sources = [clock_dir/'sim/tb_usb1_clock.v', clock_dir/'usb1_clock_60m.v',
           clock_dir/'pll_init.v', ide/'simlib/gw5a/prim_sim.v']
with tempfile.TemporaryDirectory(prefix='gw25k-clock-', dir='/private/tmp') as tmp:
    executable = Path(tmp)/'clock.vvp'
    compile_result = subprocess.run(
        ['iverilog', '-g2012', '-s', 'tb_usb1_clock', '-o', str(executable),
         *map(str, sources)], text=True, capture_output=True)
    run_result = (subprocess.run(['vvp', str(executable)], text=True,
                                capture_output=True, timeout=90)
                  if compile_result.returncode == 0 else None)
report = {
    'timestamp': datetime.datetime.now().astimezone().isoformat(),
    'passed': compile_result.returncode == 0 and run_result is not None
              and run_result.returncode == 0
              and 'PASS usb1_clock_60m' in run_result.stdout,
    'simulator': 'Icarus Verilog, official GW5A PLLA functional model',
    'pll_init_sim_macro': False,
    'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sources},
    'compile_returncode': compile_result.returncode,
    'compile_stderr': compile_result.stderr,
    'simulation_returncode': run_result.returncode if run_result else None,
    'simulation_stdout': run_result.stdout if run_result else '',
    'simulation_stderr': run_result.stderr if run_result else '',
    'limits': [
        'The functional PLL model does not model the analogue mDRP calibration effects.',
        'The nominal 60 MHz waveform is quantized to the model time precision.',
        'Physical timing closure and USB enumeration require the root build and board test.'
    ]
}
(clock_dir/'simulation_report.json').write_text(json.dumps(report, indent=2)+'\n')
print(report['simulation_stdout'], end='')
print('Report: '+str(clock_dir/'simulation_report.json'))
raise SystemExit(0 if report['passed'] else 1)
