#!/usr/bin/env python3
"""Verify one-time runtime memory startup and permanent fault isolation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/memory/workstation_runtime_memory_guard.sv'
    tb = Path(__file__).with_name('tb_workstation_runtime_memory_guard.sv')
    inputs = [source, tb, Path(__file__).resolve()]
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in inputs}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, synthesis_tested=False,
        identity='runtime-memory-guard-offline-v1-' + identity[:16], source_set_sha256=identity,
        input_sha256=hashes, input_paths={str(path.relative_to(ROOT)): str(path) for path in inputs},
        configuration=dict(reference_hz=50000000, memory_hz=100000000, memory_phase_ns=7,
            fast_timeout_cycles=12, fast_heartbeat_bits=4, default_timeout_cycles=500,
            default_heartbeat_bits=32, maximum_digital_loss_reference_cycles=505),
        limits='RTL primitive and a common transaction-gate boundary model only; no real DDR queues, DSP preservation, physical CDC/timing, synthesis, or hardware acceptance')
    try:
        lint = ['verilator', '--lint-only', '--top-module', 'workstation_runtime_memory_guard', str(source)]
        result['lint_argv'] = lint
        process = subprocess.run(lint, capture_output=True, text=True, timeout=60)
        (output / 'lint.log').write_text(process.stdout + process.stderr)
        assert process.returncode == 0 and '%Warning-' not in (output / 'lint.log').read_text(), (output / 'lint.log').read_text()
        result['lint_warning_count'] = 0
        command = ['verilator', '--binary', '--timing', '-j', '3', '--top-module',
            'tb_workstation_runtime_memory_guard', '--Mdir', str(output / 'obj'), str(source), str(tb)]
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
        result['compile_warning_counts'] = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'compile.log').read_text(), re.M):
            result['compile_warning_counts'][name] = result['compile_warning_counts'].get(name, 0) + 1
        assert not result['compile_warning_counts'], 'New guard/TB warning'
        command = [str(output / 'obj/Vtb_workstation_runtime_memory_guard')]
        result['simulation_argv'] = command
        with (output / 'simulation.log').open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        log = (output / 'simulation.log').read_text()
        assert 'PASS runtime_memory_guard:' in log, log
        result['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)}
        result['log'] = log
        result['log_sha256'] = digest(output / 'simulation.log')
        result['compile_log_sha256'] = digest(output / 'compile.log')
        # An event simulator independently exercises the between-edge reset
        # pulses and asynchronous closure, without a generated cycle model.
        command = ['iverilog', '-g2012', '-s', 'tb_workstation_runtime_memory_guard',
            '-o', str(output / 'simulation.vvp'), str(source), str(tb)]
        result['event_compile_argv'] = command
        with (output / 'event_compile.log').open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        assert not (output / 'event_compile.log').read_text().strip(), 'Event simulator compilation diagnostic'
        command = ['vvp', str(output / 'simulation.vvp')]
        result['event_simulation_argv'] = command
        with (output / 'event_simulation.log').open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        event_log = (output / 'event_simulation.log').read_text()
        assert 'PASS runtime_memory_guard:' in event_log, event_log
        result['event_metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', event_log)}
        assert result['metrics'] == result['event_metrics'], 'Independent simulator metrics differ'
        result['event_log'] = event_log
        result['event_log_sha256'] = digest(output / 'event_simulation.log')
        result['inputs_unchanged_during_run'] = hashes == {str(path.relative_to(ROOT)): digest(path) for path in inputs}
        assert result['inputs_unchanged_during_run'], 'Guard inputs changed during verification'
        result['passed'] = True
        print(log, end='')
        print(event_log, end='')
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
