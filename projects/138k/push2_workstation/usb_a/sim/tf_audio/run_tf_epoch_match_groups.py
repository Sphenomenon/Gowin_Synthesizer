#!/usr/bin/env python3
"""Actual TF owner four-state checks for the same-edge epoch comparison.

Use the existing TF fixture preparation's explicit compile list. No synthesis,
physical gain, CDC acceptance or hardware claim follows from this regression.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import z3

from run_tf_failure_factor_equivalence import ROOT, SOURCE, TB, twin_bench
from tf_epoch_match_sources import before_epoch_groups, with_epoch_groups


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('TF epoch groups: ' + message)


def symbolic():
    ak, av, bk, bv = z3.BitVecs('a_known a_value b_known b_value', 32)
    known, mismatch = ak & bk, (av ^ bv) & ak & bk
    direct_one = mismatch != 0
    direct_known = z3.Or(direct_one, known == 0xffffffff)
    groups = []
    for bit in range(0, 32, 8):
        one = z3.Extract(bit + 7, bit, mismatch) != 0
        groups.append((z3.Or(one, z3.Extract(bit + 7, bit, known) == 255), one))
    grouped_one = z3.Or([one for _, one in groups])
    grouped_known = z3.Or(grouped_one, z3.And([known for known, _ in groups]))
    solver = z3.Solver()
    solver.add(z3.Or(direct_one != grouped_one, direct_known != grouped_known))
    require(solver.check() == z3.unsat, 'arbitrary four-state grouped reduction')
    return dict(result='UNSAT', independent_input_bits=128, reachability_assumptions=[],
                scope='Hand-lifted known/value reduction relation, bound to the exact source inverse; not full SV temporal proof')


def bench():
    text, inventory = twin_bench()
    body = r'''
    reg [31:0] stored_epoch, live_epoch;
    integer vector_code, bit_at, digit_code, checks=0;
    function digit4(input integer number);case(number&3)
      0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;
    endcase endfunction
    task epoch_check;begin
      runtime_epoch=live_epoch;#1;
      if(dut.epoch_mismatch !== (|(live_epoch ^ stored_epoch)) ||
         dut.epoch_mismatch !== reference.epoch_mismatch ||
         dut.error_now !== reference.error_now ||
         dut.new_failure !== reference.new_failure ||
         dut.invalidate !== reference.invalidate ||
         dut.playback_accept !== reference.playback_accept ||
         dut.analysis_accept !== reference.analysis_accept)
        $fatal(1,"TF EPOCH actual owner four-state check=%0d",checks);
      checks=checks+1;
    end endtask
    initial if(!RUN_SCENARIOS)begin
      #1;source_run=0;compute_run=0;memory_run=0;
FORCES
      runtime_valid=1;runtime_fault=0;runtime_busy=0;runtime_rate=0;
      mode=1;run=1;restart=0;stop_request=0;cancel=0;transport_error=0;
      for(vector_code=0;vector_code<65536;vector_code=vector_code+1)begin
        stored_epoch=0;live_epoch=0;
        stored_epoch[0]=digit4(vector_code);stored_epoch[7]=digit4(vector_code>>2);
        stored_epoch[8]=digit4(vector_code>>4);stored_epoch[31]=digit4(vector_code>>6);
        live_epoch[0]=digit4(vector_code>>8);live_epoch[7]=digit4(vector_code>>10);
        live_epoch[8]=digit4(vector_code>>12);live_epoch[31]=digit4(vector_code>>14);
        epoch_check();
      end
      for(bit_at=0;bit_at<32;bit_at=bit_at+1)for(digit_code=0;digit_code<16;digit_code=digit_code+1)begin
        stored_epoch=32'h5a6c39e1;live_epoch=stored_epoch;
        stored_epoch[bit_at]=digit4(digit_code);live_epoch[bit_at]=digit4(digit_code>>2);
        epoch_check();live_epoch[(bit_at+1)%32]=~stored_epoch[(bit_at+1)%32];epoch_check();
      end
      $display("PASS TF EPOCH actual owner four-state checks=%0d immediate_controls=7",checks);$finish;
    end
'''
    forces = dict(state="3'd3", launched_epoch='stored_epoch', launched_rate="1'b0",
                  memory_ready_sync="2'b11", card_lost_o="1'b0", ddr_error_o="1'b0",
                  unsupported_o="1'b0", format_ready_o="1'b0", stop_latched="1'b0",
                  stop_request_q="1'b0", stop_pending_o="1'b0", track_q="4'd0", mode_q="1'b1",
                  restart_q="1'b0", cancel_q="1'b0", reader_restart_q="1'b0")
    body = body.replace('FORCES', '\n'.join('      force '+who+'.'+name+'='+value+';'
                         for who in ('dut', 'reference') for name, value in forces.items()))
    position = text.rfind('endmodule')
    return text[:position] + body + text[position:], inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = SOURCE.read_text()
    reference = before_epoch_groups(source)
    require(with_epoch_groups(reference) == source, 'exact source round trip')
    edge = '    always @(posedge clk_50m_i or negedge source_reset_n)'
    require(source.split(edge, 1)[1] == reference.split(edge, 1)[1], 'all sequential bytes unchanged')
    meta = json.loads((args.fixtures / 'verification.json').read_text())
    argv = meta['compile_argv']
    sources = argv[argv.index('-o')+2:]
    inputs = [Path(p) for p in sources] + [Path(__file__), Path(__file__).with_name('tf_epoch_match_sources.py'),
                                         Path(__file__).with_name('run_tf_failure_factor_equivalence.py')]
    before = {str(p): sha(p) for p in inputs}
    text, inventory = bench()
    (out/'bench.sv').write_text(text)
    (out/'reference.sv').write_text(reference.replace('module workstation_tf_runtime_service #(',
                                                    'module workstation_tf_runtime_service_reference #(', 1))
    controls = {}
    for label, wrong in [('extra_bytes', source+'// unreviewed\n'),
                         ('keep_removed', source.replace('(* syn_keep=1 *)', '(* syn_keep=0 *)', 1))]:
        try:
            before_epoch_groups(wrong)
        except ValueError:
            controls[label] = True
        else:
            require(False, 'source drift accepted ' + label)
    mutations = {
        'high_byte_omitted': ('wire epoch_mismatch=|epoch_mismatch_groups;', 'wire epoch_mismatch=|epoch_mismatch_groups[2:0];'),
        'wrong_byte': ('launched_epoch[epoch_group*8+:8]', 'launched_epoch[((epoch_group+1)%4)*8+:8]'),
        'xor_reduction': ('wire epoch_mismatch=|epoch_mismatch_groups;', 'wire epoch_mismatch=^epoch_mismatch_groups;'),
        'unknown_collapsed': ('|(runtime_epoch_i[epoch_group*8+:8] ^ launched_epoch[epoch_group*8+:8])',
                              '(runtime_epoch_i[epoch_group*8+:8] !== launched_epoch[epoch_group*8+:8])'),
    }
    runs = {}
    for label in ['baseline', *mutations]:
        candidate = source
        if label != 'baseline':
            old, new = mutations[label]
            require(candidate.count(old) == 1, 'mutant anchor ' + label)
            candidate = candidate.replace(old, new, 1)
        path = out/(label+'.sv');path.write_text(candidate)
        selected = [str(path) if p == str(SOURCE) else str(out/'bench.sv') if p == str(TB) else p for p in sources]
        command = ['iverilog', '-g2012', '-I', str(args.fixtures), '-s', 'tb_workstation_tf_runtime_service',
                   '-Ptb_workstation_tf_runtime_service.RUN_SCENARIOS=0', '-o', str(out/(label+'.vvp')),
                   *selected, str(out/'reference.sv')]
        compiled = subprocess.run(command, cwd=args.fixtures, capture_output=True, text=True, timeout=90)
        (out/(label+'-compile.log')).write_text(compiled.stdout+compiled.stderr)
        require(compiled.returncode == 0, 'compile ' + label + ': ' + compiled.stderr[-1200:])
        ran = subprocess.run(['vvp', str(out/(label+'.vvp'))], cwd=args.fixtures, capture_output=True, text=True, timeout=180)
        (out/(label+'.log')).write_text(ran.stdout+ran.stderr)
        passing = label == 'baseline'
        require((ran.returncode == 0) == passing and
                ('checks=66560' if passing else 'TF EPOCH actual owner four-state') in ran.stdout,
                'actual owner result ' + label + ': ' + ran.stdout[-1500:])
        runs[label] = dict(returncode=ran.returncode, expected_pass=passing, summary=ran.stdout)
    require(before == {str(p): sha(p) for p in inputs}, 'source drift during regression')
    report = dict(stage='maintained_TF_epoch_groups', passed=True, inputs_sha256=before,
                  exact_source_inverse=True, all_sequential_bytes_unchanged=True, symbolic=symbolic(),
                  actual_owner_inventory=inventory, actual_four_state_checks=66560, runs=runs,
                  source_controls=controls, synthesis=False, pnr=False, hardware_tested=False,
                  physical_gain_measured=False,
                  output_sha256={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=True, actual_four_state_checks=66560, mutants_rejected=4,
                         source_controls_rejected=2, verification_sha256=sha(out/'verification.json'))))


if __name__ == '__main__':
    main()
