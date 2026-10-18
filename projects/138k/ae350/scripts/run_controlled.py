#!/usr/bin/env python3
"""Run the full managed regression plus CPU/G1 event control integration."""
import datetime,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'scripts'))
from run import audio_sources,rom_sources,ORIGINAL
out=ROOT.parent/'results'/datetime.datetime.now().strftime('ae350_controlled_sim_%Y%m%d_%H%M%S_%f');out.mkdir()
sources=audio_sources()+[ROOT/'integration'/f for f in ['gw138k_event_arbiter.sv','gw138k_three_event_arbiter.sv','gw138k_event_workstation.sv','gw138k_controlled_adapter.sv','gw138k_controlled_services.sv','gw138k_controlled_audio.sv']]+[ROOT/'sim/tb_controlled_audio.sv']
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+rom_sources()}
(out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
top='tb_controlled_audio'
commands=[['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',top,'--Mdir',str(out/'obj'),*map(str,sources)],[str(out/'obj'/('V'+top))]]
print(out,flush=True)
for name,command in zip(['compile','simulation'],commands):
    with (out/(name+'.log')).open('w') as log:p=subprocess.run(command,cwd=ORIGINAL,stdout=log,stderr=subprocess.STDOUT)
    print(name,p.returncode,flush=True)
    if p.returncode:raise SystemExit(p.returncode)
assert 'PASS controlled_audio' in (out/'simulation.log').read_text()
assert all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in hashes.items())
(out/'verification.json').write_text(json.dumps(dict(passed=True,inputs_unchanged=True,hardware_tested=False),indent=2)+'\n')
