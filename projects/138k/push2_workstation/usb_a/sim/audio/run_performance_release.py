#!/usr/bin/env python3
"""Exact frozen 448-bit telemetry reset semantics with stopped clocks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
STREAM='90cb55acd6f83965d74b843993bed625d121ae2eefafbd928eb6fececb6e5376'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    source=args.project/'src/migration/gw138k_stream_cdc.sv'
    bench=Path(__file__).with_name('tb_workstation_performance_release.sv')
    text=source.read_text()
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    inputs={str(p):sha(p) for p in (source,bench,Path(__file__))}
    if sha(source)!=STREAM:raise ValueError('frozen stream source changed')
    runs={}
    cases=[('positive',source,None),
      ('async_assertion_removed',None,('always_ff @(posedge source_clk or negedge reset_n)',
                                      'always_ff @(posedge source_clk)')),
      ('release_shortened',None,("source_release<={source_release[1:0],1'b1};",
                                "source_release<={source_release[1],2'b11};")),
      ('destination_wrong_clock',None,('always_ff @(posedge destination_clk or negedge reset_n)',
                                      'always_ff @(posedge source_clk or negedge reset_n)'))]
    for name,path,mutation in cases:
        if mutation:
            before,after=mutation
            if text.count(before)!=1:raise ValueError('mutation anchor drift')
            path=args.output/(name+'.sv');path.write_text(text.replace(before,after,1))
        executable=args.output/(name+'.vvp')
        compile_argv=['iverilog','-g2012','-s','tb_workstation_performance_release','-o',str(executable),str(path),str(bench)]
        compile_run=subprocess.run(compile_argv,capture_output=True,text=True,timeout=30)
        (args.output/(name+'_compile.log')).write_text(compile_run.stdout+compile_run.stderr)
        if compile_run.returncode:raise ValueError('compile failed '+name)
        run_argv=['vvp',str(executable)]
        run=subprocess.run(run_argv,capture_output=True,text=True,timeout=30)
        log=run.stdout+run.stderr;(args.output/(name+'_run.log')).write_text(log)
        if name=='positive':
            if run.returncode or 'PASS performance_release' not in log:raise ValueError(log)
            metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)}
        elif run.returncode==0 or 'FATAL' not in log:raise ValueError('negative not rejected '+name)
        runs[name]=dict(compile_argv=compile_argv,compile_returncode=compile_run.returncode,
            run_argv=run_argv,run_returncode=run.returncode,input_sha256=sha(path),
            run_log_sha256=sha(args.output/(name+'_run.log')),rejected=bool(mutation))
        print(('PASS '+name) if mutation else log.strip())
    if inputs!={p:sha(p) for p in inputs}:raise ValueError('source changed during run')
    result=dict(policy='performance-telemetry-async-release-v1',passed=True,input_sha256=inputs,
       metrics=metrics,runs=runs,negative_controls_rejected=3,width=448,
       validation='frozen real stream RTL; both reset causes; all stopped high/low clocks; both restart orders',
       synthesis_verified=False,routed_timing_verified=False,hardware_tested=False,profile_changed=False)
    (args.output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
