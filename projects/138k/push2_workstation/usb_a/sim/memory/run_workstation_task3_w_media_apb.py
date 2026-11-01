#!/usr/bin/env python3
"""Native W-media real model boot plus independent owner8 recording readback."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'sim/music'))
from run_bp_config_ab import MUSIC_SOURCES
from tools.build_cnn_flash_image import build_image,load_words
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    header=out/'include/src/memory/ddr_address_map.vh';header.parent.mkdir(parents=True)
    header.write_bytes((ROOT/'rtl/ddr_address_map.vh').read_bytes())
    image,manifest=build_image(load_words(ROOT/'rtl/music/weights/cnn_ddr_blob.mem'))
    if manifest['payload_crc32']!='AF01A61B' or manifest['word_count']!=52239:raise ValueError('real model drift')
    image_path=out/'real_model_spi.hex';image_path.write_text('\n'.join(f'{b:02x}'for b in image)+'\n')
    music=['basic_pitch_nn_ddr.sv',*(n for n in MUSIC_SOURCES if n!='basic_pitch_nn_ddr.sv'),
           'basic_pitch_workstation_link.sv','basic_pitch_link_uart.sv','basic_pitch_ddr16_port.sv',
           'basic_pitch_ddr_command_buffer.sv','music_async_fifo.sv','workstation_cnn_ddr_broker.sv',
           'workstation_cnn_task_service.sv','basic_pitch_ddr_client_queues.sv','basic_pitch_ddr_arbiter_pipeline.sv']
    memory=['workstation_sdp.sv','workstation_ddr_bist.v','workstation_recording_ddr_client_queues.sv',
            'workstation_recording_ddr_arbiter_pipeline.sv','workstation_recording_ddr_native_bridge.sv',
            'workstation_media_memory.sv','workstation_ble_raw_ddr_store.sv']
    sources=[*(ROOT/'rtl/music'/n for n in music),*(ROOT/'rtl/memory'/n for n in memory),
        ROOT/'rtl/ddr_address_map_guard.v',ROOT/'rtl/workstation/workstation_task3_w_media.sv',ROOT/'rtl/services/workstation_task3_media_apb_service.sv',ROOT.parent/'touchboard_test/rtl/uart_tx.v',
        ROOT/'sim/memory/tb_workstation_task3_w_media_apb.sv']
    inputs=[*sources,ROOT/'rtl/ddr_address_map.vh',ROOT/'rtl/music/weights/cnn_ddr_blob.mem',Path(__file__).resolve()]
    hashes={str(p):sha(p)for p in inputs}
    result=dict(schema=1,passed=False,stage='actual_native_W_media_APB_task_entry',source_sha256=hashes,
        model_manifest=manifest,source_overlay=False,production_dimensions_unchanged=True,
        actual_model_boot=True,actual_recording_frames=24,recording_capacity_frames=2880000,
        full_60s_recording_in_this_test=False,CNN_inference_in_this_test=False,
        HCI_engine_in_this_test=False,actual_APB_task_frames=8,actual_APB_native_CRC_seal=True,phone_or_LCD_transport_in_this_test=False,
        board_profile_selected=False,synthesis=False,place_and_route=False,hardware_operated=False,
        SRAM_programmed=False,Flash_written=False)
    started=time.monotonic()
    try:
        argv=['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal',
            '--top-module','tb_workstation_task3_w_media_apb','--Mdir',str(out/'obj'),
            '-I'+str(out/'include'),'-I'+str(ROOT),'-I'+str(ROOT/'rtl/music'),*map(str,sources)]
        result['build_argv']=argv
        with(out/'build.log').open('w')as log:p=subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        result.update(build_exit=p.returncode,build_log_sha256=sha(out/'build.log'))
        if p.returncode:raise RuntimeError('W-media build failed: '+str(out/'build.log'))
        print('built actual native W-media + unchanged real CNN + unique raw store',flush=True)
        with(out/'run.log').open('w')as log:
            with subprocess.Popen([str(out/'obj/Vtb_workstation_task3_w_media_apb'),'+IMAGE='+str(image_path)],cwd=ROOT,
                    text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)as process:
                lines=[]
                for line in process.stdout:log.write(line);log.flush();lines.append(line);print(line,end='',flush=True)
                code=process.wait()
        text=''.join(lines)
        result.update(run_exit=code,run_log_sha256=sha(out/'run.log'),log=text,
            metrics={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',text)},elapsed_seconds=round(time.monotonic()-started,3))
        if code or 'PASS actual_task3_W_media_APB'not in text:raise RuntimeError('actual W-media failed: '+str(out/'run.log'))
        result['source_unchanged_during_run']=hashes=={str(p):sha(p)for p in inputs}
        if not result['source_unchanged_during_run']:raise ValueError('source drift during W-media simulation')
        result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
