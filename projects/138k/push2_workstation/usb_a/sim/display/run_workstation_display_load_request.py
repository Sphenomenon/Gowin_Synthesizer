#!/usr/bin/env python3
"""Real runtime writer/reader load-boundary races and behavioral negatives."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_runtime_counter import NATIVE, selected_source, selection_evidence

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--native-counter',action='store_true',help='Explicitly test the maintained native counter with validated prepared support');args=ap.parse_args()
    project=args.project.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    owner=ROOT/'rtl/display_data/workstation_display_runtime.sv';tb=Path(__file__).with_name('tb_workstation_display_load_request.sv')
    sources=[ROOT/'rtl/display_data_layout_pkg.svh']+[ROOT/'rtl/display_data'/p for p in ('display_data_writer.v','display_data_reader.v','display_data_analysis_source.sv','feedback_capture.v','output_audio_analysis.v')]
    sources += [project/'src/video'/p for p in ('output_audio_capture.v','audio_analysis_rom.v','feedback_wave_align.v')]
    prepared_counter=selected_source(project);counter=ROOT/NATIVE if args.native_counter else prepared_counter
    sources += [project/'src/migration/gw138k_stream_cdc.sv',counter]
    inputs=list(dict.fromkeys([*sources,owner,tb,Path(__file__).resolve(),prepared_counter,
                              ROOT/'tools/workstation_runtime_counter.py',project/'Prj1.gprj',
                              project.parents[1]/'integration_inputs.json',project.parents[1]/'workstation_profile.json']));before={str(p):sha(p) for p in inputs}
    result=dict(schema=1,passed=False,input_sha256=before,source_identity=sha(owner),producer_contract_driven_directly=True,real_writer_reader_and_ordered_DDR=True,
                counter_source=selection_evidence(project),counter_compilation=dict(source=str(counter),sha256=sha(counter),explicit_native_override=args.native_counter),
                EDA_invoked=False,hardware_operated=False,routed_timing_verified=False,deployment_allowed=False,negative_controls=[],commands={})
    def run(label,source,negative=False):
        binary=out/('obj_'+label)/'Vtb_workstation_display_load_request';command=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_workstation_display_load_request','--Mdir',str(binary.parent),'-I'+str(project),*map(str,[*sources,source,tb])]
        result['commands'][label+'_compile']=command
        with (out/(label+'_compile.log')).open('w') as f:subprocess.run(command,cwd=project,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
        warnings=re.findall(r'^%Warning-([^:]+): ([^\n]+)',(out/(label+'_compile.log')).read_text(),re.M)
        owned=[dict(kind=k,message=m) for k,m in warnings if k!='TIMESCALEMOD' and
               any('/'+name+':' in m for name in (source.name,tb.name))]
        if owned or any(k=='UNOPTFLAT' for k,m in warnings):raise ValueError('new load-boundary warning or combinational loop')
        result.setdefault('owned_warnings',{})[label]=owned
        command=[str(binary)];result['commands'][label+'_run']=command
        with (out/(label+'_run.log')).open('w') as f:r=subprocess.run(command,cwd=project,stdout=f,stderr=subprocess.STDOUT,timeout=90)
        text=(out/(label+'_run.log')).read_text()
        if negative:
            if r.returncode==0 or 'Assertion failed' not in text or 'watchdog' in text:raise ValueError('negative did not fail behavioral assertion: '+label)
            result['negative_controls'].append(dict(case=label,rejected=True,exit_code=r.returncode,error=text.strip()))
        else:
            if r.returncode:raise ValueError(text)
            match=re.search(r'PASS display_load_request: cases=(\d+) checks=(\d+) loads=(\d+) reads=(\d+) summaries=(\d+) registered_latency=1 context_races=4 stale_drain=1 disable_cancel=3 raster_gates=2 fault_retains_image=1 unsolicited_done_rejected=1',text)
            if not match:raise ValueError('missing load-boundary coverage: '+text)
            result['metrics']=dict(zip(('cases','checks','loads','reads','summaries'),map(int,match.groups())))
            print(text,end='')
    try:
        run('positive',owner)
        text=owner.read_text()
        variants=[
            ('bypass_request_register','wire load_start=load_request && enabled_i && export_live && !loading &&','wire load_start=enabled_i && pending && export_current && !loading &&'),
            ('legacy_unguarded_completion','if(loading && enabled_i && export_live && !reader_fault_o && reader_valid_o && export_current &&','if(!reader_fault_o && reader_valid_o && export_current &&'),
            ('disabled_export_revives','end else if(!enabled_i || !export_current)export_live<=0;','end else if(!export_current)export_live<=0;'),
            ('unsolicited_valid_completion','if(loading && enabled_i && export_live && !reader_fault_o && reader_valid_o && export_current &&','if(enabled_i && export_live && !reader_fault_o && reader_valid_o && export_current &&'),
        ]
        for label,old,new in variants:
            if text.count(old)!=1:raise ValueError('negative anchor drift: '+label)
            path=out/(label+'.sv');path.write_text(text.replace(old,new));run(label,path,True)
        if before!={str(p):sha(p) for p in inputs}:raise ValueError('source drift during load-boundary regression')
        result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(passed=True,negative_controls=len(result['negative_controls']),metrics=result['metrics'])))

if __name__=='__main__':main()
