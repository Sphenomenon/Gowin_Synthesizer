#!/usr/bin/env python3
"""Compare ideal LCD echo RTT with the unselected single-slot reverb budget."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_reverb_partition import CONFIG


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / ('rtl/workstation/workstation_task3_lcd_' + name + '.sv')
               for name in ('transport', 'phy')]
    sources.append(Path(__file__).with_name('tb_task3_lcd_roundtrip_budget.sv'))
    tracked = [*sources, Path(__file__), ROOT / 'tools/workstation_reverb_partition.py',
               ROOT / 'rtl/audio/workstation_remote_reverb_m.sv']
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {str(p): sha(p) for p in tracked}
    source = tracked[-1].read_text()
    match = re.search(r'parameter integer DEADLINE_CYCLES=(\d+)', source)
    if not match or int(match[1]) != CONFIG['remote_deadline_cycles']:
        raise ValueError('single-slot source deadline/configuration changed')
    deadline_ns = CONFIG['remote_deadline_cycles'] * 1e9 / CONFIG['compute_clock_hz']
    result = dict(schema=1, passed=False, source_sha256=before, trials=[], commands=[],
        comparison_configuration=CONFIG, single_slot_deadline_ns=deadline_ns,
        scope='Existing channel-0 control-frame echo over real transport/PHY RTL. '
              'Zero wire delay, immediate echo, no effect engine or media owner. '
              'A model comparison, not a hardware latency bound or media integration.',
        new_reverb_wire_protocol=False, business_enabled=False, hardware_tested=False,
        physical_budget_authorized=False, physical_RTT_ns=None)

    def command(name, argv):
        ran = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        log = output / (name + '.log')
        log.write_text(ran.stdout + ran.stderr)
        result['commands'].append(dict(command=argv, exit_code=ran.returncode,
                                      log=str(log), log_sha256=sha(log)))
        if ran.returncode:
            raise ValueError('diagnostic failed: ' + str(log))
        return ran.stdout

    try:
        result['verilator'] = command('verilator_version', ['verilator', '--version']).strip()
        for half, phase in ((10, 1), (10, 3), (10, 9), (11, 1), (11, 3), (11, 9)):
            name = 'W_half_' + str(half) + '_phase_' + str(phase)
            obj = output / (name + '_obj')
            command(name + '_compile', ['verilator', '--binary', '--timing', '--build-jobs', '4',
                '--top-module', 'tb_task3_lcd_roundtrip_budget',
                '-GW_HALF_NS=' + str(half), '-GW_PHASE_NS=' + str(phase),
                '--Mdir', str(obj), *map(str, sources)])
            text = command(name + '_run', [str(obj / 'Vtb_task3_lcd_roundtrip_budget')])
            rows = [(int(i), int(t)) for i, t in re.findall(r'LCD_ECHO request=(\d+) elapsed_ns=(\d+)', text)]
            if [i for i, _ in rows] != list(range(4)) or 'PASS task3_lcd_roundtrip_budget' not in text:
                raise ValueError('missing ordered echo observations')
            result['trials'].append(dict(M_clock_Hz=50000000, W_clock_Hz=1e9/(2*half),
                W_initial_phase_ns=phase, roundtrips_ns=[t for _, t in rows],
                all_exceed_single_slot_deadline=all(t > deadline_ns for _, t in rows)))
            print(name, rows, flush=True)
        times = [t for trial in result['trials'] for t in trial['roundtrips_ns']]
        result.update(passed=True, model_min_RTT_ns=min(times), model_max_RTT_ns=max(times),
            current_single_slot_fits_all_tested_ideal_echoes=all(t <= deadline_ns for t in times),
            conclusion='Keep the single-slot reverb seam unselected pending a transport/owner design '
                       'with a measured bounded queue and compatible sample schedule.')
    finally:
        result['source_unchanged'] = before == {str(p): sha(p) for p in tracked}
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    if not result['source_unchanged']:
        raise ValueError('diagnostic inputs changed')
    print({k: result[k] for k in ('passed', 'model_min_RTT_ns', 'model_max_RTT_ns',
        'single_slot_deadline_ns', 'current_single_slot_fits_all_tested_ideal_echoes')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
