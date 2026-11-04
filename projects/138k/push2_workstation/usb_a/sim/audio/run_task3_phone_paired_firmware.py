#!/usr/bin/env python3
"""Verify paired-v3 actual C and runtime against a checked model, not RTL."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    builder = ROOT / 'sim/audio/run_task3_phone_firmware_workload.py'
    smoke = ROOT / 'sim/fixtures/task3_phone_firmware_paired_smoke.c'
    inputs = {str(p): sha(p) for p in (builder, smoke, Path(__file__).resolve())}
    report = dict(schema='task3-paired-phone-real-firmware-v1', passed=False,
                  inputs=inputs, commands=[], hardware_tested=False,
                  native_RTL_verified=False, CPU_cycles_measured=False,
                  production_capability_bit3=False)
    try:
        spec = importlib.util.spec_from_file_location('task3_firmware_builder', builder)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.build_library(output / 'firmware', run_smoke=True)
        receipt_path = output / 'firmware/verification.json'
        receipt = json.loads(receipt_path.read_text())
        report['firmware_receipt'] = dict(path=str(receipt_path), sha256=sha(receipt_path))
        old_smoke = str(ROOT / 'sim/fixtures/task3_phone_firmware_smoke.c')
        summaries = {}
        for tag in ('native', 'sanitized'):
            executable = output / tag
            argv = next(c['argv'].copy() for c in receipt['commands'] if
                        c['argv'][-1] == str(output / ('firmware/smoke-' + tag)))
            argv[argv.index(old_smoke)] = str(smoke)
            argv[argv.index('-o') + 1] = str(executable)
            # The public test API remains small; direct protocol cases also
            # include the first-party header and decoder types for inspection.
            for name, command in ((tag + '-compile', argv), (tag + '-run', [str(executable)])):
                result = subprocess.run(command, capture_output=True, text=True, timeout=120)
                log = output / (name + '.log');log.write_text(result.stdout + result.stderr)
                report['commands'].append(dict(argv=command, returncode=result.returncode,
                                                log_sha256=sha(log)))
                if result.returncode or 'Sanitizer' in result.stderr or 'runtime error:' in result.stderr:
                    raise RuntimeError(name + ': ' + result.stdout + result.stderr)
            summaries[tag] = result.stdout.strip()
        after = {p: sha(p) for p in inputs}
        if after != inputs:
            raise ValueError('paired verification inputs changed')
        for path, digest in receipt['inputs'].items():
            if sha(ROOT / path) != digest:
                raise ValueError('actual firmware input changed during paired verification: ' + path)
        report.update(passed=True, source_unchanged=True, summaries=summaries)
        print(json.dumps(summaries, indent=2))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
