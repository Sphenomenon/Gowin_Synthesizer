#!/usr/bin/env python3
"""Native clock-command ownership through real predecoded APB CDC and switch RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools import workstation_resource_timing as timing
from tools.workstation_composition import SOURCES


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output, prepared_project=None, epoch_policy='legacy'):
    reserved,seed={'legacy':(0,0),'nonzero':(1,1),'wrap':(1,0xfffffffe)}[epoch_policy]
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    original_apb = baseline.read_bytes('src/migration/gw138k_apb_cdc.sv')
    apb_bytes = timing.apb(original_apb.decode()).encode()
    output.mkdir(parents=True, exist_ok=False)
    apb = output / 'gw138k_apb_cdc.sv'
    apb.write_bytes(apb_bytes)
    reference = None
    if prepared_project is not None:
        reference_path = prepared_project.resolve() / 'src/migration/gw138k_apb_cdc.sv'
        assert reference_path.read_bytes() == apb_bytes, 'Prepared APB mailbox differs from frozen reconstruction'
        reference = dict(path=str(reference_path), sha256=digest(reference_path), exact=True)
    sources = [ROOT / 'rtl/services/workstation_audio_clock_service.sv',
               ROOT / 'rtl/audio/workstation_sample_rate_switch.sv', apb,
               Path(__file__).with_name('tb_workstation_audio_clock_service.sv')]
    profile_path = ROOT / 'boards/custom_138k/workstation_profile_v1.json'
    profile = json.loads(profile_path.read_text())
    native_path = 'rtl/services/workstation_audio_clock_service.sv'
    assert native_path not in SOURCES, 'Clock service must remain explicitly unselected at this stage'
    runtime_profile_selected=any(path.endswith('/'+native_path) for path in profile['source_sha256'])
    inputs = sources + [Path(__file__).resolve(), ROOT / 'tools/workstation_resource_timing.py',
                       ROOT / 'tools/workstation_baselines.py', ROOT / 'tools/workstation_composition.py',
                       ROOT / 'rtl/services/AUDIO_CLOCK_SERVICE_CONTRACT.md', profile_path, baseline.manifest]
    paths = {('prepared/gw138k_apb_cdc.sv' if path == apb else str(path.relative_to(ROOT))): path for path in inputs}
    hashes = {key: digest(path) for key, path in paths.items()}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                  validation_stage='offline-native-service-real-apb-cdc-and-clock-transaction',
                  identity='audio-clock-command-offline-v2-' + epoch_policy + '-' + identity[:16], source_set_sha256=identity,
                  baseline=baseline.evidence(), runtime_profile_selected=runtime_profile_selected,
                  apb=dict(input='src/migration/gw138k_apb_cdc.sv',
                           before_sha256=hashlib.sha256(original_apb).hexdigest(),
                           predecoded_sha256=digest(apb), prepared_reference=reference),
                  input_sha256=hashes, input_paths={key: str(path) for key, path in paths.items()},
                  configuration=dict(epoch_policy=epoch_policy,reserve_zero_epoch=bool(reserved),initial_stream_epoch=seed,
                      control_hz=50000000, bus_period_ns=27.4,
                      test_accept_timeout_clocks=16, test_result_timeout_clocks=192,
                      real_switch_state_timeout_clocks=96, default_accept_timeout_clocks=32,
                      default_result_timeout_clocks=20000000, rearm_quiet_clocks=4),
                  scope='Real existing held-word CDC/predecode and real workstation_sample_rate_switch; explicit lost-response and permission/epoch fault injection',
                  limits='No new top/profile/firmware/address allocation, DCS/physical clock simulation, EDA, SRAM or hardware acceptance')
    try:
        lint = ['verilator', '--lint-only', '--top-module', 'workstation_audio_clock_service', str(sources[0])]
        result['lint_argv'] = lint
        process = subprocess.run(lint, capture_output=True, text=True, timeout=60)
        (output / 'lint.log').write_text(process.stdout + process.stderr)
        result['lint_log_sha256'] = digest(output / 'lint.log')
        result['lint_warning_count'] = (output / 'lint.log').read_text().count('%Warning-')
        if process.returncode or result['lint_warning_count']:
            raise RuntimeError('Clock service lint failed:\n' + (output / 'lint.log').read_text())
        compile_command = ['iverilog', '-g2012', '-s', 'tb_workstation_audio_clock_service',
                           '-o', str(output / 'clock_service.vvp'), *map(str, sources)]
        compile_command[1:1]=['-Ptb_workstation_audio_clock_service.RESERVE_ZERO_EPOCH='+str(reserved),
                              '-Ptb_workstation_audio_clock_service.INITIAL_STREAM_EPOCH='+str(seed)]
        result['compile_argv'] = compile_command
        process = subprocess.run(compile_command, capture_output=True, text=True, timeout=60)
        (output / 'compile.log').write_text(process.stdout + process.stderr)
        result['compile_log_sha256'] = digest(output / 'compile.log')
        if process.returncode:
            raise RuntimeError('Clock service compile failed:\n' + (output / 'compile.log').read_text())
        result['runs'] = []
        for index, phase in enumerate((3.7, 0.1, 21.9)):
            command = ['vvp', str(output / 'clock_service.vvp'), f'+BUS_PHASE={phase}']
            process = subprocess.run(command, capture_output=True, text=True, timeout=60)
            log = process.stdout + process.stderr
            log_path = output / f'run{index}.log'
            log_path.write_text(log)
            if process.returncode or 'PASS audio_clock_service:' not in log:
                raise RuntimeError('Clock service simulation failed:\n' + log)
            result['runs'].append(dict(bus_phase_ns=phase, argv=command, log=log,
                log_sha256=digest(log_path), metrics={key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)}))
            print(log, end='')
        result['inputs_unchanged_during_run'] = hashes == {key: digest(path) for key, path in paths.items()}
        assert result['inputs_unchanged_during_run'], 'Clock service input changed during verification'
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepared-project', type=Path)
    parser.add_argument('--epoch-policy',choices=('legacy','nonzero','wrap'),default='legacy')
    args = parser.parse_args()
    if args.output is not None:
        run(args.output.resolve(), args.prepared_project,args.epoch_policy)
    else:
        with tempfile.TemporaryDirectory(prefix='gw138k-clock-service-') as directory:
            run(Path(directory) / 'verification', args.prepared_project,args.epoch_policy)


if __name__ == '__main__':
    main()
