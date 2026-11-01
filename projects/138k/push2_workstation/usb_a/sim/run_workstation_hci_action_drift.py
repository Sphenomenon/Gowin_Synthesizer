#!/usr/bin/env python3
"""Source-bound action drift cofactor, full owner twin, four-state controls.

The reference is reconstructed by the exact reviewed inverse and must retain
its immutable pre-action identity. No private build tree or generated RTL is a
production input. This verifies source behavior, not physical timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import z3

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
OWNER = ROOT / 'rtl/bluetooth/hci_owner'
HOST = OWNER / 'workstation_hci_host_rx_owner.sv'
PRE_ACTION_SHA256 = '271e3d701eb8f84e238ac9ccf3114c2669ef44e09d56407fc22afb1e5e9785ea'
PRE_KNOWN_GROUPS_SHA256 = '20f45bf00fbb23ca09512d35f4bfff4273e3d4d865d56fc03bdb2e89a342b13f'
KNOWN_GROUPS_SHA256 = '6547173e42b6057dedb9ec5fe22ba3dbcda957c7f6344fcda98a39643be7fc88'
KNOWN_GROUPS_ANCHOR = '    // Action readiness excludes a known disconnect edge. Preserve the full\n'
KNOWN_GENERATION_EXPRESSION = '(|(generations[at]^known_generations_i[32*at+:32]))'
KNOWN_GENERATION_TREE = 'known_generation_changed[at]'
KNOWN_GROUPS = '''    // Compare each stored/live generation before the drift predicates.
    // Keep byte boundaries explicit so equality cannot become a serial carry.
    (* syn_keep=1 *) wire [HANDLE_SLOTS*4-1:0] known_generation_changed_groups;
    wire [HANDLE_SLOTS-1:0] known_generation_changed;
    for(genvar known_handle=0;known_handle<HANDLE_SLOTS;known_handle=known_handle+1)begin:known_identity
        for(genvar known_group=0;known_group<4;known_group=known_group+1)begin:g_generation
            assign known_generation_changed_groups[known_handle*4+known_group]=
                |(generations[known_handle][known_group*8+:8]^
                  known_generations_i[known_handle*32+known_group*8+:8]);
        end
        assign known_generation_changed[known_handle]=
            |known_generation_changed_groups[known_handle*4+:4];
    end
'''
ACTION_FENCE = '''    // Action readiness excludes a known disconnect edge. Preserve the full
    // owner drift for real disconnect/fault processing and unknown controls.
    (* syn_keep=1 *) reg action_owner_drift_fence;
    always @* begin
        case(disconnect_valid_i)
            1'b0,1'b1:action_owner_drift_fence=action_owner_drift;
            default:action_owner_drift_fence=owner_drift;
        endcase
    end
'''
ACTION_BASE = '''outstanding[at]!=0&&(!known_active_i[at]||(|(handles[at]^known_handles_i[12*at+:12]))||
                (|(generations[at]^known_generations_i[32*at+:32])))'''
ACTION_CHANGES = (
    ('reg owner_drift,invariant_bad;', 'reg owner_drift,action_owner_drift,invariant_bad;', 1),
    ('    always @* begin\n        rx_owner=-1;', ACTION_FENCE + '    always @* begin\n        rx_owner=-1;', 1),
    ('return_candidate=-1;owner_drift=0;', 'return_candidate=-1;owner_drift=0;action_owner_drift=0;', 1),
    ('            if(' + ACTION_BASE + '&&', '            if(' + ACTION_BASE + ')action_owner_drift=1;\n            if(' + ACTION_BASE + '&&', 1),
    ('!owner_drift', '!action_owner_drift_fence', 3),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('HCI action drift: ' + message)


def apply_action_transform(text):
    require(hashlib.sha256(text.encode()).hexdigest() == PRE_ACTION_SHA256, 'pre-action source identity')
    for before, after, count in ACTION_CHANGES:
        require(text.count(before) == count, 'forward anchor ' + before)
        text = text.replace(before, after)
    return text


def apply_known_groups(text):
    require(hashlib.sha256(text.encode()).hexdigest() == PRE_KNOWN_GROUPS_SHA256,
            'pre-known-generation-group source identity')
    require(text.count(KNOWN_GROUPS_ANCHOR) == 1 and text.count(KNOWN_GENERATION_EXPRESSION) == 2,
            'known-generation-group forward anchors')
    result = text.replace(KNOWN_GROUPS_ANCHOR, KNOWN_GROUPS + KNOWN_GROUPS_ANCHOR, 1).replace(
        KNOWN_GENERATION_EXPRESSION, KNOWN_GENERATION_TREE)
    require(hashlib.sha256(result.encode()).hexdigest() == KNOWN_GROUPS_SHA256,
            'complete grouped known-generation source identity')
    return result


def reverse_known_groups(text):
    require(hashlib.sha256(text.encode()).hexdigest() == KNOWN_GROUPS_SHA256,
            'grouped known-generation source identity')
    require(text.count(KNOWN_GROUPS) == 1 and text.count(KNOWN_GENERATION_TREE) == 2,
            'known-generation-group inverse anchors')
    result = text.replace(KNOWN_GROUPS, '', 1).replace(KNOWN_GENERATION_TREE, KNOWN_GENERATION_EXPRESSION)
    require(hashlib.sha256(result.encode()).hexdigest() == PRE_KNOWN_GROUPS_SHA256,
            'exact pre-known-generation-group identity')
    return result


def reverse_action_transform(text):
    if hashlib.sha256(text.encode()).hexdigest() == KNOWN_GROUPS_SHA256:
        text = reverse_known_groups(text)
    for before, after, count in reversed(ACTION_CHANGES):
        require(text.count(after) == count, 'inverse anchor ' + after)
        text = text.replace(after, before)
    require(hashlib.sha256(text.encode()).hexdigest() == PRE_ACTION_SHA256,
            'unreviewed bytes outside exact action transform')
    return text


def symbolic(source, reference):
    norm = lambda text: re.sub(r'\s+', '', text)
    base = re.search(r'if\((outstanding\[at\]!=0&&.*?)\)action_owner_drift=1;', source, re.S)[1]
    full = re.search(r'if\((outstanding\[at\]!=0&&.*?)\)owner_drift=1;', reference, re.S)[1]
    exception = 'disconnect_valid_i&&!(|(handles[at]^disconnect_handle_i))&&!disconnect_generation_changed[at]'
    require(norm(full) == norm(base) + '&&!(' + norm(exception) + ')', 'actual full/base drift equations')
    # The original full drift statement remains present byte-for-byte.
    require(('if(' + full + ')owner_drift=1;') in source, 'full drift changed')
    for name in ('rx_ready_o', 'release_ready_o', 'return_can_send_o'):
        old = re.search(r'assign ' + name + r'=(.*?);', reference, re.S)[1]
        new = re.search(r'assign ' + name + r'=(.*?);', source, re.S)[1]
        require(new.replace('!action_owner_drift_fence', '!owner_drift') == old and
                old.count('!disconnect_valid_i') == 1, 'guarded consumer ' + name)
    require(source.count(ACTION_FENCE) == 1, 'binary cofactor and X/Z fallback boundary')
    sym = lambda x: (x == 0, x == 1)
    both = lambda xs: (z3.Or([x[0] for x in xs]), z3.And([x[1] for x in xs]))
    invert = lambda x: (x[1], x[0])
    boolean = lambda x: (z3.Not(x), x)
    same = lambda a, b: z3.And(a[0] == b[0], a[1] == b[1])
    proofs = []
    for slots in (1, 2, 16):
        valid = z3.Bool('disconnect_valid')
        bases = [z3.Bool('base_' + str(i)) for i in range(slots)]
        matches = [z3.Bool('match_' + str(i)) for i in range(slots)]
        full_binary = z3.Or([z3.And(a, z3.Not(z3.And(valid, m))) for a, m in zip(bases, matches)])
        local_binary = z3.Or(bases)
        other = z3.Bool('all_other_action_qualifications')
        solver = z3.Solver()
        solver.add(z3.And(other, z3.Not(valid), z3.Not(full_binary)) !=
                   z3.And(other, z3.Not(valid), z3.Not(local_binary)))
        require(solver.check() == z3.unsat, 'binary cofactor ' + str(slots))
        raw = z3.BitVec('valid4', 2)
        valid4 = sym(raw)
        bases4 = [sym(z3.BitVec('base4_' + str(i), 2)) for i in range(slots)]
        matches4 = [sym(z3.BitVec('match4_' + str(i), 2)) for i in range(slots)]
        other4 = sym(z3.BitVec('all_other_ready_terms4', 2))
        # Procedural if only acts on a known true predicate.
        full4 = z3.Or([both([a, invert(both([valid4, m]))])[1] for a, m in zip(bases4, matches4)])
        local4 = z3.Or([a[1] for a in bases4])
        fence = z3.If(z3.Or(raw == 0, raw == 1), local4, full4)
        original = both([other4, invert(valid4), invert(boolean(full4))])
        proposed = both([other4, invert(valid4), invert(boolean(fence))])
        solver = z3.Solver()
        solver.add(z3.Not(same(original, proposed)))
        require(solver.check() == z3.unsat, 'four-state cofactor ' + str(slots))
        proofs.append(dict(HANDLE_SLOTS=slots, binary='UNSAT', four_state='UNSAT', reachability_assumptions=[]))
        if slots == 2:
            mutant = both([other4, invert(valid4), invert(boolean(local4))])
            solver = z3.Solver()
            solver.add(z3.Not(same(original, mutant)))
            require(solver.check() == z3.sat, 'unconditional fallback symbolic mutant escaped')
            negative = dict(result='SAT', mutation='unconditional base fallback', witness=str(solver.model()))
    return dict(source_equations_audited=True, source_procedural_if_truth_preserved=True,
                proofs=proofs, negative=negative, scope='local arbitrary-state cofactor; not whole-owner temporal proof')


def command(args, log, timeout=180):
    result = subprocess.run(list(map(str, args)), text=True, capture_output=True, timeout=timeout)
    log.write_text(result.stdout + result.stderr)
    return result


def four_state_bench(spec):
    text = 'module tb;\n'
    for name, (direction, width) in spec.items():
        text += ('reg ' + width + ' ' + name + "='0;\n" if direction == 'input' else
                 'wire ' + width + ' ' + name + ',ref_' + name + ';\n')
    text += 'workstation_hci_host_rx_owner dut(' + ','.join('.' + name + '(' + name + ')' for name in spec) + ');\n'
    text += 'workstation_hci_host_rx_owner_reference reference(' + ','.join(
        '.' + name + '(' + (name if direction == 'input' else 'ref_' + name) + ')'
        for name, (direction, _) in spec.items()) + ');\n'
    text += '''reg [15:0] out0=0,out1=0;reg [11:0] handle0=0,handle1=0;reg [31:0] gen0=0,gen1=0;
integer k,j,checks=0;reg [31:0] rng=32'h582e931b;
function digit4(input integer code);case(code&3)0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase endfunction
function random4();begin rng=(rng>>1)^((rng&1)?32'h80200003:0);random4=digit4(rng[1:0]);end endfunction
task check;begin
 dut.outstanding[0]=out0;dut.handles[0]=handle0;dut.generations[0]=gen0;
 dut.outstanding[1]=out1;dut.handles[1]=handle1;dut.generations[1]=gen1;
 reference.outstanding[0]=out0;reference.handles[0]=handle0;reference.generations[0]=gen0;
 reference.outstanding[1]=out1;reference.handles[1]=handle1;reference.generations[1]=gen1;#1;
 if({rx_ready_o,release_ready_o,return_can_send_o}!=={ref_rx_ready_o,ref_release_ready_o,ref_return_can_send_o})
 $fatal(1,"action drift four-state mismatch vector=%0d valid=%b drift=%b base=%b ready=%b/%b",checks,disconnect_valid_i,reference.owner_drift,dut.action_owner_drift,rx_ready_o,ref_rx_ready_o);
 checks=checks+1;end endtask
initial begin
'''
    # Expose the changed cone through real public outputs. The clock stays
    # stopped while stored array words are assigned; Icarus cannot force them.
    for who in ('dut', 'reference'):
        text += '\n'.join('force ' + who + '.' + term + ';' for term in (
            'active_o=1', 'fault_o=0', 'controller_budget_o=1', 'return_inflight_o=0',
            'offered=1', 'invariant_bad=0', 'rx_schema_good=1')) + '\n'
    return text + '''known_handles_i=0;known_generations_i=0;disconnect_handle_i=0;disconnect_generation_i=0;
for(k=0;k<16384;k=k+1)begin
 disconnect_valid_i=digit4(k);known_active_i[0]=digit4(k>>2);known_active_i[1]=digit4(k>>4);
 out0=0;out1=0;out0[0]=digit4(k>>6);out1[0]=digit4(k>>8);
 gen0=0;gen1=0;gen0[0]=digit4(k>>10);gen1[0]=digit4(k>>12);
 disconnect_generation_i=0;disconnect_generation_i[0]=random4();check();end
for(k=0;k<131072;k=k+1)begin
 disconnect_valid_i=random4();known_active_i[0]=random4();known_active_i[1]=random4();
 for(j=0;j<16;j=j+1)begin out0[j]=random4();out1[j]=random4();end
 for(j=0;j<12;j=j+1)begin handle0[j]=random4();handle1[j]=random4();disconnect_handle_i[j]=random4();known_handles_i[j]=random4();known_handles_i[j+12]=random4();end
 for(j=0;j<32;j=j+1)begin gen0[j]=random4();gen1[j]=random4();disconnect_generation_i[j]=random4();known_generations_i[j]=random4();known_generations_i[j+32]=random4();end
 check();end
out0=1;out1=0;gen0=0;gen1=0;handle0=0;handle1=0;known_active_i=0;
known_handles_i=0;known_generations_i=0;disconnect_handle_i=0;
for(k=0;k<4;k=k+1)begin disconnect_valid_i=digit4(k);disconnect_generation_i=0;disconnect_generation_i[0]=1'bx;check();disconnect_generation_i[0]=1'bz;check();end
if(checks!=147464)$fatal(1,"coverage");$display("PASS complete owner action drift four-state checks=%0d",checks);$finish;end
endmodule
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    require(not out.exists() and out != REPO and REPO not in out.parents, 'new external output required')
    out.mkdir(parents=True)
    source = HOST.read_text()
    action_source = reverse_known_groups(source)
    old = reverse_action_transform(source)
    require(apply_known_groups(apply_action_transform(old)) == source, 'exact reviewed forward/inverse')
    # No mutable cache or historical staging dependency is required.
    original = out / 'pre-action-source.sv'
    original.write_text(old)
    inputs = [HOST, OWNER / 'workstation_hci_flow_owner.sv', Path(__file__).resolve(),
              ROOT / 'sim/run_workstation_hci_identity_compare.py', ROOT / 'sim/tb_workstation_hci_host_rx_owner.sv']
    before = {str(p): sha(p) for p in inputs}
    report = dict(passed=False, inputs_sha256=before, exact_pre_action_inverse_sha256=sha(original),
                  exact_pre_known_groups_inverse_sha256=hashlib.sha256(action_source.encode()).hexdigest(),
                  symbolic=symbolic(action_source, old), physical_timing_gain_claimed=False, hardware_tested=False)
    ref = out / 'reference.sv'
    ref.write_text(old.replace('module workstation_hci_host_rx_owner', 'module workstation_hci_host_rx_owner_reference', 1))
    import run_workstation_hci_identity_compare as identity
    bench, metrics = identity.twin_bench('host_rx_owner', reference_path=original)
    tb = out / 'whole-owner-tb.sv'
    tb.write_text(bench)
    binary = out / 'whole-owner.vvp'
    result = command(['iverilog', '-g2012', '-s', 'tb_workstation_hci_host_rx_owner', '-o', binary,
                      OWNER / 'workstation_hci_flow_owner.sv', HOST, ref, tb], out / 'whole-compile.log', 60)
    require(result.returncode == 0, 'whole owner compile')
    result = command(['vvp', binary], out / 'whole-run.log')
    require(result.returncode == 0 and 'IDENTITY TWIN' in result.stdout and 'PASS checks=' in result.stdout,
            'whole source owner twin')
    report['whole_owner'] = dict(metrics, summary=result.stdout, exit_code=result.returncode)
    tb = out / 'four-state-tb.sv'
    tb.write_text(four_state_bench(identity.ports(old)))
    actual_action_base = ACTION_BASE.replace(KNOWN_GENERATION_EXPRESSION, KNOWN_GENERATION_TREE)
    mutants = {
        'unconditional_fallback': ('default:action_owner_drift_fence=owner_drift;', 'default:action_owner_drift_fence=action_owner_drift;'),
        'missing_outstanding_guard': ('if(' + actual_action_base + ')action_owner_drift=1;',
                                      'if(' + actual_action_base.replace('outstanding[at]!=0&&', '', 1) + ')action_owner_drift=1;'),
        'missing_disconnect_ready_guard': ('!activate_i&&!(return_transport_done_i&&!return_inflight_o)&&\n        !disconnect_valid_i&&!rx_valid_i&&!release_valid_i&&!action_owner_drift_fence',
                                           '!activate_i&&!(return_transport_done_i&&!return_inflight_o)&&\n        !rx_valid_i&&!release_valid_i&&!action_owner_drift_fence'),
    }
    report['four_state_cases'] = {}
    for label, mutation in [('positive', None), *mutants.items()]:
        text = source
        if mutation:
            a, b = mutation
            require(text.count(a) == 1, 'actual-module mutant anchor ' + label)
            text = text.replace(a, b, 1)
        case = out / (label + '.sv')
        case.write_text(text)
        binary = out / (label + '.vvp')
        result = command(['iverilog', '-g2012', '-s', 'tb', '-o', binary, tb, case, ref], out / (label + '-compile.log'), 60)
        require(result.returncode == 0, 'four-state compile ' + label)
        result = command(['vvp', binary], out / (label + '-run.log'))
        if mutation:
            require(result.returncode != 0 and 'action drift four-state mismatch' in result.stdout,
                    'actual-module negative escaped ' + label)
        else:
            require(result.returncode == 0 and 'checks=147464' in result.stdout, 'four-state positive')
        report['four_state_cases'][label] = dict(exit_code=result.returncode, expected_rejection=bool(mutation),
                                               source_sha256=sha(case), summary=result.stdout)
    report['inverse_source_controls'] = {}
    for label, text in [('unreviewed_bytes', source + '// unreviewed\n'),
                        ('keep_removed', source.replace('(* syn_keep=1 *) reg action_owner_drift_fence;',
                                                       '(* syn_keep=0 *) reg action_owner_drift_fence;'))]:
        try:
            reverse_action_transform(text)
        except ValueError as error:
            report['inverse_source_controls'][label] = dict(rejected=True, reason=str(error))
        else:
            require(False, 'inverse source control escaped ' + label)
    require(before == {str(p): sha(p) for p in inputs}, 'source drift during verification')
    report['passed'] = True
    report['outputs_sha256'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(output=str(out), passed=True, whole_owner=report['whole_owner'],
                          four_state_vectors=147464, actual_module_mutants=len(mutants))))


if __name__ == '__main__':
    main()
