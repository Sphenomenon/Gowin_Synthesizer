#!/usr/bin/env python3
"""Compare exact owned-transfer factoring with the complete W10 mux owner."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import z3

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'rtl/memory/workstation_recording_ddr_owner_mux.sv'
REFERENCE = Path(__file__).with_name('fixtures') / 'workstation_recording_ddr_owner_mux_before_owned_factor.sv'
TB = Path(__file__).with_name('tb_recording_ddr_owner_mux.sv')
OLD_SHA = '2af5a52d3bf9c67f93eef803e07bd9b9e636c1f65348676289dc13b487e76bf5'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('recording owned transfer: ' + message)


def symbolic():
    state = z3.BitVec('state', 2)
    flags = z3.Bools('rst channel fault transport native response active available address_good wait_reached')
    rst, channel, fault, transport, native, response, active, available, good, waited = flags
    ne = z3.And(state == 1, native)
    rr = z3.And(z3.Or(state == 2, z3.And(ne, z3.Not(active))), response)
    invalid_native = z3.And(native, state != 1)
    invalid_response = z3.And(response, z3.Not(z3.Or(state == 2, z3.And(ne, z3.Not(active)))))
    timeout = z3.And(state != 0, waited, z3.Not(z3.If(state == 1, native, response)))
    fault_now = z3.Or(transport, invalid_native, invalid_response, timeout,
        z3.And(state != 0, z3.Not(channel)), z3.And(state == 0, available, z3.Not(good)))
    opened = z3.And(rst, channel, z3.Not(fault), z3.Not(fault_now))
    owned = z3.And(rst, channel, z3.Not(fault), z3.Not(transport))
    solver = z3.Solver()
    solver.add(z3.Or(z3.And(opened, ne) != z3.And(owned, ne, z3.Not(z3.And(response, active))),
                    z3.And(opened, rr) != z3.And(owned, rr, z3.Not(invalid_native))))
    require(solver.check() == z3.unsat, 'full-domain gates differ')
    return dict(result='UNSAT', free_state_bits=2, independent_boolean_predicates=10,
                reachable_state_assumptions=False, z3_version=z3.get_version_string())


FOUR_STATE = r'''`timescale 1ns/1ps
module four_state;
function automatic logic digit(input integer pair);
case(pair)0:digit=0;1:digit=1;2:digit=1'bx;3:digit=1'bz;endcase
endfunction
function automatic [3:0] gates(input [1:0] state,input [9:0] flags);
reg rst,channel,fault,transport,native,response,active,available,address_good,wait_reached;
reg ne,rr,invalid_native,invalid_response,timed,fault_now,opened,owned,old_n,old_r,new_n,new_r;
begin
 {wait_reached,address_good,available,active,response,native,transport,fault,channel,rst}=flags;
 ne=state==1 && native;
 rr=(state==2 || (ne && !active)) && response;
 invalid_native=native && state!=1;
 invalid_response=response && !(state==2 || (ne && !active));
 timed=state!=0 && wait_reached && !(state==1 ? native:response);
 fault_now=transport || invalid_native || invalid_response || timed ||
   (state!=0 && !channel) || (state==0 && available && !address_good);
 opened=rst && channel && !fault && !fault_now;
 owned=rst && channel && !fault && !transport;
 old_n=opened && ne;old_r=opened && rr;
 new_n=ne ? (owned && !(response && active)) : (opened && ne);
 new_r=rr ? (owned && !invalid_native) : (opened && rr);
 gates={old_n,old_r,new_n,new_r};
end endfunction
integer vector_index,bit_index;reg [1:0] state;reg [9:0] flags;reg [3:0] result;
initial begin
 for(vector_index=0;vector_index<16777216;vector_index=vector_index+1)begin
  state={digit((vector_index>>22)&3),digit((vector_index>>20)&3)};
  for(bit_index=0;bit_index<10;bit_index=bit_index+1)flags[bit_index]=digit((vector_index>>(bit_index*2))&3);
  result=gates(state,flags);
  if(result[3:2]!==result[1:0])$fatal(1,"four-state mismatch vector=%h state=%b flags=%b old=%b new=%b",vector_index,state,flags,result[3:2],result[1:0]);
 end
 $display("PASS owned-transfer four-state combinations=16777216 state_encodings=16 predicates=10");$finish;
end
endmodule
'''


def simulate(output, name, sources, top, parameters=(), expected=None, timeout=90):
    command = ['iverilog', '-g2012', '-Wall', '-s', top, '-o', str(output / (name + '.vvp'))]
    command += ['-P' + top + '.' + key + '=' + str(value) for key, value in parameters]
    command += list(map(str, sources))
    compile_run = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (output / (name + '-compile.log')).write_text(compile_run.stdout + compile_run.stderr)
    require(compile_run.returncode == 0, 'compile ' + name + ': ' + compile_run.stderr)
    run = subprocess.run(['vvp', str(output / (name + '.vvp'))], capture_output=True, text=True, timeout=timeout)
    log = output / (name + '.log'); log.write_text(run.stdout + run.stderr)
    if expected:
        require(run.returncode != 0 and expected in run.stdout, 'specific mutant escaped ' + name + ': ' + run.stdout)
    else:
        require(run.returncode == 0 and 'PASS ' in run.stdout, name + ': ' + run.stdout)
    return dict(compile_argv=command, returncode=run.returncode, log_sha256=sha(log),
                expected_failure=expected, rejected=bool(expected), summary=run.stdout.strip())


def twin(output, old):
    text = TB.read_text()
    start = text.index('    workstation_recording_ddr_owner_mux #(')
    end = text.index('    integer checks=', start)
    instance = text[start:end].strip()
    require(instance.endswith(');'), 'instance end')
    prefix, bindings = instance.split(' dut(', 1)
    connections = dict(re.findall(r'\.([A-Za-z_]\w*)\(([^()]*)\)', bindings.rsplit(');', 1)[0]))
    outputs = {'ready_o':2, 'native_accept_o':2, 'response_o':2, 'valid_o':1, 'write_o':1,
               'address_o':29, 'data_o':256, 'mask_o':32, 'transport_fault_o':1, 'fault_o':1, 'busy_o':1}
    header = old.split(')(\n', 1)[1].split(');', 1)[0]
    declared = re.findall(r'\b(?:input|output)\s+(?:wire|reg)\s*(?:\[[^]]+\])?\s*([\w,]+)', header)
    declared = {name for group in declared for name in group.split(',') if name}
    require(declared == set(connections), 'complete input/output inventory')
    wires = '\n'.join('wire [' + str(width-1) + ':0] ref_' + name + ';' for name, width in outputs.items())
    bound = ','.join('.' + name + '(' + ('ref_' + name if name in outputs else signal) + ')'
                     for name, signal in connections.items())
    ref = prefix.replace('workstation_recording_ddr_owner_mux #(', 'workstation_recording_ddr_owner_mux_reference #(', 1)
    ref += ' reference(' + bound + ');'
    checks = ['if(dut.' + name + '!==ref_' + name + ')$fatal(1,"whole mux output ' + name + '");' for name in outputs]
    states = ('state', 'owner', 'prefer', 'active_write', 'waited')
    checks += ['if(dut.' + name + '!==reference.' + name + ')$fatal(1,"whole mux state ' + name + '");' for name in states]
    checks += ['if(dut.' + name + '!==reference.' + name + ')$fatal(1,"whole mux combinational ' + name + '");'
               for name in ('fault_now', 'open', 'native_event', 'read_return')]
    extra = '\n' + wires + '\n' + ref + '\ninteger twin_edges=0;\nalways @(posedge clk or negedge clk)begin #0.01;twin_edges=twin_edges+1;\n'
    extra += '\n'.join(checks) + '\nend\nfinal $display("PASS whole W10 mux twin edges=%0d outputs=11 states=5",twin_edges);\n'
    (output / 'twin.sv').write_text(text[:end] + extra + text[end:])
    (output / 'reference.sv').write_text(old.replace('module workstation_recording_ddr_owner_mux #(',
                                                  'module workstation_recording_ddr_owner_mux_reference #(', 1))
    return simulate(output, 'whole-twin', [output/'twin.sv', SOURCE, output/'reference.sv',
                    ROOT/'rtl/memory/workstation_recording_ddr_native_bridge.sv'], 'tb_recording_ddr_owner_mux')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse-four-state', type=Path,
                        help='Explicit prior completed identical exhaustive bench; no cache discovery')
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    require(sha(REFERENCE) == OLD_SHA, 'W10 full source identity')
    old, new = REFERENCE.read_text(), SOURCE.read_text()
    start = new.index('    // An owned transfer excludes IDLE address admission')
    end = new.index('    assign busy_o=', start)
    prior = ('    assign native_accept_o=open && native_event ? (owner ? 2\'b10:2\'b01):2\'b00;\n'
             '    assign response_o=open && read_return ? (owner ? 2\'b10:2\'b01):2\'b00;\n')
    require(new[:start] + prior + new[end:] == old, 'changes escape owned output gates')
    inputs = {str(p):sha(p) for p in (SOURCE, REFERENCE, TB, Path(__file__).resolve())}
    proof = symbolic()
    (output/'four-state.sv').write_text(FOUR_STATE)
    if args.reuse_four_state:
        prior = args.reuse_four_state.resolve()
        require((prior/'four-state.sv').read_text() == FOUR_STATE, 'prior four-state bench differs')
        log = (prior/'four-state.log').read_text()
        require(log.startswith('PASS owned-transfer four-state combinations=16777216 state_encodings=16 predicates=10\n')
                and 'FATAL:' not in log, 'prior exhaustive run did not complete')
        identities = {str(prior/name):sha(prior/name) for name in
                      ('four-state.sv', 'four-state.vvp', 'four-state-compile.log', 'four-state.log')}
        inputs.update(identities)
        four = dict(explicit_reused_completed_execution=str(prior), input_sha256=identities,
                    exhaustive_combinations=16777216, summary=log.strip())
    else:
        four = simulate(output, 'four-state', [output/'four-state.sv'], 'four_state', timeout=300)
    whole = twin(output, old)
    require(all(sha(Path(p)) == value for p, value in inputs.items()), 'source drift')
    report = dict(passed=True, complete_W10_source_inverse=True, inputs_sha256=inputs,
                  full_domain_two_state=proof, exhaustive_four_state_abstract_predicates=four,
                  whole_real_owner_bridge_twin=whole, source_or_physical_timing_improvement_claimed=False,
                  hardware_tested=False)
    (output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)

if __name__ == '__main__':
    main()
