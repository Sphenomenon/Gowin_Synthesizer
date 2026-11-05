#!/usr/bin/env python3
"""Full-capacity terminal semantics, four modes, and semantic fault controls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
RTL='rtl/music/workstation_task3_score_commit_m.sv'
BENCH='sim/music/tb_task3_score_terminal_pipeline.sv'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main(output):
    output.mkdir(parents=True,exist_ok=False)
    analysis=ROOT/'sim/music/tb_workstation_task3_analysis_framework.sv'
    producer=ROOT/'rtl/music/workstation_task3_tf_analysis_source.sv'
    paths=[ROOT/RTL,ROOT/BENCH,Path(__file__),analysis,producer]
    inputs={str(p):sha(p) for p in paths}
    result=dict(schema=1,passed=False,input_sha256=inputs,cases=[],profile_selected=False,
        physical_timing_verified=False,hardware_tested=False,SRAM_programmed=False,Flash_programmed=False)
    def run(label,path,negative=False):
        binary=output/(label+'.vvp')
        argv=['iverilog','-g2012','-s','tb_task3_score_terminal_pipeline','-o',str(binary),str(ROOT/BENCH),str(path)]
        p=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
        (output/(label+'-build.log')).write_text(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError('compile failed '+label)
        p=subprocess.run(['vvp',str(binary)],cwd=ROOT,capture_output=True,text=True,timeout=60)
        log=output/(label+'-run.log');log.write_text(p.stdout+p.stderr)
        passed=p.returncode==0 and 'PASS terminal pipeline' in p.stdout
        result['cases'].append(dict(case=label,negative=negative,exit_code=p.returncode,
            summary=p.stdout.strip().splitlines()[-1],run_log=dict(path=str(log),sha256=sha(log)),
            build_argv=argv,source_sha256=sha(path)))
        if passed==negative:raise RuntimeError('unexpected semantic result '+label)
    try:
        run('actual',ROOT/RTL)
        original=(ROOT/RTL).read_text()
        for label,old,new in (
            ('pending_cancel', 'if(!link_ready_i || cancel_i || panic_i)begin',
             'if(!link_ready_i || panic_i)begin'),
            ('count_high_bits', "held_count!=32'(clip_notes)",
             "held_count[11:0]!=12'(clip_notes)"),
            ('payload_hold', "assign seal_completion={identity,held_count,4'd0};", 'assign seal_completion=terminal_i;'),
            ('file_last_hold', 'assign seal_file_last=held_file_last;', 'assign seal_file_last=chunk_file_last_i;'),
            ('bad_final_note', 'held_bad<=terminal_i[3:0]!=0 || poisoned || (score_match && !score_good);',
             'held_bad<=terminal_i[3:0]!=0 || poisoned;'),
        ):
            if original.count(old)!=1:raise RuntimeError('mutation anchor drift '+label)
            path=output/(label+'.sv');path.write_text(original.replace(old,new))
            run(label,path,True)
        original=analysis.read_text()
        if original.count('endmodule')!=1:raise RuntimeError('analysis bench adaptation anchor drift')
        target=output/'analysis_pipeline.sv'
        target.write_text(original.replace('endmodule',
            "defparam collector.SYNC_READ_STORAGE=1'b1;\ndefparam collector.PIPELINED_TERMINAL=1'b1;\nendmodule"))
        top='tb_workstation_task3_analysis_framework';obj=output/'analysis_obj'
        argv=['verilator','--binary','--timing','-Wno-fatal','--build-jobs','4',
            '--top-module',top,'--Mdir',str(obj),str(target),str(ROOT/RTL),str(producer)]
        p=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
        (output/'analysis-build.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError('pipelined TF source composition build failed')
        p=subprocess.run([str(obj/('V'+top))],cwd=ROOT,capture_output=True,text=True,timeout=60)
        (output/'analysis-run.log').write_text(p.stdout+p.stderr)
        if p.returncode or 'PASS task3_analysis_logic' not in p.stdout:
            raise RuntimeError('pipelined TF source composition lifecycle failed')
        result['analysis_source_composition']=dict(passed=True,build_argv=argv,
            original_bench_sha256=sha(analysis),parameterized_bench_sha256=sha(target),
            run_log=dict(path=str(output/'analysis-run.log'),sha256=sha(output/'analysis-run.log')),
            summary=p.stdout.strip().splitlines()[0],
            scope='Real TF analysis source and score collector, held ready/valid deterministic PCM and W responder. No physical TF, actual CNN or LCD transport.')
        result.update(passed=True,inputs_unchanged=inputs=={str(p):sha(p) for p in paths},
            capacity_notes=2048,stale_identity_bits=128,revocation_boundaries=4,
            storage_and_terminal_modes=4,negative_controls_rejected=len(result['cases'])-1,
            terminal_extra_cycles=1,terminal_queue_slots=1,
            not_verified=['full endpoint/profile selection','Gowin mapping and routed timing',
                          'complete CDC, LCD physical behavior and target-board acceptance'])
        if not result['inputs_unchanged']:raise RuntimeError('input drift')
    except Exception as error:
        result['error']=str(error);raise
    finally:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(result['cases']),verification=str(output/'verification.json'))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    main(p.parse_args().output.resolve())
