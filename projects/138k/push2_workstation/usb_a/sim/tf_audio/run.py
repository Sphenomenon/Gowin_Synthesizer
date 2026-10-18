#!/usr/bin/env python3
"""Focused, self-contained TF audio/DDR regression for the workstation."""
from pathlib import Path
from datetime import datetime
import argparse,base64,hashlib,json,shutil,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--test')
    ap.add_argument('--output',type=Path,help='Results/fixtures directory; may be outside the checkout')
    ap.add_argument('--timeout',type=int,default=600);args=ap.parse_args()
    for tool in ('iverilog','vvp'):
        if not shutil.which(tool):ap.error(tool+' is required')
    tests=sorted(HERE.glob('tb_*.sv'))
    if args.test:tests=[p for p in tests if p.stem==args.test]
    if not tests:ap.error('no matching testbench')
    out=args.output.resolve() if args.output else ROOT/'out'/datetime.now().strftime('tf_audio_%Y%m%d_%H%M%S_%f')
    build=out/'build';build.mkdir(parents=True)
    (out/'src/memory').mkdir(parents=True)
    shutil.copy2(ROOT/'rtl/ddr_address_map.vh',out/'src/memory/ddr_address_map.vh')
    tables=ROOT/'rtl/tf_audio/storage/tang_mp3/mp3/tables'
    shutil.copytree(tables,out/'src/storage/tang_mp3/mp3/tables')
    (out/'sim/data').mkdir(parents=True)
    encoded=(HERE/'data/tf_mp3.mp3.b64').read_text()
    (out/'sim/data/tf_mp3.mp3').write_bytes(base64.b64decode(encoded))

    sources=sorted((ROOT/'rtl/tf_audio/storage').rglob('*.v'))
    sources += [ROOT/'rtl/tf_audio/tf_async_pcm_fifo.v',
                ROOT/'rtl/tf_audio/tf_workstation_audio_bridge.v',
                ROOT/'rtl/tf_audio/pt8211_tx.v',
                ROOT/'rtl/ddr_address_map_guard.v',
                ROOT/'rtl/display_data/gw138k_ddr_arbiter.sv']
    inputs=sources+tests+[ROOT/'rtl/ddr_address_map.vh',HERE/'data/tf_mp3.mp3.b64',Path(__file__)]
    (out/'inputs_sha256.json').write_text(json.dumps({
        str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in inputs},indent=2)+'\n')
    summary=[]
    for tb in tests:
        exe=build/(tb.stem+'.vvp');log=build/(tb.stem+'.log');start=time.monotonic()
        commands=[
            ['iverilog','-g2012','-Wall','-I',str(out),
             '-I',str(ROOT/'rtl/tf_audio/storage/tang_mp3/mp3'),
             '-s',tb.stem,'-o',str(exe),*map(str,sources),str(tb)],
            ['vvp',str(exe)]]
        chunks=[]
        for command in commands:
            try:r=subprocess.run(command,cwd=out,text=True,stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,timeout=args.timeout)
            except subprocess.TimeoutExpired as error:
                chunks.append(error.stdout or '')
                log.write_text('\n'.join(chunks)+f'\nTIMEOUT {args.timeout}s\n')
                raise SystemExit(f'{tb.stem}: timeout')
            chunks.append(r.stdout)
            if r.returncode:
                log.write_text('\n'.join(chunks));print(r.stdout[-8000:])
                raise SystemExit(f'{tb.stem}: command failed ({r.returncode})')
        log.write_text('\n'.join(chunks))
        if 'PASS '+tb.stem not in chunks[-1]:
            print(chunks[-1][-8000:]);raise SystemExit(tb.stem+': no PASS marker')
        line=f'{tb.stem}: PASS ({time.monotonic()-start:.2f}s)';summary.append(line);print(line,flush=True)
    (build/'summary.txt').write_text('\n'.join(summary)+'\n')
    print(f'{len(summary)} TF audio tests passed; logs: {build}')

if __name__=='__main__':main()
