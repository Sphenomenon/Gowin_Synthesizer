#!/usr/bin/env python3
"""Full-capacity M storage regression and legacy lifecycle in both modes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(output):
    output.mkdir(parents=True,exist_ok=False)
    score='rtl/music/workstation_task3_score_commit_m.sv'
    tap='rtl/workstation/workstation_task3_final_tap_export.sv'
    endpoint_sources=[tap,'rtl/workstation/workstation_task3_phone_command_ingress.sv',
        'rtl/workstation/workstation_task3_record_ingress.sv','rtl/audio/workstation_ae350_pcm_owner.sv']
    legacy=[('music/tb_workstation_task3_analysis_framework.sv','collector',
        [score,'rtl/music/workstation_task3_tf_analysis_source.sv'],'PASS task3_analysis_logic'),
        ('audio/tb_workstation_task3_audio_endpoints.sv','source',endpoint_sources,
         'PASS task3 audio endpoint logical composition checks=281')]
    sources={score,tap,'sim/audio/tb_task3_m_sync_storage.sv',
             'sim/audio/run_task3_m_sync_storage.py'}
    for bench,_,rtl,_ in legacy:
        sources.update(rtl);sources.add('sim/'+bench)
    before={p:sha(ROOT/p) for p in sorted(sources)}
    commands=[]

    def run(argv,label):
        p=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=60)
        log=output/(label+'.log');log.write_text(p.stdout+p.stderr)
        commands.append(dict(argv=argv,exit_code=p.returncode,log=str(log),sha256=sha(log)))
        if p.returncode:raise RuntimeError('failed '+label+': '+(p.stdout+p.stderr)[-1200:])
        return p.stdout

    results=[]
    try:
        cases=[('capacity',ROOT/'sim/audio/tb_task3_m_sync_storage.sv',[score,tap],
                'PASS M sync storage checks=12011 tap_frames=1527 full_tap=256 full_score=2048 append_score=19')]
        for bench,instance,rtl,expected in legacy:
            original=(ROOT/'sim'/bench).read_text()
            for selected in (0,1):
                label=Path(bench).stem+'_'+str(selected)
                text=original.replace('endmodule',f"defparam {instance}.SYNC_READ_STORAGE=1'b{selected};\nendmodule")
                if text==original:raise RuntimeError('legacy bench anchor absent')
                target=output/(label+'.sv');target.write_text(text)
                cases.append((label,target,rtl,expected))
        for label,bench,rtl,expected in cases:
            top=re.search(r'\bmodule\s+(\w+)',bench.read_text())[1]
            binary=output/(label+'.vvp')
            if 'analysis_framework' in label:
                # This existing bench uses forward declarations supported by
                # its original Verilator runner, but rejected by Icarus.
                directory=output/('obj_'+label)
                run(['verilator','--binary','--timing','-Wno-fatal','--build-jobs','4',
                     '--top-module',top,'--Mdir',str(directory),str(bench),*rtl],label+'_build')
                text=run([str(directory/('V'+top))],label+'_run')
            else:
                run(['iverilog','-g2012','-I.','-s',top,'-o',str(binary),str(bench),*rtl],label+'_build')
                text=run(['vvp',str(binary)],label+'_run')
            if expected not in text:raise RuntimeError('missing pass evidence: '+label)
            results.append(dict(case=label,passed=True,bench_sha256=sha(bench),summary=expected))
        unchanged=before=={p:sha(ROOT/p) for p in before}
        if not unchanged:raise RuntimeError('inputs changed during verification')
        report=dict(schema=1,passed=True,inputs_unchanged=unchanged,source_sha256=before,
            cases=results,invocations=commands,
            capacity=dict(score_notes=2048,tap_frames=256),
            verified=['tap cycle contract compared to async mode',
                '1527 ordered payloads, randomized backpressure and pointer wrap',
                'empty and last-pop/new-push write forwarding',
                'overflow, cancel, PANIC, link loss and clean rearm',
                'full score with concurrent final note/terminal',
                'cancelled prefetched score cannot leak into next song',
                'clip append and failed terminal publication fencing',
                'existing analysis/audio lifecycle in both modes'],
            not_verified=['Gowin BSRAM inference and actual resource delta',
                'fresh synthesis, routed timing, full CDC and target hardware',
                'LCD throughput, audio latency, SRAM and Flash'])
    except Exception as error:
        report=dict(schema=1,passed=False,error=str(error),source_sha256=before,
                    cases=results,invocations=commands)
        raise
    finally:
        (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(results),verification=str(output/'verification.json'))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    main(p.parse_args().output.resolve())
