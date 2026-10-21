#!/usr/bin/env python3
"""Offline geometry/control verification. Sample streams remain in RAM only."""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import resource
import xml.etree.ElementTree as ET
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('compile_scope', ROOT/'tools/scope_score/compile_scope.py')
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)


def run(command, cwd, log=None):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = subprocess.run([str(v) for v in command], cwd=cwd, capture_output=True, text=True, timeout=180)
    if log is not None:
        log.write_text(result.stdout+result.stderr)
    if result.returncode:
        # Never persist or print a sampled stream, even on a failed assertion.
        tail = [line for line in (result.stdout+result.stderr).splitlines() if not line.startswith('S ')]
        raise RuntimeError('\n'.join(tail[-45:]))
    return result.stdout


def compiler_checks(out):
    document = json.loads((ROOT/'tools/scope_score/geometry.json').read_text())
    expected=compiler.compile_geometry(document,ROOT,512)
    assert expected.nbytes==16384
    packed=[(int(x)&65535)<<16 | (int(y)&65535) for contour in expected for x,y in contour]
    assert packed==[int(word,16) for word in (ROOT/'rtl/audio/scope_vec/data/paths.mem').read_text().split()], 'geometry ROM must reproduce exactly from geometry source'
    failures = []
    def reject(name, callback):
        try:
            callback()
        except (ValueError, SyntaxError, KeyError, TypeError):
            failures.append(name)
        else:
            raise AssertionError('must explicitly reject '+name)
    reject('9 shapes', lambda: compiler.compile_geometry({'shapes': document['shapes']+[document['shapes'][0]]}, ROOT))
    reject('1024 points', lambda: compiler.compile_geometry(document, ROOT, 1024))
    reject('unsafe expression', lambda: compiler.equation('__import__("os").system("false")', np.arange(16)))
    reject('nonfinite equation', lambda: compiler.compile_geometry({'shapes':[{'x':'1e999','y':'sin(t)'}]}, ROOT))
    reject('unknown geometry field', lambda: compiler.compile_geometry({'shapes':[{'vertices':[[0,0],[1,0],[0,1]],'audio':'forbidden'}]}, ROOT))
    scene = json.loads((ROOT/'tools/scope_score/demo_scene.json').read_text())
    assert len(compiler.compile_scene(scene, 8)) == 69
    reject('unknown event/audio field', lambda: compiler.compile_scene(dict(scene, events=[dict(sample=0,op='cc',cc=90,value=127,audio=[])]),8))
    reject('257 cues', lambda: compiler.compile_scene(dict(scene,events=[dict(sample=0,op='cc',cc=90,value=127)]*257),8))
    reject('descending timestamp', lambda: compiler.compile_scene(dict(scene,events=[dict(sample=1,op='cc',cc=90,value=127),dict(sample=0,op='cc',cc=90,value=127)]),8))
    reject('out of band note', lambda: compiler.compile_scene(dict(scene,events=[dict(sample=0,op='note_on',note=96,velocity=127)]),8))
    reject('bad shape', lambda: compiler.compile_scene(dict(scene,events=[dict(sample=0,op='note_on',note=60,velocity=127,shape=8)]),8))
    svg = out/'geometry_fixture.svg'
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0,0 C1,0 1,1 0,1 Q-1,1 -1,0 L0,0 Z"/></svg>')
    assert compiler.compile_geometry({'shapes':[{'svg':svg.name}]},out,128).shape == (1,128,2)
    svg.write_text('<svg><path d="M0 0 L1 0 L1 1"/></svg>')
    reject('open SVG', lambda: compiler.svg_vertices(svg))
    svg.write_text('<svg><path transform="scale(2)" d="M0 0 L1 0 L1 1 Z"/></svg>')
    reject('unflattened SVG transform', lambda: compiler.svg_vertices(svg))
    svg.write_text('<svg><circle r="1"/></svg>')
    return dict(rejected_cases=failures, svg_closed_cubic_quadratic=True, production_path_bytes=16384)


def fixture_tables(out):
    # Test ADSR controls: 64-frame attack/decay/release; profile 1 zero steps.
    profiles = [(0x40000,0x40000,0xffffff,0x40000),(0,0,0xffffff,0),
                (0x40000,0x40000,0x800000,0x40000),(0x40000,0x40000,0x400000,0x40000),
                (0x40000,0x40000,0,0x40000)]
    test_cues=[(0,(2<<14)|(97<<7)|3),(0,(1<<14)|(69<<7)|127),(3,(69<<7)),(7,(2<<14)|(95<<7)|127)]
    (out/'scope_test_cues.mem').write_text(''.join(f'{(stamp<<32)|event:016x}\n' for stamp,event in test_cues)+'0000000000000000\n'*252)
    (out/'scope_test_adsr.mem').write_text(''.join(f'{v:06x}\n' for profile in profiles[:5] for v in profile))
    document = json.loads((ROOT/'tools/scope_score/geometry.json').read_text())
    raw = []
    for shape in document['shapes']:
        if 'vertices' in shape:
            a = compiler.resample(shape['vertices'],512)
        else:
            t = np.arange(512)*2*np.pi/512
            a = np.column_stack((compiler.equation(shape['x'],t),compiler.equation(shape['y'],t)))
        a -= a.mean(axis=0)
        raw.extend(np.rint(a*(30000/np.max(np.abs(a)))).astype(int))
    (out/'raw_paths.mem').write_text(''.join(f'{(int(x)&65535)<<16 | (int(y)&65535):08x}\n' for x,y in raw))


def fft_metrics(values, frequency, harmonics=1, n=2048):
    x = np.asarray(values[:n],float)
    window = .5-.5*np.cos(2*np.pi*np.arange(n)/n) # periodic Hann, P25 definition
    amplitude = np.abs(np.fft.rfft((x-x.mean())*window))
    fundamental = round(frequency*n/48000)
    reference = max(amplitude[max(0,fundamental-2):fundamental+3])
    db = 20*np.log10(np.maximum(amplitude,1e-30)/max(reference,1e-30))
    mask = np.ones(len(amplitude),bool)
    mask[0:3]=False
    for h in range(1,harmonics+1):
        center=round(frequency*h*n/48000)
        mask[max(0,center-2):center+3]=False
    return dict(far_peak_dbc=float(max(db[mask])),outside_power_db=float(10*np.log10(np.sum(amplitude[mask]**2)/np.sum(amplitude**2)))),db


def analyze(samples, out):
    data = {key: np.array(value,dtype=np.float64)/2**31 for key,value in samples.items()}
    result = {}
    for tag,note in [(0,69),(1,60)]:
        x,y = data[tag].T
        angle = np.unwrap(np.arctan2(y,x))
        slope = np.polyfit(np.arange(len(angle)),angle,1)[0]
        measured = slope*48000/(2*np.pi)
        target = 440*2**((note-69)/12)
        step = round(target*2**32/48000)
        estimate_error = measured-target
        assert abs(estimate_error)<0.001, (tag,measured,target)
        metric,spectrum = fft_metrics(x,target)
        result[f'note_{note}']=dict(target_hz=target,phase_step_hz=step*48000/2**32,measured_hz=measured,
                                     error_hz=estimate_error,periodic_hann_n2048=metric)
    assert result['note_60']['periodic_hann_n2048']['far_peak_dbc']<=-41.8
    result['antialias']={}
    plot_data=[]
    for tag,note in [(2,69),(3,95)]:
        frequency = 440*2**((note-69)/12)
        smooth = data[tag][:,0];raw = data[tag+100][:,0]
        metrics={}
        for name,values in [('raw',raw),('smooth',smooth)]:
            stat,db=fft_metrics(values,frequency,8,8192)
            alias=abs((13*frequency+24000)%48000-24000)
            center=round(alias*8192/48000)
            stat['h13_fold_or_removed_peak_dbc']=float(max(db[max(0,center-2):center+3]))
            metrics[name]=stat
            if tag==3:plot_data.append((name,db))
        metrics['h13_suppression_db']=metrics['raw']['h13_fold_or_removed_peak_dbc']-metrics['smooth']['h13_fold_or_removed_peak_dbc']
        assert metrics['h13_suppression_db']>35
        result['antialias'][str(note)]=metrics
    # Shape, stereo quadrature and endpoint morph independently checked.
    circle=data[0];morphed=data[5]
    phase=np.unwrap(np.arctan2(circle[:,1],circle[:,0]))
    assert abs(np.corrcoef(circle[:,0],circle[:,1])[0,1])<0.01
    mx,my=morphed.T
    stat_x,_=fft_metrics(mx,440,1,8192);stat_y,_=fft_metrics(my,880,1,8192)
    assert stat_x['far_peak_dbc']<-25 and stat_y['far_peak_dbc']<-25
    result['morph_endpoint']=dict(x_fundamental_hz=440,y_fundamental_hz=880,x=stat_x,y=stat_y)
    result['transitions']={}
    for tag,name in [(4,'morph'),(6,'rotation'),(7,'mute'),(8,'unmute'),(9,'release')]:
        delta=np.max(np.abs(np.diff(data[tag],axis=0)))
        assert delta<0.018,(name,delta)
        result['transitions'][name]=dict(max_sample_step_full_scale=float(delta),limit_full_scale=0.018)
    assert np.max(np.abs(data[7][-8:]))==0 and np.max(np.abs(data[9][-8:]))==0
    assert np.max(np.abs(data[14]))==0 and np.max(np.abs(data[15]))==0
    # Fit sine/cosine/DC together: fractional cycles must not bias calibration.
    before=data[11];after=data[12]
    def fit_calibration(block):
        angle=np.arange(len(block))*2*np.pi*440/48000
        design=np.column_stack((np.cos(angle),np.sin(angle),np.ones(len(block))))
        fit=np.linalg.lstsq(design,block,rcond=None)[0]
        return np.sqrt(fit[0]**2+fit[1]**2),fit[2]
    amp_before,dc_before=fit_calibration(before)
    amp_after,dc_after=fit_calibration(after)
    gain_x,gain_y=amp_after/amp_before
    expected_dc=1048576/2**31
    assert abs(gain_x-1.25)<.0002 and abs(gain_y-.75)<.0002
    assert abs(dc_after[0]-expected_dc)<2e-5 and abs(dc_after[1]+expected_dc)<2e-5
    result['calibration']=dict(measured_x_gain=float(gain_x),measured_y_gain=float(gain_y),
        offset_x_fit_fs=float(dc_after[0]),offset_y_fit_fs=float(dc_after[1]),expected_offset_fs=expected_dc)
    assert np.isfinite(data[16]).all() and np.max(np.abs(data[16]))<.13
    result['scan_sweep']=dict(start_hz=220,end_hz=440*(524288+1023*1024)/1048576,frames=1024,peak_full_scale=float(np.max(np.abs(data[16]))))
    result['polyphony']=dict(voices=8,peak_full_scale=float(np.max(np.abs(data[10]))),independent_rates=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for name,db in plot_data:axes[0].plot(np.fft.rfftfreq(8192,1/48000),np.maximum(db,-130),label=name)
    axes[0].set(xlabel='Hz',ylabel='dBc',title='MIDI95 square geometry: raw vs 8-harmonic smoothing',ylim=(-130,3));axes[0].legend();axes[0].grid()
    # Plot geometry only, not sampled audio or a time trace.
    words=np.array([int(v,16) for v in (ROOT/'rtl/audio/scope_vec/data/paths.mem').read_text().split()],dtype=np.uint32)
    coords=np.column_stack(((words>>16).astype(np.uint16).view(np.int16),(words&65535).astype(np.uint16).view(np.int16))).reshape(8,512,2)
    for index in (0,3,6):axes[1].plot(coords[index,:,0],coords[index,:,1],label=str(index))
    axes[1].set(title='Stored phase contours (geometry)',aspect='equal');axes[1].legend();axes[1].grid()
    fig.tight_layout();fig.savefig(out/'spectra_geometry.png',dpi=150);plt.close(fig)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    args=parser.parse_args()
    project=args.build.resolve()/'Prj1'
    out=ROOT/'results'/datetime.now().strftime('scope_vec_sim_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True);print(out,flush=True)
    (out/'sim').symlink_to(project/'sim',target_is_directory=True)
    (out/'rtl').symlink_to(project/'rtl',target_is_directory=True)
    for staged,source in [('src/ae350/gw138k_event_workstation.sv','rtl/audio/gw138k_event_workstation.sv'),('src/push2/push2_controls.sv','rtl/audio/push2_controls.sv'),('rtl/audio/scope_vec/scope_vec_engine.sv','rtl/audio/scope_vec/scope_vec_engine.sv')]:
        assert (project/staged).read_bytes()==(ROOT/source).read_bytes(), 'staged scope RTL differs from current source; prepare a new build'
    fixture_tables(out)
    result=dict(passed=False,build=str(args.build.resolve()),staged_rtl=True,hardware_tested=False,pcm_audio_files=0,sampled_streams_persisted=0,compiler=compiler_checks(out))
    sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
    audio_sources=sorted((project/'legacy/rtl/audio').glob('*.sv'))+[project/'legacy/rtl/input/midi_stream_decoder.sv']
    # Packages must be parsed before modules.
    audio_sources.sort(key=lambda p:(not p.name.endswith('_pkg.sv'),str(p)))
    integration=audio_sources+[project/'src/ae350/gw138k_event_workstation.sv',project/'src/ae350/gw138k_three_event_arbiter.sv',project/'rtl/audio/scope_vec/scope_vec_engine.sv',project/'rtl/audio/scope_vec/scope_control_player.sv',project/'rtl/audio/scope_vec/scope_tf_control.sv']
    integration += sorted((project / 'rtl/control').glob('*.sv'))
    samples={};test_summaries={};metrics={};all_inputs=set(integration)
    try:
        for top,inputs in [('tb_scope_vec',[project/'rtl/audio/scope_vec/scope_vec_engine.sv',project/'rtl/audio/scope_vec/scope_control_player.sv']),
                           ('tb_scope_injection',[project/'legacy/rtl/audio/audio_math_pkg.sv',project/'legacy/rtl/audio/stereo_effects.sv']),
                           ('tb_scope_controls',[project/'rtl/audio/scope_vec/scope_control_player.sv']),
                           ('tb_scope_push',[project/'src/push2/push2_controls.sv']),
                           ('tb_scope_workstation',integration)]:
            inputs=inputs+[HERE/(top+'.sv')];all_inputs.update(inputs)
            binary=out/(top+'_obj')/('V'+top)
            run(['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',top,'--Mdir',binary.parent,*inputs],out,out/(top+'_compile.log'))
            output=run([binary],out)
            summary=[]
            for line in output.splitlines():
                if line.startswith('S '):
                    _,tag,left,right=line.split();samples.setdefault(int(tag),[]).append((int(left),int(right)))
                elif line.startswith('M '):
                    _,name,value=line.split();metrics[name]=int(value)
                else:summary.append(line)
            test_summaries[top]=summary
            (out/(top+'_summary.log')).write_text('\n'.join(summary)+'\n')
            print(top,'PASS',flush=True)
        result.update(analyze(samples,out));result.update(passed=True,cycles=metrics,tests=test_summaries)
        compiler.audit_tree(out)
        result['inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(all_inputs | {Path(__file__),Path(compiler.__file__),*ROOT.joinpath('rtl/audio/scope_vec/data').glob('*'),*out.glob('*.mem'),*ROOT.joinpath('tools/scope_score').glob('*.json')})}
    finally:
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],output=str(out),cycles=metrics,note_69=result['note_69'],antialias=result['antialias']),indent=2))

if __name__=='__main__':
    main()
