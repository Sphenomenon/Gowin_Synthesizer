#!/usr/bin/env python3
"""Source-bound known-generation grouping and complete HCI owner checks.

The old module is reconstructed by an exact, hash-bound inverse. This runner
checks the actual complete modules, including X/Z, without changing cycles or
using a private build tree as a production source. It makes no timing claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import z3

from run_workstation_hci_action_drift import (
    HOST, OWNER, ROOT, REPO, KNOWN_GROUPS, KNOWN_GROUPS_SHA256,
    PRE_KNOWN_GROUPS_SHA256, apply_known_groups, reverse_known_groups,
)
import run_workstation_hci_identity_compare as identity


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('HCI known generation grouping: ' + message)


def command(args, log, timeout=180):
    result = subprocess.run(list(map(str, args)), text=True, capture_output=True, timeout=timeout)
    log.write_text(result.stdout + result.stderr)
    return result


def symbolic():
    # A four-state bit has a known mask and a value when known. X and Z both
    # become X under XOR. These are arbitrary 128 input bits, with no reachable
    # state or binary-input assumptions. This is a hand-lifted local relation,
    # not a formal SystemVerilog elaboration or whole-owner temporal proof.
    ak, av, bk, bv = z3.BitVecs('stored_known stored_value live_known live_value', 32)
    xor_known = ak & bk
    xor_value = (av ^ bv) & xor_known

    def reduction(known, value, bits):
        one = value != 0
        return z3.Or(one, known == (1 << bits) - 1), one

    direct = reduction(xor_known, xor_value, 32)
    groups = [reduction(z3.Extract(i + 7, i, xor_known),
                        z3.Extract(i + 7, i, xor_value), 8) for i in range(0, 32, 8)]
    any_one = z3.Or([value for _, value in groups])
    grouped = z3.Or(any_one, z3.And([known for known, _ in groups])), any_one
    solver = z3.Solver()
    solver.add(z3.Or(direct[0] != grouped[0], direct[1] != grouped[1]))
    require(solver.check() == z3.unsat, 'arbitrary four-state relation')
    return dict(result='UNSAT', independent_input_bits=128, reachability_assumptions=[],
                scope='hand-lifted XOR and reduction relation; no formal SV elaboration')


def four_state_bench(source, slots, exhaustive):
    spec = identity.ports(source.replace('HANDLE_SLOTS', str(slots)))
    text = 'module tb;\nlocalparam integer SLOTS=' + str(slots) + ';\n'
    for name, (direction, width) in spec.items():
        text += ('reg ' + width + ' ' + name + "='0;\n" if direction == 'input' else
                 'wire ' + width + ' ' + name + ',ref_' + name + ';\n')
    for module, who in [('workstation_hci_host_rx_owner', 'dut'),
                        ('workstation_hci_host_rx_owner_reference', 'reference')]:
        text += module + ' #(.HANDLE_SLOTS(SLOTS)) ' + who + '(' + ','.join(
            '.' + name + '(' + (name if direction == 'input' or who == 'dut' else 'ref_' + name) + ')'
            for name, (direction, _) in spec.items()) + ');\n'
    outputs = [name for name, (direction, _) in spec.items() if direction == 'output']
    text += '''integer at,k,j,s,bit_at,code,checks=0;reg [31:0] stored,live;
function digit4(input integer number);case(number&3)
0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase endfunction
task base(input integer target);begin
 known_active_i='1;known_is_le_i='1;known_handles_i=0;known_generations_i=0;
 for(at=0;at<SLOTS;at=at+1)begin
  known_handles_i[at*12+:12]=at+1;known_generations_i[at*32+:32]=32'h01020304+at;
  dut.handles[at]=at+1;reference.handles[at]=at+1;
  dut.generations[at]=32'h01020304+at;reference.generations[at]=32'h01020304+at;
  dut.outstanding[at]=(at==target);reference.outstanding[at]=(at==target);
  dut.pending[at]=0;reference.pending[at]=0;
 end
 disconnect_valid_i=0;disconnect_handle_i=target+1;disconnect_generation_i=32'h01020304+target;
 rx_handle_i=target+1;rx_data_length_i=1;rx_valid_i=0;rx_take_i=0;rx_want_lease_i=1;
 release_valid_i=0;release_lease_i=0;return_send_i=0;return_transport_done_i=0;
 transport_fault_i=0;activate_i=0;return_address_i=0;
end endtask
task check;begin #1;
 for(at=0;at<SLOTS;at=at+1)begin
  if(dut.known_generation_changed[at] !==
     (|(reference.generations[at]^known_generations_i[at*32+:32])))
   $fatal(1,"known generation four-state mismatch checks=%0d handle=%0d",checks,at);
 end
 if({dut.owner_drift,dut.action_owner_drift,dut.action_owner_drift_fence} !==
    {reference.owner_drift,reference.action_owner_drift,reference.action_owner_drift_fence})
  $fatal(1,"known generation four-state mismatch drift checks=%0d",checks);
'''
    text += '\n'.join(' if(' + name + ' !== ref_' + name + ')$fatal(1,"known generation four-state mismatch output ' +
                      name + ' checks=%0d",checks);' for name in outputs)
    text += '\n checks=checks+1;end endtask\ninitial begin\n'
    # Stop the clock and seed identical complete storage. Icarus does not
    # support force on memory words, so array words use hierarchical assignment.
    for who in ('dut', 'reference'):
        for assignment in ('active_o=1', 'fault_o=0', 'fault_reason_o=0', 'controller_budget_o=3',
                           'leased=0', 'retired=0', 'last_lease=0', 'offered=1',
                           'offer_handle=1', 'offer_generation=1', 'offer_count=1', 'offer_slot=0',
                           'return_inflight_o=0', 'lease_granted_o=0', 'rx_dropped_o=0', 'rx_is_le_o=0',
                           'rx_drop_reason_o=0', 'rx_slot_o=0', 'rx_lease_o=0', 'rx_generation_o=0',
                           'release_rejected_o=0', 'dropped_packets_o=0', 'rejected_releases_o=0'):
            text += ' ' + who + '.' + assignment + ';\n'
        text += ' for(at=0;at<4;at=at+1)begin ' + ''.join(
            who + '.' + name + '[at]=0;' for name in ('tokens', 'lease_generations', 'lease_handles')) + 'end\n'
    if exhaustive:
        text += '''for(s=0;s<SLOTS;s=s+1)begin base(s);
 for(k=0;k<65536;k=k+1)begin
  stored=0;live=0;
  stored[0]=digit4(k);stored[7]=digit4(k>>2);stored[8]=digit4(k>>4);stored[31]=digit4(k>>6);
  live[0]=digit4(k>>8);live[7]=digit4(k>>10);live[8]=digit4(k>>12);live[31]=digit4(k>>14);
  dut.generations[s]=stored;reference.generations[s]=stored;known_generations_i[s*32+:32]=live;check();
 end
end
'''
    text += '''for(s=0;s<SLOTS;s=s+1)for(bit_at=0;bit_at<32;bit_at=bit_at+1)
 for(code=0;code<16;code=code+1)begin base(s);
  stored=32'h5a69c3e7;live=stored;stored[bit_at]=digit4(code);live[bit_at]=digit4(code>>2);
  dut.generations[s]=stored;reference.generations[s]=stored;known_generations_i[s*32+:32]=live;
  for(j=0;j<4;j=j+1)begin disconnect_valid_i=digit4(j);check();end
  // A known mismatch must dominate independent X/Z in a different byte/bit.
  live[(bit_at+1)%32]=~stored[(bit_at+1)%32];known_generations_i[s*32+:32]=live;
  for(j=0;j<4;j=j+1)begin disconnect_valid_i=digit4(j);check();end
 end
$display("PASS known generation actual owner four-state slots=%0d checks=%0d",SLOTS,checks);$finish;
end endmodule
'''
    return text, slots * (32 * 16 * 8 + (65536 if exhaustive else 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    require(not out.exists() and out != REPO and REPO not in out.parents, 'new external output required')
    out.mkdir(parents=True)
    source = HOST.read_text()
    reference = reverse_known_groups(source)
    require(apply_known_groups(reference) == source, 'exact inverse and forward')
    edge = '    always @(posedge clk_i)begin\n'
    require(source.count(edge) == reference.count(edge) == 1 and
            source.split(edge, 1)[1] == reference.split(edge, 1)[1], 'all clocked bytes unchanged')
    inputs = [HOST, OWNER / 'workstation_hci_flow_owner.sv', Path(__file__).resolve(),
              ROOT / 'sim/run_workstation_hci_action_drift.py',
              ROOT / 'sim/run_workstation_hci_identity_compare.py',
              ROOT / 'sim/tb_workstation_hci_host_rx_owner.sv']
    before = {str(path): sha(path) for path in inputs}
    report = dict(passed=False, inputs_sha256=before, source_sha256=KNOWN_GROUPS_SHA256,
                  reference_sha256=PRE_KNOWN_GROUPS_SHA256,
                  exact_source_inverse=True, all_clocked_bytes_unchanged=True,
                  clocked_bytes_sha256=hashlib.sha256(source.split(edge, 1)[1].encode()).hexdigest(),
                  symbolic=symbolic(), physical_timing_gain_claimed=False, hardware_tested=False)
    original = out / 'before-known-generation-groups.sv'
    original.write_text(reference)
    ref = out / 'reference.sv'
    ref.write_text(reference.replace('module workstation_hci_host_rx_owner',
                                     'module workstation_hci_host_rx_owner_reference', 1))
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
    report['four_state'] = {}
    for slots in (1, 2, 16):
        bench, count = four_state_bench(reference, slots, slots == 2)
        tb = out / ('four-state-' + str(slots) + '-tb.sv')
        tb.write_text(bench)
        binary = out / ('four-state-' + str(slots) + '.vvp')
        result = command(['iverilog', '-g2012', '-s', 'tb', '-o', binary, tb, HOST, ref],
                         out / ('four-state-' + str(slots) + '-compile.log'), 60)
        require(result.returncode == 0, 'actual owner four-state compile slots=' + str(slots))
        result = command(['vvp', binary], out / ('four-state-' + str(slots) + '-run.log'))
        require(result.returncode == 0 and 'checks=' + str(count) in result.stdout,
                'actual owner four-state slots=' + str(slots))
        report['four_state'][str(slots)] = dict(checks=count, summary=result.stdout)
    mutations = {
        'ignore_high_byte': ('|known_generation_changed_groups[known_handle*4+:4]',
                             '|known_generation_changed_groups[known_handle*4+:3]'),
        'invert_result': ('|known_generation_changed_groups[known_handle*4+:4]',
                          '~|known_generation_changed_groups[known_handle*4+:4]'),
        'collapse_unknown': ('|(generations[known_handle][known_group*8+:8]^\n'
                             '                  known_generations_i[known_handle*32+known_group*8+:8])',
                             '(generations[known_handle][known_group*8+:8]!==\n'
                             '                  known_generations_i[known_handle*32+known_group*8+:8])'),
        'wrong_handle_word': ('known_generations_i[known_handle*32+known_group*8+:8]',
                              'known_generations_i[((known_handle+1)%HANDLE_SLOTS)*32+known_group*8+:8]'),
    }
    report['actual_module_mutants'] = {}
    for label, (old, new) in mutations.items():
        require(source.count(old) == 1 and old in KNOWN_GROUPS, 'actual module mutant anchor ' + label)
        mutant = out / (label + '.sv')
        mutant.write_text(source.replace(old, new, 1))
        binary = out / (label + '.vvp')
        result = command(['iverilog', '-g2012', '-s', 'tb', '-o', binary,
                          out / 'four-state-2-tb.sv', mutant, ref], out / (label + '-compile.log'), 60)
        require(result.returncode == 0, 'actual module mutant compile ' + label)
        result = command(['vvp', binary], out / (label + '-run.log'))
        require(result.returncode != 0 and 'known generation four-state mismatch' in result.stdout,
                'actual module negative escaped ' + label)
        report['actual_module_mutants'][label] = dict(expected_rejection=True,
                                                     exit_code=result.returncode, summary=result.stdout)
    report['inverse_source_controls'] = {}
    for label, text in [('unreviewed_bytes', source + '// unreviewed\n'),
                        ('keep_removed', source.replace('(* syn_keep=1 *) wire [HANDLE_SLOTS*4-1:0] known_generation_changed_groups;',
                                                       '(* syn_keep=0 *) wire [HANDLE_SLOTS*4-1:0] known_generation_changed_groups;'))]:
        try:
            reverse_known_groups(text)
        except ValueError as error:
            report['inverse_source_controls'][label] = dict(rejected=True, reason=str(error))
        else:
            require(False, 'inverse source control escaped ' + label)
    require(before == {str(path): sha(path) for path in inputs}, 'input drift during verification')
    report['passed'] = True
    report['outputs_sha256'] = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(output=str(out), passed=True, whole_owner=report['whole_owner'],
                          four_state_checks=sum(case['checks'] for case in report['four_state'].values()),
                          actual_module_mutants=len(mutations))))


if __name__ == '__main__':
    main()
