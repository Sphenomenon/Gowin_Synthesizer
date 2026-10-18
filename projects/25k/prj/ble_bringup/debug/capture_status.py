"""Capture an already-programmed BLE GAO core; never program FPGA/flash."""
from pathlib import Path
import argparse
import os
import subprocess
from datetime import datetime

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--location', help='optional FTDI location from the cable scan')
parser.add_argument('--timeout', type=int, default=30)
parser.add_argument('--output-prefix', type=Path,
                    help='unique capture path prefix; default includes current time')
args = parser.parse_args()
ide = Path('/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE')
env = dict(os.environ, DYLD_LIBRARY_PATH=str(ide/'lib'), DYLD_FRAMEWORK_PATH=str(ide/'lib'))
prefix = args.output_prefix or project/'reports'/('ble_status_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
prefix = prefix.resolve()
prefix.parent.mkdir(parents=True, exist_ok=True)
command = [str(ide/'bin/gao_sh'), '-gao', str(project/'debug/ble_status.rao'),
           '-device', 'GW5A-25A', '-cable', 'FT2CH', '-out', str(prefix)]
if args.location:
    command += ['-location', args.location]
print('Capturing the existing GAO image using FT2CH channel 0.', flush=True)
try:
    result = subprocess.run(command, cwd=project, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=args.timeout)
except subprocess.TimeoutExpired as exc:
    output = exc.stdout or b''
    if isinstance(output, bytes):
        output = output.decode(errors='replace')
    (project/'reports/gao_capture.log').write_text(output + '\nCAPTURE TIMEOUT\n')
    raise SystemExit('GAO capture timed out. Check that the matching GAO bitstream is loaded.')
(project/'reports/gao_capture.log').write_text(result.stdout)
print(result.stdout, end='')
if result.returncode:
    raise SystemExit(result.returncode)
files = sorted(prefix.parent.glob(prefix.name + '*.csv'))
if not files:
    raise SystemExit('GAO returned without a CSV capture; inspect reports/gao_capture.log.')
for file in files:
    print(file)
