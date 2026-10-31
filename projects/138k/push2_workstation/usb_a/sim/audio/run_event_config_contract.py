#!/usr/bin/env python3
"""Compare the real M13/current service+event pair in W and legacy cases."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sim/audio'))
from run_runtime_controlled import runtime_sources

REFERENCES=(('src/ae350/gw138k_event_workstation.sv','gw138k_event_workstation',
             '5d02329a6b7f08ec30d79552a4814436b7c01611f4e4bed83c1514d154ef3fd1'),
            ('rtl/audio/workstation_audio_render_service.sv','workstation_audio_render_service',
             '148f0fb7b8976099d26bbf71025105c0d0df6f3b5e06ea90f1f75cdae0e46968'))
COMMON=('accepted','core_config','requested_rate','active','response_sent','held_rate','external_busy',
        'request_muted','request_cancel_epoch','request_epoch_match','held_pcm_left','held_pcm_right',
        'core_rate_busy','core_fault','workstation.core_ce','workstation.dispatch','workstation.mode_valid',
        'workstation.panic_accept','workstation.parameter_commit','workstation.engine_rate_commit',
        'workstation.runtime_config_block','workstation.rate_ready_o','workstation.history_ready_o',
        'workstation.pending','workstation.frame_inflight')
NATIVE=tuple('workstation.runtime_configuration.'+n for n in
             ('busy','is_config','pending_rate','committed_rate','failed','applied','history_done'))

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def wrapper(service):
    header=re.search(r'module workstation_audio_render_service\b.*?\n\);',service,re.S)[0]
    parameters=re.findall(r'parameter (?:bit|integer) (\w+)=',header)
    decl=re.findall(r'\b(input|output)\s+(?:wire|reg)\s+(signed\s+)?(\[[^\]]+\]\s+)?(.*?)(?=\binput\b|\boutput\b|\)\s*;)',header,re.S)
    ports=[(direction,(signed or '')+(width or ''),n.strip())for direction,signed,width,names in decl for n in names.rstrip().rstrip(',').split(',')]
    assert len(ports)==72 and all(re.fullmatch(r'\w+',n)for _,_,n in ports),'service public port inventory drift'
    args='#('+','.join('.'+n+'('+n+')'for n in parameters)+')'
    public=[n for d,_,n in ports if d=='output'];assert len(public)==50
    text=header.replace('module workstation_audio_render_service','module event_config_contract_miter').replace('output reg','output wire')+'\n'
    text+='\n'.join('wire '+w+'reference_'+n+';'for d,w,n in ports if d=='output')+'\n'
    text+='workstation_audio_render_service '+args+' actual('+','.join('.'+n+'('+n+')'for _,_,n in ports)+');\n'
    text+='workstation_audio_render_service_before_event_config '+args+' reference('+','.join('.'+n+'('+('reference_'if d=='output'else'')+n+')'for d,_,n in ports)+');\n'
    text+='integer comparisons=0;always @(posedge clk_i or negedge clk_i)if(rst_ni)begin\n'
    text+='if({'+','.join(public)+'} !== {'+','.join('reference_'+n for n in public)+'})$fatal(1,"M13/current full service output differs");\n'
    text+=''.join('if(actual.'+n+' !== reference.'+n+')$fatal(1,"M13/current boundary differs: '+n+'");\n'for n in COMMON)
    text+='comparisons=comparisons+1;end\n'
    text+='generate if(RUNTIME_EFFECTS_ENABLE)begin: native_boundaries\nalways @(posedge clk_i or negedge clk_i)if(rst_ni)begin\n'
    text+=''.join('if(actual.'+n+' !== reference.'+n+')$fatal(1,"M13/current transaction differs: '+n+'");\n'for n in NATIVE)
    text+='end\nend endgenerate\nfinal $display("CONTRACT_MITER native=%0d d_only=%0d halfcycles=%0d public_outputs=50 common_boundaries=25 native_boundaries=7",RUNTIME_EFFECTS_ENABLE,D_ONLY_ENABLE,comparisons);\nendmodule\n'
    return text

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--variant',type=Path,help='New external test-only directory containing both complete service/event mutant sources; never edits the production tree')
    ap.add_argument('--sample-admission-miter',action='store_true',
                    help='Use immutable pre-sample-admission source and its exact inverse gate instead of the M13 reference')
    args=ap.parse_args()
    project=args.project.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tb=Path(__file__).with_name('tb_event_config_service_contract.sv')
    sources=runtime_sources(project,tb);refs=[]
    service=ROOT/'rtl/audio/workstation_audio_render_service.sv'
    references=REFERENCES;sample_contract=None;source_gate_inputs=[]
    if args.sample_admission_miter:
        import prove_sample_admission_cofactor as admission
        sample_contract=admission.source_contract()
        references=admission.SAMPLE_ADMISSION_REFERENCES
        source_gate_inputs=[Path(admission.__file__).resolve()]
    if args.variant:
        variant=args.variant.resolve()
        assert not variant.is_relative_to(ROOT),'mutant source must be outside production inputs'
        changes={ROOT/('rtl/audio/'+name):variant/name for name in
                 ('gw138k_event_workstation.sv','workstation_audio_render_service.sv')}
        assert all(p.is_file()for p in changes.values()),'complete mutant source pair missing'
        sources=[changes.get(p,p)for p in sources];service=changes[service]
    for relative,module,expected in references:
        source=project/relative;assert sha(source)==expected,'exact service/event reference drift: '+str(relative)
        text=source.read_text()
        for _,name,_ in references:text=re.sub(r'\b'+name+r'\b',name+'_before_event_config',text)
        target=out/(module+'_before_event_config.sv');target.write_text(text);sources.append(target);refs.append(source)
    target=out/'event_config_contract_miter.sv';miter=wrapper(service.read_text())
    if args.sample_admission_miter:miter=miter.replace('M13/current','pre-sample/current')
    target.write_text(miter);sources.append(target)
    memory_reference=ROOT/'sim/audio/tb_workstation_runtime_effects.sv';text=memory_reference.read_text();anchor='\nmodule tb_workstation_runtime_effects;';assert text.count(anchor)==1
    target=out/'ordered_posted_ddr_model.sv';target.write_text(text[:text.index(anchor)]);sources.append(target)
    inputs=list(dict.fromkeys(sources+refs+source_gate_inputs+[Path(__file__).resolve(),memory_reference,ROOT/'sim/audio/run_runtime_controlled.py',ROOT/'rtl/audio/runtime_spatial_room_preset.svh']))
    inputs+=sorted((project/'sim/data').rglob('*.mem'))+sorted((project/'sim/matlab/output').rglob('*.mem'))
    hashes={str(p):sha(p)for p in inputs};result=dict(schema=1,stage=('pre_sample_admission_current_service_event_W_and_default_disabled_legacy_contract'if args.sample_admission_miter else'actual_M13_current_service_event_W_and_default_disabled_legacy_contract'),passed=False,test_only_mutant_source_directory=str(args.variant.resolve())if args.variant else None,input_sha256=hashes,common_boundaries=list(COMMON),native_boundaries=list(NATIVE),sample_admission_source_contract=sample_contract,hardware_tested=False,physical_timing_verified=False)
    try:
        cmd=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_event_config_service_contract','--Mdir',str(out/'obj'),'-I'+str(ROOT),'-I'+str(project),*map(str,sources)];result['compile_argv']=cmd
        with(out/'compile.log').open('w')as log:subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        assert '%Warning-UNOPTFLAT'not in(out/'compile.log').read_text(),'combinational admission loop'
        cmd=[str(out/'obj/Vtb_event_config_service_contract')];result['run_argv']=cmd
        with(out/'run.log').open('w')as log:subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        log=(out/'run.log').read_text();assert 'PASS full W/legacy module contracts'in log
        result['cases']=[{k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',line)}for line in log.splitlines()if line.startswith('PASS event_config_contract')];assert len(result['cases'])==2
        result['miter_metrics']=[{k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',line)}for line in log.splitlines()if line.startswith('CONTRACT_MITER')];assert len(result['miter_metrics'])==2
        assert all(sha(p)==v for p,v in hashes.items()),'contract verification input drift';result['all_inputs_unchanged']=True;result['passed']=True;print(log,end='')
    finally:
        result['logs_sha256']={p.name:sha(p)for p in out.glob('*.log')};(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
