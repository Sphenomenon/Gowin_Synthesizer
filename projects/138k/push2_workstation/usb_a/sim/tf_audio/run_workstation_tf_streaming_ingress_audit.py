#!/usr/bin/env python3
"""Replay a fixed historical TF ingress audit; no product build or migration."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
REPOSITORY=ROOT.parents[3]
REVISION='4e0dc6cf250896aeb22a4af1f8450b3a20694279'
PREFIX='projects/138k/push2_workstation/usb_a/'
SECTOR='rtl/tf_audio/storage/tang_mp3/vendor/tf_sd_spi_sector_reader.v'
SECTOR_SHA256='259bedb80a6a54cf2048ae6cb2f40ec384108ae2743acb49b8acb70abf126504'
AUDITED_INPUTS=(
    'rtl/tf_audio/workstation_tf_runtime_service.sv',
    'rtl/tf_audio/storage/tf_audio_ddr_path.v',
    'rtl/tf_audio/storage/tf_sd_audio_pcm_player.v',
    'rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v',SECTOR,
    'rtl/tf_audio/storage/tang_mp3/vendor/tf_spi_session.v',
    'rtl/tf_audio/storage/tang_mp3/audio/audio_fifo.v',
    'rtl/tf_audio/storage/tf_audio_decoder_ip.v',
    'rtl/tf_audio/storage/tf_wav_pcm_decoder.v',
    'rtl/tf_audio/storage/tf_wav_chunk_parser.v',
    'rtl/tf_audio/workstation_tf_frame_bridge.sv',
    'rtl/audio/workstation_final_pcm_router.sv',
    'rtl/workstation/gw138k_push_workstation_top.v',
    'rtl/workstation/workstation_profile_runtime.sv',
    'tools/workstation_runtime_profile.py',
    'boards/custom_138k/workstation_profile_v1.json',
    'baselines/resource_rework_route0.json',
)

def sha(data):return hashlib.sha256(data).hexdigest()

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    fixture=Path(__file__).with_name('tf_sector_duplicate_command_audit_tb.sv')
    maintained={str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in (Path(__file__).resolve(),fixture)}
    blobs={}
    for name in AUDITED_INPUTS:
        fetched=subprocess.run(['git','show',REVISION+':'+PREFIX+name],cwd=REPOSITORY,capture_output=True,check=True)
        blobs[name]=fetched.stdout
    source_hashes={name:sha(data) for name,data in blobs.items()}
    if source_hashes[SECTOR]!=SECTOR_SHA256:raise ValueError('Fixed historical sector identity mismatch')
    baseline=json.loads(blobs['baselines/resource_rework_route0.json'])
    profile=json.loads(blobs['boards/custom_138k/workstation_profile_v1.json'])
    locked_identity={}
    for name in (SECTOR,'rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v',
                 'rtl/tf_audio/storage/tang_mp3/vendor/tf_spi_session.v',
                 'rtl/tf_audio/storage/tf_sd_audio_pcm_player.v'):
        original='src/storage/'+name.removeprefix('rtl/tf_audio/storage/')
        expected=baseline['files'][original]['sha256']
        if source_hashes[name]!=expected:raise ValueError('Historical locked-source identity mismatch: '+name)
        locked_identity[name]=dict(baseline_entry=original,sha256=expected)
    sector=output/'fixed_tf_sd_spi_sector_reader.v'
    sector.write_bytes(blobs[SECTOR])
    inputs=dict(revision=REVISION,fixed_source_sha256=source_hashes,maintained_test_sha256=maintained)
    identity=sha(json.dumps(inputs,sort_keys=True).encode())
    result=dict(schema=1,passed=False,identity='native-tf-streaming-ingress-audit-v1-'+identity[:16],
        source_set_sha256=identity,inputs=inputs,locked_source_identity=locked_identity,
        source_policy='git show of one fixed committed revision; never read live product RTL or staging fallback',
        implementation_complete=False,m03_complete=False,product_rtl_changed=False,profile_changed=False,
        declared_profile=dict(name=profile['name'],revision=profile['revision'],configuration=profile['configuration']),
        profile_prepare_executed=False,profile_input_locks_verified=False,
        synthesis=False,pnr=False,wire_level_verified=False,hardware_tested=False,sram_programmed=False,flash_written=False,
        limits='Actual historical sector control FSM with initialized SDHC/IDLE deposit and successful SPI-session stub. No card initialization, real SPI session, wire-level timing, SD throughput measurement, or no-DDR product implementation.')
    def execute(name,source,expect_pass):
        compile_command=['iverilog','-g2012','-Wall','-s','tb_tf_sector_duplicate_command_audit',
            '-o',str(output/(name+'.vvp')),str(source),str(fixture)]
        compiled=subprocess.run(compile_command,cwd=output,capture_output=True,text=True,timeout=30)
        compile_log=compiled.stdout+compiled.stderr;(output/(name+'_compile.log')).write_text(compile_log)
        if compiled.returncode:raise RuntimeError(compile_log)
        run_command=['vvp',str(output/(name+'.vvp'))]
        executed=subprocess.run(run_command,cwd=output,capture_output=True,text=True,timeout=30)
        log=executed.stdout+executed.stderr;(output/(name+'_run.log')).write_text(log)
        result[name]=dict(compile_argv=compile_command,run_argv=run_command,returncode=executed.returncode,
            source_sha256=sha(source.read_bytes()),compile_log_sha256=sha(compile_log.encode()),
            compile_log=compile_log,run_log_sha256=sha(log.encode()),run_log=log,
            metrics={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',log)})
        if expect_pass:
            if executed.returncode or 'PASS tf_sector_duplicate_command_audit:' not in log:raise RuntimeError(log)
            print(log,end='')
        else:
            rejected=executed.returncode!=0 and 'historical sector audit mismatch' in log
            result[name]['rejected']=rejected
            if not rejected:raise ValueError('Forward-both-sessions negative escaped: '+log)
    try:
        execute('historical_sector',sector,True)
        text=blobs[SECTOR].decode()
        anchor='if(cardstate==READING && rvalid_session &&'
        if text.count(anchor)!=1:raise ValueError('Fixed historical forwarding anchor mismatch')
        mutant=output/'forward_both_sessions_negative.v'
        mutant.write_text(text.replace(anchor,'if((cardstate==IDLE || cardstate==READING) && rvalid_session &&'))
        execute('forward_both_sessions_negative',mutant,False)
        result['divider_budget']=[]
        for divider in (12,6,3,2):
            raw=50_000_000/(16*(divider+1))
            optimistic=raw*512/(2*(512+255))
            result['divider_budget'].append(dict(divider=divider,spi_hz=raw*8,raw_Bps=raw,
                fixed_40000_token_wait_ms=40000/raw*1000,
                optimistic_old_transport_payload_Bps=optimistic,
                optimistic_one_sector_cluster_with_FAT_Bps=optimistic/2))
        result['throughput_derivation']='R_file <= (f_spi/8)*512/[2*(512+255)]. Ignores commands, response/token waits, CRC and other overhead; one extra FAT sector per one-sector cluster halves this optimistic bound.'
        result['pcm_budget']=[]
        for rate in (48000,44100):
            result['pcm_budget'].append(dict(sample_rate_hz=rate,
                WAV_stereo_input_Bps={str(bits):rate*2*bits//8 for bits in (8,16,24,32)},
                decoded_PCM16_Bps=rate*4,proposed_50ms_deficit_frames=math.ceil(rate*.05),
                proposed_50ms_deficit_bytes=4*math.ceil(rate*.05),
                proposed_3072_frame_prefill_ms=3072/rate*1000,
                proposed_4096_frame_capacity_ms=4096/rate*1000))
        result['proposed_health_example_not_acceptance']=dict(
            max_cumulative_PCM_deficit_ms=50,PCM_capacity_frames=4096,prefill_frames=3072,
            source_byte_FIFO_bytes=4096,FAT_cache_bytes=512,shallow_metadata_bridge_frames=16,
            estimated_capacity_BSRAM_blocks=dict(old_two_4KiB_byte_FIFOs=4,
                new_4KiB_byte_FIFO_plus_16KiB_PCM_plus_512B_FAT=11,net_addition=7),
            assumptions='50ms is a proposed qualification target for maximum cumulative decoded PCM deficit, with enough sustained recovery throughput. It is not a measured SD guarantee or permission for every sector to stall50ms. BSRAM counts are storage-capacity estimates, not synthesis or physical mapping.')
        result['test_inputs_unchanged_during_run']=maintained=={
            str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in (Path(__file__).resolve(),fixture)}
        if not result['test_inputs_unchanged_during_run']:raise ValueError('Maintained audit test drift')
        result['passed']=True
    finally:
        (output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
