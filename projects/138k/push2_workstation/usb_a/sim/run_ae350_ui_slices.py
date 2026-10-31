#!/usr/bin/env python3
"""Compare bounded UI rows and patches with full maintained rendering, without EDA."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(output):
    output.mkdir(parents=True,exist_ok=False)
    firmware=ROOT/'firmware/ae350'
    files=[firmware/'ui_render.c',firmware/'ui_render.h',firmware/'ui_model.h',
           Path(__file__).resolve(),Path(__file__).with_name('ae350_ui_slices_host.c')]
    inputs={str(p):sha(p)for p in files}
    baseline=(firmware/'ui_render.c').read_bytes()
    reference_sha=hashlib.sha256(baseline).hexdigest()
    (output/'reference_ui_render.c').write_bytes(baseline)
    cc=shutil.which('clang')
    if not cc:raise FileNotFoundError('clang is required for the pixel comparison')
    # Clang warns on the two retained, unused legacy keyboard helpers even
    # though the production GCC accepts static inline. Keep their bytes intact.
    common=[cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-I',str(firmware)]
    commands=[]
    def execute(argv,log):
        commands.append(argv)
        r=subprocess.run(argv,cwd=output,capture_output=True,text=True,timeout=120)
        (output/log).write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError((output/log).read_text()[-6000:])
    for sanitized in (False,True):
        suffix='san'if sanitized else'native'
        flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer']if sanitized else[]
        execute([*common,*flags,'-Dui_render=reference_ui_render','-Dui_patch=reference_ui_patch',
                 '-Dui_render_rows=reference_ui_render_rows','-Dui_patch_rows=reference_ui_patch_rows',
                 '-c',str(output/'reference_ui_render.c'),'-o','reference_'+suffix+'.o'],'reference_'+suffix+'.log')
        execute([*common,*flags,str(firmware/'ui_render.c'),str(files[-1]),'reference_'+suffix+'.o',
                 '-o','ui_slices_'+suffix],'compile_'+suffix+'.log')
        execute([str(output/('ui_slices_'+suffix))],'run_'+suffix+'.log')
        assert 'PASS ui_slices comparisons=78 'in(output/('run_'+suffix+'.log')).read_text()
    assert inputs=={p:sha(p)for p in inputs}
    result=dict(schema=1,passed=True,validation_stage='offline-maintained-full-render-versus-slice-and-patch',
        reference_policy='maintained full renderer compiled independently',reference_sha256=reference_sha,input_sha256=inputs,commands=commands,
        compiler_path=cc,compiler_sha256=sha(cc),pixel_comparisons_per_build=78,model_cases=12,row_ranges=15,
        asan_ubsan_passed=True,inputs_unchanged=True,runtime_service_integration=False,
        hardware_timing_measured=False,CPU_cycles_measured=False,EDA_invoked=False,hardware_operated=False,
        deployment_allowed=False,output_sha256={p.name:sha(p)for p in output.iterdir()if p.is_file()})
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in('commands','input_sha256','output_sha256')}))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
