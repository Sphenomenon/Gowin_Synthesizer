#!/usr/bin/env python3
"""Exercise the real USB input wrapper's explicit audio reset boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_input import input_bundle
from run_workstation_usb_runtime_reset import compact, instance


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    bundle = input_bundle(ROOT)
    support = []
    for name, payload in bundle['payloads'].items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        support.append(path)
    wrapper = ROOT / 'rtl/workstation/workstation_usb2_input.sv'
    top = ROOT / 'rtl/workstation/gw138k_push_workstation_top.v'
    bench = Path(__file__).with_name('tb_workstation_usb2_owner_reset.sv')
    sources = [ROOT / name for name in bundle['native_paths']]
    sources += [ROOT / 'rtl/control/workstation_session.sv', *support, bench]
    identities = {str(path): sha(path) for path in sources + [top, Path(__file__).resolve(),
        Path(__file__).with_name('run_workstation_usb_runtime_reset.py')]}
    result = dict(schema_version=1, passed=False, scope='actual input wrapper, service adapter, owner, locked CDC/generated FIFO and session; modeled CPU MMIO producer and held/volume application',
        hardware_tested=False, synthesis_run=False, full_reset_accepted=False,
        sram_programmed=False, flash_programmed=False, input_sha256=identities,
        selected_support=bundle['provenance'], commands={}, negative_controls={})

    def run(name, command):
        result['commands'][name] = list(map(str, command))
        process = subprocess.run(command, text=True, capture_output=True, timeout=90, cwd=output)
        (output / (name + '.log')).write_text(process.stdout + process.stderr)
        return process

    try:
        selected = {}
        for mode, defines in (('runtime', ['-DWORKSTATION_RUNTIME_NATIVE']), ('default', [])):
            path = output / (mode + '_top.pre.v')
            process = run('preprocess_' + mode, ['iverilog', '-g2012', '-E', '-DWORKSTATION_CUSTOM_138K',
                *defines, '-o', str(path), str(top)])
            if process.returncode:
                raise ValueError('top preprocessing failed: ' + mode)
            text = path.read_text()
            native = instance(text, 'u_native_usb')
            parameters = re.search(r'workstation_usb2_input\s*#\((.*?)\)\s*$', text[:text.index('u_native_usb')], re.S)
            if not parameters:
                raise ValueError('native USB parameter selection missing: ' + mode)
            values = compact(parameters[1])
            opted_in = '.AUDIO_OWNER_RESET_SYNC(1)' in values
            if opted_in != (mode == 'runtime'):
                raise ValueError('audio reset opt-in escaped runtime scope: ' + mode)
            if '.FEEDBACK_AUDIO_DOMAIN(1)' not in values:
                raise ValueError('native feedback domain changed')
            expected = '.audio_reset_n(runtime_reset_n)' if mode == 'runtime' else '.audio_reset_n(audio_reset_n)'
            if expected not in native:
                raise ValueError('native USB platform reset request binding changed')
            selected[mode] = dict(audio_owner_reset_sync=int(opted_in), parameters=values, preprocessed_sha256=sha(path))
        result['top_selection'] = selected

        def simulation(name, selected_wrapper, phase=0.001):
            binary = output / (name + '.vvp')
            actual = [selected_wrapper if path == wrapper else path for path in sources]
            compile_result = run(name + '_compile', ['iverilog', '-g2012', '-s', 'tb_workstation_usb2_owner_reset',
                '-Ptb_workstation_usb2_owner_reset.AUDIO_PHASE_NS=' + str(phase),
                '-o', str(binary), *map(str, actual)])
            if compile_result.returncode:
                raise ValueError('simulation compile failed: ' + name)
            return run(name, ['vvp', str(binary)])

        positive = simulation('positive', wrapper)
        if positive.returncode or 'PASS usb2 owner reset:' not in positive.stdout:
            raise ValueError('owner reset regression failed; see positive.log')
        cases = re.findall(r'USB2_OWNER_RESET ([^\n]+)', positive.stdout)
        metrics = [{key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', row)} for row in cases]
        if len(metrics) != 2 or {item['sync'] for item in metrics} != {0, 1}:
            raise ValueError('default and opted-in coverage missing')
        for item in metrics:
            if item != dict(sync=item['sync'], releases=5, assertions=4, stopped_fences=3,
                            attaches=2, detaches=1, panics=1, defaults=26, retained=2):
                raise ValueError('incomplete reset/lifecycle/fence coverage')
        result['metrics'] = metrics
        result['phase_runs'] = {}
        for phase in (3.7, 9.1):
            name = 'phase_' + str(phase).replace('.', '_')
            shifted = simulation(name, wrapper, phase)
            if shifted.returncode or 'PASS usb2 owner reset:' not in shifted.stdout:
                raise ValueError('owner reset phase regression failed: ' + str(phase))
            result['phase_runs'][str(phase)] = dict(passed=True, log_sha256=sha(output / (name + '.log')))
        source = wrapper.read_text()
        mutations = {
            'raw_reset_bypass': ('assign owner_audio_reset_n = release_q[2];', 'assign owner_audio_reset_n = audio_reset_n;'),
            'first_stage_exported': ('assign owner_audio_reset_n = release_q[2];', 'assign owner_audio_reset_n = release_q[0];'),
            'wrong_release_clock': ('always @(posedge clk_audio or negedge qualified_n)', 'always @(posedge clk_ref or negedge qualified_n)'),
            'missing_async_assertion': ('always @(posedge clk_audio or negedge qualified_n)', 'always @(posedge clk_audio)'),
            'owner_audio_bypass': ('.audio_reset_n(owner_audio_reset_n)', '.audio_reset_n(audio_reset_n)'),
            'feedback_reset_bypass': ('? owner_audio_reset_n : feedback_release_q[1]', '? audio_reset_n : feedback_release_q[1]'),
        }
        for name, (before, after) in mutations.items():
            if source.count(before) != 1:
                raise ValueError('negative control anchor changed: ' + name)
            path = output / (name + '.sv')
            path.write_text(source.replace(before, after))
            negative = simulation(name, path)
            if negative.returncode == 0 or 'FATAL:' not in negative.stdout:
                raise ValueError('negative control was not detected: ' + name)
            result['negative_controls'][name] = dict(rejected=True, exit_code=negative.returncode,
                first_failure=next(line for line in negative.stdout.splitlines() if 'FATAL:' in line),
                mutated_source_sha256=sha(path))
        if {str(path): sha(path) for path in sources + [top, Path(__file__).resolve(),
                Path(__file__).with_name('run_workstation_usb_runtime_reset.py')]} != identities:
            raise ValueError('regression input drifted during execution')
        result['passed'] = True
        print(positive.stdout, end='')
        print('PASS six reset negative controls; full reset acceptance remains false')
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
