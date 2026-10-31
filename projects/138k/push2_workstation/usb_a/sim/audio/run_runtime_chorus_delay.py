#!/usr/bin/env python3
"""Both-rate exhaustive actual RTL equivalence and checked provenance negatives."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_chorus_provenance import (
    verify, restore_native, sha, NARROW_POLICY, SOURCE, PROVENANCE, ADAPTATION,
)


def run(root,output):
    root,output=Path(root),Path(output)
    output.mkdir(parents=True,exist_ok=False)
    files=[root/p for p in (SOURCE,PROVENANCE,ADAPTATION,'tools/workstation_chorus_provenance.py',
           'tools/workstation_baselines.py','baselines/index.json','sim/audio/tb_workstation_runtime_chorus_delay.sv','sim/audio/run_runtime_chorus_delay.py',
           'sim/audio/fixtures/chorus_before_affine44.sv')]
    baseline=load_baseline(root,'resource_rework_route0')
    math_payload=baseline.read_bytes('legacy/rtl/audio/audio_math_pkg.sv')
    if sha(math_payload)!='f07fab099e112b18d9fc142eeb701139cae62be79e2f25596e134aaecea88f3d':
        raise ValueError('locked arithmetic dependency drift')
    math_path=output/'audio_math_pkg.sv';math_path.write_bytes(math_payload)
    files.extend([baseline.manifest,baseline.repository/baseline.descriptor['files']['legacy/rtl/audio/audio_math_pkg.sv']['source']])
    hashes={str(p):sha(p.read_bytes()) for p in files}
    source,provenance,adaptation=[(root/p).read_bytes() for p in (SOURCE,PROVENANCE,ADAPTATION)]
    _,evidence=verify(source,provenance,NARROW_POLICY,adaptation)
    previous=restore_native(source,provenance,NARROW_POLICY,adaptation)
    old_name='module workstation_runtime_chorus_effect #('
    if previous.count(old_name)!=1:raise ValueError('previous actual module name drift')
    reference=output/'previous_native_chorus.sv'
    reference.write_text(previous.replace(old_name,'module workstation_previous_chorus_effect #('))
    before_affine=(root/'sim/audio/fixtures/chorus_before_affine44.sv').read_bytes()
    if sha(before_affine)!='a2e09369634b35628920c3198b0020a51a0d4154fe690a2faf93465f8ff57900':
        raise ValueError('exact complete M12 Chorus reference drift')
    before_affine_path=output/'before_affine44_chorus.sv'
    before_affine_path.write_text(before_affine.decode().replace(old_name,'module workstation_before_affine44_chorus_effect #('))
    negatives=[]
    def reject(label,fn):
        try:fn()
        except ValueError as e:negatives.append(dict(name=label,rejected=True,error=str(e)))
        else:raise ValueError('provenance negative escaped '+label)
    reject('strict original policy rejects changed native',lambda:verify(source,provenance))
    reject('adaptation requires explicit policy',lambda:verify(source,provenance,adaptation=adaptation))
    reject('unknown policy',lambda:verify(source,provenance,'unknown',adaptation))
    reject('missing adaptation',lambda:verify(source,provenance,NARROW_POLICY))
    reject('original manifest bytes changed',lambda:verify(source,provenance+b'\n',NARROW_POLICY,adaptation))
    reject('adaptation manifest bytes changed',lambda:verify(source,provenance,NARROW_POLICY,adaptation+b'\n'))
    reject('current native bytes changed',lambda:verify(source+b'\n',provenance,NARROW_POLICY,adaptation))
    affine44=b'rounded_phase44' in source
    prior=source.replace(b"35'd134225920",b"35'd134217728") if affine44 else source.replace(b"28'd144670720",b"28'd144605184")
    reject('changed anchor cannot borrow accepted adaptation',lambda:verify(prior,provenance,NARROW_POLICY,adaptation))
    builds=[]
    def compile_run(label,current,expect_pass):
        work=output/label;work.mkdir()
        native=work/'current.sv';native.write_bytes(current)
        binary=work/'simulation.vvp'
        argv=['iverilog','-g2012','-Wall','-s','tb_workstation_runtime_chorus_delay','-o',str(binary),
              str(math_path),str(reference),str(before_affine_path),str(native),str(root/'sim/audio/tb_workstation_runtime_chorus_delay.sv')]
        c=subprocess.run(argv,capture_output=True,text=True,timeout=60)
        (work/'compile.log').write_text(c.stdout+c.stderr)
        if c.returncode:raise ValueError('actual RTL compile failed '+label+': '+c.stdout+c.stderr)
        expected_warning=('warning: Some design elements have no explicit time unit and/or\n'
            '       : time precision. This may cause confusing timing results.\n'
            '       : Affected design elements are:\n'
            '       :   -- package audio_math_pkg declared here: '+str(math_path)+':1\n')
        if c.stderr!=expected_warning:raise ValueError('unexpected actual RTL compiler warning '+c.stderr)
        r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=60)
        (work/'run.log').write_text(r.stdout+r.stderr)
        passed=r.returncode==0 and 'PASS actual Chorus rate_delay exhaustive checks=131072' in r.stdout
        if passed!=expect_pass or (not expect_pass and 'Chorus delay mismatch' not in r.stdout+r.stderr):
            raise ValueError('actual RTL control result '+label+': '+r.stdout+r.stderr)
        row=dict(name=label,expected_pass=expect_pass,passed=passed,rejected=not passed,
                 returncode=r.returncode,source_sha256=sha(current),compile_argv=argv,
                 inherited_package_timescale_warning_only=True,owned_warning_count=0,
                 compile_log_sha256=sha((work/'compile.log').read_bytes()),run_log_sha256=sha((work/'run.log').read_bytes()))
        builds.append(row)
        print(r.stdout.strip(),flush=True)
    compile_run('actual',source,True)
    mutations=[('wrong44coefficient',b"35'd361267",b"35'd361266"),
               ('wrong44rounding',b"35'd134225920",b"35'd134217728"),
               ('truncated44product',b"logic [34:0] rounded_phase44;",b"logic [33:0] rounded_phase44;"),
               ('wrong48shift',b'triangle_times3>>11',b'triangle_times3>>10')] if affine44 else [
               ('wrong44rounding',b"28'd144670720",b"28'd144605184"),
               ('truncated44product',b"logic [24:0] triangle_times441;",b"logic [23:0] triangle_times441;"),
               ('wrong44divisor',b'scaled_high44/12\'d5',b'scaled_high44/12\'d4'),
               ('wrong48shift',b'triangle_times3>>11',b'triangle_times3>>10')]
    for label,before,after in mutations:
        if source.count(before)!=1:raise ValueError('negative mutation anchor '+label)
        compile_run(label,source.replace(before,after),False)
    if any(sha(Path(p).read_bytes())!=v for p,v in hashes.items()):raise ValueError('input changed during actual RTL test')
    report=dict(schema=1,passed=True,validation_stage='offline_exhaustive_actual_RTL_function_equivalence',
        checks=131072,rates_hz=[48000,44100],triangle_values_per_rate=65536,
        actual_current_module_function_called=True,actual_previous_native_module_function_called=True,
        previous_native_restored_sha256=sha(previous.encode()),reference_rename_only_sha256=sha(reference.read_bytes()),
        exact_complete_M12_reference_sha256=sha(before_affine),
        independent64bit_physical_time_reference=True,provenance=evidence,
        provenance_negative_controls=negatives,actual_RTL_runs=builds,input_sha256=hashes,
        no_added_clock_latency=True,physical_timing_verified=False,hardware_tested=False,deployment_allowed=False)
    out=output/'verification.json';out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(passed=True,report=str(out),sha256=sha(out.read_bytes()),checks=131072,negative_controls=len(negatives)+len(mutations))))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(ROOT,args.output)


if __name__=='__main__':main()
