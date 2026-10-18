#!/usr/bin/env python3
"""Validate a frozen --with-ui build; write a new timestamped evidence directory.
Usage: check_fft2048.py /absolute/build/directory
"""
import sys
from pathlib import Path
import datetime,hashlib,json,subprocess,math
root=Path(__file__).resolve().parents[4];r=root/'migration/gw138k_audio';stage=Path(sys.argv[1]).resolve()/'Prj1';out=r/'results'/datetime.datetime.now().strftime('bar_analysis_%Y%m%d_%H%M%S_%f');out.mkdir();print(out,flush=True)
sources=[stage/'src/video'/f for f in ['output_audio_analysis.v','output_audio_capture.v','audio_analysis_rom.v']]
tb=(root/'Mega_138K/Dev/Prj1/sim/tb_output_audio_analysis.sv').read_text().replace('1023','2047').replace('1024','2048').replace('k<512','k<1024').replace('cycles>160000','cycles>250000').replace('417','834').replace('dut.display_left[dut.frequency_bin]','dut.display_left[dut.column_registered]')
column=round(511*math.log(834/2)/math.log(853/2));tb=tb.replace('column=511; repeat(3)',f'column={column}; repeat(3)')
tb=tb.replace('// The last two log endpoints are 414 and 419. Bin 834 is\n                // invisible to point sampling, but must retain its peak.','// An actual high-frequency narrow peak must survive same-column pooling.')
p=out/'tb_output_audio_analysis.sv';p.write_text(tb);h={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources+[p]}
for name,cmd in [('compile',['iverilog','-g2012','-s','tb_output_audio_analysis','-o',str(out/'sim.vvp'),*map(str,sources),str(p)]),('simulation',['vvp',str(out/'sim.vvp')])]:
 with(out/(name+'.log')).open('w')as log:q=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
 print(name,q.returncode,flush=True)
 if q.returncode:raise SystemExit(q.returncode)
fft=(root/'Mega_138K/Dev/Prj1/scripts/check_output_fft.py').read_text().replace('ROOT = Path(__file__).resolve().parents[1]',f'ROOT = Path({str(stage)!r})').replace('OUT = ROOT / "build/fft_reference"',f'OUT = Path({str(out / "fft_reference")!r})').replace('1023','2047').replace('1024','2048').replace('total/16','total/32').replace('48828.125','48000').replace('p.relative_to(ROOT).as_posix()','str(p)').replace('PASS all 2048 complex','PASS all 4096 complex')
p=out/'check_output_fft.py';p.write_text(fft);h[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();(out/'inputs.json').write_text(json.dumps(h,indent=2)+'\n')
with(out/'fft.log').open('w')as log:q=subprocess.run(['python3',str(p)],cwd=out,stdout=log,stderr=subprocess.STDOUT)
print('direct DFT',q.returncode,flush=True)
if q.returncode:raise SystemExit(q.returncode)
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in h.items())
(out/'verification.json').write_text(json.dumps(dict(passed=True,inputs_unchanged=True,scope='Nine PCM cases, dual 2048 FFT, 250000-cycle processing bound, stereo image and reset; 4096 complex bins checked against direct DFT; no interpolation.'),indent=2)+'\n')
