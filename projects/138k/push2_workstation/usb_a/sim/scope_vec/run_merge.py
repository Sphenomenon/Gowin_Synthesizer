#!/usr/bin/env python3
"""Offline scope/TF integration checks against staged full-workstation RTL.

Card/decoder and analysis-ready endpoints are behavioral test stimuli; these
checks do not claim to reverify the 172-frame Basic Pitch arithmetic or board.
Only logs and aggregate counters are saved; no sampled audio files or traces.
"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import resource
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('--test',choices=('tb_scope_dac_select','tb_scope_tf_coexist','tb_scope_tf_control','tb_scope_tf_play','tb_scope_xy','tb_scope_tf_bounds','tb_scope_workstation','tb_scope_tf_transport'))
    args=parser.parse_args()
    build=args.build.resolve();project=build/'Prj1'
    out=build/datetime.now().strftime('scope_merge_%Y%m%d_%H%M%S_%f')
    out.mkdir();print(out,flush=True)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    scope=project/'rtl/audio/scope_vec'
    for rel in ['scope_dac_select.sv','scope_vec_engine.sv','scope_control_player.sv']:
        assert (scope/rel).read_bytes()==(ROOT/'rtl/audio/scope_vec'/rel).read_bytes(), 'stale staged scope source: '+rel
    assert (project/'src/storage/tf_workstation_audio_bridge.v').read_bytes()==(ROOT/'rtl/tf_audio/tf_workstation_audio_bridge.v').read_bytes()
    sources=[project/f.get('path') for f in ET.parse(project/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
    audio_sources=[p for p in sources if not any(x in p.relative_to(project).as_posix() for x in
        ['vendor/','src/memory/','src/storage/','src/platform/','src/top/','src/usb_a/','rtl/music/',
         'src/ae350/riscv_','workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
    audio_sources += [project/'rtl/music/music_async_fifo.sv']
    # The USB/CPU lifecycle arbiter belongs to the managed audio path even
    # though it is stored next to the USB MMIO block. Older stages lack it.
    audio_sources += [p for p in sources if p.name=='gw138k_usb_lifecycle_merge.sv']
    tests={
        'tb_scope_dac_select':[project/'src/audio/pt8211_tx.v',project/'src/audio/tf_rate_pt8211_tx.v',
            project/'src/audio/pt8211_observer.v',scope/'scope_dac_select.sv'],
        'tb_scope_workstation':audio_sources,
        'tb_scope_tf_transport':[scope/'scope_tf_transport.sv'],
        'tb_scope_tf_control':[scope/'scope_tf_control.sv'],
        'tb_scope_tf_play':[project/'src/audio/pt8211_tx.v',project/'src/audio/tf_rate_pt8211_tx.v',
            project/'src/audio/pt8211_observer.v',project/'src/migration/gw138k_stream_cdc.sv',
            scope/'scope_dac_select.sv',project/'src/storage/tf_async_pcm_fifo.v',
            project/'src/storage/tf_workstation_audio_bridge.v',HERE/'tf_decoder_endpoint.sv'],
        'tb_scope_tf_bounds':list((project/'src/storage/tang_mp3/sd').glob('*.v'))+
            list((project/'src/storage/tang_mp3/vendor').glob('*.v')),
        'tb_scope_xy':[project/'src/video/output_audio_analysis.v',project/'src/video/output_audio_capture.v',
            project/'src/video/audio_analysis_rom.v'],
        'tb_scope_tf_coexist':audio_sources+[project/'src/audio/tf_rate_pt8211_tx.v',
            project/'src/storage/tf_async_pcm_fifo.v',project/'src/storage/tf_workstation_audio_bridge.v',
            HERE/'tf_decoder_endpoint.sv'],
    }
    if args.test:tests={args.test:tests[args.test]}
    result={'passed':False,'hardware_tested':False,'sample_streams_persisted':0,'audio_files_created':0,
            'limitations':['behavioral card/decoder and analysis consumer','CNN arithmetic not rerun'],
            'metrics':{},'tests':{},'inputs':{}}
    try:
        for top,inputs in tests.items():
            inputs=list(dict.fromkeys(inputs+[HERE/(top+'.sv')]))
            for p in inputs:result['inputs'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
            binary=out/(top+'_obj')/('V'+top)
            cmd=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',top,
                 '--Mdir',str(binary.parent),'-I'+str(project),*map(str,inputs)]
            with (out/(top+'_compile.log')).open('w') as log:
                r=subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT)
            if r.returncode:
                print((out/(top+'_compile.log')).read_text()[-6000:]);raise RuntimeError(top+' compile failed')
            r=subprocess.run([str(binary)],cwd=project,capture_output=True,text=True,timeout=300)
            text=r.stdout+r.stderr
            (out/(top+'_summary.log')).write_text(text)
            if r.returncode or 'PASS '+top.removeprefix('tb_') not in text:
                print(text[-5000:]);raise RuntimeError(top+' simulation failed')
            for line in text.splitlines():
                if line.startswith('M '):
                    _,name,value=line.split();result['metrics'][name]=int(value)
            result['tests'][top]='passed';print(top,'PASS',flush=True)
        result['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['metrics'],indent=2))


if __name__=='__main__':
    main()
