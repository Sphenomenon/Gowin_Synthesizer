#!/usr/bin/env python3
"""Verify maintained PCM bitmap context: real source DAG, four-state and full owner.

The symbolic scope is a checked scalar dependency overapproximation, not a full
SystemVerilog temporal proof. Actual-module cases never force derived admissions.
"""
import ast
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import z3

import ae350_pcm_bitmap_context_sources as sources
import run_ae350_pcm_window_gate as whole

OUT = None
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'rtl/audio/workstation_ae350_pcm_owner.sv'
WINDOW = ROOT / 'sim/audio/run_ae350_pcm_window_gate.py'
PRE_SHA = '1c575c3fd39d73c795cb7e49c075a1b5848be90d3cccd57e24db991a9071649b'
NEW_SHA = '290d3fbab8de519772d2be44f7ded6a7a94d5ff8e00781b37d4d2680d8aff1f0'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def norm(text):
    return re.sub(r'\s+', '', re.sub(r'//[^\n]*', '', text))


def condition_list(text):
    conditions = []
    for found in re.finditer(r'\bif\s*\(', text):
        depth, start = 1, found.end()
        end = start
        while depth:
            depth += (text[end] == '(') - (text[end] == ')')
            end += 1
        conditions.append(text[start:end-1])
    return conditions


def check_structure(before, candidate):
    marker = '    // Private bitmap writes retain the original ordering.'
    suffix = '    always @(posedge clk_i or negedge reset_ni)begin\n        if(!reset_ni)begin\n            owned<=0;'
    begin, end = before.index(marker), before.index(suffix)
    added_begin = candidate.index('    // Context revoke is the final private bitmap decision.')
    added_end = candidate.index(suffix)
    require(before[:begin] == candidate[:added_begin] and before[end:] == candidate[added_end:],
            'all bytes outside private bitmap region unchanged')
    original = before[begin:end]
    comb, sequence = original.split('    integer bitmap_slot;', 1)
    require(candidate.count(comb) == 1, 'original four-state clear process preserved byte-for-byte')
    cofactor = comb.replace('bitmap_clear_late', 'bitmap_clear_without_context').replace(
        'rejected_commit && usable', 'bitmap_rejected_without_context && bitmap_usable_without_context').replace(
        '!physical_matches', '!bitmap_physical_without_context')
    cofactor = cofactor[cofactor.index('    reg bitmap_clear_without_context'):]
    require(candidate.count(cofactor) == 1, 'cofactor clear process differs only in reviewed named operands')
    body = sequence[sequence.index('            if(accepted_window_write)'):sequence.rindex('        end\n    end\n')]
    known = body.replace('accepted_start', 'bitmap_start_without_context').replace(
        'accepted_commit', 'bitmap_commit_without_context').replace('bitmap_clear_late', 'bitmap_clear_without_context')
    cseq = candidate[candidate.index('    integer bitmap_slot;', added_begin):added_end]
    require(cseq.count('                default:begin\n' + body + '                end\n') == 1,
            'X/Z case fallback is original ordered NBA body exactly')
    require(cseq.count("                1'b1:begin\n" + known + '                end\n') == 1,
            'known-one case uses only reviewed cofactor operands')
    zero = """                1'b0:begin
                    if(accepted_stop || accepted_cancel || armed)
                        for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
                end
"""
    require(cseq.count(zero) == 1 and cseq.count('case(context_ready_i)') == 1, 'known-zero case exact source')
    shape = norm(body)
    expected = ('if(accepted_window_write)written[write_slot][write_index]<=1;'
                'if(accepted_start)beginfor(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;end'
                'if(accepted_commit)written[tail_slot]<=0;'
                'if(bitmap_clear_late)beginfor(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;end')
    require(shape == expected, 'actual ordered write/start/commit/clear assignments match symbolic next-bit model')
    return comb, cofactor


class SourceLogic:
    """Interpret actual scalar logical source; complex vector predicates are shared arbitrary atoms.

    Atoms overapproximate all four-state results of raw vector operations. No
    accepted/usable predicate is a free atom: their source dependencies expand.
    This is a source-checked local relation, not a formal full-SV elaboration.
    """
    def __init__(self, source):
        self.defs = {}
        for name, expression in re.findall(r'\bwire\s+(\w+)(?:\s*/\*.*?\*/)?\s*=\s*(.*?);', source, re.S):
            self.defs[name] = expression
        for name, expression in re.findall(r'\bassign\s+(\w+)\s*=\s*(.*?);', source, re.S):
            self.defs[name] = expression
        self.leaves, self.expanded = {}, {}
        control = re.search(r'always @\* begin\s*control_format_ok=1\'b1;control_id_ok=1\'b1;(.*?)end', source, re.S)
        require(control is not None and norm(control[1]) ==
                "if(!full_write)control_format_ok=1'b0;if(&command_id)control_id_ok=1'b0;", 'actual procedural control-format decoder')

    @staticmethod
    def c(value):
        return z3.BitVecVal(value, 2)

    @staticmethod
    def true(value):
        return value == 1

    def not_(self, value):
        return z3.If(value == 0, self.c(1), z3.If(value == 1, self.c(0), self.c(2)))

    def combine(self, op, values):
        if op == '&&':
            return z3.If(z3.Or([x == 0 for x in values]), self.c(0),
                         z3.If(z3.And([x == 1 for x in values]), self.c(1), self.c(2)))
        return z3.If(z3.Or([x == 1 for x in values]), self.c(1),
                     z3.If(z3.And([x == 0 for x in values]), self.c(0), self.c(2)))

    @staticmethod
    def split(text, token):
        depth, begin, parts, i = 0, 0, [], 0
        while i < len(text):
            char = text[i]
            if char in '([{': depth += 1
            if char in ')]}': depth -= 1
            if depth == 0 and text.startswith(token, i):
                parts.append(text[begin:i]);i += len(token);begin = i
            else: i += 1
        return parts + [text[begin:]] if parts else None

    def expression(self, raw):
        text = norm(raw)
        while text.startswith('('):
            depth, closes = 0, None
            for i, char in enumerate(text):
                depth += (char == '(') - (char == ')')
                if depth == 0: closes = i;break
            if closes != len(text)-1: break
            text = text[1:-1]
        for op in ('||', '&&'):
            parts = self.split(text, op)
            if parts:
                return self.combine(op, [self.expression(x) for x in parts])
        if text.startswith('!'):
            return self.not_(self.expression(text[1:]))
        if text in ('0', "1'b0"): return self.c(0)
        if text in ('1', "1'b1"): return self.c(1)
        if text == 'control_format_ok':
            return z3.If(self.true(self.not_(self.expression('full_write'))), self.c(0), self.c(1))
        if text == 'control_id_ok':
            return z3.If(self.true(self.expression('&command_id')), self.c(0), self.c(1))
        if text in self.defs:
            if text not in self.expanded:
                self.expanded[text] = self.expression(self.defs[text])
            return self.expanded[text]
        if text not in self.leaves:
            self.leaves[text] = z3.BitVec('raw_' + hashlib.sha256(text.encode()).hexdigest()[:12], 2)
        return self.leaves[text]

    def clear(self, body, variable):
        conditions = condition_list(body)
        require(len(conditions) == 9 and norm(conditions[3]) == 'armed', 'actual clear if inventory')
        reduced = norm(body)
        for number, condition in enumerate(conditions):
            reduced = reduced.replace('if(' + norm(condition) + ')', 'if(C' + str(number) + ')', 1)
        expected = (variable + '=0;if(C0)' + variable + '=1;if(C1)' + variable + '=1;if(C2)' + variable + '=1;'
                    'if(C3)beginif(C4)' + variable + '=1;elseif(C5)' + variable + '=1;elseif(C6)' + variable + '=1;'
                    'elseif(C7)' + variable + '=1;elseif(C8)' + variable + '=1;end')
        require(reduced == expected, 'all real clear statements and procedural if order bound to symbolic model')
        values = [self.true(self.expression(x)) for x in conditions]
        return z3.Or(*values[:3], z3.And(values[3], z3.Or(*values[4:])))


def symbolic(before, candidate, comb, cofactor):
    logic = SourceLogic(candidate)
    # These exact actual definitions establish the sole context removal.
    def terms(text):
        return sorted(SourceLogic.split(norm(text), '&&') or [norm(text)])
    for original, other in [('physical_matches', 'bitmap_physical_without_context'), ('staging_live', 'bitmap_staging_without_context')]:
        require(terms(logic.defs[original]) == sorted(['context_ready_i', *terms(logic.defs[other])]),
                'actual source context factor ' + original)
    pairs = [('usable', 'bitmap_usable_without_context', 'physical_matches', 'bitmap_physical_without_context'),
             ('start_error', 'bitmap_start_error', 'staging_live', 'bitmap_staging_without_context'),
             ('commit_error', 'bitmap_commit_error', 'usable', 'bitmap_usable_without_context'),
             ('accepted_start', 'bitmap_start_without_context', 'start_error', 'bitmap_start_error'),
             ('accepted_commit', 'bitmap_commit_without_context', 'commit_error', 'bitmap_commit_error'),
             ('rejected_commit', 'bitmap_rejected_without_context', 'commit_error', 'bitmap_commit_error')]
    for original, other, a, b in pairs:
        require(norm(logic.defs[original]).replace(a, b) == norm(logic.defs[other]), 'actual corresponding equation ' + original)
    old_body = comb[comb.index('    always @* begin') + len('    always @* begin'):comb.rindex('    end')]
    new_body = cofactor[cofactor.index('    always @* begin') + len('    always @* begin'):cofactor.rindex('    end')]
    old_clear = logic.clear(old_body, 'bitmap_clear_late')
    new_clear = logic.clear(new_body, 'bitmap_clear_without_context')
    old_w = z3.BitVec('original_written_bit', 2)
    window_hit, tail_hit = z3.Bools('same_window_bit_address same_tail_slot')
    ev = logic.expression
    true = logic.true
    def next_bit(start, commit, clear):
        result = z3.If(z3.And(true(ev('accepted_window_write')), window_hit), logic.c(1), old_w)
        result = z3.If(true(ev(start)), logic.c(0), result)
        result = z3.If(z3.And(true(ev(commit)), tail_hit), logic.c(0), result)
        return z3.If(clear, logic.c(0), result)
    normal = next_bit('accepted_start', 'accepted_commit', old_clear)
    known = next_bit('bitmap_start_without_context', 'bitmap_commit_without_context', new_clear)
    low_clear = true(ev('accepted_stop || accepted_cancel || armed'))
    low = z3.If(low_clear, logic.c(0), old_w)
    ctx, rst = ev('context_ready_i'), ev('reset_ni')
    proposed = z3.If(ctx == 0, low, z3.If(ctx == 1, known, normal))
    normal = z3.If(rst == 0, logic.c(0), normal)
    proposed = z3.If(rst == 0, logic.c(0), proposed)
    proofs = {}
    for code, label in [(0, 'context_0'), (1, 'context_1'), (2, 'context_X'), (3, 'context_Z')]:
        solver = z3.Solver();solver.add(ctx == code, normal != proposed)
        require(solver.check() == z3.unsat, 'source-derived next-bit four-state relation ' + label)
        proofs[label] = 'UNSAT'
    relations = {
        'context0_accepted_start_is_zero': ev('accepted_start') != 0,
        'context0_accepted_commit_is_zero': ev('accepted_commit') != 0,
        'context0_armed_true_implies_original_final_clear': z3.And(ev('armed') == 1, z3.Not(old_clear)),
        'window_write_true_implies_armed_true': z3.And(true(ev('accepted_window_write')), ev('armed') != 1),
    }
    for label, violation in relations.items():
        solver = z3.Solver();solver.add(violation)
        if label != 'window_write_true_implies_armed_true': solver.add(ctx == 0)
        require(solver.check() == z3.unsat, 'real dependency relation ' + label)
        proofs[label] = 'UNSAT'
    negatives = {}
    for label, wrong in [('missing_armed_revoke', z3.If(true(ev('accepted_stop || accepted_cancel')), logic.c(0), old_w)),
                         ('unknown_uses_cofactor', known)]:
        solver = z3.Solver()
        solver.add(ctx == (0 if label == 'missing_armed_revoke' else 2), rst == 1, normal != wrong)
        require(solver.check() == z3.sat, 'symbolic negative witness ' + label)
        negatives[label] = dict(result='SAT', witness=str(solver.model()))
    forbidden = ('accepted_start', 'accepted_commit', 'accepted_window_write', 'usable', 'staging_live', 'physical_matches')
    require(not set(forbidden) & set(logic.leaves), 'derived admissions must never be independent atoms')
    save(OUT / 'symbolic-actual-equations.json', dict(definitions=logic.defs, expanded=sorted(logic.expanded),
        arbitrary_vector_or_raw_atoms={k:str(v) for k,v in logic.leaves.items()}, proofs=proofs, negatives=negatives,
        scope='Source-parsed scalar dependency DAG and exact checked NBA shape. Complex raw vector predicates overapproximated by shared arbitrary four-state atoms; same-address hits arbitrary Boolean. No reachability assumptions or forced derived admissions. Not full-SystemVerilog elaboration.'))
    return dict(proofs=proofs, negative_controls=negatives, four_state_atoms=len(logic.leaves),
                derived_admissions_not_free=True, z3_version=z3.get_version_string())


def inventory():
    tree = ast.parse(WINDOW.read_text())
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == 'STATE': result['state'] = ast.literal_eval(node.value.func.value).split()
            if node.targets[0].id == 'OUTPUTS': result['outputs'] = list(ast.literal_eval(node.value))
    return result


def actual_bench(source):
    spec = {}
    header = re.search(r'\)\s*\((.*?)\);', source, re.S)[1]
    for direction, width, names in re.findall(r'\b(input|output)\s+(?:wire|reg)\s*(?:signed\s*)?(\[[^]]+\])?\s*([\w,\s]+?)(?=\binput|\boutput|$)', header):
        for name in names.strip().strip(',').split(','):
            spec[name.strip()] = direction, width
    require((len(spec),sum(direction == 'output' for direction, _ in spec.values())) in ((32,11),(33,12)),
            'actual module port inventory')
    fields = inventory()
    if 'idle_o' in spec:fields['outputs'].append('idle_o')
    text = '`timescale 1ns/1ps\nmodule tb;\n'
    for name, (direction, width) in spec.items():
        text += ('reg ' if direction == 'input' else 'wire ') + width + ' ' + name + ("=0" if direction == 'input' else ',ref_' + name) + ';\n'
    for module, who in [('workstation_ae350_pcm_owner', 'dut'), ('pcm_owner_window_reference', 'old_owner')]:
        text += module + ' #(.PREFILL_FRAMES(4),.WINDOW_BITS(3),.HISTORY_TIMEOUT_CYCLES(12)) ' + who + '(' + ','.join(
            '.' + name + '(' + ('ref_' if direction == 'output' and who == 'old_owner' else '') + name + ')' for name,(direction,_) in spec.items()) + ');\n'
    values = {name:'0' for name in fields['state']}
    values.update(staged_controller='1', staged_generation='2', staged_stream='3', staged_rate='48000', staged_physical='4',
                  staged_frames='128', active_controller='1', active_generation='2', active_stream='3', active_rate='48000',
                  active_physical='4', armed='1', cpu_previous='1', queued='2', step_q24="32'd16777216", minimum_queue='512', cache_valid='1')
    text += '''integer checks=0,i,j,k,s,b,code,ctx,kind,n,pattern;reg [31:0] rng=32'h5946a731;
function digit4(input integer number);case(number&3)0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase endfunction
function [31:0] frame_boundary(input integer number);case(number)
0:frame_boundary=0;1:frame_boundary=1;2:frame_boundary=2;3:frame_boundary=127;4:frame_boundary=128;
5:frame_boundary=129;6:frame_boundary=255;7:frame_boundary=256;8:frame_boundary=32'h7fffffff;
9:frame_boundary=32'h80000000;10:frame_boundary=32'hffffffff;11:frame_boundary=32'hxxxxxx01;
12:frame_boundary=32'hzzzzzz80;13:frame_boundary=32'hxxxxxxxx;14:frame_boundary=32'hzzzzzzzz;
15:frame_boundary=32'h000000x1;endcase endfunction
task base;begin
 clk_i=0;reset_ni=1;cpu_ready_i=1;command_valid_i=1;command_write_i=1;
 command_address_i=12'h800;command_data_i=32'h1234abcd;command_strobes_i=15;
 session_live_i=1;controller_epoch_i=1;transport_generation_i=2;physical_epoch_i=4;
 context_ready_i=1;rate_44100_i=0;tf_busy_i=0;switch_busy_i=0;sample_take_i=0;
 legacy_left_i=32'h45670000;legacy_right_i=32'h89ab0000;history_ready_i=0;history_done_i=0;
'''
    for who in ('dut', 'old_owner'):
        text += who + '.cancel_epoch_o=0;\n'
        text += '\n'.join(who + '.' + name + '=' + value + ';' for name,value in values.items()) + '\n'
        text += 'for(s=0;s<4;s=s+1)begin ' + who + ".written[s]=128'h00ff00ff00ff00ff00ff00ff00ff00ff;" + who + '.frames[s]=128;end\n'
    text += 'end endtask\ntask check;begin #1;clk_i=1;#1;\n'
    for name in list(dict.fromkeys(fields['state']+fields['outputs'])):
        text += 'if(dut.' + name + ' !== old_owner.' + name + ')$fatal(1,"PCM CONTEXT REAL FOUR STATE ' + name + ' checks=%0d ctx=%b",checks,context_ready_i);\n'
    text += '''for(s=0;s<4;s=s+1)begin
 if(dut.written[s] !== old_owner.written[s] || dut.frames[s] !== old_owner.frames[s])
  $fatal(1,"PCM CONTEXT REAL FOUR STATE bitmap/frame checks=%0d slot=%0d ctx=%b",checks,s,context_ready_i);
end
for(s=0;s<512;s=s+1)if(dut.memory[s] !== old_owner.memory[s])
 $fatal(1,"PCM CONTEXT REAL FOUR STATE memory checks=%0d word=%0d",checks,s);
checks=checks+1;clk_i=0;#1;end endtask
initial begin #2;
 for(s=0;s<512;s=s+1)begin dut.memory[s]=32'hface0000+s;old_owner.memory[s]=32'hface0000+s;end
 // Real raw commands, four-state context/armed, bitmap patterns and frame bounds.
 for(ctx=0;ctx<4;ctx=ctx+1)for(kind=0;kind<7;kind=kind+1)
  for(code=0;code<4;code=code+1)for(n=0;n<4;n=n+1)for(pattern=0;pattern<4;pattern=pattern+1)begin base();
   context_ready_i=digit4(ctx);dut.armed=digit4(code);old_owner.armed=digit4(code);
   case(kind)0:begin end 1,2,3,4,5:begin command_address_i='h040;command_data_i=kind;end
    6:begin command_address_i='h03c;command_data_i=32'hffffffff;end endcase
   dut.staged_frames=frame_boundary(n==2 ? 4:n==3 ? 5:n);old_owner.staged_frames=dut.staged_frames;
   for(s=0;s<4;s=s+1)begin
    case(pattern)0:dut.written[s]='1;1:dut.written[s]=0;2:dut.written[s]='x;3:dut.written[s]='z;endcase
    old_owner.written[s]=dut.written[s];end
   check();
 end
 // Exhaustive core raw qualifiers: no forced derived predicate or derived clear.
 for(k=0;k<16384;k=k+1)begin base();context_ready_i=digit4(k);
  dut.armed=digit4(k>>2);old_owner.armed=dut.armed;
  dut.cpu_previous=digit4(k>>4);old_owner.cpu_previous=dut.cpu_previous;
  cpu_ready_i=digit4(k>>6);session_live_i=digit4(k>>8);tf_busy_i=digit4(k>>10);switch_busy_i=digit4(k>>12);check();
 end
 for(ctx=0;ctx<4;ctx=ctx+1)for(k=0;k<4096;k=k+1)begin base();context_ready_i=digit4(ctx);
  command_address_i=12'(k);command_data_i=1;check();end
 for(ctx=0;ctx<4;ctx=ctx+1)for(i=0;i<4;i=i+1)for(n=0;n<16;n=n+1)for(code=0;code<4;code=code+1)begin base();
  context_ready_i=digit4(ctx);command_address_i='h040;command_data_i=2;
  dut.tail_slot=2'(i);old_owner.tail_slot=dut.tail_slot;dut.staged_slot=i;old_owner.staged_slot=i;
  dut.staged_frames=frame_boundary(n);old_owner.staged_frames=dut.staged_frames;
  dut.owned[i]=digit4(code);old_owner.owned[i]=dut.owned[i];check();
 end
 // Every bit of all staged/active key and live/physical raw relations, including X/Z.
 for(ctx=0;ctx<4;ctx=ctx+1)for(i=0;i<8;i=i+1)for(b=0;b<32;b=b+1)for(code=0;code<16;code=code+1)begin base();
  context_ready_i=digit4(ctx);command_address_i='h040;command_data_i=(i&1) ? 1:2;
  case(i)
   0:begin dut.staged_controller[b]=digit4(code);dut.active_controller[b]=digit4(code>>2);end
   1:begin dut.staged_generation[b]=digit4(code);dut.active_generation[b]=digit4(code>>2);end
   2:begin dut.staged_stream[b]=digit4(code);dut.active_stream[b]=digit4(code>>2);end
   3:begin dut.staged_rate[b]=digit4(code);dut.active_rate[b]=digit4(code>>2);end
   4:begin dut.staged_physical[b]=digit4(code);dut.active_physical[b]=digit4(code>>2);end
   5:begin controller_epoch_i[b]=digit4(code);dut.active_controller[b]=digit4(code>>2);end
   6:begin transport_generation_i[b]=digit4(code);dut.active_generation[b]=digit4(code>>2);end
   7:begin physical_epoch_i[b]=digit4(code);dut.active_physical[b]=digit4(code>>2);end
  endcase
'''
    for name in ('staged_controller','staged_generation','staged_stream','staged_rate','staged_physical','active_controller','active_generation','active_stream','active_rate','active_physical'):
        text += 'old_owner.' + name + '=dut.' + name + ';\n'
    text += '''check();end
 for(ctx=0;ctx<4;ctx=ctx+1)for(b=0;b<12;b=b+1)for(code=2;code<4;code=code+1)begin base();
  context_ready_i=digit4(ctx);command_address_i[b]=digit4(code);check();end
 for(ctx=0;ctx<4;ctx=ctx+1)for(i=0;i<10;i=i+1)for(code=0;code<4;code=code+1)begin base();context_ready_i=digit4(ctx);
  case(i)
  0:begin dut.failed=digit4(code);old_owner.failed=dut.failed;end
  1:begin dut.selected=digit4(code);old_owner.selected=dut.selected;end
  2:begin dut.hold_serial=digit4(code);old_owner.hold_serial=dut.hold_serial;sample_take_i=1;end
  3:begin dut.cache_valid=digit4(code);old_owner.cache_valid=dut.cache_valid;sample_take_i=1;dut.selected=1;old_owner.selected=1;end
  4:begin command_valid_i=digit4(code);end
  5:begin command_write_i=digit4(code);end
  6:begin command_strobes_i[3]=digit4(code);end
  7:begin rate_44100_i=digit4(code);end
  8:begin dut.tail_slot[1]=digit4(code);old_owner.tail_slot=dut.tail_slot;command_address_i='h040;command_data_i=2;end
  9:begin reset_ni=digit4(code);end
  endcase check();end
 $display("PASS PCM CONTEXT actual-module four-state checks=%0d states=STATE_COUNT outputs=11 memory_words=512 bitmaps=4 derived_forces=0",checks);$finish;
end endmodule
'''.replace('STATE_COUNT', str(len(fields['state'])))
    count = 4*7*4*4*4 + 16384 + 4*4096 + 4*4*16*4 + 4*8*32*16 + 4*12*2 + 4*10*4
    return text, count


def simulate(label, source, bench, passing):
    folder = OUT / label;folder.mkdir()
    (folder / 'bench.sv').write_text(bench)
    compiled = subprocess.run(['iverilog','-g2012','-s','tb','-o',str(folder/'bench.vvp'),
                               str(folder/'bench.sv'),str(source),str(OUT/'reference.sv')], capture_output=True,text=True,timeout=60)
    (folder/'compile.log').write_text(compiled.stdout+compiled.stderr)
    require(compiled.returncode == 0, 'compile ' + label + ': ' + compiled.stderr[-1500:])
    ran = subprocess.run(['vvp',str(folder/'bench.vvp')],capture_output=True,text=True,timeout=180)
    (folder/'simulation.log').write_text(ran.stdout+ran.stderr)
    require((ran.returncode == 0) == passing, 'simulation ' + label + ': ' + ran.stdout[-2000:])
    return dict(exit_code=ran.returncode,expected_pass=passing,summary=ran.stdout)


def full_owner_bench():
    bench=whole.bench();marker='arm(1);'
    require(bench.count(marker)==1,'complete owner directed context anchor')
    directed="""arm(1);write('h800,32'h1234abcd,0);
@(negedge clk);ctx_ready=0;repeat(3)@(negedge clk);ctx_ready=1;
@(negedge clk);rst=0;repeat(4)@(negedge clk);rst=1;repeat(4)@(negedge clk);
"""
    return bench.replace(marker,directed+marker,1)


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();OUT=args.output.resolve()
    require(not OUT.is_relative_to(ROOT),'external evidence directory required')
    OUT.mkdir(parents=True,exist_ok=False)
    inputs=list(dict.fromkeys(sources.inputs()+[WINDOW,whole.REFERENCE,
        ROOT/'sim/test_ae350_pcm_owner.py',Path(__file__).resolve()]))
    hashes={str(path):sha(path) for path in inputs}
    candidate=sources.normalize_later_bitmap_slots(SOURCE.read_text());before=sources.reference_view(candidate)
    require(hashlib.sha256(candidate.encode()).hexdigest()==NEW_SHA and hashlib.sha256(before.encode()).hexdigest()==PRE_SHA,
            'strict complete current/previous owner identities')
    comb,cofactor=check_structure(before,candidate)
    report=dict(schema=1,passed=False,stage='historical_PCM_context_bitmap_after_exact_later_slot_inverse',
        maintained_source_sha256=sha(SOURCE),later_bitmap_slot_inverse_verified=True,
        inputs_sha256=hashes,contract=sources.contract(),source_shape_bound=True,
        all_non_bitmap_bytes_unchanged=True,derived_predicates_forced=False,
        source_implementation=True,synthesis=False,pnr=False,hardware_tested=False,
        physical_gain_measured=False,cases={},source_negative_controls={})
    try:
        report['symbolic']=symbolic(before,candidate,comb,cofactor)
        print('PASS actual source dependency four-state cofactor',flush=True)
        (OUT/'before.sv').write_text(before);(OUT/'candidate.sv').write_text(candidate)
        (OUT/'reference.sv').write_text(before.replace('module workstation_ae350_pcm_owner',
                                                     'module pcm_owner_window_reference',1))
        controls={
            'changed_output':('assign pcm_left_o=selected ?','assign pcm_left_o=!selected ?'),
            'missing_bitmap_keep':('(* syn_keep=1 *) wire bitmap_physical_without_context=',
                                   'wire bitmap_physical_without_context='),
            'changed_unknown_fallback':('if(bitmap_clear_late)begin',"if(1'b0)begin"),
            'changed_zero_revoke':('accepted_stop || accepted_cancel || armed',
                                   'accepted_stop || accepted_cancel'),
        }
        for label,(old,new) in controls.items():
            require(candidate.count(old)==1,'source control exact anchor '+label)
            try:sources.reference_view(candidate.replace(old,new,1))
            except ValueError as error:
                report['source_negative_controls'][label]=dict(rejected=True,reason=str(error))
            else:raise ValueError('strict inverse source control survived '+label)
        bench,count=actual_bench(before)
        result=simulate('actual-four-state',OUT/'candidate.sv',bench,True)
        require('checks='+str(count) in result['summary'],'actual-module vector inventory')
        report['cases']['four_state']=dict(result,checks=count);print(result['summary'],flush=True)
        report['cases']['whole_owner']=simulate('complete-binary-owner',OUT/'candidate.sv',full_owner_bench(),True)
        require('PASS PCM window gate whole-owner cycle reference:' in report['cases']['whole_owner']['summary'],
                'complete owner positive attribution')
        print(report['cases']['whole_owner']['summary'],flush=True)
        start="                default:begin\n"
        seq=candidate[candidate.index('    integer bitmap_slot;'):candidate.index(
            '    always @(posedge clk_i or negedge reset_ni)begin\n        if(!reset_ni)begin\n            owned<=0;')]
        default=seq.split(start,1)[1].rsplit('                end\n',1)[0]
        known=seq.split("                1'b1:begin\n",1)[1].split('                end\n',1)[0]
        require(candidate.count(default)==1,'default fallback mutant anchor')
        mutants={
            'missing_low_armed_revoke':candidate.replace('accepted_stop || accepted_cancel || armed',
                                                        'accepted_stop || accepted_cancel',1),
            'missing_low_stop_revoke':candidate.replace('accepted_stop || accepted_cancel || armed',
                                                       'accepted_cancel || armed',1),
            'unknown_uses_cofactor':candidate.replace(start+default,start+known,1),
            'swapped_context_cases':candidate.replace('case(context_ready_i)','case(!context_ready_i)',1),
        }
        report['actual_module_mutants']={}
        for label,text in mutants.items():
            path=OUT/(label+'.sv');path.write_text(text)
            result=simulate('mutant-'+label,path,bench,False)
            require('PCM CONTEXT REAL FOUR STATE' in result['summary'],'negative attribution '+label)
            report['actual_module_mutants'][label]=result
        require(hashes=={str(path):sha(path) for path in inputs},'maintained inputs drifted')
        report['input_seal_before_after']=True;report['passed']=True
    finally:
        report['outputs_sha256']={str(path.relative_to(OUT)):sha(path)
                                 for path in sorted(OUT.rglob('*')) if path.is_file()}
        save(OUT/'verification.json',report)
    print(json.dumps(dict(output=str(OUT),passed=True,four_state_checks=count,
        mutants=len(mutants),verification_sha256=sha(OUT/'verification.json'))),flush=True)


if __name__=='__main__':main()
