#!/usr/bin/env python3
"""Accepted-full83 scope merge gates. No board access or PCM output in checkout."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def run(command,cwd,log,timeout=600):
    with log.open('w') as output:
        result=subprocess.run(command,cwd=cwd,stdout=output,stderr=subprocess.STDOUT,timeout=timeout)
    if result.returncode:
        raise RuntimeError(log.read_text()[-6000:])
    return log.read_text()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('--skip-merge',action='store_true',help='Use an already-passed matching scope_merge report')
    args=parser.parse_args()
    build=args.build.resolve();project=build/'Prj1'
    out=build/datetime.now().strftime('current_regression_%Y%m%d_%H%M%S_%f');out.mkdir()
    print(out,flush=True)
    metadata=json.loads((build/'build_metadata.json').read_text())
    for path,digest in metadata['music_sha256'].items():
        assert hashlib.sha256((project/path).read_bytes()).hexdigest()==digest,'stale accepted music: '+path
    result=dict(passed=False,hardware_tested=False,tests={},pcm_files_created_in_checkout=0)
    try:
        if not args.skip_merge:
            text=run([sys.executable,str(HERE/'run_merge.py'),str(build)],project,out/'scope_merge.log')
            print(text,flush=True)
        scope_reports=sorted(build.glob('scope_merge_*/verification.json'),reverse=True)
        scope=next((p for p in scope_reports if json.loads(p.read_text())['passed'] and
                    len(json.loads(p.read_text())['tests'])==8),None)
        assert scope is not None,'complete 8-test scope merge report required'
        scope_record=json.loads(scope.read_text())
        for name,digest in scope_record['inputs'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,'stale scope gate: '+name
        result['scope_merge']=str(scope.relative_to(build));result['tests'].update(scope_record['tests'])
        checks={
            'tb_scope_push':[project/'src/push2/push2_controls.sv'],
            'tb_playlist_hold':[project/'src/push2/push2_playlist_hold.sv'],
            'tb_tf_hotplug_probe':[project/'src/storage/tang_mp3/sd/tf_sd_file_reader.v'],
            'tb_song_menu':[project/'src/usb_a/push2_song_menu.sv'],
            'tb_playlist_bridge':[project/'rtl/music/tf_playlist_bridge.sv',project/'rtl/music/music_async_fifo.sv'],
            'tb_guidance':[project/'src/push2/push2_controls.sv',project/'src/push2/push2_lights.sv',
                           project/'src/usb_a/push2_score_guide.sv'],
            'tb_score_stream':[project/'src/usb_a/push2_score_guide.sv'],
        }
        for name,sources in checks.items():
            tb=HERE/(name+'.sv') if name=='tb_scope_push' else ROOT/'sim/guidance'/(name+'.sv')
            binary=out/(name+'.vvp');log=out/(name+'.log')
            text=run(['iverilog','-g2012','-s',name,'-o',str(binary),*map(str,sources),str(tb)],project,log)
            text+=run(['vvp',str(binary)],project,out/(name+'_run.log'))
            assert 'PASS' in text,name+' missing PASS'
            result['tests'][name]='passed';print(name,'PASS',flush=True)
        # Legacy compressed MP3 fixture stays in a temporary external directory;
        # regression evidence and hashes alone are retained in the build.
        with tempfile.TemporaryDirectory(prefix='tf_scope_regression_') as directory:
            external=Path(directory)
            text=run([sys.executable,str(ROOT/'sim/tf_audio/run.py'),'--output',str(external)],ROOT,out/'tf_audio.log')
            summary=(external/'build/summary.txt').read_text().splitlines()
            assert len(summary)==16,'TF suite size changed: review coverage'
            result['tests']['tf_audio_16']='passed'
            result['tf_audio_summary']=summary
            (out/'tf_inputs_sha256.json').write_bytes((external/'inputs_sha256.json').read_bytes())
            for path in (external/'build').glob('*.log'):
                (out/path.name).write_bytes(path.read_bytes())
            print('TF audio 16/16 PASS',flush=True)
        text=run([sys.executable,str(ROOT/'sim/audio/run_delay_ddr_equivalence.py'),'--output',str(out/'delay_ddr')],ROOT,out/'delay_ddr.log')
        assert 'PASS' in text
        result['tests']['delay_ddr_equivalence']='passed';print('Delay DDR equivalence PASS',flush=True)
        isolation=out/'ddr_isolation'
        text=run([sys.executable,str(ROOT/'sim/music/run_bp_ddr_isolation.py'),'--output',str(isolation)],ROOT,out/'ddr_isolation.log')
        records=json.loads((isolation/'summary.json').read_text())
        assert {r['case'] for r in records}=={'old_map','new_map'}
        assert all(r['expected_behavior_confirmed'] for r in records)
        result['tests']['bp_ddr_isolation']='passed';print('DP/delay DDR isolation PASS',flush=True)
        result['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],gates=len(result['tests'])),indent=2))


if __name__=='__main__':main()
