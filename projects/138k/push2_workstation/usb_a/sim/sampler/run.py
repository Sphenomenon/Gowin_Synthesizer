#!/usr/bin/env python3
"""Self-contained sampler tests, numerical evidence and vendor immutability hashes."""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,subprocess,sys,time,struct,wave,zlib
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--test');args=ap.parse_args()
    out=ROOT/'out'/datetime.now().strftime('sampler_%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    print(out,flush=True)
    pcm=struct.pack('<37h',*[i*301-5000 for i in range(37)])
    with wave.open(str(out/'valid.wav'),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000);w.writeframes(pcm)
    raw=(out/'valid.wav').read_bytes();(out/'wav.mem').write_text('\n'.join(f'{b:02x}' for b in raw)+'\n')
    (out/'vectors.vh').write_text(f'`define WAV_BYTES {len(raw)}\n`define WAV_CRC 32\'h{zlib.crc32(pcm):08x}\n')
    rtl=ROOT/'rtl/sampler';vendor=ROOT/'rtl/tf_audio/storage'
    sources=[rtl/'sampler_pkg.sv']+sorted(f for f in rtl.glob('*.sv') if f.name!='sampler_pkg.sv')
    sources+=[vendor/name for name in ('tf_wav_pcm_decoder.v','tf_wav_chunk_parser.v','third_party_sd_spi_file_reader.v','third_party_sd_spi_sector_reader.v','third_party_spi_session.v')]
    tests=sorted(HERE.glob('tb_*.sv'))
    if args.test: tests=[t for t in tests if t.stem==args.test]
    if not tests:ap.error('no matching test')
    inputs=sources+tests+[ROOT/'rtl/ddr_address_map.vh',HERE/'run.py',rtl/'import_samples.py']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    vendor_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl/tf_audio').rglob('*') if p.is_file()}
    (out/'inputs_sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    summary=[];metrics=[];passed=False
    try:
        for tb in tests:
            obj=out/tb.stem;log=out/(tb.stem+'.log');start=time.monotonic();chunks=[]
            commands=[['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',tb.stem,
                '--Mdir',str(obj),'-I'+str(ROOT/'rtl'),'-I'+str(out),*map(str,sources),str(tb)],
                [str(obj/('V'+tb.stem))]]
            for cmd in commands:
                r=subprocess.run(cmd,cwd=out,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
                chunks.append(r.stdout);log.write_text('\n'.join(chunks))
                if r.returncode:print(r.stdout[-6000:]);raise RuntimeError(tb.stem+' failed')
            if 'PASS '+tb.stem not in chunks[-1]:raise RuntimeError('missing PASS '+tb.stem)
            print(chunks[-1].strip(),flush=True)
            for line in chunks[-1].splitlines():
                if line.startswith('METRIC '):metrics.append(dict(test=tb.stem,**{k:int(v) for k,v in (item.split('=') for item in line[7:].split())}))
            summary.append(dict(test=tb.stem,seconds=time.monotonic()-start))
        if not args.test:
            r=subprocess.run([sys.executable,str(HERE/'test_import_tool.py')],cwd=out,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            (out/'import_tool.log').write_text(r.stdout);print(r.stdout.strip(),flush=True)
            if r.returncode:raise RuntimeError('import tool failed')
            for top in ('sampler_mode_d','sampler_storage','sampler_tf_source','sampler_grid','sampler_slice'):
                r=subprocess.run(['verilator','--lint-only','-Wall','-Wno-fatal','--top-module',top,'-I'+str(ROOT/'rtl'),*map(str,sources)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                (out/(top+'_lint.log')).write_text(r.stdout)
                if r.returncode or any(w in r.stdout for w in ('%Error','%Warning-LATCH','%Warning-UNOPTFLAT','%Warning-PINMISSING')):
                    print(r.stdout[-6000:]);raise RuntimeError('lint failed '+top)
        if vendor_hashes!={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl/tf_audio').rglob('*') if p.is_file()}:
            raise RuntimeError('vendor storage was modified')
        passed=True
    finally:
        (out/'verification.json').write_text(json.dumps(dict(passed=passed,hardware_tested=False,tests=summary,metrics=metrics,vendor_sha256=vendor_hashes,
            ddr_contract='audio-clock client: outer arbiter+CDC accept/return within 18 clocks; tests use competing clients, no board measurement'),indent=2)+'\n')
    print('EVIDENCE '+str(out/'verification.json'))
if __name__=='__main__':main()
