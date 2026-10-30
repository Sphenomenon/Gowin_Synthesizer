#!/usr/bin/env python3
"""Real minor1 writer/reader/cache to shared raster pixels and old-default parity."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_runtime_clock_audit import verify_synthesis_identity


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True,help='Frozen rev4 v2 synthesized Prj1')
    parser.add_argument('--output',type=Path,required=True,help='New evidence directory')
    args=parser.parse_args()
    project,output=args.project.resolve(),args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    seal=verify_synthesis_identity(project,project.parents[1]/'runtime_synthesis_evidence/process.json')
    reference=project/'rtl/display_data/feedback_renderer.v'
    current=ROOT/'rtl/display_data/feedback_renderer.v'
    hdmi=ROOT/'rtl/workstation/workstation_hdmi_display.sv'
    renderer=current.read_text()
    added=('    parameter integer SCALE_THREE_HALVES = 0,\n'
           '    // Shared snapshots can render analysis without instantiating a local FFT.\n'
           '    // Inherit the historical selection unless a composition opts in explicitly.\n'
           '    parameter integer RENDER_ANALYSIS = ENABLE_ANALYSIS\n')
    restored=renderer.replace(added,'    parameter integer SCALE_THREE_HALVES = 0\n').replace('feedback_dashboard #(.ENABLE_ANALYSIS(RENDER_ANALYSIS))',
                                                   'feedback_dashboard #(.ENABLE_ANALYSIS(ENABLE_ANALYSIS))')
    if restored!=reference.read_text() or renderer.count('feedback_dashboard #(.ENABLE_ANALYSIS(RENDER_ANALYSIS))')!=2:
        raise ValueError('Renderer changes exceed the one-parameter rendering split')
    if 'feedback_renderer #(.ENABLE_ANALYSIS(0),.RENDER_ANALYSIS(1),.SHARED_EXPORT(0),.SHARED_RENDER(1)' not in hdmi.read_text():
        raise ValueError('Native provider did not select shared analysis without local FFT')
    ref=output/'reference_feedback_renderer.v'
    ref.write_text(reference.read_text().replace('module feedback_renderer #(','module reference_feedback_renderer #(',1))
    display=ROOT/'rtl/display_data'
    sources=[ROOT/'rtl/display_data_layout_pkg.svh']
    sources += [display/name for name in ('display_data_writer.v','display_data_reader.v','feedback_renderer.v',
                                         'feedback_capture.v','output_audio_analysis.v')]
    sources += [project/'src/video'/name for name in ('feedback_dashboard.v','video_font_5x7.v',
                    'feedback_wave_align.v','output_audio_capture.v','audio_analysis_rom.v')]
    fixture=Path(__file__).with_name('tb_workstation_shared_analysis_pixels.sv')
    sources += [ref,fixture]
    inputs=list(dict.fromkeys(sources+[reference,hdmi,hdmi.with_suffix('.provenance.json'),Path(__file__).resolve(),
        ROOT/'tools/workstation_runtime_clock_audit.py',ROOT/'tools/workstation_synthesis_netlist.py']))
    hashes={str(path):sha(path) for path in inputs}
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    result=dict(schema=1,identity='native-shared-analysis-pixels-v1-'+identity[:16],source_set_sha256=identity,
        passed=False,validation_scope='RTL functional DDR and complete 1920x1080 raster: spectrum, XY, left/right meters, both pre-fix defaults',
        input_sha256=hashes,synthesis_reference=seal,reference_scope='Frozen v2 support and historical renderer only; current RTL is a distinct offline repair',
        renderer_diff_reverses_to_reference=True,native_local_fft_enabled=False,native_render_analysis_enabled=True,
        source_bank_budget=dict(image_bits=131072,spectrum_bits=16384,total_bits=147456,bytes=18432),
        physical_resources_verified=False,routed_timing_verified=False,hardware_tested=False,release_ready=False,deployment_allowed=False,commands={})
    def run(name,command,timeout):
        result['commands'][name]=list(map(str,command))
        with (output/(name+'.log')).open('w') as stream:
            subprocess.run(command,cwd=project,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=timeout)
        return (output/(name+'.log')).read_text()
    try:
        log=run('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',
            'tb_workstation_shared_analysis_pixels','--Mdir',str(output/'obj'),'-I'+str(project),*map(str,sources)],240)
        warnings=re.findall(r'^%Warning-([^:]+): ([^\n]+)',log,re.M)
        result['warning_counts']={k:sum(kind==k for kind,_ in warnings) for k,_ in warnings}
        normalize=lambda message:re.sub(r'^.*?:\d+:\d+: ','',message)
        baseline_warnings={(k,normalize(m)) for k,m in warnings if '/'+ref.name+':' in m}
        result['inherited_renderer_warnings']=[dict(kind=k,message=normalize(m)) for k,m in warnings
            if '/'+current.name+':' in m and (k,normalize(m)) in baseline_warnings]
        result['owned_warnings']=[dict(kind=k,message=m) for k,m in warnings if k!='TIMESCALEMOD' and
            ('/'+fixture.name+':' in m or ('/'+current.name+':' in m and (k,normalize(m)) not in baseline_warnings))]
        if result['owned_warnings'] or any(k=='UNOPTFLAT' for k,_ in warnings):
            raise ValueError('New fixture/renderer warning or combinational loop')
        log=run('simulate',[str(output/'obj/Vtb_workstation_shared_analysis_pixels')],180)
        print(log,end='')
        match=re.search(r'PASS workstation_shared_analysis_pixels: beats=(\d+) pixels=(\d+) known=(\d+) negative=(\d+) stalls=(\d+) spectrum=(\d+) xy=(\d+) writes=(\d+) reads=(\d+) default0=1 default1=1 native_no_local_fft=1',log)
        if not match:raise ValueError('Missing pixel/default/negative proof marker')
        result['metrics']=dict(zip(('beats','pixels','known_pixels','negative_differences','stalls','spectrum_columns','xy_pixels','ddr_writes','ddr_reads'),map(int,match.groups())))
        if verify_synthesis_identity(project,project.parents[1]/'runtime_synthesis_evidence/process.json')!=seal or hashes!={str(p):sha(p) for p in inputs}:
            raise ValueError('Reference or repair inputs drifted during pixel verification')
        result['source_seal_before_and_after']=True
        result['passed']=True
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(identity=result['identity'],passed=True)))


if __name__=='__main__':main()
