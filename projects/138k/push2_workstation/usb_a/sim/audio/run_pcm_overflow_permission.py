#!/usr/bin/env python3
"""Compare complete native M PCM owners and optional actual overflow mappings.

The behavioral twin checks all public outputs, named state, PCM RAM and bitmap
slots. The mapped proof expands every combinational cell to module inputs and
FF state; opaque RAM output bits correspond by exact instance/port/bit. Any
ambiguous generated FF is independent on each side, which is stronger than
assuming a correspondence. This is a conditional one-step proof, not whole
owner induction or physical timing acceptance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import workstation_m_pcm_overflow as repair
from run_ae350_pcm_window_gate import bench


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, output, label):
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (output/(label+'.log')).write_text(result.stdout+result.stderr)
    return result


def mapped(reference, candidate):
    from tools.workstation_runtime_pcm_cdc import PcmNetlist
    from tools.workstation_task3_w_consumer_nextq import Circuit, Expressions, logical, sat_compare

    class ExactCircuit(Circuit):
        def net(self, net, active=()):
            drivers = self.g.drivers.get(net, [])
            if len(drivers) == 1 and drivers[0][0] in self.g.regs:
                path, port = drivers[0]
                assert port == 'Q'
                name = logical(path)
                token = self.label+'/'+path if name in self.ambiguous else 'register/'+name
                self.memo[net] = self.e.node('state', token)
            return super().net(net, active)

    e, circuits, inventories = Expressions(), [], []
    for label, path in [('reference', reference), ('candidate', candidate)]:
        n = PcmNetlist(path.read_text(), 'workstation_ae350_pcm_owner')
        c = ExactCircuit(n, e)
        c.label = label
        for name, cell in n.cells.items():
            if cell['kind'] == 'IBUF':
                c.memo[n.pin(name, 'O')] = e.node('state', 'input/'+n.pin(name, 'I'))
            if cell['kind'] == 'RAM16SDP4':
                bits = c.g.binding_bits(n.scopes[name], cell['ports']['DO'])
                for bit, net in enumerate(bits):
                    c.memo[n.canonical(n.scopes[name], net)] = e.node(
                        'state', 'opaque/'+name+'/DO/'+str(bit))
        circuits.append(c)
        inventories.append(dict(label=label, FF_count=len(c.g.regs),
            independent_ambiguous_generated_FFs=sorted(p for p in c.g.regs if logical(p) in c.ambiguous)))
    a, b = circuits
    assert set(a.state) == set(b.state) and len(a.g.regs) == len(b.g.regs)
    proofs = []
    for bit in range(32):
        name = 'overflows_'+str(bit)
        av, ai, ac = a.next_q(a.state[name])
        bv, bi, bc = b.next_q(b.state[name])
        assert ai == bi and ac == bc
        proofs.append(dict(state=name, INIT=ai, clock=ac, **sat_compare(e, av, bv)))
    return dict(passed=True, reference_sha256=sha(reference), candidate_sha256=sha(candidate),
        reset_inclusive_overflow_nextQ_bits=32, no_internal_combinational_cuts=True,
        named_state_and_RAM_output_correspondence_are_assumptions=True,
        ambiguous_generated_FFs_independent_across_sides=True, inventories=inventories, proofs=proofs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mapped-reference', type=Path)
    parser.add_argument('--mapped-candidate', type=Path)
    args = parser.parse_args()
    assert bool(args.mapped_reference) == bool(args.mapped_candidate)
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    sources = {repair.SOURCE:sha(ROOT/repair.SOURCE), repair.ALTERNATE:sha(ROOT/repair.ALTERNATE),
               repair.TOOL:sha(ROOT/repair.TOOL)}
    parent = (ROOT/repair.SOURCE).read_text()
    selected = (ROOT/repair.ALTERNATE).read_text()
    assert repair.digest(parent) == repair.PARENT_SHA256
    assert repair.digest(selected) == repair.ALTERNATE_SHA256 and repair.restore(selected) == parent
    (out/'reference.sv').write_text(parent.replace('module workstation_ae350_pcm_owner',
                                                   'module pcm_owner_window_reference',1))
    (out/'candidate.sv').write_text(selected)
    tb = bench()
    at = tb.index('if(equivalence_cycles<7000)')
    unknowns = """for(i=0;i<4096;i=i+1)begin
 @(negedge clk);cv=1;cw=1;ca=i%2 ? 12'h040:12'h800;
 cd=i%2 ? 32'd2:32'h31415926;cs=15;
 dut.armed=i[0];old_owner.armed=i[0];dut.owned=i[4:1];old_owner.owned=i[4:1];
 if(i[5])begin ca[1:0]=i[6] ? 2'bxz:2'bzx;end
 if(i[7])begin cs[0]=i[8] ? 1'bx:1'bz;end
 if(i[9])begin cd[0]=i[10] ? 1'bx:1'bz;end
 if(i[11])begin cw=1'bx;end
end
@(negedge clk);cv=0;cw=0;take=0;
repeat(4)@(negedge clk);
"""
    (out/'tb.sv').write_text(tb[:at]+unknowns+tb[at:])
    def compile_run(source, name):
        command=['iverilog','-g2012','-s','tb','-o',str(out/name),str(source),
                 str(out/'reference.sv'),str(out/'tb.sv')]
        assert run(command,out,name+'-compile').returncode == 0
        return run(['vvp',str(out/name)],out,name+'-run')
    result = compile_run(out/'candidate.sv', 'native')
    assert result.returncode == 0 and 'cycles=11291' in result.stdout
    old = 'if(overflow_count)overflows<=increment(overflows);'
    assert selected.count(old) == 1
    (out/'wrong-overflow.sv').write_text(selected.replace(old,'if(overflow_count)overflows<=overflows;',1))
    assert compile_run(out/'wrong-overflow.sv','mutant').returncode != 0
    report = dict(passed=True, cycles=11291, public_state_and_outputs=61,
        memory_words=512, bitmap_and_frame_slots=4, random_commands=6000,
        XZ_command_cases=4096, same_edge_revoke=True, wrong_overflow_rejected=True,
        sources_sha256=sources, added_cycles=0, hardware_tested=False, physical_timing_tested=False)
    if args.mapped_reference:
        report['actual_Gowin_mapping'] = mapped(args.mapped_reference,args.mapped_candidate)
    assert all(sha(ROOT/p)==h for p,h in sources.items())
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS M PCM overflow: complete native owner, X/Z, negative control' +
          (' and32 actual mapped overflow transitions' if args.mapped_reference else ''))


if __name__ == '__main__':
    main()
