#!/usr/bin/env python3
"""Source-bound NoteOff prefix proof and whole-oscillator clock equivalence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import z3

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_baselines import load_baseline
from workstation_oscillator_release_provenance import (
    SOURCE, ADAPTATION, restore_parent, source_bundle)
from workstation_oscillator_expression_provenance import restore_native, PROVENANCE, ADAPTATION as EXPRESSION
from prove_effect_slot_admission import BooleanSV, one


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('release test exact anchor drift: ' + old)
    return text.replace(old, new)


def cone(source):
    return one(source, r'(  wire \[6:0\] off_note=.*?)  logic \[4:0\] maximum_voice_index;')


def binary_proof(source):
    """Interpret the actual static group equations; compare the old priority."""
    group = one(source, r'for\(genvar release_group=0;release_group<8;release_group=release_group\+1\) begin: g_release_prefix(.*?)\n  end')
    expected_shape = '''
    assign release_group_any[release_group]=|release_matches[release_group*4+:4];
    if(release_group==0)assign release_prefix_1[release_group]=release_group_any[release_group];
    else assign release_prefix_1[release_group]=release_group_any[release_group] || release_group_any[release_group-1];
    if(release_group<2)assign release_prefix_2[release_group]=release_prefix_1[release_group];
    else assign release_prefix_2[release_group]=release_prefix_1[release_group] || release_prefix_1[release_group-2];
    if(release_group<4)assign release_prefix_4[release_group]=release_prefix_2[release_group];
    else assign release_prefix_4[release_group]=release_prefix_2[release_group] || release_prefix_2[release_group-4];'''
    # Branch/iteration structure is fixed; RHS expressions below are read
    # from the actual source and may differ in the destructive controls.
    shape = lambda text: re.sub(r'=([^;]*);', '=RHS;', re.sub(r'\s+', '', text))
    if shape(group) != shape(expected_shape):
        raise ValueError('release static prefix structure drift')
    assignments = re.findall(r'assign (release_\w+)\[release_group\]=(.*?);', group)
    if [n for n, _ in assignments] != ['release_group_any', 'release_prefix_1', 'release_prefix_1',
                                      'release_prefix_2', 'release_prefix_2', 'release_prefix_4', 'release_prefix_4']:
        raise ValueError('release assignment inventory drift')
    matches = [z3.Bool('match' + str(i)) for i in range(32)]
    values = {}
    def evaluate(expression, g):
        def reduction(m):
            start, width = int(m[1]) * 4, 4
            name = 'reduction_' + str(start)
            env[name] = z3.Or(*matches[start:start + width])
            return name
        env = {}
        expression = re.sub(r'\brelease_group\b', str(g), expression).replace("1'b0", '0')
        expression = re.sub(r'\|release_matches\[(\d+)\*4\+:4\]', reduction, expression)
        def indexed(m):
            index = sum(int(x) for x in re.findall(r'[+-]?\d+', m[2]))
            name = m[1] + '_' + str(index)
            env[name] = values[(m[1], index)]
            return name
        expression = re.sub(r'(release_\w+)\[([\d+\-]+)\]', indexed, expression)
        return BooleanSV(expression, env).result()
    for g in range(8):
        for name, index in [('release_group_any', 0), ('release_prefix_1', 1 if g == 0 else 2),
                            ('release_prefix_2', 3 if g < 2 else 4),
                            ('release_prefix_4', 5 if g < 4 else 6)]:
            values[(name, g)] = evaluate(assignments[index][1], g)
    selection = one(source, r'assign release_select\[ev\]=(.*?);')
    if selection != 'release_matches[ev] && !release_earlier_group && !release_earlier_local':
        raise ValueError('release selection equation drift')
    guards = one(source, r'(    if\(ev<4\)assign release_earlier_group=.*?assign release_select\[ev\]=.*?;)')
    expected_guards = '''    if(ev<4)assign release_earlier_group=1'b0;
    else assign release_earlier_group=release_prefix_4[ev/4-1];
    if(ev%4==0)assign release_earlier_local=1'b0;
    else assign release_earlier_local=|release_matches[ev-1:ev/4*4];
    assign release_select[ev]=release_matches[ev] && !release_earlier_group && !release_earlier_local;'''
    if guards != expected_guards:
        raise ValueError('release local and group boundaries drift')
    differences = []
    for i in range(32):
        earlier_group = z3.BoolVal(False) if i < 4 else values[('release_prefix_4', i // 4 - 1)]
        earlier_local = z3.Or(*matches[i // 4 * 4:i])
        actual = z3.And(matches[i], z3.Not(earlier_group), z3.Not(earlier_local))
        expected = z3.And(matches[i], z3.Not(z3.Or(*matches[:i])))
        differences.append(actual != expected)
    solver = z3.Solver(); solver.add(z3.Or(*differences)); status = str(solver.check())
    return dict(status=status, arbitrary_match_bits=32, selector_outputs=32,
                assumptions=[], counterexample=str(solver.model()) if status == 'sat' else None)


def four_state(source, parent, out, label, expect_pass=True):
    folder = out / label; folder.mkdir()
    # Both modules contain the exact maintained comparator/selection cone.
    # The reference retains the immutable prior expression/native source.
    header = '''(input logic [31:0] allocated_mask_o,
input logic [2:0] envelope_state [0:31],input logic [6:0] assigned_midi_note [0:31],
input logic [4:0] maximum_voice_index,input logic [6:0] event_off_note_i,event_midi_note_i,expression_note_i,
output wire [31:0] release_matches,release_select);
localparam [2:0] ENVELOPE_RELEASE=4,ENVELOPE_IDLE=0;
'''
    def module(name, text):
        body = cone(text).replace('wire [31:0] release_matches,release_select,expression_matches,expression_select;',
                                  'wire [31:0] expression_matches,expression_select;')
        return 'module ' + name + ' #(parameter bit SEPARATE_OFF_NOTE=0)' + header + body + '\nendmodule\n'
    fixture = module('candidate', source) + module('reference', parent) + r'''
module tb;
logic [31:0] allocated_mask_o;logic [2:0] envelope_state[0:31];logic [6:0] assigned_midi_note[0:31];
logic [4:0] maximum_voice_index;logic [6:0] event_off_note_i,event_midi_note_i,expression_note_i;
wire [31:0] dm[0:1],ds[0:1],rm[0:1],rs[0:1];
for(genvar sep=0;sep<2;sep=sep+1)begin:g
candidate #(.SEPARATE_OFF_NOTE(sep)) d(allocated_mask_o,envelope_state,assigned_midi_note,maximum_voice_index,event_off_note_i,event_midi_note_i,expression_note_i,dm[sep],ds[sep]);
reference #(.SEPARATE_OFF_NOTE(sep)) r(allocated_mask_o,envelope_state,assigned_midi_note,maximum_voice_index,event_off_note_i,event_midi_note_i,expression_note_i,rm[sep],rs[sep]);
end
integer checks=0,k,i,j,lo,hi,limit;reg [31:0] rng=32'h6c813d49;
function automatic [31:0] rand32();begin rng=(rng>>1)^((rng&1)?32'h80200003:0);rand32=rng;end endfunction
function automatic random4();begin rng=rand32();case(rng[1:0])0:random4=0;1:random4=1;2:random4=1'bx;3:random4=1'bz;endcase end endfunction
task automatic check;begin #1;for(integer s=0;s<2;s=s+1)begin
if(dm[s]!==rm[s] || ds[s]!==rs[s])$fatal(1,"RELEASE_FOUR_STATE checks=%0d sep=%0d match=%h select=%h ref=%h",checks,s,dm[s],ds[s],rs[s]);
end checks=checks+1;end endtask
task automatic reset_values;begin allocated_mask_o='1;maximum_voice_index=31;event_off_note_i=60;event_midi_note_i=71;expression_note_i=40;
for(integer v=0;v<32;v=v+1)begin envelope_state[v]=1;assigned_midi_note[v]=40;end end endtask
initial begin
// Every same-cycle duplicate pair, every inclusive maximum boundary and no-match.
for(limit=0;limit<32;limit=limit+1)for(lo=0;lo<32;lo=lo+1)for(hi=lo;hi<32;hi=hi+1)begin
reset_values();maximum_voice_index=5'(limit);assigned_midi_note[lo]=60;assigned_midi_note[hi]=60;check();
event_midi_note_i=60;event_off_note_i=71;check();
end
reset_values();check();allocated_mask_o=0;check();
// All four-state placements through each comparator and each prefix boundary.
for(i=0;i<32;i=i+1)for(j=0;j<4;j=j+1)begin
reset_values();for(k=0;k<32;k=k+1)assigned_midi_note[k]=60;
case(j)0:allocated_mask_o[i]=1'bx;1:envelope_state[i]=3'bz01;2:assigned_midi_note[i]=7'bx111100;3:maximum_voice_index=5'bzzzzz;endcase
check();event_midi_note_i=event_off_note_i;check();
end
for(k=0;k<16384;k=k+1)begin
for(i=0;i<32;i=i+1)begin allocated_mask_o[i]=random4();
for(j=0;j<3;j=j+1)envelope_state[i][j]=random4();
for(j=0;j<7;j=j+1)assigned_midi_note[i][j]=random4();end
for(j=0;j<5;j=j+1)maximum_voice_index[j]=random4();
for(j=0;j<7;j=j+1)begin event_off_note_i[j]=random4();event_midi_note_i[j]=random4();expression_note_i[j]=random4();end check();
end
$display("PASS release four-state checks=%0d separate_modes=2",checks);$finish;end
endmodule
'''
    sv = folder / 'fixture.sv'; sv.write_text(fixture); binary = folder / 'run.vvp'
    command = ['iverilog', '-g2012', '-s', 'tb', '-o', str(binary), str(sv)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (folder / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode: raise ValueError('release four-state compile failed: ' + compiled.stderr)
    run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=180)
    (folder / 'run.log').write_text(run.stdout + run.stderr)
    if expect_pass:
        match = re.search(r'PASS release four-state checks=(\d+) separate_modes=2', run.stdout)
        if run.returncode or not match: raise ValueError(run.stdout + run.stderr)
    elif run.returncode == 0 or 'RELEASE_FOUR_STATE' not in run.stdout:
        raise ValueError('release negative did not fail its real four-state fixture')
    return dict(exit_code=run.returncode, checks=int(match[1]) if expect_pass else None,
                actual_source_cones=True, fixture_sha256=sha(sv.read_bytes()))


def whole(source, parent, out, stage, dependencies, separate, label, expect_pass=True):
    folder = out / label; folder.mkdir()
    native = folder / 'native.sv'; native.write_text(source)
    reference = folder / 'reference.sv'
    reference.write_text(parent.replace('workstation_runtime_oscillator_engine', 'fc_reference_oscillator').replace(
        'workstation_runtime_mix_quantizer', 'fc_reference_mix_quantizer'))
    # Reuse the established per-half-clock all-state/PCM/PANIC fixture. Its
    # original bytes remain a hashed input; these exact changes vary the
    # public NoteOff input selection and add an independent release oracle.
    tb = (ROOT / 'sim/audio/tb_oscillator_expression_equivalence.sv').read_text()
    if tb.count('.SEPARATE_OFF_NOTE(1)') != 2: raise ValueError('whole fixture parameter inventory')
    tb = tb.replace('.SEPARATE_OFF_NOTE(1)', '.SEPARATE_OFF_NOTE(' + str(separate) + ')')
    tb = replace_once(tb, "      note=7'(midi);off_note=7'(midi);velocity=7'(vel);note_on=on_value;event_valid=1;",
        "      note=7'(midi+(!on_value && " + str(separate) + " ? 13 : 0));off_note=7'(midi+(on_value ? 17 : 0));velocity=7'(vel);note_on=on_value;event_valid=1;")
    tb = replace_once(tb, '    reg [31:0] expected_select;', '    reg [31:0] expected_select,expected_release;\n    reg release_seen;')
    tb = replace_once(tb, '      seen=0;expected_select=0;', '      seen=0;expected_select=0;release_seen=0;expected_release=0;')
    anchor = '      for(integer i=0;i<32;i=i+1)begin\n        if(dut.allocated_mask_o[i]'
    insertion = '''      for(integer i=0;i<32;i=i+1)begin
        if(i<=dut.maximum_voice_index && dut.allocated_mask_o[i] &&
           dut.envelope_state[i]!=4 && dut.envelope_state[i]!=0 &&
           dut.assigned_midi_note[i]==''' + ('off_note' if separate else 'note') + ''')begin
          if(!release_seen)expected_release[i]=1;
          release_seen=1;
        end
        if(dut.allocated_mask_o[i]'''
    tb = replace_once(tb, anchor, insertion)
    tb = replace_once(tb, '      if(dut.expression_select!==expected_select',
                      '      if(dut.release_select!==expected_release)$fatal(1,"RELEASE_SELECT_ORACLE");\n      if(dut.expression_select!==expected_select')
    tbpath = folder / 'tb.sv'; tbpath.write_text(tb)
    command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
               '--top-module', 'tb_oscillator_expression_equivalence', '--Mdir', str(folder / 'obj'),
               str(tbpath), str(native), str(reference), str(ROOT / 'rtl/audio/workstation_runtime_div147.sv'), *map(str, dependencies)]
    with (folder / 'compile.log').open('w') as log:
        compiled = subprocess.run(command, cwd=stage, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if compiled.returncode or '%Warning-UNOPTFLAT:' in (folder / 'compile.log').read_text():
        raise ValueError('release whole oscillator compile failed: ' + label)
    with (folder / 'run.log').open('w') as log:
        run = subprocess.run([str(folder / 'obj/Vtb_oscillator_expression_equivalence')],
                             cwd=stage, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    text = (folder / 'run.log').read_text()
    if expect_pass:
        matches = [ln for ln in text.splitlines() if ln.startswith('PASS whole_oscillator_expression:')]
        if run.returncode or len(matches) != 1: raise ValueError(text)
        metrics = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', matches[0])}
        print('SEPARATE_OFF_NOTE', separate, matches[0], flush=True)
    elif not run.returncode or 'RELEASE_SELECT_ORACLE' not in text:
        raise ValueError('release whole negative missed independent selector oracle: ' + text)
    return dict(exit_code=run.returncode, separate_off_note=separate, metrics=metrics if expect_pass else None,
                source_sha256=sha(source.encode()), tb_sha256=sha(tb.encode()), compile_argv=command)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / n for n in (SOURCE, ADAPTATION, PROVENANCE, EXPRESSION,
        'tools/workstation_oscillator_release_provenance.py', 'tools/workstation_oscillator_expression_provenance.py',
        'sim/audio/tb_oscillator_expression_equivalence.sv', 'sim/audio/prove_effect_slot_admission.py',
        'rtl/audio/workstation_runtime_div147.sv')]
    paths.append(Path(__file__).resolve()); before = {str(p): sha(p.read_bytes()) for p in paths}
    source = (ROOT / SOURCE).read_bytes(); adaptation = (ROOT / ADAPTATION).read_bytes()
    parent = restore_parent(source, adaptation)
    report = dict(schema=1,passed=False,input_sha256=before,scope='Same-clock NoteOff selection; arbitrary binary match proof, finite real-source four-state cones, whole oscillator both rates/modes/PCM/PANIC',
                  hardware_tested=False,physical_timing_verified=False,resource_gain_claimed=False,
                  provenance=source_bundle(ROOT),runs={})
    try:
        original = restore_native(source, (ROOT / PROVENANCE).read_bytes(), (ROOT / EXPRESSION).read_bytes())
        report['unchanged_original_native_sha256'] = sha(original)
        report['all_other_source_and_clocked_bytes_exact_parent'] = True
        report['binary'] = binary_proof(source.decode()); assert report['binary']['status'] == 'unsat'
        report['runs']['four_state'] = four_state(source.decode(), parent.decode(), out, 'four_state')
        mutant = replace_once(source.decode(), 'release_prefix_2[release_group-4]', "1'b0")
        report['negative_binary'] = binary_proof(mutant); assert report['negative_binary']['status'] == 'sat'
        report['runs']['four_state_missing_low_group'] = four_state(mutant, parent.decode(), out, 'four_state_missing_low_group', False)
        baseline = load_baseline(ROOT, 'resource_rework_route0'); meta = json.loads((ROOT / PROVENANCE).read_bytes())
        stage = out / 'dependencies'; stage.mkdir(); dependencies = []; report['dependency_sha256'] = {}
        for name, identity in meta['test_dependencies'].items():
            data = baseline.read_bytes(name)
            if sha(data) != identity['baseline_sha256']: raise ValueError('release baseline dependency drift')
            if 'prepared_exact_edit' in identity:
                edit = identity['prepared_exact_edit']; data = replace_once(data.decode(), edit['before'], edit['after']).encode()
                if sha(data) != identity['prepared_sha256']: raise ValueError('release prepared dependency drift')
            target = stage / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            report['dependency_sha256'][name] = sha(data)
            if target.suffix == '.sv': dependencies.append(target)
        dependencies.sort(key=lambda p: (not p.name.endswith('_pkg.sv'), str(p)))
        for separate in (0, 1):
            report['runs']['whole_' + str(separate)] = whole(source.decode(), parent.decode(), out, stage, dependencies, separate, 'whole_' + str(separate))
        report['runs']['whole_missing_low_group'] = whole(mutant, parent.decode(), out, stage, dependencies, 1, 'whole_missing_low_group', False)
        controls = []
        for label, payload, bridge in [
            ('source_extra_byte', source+b'\n', adaptation),
            ('adaptation_extra_byte', source, adaptation+b' '),
            ('clocked_source_tamper', replace_once(source.decode(), "envelope_state[ev]<=ENVELOPE_RELEASE;", "envelope_state[ev]<=ENVELOPE_IDLE;").encode(), adaptation),
            ('selector_source_tamper', mutant.encode(), adaptation)]:
            try: restore_parent(payload, bridge)
            except ValueError as error: controls.append(dict(control=label,rejected=True,reason=str(error)))
            else: raise ValueError('release inverse accepted '+label)
        report['strict_inverse_controls'] = controls
        if before != {str(p): sha(p.read_bytes()) for p in paths}: raise ValueError('release input drift during verification')
        report['all_inputs_unchanged'] = True; report['passed'] = True
    finally:
        report['evidence_sha256'] = {str(p.relative_to(out)):sha(p.read_bytes()) for p in out.rglob('*')
                                     if p.is_file() and 'obj' not in p.parts and p.suffix in ('.json','.log','.sv')}
        (out / 'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],binary=report['binary']['status'],four_state=report['runs']['four_state'],strict_inverse_controls=len(report['strict_inverse_controls'])),indent=2))

if __name__ == '__main__': main()
