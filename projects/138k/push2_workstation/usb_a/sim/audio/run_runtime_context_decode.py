#!/usr/bin/env python3
"""Inductive transition comparison of the actual runtime context FSM blocks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SHA = 'd4f7f9dea281f7eda8861757793ec023953c2d0e2937e11034c7a665cfde8de4'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/workstation/workstation_runtime_audio.sv'
    fixture = Path(__file__).with_name('fixtures') / 'workstation_context_pre_decode.sv'
    tb = Path(__file__).with_name('tb_runtime_context_decode.sv')
    inputs = [source, fixture, tb, Path(__file__).resolve()]
    before = {str(x): sha(x) for x in inputs}
    assert sha(fixture) == FIXTURE_SHA
    text = source.read_text()
    start = '    localparam [2:0] CFG_IDLE='
    end = '    // Stream ingress and source policy'
    assert text.count(start) == text.count(end) == 1
    current = text[text.index(start):text.index(end)]
    header = '''(input compute_clk_i,compute_reset_n,context_toggle,
        input [32:0] context_payload,
        input service_fault,pcm_hard_fault,router_quiet,service_quiet,bridge_busy,
              config_ready,config_applied,service_rate);
        reg [1:0] context_sync;
        reg context_ack,integration_fault;
    '''
    reference = 'module reference_context' + header + fixture.read_text() + '\nendmodule\n'
    variants = [('current', current, False)]
    for name, old, new in (
        ('missing_accept_set', 'config_state<=CFG_ACCEPT;config_accept_pending<=1;',
         'config_state<=CFG_ACCEPT;config_accept_pending<=0;'),
        ('missing_accept_clear', 'config_state<=CFG_ACK;config_accept_pending<=0;',
         'config_state<=CFG_ACK;config_accept_pending<=1;'),
        ('missing_service_fault_veto', 'config_accept_pending && !service_fault && !pcm_hard_fault',
         'config_accept_pending && !pcm_hard_fault')):
        assert current.count(old) == 1
        variants.append((name, current.replace(old, new), True))
    result = dict(passed=False, scope='actual context FSM transition equivalence',
                  reset_and_induction_precondition='config_accept_pending == (config_state == CFG_ACCEPT)',
                  input_sha256=before, runs=[], routed_timing_verified=False, hardware_tested=False)
    try:
        for name, block, negative in variants:
            rtl = out / (name + '.sv')
            rtl.write_text('module current_context' + header + block + '\nendmodule\n' + reference)
            binary = out / (name + '.vvp')
            command = ['iverilog', '-g2012', '-s', 'tb_runtime_context_decode', '-o', str(binary), str(rtl), str(tb)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (out / (name + '_compile.log')).write_text(compiled.stdout + compiled.stderr)
            compiled.check_returncode()
            run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
            log = run.stdout + run.stderr
            (out / (name + '.log')).write_text(log)
            passed = (run.returncode != 0 and 'context decode differs' in log) if negative else (
                run.returncode == 0 and 'PASS actual context decode' in log)
            result['runs'].append(dict(name=name, negative_control=negative, passed=passed,
                exit_code=run.returncode, output=log.strip(), extracted_rtl_sha256=sha(rtl)))
            if not passed:
                raise ValueError(name + ': ' + log)
            print(log.strip())
        assert before == {str(x): sha(x) for x in inputs}
        result.update(passed=True, inputs_unchanged=True)
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
