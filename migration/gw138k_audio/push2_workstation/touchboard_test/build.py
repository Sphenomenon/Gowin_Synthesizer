#!/usr/bin/env python3
"""Build a standalone GW5AST-138C touch probe, without changing the workstation."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from netlist import connector_wiring

ROOT = Path(__file__).resolve().parent
BALLS = {
    # NEO Dock 31005 schematic, sheet 19 + BTB mapping sheets.
    'J8': {5: 'AA19', 6: 'AB20', 7: 'AA20', 8: 'AA21', 9: 'AB21', 10: 'AB22', 11: 'Y21', 12: 'Y22'},
    'J9': {5: 'R18', 6: 'T18', 7: 'P16', 8: 'R17', 9: 'T21', 10: 'U21', 11: 'P19', 12: 'R19'},
}
# Explicit electrical wiring, equivalent to a 180-degree mate of U4 pins 3..14.
HEADER, WIRING = connector_wiring()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connector', choices=BALLS, default='J8')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--power-audit',action='store_true',help='TW1 pad audit + TA1 FPGA SOM VCCIO4 telemetry (separate from PMOD 3V3)')
    parser.add_argument('--safe-gpio',action=argparse.BooleanOptionalAction,default=True,help='drive unused QT2160 GPIO1..3 low; startup readback of register 73')
    parser.add_argument('--wire-device',choices=('U1','U2'),default='U1',help='QT2160 physical bus selected for the independent wire audit')
    parser.add_argument('--wire-trace', action='store_true', help='independent pad-level I2C byte listener with TW1 telemetry')
    parser.add_argument('--diagnostic', action='store_true', help='open-drain PMOD pair sweep, DG1 telemetry')
    parser.add_argument('--no-internal-pullups', action='store_true', help='diagnostic external pull-up isolation test')
    parser.add_argument('--isolate-u1',action='store_true',help='temporary single-device/no-other-I2C traffic test')
    parser.add_argument('--frame-hz',type=int,default=50)
    parser.add_argument('--audit-config',action=argparse.BooleanOptionalAction,default=False,help='verify immutable configuration registers during every polling cycle')
    parser.add_argument('--full-scan',action='store_true',help='diagnostic scan addresses 0x08..0x77 on all pad pairs')
    parser.add_argument('--raw-words',action=argparse.BooleanOptionalAction,default=False,help='audit individual 16-bit register reads instead of 64-byte bursts')
    parser.add_argument('--black-leds',action=argparse.BooleanOptionalAction,default=True,help='send one all-black WS2812 frame before touch calibration')
    parser.add_argument('--key-mask',type=lambda x:int(x,0),default=0xffff)
    parser.add_argument('--burst',type=int,choices=range(1,33),default=1)
    parser.add_argument('--poll-ms',type=int,default=16)
    parser.add_argument('--i2c-hz',type=int,default=100000)
    parser.add_argument('--sleep-after-ms',type=int,default=0)
    parser.add_argument('--route-option', type=int, choices=(0,1,2), default=0)
    parser.add_argument('--user-code', default='5442010A')
    args = parser.parse_args()
    if args.power_audit: args.wire_trace=True
    if args.wire_device=='U2' and not args.wire_trace:
        parser.error('--wire-device U2 requires --wire-trace or --power-audit')
    if args.wire_trace and args.diagnostic:
        parser.error('--wire-trace and --diagnostic are mutually exclusive')
    if not (1 <= args.frame_hz <= 50 and 1 <= args.poll_ms <= 1000 and
            10000 <= args.i2c_hz <= 100000 and 0 <= args.sleep_after_ms <= 30000 and
            0 <= args.key_mask <= 0xffff):
        parser.error('profile out of range (frame1..50Hz, poll1..1000ms, I2C10..100kHz, sleep0..30s, mask16bit)')
    if not re.fullmatch(r'[0-9a-fA-F]{8}', args.user_code):
        parser.error('--user-code requires eight hex digits')
    out = ROOT / 'results' / datetime.now().strftime('build_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True)
    for source in (ROOT / 'rtl').glob('*'):
        shutil.copy2(source, out / source.name)
    top_path=out/'touchboard_top.sv'
    top_text=top_path.read_text()
    top_text=top_text.replace('PROBE_BURST=1, PROBE_POLL_MS=16, PROBE_I2C_HZ=100000, SLEEP_AFTER_MS=0', f'PROBE_BURST={args.burst}, PROBE_POLL_MS={args.poll_ms}, PROBE_I2C_HZ={args.i2c_hz}, SLEEP_AFTER_MS={args.sleep_after_ms}')
    top_text=top_text.replace("PROBE_KEY_MASK=16'hffff",f"PROBE_KEY_MASK=16'h{args.key_mask:04x}")
    top_text=top_text.replace('BLACK_LEDS=1',f'BLACK_LEDS={int(args.black_leds)}')
    top_text=top_text.replace('RAW_WORDS=0',f'RAW_WORDS={int(args.raw_words)}')
    top_text=top_text.replace('AUDIT_CONFIG=0',f'AUDIT_CONFIG={int(args.audit_config)}')
    top_text=top_text.replace('ISOLATE_U1=0, FRAME_HZ=50',f'ISOLATE_U1={int(args.isolate_u1)}, FRAME_HZ={args.frame_hz}')
    top_text=top_text.replace('SAFE_GPIO=1',f'SAFE_GPIO={int(args.safe_gpio)}')
    top_path.write_text(top_text)
    if args.wire_trace:
        trace_path=out/'touchboard_wire_top.sv'
        trace_text=trace_path.read_text().replace('PROBE_BURST=1, PROBE_POLL_MS=32, PROBE_I2C_HZ=100000', f'PROBE_BURST={args.burst}, PROBE_POLL_MS={args.poll_ms}, PROBE_I2C_HZ={args.i2c_hz}')
        trace_text=trace_text.replace('RAW_WORDS=1',f'RAW_WORDS={int(args.raw_words)}')
        trace_text=trace_text.replace('SAFE_GPIO=0',f'SAFE_GPIO={int(args.safe_gpio)}')
        trace_text=trace_text.replace('PROBE_SLIDER=0',f'PROBE_SLIDER={int(args.wire_device=="U2")}')
        trace_text=trace_text.replace('POWER_ADC=0',f'POWER_ADC={int(args.power_audit)}')
        trace_path.write_text(trace_text)
    if args.full_scan:
        diag_path=out/'touchboard_diag_top.sv'
        diag_path.write_text(diag_path.read_text().replace('FULL_SCAN=0','FULL_SCAN=1'))
    pins = {'clk_50m': 'V22', 'button1_n': 'AB13', 'debug_uart_tx': 'U15', 'pa_en': 'AB16'}
    pins.update({name: BALLS[args.connector][number] for name, number in WIRING.items()})
    cst = ['CLOCK_LOC "clk_50m_d" BUFG = CLK;']
    for name, ball in pins.items():
        cst.append(f'IO_LOC "{name}" {ball};')
        pull = 'NONE' if args.no_internal_pullups and name in WIRING else ('UP' if args.diagnostic and name in WIRING else ('DOWN' if name == 'ws2812_din' else ('NONE' if name in ('clk_50m', 'pa_en') else 'UP')))
        drive = '' if name in ('clk_50m', 'button1_n', 'change_n', 'ws2812_din') else ' DRIVE=4'
        bank = ' BANK_VCCIO=3.3' if name in WIRING else ''
        cst.append(f'IO_PORT "{name}" IO_TYPE=LVCMOS33 PULL_MODE={pull}{drive}{bank};')
    (out / 'touchboard.cst').write_text('\n'.join(cst) + '\n')
    sdc = '''create_clock -name clk_50m -period 20.000 -waveform {0.000 10.000} [get_ports {clk_50m}]
set_false_path -from [get_ports {button1_n change_n scl1 sda1 scl2 sda2 scl3 sda3 ws2812_din}] -to [get_pins {*meta*/D}]
set_false_path -to [get_ports {debug_uart_tx scl1 sda1 scl2 sda2 scl3 sda3 pa_en}]
'''
    (out / 'touchboard.sdc').write_text(sdc)
    entries = '\n'.join(f'<File path="{p.name}" type="file.verilog" enable="1"/>' for p in sorted((ROOT / 'rtl').glob('*')))
    (out / 'touchboard.gprj').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<Project><Template>FPGA</Template><Version>5</Version>
<Device name="GW5AST-138C" pn="GW5AST-LV138PG484AC2/I1">gw5ast138c-006</Device>
<FileList>''' + entries + '''
<File path="touchboard.cst" type="file.cst" enable="1"/>
<File path="touchboard.sdc" type="file.sdc" enable="1"/>
</FileList></Project>
''')
    (out / 'build.tcl').write_text('''open_project touchboard.gprj
set_option -top_module touchboard_top
set_option -output_base_name touchboard
set_option -verilog_std sysv2017
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -timing_driven 1
set_option -correct_hold_violation 1
set_option -place_option 2
set_option -route_option ROUTE_OPTION
set_option -gen_text_timing_rpt 1
set_option -gen_verilog_sim_netlist 1
set_option -user_code ''' + args.user_code.upper() + '\nrun all\n')
    tcl_path=out/'build.tcl'
    tcl_path.write_text(tcl_path.read_text().replace('ROUTE_OPTION',str(args.route_option)).replace('set_option -top_module touchboard_top', 'set_option -top_module touchboard_wire_top' if args.wire_trace else ('set_option -top_module touchboard_diag_top' if args.diagnostic else 'set_option -top_module touchboard_top')))
    result = dict(wire_device=args.wire_device,power_audit=args.power_audit,wire_trace=args.wire_trace,full_scan=args.full_scan,profile=dict(safe_gpio=args.safe_gpio,isolate_u1=args.isolate_u1,frame_hz=args.frame_hz,audit_config=args.audit_config,raw_words=args.raw_words,black_leds=args.black_leds,key_mask=args.key_mask,burst=args.burst,poll_ms=args.poll_ms,i2c_hz=args.i2c_hz,sleep_after_ms=args.sleep_after_ms),no_internal_pullups=args.no_internal_pullups, diagnostic=args.diagnostic, route_option=args.route_option, created_at=datetime.now().astimezone().isoformat(), connector=args.connector,
                  user_code='0x' + args.user_code.upper(), target='GW5AST-LV138PG484AC2/I1',
                  wiring=WIRING, u4_header=HEADER, netlist_wiring_verified=True, pins=pins, netlist_sha256=sha(ROOT / 'input_netlist.tel'),
                  inputs={p.name: sha(p) for p in out.iterdir() if p.is_file()},
                  hardware_tested=False, sram_programmed=False, flash_written=False)
    (out / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
    print(out, flush=True)
    if args.prepare_only:
        return
    with (out / 'gowin.log').open('w') as log:
        run = subprocess.run([str(Path.home() / '.local/bin/gw_sh'), 'build.tcl'], cwd=out,
                             stdout=log, stderr=subprocess.STDOUT)
    fs = out / 'impl/pnr/touchboard.fs'
    result['exit_code'] = run.returncode
    result['bitstream_generated'] = fs.exists() and run.returncode == 0
    if result['bitstream_generated']:
        timing = (out / 'impl/pnr/touchboard.tr').read_text()
        counts = {kind: re.search(r'<Numbers of ' + kind + r' Violated Endpoints>:(\d+)', timing) for kind in ('Setup', 'Hold')}
        result['timing_violated_endpoints'] = {kind: int(match[1]) if match else None for kind, match in counts.items()}
        result['routed_timing_passed'] = all(value == 0 for value in result['timing_violated_endpoints'].values())
        result['bitstream_sha256'] = sha(fs)
        if result['routed_timing_passed']:
            (ROOT / 'LATEST_BUILD.txt').write_text(str(out) + '\n')
    (out / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    if not result['bitstream_generated'] or not result.get('routed_timing_passed'):
        print((out / 'gowin.log').read_text()[-7000:], file=sys.stderr)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
