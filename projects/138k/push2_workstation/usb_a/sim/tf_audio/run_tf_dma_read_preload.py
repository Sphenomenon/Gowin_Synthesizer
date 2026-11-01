#!/usr/bin/env python3
"""Source-pinned TF private preload transition proof and complete RTL twin.

The symbolic relation is hand-lifted binary logic, not SV formal elaboration.
Four-state coverage is bounded actual-module simulation, not universal proof.
"""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
import z3
from tf_dma_read_preload_sources import before_read_preload,SOURCE_SHA256,REFERENCE_SHA256
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
O=parser.parse_args().output.resolve();O.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=ROOT/'rtl/tf_audio/workstation_tf_runtime_dma.sv'
fixture=Path(__file__).with_name('fixtures')/'workstation_tf_runtime_dma_before_read_preload.sv'
runner=Path(__file__).with_name('run_tf_dma_read_preload_four_state.py')
tb=Path(__file__).with_name('tb_tf_dma_read_preload_four_state.sv')
inputs=[source,fixture,runner,tb,ROOT/'rtl/ddr_address_map.vh',Path(__file__).resolve(),Path(__file__).with_name('tf_dma_read_preload_sources.py')]
before={str(p):sha(p)for p in inputs}
for p in inputs:
    copy=O/'inputs'/p.relative_to(ROOT);copy.parent.mkdir(parents=True,exist_ok=True);copy.write_bytes(p.read_bytes())
candidate=source.read_text();original=fixture.read_text()
assert sha(source)==SOURCE_SHA256 and sha(fixture)==REFERENCE_SHA256
assert before_read_preload(candidate)==original
nba=lambda value:[row for row in re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',value)if row[0]!='read_buf']
assert nba(candidate)==nba(original),'nonprivate NBA target/RHS/order changed'
drift=[]
for label,anchor in [('preload_branch',"1'b0: read_buf <= app_rdata;"),('unchanged_arithmetic',"available_bytes, 7'd96)")]:
    assert candidate.count(anchor)==1
    try:before_read_preload(candidate.replace(anchor,anchor+' ',1))
    except ValueError:drift.append(dict(label=label,rejected=True))
    else:raise ValueError('source gate accepted drift: '+label)
for anchor in [
 'wire read_response = app_rvalid && (read_pending || read_accept);',
 '!write_selected && !read_pending && !read_buf_valid &&',
 "read_pending <= 1'b1;\n                    read_pending_bytes <= read_chunk_bytes;",
 "if (read_response) begin\n                    read_pending <= 1'b0;",
 "read_buf_valid <= 1'b1;\n                    emit_index <= 6'd0;",
 "if (app_rvalid) read_pending <= 1'b0;",
 "if (emit_bytes_left == 6'd1) begin\n                        emit_index <= 6'd0;\n                        read_buf_valid <= 1'b0;",
]:assert anchor in original and anchor in candidate,anchor
names='pending valid reset_n restart hold done capture_finished request_other app_rdy app_rvalid stream fifo_full emit_nonzero emit_last'
(pending,valid,reset_n,restart,hold,done,capture_finished,request_other,app_rdy,app_rvalid,stream,fifo_full,emit_nonzero,emit_last)=z3.Bools(names)
old_data,new_data,returned=z3.BitVecs('old_data candidate_data app_rdata',256)
read_accept=z3.And(request_other,z3.Not(hold),stream,z3.Not(pending),z3.Not(valid),z3.Not(fifo_full),app_rdy)
read_response=z3.And(app_rvalid,z3.Or(pending,read_accept))
emit=z3.And(z3.Not(hold),stream,valid,z3.Not(fifo_full),emit_nonzero)
active=z3.And(reset_n,z3.Not(restart),z3.Not(hold),z3.Not(done))
next_pending=z3.If(z3.Not(reset_n),False,z3.If(restart,False,z3.If(hold,
 z3.And(pending,z3.Not(app_rvalid)),z3.If(done,z3.And(pending,z3.Not(capture_finished)),
 z3.If(read_response,False,z3.If(read_accept,True,pending))))))
next_valid=z3.If(z3.Not(reset_n),False,z3.If(restart,False,z3.If(hold,valid,
 z3.If(done,z3.And(valid,z3.Not(capture_finished)),
 z3.If(z3.And(emit,emit_last),False,z3.If(read_response,True,valid))))))
def buffer_next(previous,condition):
 return z3.If(z3.Or(z3.Not(reset_n),restart),z3.BitVecVal(0,256),
              z3.If(z3.And(active,condition),returned,previous))
old_next=buffer_next(old_data,read_response)
new_next=buffer_next(new_data,z3.Not(valid))
invariant=z3.Not(z3.And(pending,valid))
relation=z3.Implies(valid,old_data==new_data)
rows=[]
def unsat(name,assumptions,bad):
 solver=z3.Solver();solver.add(*assumptions,bad);status=str(solver.check()).upper();assert status=='UNSAT',(name,solver.model())
 rows.append(dict(name=name,result=status))
unsat('reset_establishes_pending_valid_disjoint',[],z3.And(z3.Not(reset_n),next_pending,next_valid))
unsat('pending_valid_disjoint_inductive_all_priorities',[invariant],z3.And(next_pending,next_valid))
unsat('read_response_cannot_coincide_with_published_buffer',[invariant],z3.And(read_response,valid))
unsat('effective_buffer_next_equal_when_published',[invariant,relation],z3.And(next_valid,old_next!=new_next))
unsat('valid_buffer_stable_across_valid_edges',[invariant],z3.And(valid,next_valid,new_next!=new_data))
unsat('valid_FIFO_emit_has_equal_payload',[relation],z3.And(emit,old_data!=new_data))
# Keep immediate accepted response as an explicit satisfiable coverage witness.
solver=z3.Solver();solver.add(invariant,active,z3.Not(pending),z3.Not(valid),read_accept,read_response,next_valid)
assert solver.check()==z3.sat
coverage={str(x):str(solver.model().eval(x,model_completion=True))for x in (pending,valid,read_accept,read_response,next_valid)}
negatives=[]
for name,condition,extra in [
 ('preload_when_valid_corrupts_published_beat',z3.BoolVal(True),[valid,z3.Not(done),z3.Not(hold)]),
 ('skip_immediate_response_preload',z3.And(z3.Not(valid),z3.Not(read_response)),[z3.Not(valid),z3.Not(pending),read_accept,read_response]),
 ('only_pending_response_preload_loses_zero_cycle_return',pending,[z3.Not(valid),z3.Not(pending),read_accept,read_response]),
]:
 bad_next=buffer_next(new_data,condition);solver=z3.Solver();solver.add(invariant,relation,active,*extra,next_valid,old_next!=bad_next)
 assert solver.check()==z3.sat,name
 negatives.append(dict(name=name,rejected=True,reason='SAT behavioral counterexample',model=str(solver.model())))
report=dict(schema='maintained-tf-read-private-preload-v1',passed=False,input_sha256=before,
 source_sha256=sha(source),fixture_sha256=sha(fixture),exact_complete_source_inverse=True,
 non_read_buf_NBA_targets_RHS_order_identical=True,source_drift_controls=drift,
 all_binary_transition_checks=rows,negative_controls=negatives,
 zero_cycle_response_coverage=coverage,z3_version=z3.get_version_string(),
 proof_scope='Source-pinned hand-lifted binary transition relation, not formal SV elaboration; no arbitrary four-state symbolic proof.',
 abstract_request_qualification_arbitrary=True,occupancy_or_response_size_equality_assumed=False,
 app_rvalid_pending_protocol_assumption=False,read_pending_and_valid_disjoint_is_inductively_proved=True,
 private_invalid_payload_equality_required=False,no_added_cycle=True,synthesis=False,pnr=False,hardware_tested=False)
try:
    command=[sys.executable,'-B',str(runner),'--output',str(O/'four-state')]
    run=subprocess.run(command,capture_output=True,text=True,timeout=900)
    log=O/'four-state.log';log.write_text(run.stdout+run.stderr);run.check_returncode()
    verification=O/'four-state/verification.json';record=json.loads(verification.read_text())
    assert record['passed']and record['completed']
    report['four_state']=dict(path=str(verification),sha256=sha(verification),passed=True,
        bounded_four_state_simulation=True,formal_all_four_state_proof=False,
        runs=len(record['runs']),negative_controls=sum(x['negative_control']for x in record['runs']))
    assert before=={str(p):sha(p)for p in inputs},'verification inputs changed during run'
    report.update(passed=True,inputs_unchanged=True)
finally:
    (O/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
artifacts={str(p):sha(p)for p in sorted(O.rglob('*'))if p.is_file()}
seal=O/'final-seal.json';seal.write_text(json.dumps(dict(passed=True,artifacts=artifacts,
    no_physical_gain_claimed=True),indent=2)+'\n')
print('PASS maintained TF private preload',sha(source),'seal='+sha(seal))
