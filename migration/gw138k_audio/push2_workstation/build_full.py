#!/usr/bin/env python3
"""Freeze a new Push candidate from the exact restored 93D0 source snapshot."""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,os,shutil,subprocess,xml.etree.ElementTree as ET
BASE=Path(__file__).resolve().parent
ORIGINAL=BASE.parent/'results/ae350_workstation_build_20260911_025414_047177'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--reuse-synthesis',type=Path);args=ap.parse_args()
    inputs=json.loads((ORIGINAL/'workstation_inputs.json').read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert all(sha(ORIGINAL/'Prj1'/f)==v for f,v in inputs.items()),'93D0 frozen source changed'
    out=BASE/'results'/datetime.now().strftime('workstation_%Y%m%d_%H%M%S_%f');out.mkdir()
    stage=out/'Prj1'
    shutil.copytree(ORIGINAL/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','__pycache__','*.user'))
    shutil.copytree(ORIGINAL/'reference',out/'reference')
    (out/'base_workstation_inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    dest=stage/'src/push2';dest.mkdir()
    sources=list((BASE/'rtl').glob('*.sv'))+list((BASE/'integration').glob('*.v'))+list((BASE/'integration').glob('*.sv'))
    sources += [f for f in (BASE/'vendor').glob('push2_*.sv') if f.name not in ['push2_led_tx.sv','push2_demo_pixels.sv','push2_visual_init.sv']]
    for f in sources:shutil.copy2(f,dest/f.name)
    overrides=list((BASE/'overrides').rglob('*'))
    overrides=[f for f in overrides if f.is_file()]
    for f in overrides:
        target=stage/f.relative_to(BASE/'overrides');assert target.is_file(),str(target)
        shutil.copy2(f,target)
    for suffix in ['cst','sdc']:
        with (stage/'constraints'/('tang_mega_138k.'+suffix)).open('a') as f:
            f.write('\n'+(BASE/'integration'/('push.'+suffix)).read_text())
    tree=ET.parse(stage/'Prj1.gprj');files=tree.find('FileList')
    for f in sorted(dest.iterdir()):ET.SubElement(files,'File',path=f.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    ET.indent(tree,space='    ');tree.write(stage/'Prj1.gprj',encoding='utf-8',xml_declaration=True)
    tcl=stage/'scripts/build.tcl';tcl.write_text(tcl.read_text().replace('-top_module gw138k_usb_workstation_top','-top_module gw138k_push_workstation_top'))
    hashes={str(f.relative_to(stage)):sha(f) for f in stage.rglob('*') if f.is_file()}
    (out/'workstation_inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
    (out/'push_origins.json').write_text(json.dumps({str(f):sha(f) for f in sources+overrides+[Path(__file__)]},indent=2)+'\n')
    print(out,flush=True)
    if args.prepare_only:return
    if args.reuse_synthesis:
        previous=args.reuse_synthesis.resolve();old=json.loads((previous/'workstation_inputs.json').read_text())
        for f,h in hashes.items():
            if not f.startswith('constraints/'):
                assert old.get(f)==h and sha(previous/'Prj1'/f)==h,'Changed input cannot reuse synthesis: '+f
        source=previous/'Prj1/impl/gwsynthesis'
        assert (source/'Prj1.vg').is_file(),'Missing completed synthesis'
        shutil.copytree(source,stage/'impl/gwsynthesis')
        (out/'reused_synthesis.json').write_text(json.dumps(dict(source=str(source),files={f.name:sha(f) for f in source.iterdir() if f.is_file()},non_constraint_inputs_identical=True),indent=2)+'\n')
    env=dict(os.environ,PRJ1_FLOW='pnr' if args.reuse_synthesis else 'all')
    with (out/'gowin.log').open('w') as log:
        result=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,env=env,stdout=log,stderr=subprocess.STDOUT)
    changed=[f for f,v in hashes.items() if sha(stage/f)!=v]
    (out/'tool_result.json').write_text(json.dumps(dict(exit_code=result.returncode,inputs_unchanged=not changed,changed=changed,hardware_tested=False),indent=2)+'\n')
    print('Gowin exit',result.returncode,'changed inputs',changed,flush=True)
    if result.returncode or changed:raise SystemExit(1)
if __name__=='__main__':main()
