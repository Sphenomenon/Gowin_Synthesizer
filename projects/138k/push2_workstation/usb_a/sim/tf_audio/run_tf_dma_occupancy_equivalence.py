#!/usr/bin/env python3
"""Compare maintained occupancy state against the pinned pre-change DMA."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from test_cnn_tf_write_buffer_retime import stalled_tb, zero_response_tb
OLD_SHA = 'bc1dcfad79af5777c27d7bfa65ae3b397ce103ca0a992b938027201877119752'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/tf_audio/workstation_tf_runtime_dma.sv'
    old = Path(__file__).with_name('fixtures') / 'workstation_tf_runtime_dma_pre_occupancy.sv'
    tb = Path(__file__).with_name('tb_tf_dma_occupancy_equivalence.sv')
    header = ROOT / 'rtl/ddr_address_map.vh'
    ring_oracle = Path(__file__).with_name('tb_tf_audio_ddr_dma.sv')
    inputs = [source, old, tb, header, Path(__file__).resolve(), ring_oracle,
              ROOT / 'tools/test_cnn_tf_write_buffer_retime.py']
    before = {str(p): sha(p) for p in inputs}
    result = dict(passed=False, input_sha256=before, hardware_tested=False,
                  routed_timing_verified=False, deployment_allowed=False, runs=[])
    try:
        if sha(old) != OLD_SHA:
            raise ValueError('pinned old DMA bytes changed')
        anchor = 'module workstation_tf_runtime_dma #('
        text = old.read_text()
        if text.count(anchor) != 1:
            raise ValueError('reference module identity drift')
        reference = out / 'reference.sv'
        reference.write_text(text.replace(anchor, 'module reference_workstation_tf_runtime_dma #('))
        include = out / 'src/memory'
        include.mkdir(parents=True)
        (include / header.name).write_bytes(header.read_bytes())
        mutant = out / 'mutant.sv'
        changed = "wire [6:0] accepted_delta = {6'd0, input_byte_accepted} -"
        if source.read_text().count(changed) != 1:
            raise ValueError('negative-control anchor drift')
        mutant.write_text(source.read_text().replace(changed, "wire [6:0] accepted_delta = 7'd0 -"))
        unsigned = out / 'unsigned_delta.sv'
        changed = 'upper = low_sum[6] ? occupancy[31:6] : upper_minus;'
        if source.read_text().count(changed) != 1:
            raise ValueError('signed-delta negative-control anchor drift')
        unsigned.write_text(source.read_text().replace(changed,
            'upper = low_sum[6] ? upper_plus : occupancy[31:6];'))
        carry = out / 'lost_carry.sv'
        changed = 'upper = low_sum[6] ? upper_plus : occupancy[31:6];'
        if source.read_text().count(changed) != 1:
            raise ValueError('small-delta carry negative-control anchor drift')
        carry.write_text(source.read_text().replace(changed,
            'upper = occupancy[31:6];'))
        simultaneous = out / 'simultaneous.sv'
        changed = "{1'b0, (write_accept ? pending_bytes : 6'd0)}"
        if source.read_text().count(changed) != 1:
            raise ValueError('simultaneous negative-control anchor drift')
        simultaneous.write_text(source.read_text().replace(changed,
            "{1'b0, ((write_accept && !read_response) ? pending_bytes : 6'd0)}"))
        for label, path, bank, negative in [('scaled', source, 64, False),
                                             ('hardware_capacity', source, 67108864, False),
                                             ('drop_input_count', mutant, 64, True),
                                             ('unsigned_delta', unsigned, 64, True),
                                             ('lost_upper_carry', carry, 64, True),
                                             ('simultaneous_write_lost', simultaneous, 64, True)]:
            binary = out / (label + '.vvp')
            command = ['iverilog', '-g2012', '-I', str(out), '-s', 'tb_tf_dma_occupancy_equivalence',
                       '-Ptb_tf_dma_occupancy_equivalence.BANK_BYTES=' + str(bank),
                       '-o', str(binary), str(path), str(reference), str(tb)]
            compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (out / (label + '_compile.log')).write_text(compile_result.stdout + compile_result.stderr)
            compile_result.check_returncode()
            run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
            log = run.stdout + run.stderr
            (out / (label + '.log')).write_text(log)
            if negative:
                accepted = run.returncode != 0 and (
                    'occupancy invariant differs' in log or 'small-delta arithmetic differs' in log)
            else:
                accepted = run.returncode == 0 and 'PASS DMA occupancy:' in log
            result['runs'].append(dict(label=label, command=command, exit_code=run.returncode,
                                       passed=accepted, output=log.strip(), negative_control=negative))
            if not accepted:
                raise ValueError(label + ' failed: ' + log)
            print(log.strip())
        # Independent byte/ring oracle: full, partial and empty files, wrap,
        # output backpressure, native stalls, immediate and delayed returns.
        # The native-only hold interface is tied low for this existing oracle.
        ring_text = '`timescale 1ns/1ps\n' + ring_oracle.read_text()
        ring_text = re.sub(r'\btf_audio_ddr_dma\b', 'workstation_tf_runtime_dma', ring_text)
        anchor = ".mem_ready(1'b1)"
        if ring_text.count(anchor) != 2:
            raise ValueError('ring oracle native hold binding drift')
        ring_text = ring_text.replace(anchor,
            anchor + ",.runtime_hold_i(1'b0),.runtime_restart_ack_o()")
        for stall in (False, True):
            for zero in (False, True):
                label = 'ring_stall' + str(int(stall)) + '_zero' + str(int(zero))
                text = zero_response_tb(ring_text, stall) if zero else (
                    stalled_tb(ring_text) if stall else ring_text)
                path = out / (label + '.sv')
                path.write_text(text)
                binary = out / (label + '.vvp')
                command = ['iverilog', '-g2012', '-I', str(out), '-s', 'tb_tf_audio_ddr_dma',
                           '-o', str(binary), str(source), str(path)]
                compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
                (out / (label + '_compile.log')).write_text(compiled.stdout + compiled.stderr)
                compiled.check_returncode()
                run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
                log = run.stdout + run.stderr
                (out / (label + '.log')).write_text(log)
                passed = run.returncode == 0 and 'PASS tb_tf_audio_ddr_dma:' in log
                result['runs'].append(dict(label=label, command=command, exit_code=run.returncode,
                                           passed=passed, output=log.strip(), independent_ring_oracle=True))
                if not passed:
                    raise ValueError(label + ' failed: ' + log)
                print(label, log.strip())
        if before != {str(p): sha(p) for p in inputs}:
            raise ValueError('DMA equivalence inputs changed')
        result.update(passed=True, inputs_unchanged=True)
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
