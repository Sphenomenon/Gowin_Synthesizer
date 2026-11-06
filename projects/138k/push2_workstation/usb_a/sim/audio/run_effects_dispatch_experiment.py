#!/usr/bin/env python3
"""Validate reserved broadcasts with the actual effects, DDR DMA and model."""
from pathlib import Path
import argparse, contextlib, hashlib, io, json, re, subprocess, sys, unittest

SIM=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SIM))
import test_workstation_runtime_effects as reference
ROOT=reference.ROOT
sys.path.insert(0,str(ROOT))
from tools import workstation_effects_dispatch_experiment as experiment

BENCH_SHA256='5c7fb85775b9d5b365428c6c2f578fa37587aea4d034b57c5b105f2a21e3ec58'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def bench_view(text):
    if experiment.digest(text)!=BENCH_SHA256:raise ValueError('full effects bench identity changed')
    anchor='  integer scenario=0,i,fd,records,fields,operation,en_clip,timeout;'
    monitor='''  integer reserved_requests=0,dispatched_requests=0;
  always @(posedge aclk)if(arst_n)begin
    if(u_dut.config_accept || u_dut.history_accept)reserved_requests=reserved_requests+1;
    if(u_dut.dispatch_config || u_dut.dispatch_history)begin
      dispatched_requests=dispatched_requests+1;
      if(!u_dut.dispatch_pending || !u_dut.barrier_busy || clear_i || fault ||
          !( &u_dut.stage_quiet))$fatal(1,"dispatch outside held quiescent barrier");
    end
    if(u_dut.dispatch_pending && (ready || quiet || config_ready || history_ready))
      $fatal(1,"reserved configuration exposed sample/config readiness");
  end
  final $display("DISPATCH_COUNTS reserved=%0d dispatched=%0d",reserved_requests,dispatched_requests);
'''
    case='''        9:begin
          // This is before the first possible child acceptance edge.
          // Change the incoming payload after reservation and hold PANIC's
          // DDR fence. Its ACK must not count as the reserved configuration.
          clear_i=1;rate44=0;repeat(3)@(negedge aclk);clear_i=0;
          wait(u_memory.fence_accepts==1);no_completion(30);
          if(!u_dut.dispatch_pending || u_dut.stage_rate!=0 || !u_dut.dispatch_rate)
            $fatal(1,"PANIC retracted reservation or applied mutable rate payload");
          hold_fence=0;
          $display("PENDING_PANIC reserved_rate=1 current_input_rate=0 old_fence_held=1");
        end
'''
    assert text.count(anchor)==1 and text.count('        3:begin\n')==1
    return text.replace(anchor,monitor+anchor).replace('        3:begin\n',case+'        3:begin\n')

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    parent=ROOT/experiment.SOURCE;dispatch=ROOT/experiment.DISPATCH
    bench=ROOT/'sim/audio/tb_workstation_runtime_effects.sv'
    selected=out/'selected_effects.sv';selected.write_text(experiment.apply(parent.read_text()))
    fixture=out/'effects_bench.sv';fixture.write_text(bench_view(bench.read_text()))
    original_run=subprocess.run
    commands=[]
    tracked=[parent,dispatch,bench,Path(__file__),ROOT/'tools/workstation_effects_dispatch_experiment.py']
    before={str(p):sha(p) for p in tracked}
    result=dict(schema=1,passed=False,input_sha256=before,experiment=experiment.evidence(selected.read_text()),
        scope='Actual native full effects/DDR DMA plus independent prepared and arithmetic references. '
              'Only configuration dispatch latency changes; not whole-workstation, CDC, STA or hardware acceptance.',
        production_profile_selected=False,hardware_tested=False,commands=commands)
    original_compile=[]

    def capture(argv,*args,**kwargs):
        if isinstance(argv,list) and argv[:2]==['verilator','--binary']:
            original_compile.append(list(argv))
            argv=list(argv)
            argv[argv.index(str(parent))]=str(selected)
            argv[argv.index(str(bench))]=str(fixture)
            argv.append(str(dispatch))
        ran=original_run(argv,*args,**kwargs)
        if isinstance(argv,list) and (argv[:2]==['verilator','--binary'] or '+SCENARIO=' in ' '.join(argv)):
            name='command'+str(len(commands));log=out/(name+'.log')
            log.write_text((ran.stdout or '')+(ran.stderr or ''))
            commands.append(dict(argv=argv,exit_code=ran.returncode,log=str(log),log_sha256=sha(log)))
        return ran

    class Chain(reference.RuntimeEffectsTest):
        def test_reserved_config_survives_panic_before_dispatch_and_mutated_input(self):
            self.scenario(9,expected='PASS runtime effects PANIC collision scenario=9')

    subprocess.run=capture
    log=io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            suite=unittest.defaultTestLoader.loadTestsFromTestCase(Chain)
            ran=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        result.update(tests_run=ran.testsRun,failures=len(ran.failures),errors=len(ran.errors),skips=len(ran.skipped))
        if not ran.wasSuccessful() or ran.skipped:raise ValueError('complete effects regression failed')
        if len(original_compile)!=1:raise ValueError('missing unique full effects compile')
        rows=[]
        for command in commands:
            text=Path(command['log']).read_text()
            for reserved,dispatched in re.findall(r'DISPATCH_COUNTS reserved=(\d+) dispatched=(\d+)',text):
                rows.append(dict(reserved=int(reserved),dispatched=int(dispatched)))
        assert len(rows)==10 and all(r['reserved']==r['dispatched'] for r in rows)
        result['observed_dispatch_counts']=rows
        result['passed']=True
    finally:
        subprocess.run=original_run
        (out/'tests.log').write_text(log.getvalue())
        result['sources_unchanged']=before=={str(p):sha(p) for p in tracked}
        result['prepared_test_sha256']={str(p):sha(p) for p in (selected,fixture)}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['sources_unchanged']
    print({k:result[k] for k in ('passed','tests_run','failures','errors','skips','sources_unchanged')})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
