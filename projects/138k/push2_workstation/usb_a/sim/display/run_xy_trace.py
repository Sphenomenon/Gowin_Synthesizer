#!/usr/bin/env python3
"""Independent raster/finite-history oracle for the maintained XY writer."""
import argparse,hashlib,json,math,random,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def line(x0,y0,x1,y1):
    # Integer reference raster: textbook error recurrence, separately evaluated
    # from the RTL implementation and checked for endpoint/adjacent coverage.
    dx=abs(x1-x0);sx=1 if x0<x1 else -1;dy=-abs(y1-y0);sy=1 if y0<y1 else -1;error=dx+dy
    result=[]
    while True:
        result.append((x0,y0))
        if x0==x1 and y0==y1:break
        twice=2*error
        if twice>=dy:error+=dy;x0+=sx
        if twice<=dx:error+=dx;y0+=sy
    assert len(result)<=256
    return result

def bitmap(points):
    result=set();previous=None
    for x,y,nonzero in points:
        if not nonzero:previous=None;continue
        if previous is None:result.add(y*256+x)
        else:result.update(py*256+px for px,py in line(*previous,x,y))
        previous=(x,y)
    return result

def cases():
    r=random.Random(0x13826)
    edges=[]
    # Every octant, equal-axis/tie slopes, all four corners, clamp endpoints,
    # horizontal/vertical/repeated points and zero-separated strokes.
    for x,y in [(0,0),(255,255),(255,0),(0,255),(0,0),(128,128),(128,0),(128,255),(0,128),(255,128),(128,128)]:
        edges.append((x,y,True))
    for dx,dy in [(255,1),(1,255),(255,254),(254,255),(128,64),(64,128)]:
        for flipx in [False,True]:
            for flipy in [False,True]:
                edges.extend([(0,0,False),(255 if flipx else 0,255 if flipy else 0,True),
                    (255-dx if flipx else dx,255-dy if flipy else dy,True)])
    curve=[(max(0,min(255,128+round(112*math.sin(2*math.pi*i/2048*7)))),
            max(0,min(255,128-round(104*math.sin(2*math.pi*i/2048*5+0.3)))),True) for i in range(2048)]
    sparse=[(20,30,True),(30,40,True),(0,0,False),(220,230,True),(210,220,True)]
    random_points=[(r.randrange(256),r.randrange(256),r.randrange(7)!=0) for _ in range(4096)]
    # Third/fourth silent snapshots independently prove finite lifetime.
    return [(0,False,edges),(0,False,curve),(0,False,sparse),(0,False,[(0,0,False)]),
        (0,False,[(0,0,False)]),(1,False,random_points),(0,False,sparse),
        (0,True,[(90,100,True),(94,102,True)]),(0,False,[(0,0,False)]),(0,False,[(0,0,False)]),
        (3,False,[(0,17,True),(255,17,True)])]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--source',type=Path,default=ROOT/'rtl/display_data/workstation_xy_trace.sv')
    ap.add_argument('--engine',choices=('verilator','iverilog'),default='verilator')
    ap.add_argument('--negative',choices=('no_lines','sticky_history','gain_history','segment_cap'))
    a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=a.source.resolve();tb=Path(__file__).with_name('tb_workstation_xy_trace.sv');inputs={str(p):sha(p) for p in [source,tb,Path(__file__).resolve()]}
    selected=out/'workstation_xy_trace.sv';original=source.read_text();selected.write_text(original)
    if a.negative:
        before,after={
            'no_lines':('line_x<=have_previous ? previous_x:point_x_i;','line_x<=point_x_i;'),
            'sticky_history':('history[clear_address]<=0;','history[clear_address]<=history_q;'),
            'gain_history':('keep_history<=history_valid && history_gain==gain_i;','keep_history<=history_valid;'),
            'segment_cap':("line_steps==8'hff","line_steps==8'hfe"),
        }[a.negative]
        assert original.count(before)==1
        selected.write_text(original.replace(before,after))
    selected_tb=out/tb.name;selected_tb.write_bytes(tb.read_bytes())
    cs=cases();all_points=[];history=set();old_gain=None;expected=[];metadata=[];coverage=[]
    for gain,reset,points in cs:
        current=bitmap(points)
        image=current | history if old_gain==gain and not reset else current
        expected.extend(image.__contains__(i) for i in range(65536));metadata.append((int(reset)<<19)|(gain<<16)|len(points))
        coverage.append(dict(gain=gain,reset=reset,points=len(points),raw_pixels=len(current),published_pixels=len(image)))
        history=current;old_gain=gain;all_points.extend((int(nonzero)<<16)|(y<<8)|x for x,y,nonzero in points)
    for name,values,width in [('meta',metadata,5),('points',all_points,5),('expected',expected,1)]:
        (out/(name+'.mem')).write_text(''.join(format(int(v),'0'+str(width)+'x')+'\n' for v in values))
    sealed={str(p):sha(p) for p in [selected,selected_tb,*out.glob('*.mem')]}
    report=dict(schema=1,passed=False,input_sha256=inputs,execution_sha256=sealed,negative_control=a.negative,
        engine=a.engine,coverage=coverage,history_policy='One previous raw bitmap; current OR previous at equal gain; no blended-image feedback, no brightness-decay claim',
        scope='True synchronous history memory and bounded raster writer; exact full 256x256 bitmap oracle after every frame, actual mid-segment reset, gain retirement and silence lifetime',
        hardware_tested=False,full_analysis_tested=False)
    try:
        if a.engine=='verilator':
            argv=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_workstation_xy_trace',
                '--Mdir',str(out/'obj'),'-GFRAMES='+str(len(cs)),'-GPOINTS='+str(len(all_points)),str(selected),str(selected_tb)]
            run_argv=[str(out/'obj/Vtb_workstation_xy_trace')]
        else:
            argv=['iverilog','-g2012','-s','tb_workstation_xy_trace',
                '-Ptb_workstation_xy_trace.FRAMES='+str(len(cs)),
                '-Ptb_workstation_xy_trace.POINTS='+str(len(all_points)),
                '-o',str(out/'test.vvp'),str(selected),str(selected_tb)]
            run_argv=['vvp',str(out/'test.vvp')]
        report['compile_argv']=argv;report['run_argv']=run_argv
        with (out/'compile.log').open('w') as f:subprocess.run(argv,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        with (out/'run.log').open('w') as f:p=subprocess.run(run_argv,cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=120)
        log=(out/'run.log').read_text()
        if a.negative:
            report['negative_control_rejected']=p.returncode!=0 and 'XY trace bitmap mismatch' in log
            assert report['negative_control_rejected']
        else:assert p.returncode==0 and 'PASS xy_trace ' in log,log[-2000:]
        assert all(sha(k)==v for k,v in sealed.items());assert all(sha(k)==v for k,v in inputs.items());report['passed']=True
        print(log,end='')
    finally:
        report['logs']={p.name:sha(p) for p in [out/'compile.log',out/'run.log'] if p.exists()}
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
