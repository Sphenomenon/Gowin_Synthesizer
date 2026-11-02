#!/usr/bin/env python3
"""Offline M analysis arbitration; deterministic native cursor, real service."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
SOURCES=('rtl/tf_audio/workstation_tf_direct_runtime_service.sv',
         'rtl/tf_audio/workstation_tf_frame_bridge_v2.sv','rtl/music/music_async_fifo.sv',
         'rtl/services/workstation_playback_service.sv',
         'sim/tf_audio/tb_workstation_tf_remote_analysis.sv')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    sys.path.insert(0,str(ROOT))
    from tools.workstation_task3_m_paired_profile import apply_top,inverse_top,DEPENDENCIES
    inputs=tuple(dict.fromkeys((*SOURCES,*DEPENDENCIES,
          'rtl/workstation/gw138k_push_workstation_top.v',str(Path(__file__).resolve().relative_to(ROOT)))))
    result=dict(schema=1,passed=False,input_sha256={p:sha(ROOT/p) for p in inputs},
        actual_analysis_runtime_service=True,actual_frame_bridge=True,
        native_file_owner='deterministic held-cursor fixture',actual_SPI_FAT_WAV=False,
        actual_CNN=False,actual_physical_serializer=False,physical_CDC_verified=False,
        hardware_operated=False,deployment_allowed=False)
    try:
        top=(ROOT/'rtl/workstation/gw138k_push_workstation_top.v').read_text()
        selected=apply_top(ROOT,top)
        if inverse_top(ROOT,selected)!=top:raise ValueError('M adapter roundtrip failed')
        negatives=0
        for text,operation in ((top+'\n',apply_top),
                (top.replace('wire reset_n;','wire reset_n; // drift',1),apply_top),
                (selected+'\n',inverse_top),
                (selected.replace('`include "rtl/workstation/workstation_task3_m_paired_board.svh"','',1),inverse_top),
                (selected.replace('REMOTE_PCM_COMMAND_ENABLE(1)','REMOTE_PCM_COMMAND_ENABLE(0)',1),inverse_top)):
            try:operation(ROOT,text)
            except ValueError:negatives+=1
            else:raise ValueError('M adapter accepted changed identity')
        result['adapter_negative_controls']=negatives
        command=['iverilog','-g2012','-s','tb_workstation_tf_remote_analysis','-o',str(output/'simulation.vvp'),
                 *[str(ROOT/p) for p in SOURCES]]
        result['compile_argv']=command
        cp=subprocess.run(command,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (output/'compile.log').write_text(cp.stdout)
        if cp.returncode:raise RuntimeError('iverilog failed')
        cp=subprocess.run(['vvp',str(output/'simulation.vvp')],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (output/'simulation.log').write_text(cp.stdout);print(cp.stdout,end='')
        matched=re.search(r'PASS tf_remote_analysis checks=(\d+) scenarios=(\d+)',cp.stdout)
        if cp.returncode or not matched:raise RuntimeError('analysis arbitration fixture failed')
        result.update(passed=True,checks=int(matched[1]),scenarios=int(matched[2]))
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')

if __name__=='__main__':main()
