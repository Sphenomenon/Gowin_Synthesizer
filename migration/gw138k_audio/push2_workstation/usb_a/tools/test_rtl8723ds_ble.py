#!/usr/bin/env python3
"""Portable and GW138K BLE regressions using the same staged sources as synthesis."""
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
import subprocess
import shutil

from rtl8723ds_ble_sources import ROOT, RTL_NAMES, sha, stage_vendor


def run_case(name, top, files, cwd, output, plusargs=()):
    executable = output / (name + '.vvp')
    compile_result = subprocess.run(['iverilog', '-g2012', '-s', top, '-o', str(executable),
                                     *map(str, files)], cwd=cwd, capture_output=True, text=True)
    (output / (name + '_compile.log')).write_text(compile_result.stdout + compile_result.stderr)
    if compile_result.returncode:
        return {'name': name, 'pass': False, 'stage': 'compile', 'exit_code': compile_result.returncode}
    simulation = subprocess.run(['vvp', str(executable), *plusargs], cwd=cwd,
                                capture_output=True, text=True, timeout=180)
    log = simulation.stdout + simulation.stderr
    (output / (name + '.log')).write_text(log)
    passed = simulation.returncode == 0 and any(token in log for token in (
        'BT_H5_PASS', 'PASS: bt_gatt', 'PASS: pure Verilog', 'GW138K_BLE_BOARD_PASS', 'GW138K_BLE_UART50_PASS'))
    passed &= not any(token in log for token in ('FATAL:', 'ERROR:', 'FAIL:'))
    return {'name': name, 'pass': bool(passed), 'exit_code': simulation.returncode,
            'log': str(output / (name + '.log'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact-h5', action='store_true')
    parser.add_argument('--compact-hci', action='store_true')
    args = parser.parse_args()
    for tool in ('iverilog', 'vvp'):
        if not shutil.which(tool):
            raise SystemExit('Missing simulation tool: ' + tool)
    output = ROOT / 'results' / datetime.now().strftime(('ble_compact_all_regression_' if args.compact_h5 else ('ble_compact_regression_' if args.compact_hci else 'ble_regression_')) + '%Y%m%d_%H%M%S_%f')
    vendor = output / 'Prj1/vendor/rtl8723ds_ble'
    sources = stage_vendor(vendor, compact_hci=args.compact_hci, compact_h5=args.compact_h5)
    board_sources = sorted((ROOT / 'rtl/bluetooth').glob('*.v'))
    uart = ROOT.parent / 'results/workstation_20260911_174045_306332/Prj1/src/control/uart_tx.v'
    tests = ROOT / 'tests/bluetooth'
    all_sources = sources + board_sources + [uart]
    # Reuse the independent physical-UART controller model against the real
    # GW138K board wrapper, including its top-level output-enable gates.
    original = (vendor / 'tests/tb_bt_verilog_system.v').read_text()
    start = original.index('    rtl8723ds_ble #(')
    end = original.index('    always #5', start)
    board_instance = '''    wire wl_dis;
    gw138k_ble_board_top #(.CLK_HZ(CLK_HZ),
        .STARTUP_MS(2), .DISABLE_MS(1), .SESSION_MS(10000),
        .NOTIFY_MS(5), .REPORT_MS(10000),
        .PATCH_FILE("rtl8723ds_patch.mem")) dut (
        .clk_50m(clk), .button1_n(resetn && enable),
        .ble_module_uart_tx(uart_rx), .ble_module_uart_rx(uart_tx),
        .ble_module_bt_dis(bt_enable), .ble_module_wl_dis(wl_dis),
        .debug_uart_tx());
    assign debug=dut.u_ble.debug;
    assign initialized=dut.u_ble.initialized;
    assign failed=dut.u_ble.failed;
    assign connected=dut.u_ble.connected;
    assign subscribed=dut.u_ble.subscribed;
    assign outputs_active=dut.u_ble.outputs_active;
'''
    target = output / 'tb_bt_gw138k_system.v'
    target_text = original[:start] + board_instance + original[end:]
    # The physical module TX wire has a pull-up. Stop/failure intentionally
    # releases FPGA OE, possibly in the middle of an ACK. Check parity only
    # while OE remains asserted, then ignore the unfinished serial byte.
    target_text = target_text.replace('    wire uart_tx, bt_enable, outputs_active, initialized, failed;',
        '    tri1 uart_tx;\n    wire bt_enable, outputs_active, initialized, failed;')
    target_text = target_text.replace('if(uart_tx!==0)', 'if(outputs_active && uart_tx!==0)')
    target_text = target_text.replace('if(uart_tx!==parity)', 'if(outputs_active && uart_tx!==parity)')
    target_text = target_text.replace('if(uart_tx!==1)', 'if(outputs_active && uart_tx!==1)')
    target_text = target_text.replace('if(received_byte==\'hc0) begin',
        'if(!outputs_active) begin collecting=0; host_used=0; escaped=0; end\n'
        '            else if(received_byte==\'hc0) begin')
    target.write_text(target_text)
    cases = [
        ('h5', 'tb_bt_h5', [vendor/'rtl/bt_uart.v', vendor/'rtl/bt_h5_transport.v', vendor/'tests/tb_bt_h5.v'], ()),
        ('gatt', 'tb_bt_gatt', [vendor/'rtl/bt_gatt.v', vendor/'tests/tb_bt_gatt.v'], ()),
        ('system', 'tb_bt_verilog_system', sources + [vendor/'tests/tb_bt_verilog_system.v'], ()),
        ('wrong_rom', 'tb_bt_verilog_system', sources + [vendor/'tests/tb_bt_verilog_system.v'], ('+wrong_rom',)),
        ('gw138k_system', 'tb_bt_verilog_system', all_sources + [target], ()),
        ('gw138k_wrong_rom', 'tb_bt_verilog_system', all_sources + [target], ('+wrong_rom',)),
        ('board', 'tb_gw138k_ble_board', all_sources + [tests/'tb_gw138k_ble_board.v'], ()),
        ('uart50', 'tb_gw138k_ble_uart50', [vendor/'rtl/bt_uart.v', tests/'tb_gw138k_ble_uart50.v'], ()),
    ]
    print('BLE_REGRESSION=' + str(output), flush=True)
    def execute(case):
        name, top, files, plusargs = case
        try:
            result = run_case(name, top, files, vendor, output, plusargs)
        except subprocess.TimeoutExpired:
            result = {'name': name, 'pass': False, 'stage': 'simulation', 'error': '180 s timeout'}
        print(json.dumps(result), flush=True)
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(execute, cases))
    record = {'schema_version': 1, 'compact_hci': args.compact_hci, 'compact_h5': args.compact_h5, 'passed': all(r['pass'] for r in results),
              'results': results, 'staged_source_sha256': {str(p.relative_to(vendor)): sha(p) for p in sources}}
    (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
