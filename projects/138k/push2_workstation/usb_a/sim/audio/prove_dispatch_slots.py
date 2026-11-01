#!/usr/bin/env python3
"""Source-bound dispatch exclusion and actual four-state ready-cone checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import z3

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch_slot_sources as slots
from prove_effect_slot_admission import equation, one, parse


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def control(text):
    return one(text, r'always_comb begin\s*(core_event_valid=0;.*?)\n  end\n  wire decoder_valid')


def source_contract():
    contract = slots.source_contract()
    event = (ROOT / 'rtl/audio/gw138k_event_workstation.sv').read_text()
    engines = (ROOT / 'rtl/audio/workstation_runtime_render_engines.sv').read_text()
    oscillator = (ROOT / 'rtl/audio/workstation_runtime_oscillator_engine.sv').read_text()
    assert '.synth_event_slot_ready_o(core_event_slot_ready),.expression_slot_ready_o(core_expression_slot_ready)' in event
    assert '.event_slot_ready_o(synth_event_slot_ready_o), .expression_slot_ready_o' in engines
    assert 'generate if(TIMING_OPTIMIZED && RUNTIME_RATE_ENABLE)begin: engine_dispatch_slots' in event
    block = one(event, r'begin: engine_dispatch_slots\s*(.*?)\s*end else begin: original_engine_dispatch_slots')
    assert 'case({mode_pending,allocated==32\'d0})' in block
    assert 'default: begin\n          core_event_dispatch_ready=core_event_ready;\n          core_expression_dispatch_ready=core_expression_ready;' in block
    assert equation(oscillator, 'event_ready_o') == 'event_slot_ready_o && !mode_set_valid_i'
    assert equation(oscillator, 'expression_ready_o') == 'expression_slot_ready_o && !event_valid_i && !mode_set_valid_i'
    for name in ('event_slot_ready_o', 'expression_slot_ready_o'):
        assert not {'mode_set_valid_i', 'event_valid_i', 'sample_ce_i'} & set(re.findall(r'\b\w+\b', equation(oscillator, name)))
    return event, engines, oscillator, contract


def binary(event, oscillator):
    def parsed(expression, values):
        return parse(expression.replace("32'd0", '0').replace("1'b1", '1'), values)
    env = {'allocated': z3.BitVec('allocated', 32), 'allocated_mask_o': z3.BitVec('allocated', 32),
           'load_state': z3.BitVec('load_state', 3), 'LOAD_IDLE': z3.BitVecVal(0, 3),
           'PIPELINED_ENVELOPE': z3.BoolVal(True), 'PIPELINED_RATE': z3.BoolVal(True),
           'TIMING_OPTIMIZED': z3.BoolVal(True)}
    env['mode_ready'] = parsed(equation(oscillator, 'mode_set_ready_o'), env)
    env['mode_valid'] = parsed(equation(event, 'mode_valid'), env)
    env['dispatch'] = parsed(equation(event, 'dispatch'), env)
    rows = []
    def prove(name, left, right, assumptions=()):
        solver = z3.Solver()
        solver.add(*assumptions, left != right)
        assert solver.check() == z3.unsat, name
        rows.append(dict(property=name, result='unsat', reachability_assumptions=[]))
    prove('dispatch excludes the actual same-edge mode commit', z3.And(env['dispatch'], env['mode_valid']), z3.BoolVal(False))
    env['mode_set_valid_i'] = env['mode_valid']
    env['event_slot_ready_o'] = parsed(equation(oscillator, 'event_slot_ready_o'), env)
    ready = parsed(equation(oscillator, 'event_ready_o'), env)
    prove('dispatch AND public Note ready equals dispatch AND stored slot',
          z3.And(env['dispatch'], ready), z3.And(env['dispatch'], env['event_slot_ready_o']))
    # The actual procedural owner sets Note-valid only in its release or Note
    # branches, and a kind-5 expression enters neither branch.
    actual = [re.sub(r'\s+', '', x) for x in re.findall(r'\bcore_event_valid\s*=\s*(.*?);', control(event))]
    assert actual == ['0', 'dispatch&&deferred_current', 'dispatch&&!(kind==1&&full)']
    env['event_valid_i'] = z3.BoolVal(False)
    env['expression_slot_ready_o'] = parsed(equation(oscillator, 'expression_slot_ready_o'), env)
    ready = parsed(equation(oscillator, 'expression_ready_o'), env)
    prove('kind-5 non-release dispatch AND public expression ready equals stored slot',
          z3.And(env['dispatch'], ready), z3.And(env['dispatch'], env['expression_slot_ready_o']))
    return rows


INPUTS = ('usb_lifecycle pending runtime_config_busy sample_ce_i event_config_block native_clear '
          'load_busy mix_busy vec_busy mode_pending envelope_lane_busy quiescent_o allocation_found '
          'event_valid releasing deferred_current scope_enable vec_dispatch_ready sustain full').split()


def slice_module(name, event, oscillator, current):
    ports = ','.join(INPUTS) + ',allocated,load_state,kind,a,b,tf_scope_control_o,result'
    text = 'module ' + name + '(' + ports + ');\ninput ' + ','.join(INPUTS) + ';\n'
    text += 'input [31:0] allocated,tf_scope_control_o;input [2:0] load_state;input [3:0] kind;input [6:0] a,b;output [5:0] result;\n'
    text += 'localparam TIMING_OPTIMIZED=1,RUNTIME_RATE_ENABLE=1,PIPELINED_ENVELOPE=1,PIPELINED_RATE=1,LOAD_IDLE=0;\n'
    text += 'wire [31:0] allocated_mask_o=allocated;wire mix_busy_o=mix_busy;wire mode_ready,mode_valid,dispatch;\n'
    text += 'logic core_event_valid,core_note_on,core_expression_valid,event_ready;logic [6:0] core_note,core_velocity,core_expression_note,core_expression_value;\n'
    text += "wire [6:0] release_index=7'd0;\n"
    text += 'wire mode_set_valid_i=mode_valid,event_note_on_i=core_note_on,event_valid_i=core_event_valid && !scope_enable;\n'
    for name, expression in [('mode_ready', equation(oscillator, 'mode_set_ready_o')),
                             ('mode_valid', equation(event, 'mode_valid')), ('dispatch', equation(event, 'dispatch'))]:
        text += 'assign ' + name + '=' + expression + ';\n'
    if current:
        text += 'wire event_slot_ready_o=' + equation(oscillator, 'event_slot_ready_o') + ';\n'
        text += 'wire expression_slot_ready_o=' + equation(oscillator, 'expression_slot_ready_o') + ';\n'
    text += 'wire core_event_ready=' + equation(oscillator, 'event_ready_o') + ';\n'
    text += 'wire core_expression_ready=' + equation(oscillator, 'expression_ready_o') + ';\n'
    if current:
        text += 'wire core_event_slot_ready=event_slot_ready_o,core_expression_slot_ready=expression_slot_ready_o;\n'
        text += 'logic core_event_dispatch_ready,core_expression_dispatch_ready;\n'
        text += one(event, r'begin: engine_dispatch_slots\s*(.*?)\s*end else begin: original_engine_dispatch_slots').replace('always_comb', 'always @*') + '\n'
    text += 'always @* begin\n' + control(event) + '\nend\n'
    ready = 'core_event_dispatch_ready' if current else 'core_event_ready'
    text += 'wire release_advance=releasing && dispatch && (!deferred_current || (scope_enable ? vec_dispatch_ready : ' + ready + '));\n'
    text += 'assign result={event_ready,core_event_valid,core_expression_valid,dispatch,mode_valid,release_advance};\nendmodule\n'
    return text


def four_state(event, oscillator, out, label, expect_pass=True):
    old_event = slots.reference_view('rtl/audio/gw138k_event_workstation.sv')
    old_oscillator = slots.reference_view('rtl/audio/workstation_runtime_oscillator_engine.sv')
    text = slice_module('actual', event, oscillator, True) + slice_module('reference', old_event, old_oscillator, False)
    text += 'module tb;reg ' + ','.join(INPUTS) + ';reg [31:0] allocated,tf_scope_control_o;reg [2:0] load_state;reg [3:0] kind;reg [6:0] a,b;wire[5:0] got,want;\n'
    common = ','.join('.' + n + '(' + n + ')' for n in INPUTS + ['allocated', 'load_state', 'kind', 'a', 'b', 'tf_scope_control_o'])
    text += 'actual dut(' + common + ',.result(got));reference refdut(' + common + ',.result(want));\n'
    text += '''integer checks=0,k;reg [31:0] rng=32'h4d24c051;
function automatic random4();begin rng=(rng>>1)^((rng&1)?32'h80200003:0);case(rng[1:0]) 0:random4=0;1:random4=1;2:random4=1'bx;3:random4=1'bz;endcase end endfunction
function automatic digit4(input integer code);begin case(code&3) 0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase end endfunction
task check;begin #1;if(got!==want)$fatal(1,"dispatch four-state mismatch vector=%0d got=%b want=%b mode=%b alloc=%h",checks,got,want,mode_pending,allocated);checks=checks+1;end endtask
initial begin
'''
    randomize = ''.join(n + '=random4();' for n in INPUTS)
    randomize += 'allocated={random4(),rng[30:0]};tf_scope_control_o=rng;load_state={random4(),random4(),random4()};kind=rng[3:0];a=rng[6:0];b=rng[13:7];\n'
    text += 'for(k=0;k<16384;k=k+1)begin\n' + randomize
    text += 'mode_pending=digit4(k);allocated=(k&4)?32\'d0:32\'d1;allocated[0]=digit4(k>>2);sample_ce_i=digit4(k>>4);pending=digit4(k>>6);load_state={2\'d0,digit4(k>>8)};event_valid=digit4(k>>10);releasing=digit4(k>>12);kind=(k&1)?4\'d5:4\'d1;check();end\n'
    # Also concentrate on executable Note/Off/expression states, which cannot
    # be covered well by independent unknown values on every outer veto.
    text += 'for(k=0;k<131072;k=k+1)begin\n' + randomize
    text += "if(k<65536)begin usb_lifecycle=0;pending=0;runtime_config_busy=0;sample_ce_i=0;event_config_block=0;native_clear=0;load_busy=0;mix_busy=0;vec_busy=0;mode_pending=0;load_state=0;quiescent_o=1;envelope_lane_busy=0;kind=(k%3==0)?0:(k%3==1)?1:5;end check();end\n"
    text += '$display("PASS dispatch slots four-state vectors=%0d",checks);$finish;end\nendmodule\n'
    source, executable = out / (label + '.sv'), out / label
    source.write_text(text)
    compiled = subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(executable), str(source)], capture_output=True, text=True, timeout=60)
    (out / (label + '-compile.log')).write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    run = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=60)
    (out / (label + '.log')).write_text(run.stdout + run.stderr)
    assert (run.returncode == 0) == expect_pass, label + ': ' + run.stdout + run.stderr
    return dict(returncode=run.returncode, actual_extracted_source_executed=True, expected_result=True, vectors=147456 if expect_pass else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    event, engines, oscillator, contract = source_contract()
    inputs = slots.contract_inputs() + [Path(__file__).resolve(), ROOT / 'sim/audio/prove_effect_slot_admission.py']
    before = {str(p): sha(p) for p in inputs}
    result = dict(schema=1, passed=False, source_contract=contract, binary=binary(event, oscillator), source_sha256=before,
                  scope='Exact source inverse, binary exclusion proof and executed actual ready/control expressions including X/Z; complete sequential modules tested separately',
                  hardware_tested=False, physical_timing_verified=False)
    try:
        result['four_state'] = four_state(event, oscillator, out, 'positive')
        result['negative_controls'] = []
        for name, ev, osc in [
            ('missing_allocation', event, oscillator.replace('(event_note_on_i ? allocation_found : 1\'b1)', '1\'b1')),
            ('missing_envelope_busy', event, oscillator.replace('(!PIPELINED_ENVELOPE || !envelope_lane_busy)', "1'b1")),
            ('expression_missing_envelope_busy', event, oscillator.replace(
                'assign expression_slot_ready_o = load_state == LOAD_IDLE && !mix_busy_o &&\n      !envelope_lane_busy &&',
                'assign expression_slot_ready_o = load_state == LOAD_IDLE && !mix_busy_o &&\n      1\'b1 &&')),
        ]:
            assert ev != event or osc != oscillator
            result['negative_controls'].append(dict(name=name, run=four_state(ev, osc, out, name, False)))
        fallback_mutant = event.replace('core_event_dispatch_ready=core_event_ready;', 'core_event_dispatch_ready=core_event_slot_ready;')
        try:
            slots.reference_view('rtl/audio/gw138k_event_workstation.sv', fallback_mutant)
        except AssertionError:
            result['unknown_fallback_source_drift_rejected'] = True
        else:
            raise AssertionError('unknown fallback source shape drift escaped')
        assert all(sha(p) == value for p, value in before.items()), 'dispatch proof input drift'
        result['all_inputs_unchanged'] = True
        result['passed'] = True
        print('PASS source-bound dispatch slots: 3 binary proofs, 147456 X/Z vectors, 3 rejected mutants')
    finally:
        result['logs_sha256'] = {p.name: sha(p) for p in out.glob('*.log')}
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
