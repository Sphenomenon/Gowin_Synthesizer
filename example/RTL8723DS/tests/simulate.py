"""Run the unchanged vendor protocol tests on original or adapted RTL."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import time

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--adapted', action='store_true', help='test generated Gowin storage adaptations')
args = parser.parse_args()
vendor = project / 'vendor' / 'rtl8723ds_ble'
reports = project / 'reports'
reports.mkdir(exist_ok=True)
iverilog = shutil.which('iverilog') or '/opt/homebrew/bin/iverilog'
vvp = shutil.which('vvp') or '/opt/homebrew/bin/vvp'
core = sorted((vendor / 'rtl').glob('*.v'))
prefix = 'adapted_' if args.adapted else ''
if args.adapted:
    subprocess.run([sys.executable, str(project/'prepare_adapted.py')], check=True)
    core = [project/'generated/rtl'/p.name if p.name in {'bt_h5_transport.v','bt_gatt.v','bt_verilog_core.v'} else p
            for p in core]
cases = [
    ('board', 'tb_ble_bringup',
     [project/'tests/tb_ble_bringup.v', project/'rtl/ble_bringup_top.v',
      project/'rtl/usb1_passive_monitor.v', *core],
     project, [], 'PASS: POR,'),
    ('h5', 'tb_bt_h5', [vendor/'tests/tb_bt_h5.v', *core], vendor, [], 'BT_H5_PASS'),
    ('gatt', 'tb_bt_gatt', [vendor/'tests/tb_bt_gatt.v', *core], vendor, [], 'PASS: bt_gatt'),
    ('system', 'tb_bt_verilog_system', [vendor/'tests/tb_bt_verilog_system.v', *core],
     vendor, [], 'PASS: pure Verilog UART8E1/H5 full patch'),
    ('wrong_rom', 'tb_bt_verilog_system', [vendor/'tests/tb_bt_verilog_system.v', *core],
     vendor, ['+wrong_rom'], 'PASS: pure Verilog system rejects incompatible ROM'),
]
results = {}
for name, top, files, cwd, args, token in cases:
    started = time.monotonic()
    artifact = reports / (prefix + name + '.vvp')
    compile_result = subprocess.run(
        [iverilog, '-g2012', '-s', top, '-o', str(artifact), *map(str, files)],
        cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (reports / (prefix + name + '_compile.log')).write_text(compile_result.stdout)
    if compile_result.returncode:
        raise SystemExit(f'{name}: compile failed: {compile_result.stdout}')
    result = subprocess.run([vvp, str(artifact), *args], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (reports / (prefix + name + '.log')).write_text(result.stdout)
    passed = result.returncode == 0 and token in result.stdout and 'FAIL:' not in result.stdout
    results[name] = {'pass': passed, 'seconds': round(time.monotonic()-started, 3)}
    print(name + ': ' + ('PASS' if passed else 'FAIL'), flush=True)
    if not passed:
        raise SystemExit(result.stdout)
(reports / (prefix + 'simulation_results.json')).write_text(json.dumps(results, indent=2) + '\n')
