#!/usr/bin/env python3
"""Build a frozen C-device MIDI/48k/PT8211/DDR/HDMI migration candidate."""
from pathlib import Path
import argparse
import datetime
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from run import PROJECT, WORKSPACE, ORIGINAL, TEAM, audio_sources, rom_sources

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--flow',choices=['all','syn'],default='all')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--managed-synthesis',action='store_true',
        help='synthesize CPU-facing audio subsystem only; no physical pinout or routed timing claim')
    args=parser.parse_args()
    if args.managed_synthesis and args.flow!='syn':
        parser.error('--managed-synthesis requires --flow syn')
    out=(args.output or PROJECT/'results'/datetime.datetime.now().strftime('build_%Y%m%d_%H%M%S_%f')).resolve()
    if out.exists(): parser.error('Output must be a new directory')
    subprocess.run([sys.executable,TEAM/'scripts/build.py','--prepare-only','--work-dir',out],check=True)
    stage=out/'Prj1'
    origin_files=audio_sources()+rom_sources()+list((PROJECT/'rtl').glob('*.v'))+list((PROJECT/'constraints').glob('*'))+[Path(__file__).resolve()]
    origin_hashes={str(p.relative_to(WORKSPACE)):sha(p) for p in origin_files}
    includes=[]
    for source in audio_sources():
        if source.is_relative_to(ORIGINAL):
            target=stage/'legacy'/source.relative_to(ORIGINAL)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            includes.append('`include "'+target.relative_to(stage).as_posix()+'"')
    (stage/'legacy_audio.sv').write_text('\n'.join(includes)+'\n')
    for source in rom_sources():
        target=stage/source.relative_to(ORIGINAL)
        if target.exists(): raise SystemExit(f'Refusing ROM collision: {target}')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    shutil.copytree(PROJECT/'rtl',stage/'src/migration')
    for suffix in ['cst','sdc']:
        shutil.copy2(PROJECT/'constraints'/('gw138k_audio.'+suffix),stage/'constraints'/('tang_mega_138k.'+suffix))
    # Adapt only the staged frequency axis and visible sample-rate/status text.
    # All FFT arithmetic/Hann/twiddle coefficients stay byte-for-byte identical.
    rom=stage/'src/video/audio_analysis_rom.v'; old=rom.read_text()
    new=old.replace('Fs=48,828.125 Hz.','Fs=48,000 Hz; migration frequency map.')
    def frequency(match):
        col=int(match[1]); bin_n=max(1,min(427,round(math.exp(math.log(427)*col/511))))
        return f"  9'd{col}: frequency_bin <= 9'd{bin_n};"
    new,count=re.subn(r"  9'd(\d+): frequency_bin <= 9'd\d+;",frequency,new)
    if count!=512: raise SystemExit('Unexpected frequency map format')
    rom.write_text(new)
    dash=stage/'src/video/feedback_dashboard.v'; old_dash=dash.read_text()
    new_dash=old_dash.replace('48828 HZ','48000 HZ').replace('UART','CORE').replace('10.49 MS','10.67 MS').replace('48                              ','47                              ')
    dash.write_text(new_dash)
    (out/'display_adaptation.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
        fromfile='original/audio_analysis_rom.v',tofile='candidate/audio_analysis_rom.v'))+
        ''.join(difflib.unified_diff(old_dash.splitlines(True),new_dash.splitlines(True),
        fromfile='original/feedback_dashboard.v',tofile='candidate/feedback_dashboard.v')))
    tree=ET.parse(stage/'Prj1.gprj'); files=tree.find('FileList')
    for item in list(files):
        path=item.attrib['path']
        keep=path.startswith(('src/video/','src/memory/','src/platform/','vendor/','constraints/')) or path in ['src/audio/pt8211_tx.v','src/audio/pt8211_observer.v','src/control/uart_tx.v']
        if args.managed_synthesis and path.startswith('constraints/'): keep=False
        if not keep: files.remove(item)
    ET.SubElement(files,'File',path='legacy_audio.sv',type='file.verilog',enable='1')
    for path in sorted((stage/'src/migration').glob('*')):
        ET.SubElement(files,'File',path=path.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    ET.indent(tree,space='    ');tree.write(stage/'Prj1.gprj',encoding='utf-8',xml_declaration=True)
    tcl=stage/'scripts/build.tcl'
    top='gw138k_managed_audio' if args.managed_synthesis else 'gw138k_audio_display_top'
    tcl.write_text(tcl.read_text().replace('-top_module prj1_top','-top_module '+top).replace('-verilog_std v2001','-verilog_std sysv2017'))
    frozen={str(p.relative_to(stage)):sha(p) for p in sorted(stage.rglob('*')) if p.is_file()}
    (out/'migration_inputs.json').write_text(json.dumps({'origin_sha256':origin_hashes,'staged_sha256':frozen,
        'device':'GW5AST-LV138PG484AC2/I1','sample_rate_hz':48000,'top_module':top,
        'physical_constraints_enabled':not args.managed_synthesis,
        'hardware_tested':False,'G1_candidate':'P16 / J9 pin 7; confirm physical connection before programming'},indent=2)+'\n')
    if args.prepare_only: print(stage);return
    sys.path.insert(0,str(TEAM/'scripts'))
    from gowin_paths import gowin_shell,gowin_simlib
    env=dict(os.environ,PRJ1_FLOW=args.flow,GOWIN_SIMLIB=str(gowin_simlib()),
        PRJ1_DDR_REFERENCE=str(out/'reference/ddr3_memory_interface.vo'))
    # Use the actual audited reference filename provided by the snapshot.
    refs=list((out/'reference').glob('*.vo'))
    if len(refs)!=1: raise SystemExit('Expected one audited DDR reference')
    env['PRJ1_DDR_REFERENCE']=str(refs[0])
    with (out/'gowin.log').open('w') as log:
        result=subprocess.run([str(gowin_shell()),'scripts/build.tcl'],cwd=stage,env=env,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode: raise SystemExit(f'Gowin failed: {out/"gowin.log"}')
    changed=[p for p,h in frozen.items() if sha(stage/p)!=h]
    if changed: raise SystemExit(f'Inputs changed during build: {changed}')
    if args.flow=='all':
        with (out/'check_build.log').open('w') as log:
            result=subprocess.run([sys.executable,'scripts/check_build.py'],cwd=stage,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode: raise SystemExit(f'Build audit failed: {out/"check_build.log"}')
        result=subprocess.run([sys.executable,PROJECT/'scripts/check_audio_build.py',stage,
            '--output',out/'audio_routed_audit.json'])
        if result.returncode: raise SystemExit('Additional audio PLL/CDC audit failed')
    if args.managed_synthesis:
        subprocess.run([sys.executable,PROJECT/'scripts/check_managed_synthesis.py',out,
            '--output',out/'managed_synthesis_audit.json'],check=True)
    (out/'migration_build.json').write_text(json.dumps({'flow':args.flow,'top_module':top,'gowin_exit_code':0,
        'existing_ddr_video_audit_pass':args.flow=='all','inputs_unchanged':True,'hardware_tested':False,
        'audio_pll_and_cdc_routed_review':'passed' if args.flow=='all' else 'not run'},indent=2)+'\n')
    print(out)

if __name__=='__main__': main()
