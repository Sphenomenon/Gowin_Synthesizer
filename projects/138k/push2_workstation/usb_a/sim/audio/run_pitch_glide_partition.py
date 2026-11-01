#!/usr/bin/env python3
"""Actual whole-module four-state comparison for the local glide partition."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'rtl/audio/workstation_rate_pitch_expression.sv'
PARENT = ROOT / 'sim/audio/fixtures/workstation_rate_pitch_expression_before_glide_partition.sv'
TB = ROOT / 'sim/audio/tb_pitch_glide_partition.sv'
PARENT_SHA = '8d69922207e47c009c2340e18cd3704c0f433ed485338e8e03fe0fde2a30e8ef'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same_clocked_source(source, parent):
    if sha(parent.encode()) != PARENT_SHA:
        raise ValueError('pitch original fixture identity changed')
    before = '    // 160*s+r ='
    after = '    // Divide13*s+r by147'
    end = '    // Carry the fractional increment,'
    for text, anchor in ((parent, before), (source, after)):
        if text.count(anchor) != 1 or text.count(end) != 1:
            raise ValueError('pitch local block anchor changed')
    if (parent[:parent.index(before)] != source[:source.index(after)] or
            parent[parent.index(end):] != source[source.index(end):]):
        raise ValueError('pitch source outside combinational block changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source, parent = SOURCE.read_text(), PARENT.read_text()
    same_clocked_source(source, parent)
    inputs = {str(p): sha(p.read_bytes()) for p in (SOURCE, PARENT, TB, Path(__file__))}
    report = dict(schema=1, passed=False, input_sha256=inputs,
                  original_clocked_bytes_unchanged=True, added_clock_cycles=0,
                  actual_four_state_cases=294912, half_edges=160000,
                  hardware_tested=False, synthesis_or_routed_timing_tested=False, runs={})
    reference = out / 'reference.sv'
    reference.write_text(parent.replace('module workstation_rate_pitch_expression (',
                                        'module reference_pitch ('))
    try:
        for name, payload in (
                ('production', source),
                ('unknown_digit_zero_mutant', source.replace("default:divided_digit=21'bx;",
                                                             "default:divided_digit=21'b0;"))):
            if name != 'production' and payload == source:
                raise ValueError('pitch unknown negative anchor changed')
            folder = out / name
            folder.mkdir()
            native = folder / SOURCE.name
            native.write_text(payload)
            binary = folder / 'test.vvp'
            command = ['iverilog', '-g2012', '-s', 'tb_pitch_partition', '-o', str(binary),
                       str(native), str(reference), str(TB)]
            compile_result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            (folder / 'compile.log').write_text(compile_result.stdout + compile_result.stderr)
            if compile_result.returncode:
                raise ValueError('pitch four-state compilation failed: ' + name)
            run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=60)
            text = run.stdout + run.stderr
            (folder / 'run.log').write_text(text)
            if name == 'production':
                if run.returncode or 'PASS actual_pitch_partition four_state=294912 half_edges=160000' not in text:
                    raise ValueError('pitch actual module comparison failed: ' + text)
            elif not run.returncode or 'PITCH_FOUR_STATE' not in text:
                raise ValueError('pitch unknown control was not rejected for its arithmetic behavior')
            report['runs'][name] = dict(returncode=run.returncode, compile_argv=command,
                                       source_sha256=sha(payload.encode()),
                                       log_sha256=sha(text.encode()),
                                       expected_failure=name != 'production')
        for name, current, original in (
                ('parent_tamper', source, parent + '\n'),
                ('clocked_reset_tamper', source.replace('phase <= phase +', 'phase <= phase -'), parent)):
            try:
                same_clocked_source(current, original)
            except ValueError as error:
                report['runs'][name] = dict(rejected=True, reason=str(error))
            else:
                raise ValueError('pitch source preservation negative was accepted: ' + name)
        if inputs != {p: sha(Path(p).read_bytes()) for p in inputs}:
            raise ValueError('pitch verification inputs changed during run')
        report['inputs_unchanged_during_run'] = True
        report['passed'] = True
        print('PASS actual pitch: 294912 four-state cases, 160000 half-edges, 3 negatives rejected')
    finally:
        (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
