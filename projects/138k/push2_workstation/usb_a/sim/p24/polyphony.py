#!/usr/bin/env python3
"""Check calibrated maximum polyphony for representative chords and unison peaks."""
from pathlib import Path
from datetime import datetime
import hashlib,json,math,re,shutil,subprocess,sys,xml.etree.ElementTree as ET

build=Path(sys.argv[1]).resolve();project=build/'Prj1';here=Path(__file__).resolve().parent
root=here.parents[2];out=root/'results'/datetime.now().strftime('p24_polyphony_%Y%m%d_%H%M%S_%f')
out.mkdir(parents=True);print(out,flush=True)
all_sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList')
    if f.get('type')=='file.verilog']
audio_sources=[f for f in all_sources if not any(x in str(f.relative_to(project)) for x in
    ['vendor/','src/memory/','src/storage/','src/platform/','src/top/','src/ae350/riscv_',
     'workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
tb=out/'tb_mode_levels.sv';shutil.copy2(here/tb.name,tb);inputs=audio_sources+[Path(__file__),tb]
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest()
    for f in sorted(inputs)},indent=2)+'\n')
cmd=['verilator','--binary','--timing','-O3','-j','4','-Wno-fatal','--top-module',
    'tb_mode_levels','--Mdir',str(out/'obj'),'-I'+str(project),'-I'+str(project/'src/usb_a'),
    *map(str,audio_sources),str(tb)]
with (out/'compile.log').open('w') as log:r=subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT)
if r.returncode:print((out/'compile.log').read_text()[-8000:]);raise SystemExit(1)
profiles=['flute','strings','trumpet','marimba','piano'];runs=[]
for mode in range(3):
    for profile,name in enumerate(profiles):runs.append((mode,profile,name,'chromatic',0))
for mode,profile in [(0,1),(1,3),(2,4)]:runs.append((mode,profile,profiles[profile],'unison',1))
rows=[]
for mode,profile,name,pattern,unison in runs:
    stem=f'{"ABC"[mode]}_{name}_{pattern}';samples=out/(stem+'.txt');log_path=out/(stem+'.log')
    command=[str(out/'obj/Vtb_mode_levels'),f'+MODE={mode}',f'+PROFILE={profile}',
        f'+OUT={samples}','+VOICES=32',f'+UNISON={unison}','+SKIP=1000','+CAPTURE=4096']
    with log_path.open('w') as log:r=subprocess.run(command,cwd=project,stdout=log,stderr=subprocess.STDOUT)
    if r.returncode:print(log_path.read_text()[-8000:]);raise SystemExit(1)
    values=[int(x) for x in samples.read_text().splitlines()];assert len(values)==4096
    rails=sum(x in (-2147483648,2147483647) for x in values)
    match=re.search(r'clips=(\d+)',log_path.read_text());assert match
    row=dict(mode='ABC'[mode],profile=name,pattern=pattern,voices=32,
        peak=max(map(abs,values)),rms=math.sqrt(sum(x*x for x in values)/len(values)),
        rail_frames=rails,effect_clip_frames=int(match.group(1)))
    rows.append(row);print(stem,'peak',row['peak'],'rms',round(row['rms'],2),
        'rails',rails,'fxclips',row['effect_clip_frames'],flush=True)
passed=all(row['rail_frames']==0 and row['effect_clip_frames']==0 for row in rows)
(out/'verification.json').write_text(json.dumps(dict(passed=passed,hardware_tested=False,
    source_build=str(build),sample_rate_hz=48000,rows=rows,
    scope='32-voice chromatic profiles plus peak-profile unison limits; final effects-off PCM'),indent=2)+'\n')
raise SystemExit(0 if passed else 1)
