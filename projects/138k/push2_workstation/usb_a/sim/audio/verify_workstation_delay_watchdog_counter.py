#!/usr/bin/env python3
"""Counter induction and deadline proof; run with a Python providing z3-solver."""
from pathlib import Path
import argparse,json,sys
import z3

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools import workstation_delay_watchdog_retime as repair

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    source=(ROOT/repair.SOURCE).read_text();parent=repair.restore(source)
    timeout,lag=z3.Ints('timeout lag')
    old_reset,current_reset=z3.Bools('old_reset current_reset')
    def advance(count,clear):return z3.If(clear,0,z3.If(count<timeout,count+1,count))
    # Inductive relation: the original count is the one-step projection of
    # the lagged count and the previous clear. Initially both counts are zero
    # and previous clear is asserted. Bounds prevent any 32-bit overflow.
    original=advance(lag,old_reset)
    premises=[timeout>=2,timeout<=2147483647,lag>=0,lag<=timeout]
    checks={
        'reset_relation':(z3.substitute(original,(lag,z3.IntVal(0)),(old_reset,z3.BoolVal(True)))!=0,'unsat'),
        'counter_bound':(z3.Or(original<0,original>timeout),'unsat'),
        'next_relation':(advance(original,current_reset)!=advance(advance(lag,old_reset),current_reset),'unsat'),
        'fault_edge':(z3.And(z3.Not(current_reset),original>=timeout-1)!=
                      z3.And(z3.Not(current_reset),z3.Not(old_reset),lag>=timeout-2),'unsat'),
        'mutant_late_threshold':(z3.And(z3.Not(current_reset),original>=timeout-1)!=
                      z3.And(z3.Not(current_reset),z3.Not(old_reset),lag>=timeout-1),'sat'),
        'mutant_omitted_previous_clear':(z3.And(z3.Not(current_reset),original>=timeout-1)!=
                      z3.And(z3.Not(current_reset),lag>=timeout-2),'sat'),
    }
    rows=[]
    for label,(difference,expected)in checks.items():
        solver=z3.Solver();solver.add(*premises,difference)
        result=str(solver.check());assert result==expected,(label,result)
        smt=args.output/(label+'.smt2');smt.write_text(solver.to_smt2())
        rows.append(dict(check=label,result=result,expected=expected,
                         smt2_sha256=repair.digest(smt.read_bytes()),
                         counterexample=str(solver.model())if result=='sat'else None))
    data=dict(passed=True,solver_version=z3.get_version_string(),
              source_sha256=repair.digest(source),parent_sha256=repair.digest(parent),
              manifest_sha256=repair.MANIFEST_SHA256,
              scope='known Boolean clear, all allowed integer timeouts and bounded reachable counter states; X/Z procedural behavior checked separately by Icarus twin',
              invariant='original_count=previous_clear?0:min(lagged_count+1,timeout)',
              assumptions=['asynchronous reset establishes counters=0 and previous_clear=1',
                           'timeout is an SV integer in [2,2147483647]; no32bit increment overflow'],
              checks=rows,whole_design_equivalence=False,routed_timing_verified=False,hardware_tested=False)
    (args.output/'verification.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=len(rows),solver=z3.get_version_string())))

if __name__=='__main__':main()
