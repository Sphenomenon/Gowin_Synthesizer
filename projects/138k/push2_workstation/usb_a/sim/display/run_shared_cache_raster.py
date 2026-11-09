#!/usr/bin/env python3
"""Full-HD cache raster vs an immutable pre-repair renderer, with DDR/stalls."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools import workstation_cache_raster as cache

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-stage',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();stage=a.reference_stage.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/cache.MANIFEST).read_text());reference=stage/'rtl/display_data/feedback_renderer.v'
    if sha(reference)!=manifest['sources']['rtl/display_data/feedback_renderer.v']['parent_sha256']:
        raise ValueError('Frozen renderer parent drift')
    ref=out/'reference_feedback_renderer.v';ref.write_text(reference.read_text().replace('module feedback_renderer #(','module reference_feedback_renderer #(',1))
    fixture=Path(__file__).with_name('tb_workstation_shared_analysis_pixels.sv');tb=fixture.read_text()
    def once(old,new):
        nonlocal tb
        if tb.count(old)!=1:raise ValueError('Pixel fixture anchor drift')
        tb=tb.replace(old,new,1)
    once('.RENDER_ANALYSIS(RENDER_ANALYSIS),.SHARED_RENDER(1)',
         '.SHARED_CACHE_ONLY(1),.RENDER_ANALYSIS(RENDER_ANALYSIS),.SHARED_RENDER(1)')
    once('clocks(5);rst_n=1;wait(initialized);',
         'clocks(5);rst_n=1;clocks(2);if(!frame_ready[0] || busy[0])$fatal(1,"cache raster depends on unused local capture");wait(initialized);')
    # The existing fixture predates the maintained light palette. Keep its
    # independent spectrum/XY/meter coordinates and update the expected ink.
    for old,new in [('003cdbab','00285c81'),('00a8d5bd','0068798b'),('00f1c05a','00b17522'),
                    ('000b1420','00ffffff'),('00263a4f','00e0e4e8')]:
        tb=tb.replace(old,new)
    tb=tb.replace('.source_clk(clk),.source_reset_n(rst_n)',
                  ".applied_parameters(129'd0),.source_clk(clk),.source_reset_n(rst_n)")
    target=out/'tb.sv';target.write_text(tb)
    sources=[stage/'src/memory/display_data_layout_pkg.sv']
    sources +=[ROOT/'rtl/display_data'/n for n in ('display_data_writer.v','display_data_reader.v',
          'feedback_renderer.v','feedback_capture.v','output_audio_analysis.v','feedback_dashboard.v','workstation_contest_brand.sv')]
    sources +=[stage/'src/video'/n for n in ('video_font_5x7.v','feedback_wave_align.v','output_audio_capture.v','audio_analysis_rom.v')]
    sources +=[ref,target];inputs=list(dict.fromkeys(sources+[reference,fixture,Path(__file__),ROOT/cache.MANIFEST,ROOT/cache.TOOL]))
    hashes={str(x):sha(x)for x in inputs};r=dict(passed=False,input_sha256=hashes,scope='real DDR writer/reader/cache; full-HD exact pixel and stall parity; independent analysis pixels; old defaults retained',board_accessed=False)
    try:
        for name,cmd in [('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_workstation_shared_analysis_pixels',
                 '--Mdir',str(out/'obj'),'-I'+str(stage),*map(str,sources)]),('simulate',[str(out/'obj/Vtb_workstation_shared_analysis_pixels')])]:
            with (out/(name+'.log')).open('w')as log:subprocess.run(cmd,cwd=stage,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        log=(out/'simulate.log').read_text()
        if 'PASS workstation_shared_analysis_pixels: beats=1036800 pixels=2073600 known=10' not in log:raise ValueError('Incomplete pixel proof')
        if hashes!={str(x):sha(x)for x in inputs}:raise ValueError('Inputs drifted')
        r.update(passed=True,source_seal_before_and_after=True,simulation_log=log)
        print(log,end='')
    finally:(out/'verification.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':main()
