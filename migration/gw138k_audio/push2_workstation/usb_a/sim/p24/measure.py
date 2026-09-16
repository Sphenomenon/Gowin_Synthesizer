#!/usr/bin/env python3
"""Measure P23/P24 effects-off final PCM for identical A/B/C notes."""
from pathlib import Path
from datetime import datetime
import hashlib,json,math,re,shutil,subprocess,sys,xml.etree.ElementTree as ET
import numpy as np

build=Path(sys.argv[1]).resolve();project=build/'Prj1';here=Path(__file__).resolve().parent
root=here.parents[2]
out=root/'results'/datetime.now().strftime('p24_level_measure_%Y%m%d_%H%M%S_%f')
out.mkdir(parents=True);print(out,flush=True)
all_sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList')
    if f.get('type')=='file.verilog']
audio_sources=[f for f in all_sources if not any(x in str(f.relative_to(project)) for x in
    ['vendor/','src/memory/','src/platform/','src/top/','src/ae350/riscv_',
     'workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
tb=out/'tb_mode_levels.sv';shutil.copy2(here/tb.name,tb)
inputs=audio_sources+[Path(__file__),tb]
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest()
    for f in sorted(inputs)},indent=2)+'\n')
compile_cmd=['verilator','--binary','--timing','-O3','-j','4','-Wno-fatal',
    '--top-module','tb_mode_levels','--Mdir',str(out/'obj'),'-I'+str(project),
    '-I'+str(project/'src/usb_a'),*map(str,audio_sources),str(tb)]
with (out/'compile.log').open('w') as log:
    compiled=subprocess.run(compile_cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT)
if compiled.returncode:print((out/'compile.log').read_text()[-8000:]);raise SystemExit(1)
profiles=['flute','strings','trumpet','marimba','piano'];rows=[]
def a_weighted_rms(values,fs=48000):
    samples=np.asarray(values,dtype=np.float64);samples-=samples.mean();count=len(samples)
    frequencies=np.fft.rfftfreq(count,1/fs);squared=frequencies*frequencies
    with np.errstate(divide='ignore',invalid='ignore'):
        response=(12200**2*squared*squared)/((squared+20.6**2)*
            np.sqrt((squared+107.7**2)*(squared+737.9**2))*(squared+12200**2))
        response*=10**(2/20)
    response[0]=0
    power=np.abs(np.fft.rfft(samples))**2*response**2
    if count%2==0:power[1:-1]*=2
    else:power[1:]*=2
    return math.sqrt(power.sum())/count
for mode in range(3):
    for profile,name in enumerate(profiles):
        samples=out/f'mode{mode}_{name}.txt';log_path=out/f'mode{mode}_{name}.log'
        cmd=[str(out/'obj/Vtb_mode_levels'),f'+MODE={mode}',f'+PROFILE={profile}',f'+OUT={samples}']
        with log_path.open('w') as log:r=subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT)
        if r.returncode:print(log_path.read_text()[-8000:]);raise SystemExit(1)
        values=[int(x) for x in samples.read_text().splitlines()]
        assert len(values)==8192
        match=re.search(r'clips=(\d+)',log_path.read_text());assert match
        rows.append(dict(mode='ABC'[mode],mode_index=mode,profile=name,count=len(values),
            peak=max(map(abs,values)),rms=math.sqrt(sum(x*x for x in values)/len(values)),
            a_weighted_rms=a_weighted_rms(values),dc=sum(values)/len(values),
            clip_frames=int(match.group(1))))
        print('ABC'[mode],name,'peak',rows[-1]['peak'],'rms',round(rows[-1]['rms'],2),
            'A-rms',round(rows[-1]['a_weighted_rms'],2),flush=True)
for row in rows:
    base=next(x for x in rows if x['mode']=='A' and x['profile']==row['profile'])
    row['rms_vs_A_db']=20*math.log10(row['rms']/base['rms'])
    row['a_weighted_vs_A_db']=20*math.log10(row['a_weighted_rms']/base['a_weighted_rms'])
    row['peak_vs_A_db']=20*math.log10(row['peak']/base['peak'])
result=dict(passed=True,hardware_tested=False,source_build=str(build),note=60,velocity=127,
    sample_rate_hz=48000,effects=0,pcm_input=0,skip_frames=1000,capture_frames=8192,rows=rows,
    scope='final stereo PCM; identical note/velocity/profile envelope age; one voice per run')
(out/'measurement.json').write_text(json.dumps(result,indent=2)+'\n')
