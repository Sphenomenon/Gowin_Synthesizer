#!/usr/bin/env python3
"""Real C/parser/APB/CRC/DDR format2 capture, resume and rate-fault checks.

Uses 50 MHz control, 44.1/48 kHz source pulses and the 14 ns modeled DDR clock.
The host compiler runs the maintained single C owner, not the AE350 ISA/core.
This does not select a paired profile or enable cross-board 44.1 kHz traffic.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CAPACITY = 2880000
BASE = 0x0c180000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT))
    from tools.workstation_baselines import load_baseline
    from tools.workstation_resource_timing import apb
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    cdc = output / 'gw138k_apb_cdc.sv'
    cdc.write_text(apb(baseline.read_bytes('src/migration/gw138k_apb_cdc.sv').decode()))
    cpu = ROOT / 'rtl/bluetooth/cpu_owner'
    files = [Path(__file__).with_name('ae350_ble_business_cosim.sv'), cdc,
             *[cpu / name for name in ('ble_protocol_command.v',
               'workstation_ble_record_data_engine.sv', 'workstation_ble_record_data_service.sv')],
             *[ROOT / name for name in ('rtl/services/workstation_business_mailbox.sv',
               'rtl/memory/workstation_ble_raw_ddr_store.sv',
               'rtl/memory/workstation_recording_ddr_native_bridge.sv',
               'rtl/memory/workstation_sdp.sv', 'rtl/music/music_async_fifo.sv')]]
    include = ROOT / 'firmware/ae350'
    cfiles = [include / name for name in ('business_mailbox.c', 'recording_service.c', 'ble_business_owner.c')]
    cpp = Path(__file__).with_name('ae350_ble_record_formats.cpp')
    tracked = [*files, *cfiles, cpp, Path(__file__),
               Path(__file__).with_name('ae350_ble_business_cosim.cpp'),
               *[include / name for name in ('ble_business_owner.h', 'recording_service.h',
                                             'business_mailbox.h', 'audio_services.h')]]
    before = {str(path): sha(path) for path in tracked}
    commands, mutations, mismatches = [], {}, {}
    report = dict(schema=1, passed=False, input_sha256=before, commands=commands,
                  mutations=mutations, ABI_mismatches=mismatches,
                  profile_selected=False, cross_board_44100_enabled=False,
                  synthesis=False, pnr=False, hardware_tested=False,
                  sram_programmed=False, flash_programmed=False)

    def run(argv, label, *, cwd=None, expected_failure=None, timeout=180):
        argv = list(map(str, argv))
        process = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        text = process.stdout + process.stderr
        log = output / (label + '.log')
        log.write_text(text)
        commands.append(dict(argv=argv, cwd=str(cwd) if cwd else None,
                             exit_code=process.returncode, log=str(log), log_sha256=sha(log)))
        if expected_failure:
            if process.returncode == 0 or expected_failure not in text:
                raise RuntimeError(f'{label}: expected rejection absent; {log}')
        elif process.returncode:
            raise RuntimeError(f'{label} failed; {log}')
        return text

    common = ['-DA138_BLE_BUSINESS', '-DA138_SINGLE_BLE_RECORDING',
              f'-DA138_BLE_RECORD_CAPACITY_FRAMES={CAPACITY}u', '-I' + str(include)]
    flags = [*common, '-DA138_BLE_RECORD_DUAL_RATE']
    cbase = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror']

    def objects(dual):
        result = []
        for source in cfiles:
            target = output / (source.stem + ('-dual.o' if dual else '-v3.o'))
            run([*cbase, *(flags if dual else common), '-c', source, '-o', target], target.stem)
            result.append(target)
        return result

    def build(label, selected, *, dual=True, c_dual=True, inputs=files):
        directory = output / label
        run(['verilator', '--cc', '--exe', '--build', '-j', '2', '--timing', '-Wno-fatal',
             '--top-module', 'ae350_ble_business_cosim', '+define+WORKSTATION_SINGLE_BLE_RECORDING',
             '+define+TASK3_RECORD_FORMAT_TEST', f'-GDUAL_RATE_RECORDING={int(dual)}',
             f'-GCAPACITY_FRAMES={CAPACITY}', f'-GBASE_APP={BASE}', '--Mdir', directory,
             '-CFLAGS', ' '.join([*(flags if c_dual else common), '-DA138_TASK3_LONG_RECORDING_TEST']),
             '-LDFLAGS', ' '.join(map(str, selected)), *inputs, cpp], label + '-compile', timeout=300)
        if 'UNOPTFLAT' in (output / (label + '-compile.log')).read_text():
            raise RuntimeError('combinational loop in ' + label)
        return directory / 'Vae350_ble_business_cosim'

    try:
        selected = objects(True)
        binary = build('obj', selected)
        text = run([binary], 'formats-run', timeout=90)
        metrics = re.search(r'PASS recording formats frames=(\d+) bytes=(\d+) source_ticks=(\d+) resumed_offset=(\d+) crc=([0-9a-f]+) checks=(\d+)', text)
        if not metrics:
            raise RuntimeError('complete capture/download/rate-fault evidence missing')
        # Same physical RTL model; only the C policy translation unit changes.
        source = cfiles[-1].read_text()
        controls = {
            'skip_format_grant': ('if(format==2 && o->format_grant_session==o->request.key.session && (o->format_grant_mask&2u))', 'if(format==2)'),
            'retain_grant_after_reconnect': ('o->format_grant_mask=0;', 'o->format_grant_mask|=0;'),
            'relabel_object_as_48k': ('put(o->completion_payload+16,f->rate_hz);', 'put(o->completion_payload+16,48000);')}
        link = next(line for line in (output / 'obj-compile.log').read_text().splitlines()
                    if line.startswith('c++ ') and line.rstrip().endswith(' -o Vae350_ble_business_cosim'))
        for label, (old, new) in controls.items():
            if source.count(old) != 1:
                raise RuntimeError('C negative anchor drift: ' + label)
            mutated = output / (label + '.c');mutated.write_text(source.replace(old, new))
            obj = output / (label + '.o')
            run([*cbase, *flags, '-c', mutated, '-o', obj], label + '-compile')
            argv = [str(obj) if arg == str(selected[-1]) else arg for arg in shlex.split(link)]
            argv[argv.index('-o') + 1] = str(output / label)
            run(argv, label + '-link', cwd=output / 'obj', timeout=60)
            run([output / label], label + '-run', expected_failure='FAIL ', timeout=90)
            mutations[label] = dict(rejected=True, modified_source_sha256=sha(mutated))
        engine = files[3]
        original = engine.read_text()
        old = '(!DUAL_RATE_RECORDING || source_format_i==payload[7:0]);'
        if original.count(old) != 1:
            raise RuntimeError('physical-source negative anchor drift')
        mutated = output / engine.name
        mutated.write_text(original.replace(old, "1'b1;"))
        negative = build('obj-ignore-source', selected,
                         inputs=[mutated if source == engine else source for source in files])
        run([negative], 'ignore-source-run', expected_failure='FAIL requested44.1 cannot relabel actual48k source')
        mutations['ignore_actual_source_format'] = dict(rejected=True, modified_source_sha256=sha(mutated))
        forward = build('obj-dual-C-v3-RTL', selected, dual=False)
        run([forward, 'expect-mismatch'], 'dual-C-v3-RTL-run')
        mismatches['dual_C_v3_RTL'] = 'rejected_before_object_allocation'
        reverse = build('obj-v3-C-dual-RTL', objects(False), c_dual=False)
        run([reverse, 'expect-mismatch'], 'v3-C-dual-RTL-run')
        mismatches['v3_C_dual_RTL'] = 'rejected_before_object_allocation'
        if before != {path: sha(path) for path in before}:
            raise RuntimeError('source inputs changed during verification')
        report.update(passed=True, inputs_unchanged=True,
                      control_period_ns=20, memory_period_ns=14,
                      physical_store_capacity_frames=CAPACITY,
                      capture_format=2, capture_rate_hz=44100,
                      captured_frames=int(metrics[1]), downloaded_bytes=int(metrics[2]),
                      source_ticks_in_10ms=int(metrics[3]), resumed_offset_bytes=int(metrics[4]),
                      object_crc=metrics[5], checks=int(metrics[6]),
                      source_sequence_independent_of_recorder=True,
                      actual_cadence_simulated=True, full_60_second_capture=False,
                      competing_CNN_or_phone=False, controller_is_behavioral=True,
                      scope='Maintained host-compiled sole C owner and parser/APB/CRC/raw DDR RTL. No complete AE350 core, paired ARM, LCD, RF, DAC or hardware execution.')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('passed', 'captured_frames', 'downloaded_bytes', 'object_crc', 'checks')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output.resolve())
