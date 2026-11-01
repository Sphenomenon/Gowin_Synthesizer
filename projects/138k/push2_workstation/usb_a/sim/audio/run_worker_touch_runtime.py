#!/usr/bin/env python3
"""Execute W production C MIDI mapping through the real USB FIFO and D DSP."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from run_runtime_controlled import runtime_sources

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_input import input_bundle


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    project, output = a.project.resolve(), a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    tb = ROOT/'sim/audio/tb_workstation_worker_touch_runtime.sv'
    selected = []
    for path in runtime_sources(project, tb):
        if path.is_relative_to(project):
            relative = path.relative_to(project)
            if relative.parts[:2] == ('rtl', 'control') or relative.parts[:3] == ('rtl', 'audio', 'delay_ddr'):
                path = ROOT/relative
        if path not in selected:
            selected.append(path)
    bundle = input_bundle(ROOT)
    for name, payload in bundle['payloads'].items():
        if name.endswith('gw138k_usb_event_fifo.v'):
            path = output/'gw138k_usb_event_fifo.v'
            path.write_bytes(payload)
            selected.append(path)
        elif name.endswith('gw138k_stream_cdc.sv'):
            assert payload == (project/'src/migration/gw138k_stream_cdc.sv').read_bytes()
    selected += [ROOT/'rtl/workstation/workstation_worker_usb.sv',
                 ROOT/'rtl/workstation/workstation_usb2_service_adapter.sv']
    memory_reference = ROOT/'sim/audio/tb_workstation_runtime_effects.sv'
    memory_text = memory_reference.read_text()
    anchor = '\nmodule tb_workstation_runtime_effects;'
    assert memory_text.count(anchor) == 1
    memory = output/'ordered_posted_ddr_model.sv'
    memory.write_text(memory_text.split(anchor)[0])
    selected.append(memory)
    vendor = ROOT/'vendor/usb_host_fs_8fc3/firmware'
    inputs = list(dict.fromkeys(selected + [Path(__file__).resolve(), memory_reference,
        ROOT/'sim/audio/run_runtime_controlled.py', ROOT/'tools/workstation_usb2_input.py',
        ROOT/'firmware.c', ROOT/'gw25k_panel.h', ROOT/'sim/test_gw25k_panel.c',
        ROOT/'rtl/push2_usb_a_control.sv', ROOT/'sim/audio/fixtures/d_process_before_exact_mask.svh']))
    inputs += sorted((project/'sim/data').rglob('*.mem'))
    inputs += sorted((project/'sim/matlab/output').rglob('*.mem'))
    inputs += sorted((project/'rtl/audio/scope_vec/data').glob('*.mem'))
    hashes = {str(path): sha(path) for path in inputs}
    report = dict(passed=False, hardware_tested=False, synthesis_tested=False,
        scope='production C MIDI -> captured actual MMIO writes -> service adapter -> real USB FIFO/CDC/lifecycle -> sole D parameters -> native D/full effects/ordered DDR -> coherent committed feedback',
        limits='Ideal RTL clocks and functional DDR model; no radio, hardware I2S/HDMI, physical CDC or board acceptance',
        prepared_reference=str(project), input_sha256=hashes, stages=[])
    trace, binary = output/'production-c-touch-trace.txt', output/'worker-c'
    stages = [
        ('c_compile', ['cc', '-std=c99', '-O1', '-g', '-Wall', '-Wextra',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-DWORKSTATION_WORKER_DEMO=1',
            '-I'+str(vendor), '-I'+str(vendor/'usb'), str(ROOT/'sim/test_gw25k_panel.c'), '-o', str(binary)]),
        ('c_trace', [str(binary), '--worker-touch-trace', str(trace)]),
        ('rtl_compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
            '--top-module', 'tb_workstation_worker_touch_runtime', '--Mdir', str(output/'obj'),
            '-I'+str(ROOT), '-I'+str(project), *map(str, selected)]),
        ('rtl_run', [str(output/'obj/Vtb_workstation_worker_touch_runtime'), '+TRACE='+str(trace)]),
    ]
    try:
        for name, argv in stages:
            log = output/(name+'.log')
            with log.open('x') as stream:
                p = subprocess.run(argv, cwd=project, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
            contents = log.read_text()
            report['stages'].append(dict(name=name, argv=argv, exit_code=p.returncode,
                log_sha256=sha(log), warning_count=contents.count('%Warning')))
            p.check_returncode()
            if '%Error' in contents or 'ERROR:' in contents or 'FATAL:' in contents or 'UNOPTFLAT' in contents:
                raise ValueError('compile/runtime error or combinational loop: '+name)
            if name == 'rtl_run':
                rows = [x for x in contents.splitlines() if x.startswith('PASS worker_touch_runtime ')]
                assert len(rows) == 1, contents[-3000:]
                report['stages'][-1]['result'] = rows[0]
                print(rows[0], flush=True)
        assert hashes == {str(path): sha(path) for path in inputs}, 'consumed input changed during test'
        report.update(passed=True, all_consumed_inputs_unchanged=True, production_c_trace_sha256=sha(trace),
            production_c_trace_rows=len(trace.read_text().splitlines()))
    finally:
        (output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
