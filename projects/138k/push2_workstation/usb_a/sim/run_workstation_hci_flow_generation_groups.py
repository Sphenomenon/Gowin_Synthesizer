#!/usr/bin/env python3
"""Pinned ACL generation grouping: actual flow-owner twins and four-state controls.

The original complete source is reconstructed by a strict reviewed inverse. All
simulations compile maintained RTL; no private cache or generated build tree is
a production input. This is source-stage evidence and claims no physical gain.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import z3

from workstation_hci_flow_generation_sources import (
    ROOT, REPO, FLOW, BENCH, GROUPS, PRE_FLOW_GENERATION_SHA256,
    FLOW_GENERATION_SHA256, apply_generation_groups, reverse_generation_groups,
    require,
)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def ports(source, slots=2):
    header = re.sub(r'//[^\n]*', '', source.split(') (', 1)[1].split(');', 1)[0])
    result = {}
    for direction, width, names in re.findall(r'\b(input|output)\s+(?:wire|reg)\s*(\[[^]]+\])?\s*([\w,\s]+?)(?=\binput|\boutput|$)', header):
        for name in names.strip().strip(',').split(','):
            name = name.strip()
            require(re.fullmatch(r'[A-Za-z_]\w*', name), 'unparsed port ' + name)
            result[name] = (direction, width.replace('HANDLE_SLOTS', str(slots)))
    require(len(result) == 65 and sum(v[0] == 'output' for v in result.values()) == 32, 'port inventory')
    return result


SCALARS = ('br_capacity le_capacity br_length le_length shared_pool active is_le last_generation '
           'batch_unknown batch_pairs pending_opcode pending_owner lifecycle_slot free_slot acl_slot '
           'completion_slot br_return le_return completion_bad').split()


ARRAYS = ('numbers', 'generations', 'outstanding', 'returns')


def comparisons(spec, slots, prefix):
    checks = [('dut.' + name, 'reference.' + name, name) for name in SCALARS]
    checks += [('dut.' + array + '[' + str(slot) + ']', 'reference.' + array + '[' + str(slot) + ']', array)
               for array in ARRAYS for slot in range(slots)]
    checks += [(name, 'ref_' + name, name) for name, (direction, _) in spec.items() if direction == 'output']
    return '\n'.join(f'if({a} !== {b})$fatal(1,"{prefix} {label} checks=%0d",checks);' for a, b, label in checks)


def reference_instance(spec, slots=2):
    declarations = '\n'.join('wire ' + width + ' ref_' + name + ';' for name, (direction, width) in spec.items() if direction == 'output')
    instance = 'workstation_hci_flow_owner_reference #(.HANDLE_SLOTS(' + str(slots) + ')) reference(' + ','.join(
        '.' + name + '(' + ('ref_' if direction == 'output' else '') + name + ')' for name, (direction, _) in spec.items()) + ');\n'
    return declarations + '\n' + instance


def whole_bench(source):
    spec = ports(source)
    text = BENCH.read_text()
    anchor = 'workstation_hci_flow_owner dut(.*);'
    require(text.count(anchor) == 1, 'whole bench DUT anchor')
    text = text.replace(anchor, anchor + '\n' + reference_instance(spec))
    text = text.replace("dut.last_generation=32'hfffffffe;", "dut.last_generation=32'hfffffffe;reference.last_generation=32'hfffffffe;")
    sample = 'integer twin_cycles=0;always @(posedge clk_i)begin #2;twin_cycles=twin_cycles+1;\n'
    sample += comparisons(spec, 2, 'FLOW GENERATION TWIN') + '\nend\n'
    sample += 'final $display("FLOW GENERATION TWIN cycles=%0d outputs=32 scalar_groups=19 array_words=8",twin_cycles);\n'
    require(text.count('endmodule') == 1, 'whole bench module count')
    text = text.replace('endmodule', sample + '\nendmodule')
    anchor = '        $display("PASS checks=%0d scenarios=%0d random_steps=10000",checks,scenarios);$finish;'
    require(text.count(anchor) == 1, 'whole bench completion anchor')
    extra = '''
        // Same-edge cancellation and fault priority with an invalid ACL send.
        for(integer reason=0;reason<4;reason=reason+1)begin
            reset_owner();configure(1);open_handle(12'h031,1,le_gen);
            if(reason==1 || reason==3)command_send(2,16'h0409);
            acl_handle_i=12'h031;acl_generation_i=le_gen^32'h80000000;
            acl_data_length_i=1;acl_valid_i=1;acl_send_i=1;
            transport_fault_i=(reason==0 || reason==3);command_timeout_i=(reason!=0);#1;
            check(!acl_ready_o,"same-edge cancel gates reject stale ACL immediately");tick();
            transport_fault_i=0;command_timeout_i=0;acl_send_i=0;acl_valid_i=0;#1;
            check(fault_o && fault_reason_o==(reason==0 || reason==3 ? 1:reason==1 ? 8:3),
                  "transport/timeout faults dominate invalid ACL send without debit");
            check(br_available_o==3 && handle_outstanding_o==0,"cancel leaves ACL accounting unchanged");
        end
        $display("FLOW GENERATION same_edge_priority_scenarios=4");
'''
    return text.replace(anchor, extra + anchor)


def four_state_bench(source, slots, exhaustive):
    spec = ports(source, slots)
    text = 'module tb;\nlocalparam integer SLOTS=' + str(slots) + ';\n'
    for name, (direction, width) in spec.items():
        text += ('reg ' + width + ' ' + name + "='0;\n" if direction == 'input' else 'wire ' + width + ' ' + name + ';\n')
    text += 'workstation_hci_flow_owner #(.HANDLE_SLOTS(SLOTS)) dut(.*);\n' + reference_instance(spec, slots)
    text += '''integer at,s,k,j,bit_at,code,checks=0,selector;
reg [31:0] stored,live;
function digit4(input integer number);case(number&3)
0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase endfunction
task base(input integer target);begin
 reset_ni=1;transport_fault_i=0;config_valid_i=0;br_acl_length_i=276;br_acl_count_i=3;
 le_acl_length_i=27;le_acl_count_i=2;handle_open_i=0;handle_close_i=0;handle_is_le_i=0;handle_i=1;
 acl_valid_i=1;acl_send_i=0;acl_handle_i=target+1;acl_generation_i=32'h10203040+target;acl_data_length_i=1;
 completion_start_i=0;completion_pair_valid_i=0;completion_handle_i=1;completion_count_i=0;
 completion_commit_i=0;completion_abort_i=0;command_valid_i=0;command_send_i=0;
 command_owner_i=0;command_opcode_i=16'h1001;command_response_i=0;command_timeout_i=0;
 response_is_complete_i=1;response_credits_i=0;response_status_i=0;response_opcode_i=0;
'''
    init = ('configured_o=1 fault_o=0 fault_reason_o=0 br_capacity=3 le_capacity=2 br_length=276 '
            'le_length=27 shared_pool=0 br_available_o=3 le_available_o=2 active=\'1 is_le=0 '
            'last_generation=32\'h10203050 batch_unknown=0 batch_pairs=0 pending_opcode=0 pending_owner=0 '
            'completion_active_o=0 unknown_completion_packets_o=0 command_credits_o=1 command_pending_o=0 '
            'response_valid_o=0 response_is_complete_o=0 response_owner_o=0 response_opcode_o=0 '
            'response_status_o=0 handle_rejected_o=0').split()
    for who in ('dut', 'reference'):
        for assignment in init:
            text += who + '.' + assignment + ';\n'
        text += 'for(at=0;at<SLOTS;at=at+1)begin\n'
        text += who + '.numbers[at]=at+1;' + who + ".generations[at]=32'h10203040+at;"
        text += who + '.outstanding[at]=0;' + who + '.returns[at]=0;end\n'
    text += 'end endtask\ntask check;begin #1;\n'
    text += '''for(at=0;at<SLOTS;at=at+1)begin
 if(dut.acl_generation_changed[at] !== (acl_generation_i != reference.generations[at]))
  $fatal(1,"FLOW FOUR STATE predicate slot=%0d checks=%0d",at,checks);
end
'''
    text += comparisons(spec, slots, 'FLOW FOUR STATE') + '\nchecks=checks+1;end endtask\ninitial begin\n'
    if exhaustive:
        text += '''for(s=0;s<SLOTS;s=s+1)begin base(s);
 for(k=0;k<65536;k=k+1)begin stored=0;live=0;
  stored[0]=digit4(k);stored[7]=digit4(k>>2);stored[8]=digit4(k>>4);stored[31]=digit4(k>>6);
  live[0]=digit4(k>>8);live[7]=digit4(k>>10);live[8]=digit4(k>>12);live[31]=digit4(k>>14);
  dut.generations[s]=stored;reference.generations[s]=stored;acl_generation_i=live;check();
 end
end
'''
    text += '''for(s=0;s<SLOTS;s=s+1)for(bit_at=0;bit_at<32;bit_at=bit_at+1)
 for(code=0;code<16;code=code+1)begin base(s);
  stored=32'h5a69c3e7;live=stored;stored[bit_at]=digit4(code);live[bit_at]=digit4(code>>2);
  dut.generations[s]=stored;reference.generations[s]=stored;acl_generation_i=live;check();
  live[(bit_at+1)%32]=~stored[(bit_at+1)%32];acl_generation_i=live;check();
 end
// Preserve last-match priority and unknown handle tests in the original loop.
for(s=0;s<SLOTS;s=s+1)for(code=0;code<16;code=code+1)begin base(s);
 for(at=0;at<SLOTS;at=at+1)begin dut.numbers[at]=12'h042;reference.numbers[at]=12'h042;end
 acl_handle_i=12'h042;acl_generation_i=32'h10203040+SLOTS-1;
 dut.active[s]=digit4(code);reference.active[s]=digit4(code);
 dut.numbers[s][5]=digit4(code>>2);reference.numbers[s][5]=digit4(code>>2);check();
end
// All error-chain preceding/following conditions remain in their original order.
for(s=0;s<SLOTS;s=s+1)for(code=0;code<16;code=code+1)begin base(s);
 dut.configured_o=digit4(code);reference.configured_o=digit4(code);
 dut.fault_o=digit4(code>>2);reference.fault_o=digit4(code>>2);
 acl_generation_i=32'hdeadbeef;acl_data_length_i=0;check();
end
// Even unreachable forced selectors retain memory/packed-select X behavior.
for(code=0;code<8;code=code+1)begin base(0);
 case(code)0:selector=-2;1:selector=-1;2:selector=0;3:selector=SLOTS-1;
  4:selector=SLOTS;5:selector=32'h7fffffff;6:selector=32'hxxxxxxxx;7:selector=32'hzzzzzzzz;endcase
 force dut.acl_slot=selector;force reference.acl_slot=selector;check();
 release dut.acl_slot;release reference.acl_slot;
end
$display("PASS FLOW FOUR STATE slots=%0d checks=%0d",SLOTS,checks);$finish;
end endmodule
'''
    return text, slots * (32 * 16 * 2 + 32 + (65536 if exhaustive else 0)) + 8


def simulate(out, label, candidate, bench, top, expected_pass=True):
    folder = out / label
    folder.mkdir()
    (folder / 'bench.sv').write_text(bench)
    compiled = subprocess.run(['iverilog', '-g2012', '-s', top, '-o', str(folder / 'bench.vvp'),
                               str(candidate), str(out / 'reference.sv'), str(folder / 'bench.sv')],
                              capture_output=True, text=True, timeout=60)
    (folder / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    require(compiled.returncode == 0, 'compile ' + label)
    ran = subprocess.run(['vvp', str(folder / 'bench.vvp')], capture_output=True, text=True, timeout=180)
    (folder / 'simulation.log').write_text(ran.stdout + ran.stderr)
    require((ran.returncode == 0) == expected_pass, 'simulation result ' + label + ': ' + ran.stdout[-1200:])
    return dict(exit_code=ran.returncode, summary=ran.stdout, expected_pass=expected_pass)


def symbolic():
    # Hand-lifted 4-state bit model: two independent known/value masks per operand.
    ak, av, bk, bv = z3.BitVecs('a_known a_value b_known b_value', 32)
    xk, xv = ak & bk, (av ^ bv) & ak & bk
    def reduction(known, value, bits):
        one = value != 0
        return z3.Or(one, known == (1 << bits) - 1), one
    direct = reduction(xk, xv, 32)
    groups = [reduction(z3.Extract(bit+7, bit, xk), z3.Extract(bit+7, bit, xv), 8) for bit in range(0, 32, 8)]
    one = z3.Or([v for _, v in groups])
    grouped = z3.Or(one, z3.And([k for k, _ in groups])), one
    solver = z3.Solver()
    solver.add(z3.Or(direct[0] != grouped[0], direct[1] != grouped[1]))
    require(solver.check() == z3.unsat, 'four-state symbolic relation')
    return dict(result='UNSAT', independent_input_bits=128, known_mismatch_dominates_unknown=True,
                reachability_assumptions=[], scope='Hand-lifted logical inequality/XOR/reduction relation; not formal SV elaboration or temporal proof',
                version=z3.get_version_string())


def legal_cancellation_bench(whole):
    stale = "acl_generation_i=le_gen^32'h80000000;"
    require(whole.count(stale) == 1, 'same-edge stale descriptor stimulus')
    legal = whole.replace(stale, 'acl_generation_i=le_gen;')
    anchor = 'check(!acl_ready_o,"same-edge cancel gates reject stale ACL immediately");tick();'
    require(legal.count(anchor) == 1, 'same-edge cancellation check')
    return legal.replace(anchor,
        'check(acl_error_o==0,"legal descriptor passes identity and length before cancellation");\n' +
        '            check(!acl_ready_o,"same-edge cancel gates reject legal ACL immediately");tick();')


def rejected_inverse_controls(source, reference):
    controls = {}
    cases = [
        ('inverse_extra_bytes', reverse_generation_groups, source + '// unreviewed\n'),
        ('inverse_keep_removed', reverse_generation_groups,
         source.replace('(* syn_keep=1 *)', '(* syn_keep=0 *)')),
        ('inverse_clocked_bytes_changed', reverse_generation_groups,
         source.replace('if (transport_fault_i) fail(F_TRANSPORT);',
                        'if (transport_fault_i) fail(F_ACL_SEND);')),
        ('forward_extra_bytes', apply_generation_groups, reference + '// unreviewed\n'),
    ]
    for label, transform, changed in cases:
        try:
            transform(changed)
        except ValueError as error:
            controls[label] = dict(rejected=True, reason=str(error))
        else:
            require(False, 'source drift control escaped ' + label)
    return controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    require(not out.exists() and out != REPO and REPO not in out.parents,
            'new external output directory required')
    out.mkdir(parents=True)
    helper = ROOT / 'sim/workstation_hci_flow_generation_sources.py'
    owner_runner = ROOT / 'sim/run_workstation_hci_owner.py'
    inputs = [FLOW, BENCH, helper, owner_runner, Path(__file__).resolve()]
    before = {str(path): sha(path) for path in inputs}
    source = FLOW.read_text()
    reference = reverse_generation_groups(source)
    require(apply_generation_groups(reference) == source, 'exact source inverse and forward')
    require(sha(FLOW) == FLOW_GENERATION_SHA256 and
            hashlib.sha256(reference.encode()).hexdigest() == PRE_FLOW_GENERATION_SHA256,
            'whole source pin and reconstructed reference identity')
    edge = '    always @(posedge clk_i) begin\n'
    require(source.count(edge) == reference.count(edge) == 1 and
            source.split(edge, 1)[1] == reference.split(edge, 1)[1], 'all clocked bytes unchanged')
    (out / 'before-groups.sv').write_text(reference)
    (out / 'reference.sv').write_text(reference.replace('module workstation_hci_flow_owner #(',
                                                      'module workstation_hci_flow_owner_reference #(', 1))
    report = dict(schema=1, passed=False, stage='maintained_flow_acl_generation_grouping',
        inputs_sha256=before, source_sha256=FLOW_GENERATION_SHA256,
        reference_sha256=PRE_FLOW_GENERATION_SHA256, exact_inverse_and_forward=True,
        all_clocked_bytes_unchanged=True,
        clocked_bytes_sha256=hashlib.sha256(source.split(edge, 1)[1].encode()).hexdigest(),
        actual_default_handle_slots=2, supported_handle_slots=[1, 16], byte_groups_per_generation=4,
        symbolic=symbolic(), synthesis=False, pnr=False, hardware_tested=False,
        physical_gain_measured=False, deployment_allowed=False,
        source_controls=rejected_inverse_controls(source, reference))
    whole = whole_bench(reference)
    legal = legal_cancellation_bench(whole)
    report['whole_owner'] = {}
    for label, bench in [('stale-acl', whole), ('legal-acl', legal)]:
        result = simulate(out, 'whole-owner-' + label, FLOW, bench, 'tb_workstation_hci_flow_owner')
        require('PASS checks=' in result['summary'] and 'same_edge_priority_scenarios=4' in result['summary']
                and 'FLOW GENERATION TWIN cycles=' in result['summary'], 'whole owner summary inventory')
        report['whole_owner'][label] = result
        print(result['summary'], flush=True)
    report['four_state'] = {}
    for slots in (1, 2, 16):
        bench, count = four_state_bench(reference, slots, slots == 2)
        result = simulate(out, 'four-state-' + str(slots), FLOW, bench, 'tb')
        require('checks=' + str(count) in result['summary'], 'four-state coverage inventory')
        report['four_state'][str(slots)] = dict(result, checks=count)
        print(result['summary'], flush=True)
    mutations = {
        'ignore_high_byte': ('|acl_generation_changed_groups[generation_slot*4+:4]',
                             '|acl_generation_changed_groups[generation_slot*4+:3]'),
        'invert_result': ('|acl_generation_changed_groups[generation_slot*4+:4]',
                          '~|acl_generation_changed_groups[generation_slot*4+:4]'),
        'collapse_unknown': ('|(acl_generation_i[generation_group*8+:8]^\n'
                             '                  generations[generation_slot][generation_group*8+:8])',
                             '(acl_generation_i[generation_group*8+:8]!==\n'
                             '                  generations[generation_slot][generation_group*8+:8])'),
        'wrong_slot_word': ('generations[generation_slot][generation_group*8+:8]',
                            'generations[(generation_slot+1)%HANDLE_SLOTS][generation_group*8+:8]'),
    }
    report['actual_module_mutants'] = {}
    fs, _ = four_state_bench(reference, 2, False)
    for label, (old, new) in mutations.items():
        require(source.count(old) == 1 and old in GROUPS, 'actual grouped predicate mutant anchor ' + label)
        path = out / (label + '.sv')
        path.write_text(source.replace(old, new, 1))
        result = simulate(out, 'mutant-' + label, path, fs, 'tb', False)
        require('FLOW FOUR STATE' in result['summary'], 'actual predicate mutant failure attribution')
        report['actual_module_mutants'][label] = result
    for label, old, new in [
        ('transport_priority_corrupted', 'if (transport_fault_i) fail(F_TRANSPORT);',
         'if (transport_fault_i) fail(F_ACL_SEND);'),
        ('timeout_priority_corrupted', 'if (command_pending_o) fail(F_COMMAND_TIMEOUT);',
         'if (command_pending_o) fail(F_ACL_SEND);')]:
        require(source.count(old) == 1, 'clocked priority mutant anchor ' + label)
        path = out / (label + '.sv')
        path.write_text(source.replace(old, new, 1))
        result = simulate(out, 'mutant-' + label, path, whole, 'tb_workstation_hci_flow_owner', False)
        require('FATAL:' in result['summary'], 'clocked priority mutant failure attribution')
        report['actual_module_mutants'][label] = result
    gate = '!transport_fault_i && !command_timeout_i && !response_bad;'
    require(source.count(gate) == 1, 'exact immediate ACL cancellation gate')
    for label, term in [('transport_gate_removed', '!transport_fault_i'),
                        ('timeout_gate_removed', '!command_timeout_i')]:
        path = out / (label + '.sv')
        path.write_text(source.replace(gate, gate.replace(term, "1'b1"), 1))
        result = simulate(out, 'mutant-' + label, path, legal, 'tb_workstation_hci_flow_owner', False)
        require('FAIL ' in result['summary'] and 'FATAL:' in result['summary'],
                'immediate cancellation mutant failure attribution')
        report['actual_module_mutants'][label] = result
    require(before == {str(path): sha(path) for path in inputs}, 'inputs changed during verification')
    report['source_seal_before_after'] = True
    report['tools'] = {name: dict(path=shutil.which(name), sha256=sha(shutil.which(name)))
                       for name in ('iverilog', 'vvp')}
    report['passed'] = True
    report['outputs_sha256'] = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    write_json(out / 'verification.json', report)
    print(json.dumps(dict(output=str(out), passed=True,
        four_state_checks=sum(case['checks'] for case in report['four_state'].values()),
        actual_module_mutants=len(report['actual_module_mutants']),
        source_drift_controls=len(report['source_controls']), sha256=sha(out / 'verification.json'))))


if __name__ == '__main__':
    main()
