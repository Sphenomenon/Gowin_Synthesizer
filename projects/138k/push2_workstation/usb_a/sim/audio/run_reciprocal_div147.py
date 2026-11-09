#!/usr/bin/env python3
"""Exact reciprocal arithmetic and both real M consumers against retained RTL."""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools import workstation_reciprocal_div147 as selection
from tools.workstation_baselines import load_baseline
from tools.workstation_oscillator_expression_provenance import PROVENANCE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    stage=out/'inputs';stage.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    inputs={}
    def read(path):
        inputs[str(path)]=sha(path)
        return path.read_text()
    read(Path(__file__).resolve());native=read(ROOT/selection.ALTERNATE);parent=read(ROOT/selection.SOURCE)
    if selection.sha(ROOT/selection.ALTERNATE)!=selection.ALTERNATE_SHA256 or selection.sha(ROOT/selection.SOURCE)!=selection.PARENT_SHA256:
        raise ValueError('divider source identity drift')
    helper=stage/'candidate_divider.sv';helper.write_text(native)
    oldhelper=stage/'reference_divider.sv';oldhelper.write_text(parent.replace('workstation_runtime_div147','fc_reference_div147'))
    baseline=load_baseline(ROOT,'resource_rework_route0');meta=json.loads(read(ROOT/PROVENANCE));deps=[]
    for name,identity in meta['test_dependencies'].items():
        data=baseline.read_bytes(name)
        if hashlib.sha256(data).hexdigest()!=identity['baseline_sha256']:raise ValueError('dependency drift '+name)
        if 'prepared_exact_edit'in identity:
            edit=identity['prepared_exact_edit'];text=data.decode()
            if text.count(edit['before'])!=1:raise ValueError('dependency anchor drift')
            data=text.replace(edit['before'],edit['after']).encode()
            if hashlib.sha256(data).hexdigest()!=identity['prepared_sha256']:raise ValueError('adapted dependency drift')
        target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        if target.suffix=='.sv':deps.append(target)
    deps.sort(key=lambda p:(not p.name.endswith('_pkg.sv'),str(p)))
    for path in (ROOT/'rtl/audio/scope_vec/data').glob('*.mem'):
        target=stage/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(read(path))
    report=dict(passed=False,scope='all unsigned32/42 inputs mathematically; real ordinary32/vector8 cycle equivalence; no physical acceptance',integer_proof=selection.integer_proof(),runs={})
    def run(label,top,paths,options=(),marker='PASS'):
        folder=out/label;folder.mkdir();cmd=['verilator','--binary','--timing','-j','4','-Wno-fatal',*options,'--top-module',top,'--Mdir',str(folder/'obj'),*map(str,paths)]
        with(folder/'compile.log').open('w')as log:r=subprocess.run(cmd,cwd=stage,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        if r.returncode or '%Warning-UNOPTFLAT:'in(folder/'compile.log').read_text():raise ValueError('compile failed '+label)
        with(folder/'run.log').open('w')as log:r=subprocess.run([str(folder/('obj/V'+top))],cwd=stage,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        text=(folder/'run.log').read_text();report['runs'][label]=dict(exit_code=r.returncode,log=text,log_sha256=sha(folder/'run.log'))
        if label.endswith('_mutant'):
            if not r.returncode or marker not in text:raise ValueError('negative control did not fail '+label)
        elif r.returncode or marker not in text:raise ValueError('comparison failed '+label)
        print(label,report['runs'][label]['exit_code'],flush=True)
    try:
        bench=ROOT/'sim/audio/tb_runtime_div147_independent.sv';read(bench)
        run('independent','tb_runtime_div147_independent',[bench,helper],marker='RUNTIME_DIV147_INDEPENDENT_PASS')
        old='read_address=address-DELAY;'
        # Change only the quotient ring; tag-ring and fallback remain exact.
        index=native.index('begin:g_reciprocal');prefix=native[:index];tail=native[index:]
        if tail.count(old)!=1:raise ValueError('negative-control anchor drift')
        bad=stage/'wrong_quotient_ring.sv';bad.write_text(prefix+tail.replace(old,"read_address=address-DELAY+1'b1;",1))
        run('quotient_ring_mutant','tb_runtime_div147_independent',[bench,bad],marker='DIV147_NUMERIC')
        for label in ('oscillator','vector'):
            path=ROOT/('rtl/audio/workstation_runtime_oscillator_engine.sv'if label=='oscillator'else'rtl/audio/workstation_runtime_scope_vec.sv');source=read(path);ref=source.replace('workstation_runtime_div147','fc_reference_div147')
            if label=='oscillator':
                ref=ref.replace('workstation_runtime_oscillator_engine','fc_reference_oscillator').replace('workstation_runtime_mix_quantizer','fc_reference_mix_quantizer');bench=ROOT/'sim/audio/tb_oscillator_expression_equivalence.sv';top='tb_oscillator_expression_equivalence';options=[];dependencies=deps;marker='PASS whole_oscillator_expression:'
            else:
                ref=ref.replace('workstation_runtime_scope_vec','fc_reference_vector');bench=ROOT/'sim/audio/tb_runtime_vector_pipeline_independent.sv';top='tb_runtime_vector_pipeline_independent';options=['-DVEC_REFERENCE_PIPELINED','-GCYCLE_EXACT=1'];dependencies=[];marker='VECTOR_PIPELINE_INDEPENDENT_PASS'
            read(bench);reference=stage/(label+'_reference.sv');reference.write_text(ref)
            run(label,top,[bench,path,reference,helper,oldhelper,*dependencies],options,marker)
        report['inputs_unchanged']=all(sha(Path(p))==h for p,h in inputs.items())
        if not report['inputs_unchanged']:raise ValueError('test input changed')
        report['passed']=True
    finally:
        report['input_sha256']=inputs
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
